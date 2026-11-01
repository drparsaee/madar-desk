"""Minimal desktop backup behavior, using only disposable local directories.

No Google login, live Windows profile, LAN server, or filesystem sync is used.
"""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import native_app
from tests.legacy_sample_fixture import seed_legacy_example_state


class SimpleBackupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-simple-backup-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        fake_profile = self.root / "fake-profile"
        fake_profile.mkdir()
        profile_patch = patch.dict(os.environ, {
            "APPDATA": str(fake_profile), "LOCALAPPDATA": str(fake_profile),
        })
        profile_patch.start()
        self.addCleanup(profile_patch.stop)
        datadir_patch = patch.object(native_app, "datadir", return_value=self.data)
        datadir_patch.start()
        self.addCleanup(datadir_patch.stop)
        self.bridge = seed_legacy_example_state(native_app.Bridge())

    def test_local_one_click_backup_works_without_google_credentials(self):
        self.assertFalse(self.bridge.auth.exists())
        with patch.object(self.bridge, "_access_token", side_effect=AssertionError("OAuth called")):
            saved = self.bridge.createLocalBackup()
        file = Path(saved["path"])
        self.assertTrue(file.is_file())
        self.assertEqual(file.parent, self.bridge.backups_dir)
        self.assertEqual(json.loads(file.read_text(encoding="utf-8")), self.bridge.getState())
        self.assertIs(saved["complete"], False)
        self.assertEqual(saved["scope"], "task-state-only")
        self.assertIn(saved["name"], [b["name"] for b in self.bridge.listLocalBackups()])

    def test_picker_cancel_is_safe_and_selected_folder_backup_requires_no_oauth(self):
        chosen = self.root / "desktop-sync-location"
        chosen.mkdir()
        picker = Mock()
        with patch.object(native_app.webview, "windows", [picker]):
            picker.create_file_dialog.return_value = None
            self.assertEqual(self.bridge.chooseDriveFolder(), {"canceled": True})
            self.assertFalse(self.bridge.driveFolderStatus()["configured"])
            picker.create_file_dialog.return_value = [str(chosen)]
            config = self.bridge.chooseDriveFolder()
        self.assertEqual(Path(config["folder"]), chosen / "Madar-Desk-Snapshots")
        task = self.bridge.getState()
        task["tasks"][0]["fileLinks"] = [{
            "id": "link-1", "name": "file", "path": r"\\server\share\file",
        }]
        self.bridge.saveState(task)
        with patch.object(self.bridge, "_access_token", side_effect=AssertionError("OAuth called")):
            backed_up = self.bridge.driveFolderBackup()
        content = json.loads(Path(backed_up["path"]).read_text(encoding="utf-8"))
        self.assertEqual(content["schema"], 1)
        self.assertEqual(content["type"], "backup")
        self.assertNotIn("fileLinks", content["state"]["tasks"][0])
        self.assertEqual(content["state"]["tasks"][0]["title"], task["tasks"][0]["title"])
        self.assertEqual(self.bridge.driveFolderList()[0]["name"], backed_up["name"])
        self.assertFalse(self.bridge.auth.exists())

    def test_explicit_folder_backup_explains_missing_or_unavailable_location(self):
        with self.assertRaisesRegex(RuntimeError, "پوشه"):
            self.bridge.driveFolderBackup()
        folder = self.root / "temporary-sync-folder"
        folder.mkdir()
        self.bridge.offline.set_sync_folder(folder)
        snapshots = folder / "Madar-Desk-Snapshots"
        snapshots.rmdir()
        self.assertFalse(self.bridge.driveFolderStatus()["available"])
        with self.assertRaisesRegex(RuntimeError, "پوشه"):
            self.bridge.driveFolderBackup()
        self.assertEqual(list(folder.glob("*.json")), [])

    def test_client_cannot_make_host_local_backup(self):
        self.bridge.connection = {"mode": "client", "url": "http://localhost:1"}
        with self.assertRaises(PermissionError):
            self.bridge.createLocalBackup()
        self.assertFalse(self.bridge.backups_dir.exists())


if __name__ == "__main__":
    unittest.main()
