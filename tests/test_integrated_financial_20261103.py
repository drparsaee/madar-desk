"""Synthetic tests for integrated financial audit controls, no live data."""
import math
import unittest

from accounting_core import (accounting_view, apply_accounting_command,
                             empty_rial_accounting_state, validate_accounting_state)
from accounting_reporting import ledger_reports
from standalone_accounting_tax_advisor import preflight_einvoice


USERS = {"admin": {"username": "admin", "role": "admin"}}
NOW = "2026-11-03T12:00:00Z"


class IntegratedFinancialTests(unittest.TestCase):
    def setUp(self):
        self.state = empty_rial_accounting_state()
        self.events = 0

    def cmd(self, command_type, now=NOW, **fields):
        self.events += 1
        result = apply_accounting_command(
            self.state, {"type": command_type, "eventId": f"fin.{self.events}", **fields},
            actor="admin", accounts=USERS, now=now)
        self.state = result["state"]
        return result["result"]

    def view(self):
        return accounting_view(self.state, actor="admin", accounts=USERS)

    def stock_fixture(self, *, tax=0, discount=0, qty=2, price=100):
        self.cmd("item.create", itemId="item", sku="SKU", name="Test goods",
                 kind="goods", unit="piece")
        self.cmd("item.stock.enable", itemId="item")
        self.cmd("warehouse.create", warehouseId="warehouse", name="Store")
        self.cmd("party.register", partyId="vendor", name="Vendor", kind="vendor")
        self.cmd("bill.create", billId="purchase", partyId="vendor",
                 documentDate="2026-10-01", tax=tax, discount=discount,
                 lines=[{"description": "Goods", "quantity": qty,
                         "unitPrice": price, "itemId": "item"}])
        self.cmd("bill.approve", billId="purchase")
        self.cmd("bill.issue", billId="purchase", postingDate="2026-10-01")

    def test_taxed_discounted_stock_receipt_preserves_policy_and_exact_gl(self):
        self.stock_fixture(tax=18, discount=10)
        before = self.state
        with self.assertRaisesRegex(ValueError, "taxTreatment='expense'"):
            self.cmd("inventory.receive", warehouseId="warehouse", itemId="item",
                     quantity=1, billId="purchase", postingDate="2026-10-02")
        self.assertEqual(self.state, before)
        first = self.cmd("inventory.receive", warehouseId="warehouse", itemId="item",
                         quantity=1, billId="purchase", postingDate="2026-10-02",
                         taxTreatment="expense", discountAllocation="single-line-uniform")
        self.assertEqual(first["value"], 95)
        self.cmd("inventory.receive", warehouseId="warehouse", itemId="item",
                 quantity=1, billId="purchase", postingDate="2026-10-02",
                 taxTreatment="expense", discountAllocation="single-line-uniform")
        v = self.view()
        self.assertEqual(v["stock"]["warehouse"]["item"]["value"], 190)
        self.assertEqual(v["accounts"]["5100"]["debitMinusCredit"], 0)
        self.assertEqual(v["accounts"]["5200"]["debitMinusCredit"], 18)
        self.assertEqual(v["accounts"]["5000"]["debitMinusCredit"], 0)
        self.assertEqual(v["accounts"]["2000"]["debitMinusCredit"], -208)
        self.assertEqual(ledger_reports(v)["profitLoss"],
                         {"revenue": 0, "expense": 18, "net": -18})
        self.assertTrue(validate_accounting_state(self.state))

    def test_nonintegral_discount_allocation_fails_without_mutation(self):
        self.stock_fixture(tax=10, discount=1, qty=3)
        previous = self.state
        with self.assertRaisesRegex(ValueError, "fractional"):
            self.cmd("inventory.receive", warehouseId="warehouse", itemId="item",
                     quantity=1, billId="purchase", postingDate="2026-10-02",
                     taxTreatment="expense", discountAllocation="single-line-uniform")
        self.assertEqual(self.state, previous)

    def test_configured_posting_offset_accepts_equivalent_trusted_instants(self):
        company = dict(legalName="Synthetic", address="", phone="", nationalId="",
                       economicCode="", postalCode="", reason="Set financial calendar")
        self.cmd("company.profile.set", postingUtcOffsetMinutes=210,
                 now="2026-11-02T21:30:00Z", **company)
        for instant in ("2026-11-02T22:00:00Z", "2026-11-03T01:30:00+03:30"):
            self.cmd("funds.deposit", accountId="1010", amount=1,
                     postingDate="2026-11-03", note="Local date", now=instant)
        self.assertEqual(self.view()["accounts"]["1010"]["normalBalance"], 2)
        self.assertTrue(validate_accounting_state(self.state))
        with self.assertRaisesRegex(ValueError, "future"):
            self.cmd("funds.deposit", accountId="1010", amount=1,
                     postingDate="2026-11-04", note="Future local day",
                     now="2026-11-02T22:00:00Z")

    def test_fiscal_close_rejects_incomplete_cogs_and_reports_uncertainty(self):
        self.stock_fixture()
        self.cmd("inventory.receive", warehouseId="warehouse", itemId="item",
                 quantity=2, billId="purchase", postingDate="2026-10-02")
        self.cmd("party.register", partyId="buyer", name="Buyer", kind="customer")
        self.cmd("invoice.create", invoiceId="sale", partyId="buyer",
                 documentDate="2026-10-03", lines=[
                     {"description": "Goods", "itemId": "item", "quantity": 1,
                      "unitPrice": 150}])
        self.cmd("invoice.approve", invoiceId="sale")
        self.cmd("invoice.issue", invoiceId="sale", postingDate="2026-10-03")
        r = ledger_reports(self.view(), through_date="2026-10-31")
        self.assertFalse(r["profitLossComplete"])
        self.assertEqual(r["unpostedGoodsIssues"], [
            {"invoiceId": "sale", "itemId": "item", "lineIndex": 0,
             "missingQuantity": 1}])
        previous = self.state
        with self.assertRaisesRegex(ValueError, "Period close requires inventory.issue/COGS"):
            self.cmd("period.close", throughDate="2026-10-31")
        self.assertEqual(previous, self.state)
        with self.assertRaisesRegex(ValueError, "inventory.issue/COGS for invoice sale"):
            self.cmd("fiscal.year.close", startDate="2026-10-01",
                     throughDate="2026-10-31", reason="Attempt incomplete close")
        self.assertEqual(previous, self.state)
        self.cmd("inventory.issue", warehouseId="warehouse", itemId="item",
                 quantity=1, invoiceId="sale", postingDate="2026-10-04")
        r = ledger_reports(self.view(), through_date="2026-10-31")
        self.assertTrue(r["profitLossComplete"])
        self.assertEqual(r["unpostedGoodsIssues"], [])
        self.assertEqual(r["profitLoss"]["net"], 50)
        self.cmd("fiscal.year.close", startDate="2026-10-01", throughDate="2026-10-31",
                 reason="Completed COGS before close")
        self.assertTrue(validate_accounting_state(self.state))

    def test_tax_preflight_refuses_nan_inf_and_out_of_bounds(self):
        base = {"invoiceId": "test", "issueDate": "2026-11-03",
                "lines": [{"productServiceId": "synthetic", "quantity": 1,
                           "unitPrice": 2}]}
        company = {"economicCode": "demo", "taxMemoryId": "demo"}
        for key, value in (("quantity", math.nan), ("quantity", math.inf),
                           ("unitPrice", -math.inf), ("quantity", 10**16),
                           ("unitPrice", True)):
            with self.subTest(key=key, value=str(value)):
                doc = {**base, "lines": [{**base["lines"][0], key: value}]}
                report = preflight_einvoice(doc, company)
                self.assertIn(f"lines.0.{key}", [x["field"] for x in report["issues"]
                                                      if x["severity"] == "blocker"])
                self.assertFalse(report["submissionPermitted"])

    def test_historical_unposted_goods_alert_survives_later_invoice_reversal(self):
        self.cmd("item.create", itemId="stocked", sku="S1", name="Stocked item",
                 kind="goods", unit="piece")
        self.cmd("item.stock.enable", itemId="stocked")
        self.cmd("party.register", partyId="buyer", name="Buyer", kind="customer")
        self.cmd("invoice.create", invoiceId="historic", partyId="buyer",
                 documentDate="2026-10-03", lines=[
                     {"description": "Goods", "quantity": 1, "unitPrice": 10,
                      "itemId": "stocked"}])
        self.cmd("invoice.approve", invoiceId="historic")
        self.cmd("invoice.issue", invoiceId="historic", postingDate="2026-10-03")
        issued_id = self.view()["invoices"]["historic"]["postedEntryId"]
        self.assertFalse(ledger_reports(self.view(), through_date="2026-10-03")
                         ["profitLossComplete"])
        self.cmd("journal.reverse", journalId=issued_id,
                 postingDate="2026-10-04", reason="Synthetic void")
        earlier = ledger_reports(self.view(), through_date="2026-10-03")
        self.assertFalse(earlier["profitLossComplete"])
        self.assertEqual(earlier["unpostedGoodsIssues"][0]["invoiceId"], "historic")
        later = ledger_reports(self.view(), through_date="2026-10-04")
        self.assertTrue(later["profitLossComplete"])
        self.assertEqual(later["unpostedGoodsIssues"], [])


if __name__ == "__main__":
    unittest.main()
