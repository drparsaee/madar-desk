"""Synthetic API regression tests for LAN grants and commercial task fields."""
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import native_app
from lan import LanService


class TaskAccountingLanSecurity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-task-finance-acl-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        mocked = patch.object(native_app, "datadir", return_value=self.root)
        mocked.start()
        self.addCleanup(mocked.stop)
        self.bridge = native_app.Bridge()
        self.lan = LanService(self.bridge, self.root / "lan-users.json",
                              bind="127.0.0.1", port=0)
        self.lan.setup_owner("owner", "owner-password-123")
        self.owner = self.lan.authenticate("owner", "owner-password-123")["token"]

    def register(self, name, role="editor", **grants):
        return self.lan.upsert_user(self.owner, {
            "username": name, "password": "synthetic-password-123",
            "role": role, "projects": ["p-sample"], **grants,
        })

    def test_admin_grants_are_persisted_and_revoked_without_password_rotation(self):
        registered = self.register("accountant", financeView=True, financeEdit=True)
        self.assertTrue(registered["financeEdit"])
        token = self.lan.authenticate("accountant", "synthetic-password-123")["token"]
        self.assertEqual(self.lan.standalone_accounting_read(token)["revision"], 0)
        self.lan.upsert_user(self.owner, {"username": "accountant", "password": "",
                                          "role": "editor", "projects": ["p-sample"],
                                          "financeEdit": False, "financeView": False})
        with self.assertRaises(PermissionError):
            self.lan.standalone_accounting_read(token)
        reopened = LanService(self.bridge, self.root / "lan-users.json")
        self.assertIs(reopened.users["accountant"]["financeEdit"], False)
        self.assertIs(reopened.users["accountant"]["financeView"], False)

    def test_viewer_finance_read_can_be_granted_but_never_write(self):
        viewer = self.register("reader", role="viewer", financeView=True)
        self.assertTrue(viewer["financeView"])
        self.assertFalse(viewer["financeEdit"])
        token = self.lan.authenticate("reader", "synthetic-password-123")["token"]
        self.assertEqual(self.lan.standalone_accounting_read(token)["revision"], 0)
        with self.assertRaises(PermissionError):
            self.lan.standalone_accounting_command(
                token, {"expectedRevision": 0, "command": {}})
        for invalid in (True, 1, "true"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.lan.upsert_user(self.owner, {"username": "reader", "password": "",
                                                  "role": "viewer", "projects": ["p-sample"],
                                                  "financeEdit": invalid})
        self.assertFalse(self.lan.users["reader"]["financeEdit"])

    def test_explicit_finance_writer_grant_implies_read_without_task_access(self):
        self.register("finance-writer", financeView=False, financeEdit=True)
        token = self.lan.authenticate("finance-writer",
                                      "synthetic-password-123")["token"]
        result = self.lan.standalone_accounting_read(token)
        self.assertEqual(result["revision"], 0)
        self.assertTrue(result["capabilities"]["canManage"])
        self.assertFalse(result["capabilities"]["canAdmin"])
        self.lan.upsert_user(self.owner, {
            "username": "finance-writer", "password": "",
            "role": "editor", "projects": ["p-sample"],
            "financeEdit": False, "financeView": False})
        with self.assertRaises(PermissionError):
            self.lan.standalone_accounting_read(token)

    def test_editor_cannot_change_saved_sale_quantity_used_by_prepare(self):
        self.register("worker")
        worker = self.lan.authenticate("worker", "synthetic-password-123")["token"]
        state = self.bridge.getState()
        card = next(t for t in state["tasks"] if t["projectId"] == "p-sample")
        card.update({"saleQuantity": 100, "saleUnitPrice": 20000,
                     "saleCurrency": "TOMAN", "salePartyId": "customer"})
        self.bridge.saveState(state)
        initial = self.lan.read_state(worker)
        exposed = initial["state"]["tasks"][0]
        self.assertEqual((exposed["saleQuantity"], exposed["saleUnitPrice"]), (1, 0))
        changed = deepcopy(initial["state"])
        changed["tasks"][0]["saleQuantity"] = 200
        with self.assertRaises(PermissionError):
            self.lan.write_state(worker, changed, initial["revision"])
        changed = deepcopy(initial["state"])
        changed["tasks"][0]["title"] = "Revised non-financial title"
        self.lan.write_state(worker, changed, initial["revision"])
        authoritative = next(t for t in self.bridge.getState()["tasks"]
                             if t["id"] == card["id"])
        self.assertEqual((authoritative["saleQuantity"], authoritative["saleUnitPrice"]),
                         (100, 20000))


if __name__ == "__main__":
    unittest.main()
