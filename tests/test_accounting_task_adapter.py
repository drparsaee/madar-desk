"""Isolated task-to-person sales and cost-to-vendor purchase draft acceptance."""
from copy import deepcopy
import json
import unittest

from accounting_task_adapter import task_sales_draft, task_purchase_draft
from finance import amount

PROJECTS = [{"id": "p1", "name": "چاپ", "price": 13_000_000, "costEnabled": True},
            {"id": "p2", "name": "طراحی", "price": 10_000, "costEnabled": False}]
CARDS = [{"id": "task1", "title": "چاپ بسته‌بندی", "projectId": "p1", "status": "active",
          "cost": 800_000, "costEnabled": True,
          "checklist": [{"id": "cut", "text": "دایکات", "cost": 120_000},
                        {"id": "print", "text": "چاپ افست", "cost": 300_000}]},
         {"id": "task2", "title": "طراحی", "projectId": "p2", "cost": 55_000, "checklist": []}]
CUSTOMER = {"id": "customer-sara", "name": "سارا رضایی", "kind": "customer", "reference": ""}
SUPPLIER = {"id": "vendor-printer", "name": "چاپخانه همکار", "kind": "supplier", "reference": ""}
SALE_LINES = [{"id": "p", "description": "چاپ جعبه مدل A", "quantity": 2, "unitPrice": 1_500_000}]
BASE_FINANCE = {"cardCosts": {"task1": {
    "cardId": "task1", "costEnabled": True, "estimatedDirect": 800_000,
    "actualDirect": 750_000,
    "items": [{"id": "checklist-legacy:cut", "estimated": 120_000, "actual": 110_000},
              {"id": "checklist-legacy:print", "estimated": 300_000, "actual": 290_000}]}}}


def sale(**kw):
    return task_sales_draft(task=CARDS[0], projects=PROJECTS, project_id="p1",
                            customer=CUSTOMER, lines=SALE_LINES,
                            discount=250_000, tax=100_000, advance=500_000,
                            event_id="sales-task1-v1", granted_project_ids=["p1"], **kw)


def purchase(**kw):
    return task_purchase_draft(tasks=CARDS, projects=PROJECTS,
                               finance_state=BASE_FINANCE, project_id="p1",
                               supplier=SUPPLIER,
                               selections=[{"cardId": "task1", "sourceId": "direct"},
                                           {"cardId": "task1", "sourceId": "checklist-legacy:cut"}],
                               basis="actual", approve_estimate=False,
                               event_id="purchase-task1-v1",
                               granted_project_ids=["p1"], **kw)


