import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_app
from lan import LanService


def sale():
    return {"customer": {"name": "Sample Customer", "reference": ""},
            "lines": [{"id": "service", "description": "Approved design",
                       "quantity": 1, "unitPrice": 120000}],
            "discount": 0, "tax": 0, "advance": 0, "autoInvoice": True}


class FinanceBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patch = patch.object(native_app, "datadir", return_value=self.root)
        self.patch.start()
        self.bridge = native_app.Bridge()
        # This legacy contract refers to example-2/p-sample; populate only
        # the synthetic test root rather than changing the real first-run.
        self.bridge.saveState(native_app.initial_state())

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_completed_card_makes_one_draft_after_explicit_contract(self):
        self.bridge.financeCommand({"type": "contract.set", "eventId": "setup1",
                                    "cardId": "example-2", "sale": sale()})
        before = self.bridge.getState()
        card = next(x for x in before["tasks"] if x["id"] == "example-2")
        card["status"] = "done"
        card["listId"] = "done"
        self.bridge.saveState(before)
        invoices = self.bridge.financeRead("p-sample")
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices[0]["status"], "Draft")
        self.assertEqual(invoices[0]["sale"]["total"], 120000)
        self.assertEqual(self.bridge.financeStatus()["pending"], 0)
        self.bridge.saveState(self.bridge.getState())
        self.assertEqual(len(self.bridge.financeRead("p-sample")), 1)
        restarted = native_app.Bridge()
        self.assertEqual(len(restarted.financeRead("p-sample")), 1)
        self.assertEqual(len(restarted._load_finance()["completionIds"]), 1)

    def test_without_contract_there_is_no_invented_invoice(self):
        data = self.bridge.getState()
        card = next(x for x in data["tasks"] if x["id"] == "example-2")
        card["status"] = "done"
        card["listId"] = "done"
        self.bridge.saveState(data)
        self.assertEqual(self.bridge.financeRead("p-sample"), [])

    def test_lan_editor_completion_is_authorized_but_finance_remains_admin_only(self):
        server = LanService(self.bridge, self.root / "users.json", bind="127.0.0.1", port=0)
        server.setup_owner("admin", "very-strong-password")
        admin = server.authenticate("admin", "very-strong-password")["token"]
        server.upsert_user(admin, {"username": "editor", "password": "strong-editor-password",
                                   "role": "editor", "projects": ["p-sample"]})
        editor = server.authenticate("editor", "strong-editor-password")["token"]
        server.finance_command(admin, {"type": "contract.set", "eventId": "sale1",
                                       "cardId": "example-2", "sale": sale()})
        view = server.read_state(editor)
        row = next(x for x in view["state"]["tasks"] if x["id"] == "example-2")
        row["status"] = "done"
        row["listId"] = "done"
        server.write_state(editor, view["state"], view["revision"])
        self.assertEqual(len(server.finance_read(admin, "p-sample")), 1)
        self.assertEqual(self.bridge._load_finance()["invoices"][0]["createdBy"], "editor")
        with self.assertRaises(PermissionError):
            server.finance_read(editor, "p-sample")
        with self.assertRaises(PermissionError):
            server.finance_command(editor, {"type": "invoice.issue", "eventId": "fake",
                                            "invoiceId": self.bridge._load_finance()["invoices"][0]["id"]})
        with self.assertRaises(ValueError):
            server.finance_command(admin, {"type": "completion.record", "eventId": "fake",
                                           "cardId": "example-1", "completionId": "forged"})


if __name__ == "__main__":
    unittest.main()
