"""Offline restore preview/wizard tests with disposable accounting books only."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from standalone_accounting import StandaloneAccountingStore
from standalone_accounting_backup import backup_standalone_accounting
from standalone_accounting_desktop import main as desktop_main
from standalone_accounting_restore_ui import (
    preview_restore_candidate, run_restore_wizard)


ACCOUNTS = {"local": {"username": "local", "role": "admin"}}


class RestoreWizardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-restore-wizard-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        data = self.root / "source"
        data.mkdir()
        original = data / "standalone-accounting.sqlite3"
        StandaloneAccountingStore(original, default_currency="RIAL").read(
            actor="local", accounts=ACCOUNTS)
        backup_folder = self.root / "backups"
        backup_folder.mkdir()
        self.backup = backup_standalone_accounting(
            original, backup_folder / "trusted.sqlite3",
            plaintext_acknowledged=True)
        self.folder = self.root / "new-private-book"
        self.folder.mkdir()

    def test_preview_never_creates_target_and_rejects_existing_book(self):
        preview = preview_restore_candidate(self.backup, self.folder)
        self.assertEqual(preview["revision"], 0)
        self.assertIsNone(preview["digest"])
        self.assertFalse(preview["destination"].exists())
        self.assertTrue(preview["plaintext"])
        self.assertFalse(preview["overwrites"])
        preview["destination"].write_bytes(b"DO NOT CHANGE")
        with self.assertRaises(FileExistsError):
            preview_restore_candidate(self.backup, self.folder)
        self.assertEqual(preview["destination"].read_bytes(), b"DO NOT CHANGE")

    def fake_dialogs(self, *, offline=None, plaintext=None):
        """Fake tkinter imports; no real graphics, files or user interaction."""
        flags = {"created": False, "closed": False, "success": False, "errors": []}

        class Window:
            def __init__(self):
                flags["created"] = True

            def withdraw(self):
                pass

            def destroy(self):
                flags["closed"] = True

        tk = types.ModuleType("tkinter")
        tk.Tk = Window
        tk.filedialog = types.SimpleNamespace(
            askopenfilename=lambda **kwargs: str(self.backup),
            askdirectory=lambda **kwargs: str(self.folder))
        answers = iter((offline, plaintext))
        tk.simpledialog = types.SimpleNamespace(
            askstring=lambda *args, **kwargs: next(answers))
        tk.messagebox = types.SimpleNamespace(
            askyesno=lambda *args, **kwargs: True,
            showerror=lambda *args, **kwargs: flags["errors"].append(args),
            showinfo=lambda *args, **kwargs: flags.__setitem__("success", True))
        return tk, flags

    def test_partial_or_mismatched_ack_never_writes(self):
        for offline, plain in (("offline", "PLAINTEXT"),
                               ("OFFLINE", "plaintext"),
                               ("OFFLINE", None)):
            with self.subTest(offline=offline, plaintext=plain):
                fake, flags = self.fake_dialogs(offline=offline, plaintext=plain)
                with patch.dict(sys.modules, {"tkinter": fake}):
                    self.assertEqual(run_restore_wizard(), 0)
                self.assertTrue(flags["closed"])
                self.assertFalse(flags["success"])
                self.assertFalse((self.folder / "standalone-accounting.sqlite3").exists())

    def test_wizard_with_both_exact_ack_creates_new_valid_book(self):
        fake, flags = self.fake_dialogs(
            offline="OFFLINE", plaintext="PLAINTEXT")
        with patch.dict(sys.modules, {"tkinter": fake}):
            self.assertEqual(run_restore_wizard(), 0)
        self.assertTrue(flags["closed"])
        self.assertTrue(flags["success"])
        created = self.folder / "standalone-accounting.sqlite3"
        self.assertTrue(created.is_file())
        self.assertEqual(StandaloneAccountingStore(created).read(
            actor="local", accounts=ACCOUNTS)["revision"], 0)
        self.assertTrue(self.backup.is_file())

    def test_desktop_restore_flag_exits_before_api_or_web_host(self):
        module = types.ModuleType("standalone_accounting_restore_ui")
        module.run_restore_wizard = lambda: 42
        with patch.dict(sys.modules, {"standalone_accounting_restore_ui": module}):
            self.assertEqual(desktop_main(["--restore-ui"]), 42)


if __name__ == "__main__":
    unittest.main()
