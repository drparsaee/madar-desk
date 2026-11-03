"""Synthetic reconciliation tests for all-project company ledger reports."""
import unittest

from accounting_core import accounting_view, apply_accounting_command, empty_accounting_state
from accounting_reporting import ledger_reports

NOW = "2026-10-21T16:00:00+03:30"
USERS = {"admin": {"username": "admin", "role": "admin"}}


class AccountingReportingTests(unittest.TestCase):
    def setUp(self):
        self.state = empty_accounting_state()
        self.index = 0

    def cmd(self, command_type, **fields):
        self.index += 1
        output = apply_accounting_command(self.state,
            {"type": command_type, "eventId": "rpt-" + str(self.index), **fields},
            actor="admin", accounts=USERS, now=NOW)
        self.state = output["state"]

    def report(self, **kwargs):
        return ledger_reports(accounting_view(self.state, actor="admin", accounts=USERS), **kwargs)

    def test_empty_trial_balance_and_balance_sheet_equal_zero(self):
        report = self.report()
        self.assertEqual(report["trialBalance"]["totalDebit"], 0)
        self.assertEqual(report["trialBalance"]["totalCredit"], 0)
        self.assertEqual(report["profitLoss"]["net"], 0)
        self.assertEqual(report["balanceSheet"]["assets"], 0)

    def test_sale_bill_receipt_and_liabilities_reconcile_exactly(self):
        self.cmd("party.register", partyId="customer", name="A", kind="customer")
        self.cmd("party.register", partyId="vendor", name="B", kind="vendor")
        self.cmd("invoice.create", invoiceId="s", partyId="customer", documentDate="2026-10-01",
                 lines=[{"description": "Service", "quantity": 2, "unitPrice": 500}])
        self.cmd("invoice.approve", invoiceId="s")
        self.cmd("invoice.issue", invoiceId="s", postingDate="2026-10-01")
        self.cmd("bill.create", billId="b", partyId="vendor", documentDate="2026-10-02",
                 lines=[{"description": "Print", "quantity": 1, "unitPrice": 400}])
        self.cmd("bill.approve", billId="b")
        self.cmd("bill.issue", billId="b", postingDate="2026-10-02")
        self.cmd("receipt.record", receiptId="r", partyId="customer", accountId="1010",
                 postingDate="2026-10-03", allocations=[{"invoiceId": "s", "amount": 200}])
        r = self.report()
        self.assertEqual(r["trialBalance"]["totalDebit"], 1400)
        self.assertEqual(r["trialBalance"]["totalCredit"], 1400)
        self.assertEqual(r["balanceSheet"], {"assets": 1000, "liabilities": 400,
            "capital": 0, "unclosedProfitLoss": 600, "liabilitiesAndEquity": 1000})
        self.assertEqual(r["profitLoss"], {"revenue": 1000, "expense": 400, "net": 600})
        self.assertEqual(r["accountStatements"]["1010"][0]["balanceDebitMinusCredit"], 200)
        self.assertEqual(r["accountStatements"]["1200"][-1]["balanceDebitMinusCredit"], 800)
        # As of October 1, expense/payment are not yet recognized.
        earlier = self.report(through_date="2026-10-01")
        self.assertEqual(earlier["profitLoss"]["net"], 1000)
        self.assertEqual(earlier["balanceSheet"]["assets"], 1000)
        self.assertEqual(earlier["balanceSheet"]["liabilities"], 0)
        # Period movements exclude prior revenue but the balance sheet carries it.
        later = self.report(from_date="2026-10-02", through_date="2026-10-03")
        self.assertEqual(later["profitLoss"]["net"], -400)
        self.assertEqual(later["balanceSheet"]["unclosedProfitLoss"], 600)
        self.assertEqual(later["trialBalance"]["totalDebit"], 1400)

    def test_reversal_keeps_audit_and_zeroes_balances(self):
        self.cmd("funds.deposit", accountId="1000", amount=700,
                 postingDate="2026-10-01", note="Capital")
        original = self.report()
        journal_id = original["accountStatements"]["1000"][0]["journalId"]
        self.cmd("journal.reverse", journalId=journal_id, postingDate="2026-10-02",
                 reason="Correction")
        r = self.report()
        self.assertEqual(r["trialBalance"]["totalDebit"], 0)
        self.assertEqual(r["balanceSheet"]["assets"], 0)
        self.assertEqual(len(r["accountStatements"]["1000"]), 2)
        self.assertEqual(self.report(through_date="2026-10-01")[
            "balanceSheet"]["assets"], 700)

    def test_invalid_period_refused(self):
        for kwargs in ({"from_date": "1405/01/01"},
                       {"through_date": "2026-02-30"},
                       {"from_date": "2026-10-22", "through_date": "2026-10-21"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.report(**kwargs)

    def test_closed_year_preserves_operational_profit_and_reconciles_closing(self):
        self.cmd("party.register", partyId="customer", name="Year end", kind="customer")
        self.cmd("invoice.create", invoiceId="fy-sale", partyId="customer",
                 documentDate="2025-06-01",
                 lines=[{"description": "Sale", "quantity": 1, "unitPrice": 1000}])
        self.cmd("invoice.approve", invoiceId="fy-sale")
        self.cmd("invoice.issue", invoiceId="fy-sale", postingDate="2025-06-01")
        before = self.report(from_date="2025-01-01", through_date="2025-12-31")
        self.assertEqual(before["profitLoss"], {"revenue": 1000, "expense": 0, "net": 1000})
        self.cmd("fiscal.year.close", throughDate="2025-12-31",
                 reason="Synthetic fiscal close")
        after = self.report(from_date="2025-01-01", through_date="2025-12-31")
        self.assertEqual(after["profitLoss"], before["profitLoss"])
        self.assertEqual(after["profitLossReconciliation"], {
            "basis": "operational-excludes-fiscal-year-close",
            "postCloseLedgerMovements": {"revenue": 0, "expense": 0, "net": 0},
            "closingAdjustmentNet": -1000, "reconciled": True})
        self.assertEqual(after["trialBalance"]["totalDebit"], 1000)
        self.assertEqual(after["trialBalance"]["totalCredit"], 1000)
        self.assertEqual(after["balanceSheet"]["unclosedProfitLoss"], 0)
        self.assertEqual(after["balanceSheet"]["capital"], 1000)
        self.assertTrue(any(row["sourceType"] == "fiscal.year.close" for row in
                            after["accountStatements"]["4000"]))
        next_period = self.report(from_date="2026-01-01", through_date="2026-10-21")
        self.assertEqual(next_period["profitLoss"]["net"], 0)
        self.assertEqual(next_period["profitLossReconciliation"]["closingAdjustmentNet"], 0)

    def test_closed_year_with_expense_and_future_sale_keeps_period_distinct(self):
        self.cmd("party.register", partyId="customer", name="Buyer", kind="customer")
        self.cmd("party.register", partyId="vendor", name="Supplier", kind="vendor")
        self.cmd("bill.create", billId="cost", partyId="vendor", documentDate="2025-03-01",
                 lines=[{"description": "Cost", "quantity": 1, "unitPrice": 250}])
        self.cmd("bill.approve", billId="cost")
        self.cmd("bill.issue", billId="cost", postingDate="2025-03-01")
        self.cmd("fiscal.year.close", throughDate="2025-12-31", reason="Closed loss")
        self.cmd("invoice.create", invoiceId="next", partyId="customer",
                 documentDate="2026-01-03",
                 lines=[{"description": "Service", "quantity": 1, "unitPrice": 300}])
        self.cmd("invoice.approve", invoiceId="next")
        self.cmd("invoice.issue", invoiceId="next", postingDate="2026-01-03")
        all_time = self.report()
        self.assertEqual(all_time["profitLoss"], {"revenue": 300, "expense": 250, "net": 50})
        self.assertEqual(all_time["profitLossReconciliation"]["postCloseLedgerMovements"]["net"], 300)
        self.assertEqual(all_time["profitLossReconciliation"]["closingAdjustmentNet"], 250)
        self.assertEqual(all_time["balanceSheet"]["unclosedProfitLoss"], 300)
        self.assertEqual(self.report(from_date="2025-01-01", through_date="2025-12-31")
                         ["profitLoss"]["net"], -250)
        self.assertEqual(self.report(from_date="2026-01-01")["profitLoss"]["net"], 300)

    def test_stock_sale_warning_persists_until_cogs_journal_posts(self):
        self.cmd("item.create", itemId="stock", sku="STOCK1", name="Box",
                 kind="goods", unit="pcs")
        self.cmd("item.stock.enable", itemId="stock")
        self.cmd("warehouse.create", warehouseId="W", name="Test warehouse")
        self.cmd("party.register", partyId="supplier", name="Supplier", kind="vendor")
        self.cmd("party.register", partyId="customer", name="Customer", kind="customer")
        self.cmd("bill.create", billId="purchase", partyId="supplier", documentDate="2026-10-01",
                 lines=[{"description": "Boxes", "quantity": 2, "unitPrice": 60,
                         "itemId": "stock"}])
        self.cmd("bill.approve", billId="purchase")
        self.cmd("bill.issue", billId="purchase", postingDate="2026-10-01")
        self.assertEqual(self.report()["stockCostControl"]["purchases"][0]["unpostedQuantity"], 2)
        self.cmd("inventory.receive", warehouseId="W", itemId="stock", quantity=2,
                 billId="purchase", postingDate="2026-10-01")
        self.assertEqual(self.report()["stockCostControl"]["purchases"], [])
        self.cmd("invoice.create", invoiceId="sale", partyId="customer", documentDate="2026-10-02",
                 lines=[{"description": "One box", "quantity": 1, "unitPrice": 100,
                         "itemId": "stock"}])
        self.cmd("invoice.approve", invoiceId="sale")
        self.cmd("invoice.issue", invoiceId="sale", postingDate="2026-10-02")
        pending = self.report()
        self.assertEqual(pending["profitLoss"]["net"], 100)
        self.assertEqual(pending["stockCostControl"]["assessment"], "incomplete")
        self.assertFalse(pending["stockCostControl"]["profitCertified"])
        self.assertEqual(pending["stockCostControl"]["sales"], [{
            "documentId": "sale", "itemId": "stock", "expectedQuantity": 1,
            "postedQuantity": 0, "unpostedQuantity": 1,
            "reason": "stock-issue-and-cogs-pending"}])
        self.cmd("inventory.issue", warehouseId="W", itemId="stock", quantity=1,
                 invoiceId="sale", postingDate="2026-10-03")
        complete = self.report()
        self.assertEqual(complete["profitLoss"]["net"], 40)
        self.assertEqual(complete["stockCostControl"]["sales"], [])
        self.assertEqual(complete["stockCostControl"]["assessment"],
                         "no-unmatched-tracked-lines-detected")
        self.assertFalse(complete["stockCostControl"]["profitCertified"])
        movement_id = next(key for key, row in accounting_view(
            self.state, actor="admin", accounts=USERS)["stockMovements"].items()
            if row["type"] == "inventory.issue")
        self.cmd("inventory.reverse", movementId=movement_id,
                 postingDate="2026-10-04", reason="Reversed COGS for synthetic audit")
        reversed_issue = self.report()
        self.assertEqual(reversed_issue["profitLoss"]["net"], 100)
        self.assertEqual(reversed_issue["stockCostControl"]["sales"][0]["unpostedQuantity"], 1)
        # Historical rows do not reconstruct item stock-tracking state.
        dated = self.report(through_date="2026-10-02")
        self.assertEqual(dated["stockCostControl"]["assessment"], "not-assessed")

    def test_taxed_or_discounted_purchase_has_explicit_valuation_warning(self):
        self.cmd("item.create", itemId="good", sku="GOOD1", name="Stock goods",
                 kind="goods", unit="pcs")
        self.cmd("item.stock.enable", itemId="good")
        self.cmd("warehouse.create", warehouseId="W", name="Warehouse")
        self.cmd("party.register", partyId="vendor", name="Vendor", kind="vendor")
        for i, financials in enumerate(({"tax": 18}, {"discount": 10}), 1):
            document_id = f"b{i}"
            self.cmd("bill.create", billId=document_id, partyId="vendor",
                     documentDate="2026-10-02", lines=[
                         {"description": "Stock", "quantity": 2, "unitPrice": 100,
                          "itemId": "good"}], **financials)
            self.cmd("bill.approve", billId=document_id)
            self.cmd("bill.issue", billId=document_id, postingDate="2026-10-02")
            before = self.report()
            self.assertIn({"documentId": document_id, "itemId": "good",
                           "expectedQuantity": 2, "postedQuantity": 0,
                           "unpostedQuantity": 2, "reason": "valuation-policy-required"},
                          before["stockCostControl"]["purchases"])
            with self.assertRaisesRegex(ValueError, "Allocate tax/discount"):
                self.cmd("inventory.receive", warehouseId="W", itemId="good",
                         quantity=2, billId=document_id, postingDate="2026-10-02")
            self.assertEqual(self.report(), before)


if __name__ == "__main__":
    unittest.main()
