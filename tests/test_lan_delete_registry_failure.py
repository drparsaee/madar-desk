"""Synthetic regression for registry failure after LAN task unassignment."""

from copy import deepcopy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from lan import LanService
from offline_exchange import atomic_json


class _SyntheticBridge:
    def __init__(self, path):
        self._lock = threading.RLock()
        self.state_path = path
        self.state = {"projects": [], "tasks": [{
            "id": "synthetic-task", "projectId": "synthetic-project",
            "assignees": ["editor"]}]}
        self.saved = []
        atomic_json(self.state_path, self.state)

    def getState(self):
        return self.state

    def saveState(self, incoming):
        atomic_json(self.state_path, incoming)
        self.state = deepcopy(incoming)
        self.saved.append(deepcopy(incoming))


class DeleteUserRegistryFailureTests(unittest.TestCase):
    def test_failed_registry_save_restores_persisted_task_assignments(self):
        with tempfile.TemporaryDirectory(prefix="madar-delete-registry-") as directory:
            bridge = _SyntheticBridge(Path(directory) / "state.json")
            service = LanService(bridge, Path(directory) / "users.json")
            service.setup_owner("admin", "synthetic-admin-password")
            admin = service.authenticate("admin", "synthetic-admin-password")["token"]
            service.upsert_user(admin, {
                "username": "editor", "password": "synthetic-editor-password",
                "role": "editor"})
            editor = service.authenticate("editor", "synthetic-editor-password")["token"]
            before = deepcopy(bridge.state)
            registry_before = service.users_path.read_bytes()

            with patch.object(service, "_store_users", side_effect=OSError("synthetic registry failure")):
                with self.assertRaisesRegex(OSError, "synthetic registry failure"):
                    service.delete_user(admin, "editor")

            self.assertEqual(bridge.state, before)
            self.assertEqual(json.loads(bridge.state_path.read_text(encoding="utf8")), before)
            self.assertEqual(service.users_path.read_bytes(), registry_before)
            self.assertEqual(service.account_for(editor)["username"], "editor")
            self.assertEqual(len(bridge.saved), 2)

    def test_failed_rollback_is_reported_without_revoking_identity(self):
        with tempfile.TemporaryDirectory(prefix="madar-delete-registry-") as directory:
            bridge = _SyntheticBridge(Path(directory) / "state.json")
            service = LanService(bridge, Path(directory) / "users.json")
            service.setup_owner("admin", "synthetic-admin-password")
            admin = service.authenticate("admin", "synthetic-admin-password")["token"]
            service.upsert_user(admin, {
                "username": "editor", "password": "synthetic-editor-password",
                "role": "editor"})
            editor = service.authenticate("editor", "synthetic-editor-password")["token"]
            original_save = bridge.saveState

            def fail_on_rollback(incoming):
                if bridge.saved:
                    raise OSError("synthetic rollback failure")
                return original_save(incoming)

            with patch.object(bridge, "saveState", side_effect=fail_on_rollback), patch.object(
                    service, "_store_users", side_effect=OSError("synthetic registry failure")):
                with self.assertRaisesRegex(RuntimeError, "task-state rollback failed"):
                    service.delete_user(admin, "editor")

            with self.assertRaisesRegex(PermissionError, "recovery is required"):
                service.account_for(editor)
            self.assertTrue(service.delete_journal_path.is_file())
            self.assertEqual(bridge.state["tasks"][0]["assignees"], [])


if __name__ == "__main__":
    unittest.main()
