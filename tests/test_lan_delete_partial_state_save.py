"""Synthetic failure after a committed LAN task-state write during deletion."""

from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_lan_delete_registry_failure import _SyntheticBridge
from lan import LanService


class DeletePartialStateSaveTests(unittest.TestCase):
    def _setup(self, directory):
        bridge = _SyntheticBridge(Path(directory) / "state.json")
        service = LanService(bridge, Path(directory) / "users.json")
        service.setup_owner("admin", "synthetic-admin-password")
        admin = service.authenticate("admin", "synthetic-admin-password")["token"]
        service.upsert_user(admin, {"username": "editor", "password": "synthetic-editor-password", "role": "editor"})
        editor = service.authenticate("editor", "synthetic-editor-password")["token"]
        return bridge, service, admin, editor

    def test_committed_state_then_error_restores_assignments_and_identity(self):
        with tempfile.TemporaryDirectory(prefix="madar-delete-partial-") as directory:
            bridge, service, admin, editor = self._setup(directory)
            before = deepcopy(bridge.state)
            registry_before = service.users_path.read_bytes()
            original_save = bridge.saveState
            calls = 0

            def commit_then_raise(incoming):
                nonlocal calls
                calls += 1
                result = original_save(incoming)
                if calls == 1:
                    raise OSError("synthetic post-commit failure")
                return result

            with patch.object(bridge, "saveState", side_effect=commit_then_raise):
                with self.assertRaisesRegex(OSError, "synthetic post-commit failure"):
                    service.delete_user(admin, "editor")

            self.assertEqual(bridge.state, before)
            self.assertEqual(json.loads(bridge.state_path.read_text(encoding="utf8")), before)
            self.assertEqual(service.users_path.read_bytes(), registry_before)
            self.assertEqual(service.account_for(editor)["username"], "editor")
            self.assertFalse(service.delete_journal_path.exists())
            self.assertEqual(calls, 2)

    def test_partial_save_and_failed_compensation_reports_both_failures(self):
        with tempfile.TemporaryDirectory(prefix="madar-delete-partial-") as directory:
            bridge, service, admin, editor = self._setup(directory)
            original_save = bridge.saveState
            calls = 0

            def fail_both(incoming):
                nonlocal calls
                calls += 1
                if calls == 1:
                    original_save(incoming)
                    raise OSError("synthetic post-commit failure")
                raise OSError("synthetic compensation failure")

            with patch.object(bridge, "saveState", side_effect=fail_both):
                with self.assertRaisesRegex(RuntimeError, "task-state rollback failed"):
                    service.delete_user(admin, "editor")
            # A durable incomplete mutation blocks all account access until
            # startup reconciliation can finish the pending delete.
            with self.assertRaisesRegex(PermissionError, "recovery is required"):
                service.account_for(editor)
            self.assertTrue(service.delete_journal_path.is_file())
            self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
