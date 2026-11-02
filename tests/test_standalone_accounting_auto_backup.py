"""Only disposable accounting SQLite trees; no live APPDATA or task databases."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from standalone_accounting import StandaloneAccountingStore
from standalone_accounting_identity import LocalCompanyIdentity
from standalone_accounting_template_store import StandaloneAccountingTemplateStore
import standalone_accounting_auto_backup as auto
import standalone_accounting_backup_manifest as manifest_module
from standalone_accounting_restore import restore_standalone_accounting, StandaloneRestoreError


ACTOR = "owner"
ACCOUNTS = {ACTOR: {"username": ACTOR, "role": "admin"}}
NOW = "2026-10-22T12:00:00Z"


class AutomaticBackupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-automatic-backups-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = StandaloneAccountingStore(
            self.root / "standalone-accounting.sqlite3")
        self.manager = auto.AutomaticStandaloneBackups(
            self.root, plaintext_acknowledged=True, max_backups=3)

    def event(self, sequence):
        current = self.store.read(actor=ACTOR, accounts=ACCOUNTS)["revision"]
        return self.store.command({
            "type": "party.register", "eventId": f"evt-{sequence}",
            "partyId": f"synthetic-{sequence}", "name": f"Person {sequence}",
            "kind": "customer",
        }, actor=ACTOR, accounts=ACCOUNTS,
            expected_revision=current, now=NOW)

    def files(self):
        if not self.manager.folder.exists():
            return []
        return sorted(p for p in self.manager.folder.glob(
            "standalone-accounting-auto-*.sqlite3"))

    def test_explicit_path_and_plaintext_permission(self):
        with self.assertRaises(ValueError):
            auto.AutomaticStandaloneBackups(Path("relative"), plaintext_acknowledged=True)
        with self.assertRaises(PermissionError):
            auto.AutomaticStandaloneBackups(self.root)
        with self.assertRaises(ValueError):
            auto.AutomaticStandaloneBackups(
                self.root, plaintext_acknowledged=True, max_backups=61)

    def test_missing_source_does_not_initialize_or_claim_success(self):
        self.store.path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.manager.backup_now()
        self.assertFalse(self.store.path.exists())
        self.assertEqual(self.files(), [])
        self.assertIsNone(self.manager.last_success)

    def test_empty_and_posted_snapshots_can_be_offline_restored(self):
        empty = self.manager.backup_now()
        self.assertEqual(auto._check_input(empty)[0], 0)
        self.event(1)
        source_view = self.store.read(actor=ACTOR, accounts=ACCOUNTS)
        filled = self.manager.backup_now()
        self.assertNotEqual(empty, filled)
        destination_dir = self.root / "offline-restore"
        destination_dir.mkdir()
        result = restore_standalone_accounting(
            filled, destination_dir / "standalone-accounting.sqlite3",
            plaintext_acknowledged=True, offline_acknowledged=True)
        self.assertEqual(StandaloneAccountingStore(result).read(
            actor=ACTOR, accounts=ACCOUNTS), source_view)
        self.assertEqual(self.store.read(actor=ACTOR, accounts=ACCOUNTS),
                         source_view)
        self.assertFalse((self.root / "finance.json").exists())
        self.assertFalse((self.root / "tasks.json").exists())

    def test_new_rial_ledger_snapshot_retains_currency_on_offline_restore(self):
        rial_root = self.root / "new-rial"
        rial_store = StandaloneAccountingStore(
            rial_root / "standalone-accounting.sqlite3", default_currency="RIAL")
        self.assertEqual(rial_store.read(actor=ACTOR, accounts=ACCOUNTS)[
            "view"]["currency"], "RIAL")
        original = rial_store.command({
            "type": "party.register", "eventId": "rial-first",
            "partyId": "rial-customer", "name": "Synthetic customer",
            "kind": "customer",
        }, actor=ACTOR, accounts=ACCOUNTS, expected_revision=0, now=NOW)
        manager = auto.AutomaticStandaloneBackups(
            rial_root, plaintext_acknowledged=True)
        backup = manager.backup_now()
        destination = self.root / "rial-restored"
        destination.mkdir()
        output = restore_standalone_accounting(
            backup, destination / "standalone-accounting.sqlite3",
            plaintext_acknowledged=True, offline_acknowledged=True)
        reread = StandaloneAccountingStore(output).read(
            actor=ACTOR, accounts=ACCOUNTS)
        self.assertEqual(reread, {"revision": original["revision"],
                                  "view": original["view"]})

    def test_rotation_keeps_three_valid_and_never_removes_unrelated_files(self):
        manual = self.manager.folder / "manual.sqlite3"
        self.manager.folder.mkdir()
        manual.write_bytes(b"hands off")
        snapshots = []
        for number in range(6):
            self.event(number)
            snapshots.append(self.manager.backup_now())
            time.sleep(0.003)
        self.assertEqual(self.files(), snapshots[-3:])
        self.assertEqual(manual.read_bytes(), b"hands off")
        self.assertEqual([auto._check_input(x)[0] for x in self.files()],
                         [4, 5, 6])

    def test_copy_failure_preserves_every_existing_snapshot(self):
        saved = [self.manager.backup_now() for _ in range(3)]
        before = [path.read_bytes() for path in saved]
        with patch.object(auto, "backup_standalone_accounting",
                          side_effect=sqlite3.DatabaseError("synthetic disk failure")):
            with self.assertRaises(sqlite3.DatabaseError):
                self.manager.backup_now()
        self.assertEqual(self.files(), saved)
        self.assertEqual([path.read_bytes() for path in saved], before)
        self.assertIsInstance(self.manager.last_error, sqlite3.DatabaseError)

    def test_production_default_retains_exactly_sixty(self):
        managed = auto.AutomaticStandaloneBackups(
            self.root, plaintext_acknowledged=True)
        created = [managed.backup_now() for _ in range(62)]
        current = sorted(self.files(), key=lambda path: path.stat().st_mtime_ns)
        self.assertEqual(len(current), 60)
        self.assertFalse(created[0].exists())
        self.assertFalse(created[1].exists())
        self.assertTrue(all(path.exists() for path in created[2:]))
        self.assertTrue(all(auto._check_input(path)[0] == 0 for path in current))

    def test_postpublication_failed_validation_removes_only_new_candidate(self):
        original = self.manager.backup_now()
        self.event(1)
        with patch.object(auto, "_check_input",
                          side_effect=RuntimeError("synthetic validation failed")):
            with self.assertRaises(RuntimeError):
                self.manager.backup_now()
        self.assertEqual(self.files(), [original])
        self.assertEqual(auto._check_input(original)[0], 0)

    def test_rotation_exception_retains_new_copy_and_previous_copy(self):
        original = self.manager.backup_now()
        self.event(1)
        with patch.object(self.manager, "_managed_files",
                          side_effect=OSError("simulated enumeration failure")):
            with self.assertRaises(OSError):
                self.manager.backup_now()
        self.assertEqual(len(self.files()), 2)
        self.assertTrue(original.exists())
        self.assertEqual(max(auto._check_input(p)[0] for p in self.files()), 1)

    def test_new_backup_corrupted_during_enumeration_cannot_retire_last_good_copy(self):
        """Synthetic corruption after publication must block destructive rotation."""
        manager = auto.AutomaticStandaloneBackups(
            self.root, plaintext_acknowledged=True, max_backups=1)
        original = manager.backup_now()
        self.event(1)
        enumerate_original = manager._managed_files

        def corrupt_new_manifest():
            candidates = enumerate_original()
            newest = next(path for path in candidates if path != original)
            newest.with_suffix('.manifest.json').write_text(
                '{"synthetic":"damaged-after-publication"}', encoding='utf-8')
            return candidates

        with patch.object(manager, '_managed_files', side_effect=corrupt_new_manifest):
            with self.assertRaises(manifest_module.BackupManifestError):
                manager.backup_now()
        self.assertTrue(original.is_file())
        self.assertIsNotNone(manifest_module.verify_completion_manifest(original))

    def test_failed_retirement_preserves_old_sqlite_and_both_companions(self):
        """A failed unlink cannot strip identities/templates from a valid old copy."""
        LocalCompanyIdentity(self.root).add_user(
            "synthetic-owner", "SyntheticPasswordForBackupTest", "admin")
        StandaloneAccountingTemplateStore(self.root).save(
            "issuer", "Synthetic issuer",
            {"format": "madar-issuer-profile-v1",
             "profile": {"legalName": "Synthetic Company"}})
        manager = auto.AutomaticStandaloneBackups(
            self.root, plaintext_acknowledged=True, max_backups=1)
        original = manager.backup_now()
        companions = [original.with_suffix(".templates.json"),
                      original.with_suffix(".users.json")]
        self.assertTrue(all(path.is_file() for path in companions))
        original_bytes = [path.read_bytes() for path in [original, *companions]]
        self.event(1)

        unlink = Path.unlink

        def deny_retired_sqlite(path, *args, **kwargs):
            if path == original:
                raise PermissionError("synthetic locked retired SQLite file")
            return unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", autospec=True,
                          side_effect=deny_retired_sqlite):
            with self.assertRaisesRegex(PermissionError, "synthetic locked"):
                manager.backup_now()

        self.assertEqual([path.read_bytes() for path in [original, *companions]],
                         original_bytes)
        self.assertEqual(len(self.files()), 2)
        self.assertEqual(auto._check_input(original)[0], 0)

    def test_simultaneous_backups_are_serialized_and_restorable(self):
        with ThreadPoolExecutor(max_workers=5) as pool:
            snapshots = list(pool.map(lambda _: self.manager.backup_now(), range(5)))
        self.assertEqual(len(set(snapshots)), 5)
        self.assertEqual(len(self.files()), 3)
        self.assertEqual([auto._check_input(x)[0] for x in self.files()],
                         [0, 0, 0])

    def test_background_scheduler_runs_and_stops_without_new_snapshots(self):
        active = auto.AutomaticStandaloneBackups(
            self.root, plaintext_acknowledged=True, interval_seconds=0.04)
        active.start()
        try:
            deadline = time.monotonic() + 4
            while len(self.files()) < 2 and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertGreaterEqual(len(self.files()), 2)
        finally:
            active.stop()
        count = len(self.files())
        time.sleep(0.13)
        self.assertEqual(len(self.files()), count)

    def test_concurrent_financial_commands_do_not_make_torn_snapshots(self):
        started = threading.Event()
        def writer():
            started.wait()
            for number in range(8):
                self.event(number)
        with ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit(writer)
            started.set()
            snapshots = [self.manager.backup_now() for _ in range(5)]
            future.result(timeout=10)
        revisions = [auto._check_input(p)[0] for p in snapshots if p.exists()]
        self.assertTrue(revisions)
        self.assertTrue(all(0 <= revision <= 8 for revision in revisions))
        self.assertEqual(self.store.read(
            actor=ACTOR, accounts=ACCOUNTS)["revision"], 8)

    def test_completion_manifest_is_last_published_and_versioned(self):
        LocalCompanyIdentity(self.root).add_user(
            "synthetic-owner", "SyntheticPasswordForBackupTest", "admin")
        StandaloneAccountingTemplateStore(self.root).save(
            "issuer", "Synthetic issuer", {"format": "madar-issuer-profile-v1",
            "profile": {"legalName": "Synthetic Company"}})
        source = self.manager.backup_now()
        manifest = source.with_suffix('.manifest.json')
        self.assertTrue(manifest.is_file())
        document = json.loads(manifest.read_text(encoding='utf-8'))
        self.assertEqual(document['version'], 1)
        self.assertEqual(set(document['files']), {'sqlite', 'users', 'templates'})
        target = self.root / 'verified-restore'
        target.mkdir()
        restored = restore_standalone_accounting(source, target / 'standalone-accounting.sqlite3',
                                                 plaintext_acknowledged=True, offline_acknowledged=True)
        self.assertTrue(restored.is_file())
        self.assertTrue((target / 'local-users.json').is_file())
        self.assertTrue((target / 'invoice-templates.json').is_file())

    def test_missing_declared_identity_companion_refuses_partial_transfer(self):
        LocalCompanyIdentity(self.root).add_user(
            "synthetic-owner", "SyntheticPasswordForBackupTest", "admin")
        source = self.manager.backup_now()
        source.with_suffix('.users.json').unlink()
        target = self.root / 'partial-restore'
        target.mkdir()
        with self.assertRaises(StandaloneRestoreError):
            restore_standalone_accounting(source, target / 'standalone-accounting.sqlite3',
                                          plaintext_acknowledged=True, offline_acknowledged=True)
        self.assertEqual(list(target.iterdir()), [])

    def test_missing_template_or_changed_companion_refuses_partial_transfer(self):
        StandaloneAccountingTemplateStore(self.root).save(
            "issuer", "Synthetic issuer", {"format": "madar-issuer-profile-v1",
            "profile": {"legalName": "Synthetic Company"}})
        source = self.manager.backup_now()
        companion = source.with_suffix('.templates.json')
        original = companion.read_bytes()
        destination = self.root / 'missing-template-restore'
        destination.mkdir()
        companion.unlink()
        with self.assertRaises(StandaloneRestoreError):
            restore_standalone_accounting(source, destination / 'standalone-accounting.sqlite3',
                                          plaintext_acknowledged=True, offline_acknowledged=True)
        self.assertEqual(list(destination.iterdir()), [])
        companion.write_bytes(original + b' ')
        with self.assertRaises(StandaloneRestoreError):
            restore_standalone_accounting(source, destination / 'standalone-accounting.sqlite3',
                                          plaintext_acknowledged=True, offline_acknowledged=True)

    def test_unpublished_or_unknown_manifest_refuses_automatic_restore(self):
        source = self.manager.backup_now()
        manifest = source.with_suffix('.manifest.json')
        destination = self.root / 'unpublished-restore'
        destination.mkdir()
        manifest.unlink()
        with self.assertRaises(StandaloneRestoreError):
            restore_standalone_accounting(source, destination / 'standalone-accounting.sqlite3',
                                          plaintext_acknowledged=True, offline_acknowledged=True)
        manifest.write_text('{"version":999}', encoding='utf-8')
        with self.assertRaises(StandaloneRestoreError):
            restore_standalone_accounting(source, destination / 'standalone-accounting.sqlite3',
                                          plaintext_acknowledged=True, offline_acknowledged=True)
        self.assertEqual(list(destination.iterdir()), [])

    def test_manifest_publication_interruption_retains_previous_complete_copy(self):
        LocalCompanyIdentity(self.root).add_user(
            'synthetic-owner', 'SyntheticPasswordForBackupTest', 'admin')
        original = self.manager.backup_now()
        original_names = [original, original.with_suffix('.users.json'),
                          original.with_suffix('.manifest.json')]
        original_bytes = [p.read_bytes() for p in original_names]
        link = manifest_module.os.link

        def fail_only_final_marker(source, destination, *args, **kwargs):
            if str(destination).endswith('.manifest.json'):
                raise OSError('synthetic interruption before final completion')
            return link(source, destination, *args, **kwargs)

        with patch.object(manifest_module.os, 'link', side_effect=fail_only_final_marker):
            with self.assertRaisesRegex(OSError, 'synthetic interruption'):
                self.manager.backup_now()
        self.assertEqual(self.files(), [original])
        self.assertEqual([p.read_bytes() for p in original_names], original_bytes)
        self.assertFalse(list(self.manager.folder.glob('*.tmp')))

    def test_undeclared_companion_rejected_even_when_sqlite_is_valid(self):
        source = self.manager.backup_now()
        source.with_suffix('.users.json').write_bytes(b'{}')
        destination = self.root / 'undeclared-restore'
        destination.mkdir()
        with self.assertRaises(StandaloneRestoreError):
            restore_standalone_accounting(source, destination / 'standalone-accounting.sqlite3',
                                          plaintext_acknowledged=True, offline_acknowledged=True)
        self.assertEqual(list(destination.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
