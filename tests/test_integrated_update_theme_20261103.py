"""Synthetic isolated regression for both updater entrypoints and theme state."""
import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import madar_update
import native_app
from standalone_accounting_desktop import AccountingDesktopAPI, JS_BRIDGE


class IntegratedUpdaterTests(unittest.TestCase):
    def test_release_bridge_exposes_only_fixed_host_update_commands(self):
        from native_app import ACCOUNTING_JS_BRIDGE, JS_BRIDGE as TASK_JS_BRIDGE
        for bridge in (JS_BRIDGE, ACCOUNTING_JS_BRIDGE, TASK_JS_BRIDGE):
            for name in ("releaseCheck", "releaseDownload", "releaseInstall"):
                self.assertIn("'" + name + "'", bridge)
        for command in ("saveState", "plannerWrite", "runCommand"):
            self.assertNotIn("'" + command + "'", JS_BRIDGE)

    def test_accounting_api_requires_session_and_live_window_to_install(self):
        with tempfile.TemporaryDirectory() as folder:
            api = AccountingDesktopAPI(Path(folder) / "new-synthetic-ledger")
            self.assertFalse(api.path.exists())
            with patch.object(madar_update, "check", return_value={"available": False}) as checker:
                self.assertEqual(api.releaseCheck(), {"available": False})
                checker.assert_called_once_with()
            with patch.object(madar_update, "check") as checker:
                with self.assertRaisesRegex(RuntimeError, "window"):
                    api.releaseInstall()
                checker.assert_not_called()
            api._native_window = object()
            api._exit_backed_up = True
            with patch.object(madar_update, "check") as checker:
                with self.assertRaisesRegex(RuntimeError, "closing"):
                    api.releaseCheck()
                with self.assertRaisesRegex(RuntimeError, "closing"):
                    api.releaseDownload()
                with self.assertRaisesRegex(RuntimeError, "closing"):
                    api.releaseInstall()
                checker.assert_not_called()
            self.assertFalse(api.path.exists())

    def test_accounting_uses_same_verified_host_update_as_planner(self):
        with tempfile.TemporaryDirectory() as folder:
            api = AccountingDesktopAPI(Path(folder) / "isolated")
            api._native_window = object()
            info = {"available": True, "latest": "1.0.12"}
            downloaded = {"verified": True, "path": "host-owned-only"}
            with (patch.object(madar_update, "check", return_value=info),
                  patch.object(madar_update, "download", return_value=downloaded) as download,
                  patch.object(madar_update, "schedule_verified_install", return_value={
                      "scheduledAfterExit": True, "version": "1.0.12"}) as schedule):
                self.assertEqual(api.releaseInstall()["scheduledAfterExit"], True)
                download.assert_called_once_with(info)
                schedule.assert_called_once_with(info, downloaded)
            self.assertFalse(api.path.exists())

    def test_deferred_install_revalidates_file_and_waits_for_host_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            payload = b"MZ" + b"fixture" * 85
            version = "1.0.14"
            name = f"Madar-Desk-{version}-Setup.exe"
            file = Path(folder) / name
            file.write_bytes(payload)
            info = madar_update.inspect_release({
                "tag_name": "v" + version,
                "assets": [{"name": name, "size": len(payload),
                            "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
                            "browser_download_url":
                                f"https://github.com/{madar_update.REPOSITORY}/releases/download/v{version}/{name}"}]})
            with (patch.object(madar_update.sys, "platform", "win32"),
                  patch.object(madar_update.subprocess, "Popen") as run):
                result = madar_update.schedule_verified_install(
                    info, {"verified": True, "path": str(file)}, parent_pid=87543)
                self.assertTrue(result["scheduledAfterExit"])
                cmd = run.call_args.args[0]
                decoded = base64.b64decode(cmd[-1]).decode("utf-16le")
                self.assertIn("Wait-Process -Id 87543", decoded)
                self.assertIn(info["sha256"], decoded)
                self.assertNotIn("Invoke-Expression", decoded)
                file.write_bytes(b"MZ" + b"corrupt" * 85)
                with self.assertRaises(ValueError):
                    madar_update.schedule_verified_install(
                        info, {"verified": True, "path": str(file)}, parent_pid=87543)
                self.assertEqual(run.call_count, 1)

    def test_shared_theme_defaults_migrate_without_losing_other_settings(self):
        data = native_app.initial_state()
        data["settings"].pop("themeForAllUsers", None)
        data["settings"]["customUserField"] = "keep"
        migrated = native_app.normalize_state(data)
        self.assertIs(migrated["settings"]["themeForAllUsers"], False)
        self.assertEqual(migrated["settings"]["customUserField"], "keep")
        self.assertTrue(native_app.is_valid(migrated))
        migrated["settings"]["themeForAllUsers"] = True
        self.assertTrue(native_app.is_valid(migrated))
        migrated["settings"]["themeForAllUsers"] = "yes"
        with self.assertRaises((ValueError, TypeError)):
            native_app.is_valid(migrated)

    def test_host_shared_theme_persists_to_clients_but_editor_cannot_change_it(self):
        from lan import LanService
        from tests.legacy_sample_fixture import seed_legacy_example_state
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(native_app, "datadir", return_value=root):
                bridge = seed_legacy_example_state(native_app.Bridge())
                service = LanService(bridge, root / "users.json", "127.0.0.1", 0)
                service.setup_owner("owner", "synthetic-owner-password")
                owner = service.authenticate_owner_token()
                service.upsert_user(owner, {
                    "username": "operator", "password": "synthetic-editor-password",
                    "role": "editor", "projects": ["p-sample"]})
                editor = service.authenticate("operator", "synthetic-editor-password")["token"]
                previous = service.read_state(owner)
                admin_state = previous["state"]
                admin_state["settings"]["themeForAllUsers"] = True
                admin_state["settings"]["theme"] = "dark"
                service.write_state(owner, admin_state, previous["revision"])
                read = service.read_state(editor)
                self.assertTrue(read["state"]["settings"]["themeForAllUsers"])
                self.assertEqual(read["state"]["settings"]["theme"], "dark")
                editor_state = read["state"]
                editor_state["settings"]["themeForAllUsers"] = False
                with self.assertRaises(PermissionError):
                    service.write_state(editor, editor_state, read["revision"])
                self.assertTrue(bridge.getState()["settings"]["themeForAllUsers"])


if __name__ == "__main__":
    unittest.main()
