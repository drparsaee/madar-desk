"""Synthetic LAN coworker directory: no project means no coworker visibility."""

import tempfile
import unittest
from pathlib import Path
from threading import RLock

from lan import LanService


class SyntheticBridge:
    def __init__(self):
        self._lock = RLock()

    def getState(self):
        return {"projects": [{"id": "synthetic-project"}], "tasks": []}


class LanProfileZeroGrantDirectoryTests(unittest.TestCase):
    def test_unrestricted_non_admin_cannot_enumerate_zero_grant_coworker(self):
        with tempfile.TemporaryDirectory(prefix="madar-directory-synthetic-") as folder:
            service = LanService(SyntheticBridge(), Path(folder) / "users.json",
                                 bind="127.0.0.1", port=0)
            service.setup_owner("synthetic-admin", "synthetic-owner-password")
            admin = service.authenticate_owner_token()
            for username, projects in (("unrestricted", None),
                                       ("zero-grants", []),
                                       ("scoped", ["synthetic-project"])):
                service.upsert_user(admin, {
                    "username": username, "password": "synthetic-user-password",
                    "role": "viewer", "projects": projects,
                })
            unrestricted = service.authenticate(
                "unrestricted", "synthetic-user-password")["token"]
            zero = service.authenticate("zero-grants", "synthetic-user-password")["token"]

            visible = {u["username"] for u in service.list_profiles(unrestricted)}
            self.assertIn("unrestricted", visible)
            self.assertIn("scoped", visible)
            self.assertIn("synthetic-admin", visible)
            self.assertNotIn("zero-grants", visible)

            self.assertEqual([u["username"] for u in service.list_profiles(zero)],
                             ["zero-grants"])
            self.assertIn("zero-grants", {u["username"]
                                         for u in service.list_profiles(admin)})


if __name__ == "__main__":
    unittest.main()
