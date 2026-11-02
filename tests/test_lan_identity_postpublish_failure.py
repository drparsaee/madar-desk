"""Synthetic LAN identity rollback after a registry writer publishes then raises."""

import json
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


class IdentityPostPublishFailureTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="madar-lan-identity-postpublish-")
        self.addCleanup(self.scratch.cleanup)
        self.service = LanService(_Bridge(), Path(self.scratch.name) / "users.json")
        self.service.setup_owner("admin", "synthetic-admin-password")
        self.admin = self.service.authenticate("admin", "synthetic-admin-password")["token"]
        self.service.upsert_user(self.admin, {
            "username": "editor", "password": "synthetic-editor-password", "role": "editor"})
        self.editor = self.service.authenticate("editor", "synthetic-editor-password")["token"]

    def _write_then_raise_once(self):
        real_store = self.service._store_users
        calls = []

        def store(users):
            calls.append(1)
            real_store(users)
            if len(calls) == 1:
                raise OSError("synthetic failure after atomic publication")

        return patch.object(self.service, "_store_users", side_effect=store), calls

    def _assert_registry_unchanged(self, before):
        self.assertEqual(self.service.users_path.read_bytes(), before)
        self.assertEqual(json.loads(before), self.service.users)
        self.assertEqual(self.service.account_for(self.editor)["role"], "editor")

    def test_failed_admin_promotion_does_not_survive_host_restart(self):
        before = self.service.users_path.read_bytes()
        patcher, calls = self._write_then_raise_once()
        with patcher, self.assertRaises(OSError):
            self.service.upsert_user(self.admin, {"username": "editor", "role": "admin"})
        self._assert_registry_unchanged(before)
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(LanService(_Bridge(), self.service.users_path).users["editor"]["role"], "editor")

    def test_failed_self_password_change_keeps_old_password_on_disk(self):
        before = self.service.users_path.read_bytes()
        patcher, calls = self._write_then_raise_once()
        with patcher, self.assertRaises(OSError):
            self.service.change_password(self.admin, "synthetic-admin-password", "synthetic-new-password")
        self._assert_registry_unchanged(before)
        self.assertTrue(verify_password("synthetic-admin-password", self.service.users["admin"]["passwordHash"]))
        self.assertGreaterEqual(len(calls), 2)

    def test_failed_admin_reset_keeps_target_password_and_session(self):
        before = self.service.users_path.read_bytes()
        patcher, calls = self._write_then_raise_once()
        with patcher, self.assertRaises(OSError):
            self.service.reset_password(self.admin, "editor", "synthetic-reset-password")
        self._assert_registry_unchanged(before)
        self.assertTrue(verify_password("synthetic-editor-password", self.service.users["editor"]["passwordHash"]))
        self.assertGreaterEqual(len(calls), 2)

    def test_failed_profile_update_keeps_disk_and_live_identity(self):
        before = self.service.users_path.read_bytes()
        patcher, calls = self._write_then_raise_once()
        with patcher, self.assertRaises(OSError):
            self.service.update_profile(self.editor, {"displayName": "Uncommitted synthetic profile"})
        self._assert_registry_unchanged(before)
        self.assertGreaterEqual(len(calls), 2)

    def test_foreign_registry_revision_is_not_overwritten(self):
        before = self.service.users_path.read_bytes()
        foreign = json.loads(before)
        foreign["editor"]["displayName"] = "Synthetic foreign revision"
        real_store = self.service._store_users

        def foreign_then_raise(_candidate):
            real_store(foreign)
            raise OSError("synthetic foreign writer")

        with patch.object(self.service, "_store_users", side_effect=foreign_then_raise):
            with self.assertRaisesRegex(RuntimeError, "unexpected registry revision"):
                self.service.upsert_user(self.admin, {"username": "editor", "role": "admin"})
        self.assertEqual(json.loads(self.service.users_path.read_text(encoding="utf8")), foreign)
        self.assertEqual(self.service.users["editor"]["role"], "editor")


if __name__ == "__main__":
    unittest.main()
