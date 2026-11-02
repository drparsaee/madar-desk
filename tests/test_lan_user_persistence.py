"""Synthetic failure-injection checks for LAN identity persistence and ACL."""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from lan import LanService, verify_password


class _Bridge:
    def __init__(self):
        self._lock = threading.RLock()

    def getState(self):
        return {"projects": [], "tasks": []}


class UserPersistenceFailureTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="madar-lan-persist-")
        self.addCleanup(self.scratch.cleanup)
        self.service = LanService(_Bridge(), Path(self.scratch.name) / "users.json")
        self.service.setup_owner("admin", "synthetic-admin-password")
        self.admin = self.service.authenticate("admin", "synthetic-admin-password")["token"]
        self.service.upsert_user(self.admin, {
            "username": "editor", "password": "synthetic-editor-password", "role": "editor"})

    def test_failed_role_change_does_not_grant_unpersisted_admin(self):
        editor_token = self.service.authenticate("editor", "synthetic-editor-password")["token"]
        with patch.object(self.service, "_store_users", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                self.service.upsert_user(self.admin, {"username": "editor", "role": "admin"})
        self.assertEqual(self.service.account_for(editor_token)["role"], "editor")
        self.assertEqual(self.service.users["editor"]["role"], "editor")

    def test_failed_new_user_creation_does_not_leave_ghost_login(self):
        with patch.object(self.service, "_store_users", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                self.service.upsert_user(self.admin, {
                    "username": "ghost", "password": "synthetic-ghost-password", "role": "viewer"})
        self.assertNotIn("ghost", self.service.users)

    def test_failed_password_change_keeps_old_credentials(self):
        with patch.object(self.service, "_store_users", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                self.service.change_password(self.admin, "synthetic-admin-password", "synthetic-new-password")
        stored_hash = self.service.users["admin"]["passwordHash"]
        self.assertTrue(verify_password("synthetic-admin-password", stored_hash))
        self.assertFalse(verify_password("synthetic-new-password", stored_hash))

    def test_failed_admin_password_reset_keeps_target_credentials(self):
        with patch.object(self.service, "_store_users", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                self.service.reset_password(self.admin, "editor", "synthetic-new-password")
        stored_hash = self.service.users["editor"]["passwordHash"]
        self.assertTrue(verify_password("synthetic-editor-password", stored_hash))
        self.assertFalse(verify_password("synthetic-new-password", stored_hash))

    def test_failed_profile_write_keeps_previous_identity_in_memory_and_on_disk(self):
        before = self.service.current_user(self.admin)
        disk_before = self.service.users_path.read_bytes()
        with patch.object(self.service, "_store_users", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                self.service.update_profile(self.admin, {"displayName": "Uncommitted identity"})
        self.assertEqual(self.service.current_user(self.admin), before)
        self.assertEqual(self.service.users_path.read_bytes(), disk_before)


if __name__ == "__main__":
    unittest.main()
