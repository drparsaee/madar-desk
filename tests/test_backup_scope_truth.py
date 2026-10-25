"""P0 truth-in-backup contract: scoped host snapshots must never claim full recovery.

All Bridge instances use an explicitly patched, disposable datadir. There is
no real APPDATA/LOCALAPPDATA, external service, EXE, LAN listener, or Drive use.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app
from app_storage import UnifiedAppStorage


# Match the user-approved external bridge shape. These are public return
# fields; a mismatched interim format must fail rather than silently passing.
SCOPES = {"json": "task-state-only", "sqlite": "sqlite-domains-only"}
ALWAYS_OMITTED = {"attachment-binaries", "lan-accounts", "planner-local-storage"}
JSON_ADDITIONAL_OMITTED = {"finance", "collaboration"}


class BackupScopeTruthTest(unittest.TestCase):
    def setUp(self):
        disposable = tempfile.TemporaryDirectory(prefix="madar-backup-scope-")
        self.addCleanup(disposable.cleanup)
        self.root = Path(disposable.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.profiles = self.root / "fake-profiles"
        self.profiles.mkdir()
        roaming = self.profiles / "Roaming"
        local = self.profiles / "Local"
        roaming.mkdir()
        local.mkdir()
        # Patch actual process env for the duration of each test, in addition
        # to patching native_app.datadir. This prevents any code accidentally
        # deriving a real user-profile path through inherited env.
        env_patch = patch.dict(
            os.environ, {"APPDATA": str(roaming), "LOCALAPPDATA": str(local)},
        )
        env_patch.start()
        self.addCleanup(env_patch.stop)
        datadir_patch = patch.object(native_app, "datadir", return_value=self.data)
        datadir_patch.start()
        self.addCleanup(datadir_patch.stop)
        self.bridge = native_app.Bridge()
        self.assertEqual(self.bridge.storageStatus()["mode"], "json")
        self.assertEqual(self.bridge.connection["mode"], "solo")
        self.assertIsNone(self.bridge.lan)
        self.assertTrue(self.bridge.path.is_relative_to(self.data))

    def put_unbacked_data(self):
        """Plant distinct data in each domain excluded by both quick backups."""
        profile = self.data / "lan-users.json"
        profile.write_text('{"synthetic_account":"LAN-SCOPE-PRIVATE-DO-NOT-EXPORT"}',
                           encoding="utf-8")
        blob = self.data / "attachment-storage" / "blobs" / "aa"
        blob.mkdir(parents=True)
        binary = blob / "synthetic-private-binary"
        binary.write_bytes(b"\x00\xffATTACHMENT-SCOPE-PRIVATE-BINARY\x00")
        return profile, binary

    def assert_scope(self, answer, mode):
        self.assertIsInstance(answer, dict)
        self.assertIs(answer.get("complete"), False, "A partial backup cannot be complete")
        self.assertEqual(answer.get("scope"), SCOPES[mode])
        omitted = answer.get("omitted")
        self.assertIsInstance(omitted, list, "Use the user-approved 'omitted' key")
        self.assertTrue(all(isinstance(item, str) and item for item in omitted))
        self.assertEqual(len(omitted), len(set(omitted)))
        for name in ALWAYS_OMITTED:
            self.assertIn(name, omitted, f"Missing omitted domain: {name}")
        if mode == "json":
            for name in JSON_ADDITIONAL_OMITTED:
                self.assertIn(name, omitted)
        self.assertIsInstance(answer.get("note"), str)
        self.assertTrue(answer["note"].strip(), "Partial backup needs human-readable warning")
        path = Path(answer["path"])
        self.assertTrue(path.is_file(), "Return a real usable on-disk backup")
        self.assertEqual(path.parent, self.bridge.backups_dir)
        self.assertEqual(path.name, answer["name"])
        self.assertGreater(path.stat().st_size, 0)
        return path

    def test_json_mode_partial_contract_and_exact_task_data_roundtrip(self):
        profile, binary = self.put_unbacked_data()
        state = deepcopy(self.bridge.getState())
        state["tasks"][0]["title"] = "JSON only synthetic task"
        self.bridge.saveState(state)
        saved_state = deepcopy(self.bridge.getState())

        answer = self.bridge.createLocalBackup()
        archive = self.assert_scope(answer, "json")
        self.assertEqual(archive.suffix, ".json")
        disk = json.loads(archive.read_text(encoding="utf-8"))
        self.assertEqual(disk, saved_state)
        self.assertTrue(native_app.is_valid(disk))
        serialized = archive.read_bytes()
        self.assertNotIn(b"LAN-SCOPE-PRIVATE-DO-NOT-EXPORT", serialized)
        self.assertNotIn(b"ATTACHMENT-SCOPE-PRIVATE-BINARY", serialized)

        # A partial task backup remains a valid task backup. It is not silently
        # expanded to a full backup, and independent local resources survive.
        state["tasks"][0]["title"] = "modified after snapshot"
        self.bridge.saveState(state)
        restored = self.bridge.restoreLocalBackup(answer["name"])
        self.assertEqual(restored["tasks"][0]["title"], saved_state["tasks"][0]["title"])
        self.assertEqual(profile.read_text("utf-8"),
                         '{"synthetic_account":"LAN-SCOPE-PRIVATE-DO-NOT-EXPORT"}')
        self.assertEqual(binary.read_bytes(), b"\x00\xffATTACHMENT-SCOPE-PRIVATE-BINARY\x00")

    def test_sqlite_mode_partial_contract_and_valid_four_domain_backup(self):
        profile, binary = self.put_unbacked_data()
        result = self.bridge.enableUnifiedStorage()
        self.assertEqual(result["mode"], "sqlite")
        self.bridge.collabCommand({
            "type": "comment.add", "eventId": "scope-comment-1",
            "cardId": "example-2", "text": "Synthetic scope check",
        })
        prior = self.bridge._unified_store.load()
        self.assertIsNotNone(prior)
        self.assertEqual(len(prior.bundle["collab"]["comments"]), 1)

        answer = self.bridge.createLocalBackup()
        archive = self.assert_scope(answer, "sqlite")
        self.assertEqual(archive.suffix, ".sqlite3")
        snapshot = UnifiedAppStorage(archive)
        self.assertTrue(snapshot.integrity_check())
        saved = snapshot.load()
        self.assertEqual(saved.sha256, prior.sha256)
        self.assertEqual(saved.revision, prior.revision)
        self.assertEqual(saved.bundle, prior.bundle)
        self.assertEqual(set(("tasks", "collab", "finance", "completion_outbox"))
                         - set(saved.bundle), set())
        self.assertNotIn("lan-accounts", saved.bundle)
        self.assertNotIn("attachment-binaries", saved.bundle)
        self.assertNotIn("planner-local-storage", saved.bundle)
        self.assertNotIn("LAN-SCOPE-PRIVATE-DO-NOT-EXPORT",
                         str(saved.bundle))
        self.assertNotIn("ATTACHMENT-SCOPE-PRIVATE-BINARY",
                         str(saved.bundle))
        self.assertTrue(profile.is_file())
        self.assertTrue(binary.is_file())

        # The snapshot must not be a shortcut or hardlink to the live SQLite
        # database. Later commits cannot rewrite the already-exported bytes.
        before = archive.read_bytes()
        new_state = self.bridge.getState()
        new_state["tasks"][0]["title"] = "Change after SQL snapshot"
        self.bridge.saveState(new_state)
        self.assertEqual(archive.read_bytes(), before)
        self.assertNotEqual(self.bridge._unified_store.load().sha256, saved.sha256)
        self.assertEqual(snapshot.load().sha256, saved.sha256)

    def test_both_modes_return_a_non_complete_scope_even_when_no_attachments_exist(self):
        for mode in ("json", "sqlite"):
            with self.subTest(mode=mode):
                if mode == "sqlite":
                    self.bridge.enableUnifiedStorage()
                outcome = self.bridge.createLocalBackup()
                self.assert_scope(outcome, mode)
                self.assertNotIn("full", outcome["scope"])
                self.assertIs(outcome["complete"], False)
                self.assertEqual(self.bridge.storageStatus()["mode"], mode)

    def test_client_cannot_create_a_host_backup_or_backup_directory(self):
        self.bridge.connection = {"mode": "client", "url": "http://invalid.local"}
        self.assertFalse(self.bridge.backups_dir.exists())
        with self.assertRaises(PermissionError):
            self.bridge.createLocalBackup()
        self.assertFalse(self.bridge.backups_dir.exists())

    def test_bridge_contract_source_has_no_ambiguous_full_backup_flag(self):
        # Canary for future changes that accidentally reintroduce a truthy
        # complete flag. Runtime checks above remain authoritative.
        source = Path(native_app.__file__).read_text(encoding="utf-8")
        start = source.index("    def createLocalBackup(self):")
        end = source.index("\n    def ", start + 5)
        implementation = source[start:end]
        self.assertNotIn('"complete": True', implementation)
        self.assertIn('"omitted":', implementation)
        self.assertIn('"note":', implementation)
        self.assertIn('"scope":', implementation)

    def test_ui_source_prominently_discloses_partial_backups_and_offline_full_tool(self):
        """Source-contract check only; no WebView/EXE launched by this test."""
        ui = Path(native_app.__file__).resolve().parent / "src" / "App.jsx"
        source = ui.read_text(encoding="utf-8")
        self.assertIn("محدوده واقعی پشتیبان‌ها", source)
        self.assertIn('role="note"', source)
        self.assertIn("Google Drive", source)
        self.assertIn("SQLite", source)
        self.assertIn("فایل‌های پیوست", source)
        self.assertIn("حساب‌های LAN", source)
        self.assertIn("برنامه‌ریزی شخصی", source)
        self.assertIn("maintenance_recovery.py", source)
        self.assertIn("رمزنگاری نشده", source)


if __name__ == "__main__":
    unittest.main()
