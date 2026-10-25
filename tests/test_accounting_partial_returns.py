"""Quantity-accurate partial sales/purchase returns, on synthetic in-memory ledgers."""

from copy import deepcopy
import unittest

from accounting_core import (
    accounting_view,
    apply_accounting_command,
    empty_accounting_state,
    empty_rial_accounting_state,
    validate_accounting_state,
)


NOW = "2026-10-24T12:00:00Z"
POST = "2026-10-15"
USERS = [{"username": "admin", "role": "admin"}]


class PartialReturnTests(unittest.TestCase):
    def setUp(self):
        self.state = empty_rial_accounting_state()
        self.sequence = 0

    def cmd(self, command_type, **fields):
        self.sequence += 1
        command = {"type": command_type, "eventId": "E" + str(self.sequence), **fields}
        output = apply_accounting_command(
            self.state, command, actor="admin", accounts=USERS, now=NOW)
        self.state = output["state"]
        self.assertTrue(output["changed"])
        self.assertTrue(validate_accounting_state(self.state))
        return output["result"]

    def view(self):
        return accounting_view(self.state, actor="admin", accounts=USERS)

    def seed(self, kind="invoice", *, lines=None, discount=110, tax=99):
        sales = kind == "invoice"
        party = "BUYER" if sales else "VENDOR"
        self.cmd("party.register", partyId=party, name="Synthetic party",
                 kind="customer" if sales else "vendor")
        self.cmd(kind + ".create", **{kind + "Id": "DOC"}, partyId=party,
                 documentDate="2026-10-10",
                 lines=lines or [
                     {"description": "Large", "quantity": 2, "unitPrice": 500},
                     {"description": "Small", "quantity": 1, "unitPrice": 100},
                 ], discount=discount, tax=tax)
        self.cmd(kind + ".approve", **{kind + "Id": "DOC"})
        self.cmd(kind + ".issue", **{kind + "Id": "DOC"}, postingDate=POST)

    def ret(self, kind="invoice", *, ret_id="RET1", lines=None):
        arguments = {kind + "Id": "DOC", "returnId": ret_id, "postingDate": POST,
                     "reason": "Verified partial return"}
        if lines is not None:
            arguments["lines"] = lines
        return self.cmd(kind + ".return", **arguments)

    def test_multiple_partial_sales_notes_prorate_discount_tax_and_balance_exactly(self):
        self.seed()
        note1 = self.ret(lines=[{"lineIndex": 0, "quantity": 1}])
        self.assertEqual((note1["amount"], note1["discount"], note1["tax"]),
                         (495, 50, 45))
        note2 = self.ret(ret_id="RET2", lines=[{"lineIndex": 1, "quantity": 1}])
        self.assertEqual((note2["amount"], note2["discount"], note2["tax"]),
                         (99, 10, 9))
        note3 = self.ret(ret_id="RET3", lines=[{"lineIndex": 0, "quantity": 1}])
        self.assertEqual(note3["amount"], 495)
        view = self.view()
        doc = view["invoices"]["DOC"]
        self.assertEqual(doc["total"], 1089)
        self.assertEqual(doc["status"], "issued")
        self.assertEqual(doc["returnedAmount"], 1089)
        self.assertEqual(doc["returnedQuantities"], [2, 1])
        self.assertEqual(doc["returnIds"], ["RET1", "RET2", "RET3"])
        self.assertEqual(sum(r["amount"] for r in view["returns"].values()), 1089)
        self.assertEqual(sum(r["discount"] for r in view["returns"].values()), 110)
        self.assertEqual(sum(r["tax"] for r in view["returns"].values()), 99)
        self.assertEqual(view["parties"]["BUYER"]["receivable"], 0)
        self.assertEqual(view["accounts"]["1200"]["debitMinusCredit"], 0)
        self.assertEqual(view["accounts"]["4000"]["debitMinusCredit"], 0)
        self.assertEqual(view["accounts"]["4100"]["debitMinusCredit"], 0)
        self.assertEqual(view["accounts"]["2200"]["debitMinusCredit"], 0)
        self.assertEqual(len(view["journals"]), 4)
        self.assertEqual(view["returns"]["RET1"]["kind"], "partial")
        self.assertEqual(view["returns"]["RET1"]["lines"][0]["lineIndex"], 0)
        self.assertEqual(view["returns"]["RET1"]["journalId"], "J:E5")

    def test_partial_purchase_posts_credit_expense_tax_discount_and_payable(self):
        self.seed("bill")
        note = self.ret("bill", lines=[{"lineIndex": 0, "quantity": 1}])
        self.assertEqual(note["amount"], 495)
        view = self.view()
        self.assertEqual(view["bills"]["DOC"]["status"], "issued")
        self.assertEqual(view["parties"]["VENDOR"]["payable"], 594)
        self.assertEqual(view["accounts"]["2000"]["debitMinusCredit"], -594)
        self.assertEqual(view["accounts"]["5000"]["debitMinusCredit"], 600)
        self.assertEqual(view["accounts"]["5100"]["debitMinusCredit"], -60)
        self.assertEqual(view["accounts"]["5200"]["debitMinusCredit"], 54)
        self.assertEqual(view["returns"]["RET1"]["direction"], "purchase")
        self.assertEqual(view["returns"]["RET1"]["status"], "posted")

    def test_partial_return_after_settlement_cannot_create_untracked_refund(self):
        self.seed()
        self.cmd("receipt.record", receiptId="RC", partyId="BUYER",
                 accountId="1010", postingDate=POST,
                 allocations=[{"invoiceId": "DOC", "amount": 400}])
        self.ret(lines=[{"lineIndex": 0, "quantity": 1}])
        self.assertEqual(self.view()["parties"]["BUYER"]["receivable"], 194)
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "reverse settlement or arrange refund"):
            self.ret(ret_id="RET2", lines=[{"lineIndex": 0, "quantity": 1}])
        self.assertEqual(self.state, before)
        # The remaining amount is still settleable but never overallocatable.
        self.cmd("receipt.record", receiptId="RC2", partyId="BUYER",
                 accountId="1010", postingDate=POST,
                 allocations=[{"invoiceId": "DOC", "amount": 194}])
        self.assertEqual(self.view()["parties"]["BUYER"]["receivable"], 0)
        with self.assertRaisesRegex(ValueError, "Over-allocation"):
            self.cmd("receipt.record", receiptId="RC3", partyId="BUYER",
                     accountId="1010", postingDate=POST,
                     allocations=[{"invoiceId": "DOC", "amount": 1}])

    def test_rounding_is_cumulative_and_exact_across_one_unit_notes(self):
        self.seed(lines=[{"description": "Fraction test", "quantity": 3,
                          "unitPrice": 1}], discount=1, tax=1)
        notes = [self.ret(ret_id="T" + str(i),
                          lines=[{"lineIndex": 0, "quantity": 1}])
                 for i in range(3)]
        self.assertEqual(sum(note["amount"] for note in notes), 3)
        self.assertEqual(sum(note["discount"] for note in notes), 1)
        self.assertEqual(sum(note["tax"] for note in notes), 1)
        self.assertEqual(self.view()["parties"]["BUYER"]["receivable"], 0)

    def test_overreturn_invalid_payload_reversal_and_full_return_after_partial_rejected(self):
        self.seed()
        snapshots = deepcopy(self.state)
        invalid = [
            [{"lineIndex": 0, "quantity": 3}],
            [{"lineIndex": 0, "quantity": 1}, {"lineIndex": 0, "quantity": 1}],
            [{"lineIndex": True, "quantity": 1}],
            [{"lineIndex": 3, "quantity": 1}],
            [{"lineIndex": 0, "quantity": 0}],
            [{"lineIndex": 0, "quantity": 1, "amount": 2}],
            [],
        ]
        for lines in invalid:
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                self.ret(lines=lines)
            self.assertEqual(self.state, snapshots)
        self.ret(lines=[{"lineIndex": 0, "quantity": 1}])
        with self.assertRaisesRegex(ValueError, "entirely unsettled"):
            self.ret(ret_id="FULL")
        with self.assertRaisesRegex(ValueError, "partial credit notes"):
            self.cmd("journal.reverse", journalId=self.view()["invoices"]["DOC"]["postedEntryId"], postingDate=POST,
                     reason="Would over-reverse issued amount")
        with self.assertRaisesRegex(ValueError, "wholly unsettled"):
            self.cmd("invoice.correct", invoiceId="DOC", replacementId="REPL",
                     postingDate=POST, documentDate=POST,
                     reason="Would lose note linkage", lines=[
                         {"description": "Replacement", "quantity": 1, "unitPrice": 50}])
        self.assertEqual(self.view()["invoices"]["DOC"]["returnedAmount"], 495)

    def test_note_command_idempotence_and_verified_replay(self):
        self.seed()
        command = {"type": "invoice.return", "eventId": "RETURN.ONCE",
                   "invoiceId": "DOC", "returnId": "N1", "postingDate": POST,
                   "reason": "One unit", "lines": [{"lineIndex": 0, "quantity": 1}]}
        once = apply_accounting_command(self.state, command, actor="admin",
                                        accounts=USERS, now=NOW)
        duplicate = apply_accounting_command(once["state"], command, actor="admin",
                                             accounts=USERS, now=NOW)
        self.assertFalse(duplicate["changed"])
        self.assertEqual(duplicate["result"], once["result"])
        self.assertEqual(duplicate["state"], once["state"])
        with self.assertRaisesRegex(ValueError, "Event ID reused"):
            apply_accounting_command(once["state"],
                                     {**command, "lines": [{"lineIndex": 0, "quantity": 2}]},
                                     actor="admin", accounts=USERS, now=NOW)
        self.assertTrue(validate_accounting_state(once["state"]))
        damaged = deepcopy(once["state"])
        damaged["events"][-1]["result"]["amount"] += 1
        with self.assertRaisesRegex(ValueError, "Event hash mismatch"):
            validate_accounting_state(damaged)

    def test_active_cheques_and_installments_need_cancellation(self):
        self.seed()
        self.cmd("cheque.register", chequeId="CH1", direction="receipt",
                 documentId="DOC", bankAccountId="1010", dueDate=POST,
                 amount=300, reference="Cheque no 1")
        with self.assertRaisesRegex(ValueError, "active linked cheques"):
            self.ret(lines=[{"lineIndex": 0, "quantity": 1}])
        self.cmd("cheque.cancel", chequeId="CH1", reason="Note to be posted")
        self.ret(lines=[{"lineIndex": 0, "quantity": 1}])
        with self.assertRaisesRegex(ValueError, "credit notes"):
            self.cmd("cheque.register", chequeId="CH2", direction="receipt",
                     documentId="DOC", bankAccountId="1010", dueDate=POST,
                     amount=600, reference="Cheque no 2")
        self.cmd("installments.create", planId="P1", direction="receipt",
                 documentId="DOC", schedule=[{"dueDate": "2026-11-01", "amount": 594}])
        self.assertEqual(self.view()["invoices"]["DOC"]["total"], 1089)
        with self.assertRaisesRegex(ValueError, "active instalment"):
            self.ret(ret_id="RET2", lines=[{"lineIndex": 0, "quantity": 1}])
        self.cmd("installments.cancel", planId="P1", reason="Return credit changes schedule")
        self.ret(ret_id="RET2", lines=[{"lineIndex": 0, "quantity": 1}])

    def test_linked_stock_movement_must_be_reversed_first_and_future_issues_capped(self):
        self.cmd("item.create", itemId="I", sku="SYNTH", name="Synthetic",
                 kind="goods", unit="pcs")
        self.cmd("item.stock.enable", itemId="I")
        self.cmd("warehouse.create", warehouseId="W", name="Synthetic warehouse")
        self.cmd("party.register", partyId="VENDOR", name="Vendor", kind="vendor")
        self.cmd("bill.create", billId="B", partyId="VENDOR", documentDate="2026-10-10",
                 lines=[{"description": "Goods", "quantity": 3,
                         "unitPrice": 100, "itemId": "I"}])
        self.cmd("bill.approve", billId="B")
        self.cmd("bill.issue", billId="B", postingDate=POST)
        self.cmd("inventory.receive", warehouseId="W", itemId="I",
                 quantity=3, billId="B", postingDate=POST)
        self.cmd("party.register", partyId="BUYER", name="Buyer", kind="customer")
        self.cmd("invoice.create", invoiceId="DOC", partyId="BUYER",
                 documentDate="2026-10-10", lines=[
                     {"description": "Goods", "quantity": 2,
                      "unitPrice": 200, "itemId": "I"}])
        self.cmd("invoice.approve", invoiceId="DOC")
        self.cmd("invoice.issue", invoiceId="DOC", postingDate=POST)
        self.ret(lines=[{"lineIndex": 0, "quantity": 1}])
        with self.assertRaisesRegex(ValueError, "unreturned document quantity"):
            self.cmd("inventory.issue", warehouseId="W", itemId="I",
                     quantity=2, invoiceId="DOC", postingDate=POST)
        self.cmd("inventory.issue", warehouseId="W", itemId="I",
                 quantity=1, invoiceId="DOC", postingDate=POST)
        previous = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "Reverse linked inventory movements"):
            self.ret(ret_id="RET2", lines=[{"lineIndex": 0, "quantity": 1}])
        self.assertEqual(self.state, previous)
        with self.assertRaisesRegex(ValueError, "Reverse linked inventory movements"):
            self.cmd("bill.return", billId="B", returnId="BR",
                     postingDate=POST, reason="Purchase return",
                     lines=[{"lineIndex": 0, "quantity": 1}])
        self.assertEqual(self.view()["stock"]["W"]["I"]["quantity"], 2)

    def test_full_return_legacy_path_still_reverses_whole_document(self):
        self.state = empty_accounting_state()
        self.seed("bill")
        returned = self.ret("bill")
        self.assertEqual(returned["status"], "reversed")
        self.assertEqual(self.view()["bills"]["DOC"]["returnId"], "RET1")
        self.assertEqual(self.view()["parties"]["VENDOR"]["payable"], 0)


if __name__ == "__main__":
    unittest.main()
