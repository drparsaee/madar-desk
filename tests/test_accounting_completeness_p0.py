"""Isolated, auditable correction, account and customer-credit acceptance."""
from pathlib import Path
import tempfile
import unittest

from standalone_accounting import StandaloneAccountingStore


NOW = "2026-10-24T12:00:00Z"
DAY = "2026-10-24"
USERS = {
    "root": {"username": "root", "role": "admin"},
    "viewer": {"username": "viewer", "role": "viewer", "financeView": True},
}


class AccountingP0Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="madar-full-ux-p0-")
        self.addCleanup(tmp.cleanup)
        self.store = StandaloneAccountingStore(
            Path(tmp.name) / "private-only.sqlite3", default_currency="RIAL")

    def read(self):
        return self.store.read(actor="root", accounts=USERS)

    def cmd(self, command_type, *, event_id=None, **args):
        rev = self.read()["revision"]
        return self.store.command({
            "type": command_type, "eventId": event_id or f"evt-{rev+1}", **args},
            actor="root", accounts=USERS, now=NOW, expected_revision=rev)

    def create(self, kind="invoice"):
        person = "BUYER" if kind == "invoice" else "VENDOR"
        self.cmd("party.register", partyId=person, name="Original name",
                 kind="customer" if kind == "invoice" else "vendor")
        self.cmd(kind+".create", **{kind+"Id": "DOC-A"}, partyId=person,
                 documentDate="2026-10-20",
                 lines=[{"description": "Original line", "quantity": 2, "unitPrice": 500}])
        self.cmd(kind+".approve", **{kind+"Id": "DOC-A"})
        self.cmd(kind+".issue", **{kind+"Id": "DOC-A"}, postingDate="2026-10-22")

    def correct(self, kind="invoice", **overrides):
        fields = {kind+"Id": "DOC-A", "replacementId": "DOC-B",
                  "reason": "Price correction with approval",
                  "documentDate": "2026-10-24", "postingDate": DAY,
                  "lines": [{"description": "Revised line",
                             "quantity": 3, "unitPrice": 250}]}
        fields.update(overrides)
        return self.cmd(kind+".correct", **fields)

    def test_issued_sale_corrected_as_atomic_reversal_plus_linked_draft(self):
        self.create()
        outcome = self.correct()
        view = outcome["view"]
        original, replacement = view["invoices"]["DOC-A"], view["invoices"]["DOC-B"]
        self.assertEqual(original["status"], "reversed")
        self.assertEqual(original["correctedBy"], "DOC-B")
        self.assertEqual(replacement["status"], "draft")
        self.assertEqual(replacement["correctionOf"], "DOC-A")
        self.assertEqual(replacement["sourceType"], "correction")
        self.assertEqual(replacement["total"], 750)
        self.assertEqual(len(view["journals"]), 2)
        self.assertEqual(view["parties"]["BUYER"]["receivable"], 0)
        self.assertIn(view["journals"][0]["id"], view["reversed"])
        self.assertEqual(view["journals"][1]["reversalOf"], view["journals"][0]["id"])
        for j in view["journals"]:
            self.assertEqual(sum(x["debit"] for x in j["lines"]),
                             sum(x["credit"] for x in j["lines"]))
        self.cmd("invoice.approve", invoiceId="DOC-B")
        self.cmd("invoice.issue", invoiceId="DOC-B", postingDate=DAY)
        final = self.read()["view"]
        self.assertEqual(final["parties"]["BUYER"]["receivable"], 750)
        self.assertEqual(len(final["journals"]), 3)

    def test_purchase_correction_and_invalid_replacement_leave_no_partial_change(self):
        self.create("bill")
        before = self.read()
        with self.assertRaises(ValueError):
            self.correct("bill", lines=[
                {"description": "Invalid zero quantity", "quantity": 0, "unitPrice": 300}])
        self.assertEqual(self.read(), before)
        result = self.correct("bill")
        self.assertEqual(result["view"]["bills"]["DOC-A"]["status"], "reversed")
        self.assertEqual(result["view"]["parties"]["VENDOR"]["payable"], 0)
        self.assertEqual(result["view"]["bills"]["DOC-B"]["total"], 750)

    def test_paid_document_cannot_be_corrected_without_reversing_receipt(self):
        self.create()
        self.cmd("funds.deposit", accountId="1010", amount=1000,
                 postingDate="2026-10-23", note="Synthetic bank funding")
        settle = self.cmd("receipt.record", receiptId="REC-A", partyId="BUYER",
                          accountId="1010", postingDate=DAY,
                          allocations=[{"invoiceId": "DOC-A", "amount": 300}])
        rev = settle["revision"]
        with self.assertRaisesRegex(ValueError, "wholly unsettled"):
            self.correct()
        self.assertEqual(self.read()["revision"], rev)
        self.cmd("journal.reverse",
                 journalId=settle["view"]["receipts"]["REC-A"]["journalId"],
                 postingDate=DAY, reason="Undo receipt before invoice correction")
        self.correct()
        self.assertEqual(self.read()["view"]["parties"]["BUYER"]["receivable"], 0)

    def test_party_edits_audited_and_credit_limit_blocks_excessive_sale(self):
        self.cmd("party.register", partyId="BUYER", name="First", kind="customer",
                 creditLimit=1200)
        updated = self.cmd("party.update", partyId="BUYER", name="Edited",
                           creditLimit=1100, reason="Verified customer details")
        party = updated["view"]["parties"]["BUYER"]
        self.assertEqual(party["name"], "Edited")
        self.assertEqual(party["creditLimit"], 1100)
        self.assertEqual(len(party["changeHistory"]), 1)
        self.assertEqual(party["changeHistory"][0]["before"]["name"], "First")
        self.cmd("invoice.create", invoiceId="INV-A", partyId="BUYER",
                 documentDate="2026-10-20",
                 lines=[{"description": "Sale", "quantity": 2, "unitPrice": 500}])
        self.cmd("invoice.approve", invoiceId="INV-A")
        self.cmd("invoice.issue", invoiceId="INV-A", postingDate=DAY)
        self.cmd("invoice.create", invoiceId="INV-B", partyId="BUYER",
                 documentDate="2026-10-20",
                 lines=[{"description": "Additional", "quantity": 1, "unitPrice": 200}])
        self.cmd("invoice.approve", invoiceId="INV-B")
        before = self.read()
        with self.assertRaisesRegex(ValueError, "credit limit"):
            self.cmd("invoice.issue", invoiceId="INV-B", postingDate=DAY)
        self.assertEqual(self.read(), before)
        with self.assertRaisesRegex(ValueError, "below current receivable"):
            self.cmd("party.update", partyId="BUYER", creditLimit=500,
                     reason="Invalid limit")
        with self.assertRaisesRegex(ValueError, "remove customer role"):
            self.cmd("party.update", partyId="BUYER", kind="vendor",
                     reason="Illegal historical role change")
        viewer_rev = self.read()["revision"]
        with self.assertRaises(PermissionError):
            self.store.command({
                "type": "party.update", "eventId": "viewer-tamper", "partyId": "BUYER",
                "name": "Forged", "reason": "Unauthorized"
            }, actor="viewer", accounts=USERS,
                now=NOW, expected_revision=viewer_rev)

    def test_hierarchical_account_levels_and_parent_types(self):
        self.cmd("account.create", accountId="REV.M", name="Sales subsidiary",
                 kind="revenue", liquid=False, level="moein", parentId="4000")
        self.cmd("account.create", accountId="REV.T", name="Detailed revenue",
                 kind="revenue", liquid=False, level="tafsili", parentId="REV.M")
        accounts = self.read()["view"]["accounts"]
        self.assertEqual(accounts["REV.M"]["parentId"], "4000")
        self.assertEqual(accounts["REV.T"]["parentId"], "REV.M")
        self.assertEqual(accounts["REV.T"]["level"], "tafsili")
        before = self.read()
        with self.assertRaisesRegex(ValueError, "Invalid parent"):
            self.cmd("account.create", accountId="WRONG", name="Wrong parent",
                     kind="revenue", liquid=False, level="tafsili", parentId="4000")
        with self.assertRaisesRegex(ValueError, "Invalid parent"):
            self.cmd("account.create", accountId="WRONG2", name="Wrong nature",
                     kind="expense", liquid=False, level="moein", parentId="4000")
        with self.assertRaisesRegex(ValueError, "must not be liquid"):
            self.cmd("account.create", accountId="BAD.CASH", name="Money leaf",
                     kind="asset", liquid=True, level="moein", parentId="1000")
        self.assertEqual(self.read(), before)
        self.cmd("party.register", partyId="BUYER", name="Independent buyer", kind="customer")
        self.cmd("invoice.create", invoiceId="NEW", partyId="BUYER",
                 documentDate="2026-10-23",
                 lines=[{"description": "Item", "quantity": 2,
                         "unitPrice": 300, "accountId": "REV.T"}])
        self.cmd("invoice.approve", invoiceId="NEW")
        self.cmd("invoice.issue", invoiceId="NEW", postingDate=DAY)
        self.assertEqual(self.read()["view"]["accounts"]["REV.T"]["debitMinusCredit"], -600)

    def test_full_unpaid_sale_and_purchase_returns_keep_ledger_and_reference(self):
        for kind in ("invoice", "bill"):
            with self.subTest(kind=kind):
                self.setUp()
                self.create(kind)
                before=self.read()["view"]
                self.assertEqual(len(before["journals"]), 1)
                self.cmd(kind+".return", **{kind+"Id":"DOC-A"},
                         returnId="RET-1",postingDate=DAY,
                         reason="Entire order returned before payment")
                after=self.read()["view"]
                old=after["invoices" if kind=="invoice" else "bills"]["DOC-A"]
                self.assertEqual(old["status"],"reversed")
                self.assertEqual(old["returnId"],"RET-1")
                self.assertEqual(after["returns"]["RET-1"]["amount"],1000)
                self.assertEqual(len(after["journals"]),2)
                self.assertEqual(after["parties"]["BUYER" if kind=="invoice" else "VENDOR"][
                    "receivable" if kind=="invoice" else "payable"],0)
                self.assertEqual(
                    sum(x["debit"] for x in after["journals"][1]["lines"]),
                    sum(x["credit"] for x in after["journals"][1]["lines"]))
                prior=self.read()
                with self.assertRaises(ValueError):
                    self.cmd(kind+".return", **{kind+"Id":"DOC-A"},
                             returnId="RET-2",postingDate=DAY,reason="Duplicate")
                self.assertEqual(self.read(),prior)

    def test_no_full_return_when_partially_settled(self):
        self.create()
        self.cmd("receipt.record",receiptId="RC-1",partyId="BUYER",
                 accountId="1010",postingDate=DAY,
                 allocations=[{"invoiceId":"DOC-A","amount":100}])
        previous=self.read()
        with self.assertRaisesRegex(ValueError,"entirely unsettled"):
            self.cmd("invoice.return",invoiceId="DOC-A",returnId="RET-1",
                     postingDate=DAY,reason="Invalid unpaid assumption")
        self.assertEqual(self.read(),previous)


if __name__ == "__main__":
    unittest.main()
