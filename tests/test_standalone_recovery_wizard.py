"""Offline recovery preflight and safely published new database, synthetic only."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from standalone_accounting import StandaloneAccountingStore
from standalone_accounting_auto_backup import AutomaticStandaloneBackups
from standalone_accounting_recovery_wizard import (
    list_recovery_candidates, recovery_preview,
)
from standalone_accounting_restore import restore_standalone_accounting


class RecoveryWizardPreflight(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="madar-recovery-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.current = self.root / "active"
        self.current.mkdir()
        self.destination = self.root / "new-accounting"
        self.destination.mkdir()
        self.actor = "synthetic"
        self.accounts = {self.actor: {"username": self.actor, "role": "admin"}}
        store = StandaloneAccountingStore(
            self.current / "standalone-accounting.sqlite3", default_currency="RIAL")
        store.command({"type": "party.register", "eventId": "E1",
                       "partyId": "P1", "name": "Test party", "kind": "customer"},
                      actor=self.actor, accounts=self.accounts, expected_revision=0,
                      now="2026-10-25T10:00:00Z")
        self.source = AutomaticStandaloneBackups(
            self.current, plaintext_acknowledged=True).backup_now()

    def test_preflight_readonly_then_no_clobber_restore_equal_revision(self):
        old = self.source.read_bytes()
        source_current = (self.current / "standalone-accounting.sqlite3").read_bytes()
        preview = recovery_preview(self.source, self.destination)
        self.assertEqual(preview["revision"], 1)
        self.assertEqual(preview["events"], 1)
        self.assertEqual(preview["currency"], "RIAL")
        self.assertTrue(preview["plaintext"])
        self.assertFalse(preview["existing_destination_will_be_overwritten"])
        self.assertFalse(preview["destination"].exists())
        self.assertEqual(self.source.read_bytes(), old)
        self.assertEqual((self.current / "standalone-accounting.sqlite3").read_bytes(),
                         source_current)
        output = restore_standalone_accounting(
            self.source, preview["destination"], plaintext_acknowledged=True,
            offline_acknowledged=True)
        view = StandaloneAccountingStore(output).read(
            actor=self.actor, accounts=self.accounts)
        self.assertEqual(view["revision"], 1)
        self.assertEqual(view["view"]["parties"]["P1"]["name"], "Test party")
        self.assertEqual(self.source.read_bytes(), old)

    def test_preflight_existing_destination_refuses_even_when_valid(self):
        target = self.destination / "standalone-accounting.sqlite3"
        target.write_bytes(b"existing user data must stay exactly unchanged")
        with self.assertRaises(FileExistsError):
            recovery_preview(self.source, self.destination)
        self.assertEqual(target.read_bytes(), b"existing user data must stay exactly unchanged")

    def test_candidate_list_only_verified_automatic_backups(self):
        valid = list_recovery_candidates(self.current)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["path"], self.source)
        self.assertEqual(valid[0]["revision"], 1)
        wrong = self.source.with_name(
            "standalone-accounting-auto-20261025T123456123456Z-1234567890abcdef.sqlite3")
        wrong.write_bytes(b"not a sqlite backup")
        self.assertEqual(len(list_recovery_candidates(self.current)), 1)
        self.assertEqual(list_recovery_candidates(self.destination), [])
        with self.assertRaises(ValueError):
            list_recovery_candidates(Path("relative"))

    def test_corrupt_backup_rejected_without_creating_destination(self):
        bad = self.root / "bad.sqlite3"
        bad.write_bytes(b"not a database")
        with self.assertRaises(Exception):
            recovery_preview(bad, self.destination)
        self.assertFalse((self.destination / "standalone-accounting.sqlite3").exists())

    def test_recovery_cli_exits_before_live_accounting_or_backup_service(self):
        from standalone_accounting_desktop import main
        with patch(
            "standalone_accounting_recovery_wizard.run_offline_recovery_wizard",
            return_value=True
        ) as mocked, patch(
            "standalone_accounting_desktop.AccountingDesktopAPI",
            side_effect=AssertionError("Must never open active DB in recovery mode")
        ):
            self.assertEqual(main(["--recovery", "--data-dir", str(self.current)]), 0)
        mocked.assert_called_once_with(self.current)


if __name__ == "__main__":
    unittest.main()
