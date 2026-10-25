"""Host-only synthetic task handoff and sensitive LAN projection contracts."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from standalone_accounting import StandaloneAccountingStore
from standalone_task_prepare import prepare_from_saved_task
from finance_visibility import redact_card, preserve_editor_finance
from lan import LanService
from native_app import Bridge

NOW = "2026-10-22T10:30:00Z"
USERS = {
    "manager": {"username": "manager", "role": "admin"},
    "worker": {"username": "worker", "role": "editor"},
    "accountant": {"username": "accountant", "role": "editor", "financeEdit": True},
}


class TrustedHandoff(unittest.TestCase):
    def test_parallel_preparation_same_sale_and_unpriced_work_is_idempotent(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            sales = list(executor.map(lambda _: self.prepare(), range(8)))
        self.assertEqual(len({x["id"] for x in sales}), 1)
        self.assertEqual(sum(not x["existing"] for x in sales), 1)
        with ThreadPoolExecutor(max_workers=8) as executor:
            contractors = list(executor.map(
                lambda _: self.prepare("binding.1"), range(8)))
        self.assertEqual({x["id"] for x in contractors}, {"binding.1"})
        self.assertEqual(sum(not x["existing"] for x in contractors), 1)
        view = self.view()
        self.assertEqual(len(view["invoices"]), 1)
        self.assertEqual(len(view["contractorJobs"]), 1)
        self.assertEqual(view["journals"], [])

    def setUp(self):
        temp = TemporaryDirectory(prefix="madar-handoff-synthetic-")
        self.addCleanup(temp.cleanup)
        self.store = StandaloneAccountingStore(Path(temp.name) / "standalone.sqlite3")
        self.tasks = [{"id": "book.1", "title": "کتاب بهمان",
                       "orderCustomerName": "آقای فلان", "salePartyId": "client",
                       "saleQuantity": 100, "saleUnitPrice": 20000,
                       "saleCurrency": "TOMAN",
                       "description": "۴۰۰ صفحه وزیری سیاه و سفید | جلد شومیز | سلفون مات | صحافی چسب گرم",
                       "checklist": [
                           {"id": "print.inside", "text": "چاپ داخله", "done": True},
                           {"id": "cover", "text": "چاپ جلد", "done": True},
                           {"id": "laminate", "text": "سلفون", "done": False,
                            "expenseItems": [
                                {"id": "courier.1", "description": "پیک", "partyId": "behrouz",
                                 "quantity": 1, "unitPrice": 150000, "currency": "TOMAN"},
                                {"id": "laminate.1", "description": "سلفون",
                                 "partyId": "laminate.vendor", "quantity": 100,
                                 "unitPrice": None, "currency": "TOMAN"}]},
                           {"id": "bind", "text": "صحافی", "done": False,
                            "expenseItems": [
                                {"id": "binding.1",
                                 "description": "صحافی چسب گرم کتاب بهمان",
                                 "partyId": "pooya", "quantity": 100,
                                 "unitPrice": None, "currency": "TOMAN"}]}]}]
        revision = 0
        for i, (id_, name, kind) in enumerate((
                ("client", "آقای فلان", "customer"),
                ("behrouz", "بهروز", "vendor"),
                ("laminate.vendor", "سلفون‌کشی نمونه", "vendor"),
                ("pooya", "صحافی پویا", "vendor"))):
            result = self.store.command(
                {"type": "party.register", "eventId": f"reg.{i}",
                 "partyId": id_, "name": name, "kind": kind},
                actor="manager", accounts=USERS,
                expected_revision=revision, now=NOW)
            revision = result["revision"]

    def prepare(self, expense_id=None, **kwargs):
        return prepare_from_saved_task(
            self.store, {"taskId": "book.1", "expenseId": expense_id},
            tasks=self.tasks, actor=kwargs.pop("actor", "manager"),
            accounts=USERS, now=NOW)

    def view(self):
        return self.store.read(actor="manager", accounts=USERS)["view"]

    def test_saved_book_and_costs_are_minimally_transmitted(self):
        sale = self.prepare()
        self.assertFalse(sale["existing"])
        self.assertEqual(self.prepare()["id"], sale["id"])
        self.prepare("courier.1")
        self.prepare("laminate.1")
        self.prepare("binding.1")
        self.assertTrue(self.prepare("binding.1")["existing"])
        v = self.view()
        self.assertEqual(v["invoices"][sale["id"]]["total"], 2000000)
        self.assertEqual(len(v["contractorJobs"]), 3)
        self.assertEqual(v["contractorJobs"]["courier.1"]["unitPrice"], 150000)
        self.assertIsNone(v["contractorJobs"]["laminate.1"]["unitPrice"])
        self.assertEqual(v["journals"], [])
        self.assertNotIn("۴۰۰ صفحه", str(v))
        self.assertNotIn("جلد شومیز", str(v))
        self.assertEqual(v["parties"]["pooya"]["payable"], 0)

    def test_untrusted_payload_and_non_admin_denied(self):
        for actor in ("worker", "accountant"):
            with self.assertRaises(PermissionError):
                self.prepare(actor=actor)
        for bad in (
                {"taskId": "book.1", "expenseId": None, "unitPrice": 1},
                {"taskId": "book.1", "expenseId": None, "actor": "manager"},
                {"taskId": "book.1", "expenseId": None, "description": "fake"}):
            with self.assertRaises(ValueError):
                prepare_from_saved_task(self.store, bad, tasks=self.tasks,
                                        actor="manager", accounts=USERS, now=NOW)
        with self.assertRaises(ValueError):
            self.prepare("unknown")
        self.assertEqual(self.view()["contractorJobs"], {})

    def test_no_implicit_rial_rounding(self):
        self.tasks[0]["saleCurrency"] = "RIAL"
        self.tasks[0]["saleUnitPrice"] = 125
        with self.assertRaisesRegex(ValueError, "RIAL"):
            self.prepare()
        self.tasks[0]["saleUnitPrice"] = 200000
        self.assertFalse(self.prepare()["existing"])
        self.assertEqual(next(iter(self.view()["invoices"].values()))["total"], 2000000)
        self.tasks[0]["checklist"][2]["expenseItems"][0]["currency"] = "RIAL"
        self.assertFalse(self.prepare("courier.1")["existing"])
        self.assertEqual(self.view()["contractorJobs"]["courier.1"]["currency"], "TOMAN")

    def test_employee_cannot_read_or_overwrite_multiple_financial_items(self):
        original = deepcopy(self.tasks[0])
        cleaned = redact_card(original)
        self.assertNotIn("150000", str(cleaned))
        self.assertEqual(cleaned["checklist"][2]["expenseItems"], [])
        self.assertEqual(cleaned["saleUnitPrice"], 0)
        self.assertEqual(cleaned["salePartyId"], "")
        self.assertEqual(cleaned["orderCustomerName"], "آقای فلان")
        edited = deepcopy(cleaned)
        edited["title"] = "کار پیگیری کتاب"
        preserve_editor_finance([original], [edited])
        self.assertEqual(edited["checklist"][2]["expenseItems"],
                         original["checklist"][2]["expenseItems"])
        attack = deepcopy(cleaned)
        attack["checklist"][2]["expenseItems"] = [{
            "id": "hacked", "partyId": "hacker", "unitPrice": 1}]
        with self.assertRaises(PermissionError):
            preserve_editor_finance([original], [attack])
        removed = deepcopy(cleaned)
        removed["checklist"].pop(2)
        with self.assertRaises(PermissionError):
            preserve_editor_finance([original], [removed])

    def test_native_bridge_reads_only_authoritative_saved_tasks(self):
        host = Bridge.__new__(Bridge)
        host.connection = {"mode": "solo"}
        host.lan = None
        host._lock = threading.RLock()
        host._standalone_accounting_store = lambda: self.store
        host.getState = lambda: {"tasks": self.tasks}
        with self.assertRaisesRegex(ValueError, "taskId and expenseId"):
            host.standaloneAccountingPrepare({"taskId": "book.1", "expenseId": None,
                                              "unitPrice": 1})
        prepared = host.standaloneAccountingPrepare(
            {"taskId": "book.1", "expenseId": None})
        self.assertFalse(prepared["existing"])
        self.assertEqual(self.view()["invoices"][prepared["id"]]["total"], 2000000)
        self.assertTrue(host.standaloneAccountingPrepare(
            {"taskId": "book.1", "expenseId": None})["existing"])

    def test_lan_service_authorizes_admin_and_rejects_editor_preparation(self):
        fake_bridge = Bridge.__new__(Bridge)
        fake_bridge._lock = threading.RLock()
        fake_bridge._standalone_accounting_store = lambda: self.store
        fake_bridge.getState = lambda: {"tasks": self.tasks}
        service = LanService.__new__(LanService)
        service.lock = threading.RLock()
        service.bridge = fake_bridge
        service.users = USERS
        service.account_for = lambda token: USERS[token]
        with self.assertRaises(PermissionError):
            service.standalone_accounting_prepare(
                "accountant", {"taskId": "book.1", "expenseId": "courier.1"})
        result = service.standalone_accounting_prepare(
            "manager", {"taskId": "book.1", "expenseId": "courier.1"})
        self.assertEqual(result["id"], "courier.1")
        self.assertEqual(self.view()["journals"], [])


if __name__ == "__main__":
    unittest.main()
