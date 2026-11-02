"""Kill and retry explicit accounting restores with disposable synthetic data."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from standalone_accounting import StandaloneAccountingStore
from standalone_accounting_auto_backup import AutomaticStandaloneBackups
from standalone_accounting_backup import backup_standalone_accounting
from standalone_accounting_identity import LocalCompanyIdentity
from standalone_accounting_restore import restore_standalone_accounting
from standalone_accounting_template_store import StandaloneAccountingTemplateStore
import standalone_accounting_restore as restore_module


_KILL_AT_LINK = r'''
import os
from pathlib import Path
import sys
import standalone_accounting_restore as restore

backup, destination, stop_name, phase = sys.argv[1:]
original_link = restore.os.link
def interrupt(source, target, *args, **kwargs):
    if Path(target).name == stop_name and phase == 'before':
        os._exit(72)
    result = original_link(source, target, *args, **kwargs)
    if Path(target).name == stop_name and phase == 'after':
        os._exit(71)
    return result
restore.os.link = interrupt
restore.restore_standalone_accounting(
    Path(backup), Path(destination),
    plaintext_acknowledged=True, offline_acknowledged=True)
'''


class RestoreCrashPublicationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="madar-synthetic-crash-restore-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.original = self.root / "original"
        self.original.mkdir()
        self.destination_root = self.root / "destination"
        self.destination_root.mkdir()
        self.destination = self.destination_root / "standalone-accounting.sqlite3"
        self.original_db = self.original / "standalone-accounting.sqlite3"
        StandaloneAccountingStore(self.original_db)

    def backup(self, *, identity=True, templates=True):
        if identity:
            LocalCompanyIdentity(self.original).add_user(
                "synthetic-admin", "SyntheticCrashOnlyPassword2026", "admin")
        if templates:
            StandaloneAccountingTemplateStore(self.original).save(
                "issuer", "Synthetic issuer", {"format": "madar-issuer-profile-v1",
                                                "profile": {"legalName": "Synthetic"}})
        return AutomaticStandaloneBackups(
            self.original, plaintext_acknowledged=True).backup_now()

    def restore(self, source):
        return restore_standalone_accounting(
            source, self.destination,
            plaintext_acknowledged=True, offline_acknowledged=True)

    def kill(self, backup, target_name, phase="after"):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        result = subprocess.run(
            [sys.executable, "-B", "-c", _KILL_AT_LINK,
             str(backup), str(self.destination), target_name, phase],
            capture_output=True, cwd=self.root, env=env, timeout=30)
        self.assertEqual(result.returncode, 71 if phase == "after" else 72,
                         result.stderr.decode(errors="replace"))

    def test_crash_at_every_publication_boundary_recovers_without_exposed_partial_ledger(self):
        for target_name in ("invoice-templates.json", "local-users.json",
                            "standalone-accounting.sqlite3"):
            with self.subTest(after=target_name):
                folder = self.destination_root / target_name
                folder.mkdir()
                self.destination = folder / "standalone-accounting.sqlite3"
                backup = self.backup(identity=not (self.original / "local-users.json").exists(),
                                     templates=not (self.original / "invoice-templates.json").exists())
                self.kill(backup, target_name)
                users = folder / "local-users.json"
                templates = folder / "invoice-templates.json"
                if target_name != self.destination.name:
                    self.assertFalse(self.destination.exists(),
                                     "No ledger may be visible before companions")
                else:
                    self.assertTrue(users.is_file())
                    self.assertTrue(templates.is_file())
                self.assertEqual(self.restore(backup), self.destination)
                self.assertEqual(users.read_bytes(), backup.with_suffix(".users.json").read_bytes())
                self.assertEqual(templates.read_bytes(), backup.with_suffix(".templates.json").read_bytes())
                self.assertEqual(StandaloneAccountingStore(self.destination).read(
                    actor="root", accounts={"root": {"username": "root", "role": "admin"}})["revision"], 0)
                self.assertFalse((folder / restore_module._STAGE_NAME).exists())
                with self.assertRaises(FileExistsError):
                    self.restore(backup)

    def test_crash_before_first_link_can_retry(self):
        backup = self.backup()
        self.kill(backup, "invoice-templates.json", "before")
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.destination_root / "invoice-templates.json").exists())
        self.restore(backup)
        self.assertTrue(self.destination.exists())

    def test_retry_cannot_remove_foreign_identity_or_publish_ledger(self):
        backup = self.backup()
        self.kill(backup, "invoice-templates.json")
        foreign = self.destination_root / "local-users.json"
        foreign.write_bytes(b"foreign identity; do not modify")
        with self.assertRaises(FileExistsError):
            self.restore(backup)
        self.assertEqual(foreign.read_bytes(), b"foreign identity; do not modify")
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.destination_root / "invoice-templates.json").exists())

    def test_changed_source_refuses_stale_transaction_without_deleting_its_stage(self):
        backup = self.backup()
        self.kill(backup, "invoice-templates.json")
        backup.with_suffix(".templates.json").write_bytes(b"{}")
        with self.assertRaises(restore_module.StandaloneRestoreError):
            self.restore(backup)
        self.assertFalse(self.destination.exists())
        self.assertTrue((self.destination_root / restore_module._STAGE_NAME).is_dir())

    def test_exception_at_second_link_rolls_back_owned_links_only(self):
        backup = self.backup()
        original_link = os.link

        def fail_identity(source, target, *args, **kwargs):
            if Path(target).name == "local-users.json":
                raise OSError("synthetic identity publication error")
            return original_link(source, target, *args, **kwargs)

        with patch.object(restore_module.os, "link", side_effect=fail_identity):
            with self.assertRaisesRegex(OSError, "synthetic identity publication error"):
                self.restore(backup)
        self.assertEqual(list(self.destination_root.iterdir()), [])
        self.restore(backup)
        self.assertTrue(self.destination.is_file())

    def test_legacy_sqlite_only_manual_restore_remains_no_clobber(self):
        backup = self.root / "manual.sqlite3"
        backup_standalone_accounting(self.original_db, backup, plaintext_acknowledged=True)
        self.restore(backup)
        self.assertTrue(self.destination.is_file())
        self.assertFalse((self.destination_root / "local-users.json").exists())
        with self.assertRaises(FileExistsError):
            self.restore(backup)


if __name__ == "__main__":
    unittest.main()
