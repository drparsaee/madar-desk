"""Synthetic no-IO validation of opt-in RIAL journal within TOMAN finance."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_storage import validated_bundle
from collab import empty_state as empty_collab
from native_app import initial_state
from finance import apply_finance_command, empty_finance_state, validate_finance_state
from ir_chart_model import ChartAccount, ChartSnapshot, JobReference, PostingReference
from ir_finance_v2_extension import (
    EXTENSION_KEY, HostCompanyProof, VerifiedInvoiceSourceProof,
    activate_rial_finance, compose_finance_rial_snapshot,
    load_finance_rial_journal,
)
from ir_journal_v2 import (
    FiscalPeriod, JournalLine, JournalSource, VerifiedScopes,
    new_journal_state, post_journal, JournalV2Conflict,
)
from money_policy import CompanyMoneyPolicy, snapshot_sha256


COMPANY = "co-1"
NOW = "2026-10-21T12:00:00Z"


def _chart():
    return ChartSnapshot(COMPANY, accounts=(
        ChartAccount(COMPANY, "10", "KOL", None, "Asset", "asset"),
        ChartAccount(COMPANY, "1001", "MOEIN", "10", "Bank", "asset"),
        ChartAccount(COMPANY, "100101", "TAFSILI", "1001", "Receivable", "asset",
                     accountable=True),
        ChartAccount(COMPANY, "40", "KOL", None, "Revenue", "revenue"),
        ChartAccount(COMPANY, "4001", "MOEIN", "40", "Revenue", "revenue"),
        ChartAccount(COMPANY, "400101", "TAFSILI", "4001", "Sales", "revenue",
                     accountable=True),
    ), project_ids=("p1",),
        jobs=(JobReference(COMPANY, "job-1", "p1", "card1"),))


class RialFinanceExtensionTests(unittest.TestCase):
    def setUp(self):
        self.users = {"admin": {"username": "admin", "role": "admin", "projects": None}}
        self.projects = [{"id": "p1", "name": "Project"}]
        self.cards = [{"id": "card1", "projectId": "p1", "status": "active"}]
        self.original = empty_finance_state()
        self.initial = new_journal_state(COMPANY, (
            FiscalPeriod(COMPANY, "FY26", "2026-01-01", "2026-12-31"),))

    def _activate(self, state=None):
        state = state if state is not None else self.original
        return activate_rial_finance(state, self.initial,
                                     proof=HostCompanyProof(COMPANY, "admin", snapshot_sha256(state)))

    def _finance(self, state, kind, event_id, **args):
        return apply_finance_command(
            state, {"type": kind, "eventId": event_id, **args},
            actor="admin", accounts=self.users, cards=self.cards,
            projects=self.projects, now=NOW)["state"]

    def _prepared_issue(self):
        state = self._activate()
        state = self._finance(state, "contract.set", "sale", cardId="card1", sale={
            "customer": {"name": "Company", "reference": "customer-1"},
            "lines": [{"id": "line1", "description": "Print", "quantity": 1,
                       "unitPrice": 120}],
            "discount": 0, "tax": 0, "advance": 0, "autoInvoice": True})
        self.cards[0]["status"] = "done"
        state = self._finance(state, "completion.record", "completion", cardId="card1",
                              completionId="completed-1")
        invoice_id = state["invoices"][0]["id"]
        state = self._finance(state, "invoice.review", "review", invoiceId=invoice_id)
        after = self._finance(state, "invoice.issue", "issue", invoiceId=invoice_id)
        return state, after, invoice_id

    def _candidate(self, before, *, amount=1200, event_id="rial-event",
                   posting_date="2026-10-21"):
        prior = load_finance_rial_journal(before, COMPANY)
        return post_journal(
            prior, company_id=COMPANY, fiscal_period_id="FY26", event_id=event_id,
            actor_id="admin", posting_date=posting_date,
            source=JournalSource("task", "card1", "p1", "card1"),
            lines=(JournalLine(PostingReference(COMPANY, "100101", project_id="p1",
                                                job_id="job-1", task_id="card1"), debit_rial=amount),
                   JournalLine(PostingReference(COMPANY, "400101", project_id="p1",
                                                job_id="job-1", task_id="card1"), credit_rial=amount)),
            chart=_chart(), scopes=VerifiedScopes(
                project_ids=frozenset({"p1"}),
                task_scopes=frozenset({("p1", "card1")})),
            money_policy=CompanyMoneyPolicy(COMPANY), expected_revision=prior.revision,
            today="2026-10-21")

    def _proof(self, before, after, invoice_id):
        inv = next(i for i in after["invoices"] if i["id"] == invoice_id)
        return VerifiedInvoiceSourceProof(
            COMPANY, "admin", invoice_id, "p1", "card1",
            inv["snapshotHash"], inv["sale"]["total"],
            snapshot_sha256(before), snapshot_sha256(after))

    def _compose(self, before, after, candidate, invoice_id, *, proof=None, expected=None):
        return compose_finance_rial_snapshot(
            before, after, candidate,
            expected_journal_revision=expected or load_finance_rial_journal(before, COMPANY).revision,
            proof=proof or self._proof(before, after, invoice_id))

    def test_opt_in_keeps_legacy_bytes_and_is_json_roundtrippable(self):
        baseline = json.dumps(self.original, sort_keys=True)
        result = self._activate()
        self.assertEqual(json.dumps(self.original, sort_keys=True), baseline)
        self.assertEqual({key: value for key, value in result.items() if key != EXTENSION_KEY},
                         self.original)
        self.assertTrue(validate_finance_state(json.loads(json.dumps(result))))
        self.assertEqual(load_finance_rial_journal(result, COMPANY), self.initial)
        self.assertTrue(validated_bundle({
            "tasks": initial_state(), "collab": empty_collab(),
            "finance": result, "completion_outbox": []}))

    def test_requires_current_company_activation_proof_and_pristine_history(self):
        with self.assertRaises(PermissionError):
            activate_rial_finance(self.original, self.initial,
                                  proof=HostCompanyProof(COMPANY, "admin", "0" * 64))
        with self.assertRaises(PermissionError):
            activate_rial_finance(self.original, self.initial,
                                  proof=HostCompanyProof("co-other", "admin",
                                                         snapshot_sha256(self.original)))
        active = self._activate()
        with self.assertRaises(JournalV2Conflict):
            self._activate(active)
        with self.assertRaises(ValueError):
            activate_rial_finance(self.original, self._candidate(active),
                                  proof=HostCompanyProof(COMPANY, "admin",
                                                         snapshot_sha256(self.original)))

    def test_compose_legacy_issue_and_v2_rial_in_one_finance_snapshot(self):
        before, after, invoice_id = self._prepared_issue()
        issued_copy = deepcopy(after)
        candidate = self._candidate(before)
        result = self._compose(before, after, candidate, invoice_id)
        self.assertEqual(issued_copy, after)
        self.assertEqual(result["ledger"], after["ledger"])
        self.assertEqual(result["invoices"], after["invoices"])
        self.assertEqual(result["nextInvoiceNumber"], after["nextInvoiceNumber"])
        self.assertEqual(load_finance_rial_journal(result, COMPANY), candidate)
        self.assertEqual(load_finance_rial_journal(result, COMPANY).events[-1].lines[0].debit_rial, 1200)
        self.assertTrue(validate_finance_state(json.loads(json.dumps(result))))
        pure_bundle = validated_bundle({
            "tasks": initial_state(), "collab": empty_collab(),
            "finance": result, "completion_outbox": []})
        self.assertEqual(pure_bundle["finance"][EXTENSION_KEY], result[EXTENSION_KEY])
        self.assertEqual(pure_bundle["finance"]["ledger"], after["ledger"])

    def test_rejects_forged_source_invoice_amount_actor_and_stale_revision(self):
        before, after, invoice_id = self._prepared_issue()
        candidate = self._candidate(before)
        proof = self._proof(before, after, invoice_id)
        cases = [
            replace(proof, company_id="another"),
            replace(proof, actor_id="viewer"),
            replace(proof, card_id="other"),
            replace(proof, invoice_snapshot_sha256="0" * 64),
            replace(proof, total_toman=121),
            replace(proof, total_toman=120.0),
            replace(proof, finance_before_sha256="0" * 64),
            replace(proof, finance_after_sha256="0" * 64),
        ]
        for tampered in cases:
            with self.subTest(proof=tampered), self.assertRaises((ValueError, PermissionError)):
                self._compose(before, after, candidate, invoice_id, proof=tampered)
        with self.assertRaises(JournalV2Conflict):
            self._compose(before, after, candidate, invoice_id, expected="0" * 64)
        with self.assertRaises(ValueError):
            self._compose(before, after, self._candidate(before, amount=1199), invoice_id)
        with self.assertRaises(ValueError):
            self._compose(before, after, self._candidate(
                before, posting_date="2026-10-20"), invoice_id)

    def test_freezes_existing_legacy_ledger_invoices_receipts_and_old_v2_events(self):
        before, after, invoice_id = self._prepared_issue()
        candidate = self._candidate(before)
        tampered = deepcopy(after)
        tampered["ledger"][0]["payload"]["contractId"] = "incorrect"
        with self.assertRaises(ValueError):
            self._compose(before, tampered, candidate, invoice_id)
        tampered = deepcopy(after)
        tampered["invoices"][0]["sale"]["total"] = 999
        with self.assertRaises(ValueError):
            self._compose(before, tampered, candidate, invoice_id)
        tampered = deepcopy(after)
        tampered["receipts"].pop("review")
        with self.assertRaises(ValueError):
            self._compose(before, tampered, candidate, invoice_id)
        combined = self._compose(before, after, candidate, invoice_id)
        corrupted = deepcopy(combined)
        corrupted[EXTENSION_KEY]["companies"][COMPANY]["snapshot"]["events"][0]["body"]["lines"][0]["debit_rial"] = 1
        with self.assertRaises(ValueError):
            validate_finance_state(corrupted)
        previous_v2 = load_finance_rial_journal(combined, COMPANY)
        same_source_new_id = self._candidate(combined, event_id="evil-duplicate")
        with self.assertRaises(JournalV2Conflict):
            # The candidate V2 kernel allows different IDs; embedded SQL parity
            # validation must reject a second posting of the same business source.
            self.assertTrue(validate_finance_state({
                **combined, EXTENSION_KEY: {"schemaVersion": 1, "companies": {
                    COMPANY: {"revision": same_source_new_id.revision,
                              "snapshot": __import__("ir_finance_v2_extension")._canonical_snapshot(same_source_new_id)}
                }}}))
        self.assertEqual(len(previous_v2.events), 1)

    def test_rejects_journal_field_injection_unknown_versions_and_unsafe_finance_delta(self):
        before, after, invoice_id = self._prepared_issue()
        candidate = self._candidate(before)
        forged = deepcopy(before)
        forged[EXTENSION_KEY]["unrecognized"] = 1
        with self.assertRaises(ValueError):
            validate_finance_state(forged)
        forged = deepcopy(before)
        forged[EXTENSION_KEY]["schemaVersion"] = 2
        with self.assertRaises(ValueError):
            validate_finance_state(forged)
        forged = deepcopy(before)
        forged[EXTENSION_KEY]["companies"][COMPANY]["revision"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_finance_state(forged)
        legacy_after = deepcopy(before)
        legacy_after["cardCosts"]["card1"] = {"x": "wrong"}
        with self.assertRaises(ValueError):
            self._compose(before, legacy_after, candidate, invoice_id)
        with self.assertRaises(ValueError):
            self._compose(before, before, candidate, invoice_id)


if __name__ == "__main__":
    unittest.main()
