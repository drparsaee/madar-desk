"""Financial overview: server ACL, explicit receipts, date/cost attribution and persistence."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import finance
import native_app
from tests.legacy_sample_fixture import seed_legacy_example_state
from lan import LanService


NOW = "2026-10-20T10:00:00+03:30"


class OverviewDomainTests(unittest.TestCase):
    def setUp(self):
        self.state = finance.empty_finance_state()
        self.accounts = {
            "admin": {"username": "admin", "role": "admin", "projects": None},
            "reader": {"username": "reader", "role": "viewer", "projects": None,
                       "financeView": True},
            "editor": {"username": "editor", "role": "editor", "projects": ["p1"],
                       "financeEdit": True},
        }
        self.projects = [{"id": "p1", "name": "Project", "costEnabled": True, "price": 900000},
                         {"id": "p2", "name": "Other", "costEnabled": False, "price": 30000}]
        self.cards = [{"id": "c1", "projectId": "p1", "cost": 100, "costCategory": "پیک",
                       "updatedAt": "2026-10-20T09:00:00Z", "status": "active",
                       "checklist": [{"id": "a", "cost": 30, "costCategory": "چاپ"}],
                       "checklists": [{"id": "checklist-legacy", "items": [
                           {"id": "a", "cost": 30, "costCategory": "چاپ"}]}]},
                      {"id": "c2", "projectId": "p2", "cost": 40,
                       "createdAt": "2026-10-19T00:00:00Z", "status": "active",
                       "checklist": []}]

    def command(self, action, *, actor="admin"):
        result = finance.apply_finance_command(
            self.state, action, actor=actor, accounts=self.accounts,
            cards=self.cards, projects=self.projects, now=NOW)
        self.state = result["state"]
        return result

    def overview(self, *, actor="admin", **filters):
        return finance.financial_overview(
            self.state, actor=actor, accounts=self.accounts,
            cards=self.cards, projects=self.projects, **filters)

    def test_math_category_date_and_no_inferred_sale_price(self):
        self.command({"type": "project.receipt", "eventId": "r1", "projectId": "p1",
                      "amount": 700, "receivedAt": "2026-10-20T11:00:00+03:30",
                      "description": "اولین پرداخت"})
        self.command({"type": "project.receipt", "eventId": "r2", "projectId": "p1",
                      "amount": 200, "receivedAt": "2026-10-19T11:00:00+03:30",
                      "description": ""})
        totals = self.overview()
        self.assertEqual((totals["receivedTotal"], totals["expenseTotal"], totals["profit"]),
                         (900, 170, 730))
        self.assertEqual({e["category"]: e["total"] for e in totals["categories"]},
                         {"پیک": 100, "چاپ": 30, "بدون دسته‌بندی": 40})
        self.assertEqual(len([e for e in totals["expenses"] if e["cardId"] == "c1"]), 2)
        self.assertEqual(totals["expenseBasis"], "recorded_estimates")
        today = self.overview(project_id="p1", start_date="2026-10-20", end_date="2026-10-20")
        self.assertEqual((today["receivedTotal"], today["expenseTotal"], today["profit"]),
                         (700, 130, 570))
        earlier = self.overview(start_date="2026-10-19", end_date="2026-10-19")
        self.assertEqual((earlier["receivedTotal"], earlier["expenseTotal"]), (200, 40))

    def test_explicit_invoice_payment_is_cash_but_invoice_sale_is_not(self):
        sale = {"customer": {"name": "Test", "reference": ""},
                "lines": [{"id": "line", "description": "Work", "quantity": 1, "unitPrice": 1000}],
                "discount": 0, "tax": 0, "advance": 50, "autoInvoice": True}
        contract = self.command({"type": "contract.set", "eventId": "setup", "cardId": "c1", "sale": sale})
        self.cards[0]["status"] = "done"
        self.command({"type": "completion.record", "eventId": "completed", "cardId": "c1",
                      "completionId": "complete1"})
        invoice_id = self.state["invoices"][0]["id"]
        self.command({"type": "invoice.review", "eventId": "review", "invoiceId": invoice_id})
        self.command({"type": "invoice.issue", "eventId": "issue", "invoiceId": invoice_id})
        self.command({"type": "invoice.payment", "eventId": "paid", "invoiceId": invoice_id,
                      "amount": 300})
        self.assertEqual(contract["result"]["total"], 1000)
        self.assertEqual(self.overview(project_id="p1")["receivedTotal"], 300)

    def test_receipt_idempotency_access_malformed_and_legacy_schema(self):
        action = {"type": "project.receipt", "eventId": "stable", "projectId": "p1",
                  "amount": 25, "receivedAt": NOW, "description": "Paid"}
        first = self.command(action)
        self.assertTrue(first["changed"])
        self.state = json.loads(json.dumps(self.state))
        self.assertTrue(finance.validate_finance_state(self.state))
        retry = self.command(action)
        self.assertFalse(retry["changed"])
        self.assertEqual(len(self.state["ledger"]), 1)
        with self.assertRaisesRegex(ValueError, "Idempotency"):
            self.command({**action, "amount": 26})
        for actor in ("reader", "editor"):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.overview(actor=actor)
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.command({**action, "eventId": "attempt-" + actor}, actor=actor)
        for bad in (True, 0, -1, 1.3, "1.50", 10**15 + 1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.command({**action, "eventId": "bad", "amount": bad})
        for date_string in ("2026-02-30", "2026-10", "2026-10-21T00:00:00"):
            with self.subTest(date_string=date_string), self.assertRaises(ValueError):
                self.overview(start_date=date_string)
        with self.assertRaises(ValueError):
            self.overview(start_date="2026-10-21", end_date="2026-10-20")
        with self.assertRaises(ValueError):
            self.command({**action, "eventId": "bad-date", "receivedAt": "2026-10-20"})
        with self.assertRaises(ValueError):
            self.command({**action, "eventId": "unknown", "projectId": "other"})
        with self.assertRaises(ValueError):
            self.command({**action, "eventId": "unexpected", "salePrice": 900})
        legacy = finance.empty_finance_state()
        self.assertEqual(legacy["schemaVersion"], 1)
        self.assertTrue(finance.validate_finance_state(legacy))
        self.assertEqual(self.state.keys(), legacy.keys())

    def test_actual_cost_override_and_orphan_kept(self):
        self.command({"type": "cost.set", "eventId": "costs", "cardId": "c1", "value": {
            "cardId": "c1", "costEnabled": True, "estimatedDirect": 100,
            "actualDirect": 90, "items": [{"id": "checklist-legacy:a", "estimated": 30,
                                         "actual": 29}]}})
        report = self.overview(project_id="p1")
        self.assertEqual(report["expenseTotal"], 130)
        self.assertEqual(report["actualTotal"], 119)
        self.assertEqual(report["profit"], -130)
        self.cards[0]["checklists"] = []
        self.cards[0]["checklist"] = []
        orphan = self.overview(project_id="p1")
        self.assertEqual(orphan["expenseTotal"], 130)
        self.assertEqual(orphan["actualTotal"], 119)

    def test_persian_category_with_zero_width_joining_character(self):
        self.cards[0]["costCategory"] = "هزینه\u200cپیک"
        report = self.overview(project_id="p1")
        self.assertEqual(next(row for row in report["categories"]
                              if row["category"] == "هزینه\u200cپیک")["total"], 100)

    def test_cost_dates_remain_stable_after_unrelated_task_edit(self):
        card = self.cards[0]
        card["costDate"] = "2026-10-18"
        card["checklist"][0]["costDate"] = "2026-10-19"
        card["checklists"][0]["items"][0]["costDate"] = "2026-10-19"
        first = self.overview(start_date="2026-10-18", end_date="2026-10-18")
        second = self.overview(start_date="2026-10-19", end_date="2026-10-19")
        self.assertEqual((first["expenseTotal"], second["expenseTotal"]), (100, 70))
        self.assertEqual([e["date"] for e in first["expenses"]], ["2026-10-18"])
        self.assertEqual([e["date"] for e in second["expenses"] if e["cardId"] == "c1"],
                         ["2026-10-19"])
        card["title"] = "only title changed"
        card["updatedAt"] = "2026-10-21T12:00:00Z"
        self.assertEqual(self.overview(start_date="2026-10-18", end_date="2026-10-18")
                         ["expenseTotal"], 100)
        self.assertEqual(self.overview(start_date="2026-10-19", end_date="2026-10-19")
                         ["expenseTotal"], 70)
        self.assertEqual(self.overview(start_date="2026-10-21", end_date="2026-10-21")
                         ["expenseTotal"], 0)


class OverviewBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-finance-overview-")
        self.root = Path(self.tmp.name)
        self.patch = patch.object(native_app, "datadir", return_value=self.root)
        self.patch.start()
        self.bridge = seed_legacy_example_state(native_app.Bridge())
        self.server = LanService(self.bridge, self.root / "users.json", bind="127.0.0.1", port=0)
        self.server.setup_owner("admin", "strong-password-123")
        self.admin = self.server.authenticate("admin", "strong-password-123")["token"]

    def tearDown(self):
        self.server.stop()
        self.patch.stop()
        self.tmp.cleanup()

    def test_persistence_and_editor_redacted_state_remains_writable(self):
        task_state = self.bridge.getState()
        project = next(item for item in task_state["projects"] if item["id"] == "p-sample")
        project["price"] = 999999
        task_state["tasks"][0]["costCategory"] = "پیک"
        task_state["tasks"][0]["cost"] = 70
        task_state["tasks"][0]["checklist"][0]["costCategory"] = "چاپ"
        task_state["tasks"][0]["checklist"][0]["cost"] = 20
        self.bridge.saveState(task_state)
        event = {"type": "project.receipt", "eventId": "paid-p1", "projectId": "p-sample",
                 "amount": 200, "receivedAt": NOW, "description": "deposit"}
        self.assertEqual(self.bridge.financeCommand(event)["amount"], 200)
        self.assertEqual(self.bridge.financeCommand(event)["amount"], 200)
        self.assertTrue(finance.validate_finance_state(json.loads(
            self.bridge.finance_path.read_text(encoding="utf8"))))
        self.assertEqual(native_app.Bridge().financeOverview("p-sample")["receivedTotal"], 200)
        self.server.upsert_user(self.admin, {"username": "editor", "password": "editor-password",
                                             "role": "editor", "projects": ["p-sample"]})
        self.server.upsert_user(self.admin, {"username": "viewer", "password": "viewer-password",
                                             "role": "viewer", "projects": None})
        editor = self.server.authenticate("editor", "editor-password")["token"]
        viewer = self.server.authenticate("viewer", "viewer-password")["token"]
        for token in (editor, viewer):
            view = self.server.read_state(token)
            self.assertEqual(view["state"]["projects"][0]["price"], 0)
            self.assertNotIn("receivedTotal", json.dumps(view["state"]))
            with self.assertRaises(PermissionError):
                self.server.finance_overview(token)
            with self.assertRaises(PermissionError):
                self.server.finance_command(token, {**event, "eventId": "bad-" + token[:5]})
        current = self.server.read_state(editor)
        current["state"]["tasks"][0]["title"] = "edited"
        self.server.write_state(editor, current["state"], current["revision"])
        self.assertEqual(next(item for item in self.bridge.getState()["projects"]
                              if item["id"] == "p-sample")["price"], 999999)
        self.assertEqual(self.server.finance_overview(self.admin, "p-sample")["profit"], 110)

    def test_receipt_survives_legacy_to_unified_sqlite_migration(self):
        first = {"type": "project.receipt", "eventId": "legacy-receipt",
                 "projectId": "p-sample", "amount": 400,
                 "receivedAt": NOW, "description": "old payment"}
        second = {**first, "eventId": "sqlite-receipt", "amount": 150}
        self.bridge.financeCommand(first)
        original = self.bridge.finance_path.read_bytes()
        self.bridge.enableUnifiedStorage()
        self.assertEqual(self.bridge.finance_path.read_bytes(), original)
        self.bridge.financeCommand(second)
        restarted = native_app.Bridge()
        self.assertEqual(restarted.financeOverview("p-sample")["receivedTotal"], 550)
        self.assertEqual(len([row for row in restarted._load_finance()["ledger"]
                              if row["action"] == "project.receipt"]), 2)

    def test_http_overview_requires_admin_and_rejects_bad_dates(self):
        port = self.server.start()
        def request(path, token):
            req = Request(f"http://127.0.0.1:{port}{path}", headers={
                "Authorization": "Bearer " + token})
            with urlopen(req, timeout=5) as response:
                return json.loads(response.read())
        self.assertEqual(request("/api/finance-overview?projectId=p-sample", self.admin)["profit"], 0)
        self.server.upsert_user(self.admin, {"username": "reader", "password": "reader-password",
                                             "role": "viewer", "projects": None})
        reader = self.server.authenticate("reader", "reader-password")["token"]
        with self.assertRaises(HTTPError) as denied:
            request("/api/finance-overview", reader)
        self.assertEqual(denied.exception.code, 403)
        with self.assertRaises(HTTPError) as invalid:
            request("/api/finance-overview?startDate=2026-02-30", self.admin)
        self.assertEqual(invalid.exception.code, 400)

    def test_native_validation_retains_cost_dates_and_checks_label_colors(self):
        state = self.bridge.getState()
        task = state["tasks"][0]
        task["costDate"] = "2026-10-18"
        task["checklist"][0]["costDate"] = "2026-10-19"
        task["labelColors"] = {"هزینه\u200cپیک": "#11AaFf", "__proto__": "#00ff00"}
        self.bridge.saveState(state)
        loaded = native_app.Bridge().getState()["tasks"][0]
        self.assertEqual(loaded["costDate"], "2026-10-18")
        self.assertEqual(loaded["checklist"][0]["costDate"], "2026-10-19")
        self.assertEqual(loaded["checklists"][0]["items"][0]["costDate"], "2026-10-19")
        self.assertEqual(loaded["labelColors"]["هزینه\u200cپیک"], "#11AaFf")
        self.assertEqual(loaded["labelColors"]["__proto__"], "#00ff00")
        for field, bad in (("costDate", "2026-02-30"), ("costDate", "2026-10-20T11:00:00Z"),
                           ("costDate", 20261020), ("labelColors", {"پیک": "red"}),
                           ("labelColors", {"نام": "#ff00000"})):
            bad_state = deepcopy(self.bridge.getState())
            bad_state["tasks"][0][field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                self.bridge.saveState(bad_state)
        bad_state = deepcopy(self.bridge.getState())
        bad_state["tasks"][0]["checklist"][0]["costDate"] = "2026-13-01"
        with self.assertRaises(ValueError):
            self.bridge.saveState(bad_state)


if __name__ == "__main__":
    unittest.main()
