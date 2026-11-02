"""Synthetic LAN deletion regression: failed state save cannot mutate live cache."""

import tempfile
import threading
import unittest
from pathlib import Path

from lan import LanService


class _SharedStateBridge:
    def __init__(self):
        self._lock = threading.RLock()
        self.state = {"projects": [], "tasks": [{
            "id": "synthetic-task", "projectId": "synthetic-project",
            "assignees": ["editor"]}]}
        self.attempted = 0

    def getState(self):
        # native_app.getState() also assigns and returns self.state.
        return self.state

    def saveState(self, incoming):
        self.attempted += 1
        raise OSError("synthetic state persistence failure")


class DeleteUserStateFailureTests(unittest.TestCase):
    def test_failed_task_save_keeps_live_assignments_and_identity(self):
        with tempfile.TemporaryDirectory(prefix="madar-delete-state-") as directory:
            bridge = _SharedStateBridge()
            service = LanService(bridge, Path(directory) / "users.json")
            service.setup_owner("admin", "synthetic-admin-password")
            admin = service.authenticate("admin", "synthetic-admin-password")["token"]
            service.upsert_user(admin, {
                "username": "editor", "password": "synthetic-editor-password",
                "role": "editor"})
            editor = service.authenticate("editor", "synthetic-editor-password")["token"]
            registry_before = service.users_path.read_bytes()

            with self.assertRaisesRegex(OSError, "synthetic state persistence failure"):
                service.delete_user(admin, "editor")

            self.assertEqual(bridge.attempted, 1)
            self.assertEqual(bridge.state["tasks"][0]["assignees"], ["editor"])
            self.assertEqual(service.users_path.read_bytes(), registry_before)
            self.assertEqual(service.account_for(editor)["username"], "editor")


if __name__ == "__main__":
    unittest.main()
