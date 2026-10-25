"""Offline maintenance entrypoint tests, entirely within disposable directories."""

import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from app_storage import UnifiedAppStorage
from full_recovery import _journal_path
from maintenance_recovery import (MaintenanceRefused, _maintenance_lock,
                                  _running_madar_processes as REAL_PROCESS_SCANNER,
                                  execute, main,
                                  pending_restore_journal)
from native_app import initial_state


class OfflineMaintenanceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="madar-maintenance-test-")
        self.addCleanup(folder.cleanup)
        self.parent = Path(folder.name)
        self.root = self.parent / "test-app-data"
        self.root.mkdir()
        self.backups = self.parent / "local-private-backups"
        self.backups.mkdir()
        self.archive = self.backups / "first.zip"
        (self.root / "tasks.json").write_text(
            json.dumps(initial_state(), ensure_ascii=False), encoding="utf8")
        self.original = (self.root / "tasks.json").read_bytes()
        # Other agents may have the REAL Madar EXE open during this synthetic
        # test. All in-process tests substitute an empty process inventory;
        # dedicated detection tests exercise the actual decision logic.
        guard = patch("maintenance_recovery._running_madar_processes", return_value=[])
        guard.start()
        self.addCleanup(guard.stop)

    def run_cli(self, command, archive=None, *, offline=True, ack=True):
        args = [command, "--data-root", str(self.root)]
        if archive is not None:
            args += ["--archive", str(archive)]
        if offline:
            args.append("--confirm-offline")
        if ack and command != "recover":
            args.append("--acknowledge-plaintext")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = main(args)
        return status, out.getvalue(), err.getvalue()

    def test_direct_backup_restore_recover_preserves_backup_first_original(self):
        result = execute("backup", self.root, self.archive,
                         offline_confirmed=True, plaintext_acknowledged=True)
        self.assertTrue(self.archive.is_file())
        self.assertGreaterEqual(result["files"], 1)
        edited = json.loads((self.root / "tasks.json").read_text(encoding="utf8"))
        edited["tasks"][0]["title"] = "changed after backup"
        (self.root / "tasks.json").write_text(json.dumps(edited), encoding="utf8")
        restored = execute("restore", self.root, self.archive,
                           offline_confirmed=True, plaintext_acknowledged=True)
        self.assertEqual((self.root / "tasks.json").read_bytes(), self.original)
        self.assertEqual(
            json.loads((Path(restored["preRestoreRoot"]) / "tasks.json").read_text(encoding="utf8"))
            ["tasks"][0]["title"], "changed after backup")
        self.assertTrue(Path(restored["preRestoreArchive"]).is_file())
        self.assertEqual(execute("recover", self.root, offline_confirmed=True),
                         {"recovered": False})

    def test_actual_cli_subprocess_round_trip_or_refuses_live_madar(self):
        command = [sys.executable, "-m", "maintenance_recovery"]
        script = Path(__file__).resolve().parents[1]
        env = {**os.environ, "APPDATA": str(self.parent / "unrelated-appdata"),
               "LOCALAPPDATA": str(self.parent / "unrelated-localappdata")}
        result = subprocess.run(command + [
            "backup", "--data-root", str(self.root), "--archive", str(self.archive),
            "--confirm-offline", "--acknowledge-plaintext"],
            cwd=script, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=45)
        if result.returncode == 3 and "Madar processes are still running" in result.stderr:
            # A truly independent CLI subprocess sees the machine's genuine
            # running Madar EXEs and MUST refuse. Do not bypass this safety
            # gate just to make an integration test green.
            self.assertEqual(result.stdout, "")
            self.assertFalse(self.archive.exists())
            self.assertFalse(Path(env["APPDATA"]).exists())
            self.assertFalse(Path(env["LOCALAPPDATA"]).exists())
            return
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["command"], "backup")
        self.assertFalse(Path(env["APPDATA"]).exists())
        self.assertFalse(Path(env["LOCALAPPDATA"]).exists())
        result = subprocess.run(command + [
            "restore", "--data-root", str(self.root), "--archive", str(self.archive),
            "--confirm-offline", "--acknowledge-plaintext"],
            cwd=script, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_explicit_offline_and_sensitive_plaintext_optins_mandatory(self):
        with self.assertRaises(MaintenanceRefused):
            execute("backup", self.root, self.archive, plaintext_acknowledged=True)
        with self.assertRaises(MaintenanceRefused):
            execute("backup", self.root, self.archive, offline_confirmed=True)
        status, out, err = self.run_cli("backup", self.archive, offline=False)
        self.assertEqual(status, 3)
        self.assertEqual(out, "")
        self.assertIn("REFUSED", err)
        self.assertFalse(self.archive.exists())

    def test_active_madar_process_refuses_before_source_is_read(self):
        with patch("maintenance_recovery._running_madar_processes", return_value=[54123]):
            with self.assertRaisesRegex(MaintenanceRefused, "still running"):
                execute("backup", self.root, self.archive,
                        offline_confirmed=True, plaintext_acknowledged=True)
        self.assertFalse(self.archive.exists())
        self.assertEqual((self.root / "tasks.json").read_bytes(), self.original)

    def test_locked_sqlite_active_writer_blocks_backup_and_restore(self):
        self.store = UnifiedAppStorage(self.root / "madar-unified.sqlite3")
        self.store.commit({"tasks": initial_state(), "collab": __import__("collab").empty_state(),
                           "finance": __import__("finance").empty_finance_state(),
                           "completion_outbox": []}, expected_revision=0)
        (self.root / "unified-active.json").write_text(
            '{"schema":1,"database":"madar-unified.sqlite3"}', encoding="utf8")
        execute("backup", self.root, self.archive,
                offline_confirmed=True, plaintext_acknowledged=True)
        conn = sqlite3.connect(self.root / "madar-unified.sqlite3", isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            for action in ("backup", "restore"):
                target = self.backups / "second.zip" if action == "backup" else self.archive
                with self.subTest(action=action), self.assertRaisesRegex(
                        MaintenanceRefused, "SQLite"):
                    execute(action, self.root, target,
                            offline_confirmed=True, plaintext_acknowledged=True)
            self.assertEqual(self.store.history(), [1])
        finally:
            conn.execute("ROLLBACK")
            conn.close()

    def test_maintenance_lock_refuses_overlapping_operations(self):
        with _maintenance_lock(self.root):
            with self.assertRaisesRegex(MaintenanceRefused, "maintenance process"):
                execute("backup", self.root, self.archive,
                        offline_confirmed=True, plaintext_acknowledged=True)
        self.assertFalse(self.archive.exists())

    def test_cloud_path_refused_with_no_override_or_upload(self):
        cloud = self.parent / "My Drive"
        cloud.mkdir()
        with self.assertRaisesRegex(MaintenanceRefused, "cloud"):
            execute("backup", self.root, cloud / "sensitive.zip",
                    offline_confirmed=True, plaintext_acknowledged=True)
        self.assertFalse(list(cloud.iterdir()))

    def test_corrupt_restore_archive_fails_without_touching_original(self):
        self.archive.write_bytes(b"not a ZIP at all")
        before = (self.root / "tasks.json").read_bytes()
        status, out, err = self.run_cli("restore", self.archive)
        self.assertEqual(status, 4)
        self.assertIn("FAILED", err)
        self.assertEqual(out, "")
        self.assertEqual((self.root / "tasks.json").read_bytes(), before)
        self.assertFalse(list(self.parent.glob(".madar-restore-*.json")))

    def test_untrusted_recovery_journal_fails_closed(self):
        journal = _journal_path(self.root)
        journal.write_text('{"root":"something-else","old":"../secret","stage":false}',
                           encoding="utf8")
        self.assertEqual(pending_restore_journal(self.root), journal)
        original = (self.root / "tasks.json").read_bytes()
        status, out, err = self.run_cli("recover", ack=False)
        self.assertEqual(status, 4)
        self.assertIn("FAILED", err)
        self.assertEqual(out, "")
        self.assertEqual((self.root / "tasks.json").read_bytes(), original)
        self.assertTrue(journal.exists())

    def test_pending_journal_pre_bridge_guard_is_read_only(self):
        missing = self.parent / "not-yet-created"
        self.assertIsNone(pending_restore_journal(missing))
        self.assertFalse(missing.exists())
        self.assertIsNone(pending_restore_journal(self.root))
        journal = _journal_path(self.root)
        journal.write_bytes(b"not even JSON")
        self.assertEqual(pending_restore_journal(self.root), journal)
        self.assertEqual(journal.read_bytes(), b"not even JSON")
        self.assertFalse(list(self.parent.glob(".madar-maintenance-*.lock")))

    def test_process_detector_recognizes_packaged_version_and_pythonw_host(self):
        processes = [
            SimpleNamespace(pid=5521, info={"name": "Madar-Desk-v1.0-rc1.exe", "cmdline": []}),
            SimpleNamespace(pid=5522, info={"name": "pythonw.exe",
                                            "cmdline": [sys.executable, "native_app.py"]}),
            SimpleNamespace(pid=5523, info={"name": "python.exe",
                                            "cmdline": [sys.executable, "tests/test_native.py"]}),
            SimpleNamespace(pid=5524, info={"name": "python.exe",
                                            "cmdline": [sys.executable, "-m", "native_app"]}),
        ]
        with patch("maintenance_recovery.psutil.process_iter", return_value=iter(processes)):
            self.assertEqual(REAL_PROCESS_SCANNER(), [5521, 5522, 5524])

    def test_process_scanner_refuses_if_process_inventory_unavailable(self):
        with patch("maintenance_recovery.psutil", None):
            with self.assertRaisesRegex(MaintenanceRefused, "unavailable"):
                REAL_PROCESS_SCANNER()
        self.assertFalse(self.archive.exists())


if __name__ == "__main__":
    unittest.main()
