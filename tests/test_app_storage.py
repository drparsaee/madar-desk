"""Integration tests for opt-in unified four-domain transactional SQLite."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

import collab
import finance
from app_storage import (AlreadyInitialized, ImportConflict, IntegrityError,
                         RevisionConflict, UnifiedAppStorage, UnsupportedSchema,
                         validated_bundle)
from test_data_model import legacy


@contextmanager
def sql(path):
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()  # important on Windows for TemporaryDirectory.cleanup


def bundle():
    return {"tasks": legacy(), "collab": collab.empty_state(),
            "finance": finance.empty_finance_state(), "completion_outbox": [
                {"eventId": "completed-abc", "completionId": "completion-abc",
                 "cardId": "t1", "projectId": "p1", "actor": "local",
                 "at": "2026-10-20T20:00:00+03:30"}]}


class UnifiedStorageTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="madar-unified-synthetic-")
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.db = self.folder / "app.sqlite3"
        self.store = UnifiedAppStorage(self.db)

    def test_initialization_has_no_implicit_state_or_real_paths(self):
        self.assertIsNone(self.store.load())
        self.assertEqual(self.store.history(), [])
        with sql(self.db) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertTrue(self.store.integrity_check())

    def test_commit_persists_all_domains_as_one_detached_revision(self):
        source = bundle()
        before = deepcopy(source)
        first = self.store.commit(source, expected_revision=0)
        self.assertEqual(source, before)
        self.assertEqual(first.revision, 1)
        self.assertEqual(first.bundle["collab"], source["collab"])
        self.assertEqual(first.bundle["finance"], source["finance"])
        self.assertEqual(first.bundle["completion_outbox"], source["completion_outbox"])
        self.assertEqual(first.bundle["tasks"]["tasks"][0]["cost"], 350)
        first.bundle["collab"]["rules"].append({"malformed": True})
        reopened = UnifiedAppStorage(self.db).load()
        self.assertEqual(reopened.bundle["collab"], source["collab"])
        self.assertEqual(self.store.history(), [1])
        self.assertTrue(self.store.integrity_check())

    def test_current_native_initial_state_is_backward_compatible_without_appdata(self):
        """Calls the pure factory only, never native_app.Bridge or datadir."""
        from native_app import initial_state, is_valid

        current_host_state = initial_state()
        prepared = {"tasks": current_host_state, "collab": collab.empty_state(),
                    "finance": finance.empty_finance_state(), "completion_outbox": []}
        snapshot = self.store.commit(prepared, expected_revision=0)
        self.assertEqual(snapshot.bundle["tasks"]["version"], 1)
        self.assertTrue(is_valid(snapshot.bundle["tasks"]))
        self.assertEqual(snapshot.bundle["tasks"]["projects"], current_host_state["projects"])
        self.assertEqual(len(snapshot.bundle["tasks"]["tasks"]), len(current_host_state["tasks"]))
        self.assertTrue(UnifiedAppStorage(self.db).integrity_check())

    def test_four_domain_changes_share_single_revision(self):
        first = self.store.commit(bundle(), expected_revision=0)
        newer = deepcopy(first.bundle)
        newer["tasks"]["tasks"][0]["title"] = "new title"
        newer["collab"]["watchers"] = {"t1": ["local"]}
        newer["finance"]["cardCosts"] = {}
        newer["completion_outbox"] = []
        second = self.store.commit(newer, expected_revision=1)
        self.assertEqual(second.revision, 2)
        self.assertEqual(second.bundle, validated_bundle(newer))
        self.assertEqual(self.store.load_revision(1).bundle, first.bundle)
        self.assertEqual(self.store.load_revision(2).bundle, second.bundle)

    def test_actual_collab_comment_and_finance_ledger_roundtrip(self):
        """Exercise existing domain reducers, including financial hash chain."""
        data = bundle()
        accounts = {"local": {"username": "local", "role": "admin", "projects": None},
                    "member": {"username": "member", "role": "viewer", "projects": ["p1"]}}
        projects = data["tasks"]["projects"]
        cards = data["tasks"]["tasks"]
        stamp = "2026-10-20T16:10:00Z"
        data["collab"] = collab.apply_command(
            data["collab"], {"type": "comment.add", "eventId": "comment-event-1",
                             "cardId": "t1", "text": "Approved by @member"},
            actor="local", accounts=accounts, cards=cards, projects=projects,
            now=stamp)["state"]
        contract = {"customer": {"name": "Buyer", "reference": "B1"},
                    "lines": [{"id": "line1", "description": "Printing",
                               "quantity": 1, "unitPrice": 1000}],
                    "discount": 0, "tax": 0, "advance": 0, "autoInvoice": True}
        data["finance"] = finance.apply_finance_command(
            data["finance"], {"type": "contract.set", "eventId": "sale-evt-1",
                              "cardId": "t1", "sale": contract},
            actor="local", accounts=accounts, cards=cards, projects=projects,
            now=stamp)["state"]
        cards[0]["status"] = "done"
        data["finance"] = finance.apply_finance_command(
            data["finance"], {"type": "completion.record", "eventId": "comp-evt-1",
                              "cardId": "t1", "completionId": "comp1"},
            actor="local", accounts=accounts, cards=cards, projects=projects,
            now=stamp)["state"]
        data["completion_outbox"] = []
        self.assertGreater(len(data["finance"]["ledger"]), 0)
        self.assertGreater(len(data["finance"]["invoices"]), 0)
        first = self.store.commit(data, expected_revision=0)
        from_disk = UnifiedAppStorage(self.db).load()
        self.assertEqual(from_disk.bundle, first.bundle)
        self.assertTrue(collab.validate_state(from_disk.bundle["collab"]))
        self.assertTrue(finance.validate_finance_state(from_disk.bundle["finance"]))
        self.assertTrue(self.store.integrity_check())

    def test_noop_and_stale_cas(self):
        first = self.store.commit(bundle(), expected_revision=0)
        same = self.store.commit(first.bundle, expected_revision=1)
        self.assertEqual(same.revision, 1)
        modified = deepcopy(first.bundle)
        modified["tasks"]["tasks"][0]["title"] = "update"
        self.store.commit(modified, expected_revision=1)
        with self.assertRaisesRegex(RevisionConflict, "CONFLICT"):
            self.store.commit(modified, expected_revision=1)
        self.assertEqual(self.store.history(), [2, 1])

    def test_concurrent_conflicting_writers_one_wins(self):
        first = self.store.commit(bundle(), expected_revision=0)
        barrier = Barrier(2)

        def submit(index):
            edited = deepcopy(first.bundle)
            edited["tasks"]["tasks"][0]["title"] = f"writer{index}"
            barrier.wait(timeout=10)
            try:
                return UnifiedAppStorage(self.db).commit(edited, expected_revision=1).revision
            except RevisionConflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, (1, 2)))
        self.assertEqual(sorted(map(str, results)), ["2", "conflict"])
        self.assertEqual(self.store.history(), [2, 1])

    def test_invalid_finance_and_collab_are_rejected_without_any_partial_write(self):
        old = self.store.commit(bundle(), expected_revision=0)
        invalids = [
            lambda b: b["finance"].update(nextInvoiceNumber=0),
            lambda b: b["finance"].update(ledger=[{"invalid": "hash"}]),
            lambda b: b["collab"].update(schemaVersion=99),
            lambda b: b["collab"].update(comments=[{"invalid": "comment"}]),
            lambda b: b["tasks"]["tasks"][0].update(projectId="absent"),
            lambda b: b["completion_outbox"][0].update(at="not a timestamp"),
            lambda b: b["completion_outbox"].append(deepcopy(b["completion_outbox"][0])),
        ]
        for change in invalids:
            with self.subTest(change=change):
                edited = deepcopy(old.bundle)
                change(edited)
                with self.assertRaises(ValueError):
                    self.store.commit(edited, expected_revision=1)
                self.assertEqual(self.store.load().sha256, old.sha256)
                self.assertEqual(self.store.history(), [1])

    def test_partial_bundle_cannot_clear_collab_finance_or_outbox(self):
        for invalid in ({"tasks": legacy()}, {**bundle(), "other": {}},
                        {**bundle(), "finance": None}):
            with self.assertRaises(ValueError):
                self.store.commit(invalid, expected_revision=0)
        self.assertIsNone(self.store.load())

    def test_failure_after_revision_insert_rolls_back_all_four_domains(self):
        first = self.store.commit(bundle(), expected_revision=0)
        changed = deepcopy(first.bundle)
        changed["tasks"]["tasks"][0]["title"] = "should rollback"
        changed["completion_outbox"] = []
        with sql(self.db) as conn:
            conn.execute("CREATE TRIGGER prevent_head BEFORE UPDATE ON app_head "
                         "BEGIN SELECT RAISE(ABORT,'injected four-domain failure'); END")
        with self.assertRaisesRegex(sqlite3.DatabaseError, "injected"):
            self.store.commit(changed, expected_revision=1)
        self.assertEqual(UnifiedAppStorage(self.db).load().sha256, first.sha256)
        self.assertEqual(self.store.history(), [1])

    def test_crash_before_commit_and_wal_reopen_is_consistent(self):
        first = self.store.commit(bundle(), expected_revision=0)
        # A separate process inserts an uncommitted snapshot then dies without
        # an SQLite COMMIT. SQLite must recover head and revision as a unit.
        script = (
            "import os,sqlite3,sys;"
            "c=sqlite3.connect(sys.argv[1],isolation_level=None);"
            "c.execute('BEGIN IMMEDIATE');"
            "c.execute(\"INSERT INTO app_revisions(revision,parent,bundle,digest,created_at,source) "
            "VALUES(2,1,X'7B7D','bad','now','crash')\");"
            "c.execute('UPDATE app_head SET revision=2 WHERE id=1');"
            "os._exit(53)"
        )
        result = subprocess.run([sys.executable, "-c", script, str(self.db)],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 53, result.stderr.decode(errors="replace"))
        after = UnifiedAppStorage(self.db)
        self.assertEqual(after.load().sha256, first.sha256)
        self.assertEqual(after.history(), [1])
        self.assertTrue(after.integrity_check())

    def test_restore_is_new_revision_and_keeps_complete_history(self):
        original = self.store.commit(bundle(), expected_revision=0)
        changed = deepcopy(original.bundle)
        changed["collab"]["watchers"] = {"t1": ["admin"]}
        changed["completion_outbox"] = []
        second = self.store.commit(changed, expected_revision=1)
        with self.assertRaises(RevisionConflict):
            self.store.restore(1, expected_revision=1)
        restored = self.store.restore(1, expected_revision=2)
        self.assertEqual(restored.revision, 3)
        self.assertEqual(restored.bundle, original.bundle)
        self.assertEqual(self.store.load_revision(2).bundle, second.bundle)

    def test_integrity_rejects_payload_tampering_even_with_good_sqlite(self):
        self.store.commit(bundle(), expected_revision=0)
        with sql(self.db) as conn:
            conn.execute("UPDATE app_revisions SET bundle=X'7B7D' WHERE revision=1")
        with self.assertRaises(IntegrityError):
            self.store.load()
        with self.assertRaises(IntegrityError):
            self.store.integrity_check()

    def test_recomputed_hash_cannot_hide_semantically_invalid_finance_state(self):
        self.store.commit(bundle(), expected_revision=0)
        bad = deepcopy(self.store.load().bundle)
        bad["finance"]["nextInvoiceNumber"] = 15
        raw = json.dumps(bad, ensure_ascii=False, separators=(",", ":"),
                         sort_keys=True).encode("utf-8")
        with sql(self.db) as conn:
            conn.execute("UPDATE app_revisions SET bundle=?,digest=? WHERE revision=1",
                         (raw, sha256(raw).hexdigest()))
        with self.assertRaisesRegex(IntegrityError, "Corrupt app snapshot"):
            self.store.load()
        self.assertEqual(self.store.history(), [1])

    def test_outbox_preserves_unresolved_references_for_safe_replay(self):
        data = bundle()
        data["completion_outbox"][0]["cardId"] = "deleted-card"
        data["completion_outbox"][0]["projectId"] = "removed-project"
        state = self.store.commit(data, expected_revision=0)
        self.assertEqual(state.bundle["completion_outbox"], data["completion_outbox"])

    def test_reject_nan_duplicate_domain_unknown_keys_and_forged_revision(self):
        data = bundle()
        data["collab"]["bad-key"] = "invalid"
        with self.assertRaises(ValueError):
            self.store.commit(data, expected_revision=0)
        with self.assertRaises(ValueError):
            self.store.commit(bundle(), expected_revision=True)

    def test_backup_database_is_consistent_and_no_overwrite(self):
        first = self.store.commit(bundle(), expected_revision=0)
        destination = self.folder / "db-backups" / "snap.sqlite3"
        self.assertEqual(self.store.backup_database(destination), destination)
        self.assertEqual(UnifiedAppStorage(destination).load().bundle, first.bundle)
        with self.assertRaises(FileExistsError):
            self.store.backup_database(destination)
        changed = deepcopy(first.bundle)
        changed["completion_outbox"] = []
        self.store.commit(changed, expected_revision=1)
        self.assertEqual(UnifiedAppStorage(destination).load().bundle, first.bundle)

    def test_future_database_refused_without_changing_journal_mode(self):
        future = self.folder / "future.sqlite3"
        with sql(future) as conn:
            conn.execute("PRAGMA user_version=55")
        with self.assertRaises(UnsupportedSchema):
            UnifiedAppStorage(future)
        with sql(future) as conn:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "delete")


class LegacyImportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-unified-import-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.db = self.folder / "app.sqlite3"
        self.store = UnifiedAppStorage(self.db)
        self.source_dir = self.folder / "sources"
        self.source_dir.mkdir()
        self.backups = self.folder / "backups"
        data = bundle()
        self.paths = {}
        for domain, value in data.items():
            path = self.source_dir / f"{domain}.json"
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            self.paths[domain] = path

    def import_all(self):
        return self.store.import_legacy(self.paths["tasks"],
                                        collab_json=self.paths["collab"],
                                        finance_json=self.paths["finance"],
                                        outbox_json=self.paths["completion_outbox"],
                                        backup_dir=self.backups)

    def test_all_four_sources_backup_first_single_atomic_revision(self):
        original = {key: path.read_bytes() for key, path in self.paths.items()}
        result = self.import_all()
        self.assertEqual(result.revision, 1)
        self.assertEqual(result.bundle, validated_bundle(bundle()))
        self.assertEqual(self.store.history(), [1])
        for name, content in original.items():
            self.assertEqual(self.paths[name].read_bytes(), content)
            destination = self.backups / f"{name}-{sha256(content).hexdigest()}.json"
            self.assertEqual(destination.read_bytes(), content)
        with sql(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM app_imports").fetchone()[0], 1)
        self.assertTrue(self.store.integrity_check())

    def test_idempotent_import_does_not_revert_later_user_edits(self):
        original = self.import_all()
        edited = deepcopy(original.bundle)
        edited["tasks"]["tasks"][0]["title"] = "after import"
        edited["completion_outbox"] = []
        second = self.store.commit(edited, expected_revision=1)
        repeat = self.import_all()
        self.assertEqual(repeat, second)
        self.assertEqual(self.store.history(), [2, 1])

    def test_omitted_optional_domains_are_empty_and_invalid_missing_path_fails(self):
        result = self.store.import_legacy(self.paths["tasks"], backup_dir=self.backups)
        self.assertEqual(result.bundle["collab"], collab.empty_state())
        self.assertEqual(result.bundle["finance"], finance.empty_finance_state())
        self.assertEqual(result.bundle["completion_outbox"], [])
        self.assertEqual(len(list(self.backups.glob("*.json"))), 1)
        other = UnifiedAppStorage(self.folder / "other.sqlite3")
        with self.assertRaises(FileNotFoundError):
            other.import_legacy(self.paths["tasks"], collab_json=self.folder / "missing.json",
                                backup_dir=self.backups)
        self.assertIsNone(other.load())

    def test_bad_source_in_any_domain_aborts_before_all_backups_and_sql(self):
        for domain, broken in (("tasks", b"{}"), ("collab", b"not-json"),
                               ("finance", b'{"schemaVersion":NaN}'),
                               ("completion_outbox", b'{"eventId":0}')):
            with self.subTest(domain=domain):
                good = self.paths[domain].read_bytes()
                self.paths[domain].write_bytes(broken)
                try:
                    with self.assertRaises(ValueError):
                        self.import_all()
                    self.assertEqual(self.store.history(), [])
                    self.assertFalse(self.backups.exists())
                finally:
                    self.paths[domain].write_bytes(good)

    def test_duplicate_json_keys_are_not_silently_trusted(self):
        self.paths["finance"].write_bytes(b'{"schemaVersion":1,"schemaVersion":1}')
        with self.assertRaises(ValueError):
            self.import_all()
        self.assertFalse(self.backups.exists())

    def test_changed_source_is_conflict_and_preserves_committed_bundle(self):
        first = self.import_all()
        replaced = bundle()["finance"]
        replaced["nextInvoiceNumber"] = 2  # invalid state; reject early
        self.paths["finance"].write_text(json.dumps(replaced), encoding="utf8")
        with self.assertRaises(ValueError):
            self.import_all()
        self.assertEqual(self.store.load(), first)
        self.paths["finance"].write_text(json.dumps(finance.empty_finance_state(), indent=4),
                                        encoding="utf8")  # valid different bytes
        with self.assertRaises(ImportConflict):
            self.import_all()
        self.assertEqual(self.store.load(), first)

    def test_existing_backup_poisoning_is_detected_not_overwritten(self):
        source = self.paths["finance"].read_bytes()
        self.backups.mkdir()
        target = self.backups / f"finance-{sha256(source).hexdigest()}.json"
        target.write_bytes(b"foreign data")
        with self.assertRaises(ImportConflict):
            self.import_all()
        self.assertEqual(target.read_bytes(), b"foreign data")
        self.assertIsNone(self.store.load())

    def test_failure_in_fourth_backup_cannot_initialize_half_a_database(self):
        real_link = __import__("os").link
        calls = {"n": 0}

        def fail_fourth(src, dst):
            calls["n"] += 1
            if calls["n"] == 4:
                raise OSError("synthetic fourth backup failed")
            return real_link(src, dst)

        with patch("app_storage.os.link", side_effect=fail_fourth):
            with self.assertRaisesRegex(OSError, "fourth backup"):
                self.import_all()
        self.assertEqual(self.store.history(), [])
        self.assertEqual(len(list(self.backups.glob("*.json"))), 3)
        # Valid preserved backups can be reused on the next import.
        self.assertEqual(self.import_all().revision, 1)

    def test_failure_after_bundle_insert_rolls_back_import_metadata_and_head(self):
        with sql(self.db) as conn:
            conn.execute("CREATE TRIGGER abort_metadata BEFORE INSERT ON app_imports "
                         "BEGIN SELECT RAISE(ABORT, 'synthetic crash'); END")
        with self.assertRaisesRegex(sqlite3.DatabaseError, "synthetic crash"):
            self.import_all()
        self.assertIsNone(self.store.load())
        self.assertEqual(self.store.history(), [])
        self.assertEqual(len(list(self.backups.glob("*.json"))), 4)

    def test_uncommitted_four_file_import_process_death_reopens_empty_db(self):
        """Process terminates after *all* SQL entities are staged, before COMMIT."""
        script = (
            "import os,sqlite3,sys;"
            "db=sqlite3.connect(sys.argv[1],isolation_level=None);"
            "db.execute('BEGIN IMMEDIATE');"
            "db.execute(\"INSERT INTO app_revisions(revision,parent,bundle,digest,created_at,source) "
            "VALUES(1,0,X'7B7D','broken','now','legacy-four-domain')\");"
            "db.execute('UPDATE app_head SET revision=1 WHERE id=1');"
            "db.execute(\"INSERT INTO app_imports(name,fingerprint,manifest,revision,created_at) "
            "VALUES('legacy-four-domain','fake',X'7B7D',1,'now')\");"
            "os._exit(51)"
        )
        result = subprocess.run([sys.executable, "-c", script, str(self.db)],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 51, result.stderr.decode(errors="replace"))
        reopened = UnifiedAppStorage(self.db)
        self.assertIsNone(reopened.load())
        self.assertEqual(reopened.history(), [])
        with sql(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM app_imports").fetchone()[0], 0)
        self.assertTrue(reopened.integrity_check())
        self.assertEqual(self.import_all().revision, 1)

    def test_concurrent_imports_one_revision_and_four_backups(self):
        barrier = Barrier(2)

        def worker(_):
            local = UnifiedAppStorage(self.db)
            barrier.wait(timeout=10)
            return local.import_legacy(self.paths["tasks"], collab_json=self.paths["collab"],
                                       finance_json=self.paths["finance"],
                                       outbox_json=self.paths["completion_outbox"],
                                       backup_dir=self.backups)

        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = list(pool.map(worker, (1, 2)))
        self.assertEqual(a, b)
        self.assertEqual(self.store.history(), [1])
        self.assertEqual(len(list(self.backups.glob("*.json"))), 4)

    def test_preexisting_db_cannot_be_overwritten_by_import(self):
        original = self.store.commit(bundle(), expected_revision=0)
        with self.assertRaises(AlreadyInitialized):
            self.import_all()
        self.assertEqual(self.store.load(), original)


if __name__ == "__main__":
    unittest.main()
