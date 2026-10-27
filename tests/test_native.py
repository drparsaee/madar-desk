import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app


class NativeAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-test-")
        self.root = Path(self.tmp.name)
        self.patch_dir = patch.object(native_app, "datadir", return_value=self.root)
        self.patch_dir.start()
        self.bridge = native_app.Bridge()

    def tearDown(self):
        self.patch_dir.stop()
        self.tmp.cleanup()

    def test_first_run_creates_valid_local_data(self):
        state = self.bridge.getState()
        self.assertTrue(native_app.is_valid(state))
        self.assertTrue((self.root / "tasks.json").exists())
        self.assertEqual(len(state["tasks"]), 4)

    def test_legacy_checklist_ids_survive_full_native_save_and_reload(self):
        original = native_app.initial_state()
        original["tasks"][0]["checklist"] = [
            {"text": "بدون شناسه", "done": False},
            {"id": "duplicate", "text": "اول", "done": False},
            {"id": "duplicate", "text": "دوم", "done": True},
        ]
        first = native_app.normalize_state(original)
        self.assertTrue(native_app.is_valid(first))
        named = next(g for g in first["tasks"][0]["checklists"] if g["id"] == "checklist-legacy")
        identifiers = [i["id"] for i in named["items"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertTrue(all(isinstance(i, str) and i for i in identifiers))
        native_app.atomic_save(self.root / "tasks.json", first)
        again = self.bridge.getState()
        self.assertEqual(first, again)
        original_flat = original["tasks"][0]["checklist"]
        self.assertEqual(original_flat[0].get("id"), None)
        self.assertEqual(original_flat[1]["id"], original_flat[2]["id"])

    def test_save_then_reopen_keeps_checklists_and_reports(self):
        data = self.bridge.getState()
        data["tasks"][0]["checklist"].append(
            {"id": "check-1", "text": "نهایی", "done": False})
        data["tasks"][0]["reports"].append({
            "id": "report-1", "agent": "Codex",
            "summary": "مرحله اول کامل شد.", "createdAt": "2026-10-20T13:00:00Z"})
        self.assertTrue(self.bridge.saveState(data))
        reopened = native_app.Bridge().getState()
        self.assertEqual(reopened["tasks"][0]["checklist"][-1]["text"], "نهایی")
        self.assertEqual(reopened["tasks"][0]["reports"][-1]["agent"], "Codex")

    def test_invalid_import_does_not_replace_previous_data(self):
        previous = self.bridge.getState()
        invalid = native_app.initial_state()
        invalid["tasks"][0]["projectId"] = "missing-project"
        with self.assertRaises(ValueError):
            native_app.safe_restore(self.root / "tasks.json", invalid)
        self.assertEqual(previous, self.bridge.getState())
        self.assertFalse(list(self.root.glob("backup-before-restore-*")))

    def test_restore_creates_pre_restore_backup(self):
        previous = self.bridge.getState()
        updated = native_app.initial_state()
        updated["projects"][0]["name"] = "بازیابی‌شده"
        native_app.safe_restore(self.root / "tasks.json", updated)
        backup = list(self.root.glob("backup-before-restore-*.json"))
        self.assertEqual(len(backup), 1)
        self.assertEqual(json.loads(backup[0].read_text(encoding="utf8")), previous)
        self.assertEqual(self.bridge.getState()["projects"][0]["name"], "بازیابی‌شده")

    def test_google_backup_uses_private_app_data_space(self):
        recorded = {}
        def fake_drive(url, method="GET", data=None, headers=None):
            recorded.update(url=url, method=method, data=data, headers=headers)
            return {"id": "google-backup-id"}
        self.bridge._drive = fake_drive
        result = self.bridge.driveUpload()
        self.assertEqual(result["id"], "google-backup-id")
        self.assertEqual(recorded["method"], "POST")
        self.assertIn(b'"appDataFolder"', recorded["data"])
        self.assertIn(b'"projects"', recorded["data"])
        self.assertIn("multipart/related", recorded["headers"]["Content-Type"])

    def test_google_restore_is_validated_before_local_replacement(self):
        original = self.bridge.getState()
        self.bridge.driveList = lambda: [{
            "id": "test-backup", "name": "madar-backup-example.json"}]
        def fake_drive(url, *args, **kwargs):
            if url.endswith("?alt=media"):
                return {"version": 1, "projects": [], "tasks": "wrong",
                        "settings": {}}
            raise AssertionError(url)
        self.bridge._drive = fake_drive
        with self.assertRaises(ValueError):
            self.bridge.driveRestore("test-backup")
        self.assertEqual(self.bridge.getState(), original)

    @unittest.skipUnless(os.name == "nt", "DPAPI only runs on Windows")
    def test_windows_dpapi_roundtrip(self):
        secret = b"secret-refresh-token-test"
        encrypted = native_app.protect_windows(secret)
        self.assertNotEqual(encrypted, secret)
        self.assertEqual(native_app.protect_windows(encrypted, decrypt=True), secret)

    def test_old_version_one_data_migrates_without_losing_tasks(self):
        original = native_app.initial_state()
        original.pop("stages")
        original["settings"].pop("costDefault")
        original["projects"][0].pop("price")
        original["projects"][0].pop("costEnabled")
        original["tasks"][0].pop("cost")
        self.bridge.path.write_text(json.dumps(original), encoding="utf8")
        normalized = self.bridge.getState()
        self.assertEqual(normalized["projects"][0]["price"], 0)
        self.assertFalse(normalized["projects"][0]["costEnabled"])
        self.assertEqual(normalized["tasks"][0]["cost"], 0)
        self.assertEqual(len(normalized["stages"]), 5)
        self.assertEqual(len(normalized["tasks"]), len(original["tasks"]))

    def test_custom_stages_and_toman_costs_are_validated(self):
        state = self.bridge.getState()
        state["stages"].append({"id": "delivery", "label": "تحویل", "subtitle": "", "color": "#315f87"})
        state["tasks"][0]["status"] = "delivery"
        state["projects"][1]["costEnabled"] = True
        state["projects"][1]["price"] = 2500000
        state["tasks"][0]["cost"] = 120000
        state["tasks"][0]["checklist"][0]["cost"] = 70000
        self.bridge.saveState(state)
        self.assertEqual(self.bridge.getState()["tasks"][0]["status"], "delivery")
        self.assertEqual(self.bridge.getState()["projects"][1]["price"], 2500000)
        state["tasks"][0]["cost"] = -500
        with self.assertRaises(ValueError):
            self.bridge.saveState(state)
        self.assertEqual(self.bridge.getState()["tasks"][0]["cost"], 120000)

    def test_old_data_receives_new_estimates_and_links_without_losing_values(self):
        old = native_app.initial_state()
        old["projects"][0].pop("fileLinks", None)
        old["tasks"][0].pop("estimatedMinutes", None)
        self.bridge.path.write_text(json.dumps(old), encoding="utf8")
        new = self.bridge.getState()
        self.assertEqual(new["tasks"][0]["estimatedMinutes"], 0)
        self.assertEqual(new["tasks"][0]["actualMinutes"], 0)
        self.assertEqual(new["projects"][0]["fileLinks"], [])
        self.assertEqual(len(new["tasks"]), len(old["tasks"]))

    def test_smb_links_only_and_estimate_validation(self):
        self.assertTrue(native_app.valid_share_path(r"\\OFFICE-PC\Projects\folder\file.pdf"))
        for illegal in ("https://example.com/file", r"C:\folder\file.pdf",
                        r"\\server\share\..\hidden.txt", r"\\server\share\bad:file.txt"):
            self.assertFalse(native_app.valid_share_path(illegal), illegal)
        state = self.bridge.getState()
        state["projects"][0]["fileLinks"] = [{
            "id": "link1", "name": "طرح اصلی", "path": r"\\OFFICE-PC\Projects\design.ai"}]
        state["tasks"][0]["estimatedMinutes"] = 125
        state["tasks"][0]["actualMinutes"] = 87
        self.bridge.saveState(state)
        self.assertEqual(self.bridge.getState()["tasks"][0]["estimatedMinutes"], 125)
        state["tasks"][0]["estimatedMinutes"] = -1
        with self.assertRaises(ValueError):
            self.bridge.saveState(state)
        state["tasks"][0]["estimatedMinutes"] = 125
        state["projects"][0]["fileLinks"][0]["path"] = "cmd.exe /c del C:"
        with self.assertRaises(ValueError):
            self.bridge.saveState(state)

    def test_windows_explorer_opens_share_on_local_pc(self):
        with patch.object(native_app.subprocess, "Popen") as popen:
            response = self.bridge.openSharedFile(r"\\FILESERVER\Shared\photo.jpg")
        self.assertTrue(response["opened"])
        self.assertEqual(popen.call_args.args[0][0], "explorer.exe")
        self.assertIn(r"\\FILESERVER\Shared\photo.jpg", popen.call_args.args[0])
        with self.assertRaises(ValueError):
            self.bridge.openSharedFile("https://example.org/")

    def test_local_backup_auto_and_manual_restore(self):
        original = self.bridge.getState()
        state = self.bridge.getState()
        state["tasks"][0]["title"] = "نسخه دوم"
        self.bridge.saveState(state)
        auto = list((self.root / "backups").glob("auto-*.json"))
        self.assertEqual(len(auto), 1)
        self.assertIn(auto[0].name, [item["name"] for item in self.bridge.listLocalBackups()])
        self.assertEqual(json.loads(auto[0].read_text(encoding="utf8"))["tasks"][0]["title"],
                         original["tasks"][0]["title"])
        saved = self.bridge.createLocalBackup()
        self.assertTrue(Path(saved["path"]).is_file())
        self.assertEqual(self.bridge.listLocalBackups()[0]["name"], saved["name"])
        state["tasks"][0]["title"] = "نسخه سوم"
        self.bridge.saveState(state)
        restored = self.bridge.restoreLocalBackup(saved["name"])
        self.assertEqual(restored["tasks"][0]["title"], "نسخه دوم")
        previous_day_version = self.bridge.restoreLocalBackup(auto[0].name)
        self.assertEqual(previous_day_version["tasks"][0]["title"],
                         original["tasks"][0]["title"])
        self.assertTrue(list(self.root.glob("backup-before-restore-*.json")))
        with self.assertRaises(ValueError):
            self.bridge.restoreLocalBackup("../tasks.json")

    def test_calendar_preference_is_per_computer_and_validated(self):
        self.assertEqual(self.bridge.getPreferences()["calendar"], "jalali")
        self.assertEqual(self.bridge.setPreferences({"calendar": "gregorian"})["calendar"],
                         "gregorian")
        self.assertEqual(native_app.Bridge().getPreferences()["calendar"], "gregorian")
        with self.assertRaises(ValueError):
            self.bridge.setPreferences({"calendar": "other"})

    def test_clock_widget_setting_survives_calendar_change_and_restart(self):
        self.assertEqual(self.bridge.getPreferences()["clockWidget"], "both")
        changed = self.bridge.setPreferences({"clockWidget": "date"})
        self.assertEqual(changed, {"calendar": "jalali", "clockWidget": "date"})
        self.assertEqual(self.bridge.setPreferences({"calendar": "gregorian"})["clockWidget"], "date")
        self.assertEqual(native_app.Bridge().getPreferences()["clockWidget"], "date")
        self.assertEqual(self.bridge.setPreferences({"clockWidget": "hidden"})["clockWidget"], "hidden")
        with self.assertRaises(ValueError):
            self.bridge.setPreferences({"clockWidget": "__proto__"})

    def test_card_cost_toggle_and_assignees_survive_backup(self):
        state = self.bridge.getState()
        self.assertIsNone(state["tasks"][0]["costEnabled"])
        state["tasks"][0]["costEnabled"] = True
        state["tasks"][0]["assignees"] = ["local"]
        state["projects"][1]["costEnabled"] = False
        state["tasks"][0]["cost"] = 650000
        self.bridge.saveState(state)
        self.assertEqual(self.bridge.getState()["tasks"][0]["cost"], 650000)
        self.assertTrue(self.bridge.getState()["tasks"][0]["costEnabled"])
        snap = self.bridge.createLocalBackup()
        restored = self.bridge.restoreLocalBackup(snap["name"])
        self.assertEqual(restored["tasks"][0]["assignees"], ["local"])
        self.assertTrue(restored["tasks"][0]["costEnabled"])
        state["tasks"][0]["costEnabled"] = "true"
        with self.assertRaises(ValueError):
            self.bridge.saveState(state)

    def test_solo_profile_is_private_and_persistent(self):
        saved = self.bridge.lanMyProfile({
            "displayName": "پروفایل شخصی", "avatarIcon": "star", "avatarPhoto": ""})
        self.assertEqual(saved["displayName"], "پروفایل شخصی")
        self.assertEqual(native_app.Bridge().lanProfiles()[0]["avatarIcon"], "star")
        self.assertEqual(self.bridge.lanStatus()["user"]["displayName"], "پروفایل شخصی")

    def test_solo_assignee_becomes_owner_on_lan_host(self):
        from lan import LanService
        state = self.bridge.getState()
        state["tasks"][0]["assignees"] = ["local"]
        self.bridge.saveState(state)
        server = LanService(self.bridge, self.root / "accounts-test.json", bind="127.0.0.1", port=0)
        server.setup_owner("owner1", "password-very-strong")
        self.bridge.lan = server
        self.bridge._migrate_local_assignees_to_owner()
        self.assertEqual(self.bridge.getState()["tasks"][0]["assignees"], ["owner1"])

    def test_drive_desktop_folder_backup_and_safe_restore(self):
        folder = self.root / "Google Drive synced folder"
        folder.mkdir()
        self.bridge.offline.set_sync_folder(folder)
        before = self.bridge.getState()
        saved = self.bridge.driveFolderBackup()
        self.assertTrue(saved["name"].endswith(".json"))
        self.assertEqual(self.bridge.driveFolderList()[0]["name"],saved["name"])
        edited = self.bridge.getState()
        edited["tasks"][0]["title"] = "changed after backup"
        self.bridge.saveState(edited)
        result = self.bridge.driveFolderRestore(saved["name"])
        self.assertEqual(result["tasks"][0]["title"],before["tasks"][0]["title"])
        self.assertTrue(list(self.root.glob("backup-before-restore-*.json")))
        with self.assertRaises(ValueError):
            self.bridge.driveFolderRestore("../passwords.json")


if __name__ == "__main__":
    unittest.main()
