"""Synthetic LAN account lineage persistence and E2 identity boundary.

No host service listener, installed profile, network or official ledger.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import native_app
from lan import LanService
from mtr_account_lineage import AccountLineageError
from mtr_host_request_store import HostRequestStore
from mtr_lan_finance_adapter import MtrLanFinanceAdapter


PASSWORD = "synthetic-owner-secret-123"
NEW_PASSWORD = "synthetic-user-new-secret-456"


class AccountLineageLanIntegrationTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory(prefix="mtr-lineage-host-synthetic-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        with patch.object(native_app, "datadir", return_value=self.root):
            self.bridge = native_app.Bridge()
            self.bridge.saveState(native_app.initial_state())
        self.users_path = self.root / "private-users.json"
        self.host = LanService(self.bridge, self.users_path)
        self.host.setup_owner("owner", PASSWORD)
        self.admin = self.host.authenticate("owner", PASSWORD)["token"]
        self._create_editor()

    def _create_editor(self, *, password=PASSWORD):
        self.host.upsert_user(self.admin, {
            "username": "editor", "password": password, "role": "editor",
            "projects": ["p-sample"], "financeEdit": True,
        })

    def _actor(self, token):
        return MtrLanFinanceAdapter(
            self.host, HostRequestStore(self.root / "synthetic-host-requests.sqlite3"),
            org_id="synthetic-org",
        )._recovery_principal(token).user_id

    def test_password_rotation_and_host_restart_preserve_private_generation(self):
        first = self.host.authenticate("editor", PASSWORD)["token"]
        old = self._actor(first)
        private_lineage = self.host.users["editor"]["accountLineage"]
        self.assertEqual(len(private_lineage), 32)
        self.assertNotIn("accountLineage", self.host.list_users(self.admin)[1])
        self.assertNotIn("accountLineage", self.host.read_state(first)["user"])
        self.host.upsert_user(self.admin, {
            "username": "editor", "password": NEW_PASSWORD,
        })
        self.assertEqual(self.host.users["editor"]["accountLineage"], private_lineage)
        relogin = self.host.authenticate("editor", NEW_PASSWORD)["token"]
        self.assertEqual(self._actor(relogin), old)
        self.host = LanService(self.bridge, self.users_path)
        restarted = self.host.authenticate("editor", NEW_PASSWORD)["token"]
        self.assertEqual(self._actor(restarted), old)

    def test_deletion_and_recreation_same_username_changes_actor_generation(self):
        first = self.host.authenticate("editor", PASSWORD)["token"]
        old = self._actor(first)
        self.host.delete_user(self.admin, "editor")
        self._create_editor()
        new_token = self.host.authenticate("editor", PASSWORD)["token"]
        self.assertNotEqual(self._actor(new_token), old)

    def test_browser_cannot_override_lineage_and_legacy_missing_lineage_denied(self):
        with self.assertRaisesRegex(ValueError, "lineage"):
            self.host.upsert_user(self.admin, {
                "username": "editor", "accountLineage": "a" * 32,
            })
        current = dict(self.host.users["editor"])
        current.pop("accountLineage")
        self.host._publish_users({**self.host.users, "editor": current})
        token = self.host.authenticate("editor", PASSWORD)["token"]
        with self.assertRaises(AccountLineageError):
            self._actor(token)

    def test_duplicate_private_lineage_does_not_allow_another_account_to_inherit_actor(self):
        editor_token = self.host.authenticate("editor", PASSWORD)["token"]
        old_actor = self._actor(editor_token)
        duplicate = dict(self.host.users["owner"])
        duplicate["accountLineage"] = self.host.users["editor"]["accountLineage"]
        self.host._publish_users({**self.host.users, "owner": duplicate})
        with self.assertRaises(PermissionError):
            self._actor(editor_token)
        # Even the attacker who copied the other user's lineage should not
        # impersonate the historical actor through another private account.
        with self.assertRaises(PermissionError):
            self._actor(self.admin)
        self.assertTrue(old_actor.startswith("mtr-actor-v1-"))


if __name__ == "__main__":
    unittest.main()
