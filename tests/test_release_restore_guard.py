"""Fail-closed Windows launch checks; never uses the real application profile."""

import inspect
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app
from maintenance_recovery import pending_restore_journal
from full_recovery import _journal_path


class StartupRestoreGuardTests(unittest.TestCase):
    def test_journal_discovery_is_read_only_even_if_data_root_missing(self):
        with tempfile.TemporaryDirectory(prefix="madar-startup-guard-") as folder:
            root = Path(folder) / "AppData" / "MadarDesk"
            self.assertIsNone(pending_restore_journal(root))
            self.assertFalse(root.exists())
            journal = _journal_path(root)
            journal.parent.mkdir(parents=True, exist_ok=True)
            journal.write_text("malformed-on-purpose", encoding="utf8")
            self.assertEqual(pending_restore_journal(root), journal)
            self.assertFalse(root.exists())
            self.assertEqual(journal.read_text(encoding="utf8"), "malformed-on-purpose")

    def test_main_checks_journal_before_bridge_or_data_root_creation(self):
        source = inspect.getsource(native_app.main)
        self.assertLess(source.index("pending_restore_journal(data_root)"),
                        source.index("api = Bridge()"))
        self.assertIn("if pending is not None:", source)


if __name__ == "__main__":
    unittest.main()
