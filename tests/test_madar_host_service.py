"""Isolated Windows native host process lifecycle/security integration.

Never registers/starts an OS service or uses a user's actual APPDATA. Real
TLS and temporary task data verify host behavior without GUI or SCM writes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import subprocess
import base64
import tempfile
import threading
import unittest
from unittest.mock import patch

import madar_host_service as host
import native_app
from offline_exchange import atomic_json
from lan import pinned_https_json


class HostServiceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="madar-native-service-qa-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.data = self.root / "host-data"
        self.tls = self.data / "tls"
        self.tls.mkdir(parents=True)
        source = runpy.run_path(str(Path(__file__).with_name("test_lan_tls.py")))
        (self.tls / "cert.pem").write_text(source["_CERT"], encoding="ascii")
        (self.tls / "key.pem").write_text(source["_KEY"], encoding="ascii")
        # Even a mistaken default native_app.datadir() points only to temp.
        environment = patch.dict(os.environ, {
            "APPDATA": str(self.root / "user-appdata"),
            "LOCALAPPDATA": str(self.root / "user-local"),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.password = "temporary-host-password-for-qa"

    def provision(self):
        return host.provision_authority(
            self.data, "hostadmin",
            password_reader=lambda _prompt: self.password)

    def run_in_thread(self, *, port=0, bind="127.0.0.1"):
        stop = threading.Event()
        ready = threading.Event()
        details = {"error": None, "port": None}

        def on_ready(chosen):
            details["port"] = chosen
            ready.set()

        def worker():
            try:
                host.run_host_service(self.data, stop, port=port, bind=bind,
                                      on_ready=on_ready)
            except Exception as exc:
                details["error"] = exc
                ready.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self.addCleanup(lambda: (stop.set(), thread.join(timeout=8)))
        self.assertTrue(ready.wait(10), "Service did not become ready")
        if details["error"]:
            raise details["error"]
        self.assertTrue(thread.is_alive())
        return stop, thread, details

    def request_tls(self, port, path, *, body=None, token=None, fingerprint=None):
        return pinned_https_json(
            f"https://127.0.0.1:{port}{path}",
            fingerprint or host.check_authority(self.data)["fingerprint"],
            method="POST" if body is not None else "GET",
            data=body,
            headers={"Authorization": "Bearer " + token} if token else {})

    def test_provision_new_authority_with_password_hash_not_plaintext(self):
        result = self.provision()
        self.assertEqual(result["dataRoot"], str(self.data))
        self.assertEqual(len(result["fingerprint"]), 64)
        accounts = (self.data / "lan-users.json").read_text(encoding="utf8")
        self.assertNotIn(self.password, accounts)
        self.assertIn("passwordHash", accounts)
        self.assertTrue((self.data / "tasks.json").exists())
        self.assertEqual(
            json.loads((self.data / "tasks.json").read_text(encoding="utf8"))["tasks"],
            [], "A freshly provisioned real host must start with no sample cards")
        self.assertFalse((self.data / "lan-connection.json").exists())
        self.assertFalse((self.root / "user-appdata").exists())
        with self.assertRaisesRegex(RuntimeError, "existing Madar data"):
            self.provision()

    def test_existing_gui_data_is_never_adopted_or_migrated(self):
        old = self.root / "old-gui"
        old.mkdir()
        old_task = old / "tasks.json"
        old_task.write_text('{"tasks": "valuable"}', encoding="utf8")
        with self.assertRaises(RuntimeError):
            host.provision_authority(old, "hostadmin",
                                     password_reader=lambda _: self.password)
        self.assertEqual(old_task.read_text(encoding="utf8"), '{"tasks": "valuable"}')
        guiroot = Path(os.environ["APPDATA"]) / "MadarDesk"
        with self.assertRaisesRegex(ValueError, "GUI APPDATA"):
            host.provision_authority(guiroot, "hostadmin",
                                     password_reader=lambda _: self.password)
        self.assertFalse(guiroot.exists())

    def test_missing_tls_or_mismatched_password_fails_without_account(self):
        (self.tls / "key.pem").unlink()
        with self.assertRaises(ValueError):
            self.provision()
        self.assertFalse((self.data / "lan-users.json").exists())
        self.assertFalse((self.data / host.AUTHORITY_NAME).exists())

    def test_reject_gui_connection_and_corrupt_authority_before_start(self):
        self.provision()
        connection = self.data / "lan-connection.json"
        connection.write_text('{"mode": "server"}', encoding="utf8")
        with self.assertRaisesRegex(RuntimeError, "GUI LAN configuration"):
            host.check_authority(self.data)
        connection.unlink()
        marker = self.data / host.AUTHORITY_NAME
        saved = marker.read_bytes()
        marker.write_text('{"schema": 1, "kind": "client"}', encoding="utf8")
        with self.assertRaises(ValueError):
            host.check_authority(self.data)
        marker.write_bytes(saved)

    def test_tls_server_survives_gui_absence_and_preserves_saved_state(self):
        details = self.provision()
        # This persistence test edits a card; provision correctly creates an
        # EMPTY real host. Seed sample cards only in this disposable fixture.
        atomic_json(self.data / "tasks.json",
                    native_app.normalize_state(native_app.initial_state()))
        stop, thread, running = self.run_in_thread()
        port = running["port"]
        token = self.request_tls(port, "/api/login", body={
            "username": "hostadmin", "password": self.password})["token"]
        original = self.request_tls(port, "/api/state", token=token)
        self.assertEqual(len(original["state"]["tasks"]), 4)
        data = original["state"]
        data["tasks"][0]["title"] = "Host-owned persistent update"
        self.request_tls(port, "/api/state",
                 body={"state": data, "revision": original["revision"]},
                 token=token)
        self.assertEqual(self.request_tls(port, "/api/state", token=token)["state"]["tasks"][0]["title"],
                         "Host-owned persistent update")
        # Host still responds when no pywebview window exists.
        self.assertTrue(thread.is_alive())
        self.assertFalse((self.root / "user-appdata").exists())
        stop.set()
        thread.join(timeout=8)
        self.assertFalse(thread.is_alive())
        self.assertIsNone(running["error"])
        from standalone_accounting_auto_backup import BACKUP_FOLDER
        finance_backups = self.data / BACKUP_FOLDER
        self.assertTrue(finance_backups.is_dir())
        self.assertGreaterEqual(len(list(finance_backups.glob("*.sqlite3"))), 1)
        self.assertTrue((self.data / "backups").is_dir())
        stop2, thread2, restarted = self.run_in_thread()
        token2 = self.request_tls(restarted["port"], "/api/login", body={
            "username": "hostadmin", "password": self.password},
                          fingerprint=details["fingerprint"])["token"]
        self.assertEqual(self.request_tls(restarted["port"], "/api/state", token=token2)
                         ["state"]["tasks"][0]["title"], "Host-owned persistent update")
        stop2.set()
        thread2.join(timeout=8)

    def test_duplicate_host_lock_rejected_without_writer_fallback(self):
        self.provision()
        stop, thread, running = self.run_in_thread()
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            host.run_host_service(self.data, threading.Event(), port=0,
                                  bind="127.0.0.1")
        self.assertTrue(thread.is_alive())
        token = self.request_tls(running["port"], "/api/login", body={
            "username": "hostadmin", "password": self.password})["token"]
        self.assertTrue(self.request_tls(running["port"], "/api/state", token=token)["state"])
        stop.set()
        thread.join(timeout=8)

    def test_same_https_port_with_separate_authorities_fails_closed(self):
        self.provision()
        stop, thread, running = self.run_in_thread()
        another_root = self.root / "another-host"
        another_tls = another_root / "tls"
        another_tls.mkdir(parents=True)
        (another_tls / "cert.pem").write_bytes((self.tls / "cert.pem").read_bytes())
        (another_tls / "key.pem").write_bytes((self.tls / "key.pem").read_bytes())
        host.provision_authority(another_root, "hostadmin",
                                 password_reader=lambda _: self.password)
        before = (another_root / "tasks.json").read_bytes()
        with self.assertRaises(OSError):
            host.run_host_service(another_root, threading.Event(),
                                  port=running["port"], bind="127.0.0.1")
        self.assertEqual((another_root / "tasks.json").read_bytes(), before)
        self.assertTrue(thread.is_alive())
        stop.set()
        thread.join(timeout=8)

    def test_service_mode_requires_real_scm_and_installers_are_opt_in(self):
        self.assertEqual(host.SERVICE_NAME, "MadarHost")
        install = (Path(__file__).parents[1] / "scripts" /
                   "Install-MadarHostService.ps1").read_text(encoding="utf8")
        remove = (Path(__file__).parents[1] / "scripts" /
                  "Remove-MadarHostService.ps1").read_text(encoding="utf8")
        self.assertIn("NT SERVICE\\MadarHost", install)
        self.assertIn("sidtype", install)
        self.assertIn("ShouldProcess", install)
        self.assertIn("ShouldProcess", remove)
        self.assertIn("sc.exe delete", remove)
        self.assertNotIn("Remove-Item", remove)
        self.assertNotIn("password=", install.lower())
        self.assertIn("HostExe", install)
        self.assertIn("Profile Private", install.replace("-Profile Private", "Profile Private"))
        self.assertIn("LocalSubnet", install)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell parser required")
    def test_install_and_remove_powershell_are_syntax_valid_without_execution(self):
        for filename in ("Install-MadarHostService.ps1", "Remove-MadarHostService.ps1"):
            with self.subTest(script=filename):
                script = Path(__file__).parents[1] / "scripts" / filename
                powershell_path = "'" + str(script).replace("'", "''") + "'"
                command = (
                    "$tokens=$null; $errs=@(); "
                    "[System.Management.Automation.Language.Parser]::ParseFile("
                    + powershell_path + ",[ref]$tokens,[ref]$errs) | Out-Null; "
                    "if($errs.Count -gt 0){ $errs | ForEach-Object Message; exit 1 }; exit 0"
                )
                encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive",
                     "-EncodedCommand", encoded], capture_output=True, text=True,
                    timeout=15)
                self.assertEqual(result.returncode, 0,
                                 result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
