"""LAN role/profile authorization and explicit workplace-avatar selection."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import native_app
from lan import LanService, clean_profile


class RoleProfilesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="madar-role-profiles-")
        self.root = Path(self.temporary.name)
        self.datadir_patch = patch.object(native_app, "datadir", return_value=self.root)
        self.datadir_patch.start()
        self.bridge = native_app.Bridge()
        self.service = LanService(self.bridge, self.root / "accounts.json", "127.0.0.1", 0)
        self.service.setup_owner("admin", "server-owner-123")
        self.base = f"http://127.0.0.1:{self.service.start()}"
        self.admin = self.request("/api/login", {
            "username": "admin", "password": "server-owner-123"})["token"]

    def tearDown(self):
        try:
            self.service.stop()
        finally:
            self.datadir_patch.stop()
            self.temporary.cleanup()

    def request(self, endpoint, payload=None, token=None):
        kwargs = {"headers": {"Content-Type": "application/json"}}
        if token:
            kwargs["headers"]["Authorization"] = "Bearer " + token
        if payload is not None:
            kwargs["data"] = json.dumps(payload, ensure_ascii=False).encode("utf8")
        with urlopen(Request(self.base + endpoint, **kwargs), timeout=10) as result:
            return json.loads(result.read())

    def status(self, code, callback):
        with self.assertRaises(HTTPError) as outcome:
            callback()
        self.assertEqual(outcome.exception.code, code)

    def create(self, username, role, projects=None, **profile):
        self.request("/api/user", {
            "username": username, "password": "worker-password-123",
            "role": role, "projects": projects, **profile}, self.admin)
        return self.request("/api/login", {
            "username": username, "password": "worker-password-123"})["token"]

    def test_admin_can_create_scoped_accounts_with_explicit_function_and_color(self):
        token = self.create("designer", "editor", ["p-sample"],
                            displayName="طراح بسته‌بندی",
                            avatarIcon="palette", avatarColor="#ab12cd")
        account = self.request("/api/state", token=token)["user"]
        self.assertEqual(account["role"], "editor")
        self.assertEqual(account["projects"], ["p-sample"])
        self.assertEqual(account["avatarColor"], "#ab12cd")
        self.assertEqual(account["avatarIcon"], "palette")
        self.assertNotIn("passwordHash", account)
        self.assertNotIn("passwordHash", self.request("/api/users", token=self.admin)["users"][1])

    def test_editor_and_viewer_cannot_manage_accounts_or_promote_them(self):
        tokens = [self.create("editor", "editor", ["p-sample"]),
                  self.create("viewer", "viewer", ["p-sample"])]
        for token in tokens:
            with self.subTest(token=token[:6]):
                self.status(403, lambda: self.request("/api/users", token=token))
                self.status(403, lambda: self.request("/api/user", {
                    "username": "intruder", "password": "intruder-password",
                    "role": "admin"}, token))
                self.status(403, lambda: self.request("/api/user", {
                    "username": "editor", "role": "admin", "projects": None}, token))
                self.status(403, lambda: self.request("/api/users", {
                    "username": "admin"}, token))
                self.status(403, lambda: self.request("/api/reset-password", {
                    "username": "admin", "newPassword": "unauthorized-123"}, token))
        self.assertNotIn("intruder", self.service.users)
        self.assertEqual(self.service.users["editor"]["role"], "editor")

    def test_self_profile_blocks_role_scope_and_identity_injection(self):
        editor = self.create("worker", "editor", ["p-sample"])
        for name, value in (
                ("role", "admin"), ("projects", None), ("username", "admin"),
                ("passwordHash", "injected"), ("isAdmin", True)):
            with self.subTest(field=name):
                self.status(403, lambda: self.request("/api/profile", {
                    "displayName": "safe", name: value}, editor))
        after = self.request("/api/state", token=editor)["user"]
        self.assertEqual(after["role"], "editor")
        self.assertEqual(after["projects"], ["p-sample"])
        self.assertEqual(after["displayName"], "")

    def test_users_with_disjoint_or_zero_project_scope_do_not_see_other_profiles(self):
        narrow = self.create("onlysample", "viewer", ["p-sample"])
        other = self.create("onlypersonal", "editor", ["p-personal"])
        empty = self.create("noaccess", "viewer", [])
        sample = self.request("/api/profiles", token=narrow)["users"]
        self.assertNotIn("onlypersonal", [u["username"] for u in sample])
        self.assertNotIn("noaccess", [u["username"] for u in sample])
        self.assertIn("admin", [u["username"] for u in sample])
        self.assertEqual(next(u for u in sample if u["username"] == "admin")["projects"], ["p-sample"])
        other_users = [u["username"] for u in self.request("/api/profiles", token=other)["users"]]
        self.assertNotIn("onlysample", other_users)
        empty_users = self.request("/api/profiles", token=empty)["users"]
        self.assertEqual([u["username"] for u in empty_users], ["noaccess"])
        for entry in sample + empty_users:
            self.assertNotIn("passwordHash", entry)

    def test_admin_cannot_claim_a_scoped_admin_role(self):
        self.status(400, lambda: self.request("/api/user", {
            "username": "scopedadmin", "password": "new-owner-123",
            "role": "admin", "projects": ["p-sample"]}, self.admin))
        self.status(400, lambda: self.request("/api/user", {
            "username": "scopedadmin", "password": "new-owner-123",
            "role": ["admin"], "projects": None}, self.admin))
        self.assertNotIn("scopedadmin", self.service.users)

    def test_self_service_avatar_changes_do_not_change_permissions(self):
        viewer = self.create("factoryworker", "viewer", ["p-sample"])
        updated = self.request("/api/profile", {
            "displayName": "کارگاه", "avatarIcon": "production",
            "avatarColor": "#fF3300", "avatarPhoto": ""}, viewer)["user"]
        self.assertEqual(updated["avatarIcon"], "production")
        self.assertEqual(updated["avatarColor"], "#ff3300")
        self.assertEqual(updated["role"], "viewer")
        self.assertEqual(updated["projects"], ["p-sample"])
        saved = self.request("/api/login", {
            "username": "factoryworker", "password": "worker-password-123"})["user"]
        self.assertEqual(saved["avatarColor"], "#ff3300")

    def test_invalid_profile_values_are_rejected_without_modifying_account(self):
        token = self.create("staffer", "editor", ["p-sample"])
        before = dict(self.service.users["staffer"])
        for invalid in (
                {"avatarIcon": ["finance"]}, {"avatarColor": "red"},
                {"avatarColor": "#11223z"}, {"avatarColor": ["#112233"]},
                {"avatarIcon": "imaginary"}):
            with self.subTest(invalid=invalid):
                self.status(400, lambda: self.request("/api/profile", invalid, token))
        self.assertEqual(before, self.service.users["staffer"])
        self.assertEqual(clean_profile({})["avatarColor"], "#5376b5")

    def test_admin_update_preserves_profile_on_role_edit_and_restricts_projects(self):
        token = self.create("helper", "viewer", ["p-sample"],
                            avatarIcon="support", avatarColor="#112233")
        self.request("/api/user", {
            "username": "helper", "password": "", "role": "editor",
            "projects": ["p-personal"]}, self.admin)
        profile = self.request("/api/state", token=token)["user"]
        self.assertEqual(profile["role"], "editor")
        self.assertEqual(profile["projects"], ["p-personal"])
        self.assertEqual(profile["avatarIcon"], "support")
        self.assertEqual(profile["avatarColor"], "#112233")


if __name__ == "__main__":
    unittest.main()
