"""End-to-end event/CAS/SQLite tests; synthetic data only."""
from pathlib import Path
import tempfile
import unittest

from standalone_accounting import StandaloneAccountingStore


NOW = "2026-10-24T18:00:00Z"
USERS = {"root": {"username": "root", "role": "admin"},
         "viewer": {"username": "viewer", "role": "viewer", "financeView": True}}


class ExtendedAccountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-extended-qa-")
        self.addCleanup(self.tmp.cleanup)
        self.store = StandaloneAccountingStore(
            Path(self.tmp.name) / "standalone-accounting.sqlite3",
            default_currency="RIAL")

    def read(self):
        return self.store.read(actor="root", accounts=USERS)

    def cmd(self, command_type, **fields):
        before = self.read()
        result = self.store.command(
            {"type": command_type, "eventId": f"test.{before['revision']+1}", **fields},
            actor="root", accounts=USERS, expected_revision=before["revision"],
            now=NOW)
        self.assertEqual(result["revision"], before["revision"]+1)
        return result

    def seed_sale(self, *, doc_id="INV1", qty=2, price=500, item_id=None):
        if "BUYER" not in self.read()["view"]["parties"]:
            self.cmd("party.register", partyId="BUYER", name="Customer", kind="customer")
        row = {"description": "Synthetic goods", "quantity": qty,
               "unitPrice": price}
        if item_id:
            row["itemId"] = item_id
        self.cmd("invoice.create", invoiceId=doc_id, partyId="BUYER",
                 documentDate="2026-10-10", lines=[row])
        self.cmd("invoice.approve", invoiceId=doc_id)
        self.cmd("invoice.issue", invoiceId=doc_id, postingDate="2026-10-11")

    def seed_bill(self, *, item_id=None):
        self.cmd("party.register", partyId="VENDOR", name="Vendor", kind="vendor")
        row = {"description": "Synthetic input", "quantity": 5, "unitPrice": 140}
        if item_id:
            row["itemId"] = item_id
        self.cmd("bill.create", billId="BILL1", partyId="VENDOR",
                 documentDate="2026-10-10", lines=[row])
        self.cmd("bill.approve", billId="BILL1")
        self.cmd("bill.issue", billId="BILL1", postingDate="2026-10-10")

    def test_cheques_recognize_no_cash_before_clearing_and_reversal_safe(self):
        self.seed_sale()
        a = self.cmd("cheque.register", chequeId="CH1", direction="receipt",
                     documentId="INV1", bankAccountId="1010", dueDate="2026-10-12",
                     amount=500, reference="BANK1")
        self.assertEqual(a["view"]["parties"]["BUYER"]["receivable"], 1000)
        self.assertEqual(len(a["view"]["journals"]), 1)
        self.cmd("cheque.deposit", chequeId="CH1")
        paid = self.cmd("cheque.clear", chequeId="CH1", postingDate="2026-10-13")
        self.assertEqual(paid["view"]["parties"]["BUYER"]["receivable"], 500)
        self.assertEqual(paid["view"]["cheques"]["CH1"]["status"], "cleared")
        self.assertEqual(paid["view"]["accounts"]["1010"]["debitMinusCredit"], 500)
        with self.assertRaisesRegex(ValueError, "clearance"):
            self.cmd("cheque.return", chequeId="CH1", reason="Attempted invalid bounce")
        reversal = self.cmd("journal.reverse", journalId=paid["view"]["cheques"]["CH1"]["journalId"],
                            postingDate="2026-10-14", reason="Bank found cheque dishonoured")
        self.assertEqual(reversal["view"]["cheques"]["CH1"]["status"], "reversed")
        self.assertEqual(reversal["view"]["parties"]["BUYER"]["receivable"], 1000)
        self.assertEqual(reversal["view"]["accounts"]["1010"]["debitMinusCredit"], 0)
        self.assertEqual(len(reversal["view"]["journals"]), 3)

    def test_pending_cheque_must_be_cancelled_before_full_invoice_return(self):
        self.seed_sale()
        self.cmd("cheque.register", chequeId="CH-PENDING", direction="receipt",
                 documentId="INV1", bankAccountId="1010", dueDate="2026-10-12",
                 amount=500, reference="UNSETTLED-CHEQUE")
        revision=self.read()["revision"]
        with self.assertRaisesRegex(ValueError, "linked cheques"):
            self.cmd("invoice.return", invoiceId="INV1", returnId="RETURN-A",
                     postingDate="2026-10-15", reason="Customer returned full order")
        self.assertEqual(self.read()["revision"], revision)
        self.cmd("cheque.return", chequeId="CH-PENDING",
                 reason="Instrument dishonoured")
        with self.assertRaisesRegex(ValueError, "linked cheques"):
            self.cmd("invoice.return", invoiceId="INV1", returnId="RETURN-A",
                     postingDate="2026-10-15", reason="Return pending cheque still re-deliverable")
        self.cmd("cheque.cancel", chequeId="CH-PENDING",
                 reason="Original sale is void; void pending instrument")
        returned=self.cmd("invoice.return", invoiceId="INV1", returnId="RETURN-A",
                          postingDate="2026-10-15", reason="Customer returned full order")
        self.assertEqual(returned["view"]["invoices"]["INV1"]["status"], "reversed")
        self.assertEqual(returned["view"]["returns"]["RETURN-A"]["amount"], 1000)
        self.assertEqual(returned["view"]["cheques"]["CH-PENDING"]["status"], "cancelled")
        self.assertEqual(returned["view"]["parties"]["BUYER"]["receivable"], 0)
        with self.assertRaisesRegex(ValueError, "returned"):
            self.cmd("cheque.redeliver", chequeId="CH-PENDING",
                     reason="Illegal revival of cancelled instrument")

    def test_cheque_payables_return_and_unique_bank_reference(self):
        self.seed_bill()
        self.cmd("funds.deposit", accountId="1010", amount=1000,
                 postingDate="2026-10-10", note="Synthetic opening funding")
        self.cmd("cheque.register", chequeId="CH2", direction="payment",
                 documentId="BILL1", bankAccountId="1010", dueDate="2026-10-13",
                 amount=700, reference="REF-B")
        with self.assertRaisesRegex(ValueError, "cheque reference"):
            self.cmd("cheque.register", chequeId="CH3", direction="payment",
                     documentId="BILL1", bankAccountId="1010", dueDate="2026-10-14",
                     amount=100, reference="REF-B")
        self.cmd("cheque.return", chequeId="CH2", reason="Lost payee instrument")
        self.cmd("cheque.redeliver", chequeId="CH2", reason="Reissued pending cheque")
        clearing = self.cmd("cheque.clear", chequeId="CH2", postingDate="2026-10-13")
        self.assertEqual(clearing["view"]["parties"]["VENDOR"]["payable"], 0)
        self.assertEqual(clearing["view"]["accounts"]["1010"]["debitMinusCredit"], 300)

    def test_bank_statement_reconciliation_requires_exact_journal(self):
        self.cmd("funds.deposit", accountId="1010", amount=800,
                 postingDate="2026-10-14", note="Authenticated test deposit")
        self.cmd("bank.statement.add", statementId="ST1", accountId="1010",
                 date="2026-10-14", amount=800, reference="BANK-ST-1")
        first = self.read()
        j = first["view"]["journals"][0]["id"]
        self.cmd("bank.statement.match", statementId="ST1", journalId=j,
                 reason="Statement matched by accountant")
        with self.assertRaisesRegex(ValueError, "Unmatch bank"):
            self.cmd("journal.reverse", journalId=j, postingDate="2026-10-15",
                     reason="Invalid reversal")
        self.cmd("bank.statement.unmatch", statementId="ST1",
                 reason="Bank dispute re-opened")
        self.cmd("journal.reverse", journalId=j, postingDate="2026-10-15",
                 reason="Verified correction")
        self.assertIsNone(self.read()["view"]["bankStatements"]["ST1"]["journalId"])

    def test_instalments_are_schedule_only_without_duplicate_ar(self):
        self.seed_sale()
        out = self.cmd("installments.create", planId="PLAN1", direction="receipt",
                       documentId="INV1", schedule=[
                           {"dueDate": "2026-11-01", "amount": 400},
                           {"dueDate": "2026-12-01", "amount": 600}])
        self.assertEqual(out["view"]["installmentPlans"]["PLAN1"]["active"], True)
        self.assertEqual(len(out["view"]["journals"]), 1)
        self.assertEqual(out["view"]["parties"]["BUYER"]["receivable"], 1000)
        with self.assertRaisesRegex(ValueError, "active instalment"):
            self.cmd("installments.create", planId="PLAN2", direction="receipt",
                     documentId="INV1", schedule=[
                         {"dueDate": "2026-11-01", "amount": 200}])
        self.cmd("installments.cancel", planId="PLAN1", reason="New payment agreement")

    def test_inventory_receipt_fifo_sale_and_warehouse_transfer(self):
        self.cmd("item.create", itemId="ITEM1", sku="GOOD1", name="Box",
                 kind="goods", unit="عدد")
        self.cmd("item.stock.enable", itemId="ITEM1")
        self.cmd("warehouse.create", warehouseId="W1", name="Primary")
        self.cmd("warehouse.create", warehouseId="W2", name="Secondary")
        self.seed_bill(item_id="ITEM1")
        self.cmd("inventory.receive", warehouseId="W1", itemId="ITEM1",
                 quantity=5, billId="BILL1", postingDate="2026-10-11")
        self.assertEqual(self.read()["view"]["stock"]["W1"]["ITEM1"]["value"], 700)
        self.cmd("inventory.transfer", warehouseId="W1", itemId="ITEM1",
                 quantity=2, toWarehouseId="W2", postingDate="2026-10-12",
                 reason="Warehouse relocation")
        self.seed_sale(item_id="ITEM1")
        output = self.cmd("inventory.issue", warehouseId="W2", itemId="ITEM1",
                          quantity=2, invoiceId="INV1", postingDate="2026-10-13")
        self.assertEqual(output["view"]["stock"]["W2"]["ITEM1"]["quantity"], 0)
        self.assertEqual(output["view"]["stock"]["W1"]["ITEM1"]["value"], 420)
        self.assertEqual(output["view"]["accounts"]["1300"]["debitMinusCredit"], 420)
        self.assertEqual(output["view"]["accounts"]["5300"]["debitMinusCredit"], 280)
        with self.assertRaisesRegex(ValueError, "linked inventory"):
            self.cmd("journal.reverse",
                     journalId=output["view"]["bills"]["BILL1"]["postedEntryId"],
                     postingDate="2026-10-14", reason="Attempt stock history deletion")
        issue_id = next(k for k,v in output["view"]["stockMovements"].items()
                        if v["type"] == "inventory.issue")
        corrected = self.cmd("inventory.reverse", movementId=issue_id,
                             postingDate="2026-10-14", reason="Customer order cancelled")
        self.assertEqual(corrected["view"]["accounts"]["5300"]["debitMinusCredit"], 0)
        self.assertEqual(corrected["view"]["stock"]["W2"]["ITEM1"]["value"], 280)
        self.assertEqual(corrected["view"]["stock"]["W2"]["ITEM1"]["quantity"], 2)
        self.assertTrue(corrected["view"]["stockMovements"][issue_id]["reversed"])
        issued_journal=corrected["view"]["invoices"]["INV1"]["postedEntryId"]
        self.cmd("journal.reverse",journalId=issued_journal,
                 postingDate="2026-10-15",reason="Linked stock issue already undone")

    def test_payroll_two_stage_and_explicit_tax_rule(self):
        self.cmd("funds.deposit", accountId="1010", amount=80000,
                 postingDate="2026-10-10", note="Synthetic capital")
        self.cmd("tax.rule.set", ruleId="TEST-RATE", name="Configurable only",
                 rateBasisPoints=600, effectiveFrom="2026-10-01",
                 reason="Accounting staff policy, not legal certification")
        out = self.cmd("payroll.accrue", payrollId="PAY1", employeeId="EMP1",
                       period="2026-10-01", gross=10000, withholding=2000,
                       reason="Synthetic signed pay slip")
        self.assertEqual(out["view"]["payroll"]["PAY1"]["status"], "accrued")
        self.assertEqual(out["view"]["accounts"]["2300"]["debitMinusCredit"], -8000)
        self.cmd("payroll.pay", payrollId="PAY1", postingDate="2026-10-24",
                 accountId="1010")
        final = self.read()["view"]
        self.assertEqual(final["accounts"]["2300"]["debitMinusCredit"], 0)
        self.assertEqual(final["accounts"]["2400"]["debitMinusCredit"], -2000)
        self.assertEqual(final["payroll"]["PAY1"]["status"], "paid")
        remitted = self.cmd("payroll.remit", payrollId="PAY1",
                            postingDate="2026-10-24", accountId="1010")
        self.assertEqual(remitted["view"]["accounts"]["2400"]["debitMinusCredit"], 0)
        self.assertTrue(remitted["view"]["payroll"]["PAY1"]["remittanceJournalId"])
        self.cmd("party.register", partyId="BUYER", name="Tax customer", kind="customer")
        self.cmd("invoice.create", invoiceId="TAX1", partyId="BUYER",
                 documentDate="2026-10-23",
                 lines=[{"description": "Item", "quantity": 2, "unitPrice": 500}],
                 tax=60, taxRuleId="TEST-RATE")
        with self.assertRaisesRegex(ValueError, "Tax amount does not match"):
            self.cmd("invoice.create", invoiceId="TAX-FAKE", partyId="BUYER",
                     documentDate="2026-10-23",
                     lines=[{"description": "Item", "quantity": 2, "unitPrice": 500}],
                     tax=59,taxRuleId="TEST-RATE")
        self.cmd("tax.rule.set", ruleId="TEST-RATE", name="Later internal rate",
                 rateBasisPoints=1000, effectiveFrom="2026-10-24",
                 reason="Later change must not corrupt earlier effective rate")
        self.cmd("invoice.create", invoiceId="TAX-HIST", partyId="BUYER",
                 documentDate="2026-10-23",
                 lines=[{"description": "Earlier rate", "quantity": 2, "unitPrice": 500}],
                 tax=60,taxRuleId="TEST-RATE")
        self.cmd("invoice.create", invoiceId="TAX-NEW", partyId="BUYER",
                 documentDate="2026-10-24",
                 lines=[{"description": "Current rate", "quantity": 2, "unitPrice": 500}],
                 tax=100,taxRuleId="TEST-RATE")
        final=self.read()["view"]["invoices"]
        self.assertEqual(final["TAX-HIST"]["taxRuleRate"],600)
        self.assertEqual(final["TAX-NEW"]["taxRuleRate"],1000)

    def test_close_year_transfers_profit_not_cash_and_prevents_backdate(self):
        self.cmd("funds.deposit", accountId="1010", amount=10000,
                 postingDate="2025-01-01", note="Prior year synthetic capital")
        self.cmd("party.register", partyId="BUYER", name="Customer", kind="customer")
        self.cmd("invoice.create", invoiceId="YEAR1", partyId="BUYER",
                 documentDate="2025-11-30",
                 lines=[{"description": "Sale", "quantity": 2, "unitPrice": 250}])
        self.cmd("invoice.approve", invoiceId="YEAR1")
        self.cmd("invoice.issue", invoiceId="YEAR1", postingDate="2025-12-01")
        result = self.cmd("fiscal.year.close", throughDate="2025-12-31",
                          reason="Reviewed annual closing")
        self.assertEqual(result["view"]["accounts"]["4000"]["debitMinusCredit"], 0)
        self.assertEqual(result["view"]["accounts"]["3100"]["debitMinusCredit"], -500)
        self.assertEqual(result["view"]["closedThrough"], "2025-12-31")
        with self.assertRaisesRegex(ValueError, "closed period"):
            self.cmd("funds.deposit", accountId="1010", amount=1,
                     postingDate="2025-12-20", note="Backdate not allowed")

    def test_company_profile_and_document_due_date_are_audited_and_bounded(self):
        self.cmd("company.profile.set",legalName="Synthetic Printing Co",
                 address="Private test directory",phone="000-000",
                 nationalId="TEST-ID",economicCode="TEST-EC",
                 postalCode="0000000000",reason="Reviewed test company profile")
        profile=self.read()["view"]["companyProfile"]
        self.assertEqual(profile["legalName"],"Synthetic Printing Co")
        self.assertEqual(len(profile["history"]),1)
        with self.assertRaisesRegex(ValueError,"makes no changes"):
            self.cmd("company.profile.set",legalName="Synthetic Printing Co",
                     address="Private test directory",phone="000-000",
                     nationalId="TEST-ID",economicCode="TEST-EC",
                     postalCode="0000000000",reason="No change should fail")
        self.cmd("company.profile.set",legalName="Synthetic Printer LLC",
                 address="Private test directory",phone="000-000",
                 nationalId="TEST-ID",economicCode="TEST-EC",
                 postalCode="0000000000",reason="Reviewed legal name correction")
        self.assertEqual(len(self.read()["view"]["companyProfile"]["history"]),2)
        self.cmd("party.register",partyId="BUYER",name="Duedate customer",kind="customer")
        self.cmd("invoice.create",invoiceId="DUE-A",partyId="BUYER",
                 documentDate="2026-10-15",dueDate="2026-11-15",
                 lines=[{"description":"Timed sale","quantity":2,"unitPrice":100}])
        self.assertEqual(self.read()["view"]["invoices"]["DUE-A"]["dueDate"],
                         "2026-11-15")
        self.cmd("invoice.approve",invoiceId="DUE-A")
        self.cmd("invoice.issue",invoiceId="DUE-A",postingDate="2026-10-15")
        with self.assertRaisesRegex(ValueError,"due date cannot precede"):
            self.cmd("invoice.create",invoiceId="DUE-INVALID",partyId="BUYER",
                     documentDate="2026-10-20",dueDate="2026-10-19",
                     lines=[{"description":"Timed sale","quantity":1,"unitPrice":100}])

    def test_bank_csv_batch_is_atomic_and_duplicate_safe(self):
        self.cmd("funds.deposit",accountId="1010",amount=4000,
                 postingDate="2026-10-10",note="Evidence")
        before=self.read()
        batch=[
            {"statementId":"ROW1","accountId":"1010","date":"2026-10-10",
             "amount":4000,"reference":"BANK-REF-1"},
            {"statementId":"ROW2","accountId":"1010","date":"2026-10-10",
             "amount":0,"reference":"BANK-REF-2"},
        ]
        with self.assertRaisesRegex(ValueError,"Invalid signed"):
            self.cmd("bank.statement.batch",rows=batch)
        self.assertEqual(self.read(),before)
        batch[1]["amount"]=-200
        result=self.cmd("bank.statement.batch",rows=batch)
        self.assertEqual(len(result["view"]["bankStatements"]),2)
        self.assertEqual(result["revision"],before["revision"]+1)
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            self.cmd("bank.statement.batch",rows=batch)

    def test_jalali_fiscal_boundary_and_inconsistent_start_are_rejected(self):
        self.cmd("funds.deposit",accountId="1010",amount=700,
                 postingDate="2025-03-21",note="FY1404 synthetic fund")
        self.cmd("fiscal.year.close",startDate="2025-03-21",
                 throughDate="2026-03-20",periodId="FY1404",
                 reason="Persian fiscal year 1404 close")
        closed=self.read()
        self.assertEqual(closed["view"]["fiscalYears"][0]["periodId"],"FY1404")
        self.assertEqual(closed["view"]["closedThrough"],"2026-03-20")
        with self.assertRaisesRegex(ValueError,"contiguous"):
            self.cmd("fiscal.year.close",startDate="2026-03-22",
                     throughDate="2026-09-30",periodId="BAD-FY",
                     reason="Omitted a day")

    def test_historical_custom_account_same_as_new_system_id_remains_replayable(self):
        # Build a synthetic event chain using the *previous* default account
        # catalog, then replay it with the expanded catalog restored.
        import accounting_core as core
        old_defaults = core._DEFAULT_ACCOUNTS
        state = core.empty_rial_accounting_state()
        try:
            core._DEFAULT_ACCOUNTS = tuple(a for a in old_defaults
                if a[0] not in core._NEW_SYSTEM_ACCOUNTS)
            events = [
                {"type":"account.create","eventId":"historical.1",
                 "accountId":"1300","name":"Historical custom 1300",
                 "kind":"asset","liquid":False},
                {"type":"funds.deposit","eventId":"historical.2",
                 "accountId":"1010","amount":1000,
                 "postingDate":"2026-10-20","note":"Synthetic old deposit"},
                {"type":"journal.manual","eventId":"historical.3",
                 "postingDate":"2026-10-20","note":"Old authorized stock account",
                 "lines":[{"accountId":"1300","debit":100,"credit":0},
                          {"accountId":"1010","debit":0,"credit":100}]},
            ]
            for command in events:
                state = core.apply_accounting_command(state,command,actor="root",
                    accounts=USERS,now=NOW)["state"]
        finally:
            core._DEFAULT_ACCOUNTS = old_defaults
        self.assertTrue(core.validate_accounting_state(state))
        legacy = core.accounting_view(state,actor="root",accounts=USERS)
        self.assertFalse(legacy["accounts"]["1300"]["system"])
        self.assertEqual(legacy["accounts"]["1300"]["debitMinusCredit"],100)
        self.assertEqual(len(legacy["journals"]),2)
        revised = core.apply_accounting_command(state,{
            "type":"bank.statement.add","eventId":"legacy.bank",
            "statementId":"ST-LEG","accountId":"1010",
            "date":"2026-10-20","amount":1000,"reference":"LEGACY-ST"},
            actor="root",accounts=USERS,now=NOW)
        self.assertTrue(core.validate_accounting_state(revised["state"]))


if __name__ == "__main__":
    unittest.main()
