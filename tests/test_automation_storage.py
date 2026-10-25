"""Automation journal opt-in tests against isolated disposable SQLite databases."""

import copy
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

import automation_v1
import collab
import finance
from app_storage import (
    AUTOMATION_DOMAINS, DOMAINS, IntegrityError, RevisionConflict,
    UnifiedAppStorage, validated_bundle, with_automation,
)
from test_data_model import legacy


NOW = "2026-10-21T09:30:00Z"
ACCOUNTS = [{"username": "owner", "role": "admin", "projects": None},
            {"username": "editor", "role": "editor", "projects": ["p1"]}]
EVENT = {"type": "event.publish", "eventId": "auto-storage-event",
         "cardId": "t1", "trigger": "card_moved", "data": {"toColumnId": "done"}}


def four_bundle():
    return {"tasks": legacy(), "collab": collab.empty_state(),
            "finance": finance.empty_finance_state(), "completion_outbox": []}


def rule_and_queue(five):
    cards, projects = five["tasks"]["tasks"], five["tasks"]["projects"]
    five["collab"] = collab.apply_command(
        five["collab"], {"type": "rule.upsert", "eventId": "upsert-rule", "rule": {
            "id": "safe-rule", "projectId": "p1", "trigger": "card_moved",
            "conditions": [{"field": "toColumnId", "equals": "done"}],
            "actions": [{"type": "comment", "text": "Recorded via durable journal"}],
            "enabled": True,
        }}, actor="owner", accounts=ACCOUNTS, cards=cards, projects=projects, now=NOW
    )["state"]
    five["automation"] = automation_v1.enqueue_events(
        five["automation"], [EVENT], actor="editor", accounts=ACCOUNTS,
        cards=cards, projects=projects, now=NOW
    )["state"]
    return five


class FiveDomainStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-automation-storage-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = self.root / "app.sqlite3"
        self.store = UnifiedAppStorage(self.db)

    def test_old_four_domain_records_preserve_shape_checksum_and_existing_history(self):
        old = self.store.commit(four_bundle(), expected_revision=0)
        self.assertEqual(set(old.bundle), DOMAINS)
        self.assertEqual(self.store.load_revision(1), old)
        self.assertEqual(self.store.history(), [1])
        self.assertEqual(UnifiedAppStorage(self.db).load().sha256, old.sha256)
        self.assertTrue(self.store.integrity_check())
        # sqlite3.Connection.__exit__ commits/rolls back but DOES NOT close on
        # Windows. Explicit closing avoids a leaked handle in temp cleanup.
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual({row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )}, {"app_revisions", "app_head", "app_imports"})

    def test_new_database_stays_four_domain_until_explicit_activation(self):
        first = self.store.commit(four_bundle(), expected_revision=0)
        same = self.store.commit(first.bundle, expected_revision=1)
        self.assertEqual(same.revision, 1)
        activated = self.store.commit(with_automation(first.bundle), expected_revision=1)
        self.assertEqual(activated.revision, 2)
        self.assertEqual(set(activated.bundle), AUTOMATION_DOMAINS)
        self.assertEqual(activated.bundle["automation"], automation_v1.empty_state())
        self.assertEqual(self.store.load_revision(1).bundle, first.bundle)
        self.assertEqual(with_automation(first.bundle)["automation"], automation_v1.empty_state())
        self.assertTrue(self.store.integrity_check())

    def test_reject_implicit_fifth_domain_drop_by_legacy_four_domain_writer(self):
        four = self.store.commit(four_bundle(), expected_revision=0)
        five = self.store.commit(with_automation(four.bundle), expected_revision=1)
        stale = copy.deepcopy(five.bundle)
        stale.pop("automation")
        stale["tasks"]["tasks"][0]["title"] = "Would lose journal"
        with self.assertRaisesRegex(ValueError, "requires automation journal"):
            self.store.commit(stale, expected_revision=2)
        self.assertEqual(self.store.load(), five)
        with self.assertRaisesRegex(ValueError, "Cannot restore four-domain"):
            self.store.restore(1, expected_revision=2)
        self.assertEqual(self.store.history(), [2, 1])
        self.assertTrue(self.store.integrity_check())

    def test_atomic_5_domain_commit_durable_after_reopen_and_journal_replay(self):
        old = self.store.commit(four_bundle(), expected_revision=0)
        queued = rule_and_queue(with_automation(old.bundle))
        queued["tasks"]["tasks"][0]["title"] = "Job queued with task"
        queued["completion_outbox"] = [{
            "eventId": "complete-a", "completionId": "done-a", "cardId": "t1",
            "projectId": "p1", "actor": "owner", "at": NOW
        }]
        committed = self.store.commit(queued, expected_revision=1)
        self.assertEqual(committed.revision, 2)
        reopened = UnifiedAppStorage(self.db)
        persisted = reopened.load().bundle
        self.assertEqual(persisted, validated_bundle(queued))
        self.assertEqual(len(persisted["automation"]["jobs"]), 1)
        delivered = automation_v1.run_batch(
            persisted["automation"], persisted["collab"], accounts=ACCOUNTS,
            cards=persisted["tasks"]["tasks"], projects=persisted["tasks"]["projects"],
            now=NOW
        )
        persisted["collab"] = delivered["collab"]
        persisted["automation"] = delivered["state"]
        persisted["finance"]["cardCosts"] = {}
        result = reopened.commit(persisted, expected_revision=2)
        self.assertEqual(result.revision, 3)
        recovered = UnifiedAppStorage(self.db).load().bundle
        self.assertEqual(len(recovered["collab"]["comments"]), 1)
        self.assertEqual(recovered["automation"]["jobs"], [])
        self.assertIn(EVENT["eventId"], recovered["automation"]["receipts"])
        self.assertEqual(recovered["completion_outbox"], queued["completion_outbox"])
        self.assertEqual(recovered["finance"], persisted["finance"])
        self.assertEqual(recovered["tasks"]["tasks"][0]["title"], "Job queued with task")
        self.assertEqual(reopened.load_revision(2).bundle, validated_bundle(queued))
        self.assertTrue(reopened.integrity_check())

    def test_noop_cas_and_stale_or_concurrent_writes_do_not_lose_journal(self):
        start = self.store.commit(with_automation(four_bundle()), expected_revision=0)
        self.assertEqual(self.store.commit(start.bundle, expected_revision=1).revision, 1)
        barrier = threading.Barrier(2)

        def writer(index):
            candidate = copy.deepcopy(start.bundle)
            candidate["tasks"]["tasks"][0]["title"] = f"writer{index}"
            candidate["automation"]["audit"] = [{
                "sequence": 1, "eventId": f"notice-{index}", "outcome": "queued",
                "attempt": 0, "error": "", "at": NOW
            }]
            candidate["automation"]["nextAudit"] = 2
            barrier.wait(timeout=5)
            try:
                return UnifiedAppStorage(self.db).commit(candidate, expected_revision=1).revision
            except RevisionConflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = sorted(str(v) for v in pool.map(writer, [1, 2]))
        self.assertEqual(outcomes, ["2", "conflict"])
        self.assertEqual(len(self.store.load().bundle["automation"]["audit"]), 1)
        with self.assertRaises(RevisionConflict):
            self.store.commit(start.bundle, expected_revision=1)
        self.assertEqual(self.store.history(), [2, 1])
        self.assertTrue(self.store.integrity_check())

    def test_partial_sql_write_rollback_keeps_all_five_domains(self):
        first = self.store.commit(with_automation(four_bundle()), expected_revision=0)
        candidate = rule_and_queue(copy.deepcopy(first.bundle))
        candidate["tasks"]["tasks"][0]["cost"] = 500
        connection = sqlite3.connect(self.db)
        try:
            with connection:
                connection.execute("CREATE TRIGGER block_head BEFORE UPDATE ON app_head "
                                   "BEGIN SELECT RAISE(ABORT,'synthetic rollback'); END")
        finally:
            connection.close()
        with self.assertRaisesRegex(sqlite3.DatabaseError, "synthetic rollback"):
            self.store.commit(candidate, expected_revision=1)
        self.assertEqual(UnifiedAppStorage(self.db).load(), first)
        self.assertEqual(self.store.history(), [1])

    def test_process_crash_during_uncommitted_five_domain_update_recovers_previous(self):
        first = self.store.commit(with_automation(four_bundle()), expected_revision=0)
        candidate = rule_and_queue(copy.deepcopy(first.bundle))
        candidate["tasks"]["tasks"][0]["title"] = "crashed before commit"
        from app_storage import _encode
        payload = _encode(validated_bundle(candidate))
        payload_path = self.root / "attempt.json"
        payload_path.write_bytes(payload)
        code = (
            "import os, sqlite3,hashlib,sys;"
            "payload=open(sys.argv[2],'rb').read();"
            "db=sqlite3.connect(sys.argv[1],isolation_level=None);"
            "db.execute('BEGIN IMMEDIATE');"
            "db.execute('INSERT INTO app_revisions(revision,parent,bundle,digest,created_at,source) "
            "VALUES(2,1,?,?,?,?)',(payload,hashlib.sha256(payload).hexdigest(),'now','crash'));"
            "db.execute('UPDATE app_head SET revision=2 WHERE id=1');"
            "os._exit(63)"
        )
        crashed = subprocess.run([sys.executable, "-c", code, str(self.db), str(payload_path)],
                                 capture_output=True, timeout=15)
        self.assertEqual(crashed.returncode, 63, crashed.stderr.decode(errors="replace"))
        reopened = UnifiedAppStorage(self.db)
        self.assertEqual(reopened.load(), first)
        self.assertEqual(reopened.history(), [1])
        self.assertTrue(reopened.integrity_check())

    def test_five_domain_sqlite_backup_roundtrip_and_historic_restore(self):
        first = self.store.commit(with_automation(four_bundle()), expected_revision=0)
        modified = rule_and_queue(copy.deepcopy(first.bundle))
        second = self.store.commit(modified, expected_revision=1)
        backup = self.root / "five-backup.sqlite3"
        self.assertEqual(self.store.backup_database(backup), backup)
        self.assertEqual(UnifiedAppStorage(backup).load(), second)
        self.assertTrue(UnifiedAppStorage(backup).integrity_check())
        third = self.store.restore(1, expected_revision=2)
        self.assertEqual(third.revision, 3)
        self.assertEqual(third.bundle, first.bundle)
        self.assertEqual(self.store.load_revision(2).bundle, second.bundle)
        self.assertEqual(UnifiedAppStorage(backup).history(), [2, 1])

    def test_old_db_legacy_import_remains_four_domains_then_can_activate(self):
        source = self.root / "tasks.json"
        original = json.dumps(legacy(), ensure_ascii=False).encode("utf-8")
        source.write_bytes(original)
        initial = self.store.import_legacy(source, backup_dir=self.root / "backups")
        self.assertEqual(set(initial.bundle), DOMAINS)
        backup_file = self.root / "backups" / f"tasks-{sha256(original).hexdigest()}.json"
        self.assertEqual(backup_file.read_bytes(), original)
        five = self.store.commit(with_automation(initial.bundle), expected_revision=1)
        self.assertEqual(five.revision, 2)
        self.assertEqual(set(five.bundle), AUTOMATION_DOMAINS)
        self.assertEqual(self.store.import_legacy(source, backup_dir=self.root / "backups"), five)
        self.assertEqual(self.store.load_revision(1), initial)
        self.assertTrue(self.store.integrity_check())

    def test_invalid_journal_rejected_before_database_write_and_byte_safe(self):
        initial = self.store.commit(with_automation(four_bundle()), expected_revision=0)
        bad_values = [
            {"schemaVersion": 1, "jobs": [{"type": "exec"}], "audit": [], "receipts": {}, "nextAudit": 1},
            {"schemaVersion": 1, "jobs": [], "audit": [], "receipts": {}, "nextAudit": False},
            {"schemaVersion": 1, "jobs": [], "audit": [], "receipts": {}, "nextAudit": 1, "secret": "x"},
            {},
            None
        ]
        for value in bad_values:
            with self.subTest(value=value):
                candidate = copy.deepcopy(initial.bundle)
                candidate["automation"] = value
                with self.assertRaises(ValueError):
                    self.store.commit(candidate, expected_revision=1)
                self.assertEqual(self.store.load(), initial)
                self.assertEqual(self.store.history(), [1])

    def test_tampered_fifth_domain_even_with_recomputed_digest_fails_closed(self):
        initial = self.store.commit(with_automation(four_bundle()), expected_revision=0)
        corrupted = copy.deepcopy(initial.bundle)
        corrupted["automation"]["jobs"] = [{"type": "shell", "command": "echo private"}]
        payload = json.dumps(corrupted, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        connection = sqlite3.connect(self.db)
        try:
            with connection:
                connection.execute(
                    "UPDATE app_revisions SET bundle=?,digest=? WHERE revision=1",
                    (payload, sha256(payload).hexdigest()))
        finally:
            connection.close()
        with self.assertRaisesRegex(IntegrityError, "Corrupt app snapshot"):
            self.store.load()
        with self.assertRaises(IntegrityError):
            self.store.integrity_check()

    def test_old_four_domain_backup_reopens_without_schema_upgrade(self):
        first = self.store.commit(four_bundle(), expected_revision=0)
        backup = self.root / "legacy.sqlite3"
        self.store.backup_database(backup)
        again = UnifiedAppStorage(backup)
        self.assertEqual(again.load(), first)
        upgraded = again.commit(with_automation(first.bundle), expected_revision=1)
        self.assertEqual(upgraded.revision, 2)
        # Original source DB remains four-domain and backup is a distinct file.
        self.assertEqual(set(self.store.load().bundle), DOMAINS)
        self.assertEqual(self.store.history(), [1])


if __name__ == "__main__":
    unittest.main()
