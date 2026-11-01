"""Isolated real LAN-host user creation, authentication, and permission checks."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_app
from lan import LanService


class LanUserCreationFlowTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="madar-lan-create-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "host").mkdir()
        datadir_patch = patch.object(native_app, "datadir", return_value=self.root / "host")
        datadir_patch.start()
        self.addCleanup(datadir_patch.stop)
        self.host = native_app.Bridge()
        # This test explicitly grants a user access to p-sample. Real
        # customer first-run is intentionally empty; supply the historical
        # example project as a disposable fixture, not a production default.
        self.host.saveState(native_app.initial_state())
        self.service = LanService(
            self.host, self.root / "lan-users.json", bind="127.0.0.1", port=0
        )
        self.service.setup_owner("owner", "owner-password-2026")
        self.host.lan = self.service
        self.port = self.service.start()
        self.addCleanup(self.service.stop)
        self.client = native_app.Bridge()
        self.client.connection = {
            "mode": "client", "url": f"http://127.0.0.1:{self.port}"
        }
        self.client.remote_token = self.service.authenticate(
            "owner", "owner-password-2026"
        )["token"]

    def test_admin_creates_viewer_editor_and_both_can_sign_in(self):
        users = (
            ("worker-view", "viewer", "employee", []),
            ("worker-edit", "editor", "middle", ["p-sample"]),
        )
        for username, role, display_role, scope in users:
            # Match the ordinary (not customized) UI payload. Overrides are
            # intentionally omitted, so the host inherits the chosen template.
            account = self.client.lanSaveUser({
                "username": username, "password": "staff-password-2026",
                "role": role, "displayRole": display_role, "projects": scope,
                "displayName": "کاربر آزمایشی", "avatarIcon": "user",
                "avatarColor": "#5376b5", "avatarPhoto": "",
            })
            self.assertEqual((account["role"], account["displayRole"]),
                             (role, display_role))
            self.assertEqual(account["projects"], scope)
            self.assertEqual(self.service.authenticate(
                username, "staff-password-2026")["user"]["role"], role)

        names = {u["username"] for u in self.client.lanUsers()}
        self.assertEqual(names, {"owner", "worker-view", "worker-edit"})
        self.assertNotIn("passwordHash", self.client.lanUsers()[1])
        self.assertEqual(self.service.users["worker-view"]["displayRole"], "employee")
        self.assertNotIn("displayMode", self.service.users["worker-view"])
        self.assertNotIn("displayFeatures", self.service.users["worker-view"])

    def test_non_admin_and_solo_cannot_create_or_list_accounts(self):
        self.client.lanSaveUser({
            "username": "worker-edit", "password": "staff-password-2026",
            "role": "editor", "displayRole": "middle", "projects": None,
        })
        self.client.remote_token = self.service.authenticate(
            "worker-edit", "staff-password-2026"
        )["token"]
        with self.assertRaises(PermissionError):
            self.client.lanSaveUser({
                "username": "forbidden", "password": "staff-password-2026",
                "role": "admin", "displayRole": "superadmin", "projects": None,
            })
        with self.assertRaises(PermissionError):
            self.client.lanUsers()

        # No LAN server or authenticated remote session: no mock/fake account.
        solo = native_app.Bridge()
        with self.assertRaisesRegex(RuntimeError, "سرور دیگری"):
            solo.lanSaveUser({
                "username": "fake-user", "password": "staff-password-2026",
                "role": "viewer", "displayRole": "employee", "projects": None,
            })
        self.assertNotIn("fake-user", self.service.users)

    def test_customized_display_uses_valid_non_null_host_fields(self):
        new_user = self.client.lanSaveUser({
            "username": "specialist", "password": "staff-password-2026",
            "role": "editor", "displayRole": "middle", "projects": None,
            "displayMode": "basic", "displayFeatures": ["cards"],
        })
        self.assertEqual(new_user["displayMode"], "basic")
        self.assertEqual(new_user["displayFeatures"], ["cards"])
        with self.assertRaises(RuntimeError):
            self.client.lanSaveUser({
                "username": "rejected", "password": "staff-password-2026",
                "role": "viewer", "displayRole": "employee", "projects": None,
                "displayMode": None, "displayFeatures": None,
            })
        self.assertNotIn("rejected", self.service.users)

    def test_owner_native_bridge_saves_resets_and_deletes_user(self):
        saved = self.host.lanSaveUser({
            "username": "direct-owner-user",
            "password": "staff-password-2026",
            "role": "editor",
            "displayRole": "middle",
            "projects": ["p-sample"],
        })
        self.assertEqual(saved["role"], "editor")
        self.assertEqual(saved["projects"], ["p-sample"])
        self.assertTrue(any(u["username"] == "direct-owner-user"
                            for u in self.host.lanUsers()))
        self.host.lanResetPassword("direct-owner-user", "changed-password-2026")
        with self.assertRaises(PermissionError):
            self.service.authenticate("direct-owner-user", "staff-password-2026")
        self.assertEqual(
            self.service.authenticate("direct-owner-user", "changed-password-2026")["user"]["role"],
            "editor")
        self.assertTrue(self.host.lanDeleteUser("direct-owner-user"))
        self.assertFalse(any(u["username"] == "direct-owner-user"
                             for u in self.host.lanUsers()))


if __name__ == "__main__":
    unittest.main()
