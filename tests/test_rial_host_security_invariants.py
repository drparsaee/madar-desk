"""Hostile synthetic RIAL host tests. Only disposable SQLite files are created.

Security pass here refers to the exercised host/domain entrypoints. No HTTP
listener, real APPDATA, real user database, or Windows executable is launched.
"""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import native_app
from app_storage import UnifiedAppStorage, RevisionConflict
from collab import empty_state as empty_collab
from finance import apply_finance_command, empty_finance_state
from ir_chart_model import ChartAccount, ChartSnapshot, JobReference, PostingReference
from ir_finance_v2_extension import (
    VerifiedInvoiceSourceProof, _entry, compose_finance_rial_snapshot,
    load_finance_rial_journal,
)
from ir_journal_v2 import (
    JournalLine, JournalSource, VerifiedScopes, post_journal,
)
from lan import LanService
from money_policy import CompanyMoneyPolicy, snapshot_sha256

COMPANY = "company-A"
TODAY = "2026-10-22"
NOW = TODAY + "T11:00:00Z"
ACTIVATE = {"companyId": COMPANY, "fiscalPeriodId": "FY26",
            "startDate": "2026-01-01", "endDate": "2026-12-31"}
PROJECT = "p-sample"
CARD = "example-2"


def chart():
    return ChartSnapshot(COMPANY, accounts=(
        ChartAccount(COMPANY, "10", "KOL", None, "Assets", "asset"),
        ChartAccount(COMPANY, "1001", "MOEIN", "10", "Receivables", "asset"),
        ChartAccount(COMPANY, "100101", "TAFSILI", "1001", "AR", "asset", accountable=True),
        ChartAccount(COMPANY, "40", "KOL", None, "Revenue", "revenue"),
        ChartAccount(COMPANY, "4001", "MOEIN", "40", "Sales", "revenue"),
        ChartAccount(COMPANY, "400101", "TAFSILI", "4001", "Sales", "revenue",
                     accountable=True),
    ), project_ids=(PROJECT,), jobs=(JobReference(COMPANY, "job-1", PROJECT, CARD),))


def journal_post(state, event_id, *, source_project=PROJECT, line_company=COMPANY,
                 line_project=PROJECT, verified=True, amount=1200):
    scopes = VerifiedScopes(
        project_ids=frozenset({PROJECT}) if verified else frozenset(),
        task_scopes=frozenset({(PROJECT, CARD)}) if verified else frozenset())
    source = JournalSource("task", CARD, source_project, CARD)
    lines = (
        JournalLine(PostingReference(line_company, "100101", project_id=line_project,
                                     job_id="job-1", task_id=CARD), debit_rial=amount),
        JournalLine(PostingReference(line_company, "400101", project_id=line_project,
                                     job_id="job-1", task_id=CARD), credit_rial=amount),
    )
    return post_journal(
        state, company_id=COMPANY, fiscal_period_id="FY26", event_id=event_id,
        actor_id="local", posting_date=TODAY, source=source, lines=lines,
        chart=chart(), scopes=scopes, money_policy=CompanyMoneyPolicy(COMPANY),
        expected_revision=state.revision, today=TODAY)


