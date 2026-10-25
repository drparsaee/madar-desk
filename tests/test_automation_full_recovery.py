"""Real five-domain full archive roundtrips, only with disposable local roots.

These integration tests intentionally call the production full_recovery API,
without starting a host, opening APPDATA, or invoking a subprocess.
"""

import base64
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import warnings
import zipfile

import automation_v1
import collab
import finance
from app_storage import IntegrityError, UnifiedAppStorage, with_automation
from attachments import AttachmentError, AttachmentStore
from full_recovery import (
    RecoveryError, create_full_backup, recover_interrupted_restore,
    restore_full_backup,
)
from test_data_model import legacy


NOW = "2026-10-21T09:30:00Z"
USERS = {
    "owner": {"username": "owner", "role": "admin", "projects": None},
    "editor": {"username": "editor", "role": "editor", "projects": ["p1"]},
}
EVENTS = [
    {"type": "event.publish", "eventId": "recover-event-01", "cardId": "t1",
     "trigger": "card_moved", "data": {"toColumnId": "done"}},
    {"type": "event.publish", "eventId": "recover-event-02", "cardId": "t1",
     "trigger": "card_moved", "data": {"toColumnId": "done"}},
]


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


class ActivatedAutomationFullRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-five-domain-recovery-")
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name)
        self.root = self.parent / "source"
        self.root.mkdir()
        self.archive = self.parent / "five-domains.zip"
        self.db_file = self.root / "madar-unified.sqlite3"
        self.database = UnifiedAppStorage(self.db_file)

        four = {"tasks": legacy(), "collab": collab.empty_state(),
                "finance": finance.empty_finance_state(), "completion_outbox": []}
        first = self.database.commit(four, expected_revision=0)
        five = with_automation(first.bundle)
        cards, projects = five["tasks"]["tasks"], five["tasks"]["projects"]
        configured = collab.apply_command(
            five["collab"], {"type": "rule.upsert", "eventId": "recovery-rule-setup",
                             "rule": {"id": "recovery-rule", "projectId": "p1",
                                      "trigger": "card_moved",
                                      "conditions": [{"field": "toColumnId", "equals": "done"}],
                                      "actions": [{"type": "comment",
                                                   "text": "Safely restored automated comment"}],
                                      "enabled": True}},
            actor="owner", accounts=USERS, cards=cards, projects=projects, now=NOW)
        five["collab"] = configured["state"]
        queued = automation_v1.enqueue_events(
            five["automation"], EVENTS, actor="editor", accounts=USERS,
            cards=cards, projects=projects, now=NOW)
        self.assertEqual(queued["added"], 2)
        applied = automation_v1.run_batch(
            queued["state"], five["collab"], accounts=USERS, cards=cards,
            projects=projects, now=NOW, limit=1)
        self.assertEqual(applied["applied"], 1)
        five["automation"] = applied["state"]
        five["collab"] = applied["collab"]
        five["completion_outbox"] = [{
            "eventId": "recovery-completion", "completionId": "recovery-done",
            "cardId": "t1", "projectId": "p1", "actor": "owner", "at": NOW,
        }]
        five["tasks"]["tasks"][0]["title"] = "This title must survive recovery"
        self.original = self.database.commit(five, expected_revision=1)
        self.assertEqual(self.original.revision, 2)
        self.assertEqual(len(self.original.bundle["automation"]["audit"]), 3)
        self.assertEqual(len(self.original.bundle["automation"]["receipts"]), 1)
        self.assertEqual(len(self.original.bundle["automation"]["jobs"]), 1)
        (self.root / "unified-active.json").write_bytes(_json_bytes(
            {"schema": 1, "database": "madar-unified.sqlite3"}))

        self.attachments = AttachmentStore(self.root / "attachment-storage")
        self.original_payload = "آزمایش بازیابی پیوست \n attachment audit 01".encode("utf-8")
        self.attachment = self._upload("recover-attachment-01", "original.txt", self.original_payload)

    def _upload(self, request_id, filename, content):
        return self.attachments.upload(
            actor="owner", accounts=USERS, cards=self.original.bundle["tasks"]["tasks"],
            projects=self.original.bundle["tasks"]["projects"], card_id="t1",
            filename=filename, content_base64=base64.b64encode(content).decode("ascii"),
            request_id=request_id, now=NOW)

    def _read_attachment(self, storage, attachment_id):
        result = storage.read(
            attachment_id=attachment_id, actor="owner", accounts=USERS,
            cards=self.original.bundle["tasks"]["tasks"],
            projects=self.original.bundle["tasks"]["projects"])
        return base64.b64decode(result["contentBase64"])

    def _make_invalid_archive(self, filename, *, changed=None, omitted=(), extra=None,
                              refresh_outer_manifest=False):
        """Modify a ZIP copy; never edit the valid source archive."""
        target = self.parent / filename
        with zipfile.ZipFile(self.archive, "r") as incoming:
            files = {name: incoming.read(name) for name in incoming.namelist()}
        for name in omitted:
            files.pop(name, None)
        if changed:
            files.update(changed)
        if refresh_outer_manifest:
            manifest = json.loads(files["manifest.json"])
            for zip_name in list(manifest["files"]):
                name = "data/" + zip_name
                if name not in files:
                    continue
                raw = files[name]
                manifest["files"][zip_name] = {
                    "size": len(raw), "sha256": sha256(raw).hexdigest()}
            files["manifest.json"] = _json_bytes(manifest)
        with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_STORED) as output:
            for name, content in files.items():
                output.writestr(name, content)
            if extra:
                output.writestr(extra[0], extra[1])
        return target

    def _assert_live_root_unchanged(self):
        actual = UnifiedAppStorage(self.db_file)
        self.assertTrue(actual.integrity_check())
        self.assertEqual(actual.load(), self.original)
        self.assertEqual(self._read_attachment(
            AttachmentStore(self.root / "attachment-storage"), self.attachment["id"]),
            self.original_payload)
        self.assertEqual(recover_interrupted_restore(self.root, offline=True),
                         {"recovered": False})
        self.assertFalse(list(self.parent.glob("madar-pre-restore-*.zip")))

    def test_full_backup_and_restore_five_domains_with_audit_receipts_and_attachments(self):
        report = create_full_backup(self.root, self.archive, offline=True)
        self.assertGreaterEqual(report["files"], 5)
        with zipfile.ZipFile(self.archive, "r") as zipped:
            members = zipped.namelist()
            self.assertIn("data/madar-unified.sqlite3", members)
            self.assertIn("data/attachment-storage/attachments.sqlite3", members)
            self.assertIn("data/attachment-storage/blobs/" +
                          self.attachment["sha256"][:2] + "/" + self.attachment["sha256"], members)

        later = deepcopy(self.original.bundle)
        pending = automation_v1.run_batch(
            later["automation"], later["collab"], accounts=USERS,
            cards=later["tasks"]["tasks"], projects=later["tasks"]["projects"],
            now=NOW, limit=2)
        self.assertEqual(pending["applied"], 1)
        later["automation"], later["collab"] = pending["state"], pending["collab"]
        later["tasks"]["tasks"][0]["title"] = "Changed after archive"
        later["completion_outbox"] = []
        newest = self.database.commit(later, expected_revision=2)
        self.assertEqual(newest.revision, 3)
        new_upload = self._upload("recover-attachment-02", "later.txt", b"later upload only")

        result = restore_full_backup(self.root, self.archive, offline=True)
        self.assertTrue(Path(result["preRestoreArchive"]).is_file())
        self.assertTrue(Path(result["preRestoreRoot"]).is_dir())
        recovered = UnifiedAppStorage(self.db_file)
        self.assertTrue(recovered.integrity_check())
        self.assertEqual(recovered.load(), self.original)
        self.assertEqual(recovered.history(), [2, 1])
        self.assertEqual(recovered.load_revision(1).bundle.keys(),
                         self.original.bundle.keys() - {"automation"})
        self.assertEqual(recovered.load().bundle["automation"]["receipts"],
                         self.original.bundle["automation"]["receipts"])
        self.assertEqual(recovered.load().bundle["automation"]["audit"],
                         self.original.bundle["automation"]["audit"])
        self.assertEqual(recovered.load().bundle["automation"]["jobs"],
                         self.original.bundle["automation"]["jobs"])
        recovered_attachments = AttachmentStore(self.root / "attachment-storage")
        self.assertEqual(self._read_attachment(recovered_attachments, self.attachment["id"]),
                         self.original_payload)
        self.assertEqual(len(recovered_attachments.list_card(
            actor="owner", accounts=USERS, cards=self.original.bundle["tasks"]["tasks"],
            projects=self.original.bundle["tasks"]["projects"], card_id="t1")), 1)
        self.assertEqual(self._read_attachment(
            AttachmentStore(Path(result["preRestoreRoot"]) / "attachment-storage"), new_upload["id"]),
            b"later upload only")
        rollback = UnifiedAppStorage(Path(result["preRestoreRoot"]) / "madar-unified.sqlite3")
        self.assertEqual(rollback.load(), newest)
        self.assertEqual(recover_interrupted_restore(self.root, offline=True),
                         {"recovered": False})

    def test_damaged_archives_are_rejected_before_root_swap_or_rollback_archive(self):
        create_full_backup(self.root, self.archive, offline=True)
        with zipfile.ZipFile(self.archive) as zipped:
            db_raw = zipped.read("data/madar-unified.sqlite3")
            blob_name = "data/attachment-storage/blobs/" + self.attachment["sha256"][:2] + "/" + self.attachment["sha256"]
            blob_raw = zipped.read(blob_name)
        attacks = {
            "missing-db": self._make_invalid_archive(
                "missing-db.zip", omitted=("data/madar-unified.sqlite3",)),
            "db-checksum": self._make_invalid_archive(
                "db-checksum.zip", changed={"data/madar-unified.sqlite3": db_raw[:-1] + b"x"}),
            "missing-blob": self._make_invalid_archive(
                "missing-blob.zip", omitted=(blob_name,)),
            "traversal": self._make_invalid_archive(
                "traversal.zip", extra=("data/../injected.txt", b"forbidden")),
            "blob-damaged-even-with-updated-outer-manifest": self._make_invalid_archive(
                "blob-damaged.zip", changed={blob_name: b"Z" * len(blob_raw)},
                refresh_outer_manifest=True),
        }
        for label, malicious in attacks.items():
            with self.subTest(attack=label):
                with self.assertRaises((RecoveryError, ValueError, AttachmentError,
                                        IntegrityError, zipfile.BadZipFile)):
                    restore_full_backup(self.root, malicious, offline=True)
                self._assert_live_root_unchanged()

    def test_forged_archive_checksums_cannot_hide_semantically_invalid_automation(self):
        create_full_backup(self.root, self.archive, offline=True)
        with zipfile.ZipFile(self.archive) as zipped:
            database_blob = zipped.read("data/madar-unified.sqlite3")
        damaged_db = self.parent / "forged-automation.sqlite3"
        damaged_db.write_bytes(database_blob)
        tampered = deepcopy(self.original.bundle)
        tampered["automation"]["audit"][0]["outcome"] = "run-shell"
        encoded = _json_bytes(tampered)
        with closing(sqlite3.connect(damaged_db)) as connection:
            with connection:
                connection.execute("UPDATE app_revisions SET bundle=?,digest=? WHERE revision=2",
                                   (encoded, sha256(encoded).hexdigest()))
        malicious = self._make_invalid_archive(
            "forged-automation.zip",
            changed={"data/madar-unified.sqlite3": damaged_db.read_bytes()},
            refresh_outer_manifest=True)
        with self.assertRaises((RecoveryError, ValueError, AttachmentError,
                                IntegrityError, zipfile.BadZipFile)):
            restore_full_backup(self.root, malicious, offline=True)
        self._assert_live_root_unchanged()

    def test_offline_flag_is_mandatory_and_does_not_create_archives(self):
        with self.assertRaises(RecoveryError):
            create_full_backup(self.root, self.archive)
        self.assertFalse(self.archive.exists())
        create_full_backup(self.root, self.archive, offline=True)
        with self.assertRaises(RecoveryError):
            restore_full_backup(self.root, self.archive)
        self.assertFalse(list(self.parent.glob("madar-pre-restore-*.zip")))
        self._assert_live_root_unchanged()


if __name__ == "__main__":
    unittest.main()
