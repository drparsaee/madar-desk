"""Madar accounting integration: task sales, purchase expenses, balanced AR/AP.

All inputs are synthetic; no real APPDATA or user accounting is loaded.
"""
from copy import deepcopy
import json
import unittest

import finance
from accounting_service import (apply_madar_accounting, read_madar_accounting,
                                validate_accounting_extension)


NOW = "2026-10-21T13:30:00+00:00"
DAY = "2026-10-21"
ACCOUNTS = {"admin": {"username": "admin", "role": "admin", "projects": None},
            "editor": {"username": "editor", "role": "editor", "projects": ["p1"]},
            "viewer": {"username": "viewer", "role": "viewer", "projects": ["p1"]}}
PROJECTS = [{"id": "p1", "name": "Printing", "costEnabled": True},
            {"id": "p2", "name": "Other", "costEnabled": False}]
TASKS = [{"id": "task-1", "projectId": "p1", "title": "Printing task", "cost": 500,
          "costEnabled": True, "checklist": [{"id": "c1", "text": "Paper", "cost": 150}]},
         {"id": "task-2", "projectId": "p2", "title": "Other", "cost": 999,
          "checklist": []}]
CUSTOMER = {"id": "person-ali", "name": "Ali Rezaei", "reference": "", "kind": "customer"}
VENDOR = {"id": "vendor-paper", "name": "Paper Supplier", "reference": "", "kind": "supplier"}


def sales_command(event_id="sales1"):
    return {"type": "draft.sales.fromTask", "eventId": event_id, "projectId": "p1",
            "cardId": "task-1", "party": CUSTOMER,
            "lines": [{"id": "service", "description": "Service invoice", "quantity": 2,
                       "unitPrice": 1000}],
            "discount": 100, "tax": 50, "advance": 300}


def purchase_command(event_id="purchase1", basis="actual", approve=False):
    return {"type": "draft.purchase.fromCosts", "eventId": event_id, "projectId": "p1",
            "party": VENDOR, "selections": [{"cardId": "task-1", "sourceId": "direct"}],
            "basis": basis, "approveEstimate": approve}


