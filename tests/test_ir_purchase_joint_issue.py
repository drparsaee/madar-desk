"""Pure purchase composer contracts on synthetic accounting states only."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from accounting_core import accounting_view
from accounting_service import apply_madar_accounting
from app_storage import UnifiedAppStorage
from collab import empty_state as empty_collab
from finance import empty_finance_state, validate_finance_state
from ir_finance_v2_extension import HostCompanyProof, activate_rial_finance, load_finance_rial_journal
from ir_journal_v2 import FiscalPeriod, new_journal_state
from ir_purchase_joint_issue import compose_purchase_issue_with_rial
from money_policy import snapshot_sha256, MAX_RIAL


NOW = "2026-10-22T10:12:00Z"
COMPANY = "company1"
PROJECT = "p1"
CARD = "card1"
STEP = "step1"
INTAKE = "intake1"
SUPPLIER = {"id": "vendor1", "name": "Synthetic Supplier",
            "kind": "supplier", "reference": "V-42"}


def activate(initial=None):
    initial = initial or empty_finance_state()
    journal = new_journal_state(COMPANY, (
        FiscalPeriod(COMPANY, "FY2026", "2026-01-01", "2026-12-31"),))
    return activate_rial_finance(
        initial, journal,
        proof=HostCompanyProof(COMPANY, "admin", snapshot_sha256(initial)))


class PurchaseComposerTests(unittest.TestCase):
    def setUp(self):
        self.users = {"admin": {"username": "admin", "role": "admin", "projects": None},
                      "editor": {"username": "editor", "role": "editor", "projects": [PROJECT]}}
        self.cards = [{"id": CARD, "projectId": PROJECT, "status": "active",
                       "checklist": [{"id": STEP, "text": "Cut cartons", "done": False}]}]
        self.projects = [{"id": PROJECT, "name": "Synthetic project"}]
        self.finance = activate()
        self.command = None
        self.before = None
        self.after = None

    def run_accounting(self, state, command, *, actor="admin", now=NOW):
        return apply_madar_accounting(
            state, command, actor=actor, accounts=self.users,
            cards=self.cards, projects=self.projects, now=now)

    def stage_bill(self, *, unit_price=120, quantity=7):
        state = self.finance
        for command in (
            {"type": "intake.create", "eventId": "create1", "intakeId": INTAKE,
             "projectId": PROJECT, "cardId": CARD, "stepId": STEP,
             "quantity": quantity, "supplier": deepcopy(SUPPLIER)},
            {"type": "intake.price", "eventId": "price1", "intakeId": INTAKE,
             "unitPrice": unit_price},
            {"type": "intake.convert", "eventId": "convert1", "intakeId": INTAKE},
        ):
            state = self.run_accounting(state, command)["state"]
        bill_id = next(iter(accounting_view(state["accounting"], actor="admin",
                                             accounts=self.users)["bills"]))
        state = self.run_accounting(
            state, {"type": "document.review", "eventId": "review1",
                    "documentId": bill_id, "projectId": PROJECT})["state"]
        self.before = state
        self.command = {"type": "document.issue", "eventId": "issue1",
                        "documentId": bill_id, "projectId": PROJECT,
                        "postingDate": "2026-10-22"}
        self.after = self.run_accounting(state, self.command)["state"]
        return bill_id

    def compose(self, *, before=None, after=None, command=None, actor="admin",
                users=None, cards=None, projects=None, expected_finance_sha256=None,
                expected_journal_revision=None, now=NOW):
        state = before if before is not None else self.before
        journal = load_finance_rial_journal(state, COMPANY)
        return compose_purchase_issue_with_rial(
            state, after if after is not None else self.after,
            command if command is not None else self.command,
            actor=actor, accounts=users if users is not None else self.users,
            cards=cards if cards is not None else self.cards,
            projects=projects if projects is not None else self.projects, now=now,
            expected_finance_sha256=expected_finance_sha256
            if expected_finance_sha256 is not None else snapshot_sha256(state),
            expected_journal_revision=expected_journal_revision
            if expected_journal_revision is not None else journal.revision,
        )

    def test_complete_priced_intake_issues_exact_balanced_rial_candidate(self):
        bill_id = self.stage_bill()
        immutable_after = deepcopy(self.after)
        immutable_before = deepcopy(self.before)
        output = self.compose()
        self.assertEqual(output["state"]["accounting"], self.after["accounting"])
        self.assertEqual(output["state"]["purchaseIntakes"], self.after["purchaseIntakes"])
        self.assertEqual(self.before, immutable_before)
        self.assertEqual(self.after, immutable_after)
        validate_finance_state(output["state"])
        journal = load_finance_rial_journal(output["state"], COMPANY)
        self.assertEqual(len(journal.events), 1)
        event = journal.events[0]
        self.assertEqual(event.source.kind, "independent")
        self.assertEqual(event.source.source_id, bill_id)
        self.assertEqual(event.source.project_id, PROJECT)
        self.assertEqual(event.actor_id, "admin")
        self.assertEqual(sum(x.debit_rial for x in event.lines), 8400)
        self.assertEqual(sum(x.credit_rial for x in event.lines), 8400)
        self.assertEqual(next(x.reference.party_id for x in event.lines
                              if x.credit_rial), SUPPLIER["id"])
        proof = output["sourceContract"]
        self.assertEqual((proof["quantity"], proof["unit_price_toman"],
                          proof["total_toman"], proof["total_rial"]), (7, 120, 840, 8400))
        self.assertEqual(proof["finance_before_sha256"], snapshot_sha256(self.before))
        canonical = json.dumps({k: v for k, v in proof.items()
                                if k != "attestation_sha256"}, ensure_ascii=False,
                               sort_keys=True, separators=(",", ":"), allow_nan=False)
        self.assertEqual(proof["attestation_sha256"],
                         sha256(canonical.encode("utf-8")).hexdigest())
        self.assertEqual(output["result"]["rialAmount"], "8400")
        self.assertEqual(output["result"]["postingMode"], "verified-intake-purchase-shadow")

    def test_unpriced_intake_and_unapproved_bill_rejected_without_posting(self):
        state = self.run_accounting(self.finance, {
            "type": "intake.create", "eventId": "unpriced-create", "intakeId": INTAKE,
            "projectId": PROJECT, "cardId": CARD, "stepId": STEP,
            "quantity": 7, "supplier": deepcopy(SUPPLIER)})["state"]
        command = {"type": "document.issue", "eventId": "issue1",
                   "documentId": "fakebill", "projectId": PROJECT,
                   "postingDate": "2026-10-22"}
        with self.assertRaises(ValueError):
            self.compose(before=state, after=state, command=command)
        self.assertEqual(len(load_finance_rial_journal(state, COMPANY).events), 0)
        self.stage_bill()
        with self.assertRaises(ValueError):
            self.compose(after=self.before)

    def test_forgeries_actor_project_supplier_price_and_link_are_refused(self):
        self.stage_bill()
        with self.assertRaises(PermissionError):
            self.compose(actor="editor")
        with self.assertRaises((ValueError, PermissionError)):
            self.compose(command={**self.command, "projectId": "other"})
        with self.assertRaises((ValueError, PermissionError)):
            self.compose(cards=[{"id": CARD, "projectId": "other",
                                 "checklist": [{"id": STEP, "text": "Cut cartons"}]}])
        with self.assertRaises(ValueError):
            self.compose(after={**self.after, "accountingSources": {}})
        forged = deepcopy(self.before)
        forged["accountingSources"][self.command["documentId"]]["fingerprint"] = "0" * 64
        # Fake source fingerprint still satisfies the generic link schema, but
        # this purchase composer verifies the original intake recipe.
        self.assertTrue(validate_finance_state(forged))
        forged_after = self.run_accounting(forged, self.command)["state"]
        with self.assertRaises(PermissionError):
            self.compose(before=forged, after=forged_after)
        forged = deepcopy(self.before)
        forged["purchaseIntakes"]["records"][INTAKE]["unitPrice"] = 121
        self.assertTrue(validate_finance_state(forged))
        forged_after = self.run_accounting(forged, self.command)["state"]
        with self.assertRaises((ValueError, PermissionError)):
            self.compose(before=forged, after=forged_after)
        forged = deepcopy(self.before)
        forged["purchaseIntakes"]["records"][INTAKE]["supplier"]["name"] = "Forged Vendor"
        self.assertTrue(validate_finance_state(forged))
        forged_after = self.run_accounting(forged, self.command)["state"]
        with self.assertRaises((ValueError, PermissionError)):
            self.compose(before=forged, after=forged_after)

    def test_reject_stale_revision_wrong_snapshots_and_malformed_intent(self):
        self.stage_bill()
        with self.assertRaises(PermissionError):
            self.compose(expected_finance_sha256="0" * 64)
        with self.assertRaises(ValueError):
            self.compose(expected_journal_revision="0" * 64)
        with self.assertRaises(ValueError):
            self.compose(command={**self.command, "actor": "admin"})
        with self.assertRaises(ValueError):
            self.compose(after={**self.after, "nextInvoiceNumber": 2})
        with self.assertRaises(ValueError):
            self.compose(after=self.before)
        with self.assertRaises(ValueError):
            self.compose(now="2026-10-21T10:12:00Z")

    def test_duplicate_event_ids_and_stale_other_bill_cannot_create_second_mirror(self):
        self.stage_bill()
        output = self.compose()
        with self.assertRaises(ValueError):
            self.compose(before=output["state"], after=output["state"])
        # A distinct event ID cannot issue the same already-issued bill.
        duplicate_command = {**self.command, "eventId": "issue-another"}
        with self.assertRaises(ValueError):
            self.compose(before=output["state"], after=output["state"],
                         command=duplicate_command)
        # Make a second, valid standalone bill with its own ID. Its document
        # exists in the legacy event stream, so generic finance validation
        # allows an index referring to it; the duplicate commercial source
        # itself is the hostile mutation the composer must catch.
        before = self.run_accounting(self.before, {
            "type": "document.create", "eventId": "another-bill",
            "kind": "purchase", "documentId": "B-independent",
            "projectId": PROJECT, "partyId": SUPPLIER["id"],
            "documentDate": "2026-10-22",
            "lines": [{"description": "Unrelated draft", "quantity": 1,
                       "unitPrice": 20}]})["state"]
        before["accountingSources"]["B-independent"] = deepcopy(
            before["accountingSources"][self.command["documentId"]])
        self.assertTrue(validate_finance_state(before))
        after = self.run_accounting(before, self.command)["state"]
        with self.assertRaisesRegex(ValueError, "Business work step"):
            self.compose(before=before, after=after)

    def test_float_or_out_of_range_toman_fails_closed(self):
        self.stage_bill()
        wrong = deepcopy(self.before)
        wrong["purchaseIntakes"]["records"][INTAKE]["unitPrice"] = 120.0
        with self.assertRaises(ValueError):
            self.compose(before=wrong, after=wrong)
        self.assertEqual(MAX_RIAL, 9_007_199_254_740_991)
        # Valid TOMAN cap of 10**15 can exceed RIAL cap after x10.
        self.stage_bill(unit_price=900_719_925_474_100, quantity=1)
        with self.assertRaises(ValueError):
            self.compose()

    def test_single_company_and_explicit_period_are_required(self):
        self.stage_bill()
        # Even an independently valid second empty company journal cannot
        # map an existing legacy bill to an authoritative company.
        extra = new_journal_state("company2", (
            FiscalPeriod("company2", "FY2026", "2026-01-01", "2026-12-31"),))
        from ir_finance_v2_extension import _entry
        before = deepcopy(self.before)
        before["rialJournalV2"]["companies"]["company2"] = _entry(extra)
        self.assertTrue(validate_finance_state(before))
        after = self.run_accounting(before, self.command)["state"]
        with self.assertRaises(PermissionError):
            self.compose(before=before, after=after)
        # A RIAL fiscal calendar without the issue's date is valid to store,
        # but cannot be used to infer a period or backfill a purchase.
        wrong = activate(empty_finance_state())
        empty = new_journal_state(COMPANY, (
            FiscalPeriod(COMPANY, "FY2025", "2025-01-01", "2025-12-31"),))
        wrong["rialJournalV2"]["companies"][COMPANY] = _entry(empty)
        self.finance = wrong
        self.stage_bill()
        with self.assertRaisesRegex(ValueError, "fiscal period"):
            self.compose()

    def test_sqlite_host_guard_rejects_purchase_without_matching_authoritative_task(self):
        self.stage_bill()
        result = self.compose()
        # The host now supports a paired old accounting/V2 purchase issue, but
        # must reject one if its actual task snapshot does not contain the
        # source card/project/step. This disposable bundle deliberately uses
        # unrelated sample tasks rather than this test's synthetic card.
        with tempfile.TemporaryDirectory(prefix=".purchase-eval-", dir=Path(__file__).resolve().parents[1]) as tmp:
            store = UnifiedAppStorage(Path(tmp) / "fixture.sqlite3")
            dummy_tasks = __import__("native_app").initial_state()
            bundle = {"tasks": dummy_tasks, "collab": empty_collab(),
                      "finance": self.before, "completion_outbox": []}
            start = store.commit(bundle, expected_revision=0)
            with self.assertRaises((ValueError, PermissionError)):
                store.commit({**bundle, "finance": result["state"]},
                             expected_revision=start.revision)
            self.assertEqual(store.load().bundle, start.bundle)
            self.assertEqual(store.load().revision, start.revision)
            self.assertTrue(store.integrity_check())

    def test_activated_host_storage_accepts_authenticated_unpriced_intake_without_rial_posting(self):
        # RIAL activation allows unpriced intake ONLY via an authenticated
        # command CAS, never by trusting an independently prepared snapshot.
        tasks = __import__("native_app").initial_state()
        card = next(t for t in tasks["tasks"] if t["id"] == "example-2")
        step = next(row for row in card["checklist"] if row.get("id") and row.get("text"))
        command = {"type": "intake.create", "eventId": "intake-first",
                   "intakeId": INTAKE, "projectId": card["projectId"],
                   "cardId": card["id"], "stepId": step["id"],
                   "quantity": 2, "supplier": deepcopy(SUPPLIER)}
        intake = apply_madar_accounting(
            self.finance, command, actor="admin", accounts=self.users,
            cards=tasks["tasks"], projects=tasks["projects"], now=NOW)["state"]
        with tempfile.TemporaryDirectory(prefix=".purchase-eval-", dir=Path(__file__).resolve().parents[1]) as tmp:
            store = UnifiedAppStorage(Path(tmp) / "fixture.sqlite3")
            bundle = {"tasks": tasks,
                      "collab": empty_collab(), "finance": self.finance,
                      "completion_outbox": []}
            first = store.commit(bundle, expected_revision=0)
            with self.assertRaises(PermissionError):
                store.commit({**bundle, "finance": intake},
                             expected_revision=first.revision)
            self.assertEqual(store.load().revision, first.revision)
            accepted = store.commit_authenticated_intake(
                command, actor="admin", accounts=self.users, now=NOW,
                expected_revision=first.revision,
                expected_finance_sha256=snapshot_sha256(self.finance))
            self.assertTrue(accepted["changed"])
            self.assertEqual(accepted["revision"], first.revision + 1)
            self.assertEqual(store.load().bundle["finance"], intake)
            self.assertFalse(load_finance_rial_journal(intake, COMPANY).events)
            self.assertEqual([event["command"]["type"]
                              for event in intake["accounting"]["events"]],
                             ["party.register"])
            self.assertTrue(store.integrity_check())


if __name__ == "__main__":
    unittest.main()
