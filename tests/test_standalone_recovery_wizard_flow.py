"""Whole recovery-wizard decision flow using synthetic books and mocked dialogs.

No human desktop, APPDATA, task manager, external service or live SQL is touched.
"""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from standalone_accounting import StandaloneAccountingStore
from standalone_accounting_auto_backup import AutomaticStandaloneBackups
from standalone_accounting_recovery_wizard import run_offline_recovery_wizard


class _FakeRoot:
    def withdraw(self):
        return None

    def destroy(self):
        return None


class RecoveryDecisionFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-recovery-flow-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.active = self.base / "source-book"
        self.active.mkdir()
        self.dest = self.base / "new-book"
        self.dest.mkdir()
        self.user = "test-operator"
        self.accounts = {self.user: {"username": self.user, "role": "admin"}}
        store = StandaloneAccountingStore(self.active / "standalone-accounting.sqlite3",
                                          default_currency="RIAL")
        store.command({"type": "party.register", "eventId": "e-1", "partyId": "P1",
                       "name": "Sample party", "kind": "customer"},
                      actor=self.user, accounts=self.accounts, expected_revision=0,
                      now="2026-10-25T12:00:00Z")
        self.source = AutomaticStandaloneBackups(
            self.active, plaintext_acknowledged=True).backup_now()
        self.original_backup = self.source.read_bytes()
        self.original_db = (self.active / "standalone-accounting.sqlite3").read_bytes()

    def run_wizard(self, *, answers=(True, True), source=None, destination=None):
        messages = []
        decisions = iter(answers)
        tk = types.ModuleType("tkinter")
        tk.Tk = _FakeRoot
        tk.filedialog = types.SimpleNamespace(
            askopenfilename=lambda **_: str(source if source is not None else self.source),
            askdirectory=lambda **_: str(destination if destination is not None else self.dest))
        tk.messagebox = types.SimpleNamespace(
            askyesno=lambda title, body, **_: (messages.append((title, body)), next(decisions))[1],
            showinfo=lambda title, body, **_: messages.append(("success", body)),
            showerror=lambda title, body, **_: messages.append(("error", body)))
        with patch.dict(sys.modules, {"tkinter": tk}):
            result = run_offline_recovery_wizard(self.active)
        return result, messages

    def assert_untouched_source(self):
        self.assertEqual(self.source.read_bytes(), self.original_backup)
        self.assertEqual((self.active / "standalone-accounting.sqlite3").read_bytes(),
                         self.original_db)
        for filename in ("tasks.json", "finance.json", "madar-unified.sqlite3"):
            self.assertFalse((self.dest / filename).exists())

    def test_both_confirmations_create_independent_replayable_book(self):
        completed, messages = self.run_wizard()
        self.assertTrue(completed)
        self.assertEqual([m[0] for m in messages[-1:]], ["success"])
        self.assertEqual(len(messages), 3)
        restored = self.dest / "standalone-accounting.sqlite3"
        view = StandaloneAccountingStore(restored).read(
            actor=self.user, accounts=self.accounts)
        self.assertEqual(view["revision"], 1)
        self.assertEqual(view["view"]["currency"], "RIAL")
        self.assertIn("P1", view["view"]["parties"])
        self.assert_untouched_source()

    def test_declining_either_confirmation_publishes_nothing(self):
        for answers in ((False,), (True, False)):
            completed, _ = self.run_wizard(answers=answers)
            self.assertFalse(completed)
            self.assertFalse((self.dest / "standalone-accounting.sqlite3").exists())
        self.assert_untouched_source()

    def test_existing_destination_cannot_be_overwritten(self):
        path = self.dest / "standalone-accounting.sqlite3"
        path.write_bytes(b"EXISTING MUST STAY")
        completed, messages = self.run_wizard()
        self.assertFalse(completed)
        self.assertEqual(path.read_bytes(), b"EXISTING MUST STAY")
        self.assertTrue(any(m[0] == "error" for m in messages))
        self.assert_untouched_source()

    def test_bad_source_rejected_before_any_confirmation(self):
        bad = self.base / "corrupt.sqlite3"
        bad.write_bytes(b"NOT VALID")
        completed, messages = self.run_wizard(source=bad)
        self.assertFalse(completed)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0][0], "error")
        self.assertFalse((self.dest / "standalone-accounting.sqlite3").exists())
        self.assert_untouched_source()


if __name__ == "__main__":
    unittest.main()
