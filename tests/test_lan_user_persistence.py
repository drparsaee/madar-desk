"""Synthetic failure-injection checks for LAN identity persistence and ACL."""

from copy import deepcopy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from lan import LanService, verify_password


class _Bridge:
    def __init__(self):
        self._lock = threading.RLock()
        self.state = {"projects": [], "tasks": []}

    def getState(self):
        return deepcopy(self.state)

    def saveState(self, state):
        self.state = deepcopy(state)


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

    def test_user_registry_update_never_overwrites_unowned_fixed_temp_file(self):
        unrelated = self.service.users_path.with_name(self.service.users_path.name + ".tmp")
        sentinel = b"unrelated-synthetic-file-do-not-clobber"
        unrelated.write_bytes(sentinel)
        self.service.update_profile(self.admin, {"displayName": "Synthetic updated profile"})
        self.assertEqual(unrelated.read_bytes(), sentinel)
        self.assertEqual(self.service.current_user(self.admin)["displayName"],
                         "Synthetic updated profile")

    def test_failed_user_deletion_keeps_account_session_and_registry(self):
        editor_token = self.service.authenticate("editor", "synthetic-editor-password")["token"]
        disk_before = self.service.users_path.read_bytes()
        with patch.object(self.service, "_store_users", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                self.service.delete_user(self.admin, "editor")
        self.assertEqual(self.service.users_path.read_bytes(), disk_before)
        self.assertEqual(self.service.account_for(editor_token)["username"], "editor")
        self.assertEqual(self.service.users["editor"]["role"], "editor")

    def test_failed_delete_preserves_user_session_and_assigned_cards(self):
        bridge = self.service.bridge
        bridge.state["tasks"] = [{"id": "card-qa", "assignees": ["editor", "admin"]}]
        old_state = deepcopy(bridge.state)
        before_registry = self.service.users_path.read_bytes()
        editor_token = self.service.authenticate("editor", "synthetic-editor-password")["token"]
        with patch.object(self.service, "_store_users", side_effect=OSError("synthetic disk failure")):
            with self.assertRaisesRegex(OSError, "synthetic disk failure"):
                self.service.delete_user(self.admin, "editor")
        self.assertEqual(bridge.getState(), old_state)
        self.assertIn("editor", self.service.users)
        self.assertEqual(self.service.account_for(editor_token)["username"], "editor")
        self.assertEqual(self.service.users_path.read_bytes(), before_registry)

    def test_delete_rolls_back_registry_if_card_save_fails(self):
        bridge = self.service.bridge
        bridge.state["tasks"] = [{"id": "card-qa", "assignees": ["editor"]}]
        old_state = deepcopy(bridge.state)
        before_registry = self.service.users_path.read_bytes()
        editor_token = self.service.authenticate("editor", "synthetic-editor-password")["token"]
        with patch.object(bridge, "saveState", side_effect=OSError("synthetic card write failure")):
            with self.assertRaisesRegex(OSError, "synthetic card write failure"):
                self.service.delete_user(self.admin, "editor")
        self.assertEqual(bridge.getState(), old_state)
        self.assertIn("editor", self.service.users)
        self.assertEqual(self.service.account_for(editor_token)["username"], "editor")
        self.assertEqual(self.service.users_path.read_bytes(), before_registry)

    def test_failed_delete_does_not_mutate_a_live_bridge_state_reference(self):
        bridge = self.service.bridge
        bridge.state["tasks"] = [{"id": "card-qa", "assignees": ["editor", "admin"]}]
        original = deepcopy(bridge.state)
        # Native state getters may expose an alias, not a detached copy.
        with patch.object(bridge, "getState", side_effect=lambda: bridge.state):
            with patch.object(self.service, "_store_users", side_effect=OSError("synthetic disk failure")):
                with self.assertRaises(OSError):
                    self.service.delete_user(self.admin, "editor")
        self.assertEqual(bridge.state, original)

    def test_delete_rejects_unhashable_username_without_side_effects(self):
        before = self.service.users_path.read_bytes()
        for invalid in ([], {}, ["editor"]):
            with self.subTest(type=type(invalid).__name__):
                with self.assertRaises(ValueError):
                    self.service.delete_user(self.admin, invalid)
        self.assertIn("editor", self.service.users)
        self.assertEqual(self.service.users_path.read_bytes(), before)

    def test_successful_delete_unassigns_cards_and_revokes_deleted_session(self):
        bridge = self.service.bridge
        bridge.state["tasks"] = [{"id": "card-qa", "assignees": ["editor", "admin"]}]
        editor_token = self.service.authenticate("editor", "synthetic-editor-password")["token"]
        self.assertTrue(self.service.delete_user(self.admin, "editor"))
        self.assertEqual(bridge.getState()["tasks"][0]["assignees"], ["admin"])
        self.assertNotIn("editor", self.service.users)
        self.assertNotIn("editor", self.service._read_users())
        with self.assertRaises(PermissionError):
            self.service.account_for(editor_token)


if __name__ == "__main__":
    unittest.main()
