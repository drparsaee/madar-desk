"""Offline synthetic full backup/restore tests; never read real Windows APPDATA."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import base64
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
import warnings
from unittest.mock import patch
import zipfile

import collab
import finance
from app_storage import UnifiedAppStorage
from attachments import AttachmentStore
from full_recovery import (RecoveryError, create_full_backup,
                           restore_full_backup, recover_interrupted_restore)
from lan import make_account
from native_app import initial_state


class FullRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-full-recovery-test-")
        self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name)
        self.root = self.parent / "data"
        self.root.mkdir()
        self.archive = self.parent / "full.zip"
        self.tasks = initial_state()
        self.cards = self.tasks["tasks"]
        self.projects = self.tasks["projects"]
        self.users = {"owner": make_account("owner", "strong-test-password", "admin"),
                      "viewer_a": make_account("viewer_a", "strong-test-password", "viewer", ["p-sample"])}
        self.write("tasks.json", self.tasks)
        self.write("collab.json", collab.empty_state())
        self.write("finance.json", finance.empty_finance_state())
        self.write("finance-completion-outbox.json", [])
        self.write("automation-card-outbox.json", [])
        self.write("lan-users.json", self.users)
        self.write("personal-profile.json", {"displayName": "دوست", "avatarIcon": "star",
                                             "avatarPhoto": "", "avatarColor": "#ffffff"})
        self.write("preferences.json", {"calendar": "jalali"})

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf8")

    def test_legacy_full_restore_all_domains_and_sensitive_account_hash(self):
        unrelated = self.root / "unknown-local-note.txt"
        unrelated.write_text("local notes should not be deleted", encoding="utf8")
        before = {name: (self.root / name).read_bytes() for name in (
            "tasks.json", "finance.json", "collab.json", "lan-users.json",
            "personal-profile.json", "automation-card-outbox.json")}
        report = create_full_backup(self.root, self.archive, offline=True)
        self.assertGreater(report["files"], 4)
        self.assertNotIn("password", str(report).lower())
        self.tasks["tasks"][0]["title"] = "changed after archive"
        self.write("tasks.json", self.tasks)
        result = restore_full_backup(self.root, self.archive, offline=True)
        self.assertTrue(Path(result["preRestoreArchive"]).is_file())
        self.assertEqual(
            (Path(result["preRestoreRoot"]) / unrelated.name).read_text(encoding="utf8"),
            "local notes should not be deleted")
        self.assertFalse((self.root / unrelated.name).exists())
        for name, raw in before.items():
            self.assertEqual((self.root / name).read_bytes(), raw)
        self.assertEqual(recover_interrupted_restore(self.root, offline=True),
                         {"recovered": False})
        # Full original users and password hashes are retained, without sessions.
        self.assertEqual(json.loads((self.root / "lan-users.json").read_text("utf8")), self.users)
        self.assertEqual(self.users["viewer_a"]["projects"], ["p-sample"])

    def test_unified_sqlite_wal_four_domains_history_and_attachments(self):
        state = {"tasks": self.tasks, "finance": finance.empty_finance_state(),
                 "collab": collab.empty_state(), "completion_outbox": []}
        database = UnifiedAppStorage(self.root / "madar-unified.sqlite3")
        database.commit(state, expected_revision=0)
        second = deepcopy(database.load().bundle)
        second["tasks"]["tasks"][0]["title"] = "sqlite second revision"
        second["finance"]["cardCosts"] = {}
        database.commit(second, expected_revision=1)
        self.write("unified-active.json", {"schema": 1, "database": "madar-unified.sqlite3"})

        attachments = AttachmentStore(self.root / "attachment-storage")
        attached = attachments.upload(
            actor="owner", accounts=self.users, cards=self.cards, projects=self.projects,
            card_id=self.cards[0]["id"], filename="notes.txt",
            content_base64=base64.b64encode("اینجا فایل است".encode()).decode(),
            request_id="full-backup-attachment-1", now=datetime.now(timezone.utc).isoformat())
        self.assertEqual(attachments.list_card(
            actor="owner", accounts=self.users, cards=self.cards,
            projects=self.projects, card_id=self.cards[0]["id"])[0]["id"], attached["id"])

        create_full_backup(self.root, self.archive, offline=True)
        with zipfile.ZipFile(self.archive) as zipped:
            self.assertIn("data/attachment-storage/attachments.sqlite3", zipped.namelist())
            self.assertIn("data/madar-unified.sqlite3", zipped.namelist())
            self.assertIn("data/attachment-storage/blobs/" +
                          attached["sha256"][:2] + "/" + attached["sha256"], zipped.namelist())

        database.commit(state, expected_revision=2)
        result = restore_full_backup(self.root, self.archive, offline=True)
        self.assertGreater(result["files"], 10)
        reopened = UnifiedAppStorage(self.root / "madar-unified.sqlite3")
        self.assertTrue(reopened.integrity_check())
        self.assertEqual(reopened.history(), [2, 1])
        self.assertEqual(reopened.load().bundle["tasks"]["tasks"][0]["title"],
                         "sqlite second revision")
        recovered = AttachmentStore(self.root / "attachment-storage")
        response = recovered.read(attachment_id=attached["id"], actor="owner",
                                  accounts=self.users, cards=self.cards, projects=self.projects)
        self.assertEqual(base64.b64decode(response["contentBase64"]), "اینجا فایل است".encode())

    def test_offline_gate_and_disjoint_paths(self):
        with self.assertRaises(RecoveryError):
            create_full_backup(self.root, self.archive)
        with self.assertRaises(RecoveryError):
            create_full_backup(self.root, self.root / "inside.zip", offline=True)
        with self.assertRaises(RecoveryError):
            restore_full_backup(self.root, self.archive)
        with self.assertRaises(RecoveryError):
            recover_interrupted_restore(self.root)

    def test_reject_invalid_source_before_creating_archive(self):
        self.write("finance.json", {"ledger": "corrupt"})
        with self.assertRaises(ValueError):
            create_full_backup(self.root, self.archive, offline=True)
        self.assertFalse(self.archive.exists())

    def test_corrupted_zip_member_after_inventory_does_not_publish(self):
        """A validated source is insufficient if the final archive differs."""
        import full_recovery

        source_before = (self.root / "tasks.json").read_bytes()
        original_inventory = full_recovery._inventory

        def corrupt_staged_snapshot_after_hash(folder):
            entries, size = original_inventory(folder)
            staged_task = folder / "tasks.json"
            changed = json.loads(staged_task.read_text(encoding="utf8"))
            # The new title contains the identical UTF-8 byte count so the
            # integrity gate must compare SHA, not just member size.
            changed["tasks"][0]["title"] = changed["tasks"][0]["title"][::-1]
            staged_task.write_text(json.dumps(changed, ensure_ascii=False),
                                   encoding="utf8")
            return entries, size

        with patch.object(full_recovery, "_inventory",
                          side_effect=corrupt_staged_snapshot_after_hash):
            with self.assertRaisesRegex(RecoveryError, "SHA-256 mismatch"):
                create_full_backup(self.root, self.archive, offline=True)
        self.assertFalse(self.archive.exists(), "An unrestorable ZIP must never be published")
        self.assertEqual((self.root / "tasks.json").read_bytes(), source_before)
        self.assertFalse(list(self.parent.glob(".madar-backup-*")))
        self.assertFalse(list(self.parent.glob(".*.tmp")))

    def test_missing_payload_corruption_traversal_symlink_and_duplicate_rejected(self):
        create_full_backup(self.root, self.archive, offline=True)
        with zipfile.ZipFile(self.archive) as original:
            snapshot = [(item.filename, original.read(item)) for item in original.infolist()]
        for attack in ("missing", "mutated", "traversal", "symlink", "duplicate"):
            malicious = self.parent / f"{attack}.zip"
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Duplicate name:")
                with zipfile.ZipFile(malicious, "w", compression=zipfile.ZIP_STORED) as zipped:
                    for name, raw in snapshot:
                        if attack == "missing" and name == "data/lan-users.json":
                            continue
                        if attack == "mutated" and name == "data/tasks.json":
                            raw = b"x" * len(raw)
                        zipped.writestr(name, raw)
                    if attack == "traversal":
                        zipped.writestr("data/../outside.txt", b"malicious")
                    if attack == "duplicate":
                        zipped.writestr("data/tasks.json", b"duplicate")
                    if attack == "symlink":
                        info = zipfile.ZipInfo("data/personal-profile.json")
                        info.create_system = 3
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        zipped.writestr(info, b"../secret")
            previous = (self.root / "tasks.json").read_bytes()
            with self.subTest(attack=attack), self.assertRaises((RecoveryError, ValueError, zipfile.BadZipFile)):
                restore_full_backup(self.root, malicious, offline=True)
            self.assertEqual((self.root / "tasks.json").read_bytes(), previous)
            self.assertFalse(list(self.parent.glob("madar-pre-restore-*.zip")))
            self.assertEqual(recover_interrupted_restore(self.root, offline=True),
                             {"recovered": False})

    def test_corrupt_existing_root_blocks_restore_before_swap(self):
        create_full_backup(self.root, self.archive, offline=True)
        self.write("tasks.json", {"version": -10})
        previous = (self.root / "tasks.json").read_bytes()
        with self.assertRaises(ValueError):
            restore_full_backup(self.root, self.archive, offline=True)
        self.assertEqual((self.root / "tasks.json").read_bytes(), previous)
        self.assertFalse(list(self.parent.glob(".madar-restore-*.json")))

    def test_failed_second_rename_rolls_back_old_directory(self):
        import full_recovery
        create_full_backup(self.root, self.archive, offline=True)
        self.tasks["tasks"][0]["title"] = "most current and must survive"
        self.write("tasks.json", self.tasks)
        previous = (self.root / "tasks.json").read_bytes()
        actual_replace = os.replace

        def fail_stage_move(source, target):
            if Path(source).name.startswith(".madar-restore-stage-") and Path(target) == self.root:
                raise OSError("simulated second rename failure")
            return actual_replace(source, target)

        with patch.object(full_recovery.os, "replace", side_effect=fail_stage_move):
            with self.assertRaisesRegex(OSError, "simulated"):
                restore_full_backup(self.root, self.archive, offline=True)
        self.assertEqual((self.root / "tasks.json").read_bytes(), previous)
        self.assertFalse(list(self.parent.glob(".madar-restore-*.json")))
        self.assertTrue(list(self.parent.glob("madar-pre-restore-*.zip")))

    def test_crash_after_original_move_recovered_by_journal(self):
        import full_recovery
        create_full_backup(self.root, self.archive, offline=True)
        source = (self.root / "tasks.json").read_bytes()
        stage = self.parent / (".madar-restore-stage-" + "a" * 24)
        old = self.parent / (".madar-restore-old-" + "a" * 24)
        stage.mkdir()
        (stage / "tasks.json").write_bytes(b"do not publish")
        journal = full_recovery._journal_path(self.root)
        full_recovery._journal_write(journal, {"root": str(self.root),
                                              "stage": stage.name, "old": old.name})
        os.replace(self.root, old)
        result = recover_interrupted_restore(self.root, offline=True)
        self.assertTrue(result["recovered"])
        self.assertEqual((self.root / "tasks.json").read_bytes(), source)
        self.assertFalse(stage.exists())
        self.assertFalse(journal.exists())

    def test_crash_after_new_root_is_published_restores_original_root(self):
        import full_recovery
        create_full_backup(self.root, self.archive, offline=True)
        original = (self.root / "tasks.json").read_bytes()
        token = "b" * 24
        stage = self.parent / (".madar-restore-stage-" + token)
        old = self.parent / (".madar-restore-old-" + token)
        stage.mkdir()
        (stage / "tasks.json").write_bytes(b"staged newer root")
        journal = full_recovery._journal_path(self.root)
        full_recovery._journal_write(journal, {"root": str(self.root),
                                              "stage": stage.name, "old": old.name})
        os.replace(self.root, old)
        os.replace(stage, self.root)
        self.assertEqual((self.root / "tasks.json").read_bytes(), b"staged newer root")
        result = recover_interrupted_restore(self.root, offline=True)
        self.assertTrue(result["recovered"])
        self.assertEqual((self.root / "tasks.json").read_bytes(), original)
        self.assertFalse(stage.exists())

    def test_modified_recovery_journal_is_rejected_without_touching_root(self):
        import full_recovery
        previous = (self.root / "tasks.json").read_bytes()
        journal = full_recovery._journal_path(self.root)
        full_recovery._journal_write(journal, {
            "root": str(self.root), "stage": "../other",
            "old": ".madar-restore-old-" + "c" * 24})
        with self.assertRaises(RecoveryError):
            recover_interrupted_restore(self.root, offline=True)
        self.assertEqual((self.root / "tasks.json").read_bytes(), previous)
        self.assertTrue(journal.exists())

    def test_existing_path_symlink_is_rejected(self):
        link = self.root / "finance.json"
        link.unlink()
        try:
            link.symlink_to(self.parent / "outside.json")
        except (OSError, NotImplementedError):
            self.skipTest("Creating symlinks not supported on this filesystem")
        with self.assertRaises(RecoveryError):
            create_full_backup(self.root, self.archive, offline=True)
        self.assertFalse(self.archive.exists())


if __name__ == "__main__":
    unittest.main()
