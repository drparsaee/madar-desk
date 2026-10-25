"""SQLite snapshots: ACID, strict revisions, backup-first JSON migration."""

import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
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

from data_model import normalize_plus
from persistent_store import (
    MigrationConflict, RevisionConflict, SQLiteSnapshotStore,
    SnapshotIntegrityError, StoreAlreadyInitialized, UnsupportedSchemaError,
)
from test_data_model import legacy


@contextmanager
def sql_connection(path):
    """SQLite `with conn:` commits, but it does not close Windows handles."""
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-sqlite-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data.sqlite3"
        self.store = SQLiteSnapshotStore(self.path)

    def test_new_file_creates_empty_supported_schema(self):
        self.assertIsNone(self.store.load())
        self.assertEqual(self.store.history(), [])
        with sql_connection(self.path) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertTrue(self.store.integrity_check())

    def test_save_and_reopen_roundtrip_every_legacy_property(self):
        state = legacy()
        before = copy.deepcopy(state)
        snapshot = self.store.save(state, expected_revision=0)
        self.assertEqual(snapshot.revision, 1)
        self.assertEqual(state, before)
        self.assertEqual(snapshot.state, normalize_plus(state))
        reopened = SQLiteSnapshotStore(self.path).load()
        self.assertEqual(snapshot.state, reopened.state)
        self.assertEqual(snapshot.sha256, reopened.sha256)
        self.assertEqual(reopened.state["tasks"][0]["cost"], 350)
        self.assertEqual(reopened.state["tasks"][0]["assignees"], ["editor"])
        self.assertEqual(reopened.state["tasks"][0]["fileLinks"], [])

    def test_cas_rejects_stale_writes_and_noop_does_not_advance(self):
        first = self.store.save(legacy(), expected_revision=0)
        repeated = self.store.save(first.state, expected_revision=1)
        self.assertEqual(first.revision, repeated.revision)
        changed = copy.deepcopy(first.state)
        changed["tasks"][0]["title"] = "Updated"
        second = SQLiteSnapshotStore(self.path).save(changed, expected_revision=1)
        self.assertEqual(second.revision, 2)
        with self.assertRaisesRegex(RevisionConflict, "CONFLICT"):
            self.store.save(changed, expected_revision=1)
        self.assertEqual(self.store.load().revision, 2)
        self.assertEqual(self.store.history(), [2, 1])
        self.assertEqual(self.store.load_revision(1).state["tasks"][0]["title"], "اول")

    def test_concurrent_writers_get_exactly_one_revision_commit(self):
        original = self.store.save(legacy(), expected_revision=0)
        barrier = Barrier(2)

        def writer(name):
            changed = copy.deepcopy(original.state)
            changed["tasks"][0]["title"] = name
            other = SQLiteSnapshotStore(self.path)
            barrier.wait(timeout=6)
            try:
                return ("committed", other.save(changed, expected_revision=1).revision)
            except RevisionConflict:
                return ("conflict", None)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(writer, ("writer-a", "writer-b")))
        self.assertEqual(sorted(label for label, _ in results), ["committed", "conflict"])
        self.assertEqual(self.store.history(), [2, 1])
        self.assertIn(self.store.load().state["tasks"][0]["title"], ("writer-a", "writer-b"))

    def test_invalid_json_does_not_mutate_committed_state(self):
        original = self.store.save(legacy(), expected_revision=0)
        for invalid in (lambda s: s["tasks"][0].update(projectId="not-found"),
                        lambda s: s["tasks"][0].update(cost=-10),
                        lambda s: s.update(extension=float("nan"))):
            data = legacy()
            invalid(data)
            with self.assertRaises(ValueError):
                self.store.save(data, expected_revision=1)
            self.assertEqual(self.store.load().sha256, original.sha256)
            self.assertEqual(self.store.history(), [1])

    def test_snapshot_and_head_update_are_one_transaction(self):
        first = self.store.save(legacy(), expected_revision=0)
        new = copy.deepcopy(first.state)
        new["tasks"][0]["title"] = "Must roll back"
        # SQLite itself aborts after the new snapshot was inserted.
        with sql_connection(self.path) as conn:
            conn.execute("CREATE TRIGGER block_head BEFORE UPDATE ON head "
                         "BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaisesRegex(sqlite3.DatabaseError, "injected failure"):
            self.store.save(new, expected_revision=1)
        self.assertEqual(self.store.history(), [1])
        self.assertEqual(SQLiteSnapshotStore(self.path).load().sha256, first.sha256)

    def test_process_exit_during_uncommitted_write_does_not_publish_snapshot(self):
        first = self.store.save(legacy(), expected_revision=0)
        script = (
            "import os,sqlite3,sys; "
            "c=sqlite3.connect(sys.argv[1],isolation_level=None); "
            "c.execute('BEGIN IMMEDIATE'); "
            "c.execute(\"INSERT INTO snapshots(revision,parent_revision,payload,digest,created_at,source) "
            "VALUES(2,1,X'7B7D','invalid','now','crash')\"); "
            "os._exit(37)"
        )
        result = subprocess.run([sys.executable, "-c", script, str(self.path)],
                                capture_output=True, timeout=12)
        self.assertEqual(result.returncode, 37, result.stderr.decode(errors="replace"))
        reopened = SQLiteSnapshotStore(self.path)
        self.assertEqual(reopened.load().sha256, first.sha256)
        self.assertEqual(reopened.history(), [1])
        self.assertTrue(reopened.integrity_check())

    def test_restore_appends_new_revision_and_preserves_history(self):
        a = self.store.save(legacy(), expected_revision=0)
        b_state = copy.deepcopy(a.state)
        b_state["tasks"][0]["title"] = "new"
        b = self.store.save(b_state, expected_revision=1)
        with self.assertRaises(RevisionConflict):
            self.store.restore(1, expected_revision=1)
        restored = self.store.restore(1, expected_revision=2)
        self.assertEqual(restored.revision, 3)
        self.assertEqual(restored.source, "restore:1")
        self.assertEqual(restored.state, a.state)
        self.assertEqual(self.store.load_revision(2).state, b.state)

    def test_explicit_restore_of_same_content_is_auditable(self):
        a = self.store.save(legacy(), expected_revision=0)
        same = self.store.restore(1, expected_revision=a.revision)
        self.assertEqual(same.revision, 2)
        self.assertEqual(same.state, a.state)
        self.assertEqual(same.source, "restore:1")
        self.assertEqual(self.store.history(), [2, 1])

    def test_backup_uses_online_sqlite_api_and_is_immutable(self):
        initial = self.store.save(legacy(), expected_revision=0)
        destination = self.root / "backups" / "first.sqlite3"
        result = self.store.backup_database(destination)
        self.assertEqual(result, destination)
        self.assertEqual(SQLiteSnapshotStore(result).load().state, initial.state)
        with self.assertRaises(FileExistsError):
            self.store.backup_database(destination)
        with self.assertRaises(FileExistsError):
            self.store.backup_database(self.path)
        changed = copy.deepcopy(initial.state)
        changed["tasks"][0]["title"] = "after backup"
        self.store.save(changed, expected_revision=1)
        self.assertEqual(SQLiteSnapshotStore(result).load().state, initial.state)

    def test_backup_publish_failure_does_not_leave_target_or_touch_source(self):
        original = self.store.save(legacy(), expected_revision=0)
        destination = self.root / "backups" / "unpublished.sqlite3"
        with patch("persistent_store.os.link", side_effect=OSError("no atomic link")):
            with self.assertRaisesRegex(OSError, "no atomic link"):
                self.store.backup_database(destination)
        self.assertFalse(destination.exists())
        self.assertEqual(self.store.load(), original)

    def test_schema_upgrade_refuses_unknown_newer_or_unversioned_db(self):
        future = self.root / "future.sqlite3"
        with sql_connection(future) as conn:
            conn.execute("PRAGMA user_version=17")
        with self.assertRaises(UnsupportedSchemaError):
            SQLiteSnapshotStore(future)
        with sql_connection(future) as conn:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        unknown = self.root / "unversioned.sqlite3"
        with sql_connection(unknown) as conn:
            conn.execute("CREATE TABLE users(id TEXT)")
        with self.assertRaises(UnsupportedSchemaError):
            SQLiteSnapshotStore(unknown)
        with sql_connection(unknown) as conn:
            self.assertIn("users", [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")])

    def test_checksum_tampering_detected_on_read(self):
        self.store.save(legacy(), expected_revision=0)
        with sql_connection(self.path) as conn:
            conn.execute("UPDATE snapshots SET payload=? WHERE revision=1", (b'{}',))
        with self.assertRaises(SnapshotIntegrityError):
            self.store.load()
        with self.assertRaises(SnapshotIntegrityError):
            self.store.integrity_check()

    def test_bad_revision_arguments_and_out_of_range_reads(self):
        with self.assertRaises(ValueError):
            self.store.save(legacy(), expected_revision=True)
        with self.assertRaises(ValueError):
            self.store.save(legacy(), expected_revision=-1)
        with self.assertRaises(ValueError):
            self.store.history(limit=0)
        with self.assertRaises(KeyError):
            self.store.load_revision(123)


class LegacyImportTests(unittest.TestCase):
    def setUp(self):
        StorageTests.setUp(self)
        self.source = self.root / "tasks.json"
        self.backup_dir = self.root / "source-backups"
        self.source.write_text(json.dumps(legacy(), ensure_ascii=False, indent=2), encoding="utf-8")

    def test_import_is_backup_first_lossless_and_repeated_import_is_safe(self):
        raw = self.source.read_bytes()
        result = self.store.bootstrap_from_json(self.source, backup_dir=self.backup_dir)
        self.assertEqual(result.revision, 1)
        self.assertEqual(result.state, normalize_plus(legacy()))
        expected_backup = self.backup_dir / f"legacy-{sha256(raw).hexdigest()}.json"
        self.assertEqual(expected_backup.read_bytes(), raw)
        self.assertEqual(self.source.read_bytes(), raw)
        self.assertEqual(self.store.bootstrap_from_json(self.source, backup_dir=self.backup_dir).revision, 1)
        self.assertEqual(self.store.history(), [1])
        self.assertTrue(self.store.integrity_check())

    def test_import_migrates_duplicate_and_missing_legacy_checklist_ids(self):
        source = legacy()
        source["tasks"][0]["checklist"] = [
            {"text": "forgot id", "done": False},
            {"id": "existing", "text": "first", "done": True},
            {"id": "existing", "text": "second", "done": False},
        ]
        self.source.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        original = self.source.read_bytes()
        imported = self.store.bootstrap_from_json(self.source, backup_dir=self.backup_dir)
        migrated = imported.state["tasks"][0]
        self.assertEqual(migrated["checklist"], source["tasks"][0]["checklist"])
        ids = [item["id"] for item in migrated["checklists"][0]["items"]]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(imported.state, normalize_plus(imported.state))
        self.assertEqual(self.source.read_bytes(), original)

    def test_two_concurrent_importers_record_single_migration(self):
        barrier = Barrier(2)

        def importer():
            independent = SQLiteSnapshotStore(self.path)
            barrier.wait(timeout=6)
            return independent.bootstrap_from_json(self.source, backup_dir=self.backup_dir)

        with ThreadPoolExecutor(max_workers=2) as pool:
            one, two = list(pool.map(lambda _: importer(), range(2)))
        self.assertEqual(one, two)
        self.assertEqual(self.store.history(), [1])
        self.assertEqual(len(list(self.backup_dir.glob("legacy-*.json"))), 1)

    def test_second_import_returns_latest_and_never_reverts_user_edits(self):
        original = self.store.bootstrap_from_json(self.source, backup_dir=self.backup_dir)
        changed = copy.deepcopy(original.state)
        changed["tasks"][0]["title"] = "edited after migration"
        second = self.store.save(changed, expected_revision=1)
        same_import = self.store.bootstrap_from_json(self.source, backup_dir=self.backup_dir)
        self.assertEqual(same_import.state, second.state)
        self.assertEqual(self.store.history(), [2, 1])

    def test_changed_source_after_import_rejected_without_overwriting(self):
        first = self.store.bootstrap_from_json(self.source, backup_dir=self.backup_dir)
        different = legacy()
        different["tasks"][0]["title"] = "different source"
        self.source.write_text(json.dumps(different, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(MigrationConflict):
            self.store.bootstrap_from_json(self.source, backup_dir=self.backup_dir)
        self.assertEqual(self.store.load(), first)

    def test_initializing_from_json_does_not_replace_nonempty_database(self):
        original = self.store.save(legacy(), expected_revision=0)
        with self.assertRaises(StoreAlreadyInitialized):
            self.store.bootstrap_from_json(self.source, backup_dir=self.backup_dir)
        self.assertEqual(self.store.load(), original)

    def test_invalid_source_does_not_write_any_snapshot_or_backup(self):
        for invalid in (b'{"version":1,"projects":[],"tasks":"bad"}',
                        b'not json', b'{"version":NaN}', b'\xff'):
            with self.subTest(invalid=invalid):
                self.source.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    self.store.bootstrap_from_json(self.source, backup_dir=self.backup_dir)
                self.assertEqual(self.store.history(), [])
                self.assertFalse(self.backup_dir.exists())

    def test_existing_conflicting_backup_cannot_be_overwritten(self):
        raw = self.source.read_bytes()
        self.backup_dir.mkdir()
        destination = self.backup_dir / f"legacy-{sha256(raw).hexdigest()}.json"
        destination.write_bytes(b"someone else's backup")
        with self.assertRaises(MigrationConflict):
            self.store.bootstrap_from_json(self.source, backup_dir=self.backup_dir)
        self.assertEqual(destination.read_bytes(), b"someone else's backup")
        self.assertIsNone(self.store.load())

    def test_backup_creation_failure_prevents_database_import(self):
        with patch("persistent_store.os.link", side_effect=OSError("unsupported")):
            with self.assertRaisesRegex(OSError, "unsupported"):
                self.store.bootstrap_from_json(self.source, backup_dir=self.backup_dir)
        self.assertIsNone(self.store.load())

    def test_interrupted_import_rolls_back_metadata_and_snapshot(self):
        with sql_connection(self.path) as conn:
            conn.execute("CREATE TRIGGER abort_metadata BEFORE INSERT ON migrations "
                         "BEGIN SELECT RAISE(ABORT, 'simulate crash at metadata'); END")
        with self.assertRaisesRegex(sqlite3.DatabaseError, "simulate crash"):
            self.store.bootstrap_from_json(self.source, backup_dir=self.backup_dir)
        self.assertEqual(self.store.history(), [])
        self.assertIsNone(SQLiteSnapshotStore(self.path).load())
        self.assertEqual(len(list(self.backup_dir.glob("legacy-*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
