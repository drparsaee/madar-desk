"""Synthetic host-to-storage security tests; no real Madar/Parsian data."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_storage import RevisionConflict, UnifiedAppStorage
from ir_finance_v2_extension import load_finance_rial_journal
from ir_invoice_joint_issue import issue_legacy_sales_with_rial
from finance import apply_finance_command, empty_finance_state
from ir_finance_v2_extension import HostCompanyProof, activate_rial_finance
from ir_journal_v2 import FiscalPeriod, new_journal_state
from money_policy import snapshot_sha256
from native_app import initial_state
import collab

NOW = "2026-10-21T12:00:00Z"
COMPANY = "co-test"


class JointIssueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-joint-rial-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.store = UnifiedAppStorage(Path(self.temp.name) / "synthetic.sqlite3")
        self.users = {
            "admin": {"username": "admin", "role": "admin", "projects": None},
            "viewer": {"username": "viewer", "role": "viewer", "projects": None},
        }
        self.projects = [{"id": "p1", "name": "Test"}]
        self.cards = [{"id": "c1", "projectId": "p1", "status": "done"}]
        finance = empty_finance_state()
        period = FiscalPeriod(COMPANY, "FY26", "2026-01-01", "2026-12-31")
        finance = activate_rial_finance(
            finance, new_journal_state(COMPANY, (period,)),
            proof=HostCompanyProof(COMPANY, "admin", snapshot_sha256(finance)))
        self.finance = finance
        self.bundle = {
            "tasks": initial_state(), "collab": collab.empty_state(),
            "finance": finance, "completion_outbox": [],
        }

    def update(self, command, actor="admin"):
        out = apply_finance_command(
            self.finance, command, actor=actor, accounts=self.users,
            cards=self.cards, projects=self.projects, now=NOW,
        )
        self.finance = out["state"]
        return out

    def make_reviewed_invoice(self, *, discount=0, tax=0, advance=0,
                              unit_price=100, quantity=2, prefix="a"):
        sale = {"customer": {"name": "Synthetic", "reference": "fake"},
                "lines": [{"id": "line", "description": "Printing",
                           "quantity": quantity, "unitPrice": unit_price}],
                "discount": discount, "tax": tax, "advance": advance,
                "autoInvoice": True}
        self.update({"type": "contract.set", "eventId": prefix + "-contract",
                     "cardId": "c1", "sale": sale})
        self.update({"type": "completion.record", "eventId": prefix + "-done",
                     "cardId": "c1", "completionId": prefix + "-complete"})
        invoice_id = self.finance["invoices"][-1]["id"]
        self.update({"type": "invoice.review", "eventId": prefix + "-review",
                     "invoiceId": invoice_id})
        return invoice_id

    def joint(self, invoice_id, *, event="issue", actor="admin"):
        return issue_legacy_sales_with_rial(
            self.finance, {"type": "invoice.issue", "eventId": event,
                           "invoiceId": invoice_id},
            actor=actor, accounts=self.users, cards=self.cards,
            projects=self.projects, now=NOW,
        )

    def test_atomic_commit_exact_revenue_and_idempotent_retry(self):
        invoice = self.make_reviewed_invoice(discount=10, tax=20)
        before = deepcopy(self.finance)
        result = self.joint(invoice)
        self.assertEqual(result["result"]["rialAmount"], "2100")
        self.assertEqual(self.finance, before)  # pure
        first = self.store.commit({**self.bundle, "finance": before},
                                  expected_revision=0)
        second = self.store.commit(
            {**first.bundle, "finance": result["state"]},
            expected_revision=first.revision)
        self.assertEqual(second.revision, 2)
        state = load_finance_rial_journal(second.bundle["finance"], COMPANY)
        rows = state.events[-1].lines
        self.assertEqual(
            [(r.reference.account_code, r.debit_rial, r.credit_rial) for r in rows],
            [("100101", 2100, 0), ("400101", 0, 1900), ("200101", 0, 200)])
        self.finance = second.bundle["finance"]
        retry = self.joint(invoice)
        self.assertFalse(retry["changed"])
        self.assertEqual(retry["state"], self.finance)
        self.assertEqual(retry["result"], result["result"])
        self.assertEqual(len(load_finance_rial_journal(self.finance, COMPANY).events), 1)

    def test_two_different_invoices_same_card_have_distinct_business_sources(self):
        first_invoice = self.make_reviewed_invoice(prefix="first")
        issued1 = self.joint(first_invoice, event="first-issue")
        self.finance = issued1["state"]
        second_invoice = self.make_reviewed_invoice(prefix="second")
        issued2 = self.joint(second_invoice, event="second-issue")
        self.assertNotEqual(first_invoice, second_invoice)
        self.assertEqual(issued2["result"]["rialAmount"], "2000")
        state = load_finance_rial_journal(issued2["state"], COMPANY)
        self.assertEqual(len(state.events), 2)
        self.assertEqual({e.source.source_id for e in state.events},
                         {first_invoice, second_invoice})
        self.assertEqual({e.source.kind for e in state.events}, {"independent"})

    def test_exact_large_rial_limit_is_fail_closed_before_finance_write(self):
        invoice = self.make_reviewed_invoice(
            prefix="maximum", unit_price=900_719_925_474_100, quantity=1)
        previous = deepcopy(self.finance)
        with self.assertRaises(ValueError):
            self.joint(invoice)
        self.assertEqual(self.finance, previous)

    def test_old_unmirrored_invoice_issue_is_rejected_with_no_db_change(self):
        invoice = self.make_reviewed_invoice()
        first = self.store.commit({**self.bundle, "finance": self.finance},
                                  expected_revision=0)
        old_only = apply_finance_command(
            self.finance, {"type": "invoice.issue", "eventId": "legacy-only",
                           "invoiceId": invoice}, actor="admin", accounts=self.users,
            cards=self.cards, projects=self.projects, now=NOW)["state"]
        with self.assertRaisesRegex(ValueError, "joint issue"):
            self.store.commit({**first.bundle, "finance": old_only},
                              expected_revision=first.revision)
        self.assertEqual(self.store.load().revision, first.revision)
        self.assertEqual(self.store.load().bundle["finance"], self.finance)

    def test_unauthorized_editor_wrong_card_and_advance_fail_closed(self):
        invoice = self.make_reviewed_invoice()
        with self.assertRaises(PermissionError):
            self.joint(invoice, actor="viewer")
        before = deepcopy(self.finance)
        self.cards[0]["projectId"] = "p2"
        with self.assertRaises(ValueError):
            self.joint(invoice)
        self.assertEqual(self.finance, before)
        self.cards[0]["projectId"] = "p1"
        other = JointIssueTests("runTest")
        other.setUp()
        self.addCleanup(other.temp.cleanup)
        advanced = other.make_reviewed_invoice(advance=1)
        with self.assertRaisesRegex(ValueError, "Advance"):
            other.joint(advanced)

    def test_wrong_or_closed_period_and_overflow_fail_without_commit(self):
        invoice = self.make_reviewed_invoice()
        # The host timestamp must fall within the activated fiscal calendar.
        with self.assertRaisesRegex(ValueError, "No unique"):
            issue_legacy_sales_with_rial(
                self.finance, {"type": "invoice.issue", "eventId": "late",
                               "invoiceId": invoice},
                actor="admin", accounts=self.users, cards=self.cards,
                projects=self.projects, now="2027-10-21T12:00:00Z")
        self.assertFalse(any(i["action"] == "invoice.issue"
                             for i in self.finance["ledger"]))

    def test_sql_cas_rejects_stale_and_injected_failure_rollback(self):
        invoice = self.make_reviewed_invoice()
        before = deepcopy(self.finance)
        candidate = self.joint(invoice)["state"]
        first = self.store.commit({**self.bundle, "finance": before},
                                  expected_revision=0)
        to_commit = {**first.bundle, "finance": candidate}
        with patch.object(UnifiedAppStorage, "_insert",
                          side_effect=RuntimeError("synthetic disk failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic disk failure"):
                self.store.commit(to_commit, expected_revision=first.revision)
        self.assertEqual(self.store.load().revision, first.revision)
        successful = self.store.commit(to_commit, expected_revision=first.revision)
        self.assertEqual(successful.revision, 2)
        with self.assertRaises(RevisionConflict):
            self.store.commit({**first.bundle, "finance": before},
                              expected_revision=first.revision)
        self.assertEqual(self.store.load().revision, 2)

    def test_active_company_cannot_drop_or_rewrite_history(self):
        invoice = self.make_reviewed_invoice()
        first = self.store.commit(
            {**self.bundle, "finance": self.finance}, expected_revision=0)
        issue = self.joint(invoice)["state"]
        committed = self.store.commit(
            {**first.bundle, "finance": issue}, expected_revision=1)
        tampered = deepcopy(committed.bundle)
        del tampered["finance"]["rialJournalV2"]
        with self.assertRaises(ValueError):
            self.store.commit(tampered, expected_revision=2)
        self.assertEqual(self.store.load().revision, 2)

    def test_activation_is_only_empty_attachment_to_clean_finance(self):
        original = empty_finance_state()
        first = self.store.commit(
            {**self.bundle, "finance": original}, expected_revision=0)
        clean = self.store.commit(
            {**first.bundle, "finance": self.finance},
            expected_revision=first.revision)
        self.assertEqual(clean.revision, 2)
        self.assertEqual(load_finance_rial_journal(
            clean.bundle["finance"], COMPANY).events, ())

    def test_atomic_activation_refuses_mixed_legacy_changes_and_history(self):
        original = empty_finance_state()
        first = self.store.commit(
            {**self.bundle, "finance": original}, expected_revision=0)
        self.update({"type": "project.receipt", "eventId": "legacy-money",
                     "projectId": "p1", "amount": 20, "receivedAt": NOW,
                     "description": "old business receipt"})
        mixed = deepcopy(self.finance)
        with self.assertRaises(ValueError):
            self.store.commit(
                {**first.bundle, "finance": mixed}, expected_revision=1)
        self.assertEqual(self.store.load().revision, 1)
        # Even when the old state already has legacy history, activation
        # cannot evade the checked migrate/reconcile gate.
        historic = deepcopy(self.finance)
        del historic["rialJournalV2"]
        db2 = UnifiedAppStorage(Path(self.temp.name) / "second.sqlite3")
        base = db2.commit({**self.bundle, "finance": historic}, expected_revision=0)
        candidate = deepcopy(self.finance)
        with self.assertRaisesRegex(ValueError, "migration"):
            db2.commit({**base.bundle, "finance": candidate}, expected_revision=1)
        self.assertEqual(db2.load().revision, 1)


if __name__ == "__main__":
    unittest.main()
