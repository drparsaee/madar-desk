"""Synthetic/manual offline standalone backup tests, never use APPDATA or live DBs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import standalone_accounting_backup as backup
from standalone_accounting import (
    StandaloneAccountingStore, AccountingIntegrityError,
)


ACCOUNTS = {"root": {"username": "root", "role": "admin"}}
NOW = "2026-10-22T14:22:00Z"


class StandaloneAccountingBackupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-manual-backup-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "standalone-accounting.sqlite3"
        self.destination = self.root / "manual-backup.sqlite3"

    def create_source(self):
        return StandaloneAccountingStore(self.source)

    def command(self, store, event_id, party_id=None):
        party_id = party_id or event_id
        revision = store.read(actor="root", accounts=ACCOUNTS)["revision"]
        return store.command({
            "type": "party.register", "eventId": event_id,
            "partyId": party_id, "name": "Synthetic " + party_id,
            "kind": "customer"
        }, actor="root", accounts=ACCOUNTS,
            expected_revision=revision, now=NOW)

    def backup(self, *, source=None, destination=None, acknowledged=True):
        return backup.backup_standalone_accounting(
            self.source if source is None else source,
            self.destination if destination is None else destination,
            plaintext_acknowledged=acknowledged)

    def assert_no_partial(self):
        self.assertFalse(list(self.root.glob(".*.partial-*")),
                         "Temporary backup files or SQLite sidecars leaked")

    def read_source(self):
        return StandaloneAccountingStore(self.source).read(
            actor="root", accounts=ACCOUNTS)

    def test_existing_empty_source_preserved_and_revision_zero_backup(self):
        self.create_source()
        expected = self.read_source()
        self.assertEqual(expected["revision"], 0)
        self.assertEqual(self.backup(), self.destination)
        self.assertTrue(self.destination.is_file())
        self.assertEqual(StandaloneAccountingStore(self.destination).read(
            actor="root", accounts=ACCOUNTS), expected)
        self.assertEqual(self.read_source(), expected)
        self.assert_no_partial()

    def test_full_posted_history_copied_and_replayed_without_loss(self):
        store = self.create_source()
        self.command(store, "ev-1")
        self.command(store, "ev-2")
        expected = self.read_source()
        self.assertEqual(expected["revision"], 2)
        self.backup()
        self.assertEqual(StandaloneAccountingStore(self.destination).read(
            actor="root", accounts=ACCOUNTS), expected)
        self.assertEqual(self.read_source(), expected)
        self.assert_no_partial()

    def test_source_missing_refuses_without_initializing_sqlite(self):
        with self.assertRaises(FileNotFoundError):
            self.backup()
        self.assertFalse(self.source.exists())
        self.assertFalse(self.destination.exists())
        self.assert_no_partial()

    def test_required_acknowledgement_is_literal_bool_true(self):
        self.create_source()
        for value in (False, None, 1, "yes", {}, 0):
            with self.subTest(value=value), self.assertRaises(PermissionError):
                self.backup(acknowledged=value)
        self.assertFalse(self.destination.exists())
        self.assert_no_partial()

    def test_source_and_destination_must_be_absolute_path_objects(self):
        self.create_source()
        for invalid in ("file.sqlite3", Path("relative.sqlite3"), 5):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                self.backup(destination=invalid)
        with self.assertRaises(ValueError):
            backup.backup_standalone_accounting(
                self.source, None, plaintext_acknowledged=True)
        with self.assertRaises(ValueError):
            self.backup(source=Path("standalone-accounting.sqlite3"))
        self.assertFalse(self.destination.exists())

    def test_cannot_copy_task_unified_or_other_named_databases(self):
        for name in ("madar-unified.sqlite3", "tasks.sqlite3",
                     "finance.sqlite3", "original-backup.sqlite3"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.backup(source=self.root / name)
        self.assertFalse(self.destination.exists())

    def test_same_path_refused_without_deleting_original(self):
        self.create_source()
        with self.assertRaises(ValueError):
            self.backup(destination=self.source)
        self.assertEqual(self.read_source()["revision"], 0)
        self.assert_no_partial()

    def test_existing_target_never_overwritten_or_removed(self):
        self.create_source()
        contents = b"external document, must stay unchanged"
        self.destination.write_bytes(contents)
        with self.assertRaises(FileExistsError):
            self.backup()
        self.assertEqual(self.destination.read_bytes(), contents)
        self.assert_no_partial()

    def test_existing_hard_link_alias_is_refused_without_modification(self):
        self.create_source()
        os.link(self.source, self.destination)
        with self.assertRaises((ValueError, FileExistsError)):
            self.backup()
        self.assertEqual(self.read_source()["revision"], 0)
        self.assert_no_partial()

    def test_source_symlink_rejected(self):
        target = self.root / "actual-source.sqlite3"
        target_store = StandaloneAccountingStore(target)
        self.assertEqual(target_store.read(actor="root", accounts=ACCOUNTS)["revision"], 0)
        try:
            self.source.symlink_to(target)
        except (NotImplementedError, OSError) as exc:
            self.skipTest("Windows symlink privilege unavailable: " + str(exc))
        with self.assertRaises(ValueError):
            self.backup()
        self.assertFalse(self.destination.exists())

    def test_destination_symlink_or_dangling_symlink_rejected(self):
        self.create_source()
        for target in (self.root / "absent.db", self.source):
            try:
                self.destination.symlink_to(target)
            except (NotImplementedError, OSError) as exc:
                self.skipTest("Windows symlink privilege unavailable: " + str(exc))
            try:
                with self.assertRaises(ValueError):
                    self.backup()
            finally:
                self.destination.unlink()
        self.assert_no_partial()

    def test_destination_parent_symlink_rejected(self):
        self.create_source()
        directory = self.root / "real-dest"
        directory.mkdir()
        alias = self.root / "alias-dest"
        try:
            alias.symlink_to(directory, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            self.skipTest("Windows symlink privilege unavailable: " + str(exc))
        with self.assertRaises(ValueError):
            self.backup(destination=alias / "backup.sqlite3")
        self.assertFalse((directory / "backup.sqlite3").exists())

    def test_destination_parent_must_exist_and_is_not_auto_created(self):
        self.create_source()
        missing = self.root / "uncreated" / "backup.sqlite3"
        with self.assertRaises(FileNotFoundError):
            self.backup(destination=missing)
        self.assertFalse(missing.parent.exists())

    def test_foreign_database_same_filename_refused_even_with_sqlite_integrity(self):
        with closing(sqlite3.connect(str(self.source))) as db:
            db.execute("CREATE TABLE tasks(id INTEGER, body TEXT)")
            db.execute("PRAGMA user_version=1")
            db.commit()
        with self.assertRaises(backup.StandaloneBackupError):
            self.backup()
        self.assertFalse(self.destination.exists())
        self.assert_no_partial()

    def test_wrong_schema_version_refused(self):
        self.create_source()
        with closing(sqlite3.connect(str(self.source))) as db:
            db.execute("PRAGMA user_version=7")
            db.commit()
        with self.assertRaises(backup.StandaloneBackupError):
            self.backup()
        self.assertFalse(self.destination.exists())
        self.assert_no_partial()

    def test_unexpected_schema_view_is_refused_not_silently_copied(self):
        self.create_source()
        with closing(sqlite3.connect(str(self.source))) as db:
            db.execute("CREATE VIEW stolen AS SELECT * FROM standalone_accounting")
            db.commit()
        with self.assertRaises(backup.StandaloneBackupError):
            self.backup()
        self.assertFalse(self.destination.exists())
        self.assert_no_partial()

    def test_checksum_corruption_refused_and_source_preserved(self):
        store = self.create_source()
        self.command(store, "good-event")
        with closing(sqlite3.connect(str(self.source))) as db:
            db.execute("UPDATE standalone_accounting SET digest=?", ("0" * 64,))
            db.commit()
        with self.assertRaises(AccountingIntegrityError):
            self.backup()
        with closing(sqlite3.connect(str(self.source))) as db:
            digest = db.execute(
                "SELECT digest FROM standalone_accounting").fetchone()[0]
        self.assertEqual(digest, "0" * 64)
        self.assertFalse(self.destination.exists())
        self.assert_no_partial()

    def test_rehashed_corrupt_event_replay_refused(self):
        store = self.create_source()
        self.command(store, "first")
        with closing(sqlite3.connect(str(self.source))) as db:
            original = json.loads(db.execute(
                "SELECT state FROM standalone_accounting").fetchone()[0])
            original["events"][0]["result"] = {"tampered": True}
            raw = json.dumps(original, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf8")
            db.execute("UPDATE standalone_accounting SET state=?, digest=?",
                       (raw, sha256(raw).hexdigest()))
            db.commit()
        with self.assertRaises(AccountingIntegrityError):
            self.backup()
        self.assertFalse(self.destination.exists())
        self.assert_no_partial()

    def test_backup_copy_failure_cleans_partial_and_does_not_publish(self):
        self.create_source()
        def interrupt(source, temp):
            temp.write_bytes(b"partial\n")
            raise OSError("Injected copy failure")
        with patch.object(backup, "_sqlite_backup", side_effect=interrupt):
            with self.assertRaisesRegex(OSError, "Injected copy failure"):
                self.backup()
        self.assertFalse(self.destination.exists())
        self.assert_no_partial()

    def test_validation_failure_cleans_all_partial_files(self):
        self.create_source()
        with patch.object(backup, "_validate_backup",
                          side_effect=backup.StandaloneBackupError("bad replay")):
            with self.assertRaisesRegex(backup.StandaloneBackupError, "bad replay"):
                self.backup()
        self.assertFalse(self.destination.exists())
        self.assert_no_partial()

    def test_fsync_failure_never_publishes_file(self):
        self.create_source()
        with patch.object(backup, "_sync_file", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.backup()
        self.assertFalse(self.destination.exists())
        self.assert_no_partial()

    def test_no_overwrite_race_between_check_and_publish(self):
        self.create_source()
        original_link = backup.os.link
        sentinel = b"racer-created-target"
        def racer(source, target):
            Path(target).write_bytes(sentinel)
            return original_link(source, target)
        with patch.object(backup.os, "link", side_effect=racer):
            with self.assertRaises(FileExistsError):
                self.backup()
        self.assertEqual(self.destination.read_bytes(), sentinel)
        self.assert_no_partial()

    def test_directory_sync_failure_revokes_own_new_publication(self):
        self.create_source()
        with patch.object(backup, "_sync_directory",
                          side_effect=OSError("simulated directory sync failure")):
            with self.assertRaisesRegex(OSError, "simulated directory sync failure"):
                self.backup()
        self.assertFalse(self.destination.exists(),
                         "Failed backup must not leave a newly published file")
        self.assertEqual(self.read_source()["revision"], 0)
        self.assert_no_partial()

    def test_directory_sync_failure_preserves_racing_replacement(self):
        self.create_source()
        sentinel = b"unrelated replacement after publication; preserve"

        def replace_then_fail(_parent):
            # Another process replaces our published name before sync fails.
            self.destination.unlink()
            self.destination.write_bytes(sentinel)
            raise OSError("simulated directory sync after replacement")

        with patch.object(backup, "_sync_directory", side_effect=replace_then_fail):
            with self.assertRaisesRegex(OSError, "simulated directory sync"):
                self.backup()
        self.assertEqual(self.destination.read_bytes(), sentinel)
        self.assert_no_partial()

    def test_existing_source_unmodified_after_backup(self):
        store = self.create_source()
        self.command(store, "event-1")
        source_before = self.read_source()
        self.backup()
        self.assertEqual(self.read_source(), source_before)
        self.assertFalse((self.root / "madar-unified.sqlite3").exists())
        self.assertFalse((self.root / "tasks.json").exists())
        self.assertFalse((self.root / "finance.json").exists())

    def test_concurrent_source_writers_produce_integral_snapshot(self):
        store = self.create_source()
        self.command(store, "initial")
        start_writers = threading.Event()
        done = threading.Event()
        errors = []
        def writer():
            start_writers.wait(5)
            try:
                for index in range(1, 17):
                    self.command(store, "event-" + str(index))
            except Exception as exc:
                errors.append(exc)
            finally:
                done.set()
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(writer)
            start_writers.set()
            published = self.backup()
            done.wait(10)
            future.result(timeout=10)
        self.assertFalse(errors, errors)
        snap = StandaloneAccountingStore(published).read(
            actor="root", accounts=ACCOUNTS)
        live = self.read_source()
        self.assertGreaterEqual(snap["revision"], 1)
        self.assertLessEqual(snap["revision"], live["revision"])
        self.assertEqual(snap["revision"], len(snap["view"]["parties"]))
        self.assertEqual(live["revision"], 17)
        self.assertEqual(snap["view"]["currency"], "TOMAN")
        self.assert_no_partial()

    def test_two_backup_requests_same_target_one_succeeds(self):
        self.create_source()
        def attempt(_):
            try:
                self.backup()
                return "ok"
            except FileExistsError:
                return "exists"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (1, 2)))
        self.assertEqual(sorted(results), ["exists", "ok"])
        self.assertTrue(self.destination.is_file())
        self.assert_no_partial()

    def test_cli_requires_all_args_and_acknowledgement(self):
        self.create_source()
        script = [sys.executable, "-B", "-m", "standalone_accounting_backup",
                  "--source", str(self.source),
                  "--destination", str(self.destination)]
        without_ack = subprocess.run(script, cwd=self.root,
                                     capture_output=True, text=True, timeout=12,
                                     env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
        self.assertEqual(without_ack.returncode, 1)
        self.assertIn("acknowledgement", without_ack.stderr)
        self.assertFalse(self.destination.exists())
        success = subprocess.run(
            script + ["--acknowledge-plaintext"], cwd=self.root,
            capture_output=True, text=True, timeout=12,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertTrue(self.destination.exists())
        self.assert_no_partial()

    def test_cli_never_overwrites_existing_target(self):
        self.create_source()
        self.destination.write_bytes(b"owned")
        result = backup.main(["--source", str(self.source),
                              "--destination", str(self.destination),
                              "--acknowledge-plaintext"])
        self.assertEqual(result, 1)
        self.assertEqual(self.destination.read_bytes(), b"owned")

    def test_cli_reports_corrupt_rehashed_source_without_traceback(self):
        store = self.create_source()
        self.command(store, "original")
        with closing(sqlite3.connect(str(self.source))) as db:
            state = json.loads(db.execute(
                "SELECT state FROM standalone_accounting").fetchone()[0])
            state["events"][0]["result"] = {"invalid": "forged"}
            raw = json.dumps(state, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf8")
            db.execute("UPDATE standalone_accounting SET state=?,digest=?",
                       (raw, sha256(raw).hexdigest()))
            db.commit()
        import io
        from contextlib import redirect_stderr
        message = io.StringIO()
        with redirect_stderr(message):
            code = backup.main(["--source", str(self.source),
                                "--destination", str(self.destination),
                                "--acknowledge-plaintext"])
        self.assertEqual(code, 1)
        self.assertIn("Backup refused:", message.getvalue())
        self.assertFalse(self.destination.exists())
        self.assert_no_partial()


if __name__ == "__main__":
    unittest.main()
