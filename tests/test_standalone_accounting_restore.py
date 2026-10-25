"""All restore tests are synthetic; paths are private TemporaryDirectory only."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stderr
from hashlib import sha256
import io
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

import standalone_accounting_restore as restore
from standalone_accounting_backup import backup_standalone_accounting
from standalone_accounting import StandaloneAccountingStore, AccountingIntegrityError


ACTOR = "root"
USERS = {ACTOR: {"username": ACTOR, "role": "admin"}}
NOW = "2026-10-22T14:00:00Z"


class StandaloneRestoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-restore-synthetic-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.original = self.root / "original" / "standalone-accounting.sqlite3"
        self.original.parent.mkdir()
        self.backup = self.root / "backups" / "accounting-20261022.sqlite3"
        self.backup.parent.mkdir()
        self.target = self.root / "restore-target" / "standalone-accounting.sqlite3"
        self.target.parent.mkdir()
        self.original_store = StandaloneAccountingStore(self.original)

    def issue(self, *, event_id="party-1", party_id=None):
        head = self.original_store.read(actor=ACTOR, accounts=USERS)
        return self.original_store.command(
            {"type": "party.register", "eventId": event_id,
             "partyId": party_id or event_id, "name": "Synthetic",
             "kind": "customer"},
            actor=ACTOR, accounts=USERS,
            expected_revision=head["revision"], now=NOW)

    def snapshot_backup(self):
        return backup_standalone_accounting(
            self.original, self.backup, plaintext_acknowledged=True)

    def restore(self, *, source=None, destination=None, plaintext=True, offline=True):
        return restore.restore_standalone_accounting(
            self.backup if source is None else source,
            self.target if destination is None else destination,
            plaintext_acknowledged=plaintext, offline_acknowledged=offline)

    def assert_clean(self):
        self.assertFalse(list(self.target.parent.glob(".*.restore-*")),
                         "Partial restore or SQLite temporary sidecars leaked")

    def expected_view(self):
        return self.original_store.read(actor=ACTOR, accounts=USERS)

    def test_backup_restore_read_exact_equivalence_two_events(self):
        self.issue(event_id="c1")
        self.issue(event_id="c2")
        expected = self.expected_view()
        self.snapshot_backup()
        self.assertEqual(self.restore(), self.target)
        self.assertTrue(self.target.is_file())
        actual = StandaloneAccountingStore(self.target).read(
            actor=ACTOR, accounts=USERS)
        self.assertEqual(actual, expected)
        self.assertEqual(actual["revision"], 2)
        self.assertEqual(actual["view"]["currency"], "TOMAN")
        self.assertEqual(self.expected_view(), expected)
        self.assert_clean()
        for filename in ("tasks.json", "finance.json", "madar-unified.sqlite3"):
            self.assertFalse((self.target.parent / filename).exists())

    def test_valid_empty_history_restores_revision_zero(self):
        self.snapshot_backup()
        self.restore()
        result = StandaloneAccountingStore(self.target).read(
            actor=ACTOR, accounts=USERS)
        self.assertEqual(result["revision"], 0)
        self.assertEqual(result["view"]["parties"], {})
        self.assert_clean()

    def test_post_restore_store_can_append_under_its_own_cas(self):
        self.snapshot_backup()
        self.restore()
        reopened = StandaloneAccountingStore(self.target)
        committed = reopened.command(
            {"type": "party.register", "eventId": "new-offline",
             "partyId": "p-after-restore", "name": "Synthetic New",
             "kind": "customer"}, actor=ACTOR, accounts=USERS,
            expected_revision=0, now=NOW)
        self.assertEqual(committed["revision"], 1)
        self.assertEqual(self.original_store.read(
            actor=ACTOR, accounts=USERS)["revision"], 0)

    def test_plaintext_and_offline_flags_must_be_literal_true(self):
        for invalid in (False, None, "yes", 1, [], {}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(PermissionError):
                    self.restore(plaintext=invalid)
                with self.assertRaises(PermissionError):
                    self.restore(offline=invalid)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.backup.exists())
        self.assert_clean()

    def test_missing_source_does_not_silently_initialize(self):
        with self.assertRaises(FileNotFoundError):
            self.restore()
        self.assertFalse(self.backup.exists())
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_destination_parent_must_exist_no_silent_appdata_creation(self):
        self.snapshot_backup()
        new_path = self.root / "not-created" / "standalone-accounting.sqlite3"
        with self.assertRaises(FileNotFoundError):
            self.restore(destination=new_path)
        self.assertFalse(new_path.parent.exists())
        self.assert_clean()

    def test_absolute_paths_required_and_no_implicit_env_appdata(self):
        self.snapshot_backup()
        for value in ("relative.sqlite3", Path("relative.sqlite3"), 55, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                restore.restore_standalone_accounting(
                    self.backup, value, plaintext_acknowledged=True,
                    offline_acknowledged=True)
        with self.assertRaises(ValueError):
            self.restore(source=Path("my-backup.sqlite3"))
        self.assertFalse(self.target.exists())

    def test_destination_must_be_exact_standalone_database_filename(self):
        self.snapshot_backup()
        for name in ("madar-unified.sqlite3", "tasks.sqlite3",
                     "finance.json", "backup.sqlite3", "standalone-accounting.db"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.restore(destination=self.target.with_name(name))
            self.assertFalse(self.target.with_name(name).exists())
        self.assert_clean()

    def test_no_overwrite_existing_real_database_target(self):
        self.snapshot_backup()
        untouched = StandaloneAccountingStore(self.target)
        original_result = untouched.read(actor=ACTOR, accounts=USERS)
        with self.assertRaises(FileExistsError):
            self.restore()
        self.assertEqual(untouched.read(actor=ACTOR, accounts=USERS),
                         original_result)
        self.assert_clean()

    def test_existing_target_arbitrary_file_never_deleted(self):
        self.snapshot_backup()
        contents = b"NOT A DATABASE; MUST NEVER DELETE"
        self.target.write_bytes(contents)
        with self.assertRaises(FileExistsError):
            self.restore()
        self.assertEqual(self.target.read_bytes(), contents)
        self.assert_clean()

    def test_same_source_and_destination_rejected(self):
        # Both names are the database filename, but must not refer to one inode.
        self.snapshot_backup()
        same = self.root / "backups" / "standalone-accounting.sqlite3"
        os.link(self.backup, same)
        with self.assertRaises((ValueError, FileExistsError)):
            self.restore(source=same, destination=same)
        self.assertTrue(same.is_file())

    def test_hard_link_alias_for_destination_rejected(self):
        self.snapshot_backup()
        os.link(self.backup, self.target)
        with self.assertRaises(ValueError):
            self.restore()
        self.assertEqual(self.backup.read_bytes(), self.target.read_bytes())
        self.assert_clean()

    def test_source_symlink_rejected(self):
        self.snapshot_backup()
        alias = self.root / "backup-alias.sqlite3"
        try:
            alias.symlink_to(self.backup)
        except (NotImplementedError, OSError) as exc:
            self.skipTest("No symlink privilege: " + str(exc))
        with self.assertRaises(ValueError):
            self.restore(source=alias)
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_destination_symlink_dangling_rejected(self):
        self.snapshot_backup()
        try:
            self.target.symlink_to(self.root / "missing.sqlite3")
        except (NotImplementedError, OSError) as exc:
            self.skipTest("No symlink privilege: " + str(exc))
        with self.assertRaises(ValueError):
            self.restore()
        self.assertTrue(self.target.is_symlink())
        self.assert_clean()

    def test_destination_parent_symlink_rejected(self):
        self.snapshot_backup()
        alias = self.root / "parent-alias"
        try:
            alias.symlink_to(self.target.parent, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            self.skipTest("No symlink privilege: " + str(exc))
        with self.assertRaises(ValueError):
            self.restore(destination=alias / self.target.name)
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_destination_sidecars_prohibit_restore(self):
        self.snapshot_backup()
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(self.target) + suffix)
            sidecar.write_bytes(b"stale sidecar; preserve it")
            try:
                with self.subTest(suffix=suffix), self.assertRaises(
                        restore.StandaloneRestoreError):
                    self.restore()
                self.assertEqual(sidecar.read_bytes(),
                                 b"stale sidecar; preserve it")
                self.assertFalse(self.target.exists())
            finally:
                sidecar.unlink()
        self.assert_clean()

    def test_source_backup_with_sidecars_rejected(self):
        self.snapshot_backup()
        sidecar = Path(str(self.backup) + "-wal")
        sidecar.write_bytes(b"not an offline one-file backup")
        with self.assertRaises(restore.StandaloneRestoreError):
            self.restore()
        self.assertEqual(sidecar.read_bytes(), b"not an offline one-file backup")
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_foreign_task_database_refused_even_if_renamed_to_sqlite_backup(self):
        with closing(sqlite3.connect(str(self.backup))) as conn:
            conn.execute("CREATE TABLE tasks(task_id TEXT, body TEXT)")
            conn.execute("PRAGMA user_version=1")
        with self.assertRaises(restore.StandaloneBackupError):
            self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_foreign_table_alongside_standalone_table_refused(self):
        self.snapshot_backup()
        with closing(sqlite3.connect(str(self.backup))) as conn:
            conn.execute("CREATE TABLE finance_legacy_private(id INTEGER)")
        with self.assertRaises(restore.StandaloneBackupError):
            self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_wrong_schema_version_rejected_without_destination(self):
        self.snapshot_backup()
        with closing(sqlite3.connect(str(self.backup))) as conn:
            conn.execute("PRAGMA user_version=777")
        with self.assertRaises(restore.StandaloneBackupError):
            self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_garbage_sqlite_header_rejected(self):
        self.backup.write_bytes(b"not a SQLite database")
        with self.assertRaises(sqlite3.DatabaseError):
            self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_digest_tampering_refused(self):
        self.issue()
        self.snapshot_backup()
        with closing(sqlite3.connect(str(self.backup))) as conn:
            conn.execute("UPDATE standalone_accounting SET digest=?", ("0" * 64,))
            conn.commit()
        with self.assertRaises(AccountingIntegrityError):
            self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_rehashed_semantic_forgery_refused(self):
        self.issue()
        self.snapshot_backup()
        with closing(sqlite3.connect(str(self.backup))) as conn:
            raw = conn.execute("SELECT state FROM standalone_accounting").fetchone()[0]
            parsed = json.loads(raw)
            parsed["events"][0]["result"] = {"approved": "FORGED"}
            forged = json.dumps(parsed, sort_keys=True, ensure_ascii=False,
                                separators=(",", ":"), allow_nan=False).encode()
            conn.execute("UPDATE standalone_accounting SET state=?, digest=?",
                         (forged, sha256(forged).hexdigest()))
            conn.commit()
        with self.assertRaises(AccountingIntegrityError):
            self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_copy_failure_leaves_no_target_or_plaintext_temp(self):
        self.snapshot_backup()
        def fail(source, path):
            path.write_bytes(b"partial data")
            raise OSError("simulated disk failure")
        with patch.object(restore, "_sqlite_backup", side_effect=fail):
            with self.assertRaisesRegex(OSError, "simulated disk failure"):
                self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_postcopy_validation_failure_leaves_no_target(self):
        self.snapshot_backup()
        with patch.object(restore, "_validate_backup",
                          side_effect=restore.StandaloneRestoreError("invalid replay")):
            with self.assertRaisesRegex(restore.StandaloneRestoreError,
                                        "invalid replay"):
                self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_fsync_error_refuses_publish_and_cleans(self):
        self.snapshot_backup()
        with patch.object(restore, "_sync_file", side_effect=OSError("no space left")):
            with self.assertRaisesRegex(OSError, "no space left"):
                self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_different_revision_between_input_and_temp_fails_closed(self):
        self.issue()
        self.snapshot_backup()
        with patch.object(restore, "_validate_backup", return_value=100):
            with self.assertRaisesRegex(restore.StandaloneRestoreError,
                                        "head changed"):
                self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_valid_but_different_snapshot_same_revision_refused(self):
        self.issue(event_id="real-1", party_id="client-A")
        self.snapshot_backup()
        other = self.root / "other" / "standalone-accounting.sqlite3"
        other.parent.mkdir()
        alternative = StandaloneAccountingStore(other)
        result = alternative.command(
            {"type": "party.register", "eventId": "real-1",
             "partyId": "client-B", "name": "Other party",
             "kind": "customer"}, actor=ACTOR, accounts=USERS,
            expected_revision=0, now=NOW)
        self.assertEqual(result["revision"], 1)
        original = restore._sqlite_backup
        def switch_content(_source, destination):
            return original(other, destination)
        with patch.object(restore, "_sqlite_backup", side_effect=switch_content):
            with self.assertRaisesRegex(restore.StandaloneRestoreError,
                                        "head changed"):
                self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_publish_no_clobber_race_preserves_other_file(self):
        self.snapshot_backup()
        original_link = os.link
        content = b"created by other process"
        def racing_link(src, dst):
            Path(dst).write_bytes(content)
            return original_link(src, dst)
        with patch.object(restore.os, "link", side_effect=racing_link):
            with self.assertRaises(FileExistsError):
                self.restore()
        self.assertEqual(self.target.read_bytes(), content)
        self.assert_clean()

    def test_concurrent_restore_same_target_exactly_one_succeeds(self):
        self.snapshot_backup()
        def call(_):
            try:
                self.restore()
                return "created"
            except FileExistsError:
                return "exists"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(call, (1, 2)))
        self.assertEqual(sorted(results), ["created", "exists"])
        self.assertEqual(StandaloneAccountingStore(self.target).read(
            actor=ACTOR, accounts=USERS)["revision"], 0)
        self.assert_clean()

    def test_offline_backup_source_unexpected_mutation_during_operation_denied(self):
        self.issue()
        self.snapshot_backup()
        original = restore._sqlite_backup
        # Simulate an inconsistent copy becoming a different (valid) revision.
        def different_snapshot(source, destination):
            original(source, destination)
            with closing(sqlite3.connect(str(destination))) as conn:
                conn.execute("DELETE FROM standalone_accounting")
                conn.commit()
        with patch.object(restore, "_sqlite_backup",
                          side_effect=different_snapshot):
            with self.assertRaisesRegex(restore.StandaloneRestoreError,
                                        "head changed"):
                self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_directory_sync_error_rolls_back_own_new_publication(self):
        self.snapshot_backup()
        with patch.object(restore, "_sync_directory",
                          side_effect=OSError("mock sync failure")):
            with self.assertRaisesRegex(OSError, "mock sync failure"):
                self.restore()
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_after_publish_racing_replacement_never_deleted_on_error(self):
        self.snapshot_backup()
        other_content = b"racing operator file; DO NOT REMOVE"
        def replacement_then_error(_parent):
            # Simulate another process unlinking and replacing the newly
            # published file before the final directory-sync step returns.
            self.target.unlink()
            self.target.write_bytes(other_content)
            raise OSError("sync interrupted after foreign replacement")
        with patch.object(restore, "_sync_directory",
                          side_effect=replacement_then_error):
            with self.assertRaisesRegex(OSError, "sync interrupted"):
                self.restore()
        self.assertEqual(self.target.read_bytes(), other_content)
        self.assert_clean()

    def test_cli_requires_flags_and_paths(self):
        self.snapshot_backup()
        cli = [sys.executable, "-B", "-m", "standalone_accounting_restore",
               "--source", str(self.backup),
               "--destination", str(self.target)]
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        for flags in ([], ["--offline"], ["--acknowledge-plaintext"]):
            with self.subTest(flags=flags):
                response = subprocess.run(cli + flags, capture_output=True,
                                          text=True, timeout=15, cwd=self.root,
                                          env=env)
                self.assertEqual(response.returncode, 1)
                self.assertIn("Offline restore refused", response.stderr)
                self.assertFalse(self.target.exists())
        success = subprocess.run(
            cli + ["--acknowledge-plaintext", "--offline"],
            capture_output=True, text=True, timeout=15, cwd=self.root, env=env)
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertIn("restore created", success.stdout)
        self.assertTrue(self.target.exists())
        self.assert_clean()

    def test_cli_existing_target_is_nonzero_without_traceback(self):
        self.snapshot_backup()
        self.target.write_bytes(b"keep")
        message = io.StringIO()
        with redirect_stderr(message):
            result = restore.main([
                "--source", str(self.backup), "--destination", str(self.target),
                "--acknowledge-plaintext", "--offline"])
        self.assertEqual(result, 1)
        self.assertIn("Offline restore refused", message.getvalue())
        self.assertEqual(self.target.read_bytes(), b"keep")

    def test_cli_corrupt_backup_nonzero_no_traceback(self):
        self.backup.write_bytes(b"garbage")
        message = io.StringIO()
        with redirect_stderr(message):
            result = restore.main([
                "--source", str(self.backup), "--destination", str(self.target),
                "--acknowledge-plaintext", "--offline"])
        self.assertEqual(result, 1)
        self.assertIn("Offline restore refused", message.getvalue())
        self.assertNotIn("Traceback", message.getvalue())
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