class AccountingServiceTests(unittest.TestCase):
    def setUp(self):
        self.finance = finance.empty_finance_state()
        self.finance["cardCosts"]["task-1"] = {
            "cardId": "task-1", "costEnabled": True,
            "estimatedDirect": 500, "actualDirect": 450, "items": []}
        self.assertTrue(finance.validate_finance_state(self.finance))

    def do(self, cmd, actor="admin"):
        output = apply_madar_accounting(self.finance, cmd, actor=actor,
                                        accounts=ACCOUNTS, cards=TASKS,
                                        projects=PROJECTS, now=NOW)
        self.finance = output["state"]
        return output

    def view(self, project="p1"):
        return read_madar_accounting(self.finance, actor="admin", accounts=ACCOUNTS,
                                    project_id=project)

    def test_legacy_finance_without_accounting_extensions_stays_valid(self):
        before = deepcopy(self.finance)
        self.assertTrue(validate_accounting_extension(self.finance))
        self.assertEqual(before, self.finance)
        self.assertNotIn("accounting", self.finance)

    def test_task_sale_to_named_person_and_receivable_from_posted_invoice(self):
        created = self.do(sales_command())
        self.assertEqual(created["result"]["total"], 1950)
        self.assertTrue(created["changed"])
        self.assertEqual(self.view()["documents"][0]["status"], "Draft")
        self.assertEqual(self.view()["balances"][0]["receivable"], 0)
        inv_id = created["result"]["documentId"]
        self.do({"type": "document.review", "eventId": "review1",
                 "projectId": "p1", "documentId": inv_id})
        self.do({"type": "document.issue", "eventId": "issue1",
                 "projectId": "p1", "documentId": inv_id, "postingDate": DAY})
        data = self.view()
        self.assertEqual(data["documents"][0]["party"]["name"], "Ali Rezaei")
        self.assertEqual(data["documents"][0]["status"], "Issued")
        self.assertEqual(data["balances"][0]["receivable"], 1950)
        # The sale 'advance: 300' declaration did not fabricate a cash deposit.
        self.assertEqual(data["trialBalance"]["1000"]["normalBalance"], 0)
        self.assertEqual(data["trialBalance"]["1200"]["normalBalance"], 1950)

    def test_purchase_supplier_debt_partial_payment_and_trial_balance(self):
        created = self.do(purchase_command())
        bill = created["result"]["documentId"]
        self.assertEqual(self.view()["documents"][0]["total"], 450)
        self.do({"type": "document.review", "eventId": "rv2",
                 "projectId": "p1", "documentId": bill})
        self.do({"type": "document.issue", "eventId": "is2",
                 "projectId": "p1", "documentId": bill, "postingDate": DAY})
        self.assertEqual(self.view()["balances"][0]["payable"], 450)
        # Explicit funding before payment; never invent sufficient cash.
        self.do({"type": "funds.deposit", "eventId": "fund1",
                 "accountId": "1010", "amount": 600, "postingDate": DAY,
                 "note": "Test opening funds"})
        self.do({"type": "payment.record", "eventId": "pay1", "paymentId": "pay1",
                 "partyId": VENDOR["id"], "accountId": "1010", "postingDate": DAY,
                 "allocations": [{"billId": bill, "amount": 200}]})
        data = self.view()
        self.assertEqual(data["balances"][0]["payable"], 250)
        self.assertEqual(data["trialBalance"]["1010"]["normalBalance"], 400)
        self.assertTrue(finance.validate_finance_state(self.finance))

    def test_receipt_partial_from_person_reduces_receivable(self):
        inv = self.do(sales_command())["result"]["documentId"]
        self.do({"type": "document.review", "eventId": "rv1",
                 "projectId": "p1", "documentId": inv})
        self.do({"type": "document.issue", "eventId": "is1",
                 "projectId": "p1", "documentId": inv, "postingDate": DAY})
        self.do({"type": "receipt.record", "eventId": "r1", "receiptId": "receipt-1",
                 "partyId": CUSTOMER["id"], "accountId": "1010", "postingDate": DAY,
                 "allocations": [{"invoiceId": inv, "amount": 500}]})
        data = self.view()
        self.assertEqual(data["balances"][0]["receivable"], 1450)
        self.assertEqual(data["trialBalance"]["1010"]["normalBalance"], 500)

    def test_exact_retry_is_idempotent_and_different_reuse_fails(self):
        cmd = purchase_command()
        first = self.do(cmd)
        event_count = len(self.finance["accounting"]["events"])
        retry = self.do(cmd)
        self.assertEqual(first["result"], retry["result"])
        self.assertFalse(retry["changed"])
        self.assertEqual(len(self.finance["accounting"]["events"]), event_count)
        different = purchase_command()
        different["party"] = deepcopy(VENDOR)
        different["party"]["name"] = "Other Vendor"
        with self.assertRaises(ValueError):
            self.do(different)

    def test_same_cost_source_cannot_create_second_supplier_purchase(self):
        self.do(purchase_command())
        with self.assertRaisesRegex(ValueError, "Cost source already"):
            self.do(purchase_command(event_id="duplicate-bill"))

    def test_estimated_cost_requires_confirmation(self):
        with self.assertRaises(ValueError):
            self.do(purchase_command(basis="estimated"))
        out = self.do(purchase_command(basis="estimated", approve=True))
        self.assertEqual(out["result"]["total"], 500)
        self.assertEqual(self.view()["documents"][0]["status"], "Draft")

    def test_cancel_unissued_bill_keeps_history_and_allows_revised_new_draft(self):
        first = self.do(purchase_command())["result"]["documentId"]
        self.do({"type": "document.cancel", "eventId": "cancel-purchase",
                 "documentId": first, "projectId": "p1",
                 "reason": "Supplier corrected expense details"})
        self.assertEqual(self.view()["documents"][0]["status"], "Cancelled")
        second = self.do(purchase_command(event_id="corrected-bill"))["result"]["documentId"]
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.view()["documents"]), 2)

    def test_viewer_cannot_read_and_editor_cannot_post(self):
        with self.assertRaises(PermissionError):
            read_madar_accounting(self.finance, actor="viewer",
                                  accounts=ACCOUNTS, project_id="p1")
        with self.assertRaises(PermissionError):
            self.do(sales_command(), actor="editor")

    def test_foreign_task_cannot_issue_named_person_sale(self):
        command = sales_command()
        command["cardId"] = "task-2"
        with self.assertRaises(PermissionError):
            self.do(command)

    def test_invoice_state_is_json_roundtrippable_and_no_input_mutation(self):
        before = deepcopy(self.finance)
        output = apply_madar_accounting(self.finance, sales_command(),
                                        actor="admin", accounts=ACCOUNTS,
                                        cards=TASKS, projects=PROJECTS, now=NOW)
        self.assertEqual(before, self.finance)
        self.assertEqual(json.loads(json.dumps(output["state"])), output["state"])
        self.assertTrue(validate_accounting_extension(output["state"]))


if __name__ == "__main__":
    unittest.main()