class RialHostSecurityInvariants(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix=".rial-host-security-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = UnifiedAppStorage(self.root / "synthetic-unified.sqlite3")
        tasks = native_app.initial_state()
        self.store.commit({"tasks": tasks, "collab": empty_collab(),
                           "finance": empty_finance_state(), "completion_outbox": []},
                          expected_revision=0)
        # Bypass Bridge.__init__ to prevent all APPDATA/global side effects.
        self.bridge = native_app.Bridge.__new__(native_app.Bridge)
        self.bridge._unified_store = self.store
        self.bridge._lock = threading.RLock()
        self.bridge.lan = None
        self.bridge.connection = {"mode": "solo"}
        self.bridge.state = tasks
        self.bridge._finance_warning = ""
        self.bridge._observed_local_revision = __import__("lan").revision(tasks)
        self.bridge._ui_cas_required = False
        self.bridge._automatic_backup_before_change = lambda: None
        self.bridge.offline = SimpleNamespace(publish=lambda **kwargs: None)
        self.bridge.path = self.root / "synthetic-task-lock.json"
        self.bridge.collab_path = self.root / "synthetic-collab.json"
        self.bridge.finance_path = self.root / "synthetic-finance.json"
        self.bridge.finance_outbox_path = self.root / "synthetic-outbox.json"
        self.bridge.automation_outbox_path = self.root / "synthetic-automation-outbox.json"

    def active(self):
        result = self.bridge.rialJournalActivate(dict(ACTIVATE))
        self.assertEqual(result["status"], "activated-empty-only")
        return self.store.load()

    def replace_finance(self, finance):
        current = self.store.load()
        return self.store.commit({**current.bundle, "finance": finance},
                                 expected_revision=current.revision)

    def command(self, current, event_type, event_id, **fields):
        return apply_finance_command(
            current, {"type": event_type, "eventId": event_id, **fields},
            actor="local", accounts={"local": {"username": "local", "role": "admin",
                                               "projects": None}},
            cards=self.store.load().bundle["tasks"]["tasks"],
            projects=self.store.load().bundle["tasks"]["projects"], now=NOW)["state"]

    def prepare_issued_candidate(self):
        active = self.active()
        draft = self.command(active.bundle["finance"], "contract.set", "sale",
                             cardId=CARD, sale={
                                 "customer": {"name": "Synthetic buyer", "reference": "buyer"},
                                 "lines": [{"id": "ln", "description": "Work",
                                            "quantity": 1, "unitPrice": 120}],
                                 "discount": 0, "tax": 0, "advance": 0,
                                 "autoInvoice": True})
        self.replace_finance(draft)
        task_bundle = deepcopy(self.store.load().bundle["tasks"])
        next_card = next(t for t in task_bundle["tasks"] if t["id"] == CARD)
        next_card["status"] = "done"
        prior = self.store.load()
        self.store.commit({**prior.bundle, "tasks": task_bundle},
                          expected_revision=prior.revision)
        created = self.command(self.store.load().bundle["finance"], "completion.record",
                               "complete", cardId=CARD, completionId="complete-1")
        self.replace_finance(created)
        invoice_id = self.store.load().bundle["finance"]["invoices"][0]["id"]
        reviewed = self.command(self.store.load().bundle["finance"], "invoice.review",
                                "review", invoiceId=invoice_id)
        self.replace_finance(reviewed)
        before = self.store.load()
        after_finance = self.command(before.bundle["finance"], "invoice.issue",
                                     "issue-toman", invoiceId=invoice_id)
        prior_rial = load_finance_rial_journal(before.bundle["finance"], COMPANY)
        posted_rial = journal_post(prior_rial, "issue-rial")
        invoice = after_finance["invoices"][0]
        proof = VerifiedInvoiceSourceProof(
            COMPANY, "local", invoice_id, PROJECT, CARD,
            invoice["snapshotHash"], invoice["sale"]["total"],
            snapshot_sha256(before.bundle["finance"]), snapshot_sha256(after_finance))
        pair = compose_finance_rial_snapshot(
            before.bundle["finance"], after_finance, posted_rial,
            expected_journal_revision=prior_rial.revision, proof=proof)
        return before, after_finance, pair

    def test_old_snapshot_downgrade_and_historic_restore_are_rejected(self):
        legacy = self.store.load()
        active = self.active()
        with self.assertRaisesRegex(ValueError, "RIAL"):
            self.store.commit(legacy.bundle, expected_revision=active.revision)
        with self.assertRaisesRegex(ValueError, "RIAL"):
            self.store.restore(legacy.revision, expected_revision=active.revision)
        with self.assertRaises(RevisionConflict):
            self.store.commit(legacy.bundle, expected_revision=legacy.revision)
        self.assertEqual(self.store.load().revision, active.revision)
        self.assertIn("rialJournalV2", self.store.load().bundle["finance"])

    def test_older_lan_client_task_snapshot_preserves_active_finance(self):
        service = LanService(self.bridge, self.root / "synthetic-lan-users.json")
        service.setup_owner("owner", "OwnerPassword-2026!")
        token = service.authenticate("owner", "OwnerPassword-2026!")["token"]
        old_client = service.read_state(token)
        activated = self.active()
        # Old LAN clients submit only a task snapshot; finance is server owned.
        service.write_state(token, old_client["state"], old_client["revision"])
        after = self.store.load()
        self.assertIn("rialJournalV2", after.bundle["finance"])
        self.assertEqual(after.bundle["finance"], activated.bundle["finance"])
        self.assertTrue(self.store.integrity_check())
        self.assertEqual(service.read_state(token)["state"], old_client["state"])

    def test_host_activation_requires_empty_legacy_and_stays_atomic(self):
        before = self.store.load()
        financial = self.command(before.bundle["finance"], "contract.set", "contract-old",
                                 cardId=CARD, sale={
                                     "customer": {"name": "Synthetic buyer", "reference": "buyer"},
                                     "lines": [{"id": "ln", "description": "Work",
                                                "quantity": 1, "unitPrice": 120}],
                                     "discount": 0, "tax": 0, "advance": 0,
                                     "autoInvoice": True})
        stale = self.replace_finance(financial)
        with self.assertRaisesRegex(ValueError, "Legacy TOMAN"):
            self.bridge.rialJournalActivate(dict(ACTIVATE))
        self.assertEqual(self.store.load().revision, stale.revision)
        self.assertNotIn("rialJournalV2", self.store.load().bundle["finance"])

    def test_forged_company_and_project_rejected_by_verified_posting(self):
        current = self.active()
        state = load_finance_rial_journal(current.bundle["finance"], COMPANY)
        for scenario in (
            {"line_company": "other-company"},
            {"source_project": "p-personal", "line_project": "p-personal"},
            {"verified": False},
        ):
            with self.subTest(scenario=scenario), self.assertRaises(ValueError):
                journal_post(state, "forged-" + str(len(scenario)), **scenario)
        self.assertEqual(self.store.load().revision, current.revision)

    def test_same_business_source_different_event_id_fails_sql_boundary(self):
        before, _, pair = self.prepare_issued_candidate()
        posted = self.replace_finance(pair)
        self.assertEqual(len(load_finance_rial_journal(posted.bundle["finance"], COMPANY).events), 1)
        # Pure kernel's event-ID idempotency alone is insufficient: the SQL
        # serialization/host must check business-source identity independently.
        first = load_finance_rial_journal(posted.bundle["finance"], COMPANY)
        second = journal_post(first, "posted-B")
        # The first serialization boundary rejects a second ID for that source.
        with self.assertRaisesRegex(ValueError, "Business source"):
            _entry(second)
        self.assertEqual(self.store.load().revision, posted.revision)

    def test_commit_exception_after_insertion_rolls_back_all_domains(self):
        active = self.active()
        candidate = deepcopy(active.bundle)
        candidate["tasks"]["settings"]["theme"] = "dark"
        candidate["collab"] = deepcopy(active.bundle["collab"])
        original = UnifiedAppStorage._insert

        def crash_after_insert(cls, connection, raw, current, source):
            original(connection, raw, current, source)
            raise OSError("synthetic interruption after INSERT and head UPDATE")

        with patch.object(UnifiedAppStorage, "_insert", classmethod(crash_after_insert)):
            with self.assertRaisesRegex(OSError, "synthetic interruption"):
                self.store.commit(candidate, expected_revision=active.revision)
        persisted = self.store.load()
        self.assertEqual(persisted.revision, active.revision)
        self.assertEqual(persisted.bundle, active.bundle)
        self.assertEqual(self.store.history(), [active.revision, 1])
        self.assertTrue(self.store.integrity_check())

    def test_legacy_only_invoice_issue_is_denied_after_activation(self):
        before, after_finance, pair = self.prepare_issued_candidate()
        with self.assertRaisesRegex(ValueError, "joint issue"):
            self.replace_finance(after_finance)
        self.assertEqual(self.store.load().revision, before.revision)
        # This confirms valid atomic storage, NOT a public host API for issuing
        # both sides. Host wiring is a separate requirement and is not invoked.
        committed = self.replace_finance(pair)
        self.assertEqual(committed.revision, before.revision + 1)
        self.assertEqual(committed.bundle["finance"], pair)
        self.assertEqual(len(load_finance_rial_journal(pair, COMPANY).events), 1)

    def test_native_host_joint_issue_is_single_cas_and_exact_replay(self):
        before, _, _ = self.prepare_issued_candidate()
        invoice_id = before.bundle["finance"]["invoices"][0]["id"]
        command = {"type": "invoice.issue", "eventId": "issue-toman", "invoiceId": invoice_id}
        issued = self.bridge.financeCommand(command)
        self.assertEqual(issued["postingMode"], "legacy-task-sales-shadow")
        self.assertEqual(issued["rialAmount"], "1200")
        current = self.store.load()
        self.assertEqual(current.revision, before.revision + 1)
        self.assertEqual(len(current.bundle["finance"]["ledger"]),
                         len(before.bundle["finance"]["ledger"]) + 1)
        journal = load_finance_rial_journal(current.bundle["finance"], COMPANY)
        self.assertEqual(len(journal.events), 1)
        self.assertEqual(sum(line.debit_rial for line in journal.events[0].lines), 1200)
        self.assertEqual(sum(line.credit_rial for line in journal.events[0].lines), 1200)
        replay_result = self.bridge.financeCommand(command)
        self.assertEqual(replay_result, issued)
        self.assertEqual(self.store.load().revision, current.revision)
        with self.assertRaises(ValueError):
            self.bridge.financeCommand({**command, "eventId": "second-event-for-same-invoice"})
        self.assertEqual(self.store.load().revision, current.revision)
        self.assertTrue(self.store.integrity_check())

    def test_trusted_finance_cas_blocks_intervening_finance_mutation(self):
        before, _, pair = self.prepare_issued_candidate()
        intervening = self.command(before.bundle["finance"], "contract.set", "another-contract",
                                   cardId=CARD, sale={
                                       "customer": {"name": "Synthetic buyer", "reference": "buyer"},
                                       "lines": [{"id": "line2", "description": "Different work",
                                                  "quantity": 1, "unitPrice": 99}],
                                       "discount": 0, "tax": 0, "advance": 0,
                                       "autoInvoice": False})
        later = self.replace_finance(intervening)
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            self.bridge._commit_domain("finance", pair,
                                       expected_finance_sha256=snapshot_sha256(before.bundle["finance"]))
        self.assertEqual(self.store.load().revision, later.revision)
        self.assertEqual(self.store.load().bundle["finance"], intervening)

    def test_lan_editor_finance_grant_cannot_activate_or_read_rial(self):
        active = self.active()
        service = LanService(self.bridge, self.root / "synthetic-users.json")
        service.setup_owner("owner", "OwnerPassword-2026!")
        owner = service.authenticate("owner", "OwnerPassword-2026!")["token"]
        service.upsert_user(owner, {"username": "editor", "password": "EditorPassword-2026!",
                                   "role": "editor", "projects": [PROJECT]})
        service.users["editor"]["financeEdit"] = True  # hostile grant, even if separately provisioned
        editor = service.authenticate("editor", "EditorPassword-2026!")["token"]
        with self.assertRaises(PermissionError):
            service.rial_journal_activate(editor, dict(ACTIVATE))
        with self.assertRaises(PermissionError):
            service.rial_journal_read(
                editor, {"companyId": COMPANY, "fiscalPeriodId": "FY26"})
        with self.assertRaises(PermissionError):
            service.rial_journal_read(
                "forged-bearer", {"companyId": COMPANY, "fiscalPeriodId": "FY26"})
        self.assertEqual(self.store.load().revision, active.revision)

    def test_unpriced_supplier_intake_does_not_issue_invoice_or_debt(self):
        created = self.bridge.accountingCommand({
            "type": "intake.create", "eventId": "intake-a", "intakeId": "in-1",
            "projectId": PROJECT, "cardId": CARD, "stepId": "step-2-0", "quantity": 5,
            "supplier": {"id": "vendor-a", "name": "Synthetic Vendor",
                         "kind": "supplier", "reference": ""}})
        self.assertEqual(created["status"], "unpriced")
        self.assertEqual(created["bookedPayable"], 0)
        with self.assertRaises(ValueError):
            self.bridge.accountingCommand(
                {"type": "intake.convert", "eventId": "unpriced-convert", "intakeId": "in-1"})
        view = self.bridge.accountingRead(PROJECT)
        self.assertFalse(view["documents"])
        self.assertEqual(view["purchaseIntakes"][0]["unitPrice"], None)
        self.assertEqual(next(v["payable"] for v in view["balances"]
                              if v["partyId"] == "vendor-a"), 0)

    def test_rial_invoice_preview_payload_not_exposed_as_unverified_host_post(self):
        self.active()
        with self.assertRaises(ValueError):
            self.bridge.rialJournalRead({
                "companyId": COMPANY, "fiscalPeriodId": "FY26",
                "invoiceKind": "purchase", "invoiceId": "in-1", "previewOnly": True})
        self.assertEqual(self.bridge.rialJournalRead({
            "companyId": COMPANY, "fiscalPeriodId": "FY26"})["journals"], [])


if __name__ == "__main__":
    unittest.main()
