"""Synthetic regression: omitted account fields must not widen LAN grants."""

import tempfile
import threading
import unittest
from pathlib import Path

from lan import LanService


class _Bridge:
    def __init__(self):
        self._lock = threading.RLock()

    def getState(self):
        return {"projects": [{"id": "synthetic-project"}], "tasks": []}


class PartialAccountUpdateScopeTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="madar-synthetic-partial-user-")
        self.addCleanup(scratch.cleanup)
        self.registry = Path(scratch.name) / "users.json"
        self.service = LanService(_Bridge(), self.registry)
        self.service.setup_owner("admin", "synthetic-owner-password")
        self.admin = self.service.authenticate("admin", "synthetic-owner-password")["token"]
        self.service.upsert_user(self.admin, {
            "username": "scoped", "password": "synthetic-worker-password",
            "role": "editor", "projects": ["synthetic-project"],
            "financeView": True,
        })

    def test_profile_only_admin_update_preserves_existing_role_and_project_grants(self):
        self.service.upsert_user(self.admin, {
            "username": "scoped", "displayName": "Synthetic Worker"})
        current = self.service.users["scoped"]
        self.assertEqual(current["role"], "editor")
        self.assertEqual(current["projects"], ["synthetic-project"])
        self.assertTrue(current["financeView"])
        self.assertEqual(current["displayName"], "Synthetic Worker")
        reloaded = LanService(_Bridge(), self.registry).users["scoped"]
        self.assertEqual(reloaded["projects"], ["synthetic-project"])
        self.assertEqual(reloaded["role"], "editor")

    def test_password_only_admin_update_does_not_make_scoped_user_unrestricted(self):
        self.service.upsert_user(self.admin, {
            "username": "scoped", "password": "synthetic-new-worker-password"})
        self.assertEqual(self.service.users["scoped"]["projects"], ["synthetic-project"])
        self.assertEqual(self.service.users["scoped"]["role"], "editor")
        self.assertEqual(
            self.service.authenticate("scoped", "synthetic-new-worker-password")["user"]["projects"],
            ["synthetic-project"],
        )

    def test_explicit_unrestricted_scope_still_requires_explicit_none(self):
        self.service.upsert_user(self.admin, {"username": "scoped", "projects": None})
        self.assertIsNone(self.service.users["scoped"]["projects"])
        self.assertEqual(self.service.users["scoped"]["role"], "editor")

    def test_explicit_admin_promotion_keeps_existing_unrestricted_admin_contract(self):
        self.service.upsert_user(self.admin, {"username": "scoped", "role": "admin"})
        self.assertEqual(self.service.users["scoped"]["role"], "admin")
        self.assertIsNone(self.service.users["scoped"]["projects"])

    def test_invalid_explicit_scope_rejected_without_registry_change(self):
        before = self.registry.read_bytes()
        with self.assertRaises(ValueError):
            self.service.upsert_user(self.admin, {
                "username": "scoped", "projects": ["synthetic-project", "synthetic-project"]})
        self.assertEqual(self.registry.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