class AdapterTests(unittest.TestCase):
    def test_sale_issues_personal_named_draft_but_not_paid_or_posted(self):
        output = sale()
        invoice = output["document"]
        self.assertEqual(invoice["party"]["name"], "سارا رضایی")
        self.assertEqual(invoice["party"]["kind"], "customer")
        self.assertEqual(invoice["subtotal"], 3_000_000)
        self.assertEqual(invoice["total"], 2_850_000)
        self.assertEqual(invoice["remaining"], 2_350_000)
        self.assertEqual(invoice["status"], "Draft")
        self.assertEqual(output["financeCommand"]["type"], "contract.set")
        self.assertFalse(output["financeCommand"]["sale"]["autoInvoice"])

    def test_sales_price_not_inferred_from_task_cost_or_project_price(self):
        changed = deepcopy(CARDS[0])
        changed["cost"] = 50_000_000
        output = task_sales_draft(task=changed, projects=PROJECTS,
                                   project_id="p1", customer=CUSTOMER,
                                   lines=SALE_LINES, discount=250_000, tax=100_000,
                                   advance=500_000, event_id="e", granted_project_ids=["p1"])
        self.assertEqual(output["document"]["total"], 2_850_000)
        self.assertNotIn("cost", output["document"])

    def test_purchase_makes_vendor_bill_draft_from_recorded_actuals(self):
        output = purchase()
        self.assertEqual(output["document"]["party"]["name"], "چاپخانه همکار")
        self.assertEqual(output["document"]["kind"], "purchase")
        self.assertEqual(output["document"]["subtotal"], 860_000)
        self.assertEqual(output["document"]["status"], "Draft")
        self.assertEqual(output["document"]["basis"], "actual")
        self.assertNotIn("paid", output["document"])

    def test_estimate_only_explicitly_confirmed_and_still_draft(self):
        kwargs = {"tasks": CARDS, "projects": PROJECTS, "finance_state": BASE_FINANCE,
                  "project_id": "p1", "supplier": SUPPLIER,
                  "selections": [{"cardId": "task1", "sourceId": "direct"}],
                  "basis": "estimated", "event_id": "event-e", "granted_project_ids": ["p1"]}
        with self.assertRaisesRegex(ValueError, "confirmation"):
            task_purchase_draft(**kwargs, approve_estimate=False)
        draft = task_purchase_draft(**kwargs, approve_estimate=True)["document"]
        self.assertEqual(draft["total"], 800_000)
        self.assertTrue(draft["estimatedApproved"])
        self.assertEqual(draft["status"], "Draft")

    def test_selection_cannot_double_bill_same_expense_within_draft(self):
        with self.assertRaisesRegex(ValueError, "once"):
            task_purchase_draft(tasks=CARDS, projects=PROJECTS,
                                finance_state=BASE_FINANCE, project_id="p1",
                                supplier=SUPPLIER, basis="actual", approve_estimate=False,
                                event_id="duplicate", granted_project_ids=["p1"],
                                selections=[{"cardId": "task1", "sourceId": "direct"}] * 2)

    def test_foreign_project_access_never_reads_foreign_costs(self):
        with self.assertRaises(PermissionError):
            task_purchase_draft(tasks=CARDS, projects=PROJECTS,
                                finance_state=BASE_FINANCE, project_id="p1",
                                supplier=SUPPLIER, basis="estimated", approve_estimate=True,
                                event_id="foreign", granted_project_ids=["p1"],
                                selections=[{"cardId": "task2", "sourceId": "direct"}])
        with self.assertRaises(PermissionError):
            task_sales_draft(task=CARDS[0], projects=PROJECTS, project_id="p1",
                             customer=CUSTOMER, lines=SALE_LINES, discount=0,
                             tax=0, advance=0, event_id="no-grant",
                             granted_project_ids=["p2"])

    def test_invalid_or_unpayable_cost_sources_fail_closed(self):
        data = deepcopy(BASE_FINANCE)
        data["cardCosts"]["task1"]["actualDirect"] = 0
        kwargs = {"tasks": CARDS, "projects": PROJECTS, "finance_state": data,
                  "project_id": "p1", "supplier": SUPPLIER,
                  "basis": "actual", "approve_estimate": False, "event_id": "zero",
                  "granted_project_ids": ["p1"]}
        with self.assertRaisesRegex(ValueError, "positive"):
            task_purchase_draft(**kwargs, selections=[{"cardId": "task1", "sourceId": "direct"}])
        with self.assertRaisesRegex(ValueError, "Unknown"):
            task_purchase_draft(**kwargs, selections=[{"cardId": "task1", "sourceId": "other"}])

    def test_legacy_orphaned_cost_is_not_eligible_for_new_purchase(self):
        tasks = deepcopy(CARDS)
        tasks[0]["checklist"] = [tasks[0]["checklist"][-1]]
        with self.assertRaisesRegex(ValueError, "Unknown"):
            task_purchase_draft(tasks=tasks, projects=PROJECTS,
                                finance_state=BASE_FINANCE, project_id="p1",
                                supplier=SUPPLIER, basis="actual", approve_estimate=False,
                                event_id="orphan", granted_project_ids=["p1"],
                                selections=[{"cardId": "task1", "sourceId": "checklist-legacy:cut"}])

    def test_purchase_fingerprint_deterministic_and_no_source_mutation(self):
        before = json.dumps({"tasks": CARDS, "finance": BASE_FINANCE}, sort_keys=True)
        one = purchase()
        two = purchase()
        self.assertEqual(one, two)
        self.assertEqual(before, json.dumps({"tasks": CARDS, "finance": BASE_FINANCE}, sort_keys=True))
        self.assertEqual(len(one["fingerprint"]), 64)

    def test_sale_invalid_party_or_float_money_rejected(self):
        customer = deepcopy(CUSTOMER)
        customer["name"] = ""
        with self.assertRaisesRegex(ValueError, "name"):
            task_sales_draft(task=CARDS[0], projects=PROJECTS, project_id="p1",
                             customer=customer, lines=SALE_LINES, discount=0, tax=0,
                             advance=0, event_id="invalid", granted_project_ids=["p1"])
        with self.assertRaises(ValueError):
            task_sales_draft(task=CARDS[0], projects=PROJECTS, project_id="p1",
                             customer=CUSTOMER, lines=SALE_LINES, discount=0.1, tax=0,
                             advance=0, event_id="invalid2", granted_project_ids=["p1"])

    def test_partial_sale_total_bounds_and_advance_guard(self):
        with self.assertRaisesRegex(ValueError, "advance"):
            task_sales_draft(task=CARDS[0], projects=PROJECTS, project_id="p1",
                             customer=CUSTOMER, lines=SALE_LINES, discount=0, tax=0,
                             advance=3_000_001, event_id="invalid3",
                             granted_project_ids=["p1"])

    def test_source_can_roundtrip_json_and_money_is_integer(self):
        draft = purchase()["document"]
        self.assertEqual(json.loads(json.dumps(draft, ensure_ascii=False)), draft)
        self.assertEqual(type(draft["total"]), int)
        self.assertEqual(amount(draft["total"]), draft["total"])


if __name__ == "__main__":
    unittest.main()
