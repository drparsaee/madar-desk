"""MadarHost admin-managed E6 internal inbox opt-in/field ACL, no delivery."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
import unittest
from unittest.mock import patch

from lan import LanService, _INTERNAL_NOTICE_ROLE_FIELDS
from mtr_lan_notification_adapter import _FIELDS


class DisposableBridge:
    def __init__(self):
        self._lock = RLock()
        self._state = {
            "projects": [{"id": "project-one"}],
            "tasks": [{"id": "task-one", "projectId": "project-one",
                       "assignees": ["editor"], "title": "synthetic"}],
        }

    def getState(self):
        return deepcopy(self._state)


class InternalNoticeHostAdminTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mtr-notice-grants-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        env = patch.dict(os.environ, {
            "APPDATA": str(root), "LOCALAPPDATA": str(root),
            "USERPROFILE": str(root), "HOME": str(root),
            "TEMP": str(root), "TMP": str(root),
        })
        env.start()
        self.addCleanup(env.stop)
        self.users_path = root / "users.json"
        self.bridge = DisposableBridge()
        self.host = LanService(self.bridge, self.users_path, bind="127.0.0.1", port=0)
        self.host.setup_owner("owner", "synthetic-test-password-12345")
        self.owner = self.host.authenticate("owner", "synthetic-test-password-12345")["token"]

    def edit(self, **fields):
        return self.host.upsert_user(self.owner, {
            "username": "editor", "role": "editor", "projects": ["project-one"],
            "password": "synthetic-test-password-12345",
            **fields,
        })

    def test_host_notification_field_cap_is_exact_adapter_role_cap(self):
        self.assertEqual(_INTERNAL_NOTICE_ROLE_FIELDS, _FIELDS)

    def test_default_off_and_only_admin_can_read_internal_notice_grants(self):
        self.edit()
        record = self.host.users["editor"]
        self.assertIs(record["internalNotificationsEnabled"], False)
        self.assertIsNone(record["internalNotificationFields"])
        admin_listing = next(row for row in self.host.list_users(self.owner)
                             if row["username"] == "editor")
        self.assertIs(admin_listing["internalNotificationsEnabled"], False)
        self.assertIsNone(admin_listing["internalNotificationFields"])
        user = self.host.authenticate("editor", "synthetic-test-password-12345")["token"]
        with self.assertRaises(PermissionError):
            self.host.list_users(user)
        # Ordinary coworker profile projections must not carry private opt-in
        # flags and grants to unrelated users.
        self.assertNotIn("internalNotificationsEnabled", self.host._public_user(record))
        self.assertNotIn("internalNotificationFields", self.host._public_user(record))

    def test_opt_in_narrows_role_ceiling_and_persists_after_restart(self):
        self.edit(internalNotificationsEnabled=True,
                  internalNotificationFields=["status", "actor_id"])
        account = self.host.users["editor"]
        self.assertTrue(account["internalNotificationsEnabled"])
        self.assertEqual(account["internalNotificationFields"], ["status", "actor_id"])
        self.assertEqual(json.loads(self.users_path.read_text(encoding="utf8"))
                         ["editor"]["internalNotificationFields"],
                         ["status", "actor_id"])
        reloaded = LanService(self.bridge, self.users_path, bind="127.0.0.1", port=0)
        self.assertTrue(reloaded.users["editor"]["internalNotificationsEnabled"])
        self.assertEqual(reloaded.users["editor"]["internalNotificationFields"],
                         ["status", "actor_id"])

    def test_role_downgrade_immediately_redacts_inherited_private_fields(self):
        self.edit(internalNotificationsEnabled=True,
                  internalNotificationFields=["status", "actor_id"])
        self.host.upsert_user(self.owner, {
            "username": "editor", "role": "viewer", "projects": ["project-one"],
        })
        updated = self.host.users["editor"]
        self.assertEqual(updated["role"], "viewer")
        self.assertEqual(updated["internalNotificationFields"], ["status"])
        self.assertTrue(updated["internalNotificationsEnabled"])

    def test_explicit_viewer_private_field_escalation_is_denied(self):
        self.edit()
        with self.assertRaises((PermissionError, ValueError)):
            self.host.upsert_user(self.owner, {
                "username": "editor", "role": "viewer",
                "projects": ["project-one"],
                "internalNotificationFields": ["status", "actor_id"],
            })
        self.assertEqual(self.host.users["editor"]["role"], "editor")
        self.assertIs(self.host.users["editor"]["internalNotificationsEnabled"], False)

    def test_malformed_boolean_field_duplicate_or_type_never_saved(self):
        self.edit()
        before = self.users_path.read_bytes()
        scenarios = (
            {"internalNotificationsEnabled": "yes"},
            {"internalNotificationFields": "status"},
            {"internalNotificationFields": ["status", "status"]},
            {"internalNotificationFields": ["status", 5]},
            {"internalNotificationFields": ["status", "untrusted_private"]},
        )
        for data in scenarios:
            with self.subTest(data=data), self.assertRaises((ValueError, PermissionError)):
                self.host.upsert_user(self.owner, {"username": "editor", **data})
            self.assertEqual(self.users_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
