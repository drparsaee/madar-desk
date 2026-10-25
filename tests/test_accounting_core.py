"""Focused executable accounting invariants, using disposable JSON snapshots."""

from copy import deepcopy
import json
import unittest

from accounting_core import (
    MAX_TOMAN, accounting_view, apply_accounting_command,
    empty_accounting_state, validate_accounting_state,
)


NOW = "2026-10-21T16:00:00+03:30"
TODAY = "2026-10-21"
USERS = [
    {"username": "root", "role": "admin"},
    {"username": "finance", "role": "editor", "financeEdit": True},
    {"username": "observer", "role": "viewer"},
]


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.state = empty_accounting_state()
        self.serial = 0

    def run_command(self, command_type, *, actor="root", now=NOW, **fields):
        self.serial += 1
        cmd = {"type": command_type, "eventId": f"event-{self.serial}", **fields}
        result = apply_accounting_command(self.state, cmd, actor=actor, accounts=USERS, now=now)
        self.state = result["state"]
        return result

    def view(self):
        return accounting_view(self.state, actor="root", accounts=USERS)

    def customer(self):
        self.run_command("party.register", partyId="client-1", name="Client One", kind="customer")

    def vendor(self):
        self.run_command("party.register", partyId="vendor-1", name="Vendor One", kind="vendor")

    def draft_sale(self, invoice_id="sale-1", total=1000, **kwargs):
        return self.run_command("invoice.create", invoiceId=invoice_id, partyId="client-1",
                                documentDate="2026-10-01",
                                lines=[{"description": "Design", "quantity": 2,
                                        "unitPrice": total // 2}], **kwargs)

    def issue_sale(self, invoice_id="sale-1", total=1000, **kwargs):
        self.draft_sale(invoice_id, total, **kwargs)
        self.run_command("invoice.approve", invoiceId=invoice_id)
        return self.run_command("invoice.issue", invoiceId=invoice_id, postingDate=TODAY)

    def issue_bill(self, bill_id="bill-1", total=400):
        self.run_command("bill.create", billId=bill_id, partyId="vendor-1",
                         documentDate="2026-10-01",
                         lines=[{"description": "Paper", "quantity": 2, "unitPrice": total // 2}])
        self.run_command("bill.approve", billId=bill_id)
        return self.run_command("bill.issue", billId=bill_id, postingDate=TODAY)

    def funding(self, amount=1000):
        return self.run_command("funds.deposit", accountId="1010", amount=amount,
                                postingDate=TODAY, note="Owner contributed own funds")

    def test_empty_schema_and_defensive_view(self):
        self.assertTrue(validate_accounting_state(self.state))
        old = deepcopy(self.state)
        projection = self.view()
        self.assertEqual(projection["accounts"]["1000"]["normalBalance"], 0)
        projection["accounts"]["1000"]["name"] = "edited"
        self.assertEqual(self.state, old)
        self.assertEqual(json.loads(json.dumps(self.state)), self.state)

    def test_sale_is_double_entry_only_after_issue(self):
        self.customer()
        self.draft_sale()
        self.run_command("invoice.approve", invoiceId="sale-1")
        self.assertEqual(self.view()["journals"], [])
        issued = self.run_command("invoice.issue", invoiceId="sale-1", postingDate=TODAY)
        view = self.view()
        self.assertEqual(issued["result"]["number"], 1)
        self.assertEqual(view["parties"]["client-1"]["receivable"], 1000)
        self.assertEqual(view["accounts"]["1200"]["normalBalance"], 1000)
        self.assertEqual(view["accounts"]["4000"]["normalBalance"], 1000)
        self.assertEqual(sum(x["debit"] for x in view["journals"][0]["lines"]), 1000)
        self.assertEqual(sum(x["credit"] for x in view["journals"][0]["lines"]), 1000)
        self.assertTrue(validate_accounting_state(self.state))

    def test_purchase_is_expense_debit_and_party_credit(self):
        self.vendor()
        self.issue_bill()
        view = self.view()
        self.assertEqual(view["parties"]["vendor-1"]["payable"], 400)
        self.assertEqual(view["accounts"]["2000"]["normalBalance"], 400)
        self.assertEqual(view["accounts"]["5000"]["normalBalance"], 400)
        self.assertEqual(view["bills"]["bill-1"]["number"], 1)

    def test_full_cycle_partial_allocations_and_settlement(self):
        self.customer()
        self.vendor()
        self.issue_sale()
        self.issue_sale("sale-2", 600)
        self.issue_bill()
        self.funding(300)
        self.run_command("receipt.record", receiptId="r-1", partyId="client-1",
                         accountId="1010", postingDate=TODAY,
                         allocations=[{"invoiceId": "sale-1", "amount": 700},
                                      {"invoiceId": "sale-2", "amount": 300}])
        self.run_command("payment.record", paymentId="p-1", partyId="vendor-1",
                         accountId="1010", postingDate=TODAY,
                         allocations=[{"billId": "bill-1", "amount": 400}])
        view = self.view()
        self.assertEqual(view["parties"]["client-1"]["receivable"], 600)
        self.assertEqual(view["parties"]["vendor-1"]["payable"], 0)
        self.assertEqual(view["accounts"]["1010"]["normalBalance"], 900)
        self.assertEqual(view["invoices"]["sale-1"]["allocated"], 700)
        self.assertEqual(view["invoices"]["sale-2"]["allocated"], 300)
        self.assertTrue(validate_accounting_state(self.state))

    def test_payment_requires_actual_available_funds(self):
        self.vendor()
        self.issue_bill()
        old = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            self.run_command("payment.record", paymentId="p-1", partyId="vendor-1",
                             accountId="1010", postingDate=TODAY,
                             allocations=[{"billId": "bill-1", "amount": 1}])
        self.assertEqual(old, self.state)

    def test_backdated_payment_cannot_overdraw_historical_bank_balance(self):
        self.vendor()
        self.run_command("bill.create", billId="bill-1", partyId="vendor-1",
                         documentDate="2026-10-01",
                         lines=[{"description": "Materials", "quantity": 1,
                                 "unitPrice": 400}])
        self.run_command("bill.approve", billId="bill-1")
        self.run_command("bill.issue", billId="bill-1", postingDate="2026-10-18")
        self.run_command("funds.deposit", accountId="1010", amount=500,
                         postingDate="2026-10-20", note="Bank proof checked by host")
        with self.assertRaisesRegex(ValueError, "historical"):
            self.run_command("payment.record", paymentId="p-1", partyId="vendor-1",
                             accountId="1010", postingDate="2026-10-19",
                             allocations=[{"billId": "bill-1", "amount": 400}])
        self.assertEqual(self.view()["bills"]["bill-1"]["allocated"], 0)

    def test_settlement_refused_before_invoice_issue_date(self):
        self.customer()
        self.issue_sale()
        with self.assertRaisesRegex(ValueError, "cannot precede"):
            self.run_command("receipt.record", receiptId="backdated", partyId="client-1",
                             accountId="1010", postingDate="2026-10-20",
                             allocations=[{"invoiceId": "sale-1", "amount": 100}])

    def test_receipt_overallocation_and_duplicate_target_refused(self):
        self.customer()
        self.issue_sale()
        for allocations in ([{"invoiceId": "sale-1", "amount": 1001}],
                            [{"invoiceId": "sale-1", "amount": 300},
                             {"invoiceId": "sale-1", "amount": 200}]):
            with self.subTest(allocations=allocations):
                with self.assertRaises(ValueError):
                    self.run_command("receipt.record", receiptId="r-invalid",
                                     partyId="client-1", accountId="1010",
                                     postingDate=TODAY, allocations=allocations)
        self.assertEqual(self.view()["invoices"]["sale-1"]["allocated"], 0)

    def test_allocation_to_other_party_or_draft_refused(self):
        self.customer()
        self.run_command("party.register", partyId="client-2", name="Other", kind="customer")
        self.draft_sale()
        with self.assertRaisesRegex(ValueError, "issued document"):
            self.run_command("receipt.record", receiptId="r-1", partyId="client-2",
                             accountId="1010", postingDate=TODAY,
                             allocations=[{"invoiceId": "sale-1", "amount": 100}])

    def test_reversal_clears_allocation_before_reversing_invoice(self):
        self.customer()
        self.issue_sale()
        receipt = self.run_command("receipt.record", receiptId="r-1", partyId="client-1",
                                   accountId="1010", postingDate=TODAY,
                                   allocations=[{"invoiceId": "sale-1", "amount": 1000}])
        old = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "settlements first"):
            self.run_command("journal.reverse", journalId="J:event-4",
                             postingDate=TODAY, reason="Mistaken billable task")
        self.assertEqual(self.state, old)
        self.run_command("journal.reverse", journalId=receipt["result"]["journalId"],
                         postingDate=TODAY, reason="Bank returned the deposit")
        issue_id = self.view()["invoices"]["sale-1"]["postedEntryId"]
        self.run_command("journal.reverse", journalId=issue_id, postingDate=TODAY,
                         reason="Invoice cancelled after refund")
        v = self.view()
        self.assertEqual(v["parties"]["client-1"]["receivable"], 0)
        self.assertEqual(v["accounts"]["1200"]["normalBalance"], 0)
        self.assertEqual(v["accounts"]["1010"]["normalBalance"], 0)
        self.assertEqual(v["invoices"]["sale-1"]["status"], "reversed")
        self.assertEqual(len(v["journals"]), 4)
        self.assertTrue(validate_accounting_state(self.state))

    def test_cannot_reverse_receipt_after_funds_spent(self):
        self.customer()
        self.vendor()
        self.issue_sale()
        self.issue_bill()
        receipt = self.run_command("receipt.record", receiptId="r-1", partyId="client-1",
                                   accountId="1010", postingDate=TODAY,
                                   allocations=[{"invoiceId": "sale-1", "amount": 400}])
        self.run_command("payment.record", paymentId="p-1", partyId="vendor-1",
                         accountId="1010", postingDate=TODAY,
                         allocations=[{"billId": "bill-1", "amount": 400}])
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            self.run_command("journal.reverse", journalId=receipt["result"]["journalId"],
                             postingDate=TODAY, reason="Refund")

    def test_discounts_and_explicit_tax_post_balanced_without_auto_tax_rates(self):
        self.customer()
        self.vendor()
        self.issue_sale(discount=100, tax=50)
        self.run_command("bill.create", billId="bill-1", partyId="vendor-1",
                         documentDate="2026-10-01", discount=25, tax=10,
                         lines=[{"description": "Paper", "quantity": 2, "unitPrice": 200}])
        self.run_command("bill.approve", billId="bill-1")
        self.run_command("bill.issue", billId="bill-1", postingDate=TODAY)
        v = self.view()
        self.assertEqual(v["parties"]["client-1"]["receivable"], 950)
        self.assertEqual(v["parties"]["vendor-1"]["payable"], 385)
        self.assertEqual(v["accounts"]["2200"]["normalBalance"], 50)
        self.assertEqual(v["accounts"]["4100"]["normalBalance"], 100)
        self.assertEqual(v["accounts"]["5100"]["normalBalance"], 25)
        self.assertEqual(v["accounts"]["5200"]["normalBalance"], 10)

    def test_closed_period_and_invalid_calendar_boundaries(self):
        self.customer()
        self.draft_sale()
        self.run_command("invoice.approve", invoiceId="sale-1")
        self.run_command("period.close", throughDate="2026-10-20")
        with self.assertRaisesRegex(ValueError, "closed period"):
            self.run_command("invoice.issue", invoiceId="sale-1", postingDate="2026-10-20")
        with self.assertRaisesRegex(ValueError, "future"):
            self.run_command("invoice.issue", invoiceId="sale-1", postingDate="2026-10-22")
        with self.assertRaisesRegex(ValueError, "calendar date"):
            self.run_command("invoice.issue", invoiceId="sale-1", postingDate="2026-02-30")
        with self.assertRaisesRegex(ValueError, "boundary"):
            self.run_command("period.close", throughDate="2026-10-20")
        self.run_command("invoice.issue", invoiceId="sale-1", postingDate=TODAY)
        self.assertEqual(self.view()["closedThrough"], "2026-10-20")

    def test_refuse_reversal_in_closed_period(self):
        funding = self.funding()
        self.run_command("period.close", throughDate=TODAY)
        with self.assertRaisesRegex(ValueError, "closed period"):
            self.run_command("journal.reverse", journalId=funding["result"]["journalId"],
                             postingDate=TODAY, reason="Correction")

    def test_idempotency_and_event_id_conflict(self):
        cmd = {"type": "party.register", "eventId": "party-one", "partyId": "client-1",
               "name": "Client One", "kind": "customer"}
        first = apply_accounting_command(self.state, cmd, actor="root", accounts=USERS, now=NOW)
        self.state = first["state"]
        replay = apply_accounting_command(self.state, cmd, actor="root", accounts=USERS,
                                          now="2026-10-21T17:00:00+03:30")
        self.assertFalse(replay["changed"])
        self.assertEqual(replay["state"], self.state)
        self.assertEqual(replay["result"], first["result"])
        with self.assertRaisesRegex(ValueError, "reused"):
            apply_accounting_command(self.state, {**cmd, "name": "Changed"},
                                     actor="root", accounts=USERS, now=NOW)
        with self.assertRaisesRegex(ValueError, "reused"):
            apply_accounting_command(self.state, cmd, actor="finance", accounts=USERS, now=NOW)

    def test_demotion_blocks_replay_and_edits(self):
        self.customer()
        cmd = {"type": "party.register", "eventId": "event-1", "partyId": "client-1",
               "name": "Client One", "kind": "customer"}
        with self.assertRaises(PermissionError):
            apply_accounting_command(self.state, cmd, actor="root",
                                     accounts=[{"username": "root", "role": "viewer"}], now=NOW)
        with self.assertRaises(PermissionError):
            apply_accounting_command(self.state, {**cmd, "eventId": "new"},
                                     actor="observer", accounts=USERS, now=NOW)

    def test_finance_editor_can_approve_and_issue_but_cannot_close_period(self):
        self.run_command("party.register", partyId="client-1", name="Client One",
                         kind="customer", actor="finance")
        self.run_command("invoice.create", invoiceId="i-1", partyId="client-1",
                         documentDate=TODAY,
                         lines=[{"description": "Work", "quantity": 1, "unitPrice": 123}],
                         actor="finance")
        self.run_command("invoice.approve", invoiceId="i-1", actor="finance")
        self.run_command("invoice.issue", invoiceId="i-1", postingDate=TODAY,
                         actor="finance")
        with self.assertRaises(PermissionError):
            self.run_command("period.close", throughDate=TODAY, actor="finance")
        with self.assertRaises(PermissionError):
            accounting_view(self.state, actor="observer", accounts=USERS)
        self.assertEqual(accounting_view(self.state, actor="finance", accounts=USERS)[
            "invoices"]["i-1"]["status"], "issued")

    def test_amount_validation_bool_float_overflow(self):
        self.customer()
        for invalid in (True, 1.0, -1, MAX_TOMAN + 1, "100", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.run_command("invoice.create", invoiceId="i-invalid", partyId="client-1",
                                     documentDate=TODAY, lines=[{"description": "Work",
                                         "quantity": 1, "unitPrice": invalid}])
        with self.assertRaisesRegex(ValueError, "line total"):
            self.run_command("invoice.create", invoiceId="i-too-big", partyId="client-1",
                             documentDate=TODAY, lines=[{"description": "Work",
                                 "quantity": 2, "unitPrice": MAX_TOMAN}])

    def test_named_party_required_correct_direction(self):
        self.customer()
        with self.assertRaisesRegex(ValueError, "incompatible named party"):
            self.run_command("bill.create", billId="bad", partyId="client-1",
                             documentDate=TODAY, lines=[{"description": "Input",
                                 "quantity": 1, "unitPrice": 100}])
        with self.assertRaisesRegex(ValueError, "incompatible named party"):
            self.run_command("invoice.create", invoiceId="bad", partyId="unknown",
                             documentDate=TODAY, lines=[{"description": "Input",
                                 "quantity": 1, "unitPrice": 100}])

    def test_business_source_is_deduplicated_across_distinct_event_ids(self):
        self.customer()
        line = [{"description": "Task service", "quantity": 1, "unitPrice": 100}]
        self.run_command("invoice.create", invoiceId="i-1", partyId="client-1",
                         documentDate=TODAY, lines=line,
                         sourceType="task-completion", sourceId="completion-123")
        with self.assertRaisesRegex(ValueError, "already been"):
            self.run_command("invoice.create", invoiceId="i-2", partyId="client-1",
                             documentDate=TODAY, lines=line,
                             sourceType="task-completion", sourceId="completion-123")
        with self.assertRaisesRegex(ValueError, "must be supplied together"):
            self.run_command("invoice.create", invoiceId="i-3", partyId="client-1",
                             documentDate=TODAY, lines=line, sourceType="task-completion")
        self.assertEqual(self.view()["invoices"]["i-1"]["sourceId"], "completion-123")

    def test_cancel_unissued_and_recreate_with_same_source(self):
        self.customer()
        common = {"partyId": "client-1", "documentDate": TODAY,
                  "sourceType": "task", "sourceId": "task-42",
                  "lines": [{"description": "Design", "quantity": 1, "unitPrice": 100}]}
        self.run_command("invoice.create", invoiceId="old", **common)
        self.run_command("invoice.cancel", invoiceId="old", reason="Incorrect price")
        self.run_command("invoice.create", invoiceId="fixed", **common)
        self.run_command("invoice.approve", invoiceId="fixed")
        self.run_command("invoice.issue", invoiceId="fixed", postingDate=TODAY)
        with self.assertRaisesRegex(ValueError, "unissued"):
            self.run_command("invoice.cancel", invoiceId="fixed", reason="Cannot cancel posted")
        self.assertEqual(self.view()["invoices"]["old"]["status"], "cancelled")
        self.assertEqual(self.view()["invoices"]["fixed"]["status"], "issued")

    def test_new_account_and_party_both_roles(self):
        self.run_command("account.create", accountId="4090", name="Services",
                         kind="revenue", liquid=False)
        self.run_command("party.register", partyId="company-1", name="Dual Company",
                         kind="both")
        self.run_command("invoice.create", invoiceId="i-1", partyId="company-1",
                         documentDate=TODAY, lines=[{"description": "Services", "quantity": 1,
                             "unitPrice": 123, "accountId": "4090"}])
        self.run_command("bill.create", billId="b-1", partyId="company-1",
                         documentDate=TODAY, lines=[{"description": "Supplies", "quantity": 1,
                             "unitPrice": 42}])
        self.run_command("invoice.approve", invoiceId="i-1")
        self.run_command("bill.approve", billId="b-1")
        self.run_command("invoice.issue", invoiceId="i-1", postingDate=TODAY)
        self.run_command("bill.issue", billId="b-1", postingDate=TODAY)
        view = self.view()
        self.assertEqual(view["parties"]["company-1"]["netReceivable"], 81)
        self.assertEqual(view["accounts"]["4090"]["normalBalance"], 123)

    def test_journals_never_deleted_when_reversed(self):
        fund = self.funding(123)
        prior = deepcopy(self.state["events"])
        self.run_command("journal.reverse", journalId=fund["result"]["journalId"],
                         postingDate=TODAY, reason="Funding input mistake")
        self.assertEqual(self.state["events"][:len(prior)], prior)
        v = self.view()
        self.assertEqual(len(v["journals"]), 2)
        self.assertEqual(v["accounts"]["1010"]["normalBalance"], 0)
        with self.assertRaises(ValueError):
            self.run_command("journal.reverse", journalId=fund["result"]["journalId"],
                             postingDate=TODAY, reason="Twice")

    def test_tamper_detection_replays_chain_and_results(self):
        self.customer()
        original = deepcopy(self.state)
        for change in (lambda s: s["events"][0]["command"].update(name="Forged"),
                       lambda s: s["events"][0].update(result={"partyId": "fake"}),
                       lambda s: s["events"][0].update(hash="0" * 64),
                       lambda s: s["events"][0].update(previousHash="1" * 64)):
            changed = deepcopy(original)
            change(changed)
            with self.assertRaises(ValueError):
                validate_accounting_state(changed)

    def test_numbering_never_reused_after_reversal(self):
        self.customer()
        first = self.issue_sale()
        self.run_command("journal.reverse", journalId=first["result"]["journalId"],
                         postingDate=TODAY, reason="Cancel wrong sale")
        second = self.issue_sale("sale-2", 200)
        self.assertEqual(second["result"]["number"], 2)
        self.assertTrue(validate_accounting_state(self.state))

    def test_invalid_clock_and_state_schema_refused(self):
        cmd = {"type": "party.register", "eventId": "e", "partyId": "p",
               "name": "Person", "kind": "customer"}
        with self.assertRaisesRegex(ValueError, "timezone"):
            apply_accounting_command(self.state, cmd, actor="root", accounts=USERS,
                                     now="2026-10-21T16:00:00")
        corrupted = {**self.state, "extra": None}
        with self.assertRaises(ValueError):
            validate_accounting_state(corrupted)


if __name__ == "__main__":
    unittest.main()
