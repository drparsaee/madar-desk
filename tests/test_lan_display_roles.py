"""Presentation role catalog, per-account constraints, and LAN authorization."""

import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lan import LanService
from role_profiles import DISPLAY_FEATURE_TIERS


class _DisposableBridge:
    def __init__(self):
        self._lock = threading.RLock()

    def getState(self):
        return {"projects": [], "tasks": []}


class DisplayRolesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="madar-display-roles-")
        self.addCleanup(self.folder.cleanup)
        self.users_file = Path(self.folder.name) / "lan-users.json"
        self.server = LanService(_DisposableBridge(), self.users_file, bind="127.0.0.1", port=0)
        self.server.setup_owner("owner", "owner-secure-123")
        self.base = f"http://127.0.0.1:{self.server.start()}"
        self.addCleanup(self.server.stop)
        self.admin = self.request("/api/login", {"username": "owner", "password": "owner-secure-123"})["token"]

    def request(self, path, payload=None, token=None, *, method=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf8")
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        with urlopen(Request(self.base + path, data=data, headers=headers,
                             method=method or ("POST" if data is not None else "GET")), timeout=8) as response:
            return json.loads(response.read())

    def assert_status(self, status, call):
        with self.assertRaises(HTTPError) as raised:
            call()
        self.assertEqual(raised.exception.code, status)

    def add_user(self, name, role="viewer", **presentation):
        return self.request("/api/user", {"username": name, "password": "long-password-123",
                                          "role": role, "projects": None, **presentation}, self.admin)["user"]

    def login(self, username):
        return self.request("/api/login", {"username": username, "password": "long-password-123"})

    def test_predefined_profiles_and_default_legacy_roles(self):
        roles = self.request("/api/display-roles", token=self.admin)["roles"]
        self.assertEqual([role["id"] for role in roles],
                         ["superadmin", "senior", "middle", "unit", "employee"])
        self.assertTrue(all(role["isBuiltin"] for role in roles))
        self.assert_status(400, lambda: self.request("/api/display-roles", {
            "id": "superadmin", "label": "مدیرکل", "displayMode": "basic",
            "features": ["cards"]}, self.admin))
        admin = self.request("/api/me", token=self.admin)["user"]
        self.assertEqual((admin["role"], admin["displayRole"], admin["displayMode"]),
                         ("admin", "superadmin", "finance"))
        self.assertEqual(set(admin["displayFeatures"]), set(DISPLAY_FEATURE_TIERS))
        self.assertEqual((self.add_user("staff")["displayRole"],
                          self.add_user("operator", "editor")["displayRole"]),
                         ("employee", "middle"))
        self.assertNotIn("passwordHash", self.request("/api/me", token=self.admin)["user"])

    def test_client_presentation_keys_match_server_allowlist(self):
        source = (Path(__file__).resolve().parent.parent / "src" / "interface_mode.js").read_text(encoding="utf8")
        config = source[source.index("INTERFACE_FEATURE_TIERS"):source.index("ADMIN_ONLY_FEATURES")]
        client = dict(re.findall(r"([A-Za-z][A-Za-z0-9]*):\s*'(basic|operations|finance)'", config))
        self.assertEqual(DISPLAY_FEATURE_TIERS, client)
        self.assertEqual(DISPLAY_FEATURE_TIERS["accountingDashboard"], "finance")

    def test_builtin_catalog_is_restored_on_reload_after_feature_updates(self):
        roles = self.server.list_display_roles(self.admin)
        record = [{k: value for k, value in entry.items() if k != "isBuiltin"} for entry in roles]
        record[0]["features"] = []
        self.server.display_roles_path.write_text(json.dumps({"version": 1, "roles": record}), encoding="utf8")
        restored = LanService(_DisposableBridge(), self.users_file, bind="127.0.0.1", port=0)
        self.assertEqual(set(restored.display_roles["superadmin"]["features"]),
                         set(DISPLAY_FEATURE_TIERS))

    def test_role_catalog_management_and_restart_persistence(self):
        role = {"id": "account-lead", "label": "سرپرست حسابداری", "displayMode": "operations",
                "features": ["cards", "planner", "activity"]}
        saved = self.request("/api/display-roles", role, self.admin)["role"]
        self.assertEqual(saved["label"], "سرپرست حسابداری")
        self.assertFalse(saved["isBuiltin"])
        self.assertEqual(set(saved["features"]), set(role["features"]))
        person = self.add_user("reader", displayRole=role["id"], displayFeatures=["cards"])
        self.assertEqual(person["displayFeatures"], ["cards"])
        self.assertEqual(person["role"], "viewer")
        self.assert_status(400, lambda: self.request("/api/display-roles?id=account-lead",
                                                      token=self.admin, method="DELETE"))
        self.assertTrue(self.server.display_roles_path.exists())
        # Reopen the catalog and accounts without touching any live user data.
        restored = LanService(_DisposableBridge(), self.users_file, bind="127.0.0.1", port=0)
        self.assertEqual(restored.display_roles[role["id"]]["label"], role["label"])
        self.assertEqual(restored.users["reader"]["displayRole"], role["id"])
        self.assertEqual(restored._public_user(restored.users["reader"])["displayFeatures"], ["cards"])
        self.request("/api/user", {"username": "reader", "password": "", "role": "viewer",
                                   "projects": None, "displayRole": "employee"}, self.admin)
        self.assertTrue(self.request("/api/display-roles", {"action": "delete", "id": role["id"]},
                                     self.admin)["ok"])
        self.assertNotIn(role["id"], self.server.display_roles)
        self.assert_status(400, lambda: self.request("/api/display-roles?id=employee",
                                                      token=self.admin, method="DELETE"))

    def test_updates_refresh_active_sessions_without_relogin(self):
        self.add_user("worker")
        session = self.login("worker")["token"]
        self.assertEqual(self.request("/api/me", token=session)["user"]["displayMode"], "basic")
        self.request("/api/user", {"username": "worker", "role": "viewer", "projects": None,
                                   "displayRole": "unit", "displayMode": "operations",
                                   "displayFeatures": ["cards", "planner"]}, self.admin)
        user = self.request("/api/me", token=session)["user"]
        self.assertEqual(user["displayRole"], "unit")
        self.assertEqual(user["displayFeatures"], ["cards", "planner"])
        self.assertEqual(user["role"], "viewer")
        self.assert_status(403, lambda: self.request("/api/users", token=session))
        self.assert_status(403, lambda: self.request("/api/display-roles", token=session))
        self.assert_status(403, lambda: self.request("/api/display-roles", {
            "id": "test", "label": "fake", "displayMode": "basic", "features": []}, session))
        self.assert_status(403, lambda: self.request("/api/display-roles", {"invalid": 1}, session))
        self.assert_status(403, lambda: self.request("/api/display-roles", {
            "action": "delete", "id": "unit"}, session))
        self.assert_status(403, lambda: self.request("/api/profile", {
            "displayRole": "senior"}, session))
        self.assert_status(403, lambda: self.request("/api/me"))

    def test_invalid_ids_features_modes_and_user_overrides_rejected(self):
        valid = {"id": "custom-manager", "label": "مدیر عملیات", "displayMode": "operations",
                 "features": ["cards", "planner"]}
        for invalid in (
            {**valid, "id": "../outside"}, {**valid, "id": "ADMIN"},
            {**valid, "label": "\n"}, {**valid, "features": ["passwordHash"]},
            {**valid, "features": ["cards", "cards"]},
            {**valid, "features": ["cards", {}]},
            {**valid, "features": ["projectFinance"]},
            {**valid, "displayMode": "master"},
            {**valid, "isAdmin": True},
        ):
            with self.subTest(invalid=invalid):
                self.assert_status(400, lambda: self.request("/api/display-roles", invalid, self.admin))
        self.assert_status(400, lambda: self.request("/api/user", {
            "username": "bad", "role": "viewer", "password": "long-password-123",
            "displayRole": "nonexistent"}, self.admin))
        self.assert_status(400, lambda: self.request("/api/user", {
            "username": "bad", "role": "viewer", "password": "long-password-123",
            "displayRole": "superadmin"}, self.admin))
        self.assert_status(400, lambda: self.request("/api/user", {
            "username": "bad", "role": "admin", "projects": None,
            "password": "long-password-123", "displayRole": "employee"}, self.admin))
        self.assert_status(400, lambda: self.request("/api/user", {
            "username": "bad", "role": "viewer", "password": "long-password-123",
            "displayRole": "employee", "displayMode": "finance"}, self.admin))
        self.assert_status(400, lambda: self.request("/api/user", {
            "username": "bad", "role": "viewer", "password": "long-password-123",
            "displayRole": "employee", "displayFeatures": ["profitPeek"]}, self.admin))
        self.assertNotIn("bad", self.server.users)

    def test_role_edits_reduce_effective_features_and_never_raise_acl(self):
        custom = {"id": "custom-manager", "label": "نمای مدیر", "displayMode": "finance",
                  "features": ["cards", "planner", "projectFinance"]}
        self.request("/api/display-roles", custom, self.admin)
        account = self.add_user("reader", "viewer", displayRole="custom-manager",
                                displayFeatures=["cards", "projectFinance"])
        self.assertIn("projectFinance", account["displayFeatures"])
        viewer_token = self.login("reader")["token"]
        self.assert_status(403, lambda: self.request("/api/finance-overview", token=viewer_token))
        self.request("/api/display-roles", {**custom, "displayMode": "basic",
                                             "features": ["cards"]}, self.admin)
        updated = self.request("/api/me", token=viewer_token)["user"]
        self.assertEqual(updated["displayMode"], "basic")
        self.assertEqual(updated["displayFeatures"], ["cards"])
        self.assertEqual(updated["role"], "viewer")
        self.assert_status(403, lambda: self.request("/api/users", token=viewer_token))

    def test_stale_account_overrides_are_clamped_only_when_omitted(self):
        custom = {"id": "custom-manager", "label": "نمای مدیر", "displayMode": "finance",
                  "features": ["cards", "planner", "projectFinance"]}
        self.request("/api/display-roles", custom, self.admin)
        self.add_user("reader", "viewer", displayRole="custom-manager",
                      displayMode="finance", displayFeatures=["cards", "planner", "projectFinance"])
        token = self.login("reader")["token"]
        self.request("/api/display-roles", {**custom, "displayMode": "basic",
                                             "features": ["cards"]}, self.admin)
        self.assertEqual(self.request("/api/me", token=token)["user"]["displayFeatures"], ["cards"])

        # A normal profile edit must not fail because the old overrides were
        # granted when the custom role included more presentation features.
        ordinary = {"username": "reader", "role": "viewer", "projects": None,
                    "password": "", "displayName": "کارمند فروش"}
        result = self.request("/api/user", ordinary, self.admin)["user"]
        self.assertEqual((result["displayMode"], result["displayFeatures"]),
                         ("basic", ["cards"]))
        self.assertEqual(result["displayName"], "کارمند فروش")
        self.assertNotIn("displayMode", self.server.users["reader"])
        self.assertEqual(self.server.users["reader"]["displayFeatures"], ["cards"])

        # When present in the payload, out-of-tier overrides remain errors.
        for explicit in ({"displayMode": "finance"},
                         {"displayMode": None},
                         {"displayFeatures": ["planner"]},
                         {"displayFeatures": None}):
            with self.subTest(explicit=explicit):
                self.assert_status(400, lambda: self.request("/api/user", {
                    **ordinary, **explicit}, self.admin))
        self.assertEqual(self.server.users["reader"]["displayFeatures"], ["cards"])

        # An explicit valid mode does not force a caller to resubmit the old,
        # now stale feature override. A valid explicit feature list also works.
        self.request("/api/user", {**ordinary, "displayMode": "basic",
                                   "displayFeatures": ["cards"]}, self.admin)
        self.assertEqual(self.request("/api/me", token=token)["user"]["role"], "viewer")


if __name__ == "__main__":
    unittest.main()
