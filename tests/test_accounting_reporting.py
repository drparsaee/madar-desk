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


if __name__ == "__main__":
    unittest.main()
