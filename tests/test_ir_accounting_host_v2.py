"""RIAL host boundary tests. All storage is isolated tempfile SQLite."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ir_accounting_host_v2 import (
    RIALAccountingHost, RIALHostRefusal, TrustedAccountingPrincipal,
    VerifiedIssuedDocument,
)
from ir_chart_model import (
    ChartAccount, ChartSnapshot, CostCenter, DetailBinding, FloatingDetail,
    JobReference, PartyDetailLink, PostingReference,
)
from ir_journal_sqlite import RIALJournalStorage
from ir_journal_v2 import (
    FiscalPeriod, JournalLine, JournalSource, VerifiedScopes,
    JournalV2Conflict, new_journal_state, replay_journal,
)
from money_policy import CompanyMoneyPolicy


def make_chart(company):
    rows = (
        ChartAccount(company, "10", "KOL", None, "Assets", "asset"),
        ChartAccount(company, "1001", "MOEIN", "10", "Receivables", "asset"),
        ChartAccount(company, "100101", "TAFSILI", "1001", "AR", "asset",
                     accountable=True, requires_detail=True),
        ChartAccount(company, "20", "KOL", None, "Liabilities", "liability"),
        ChartAccount(company, "2001", "MOEIN", "20", "Payables", "liability"),
        ChartAccount(company, "200101", "TAFSILI", "2001", "AP", "liability",
                     accountable=True, requires_detail=True),
        ChartAccount(company, "40", "KOL", None, "Revenue", "revenue"),
        ChartAccount(company, "4001", "MOEIN", "40", "Sales", "revenue"),
        ChartAccount(company, "400101", "TAFSILI", "4001", "Sales", "revenue",
                     accountable=True),
        ChartAccount(company, "50", "KOL", None, "Expenses", "expense"),
        ChartAccount(company, "5001", "MOEIN", "50", "Purchases", "expense"),
        ChartAccount(company, "500101", "TAFSILI", "5001", "Materials", "expense",
                     accountable=True),
    )
    return ChartSnapshot(
        company, accounts=rows,
        details=(FloatingDetail(company, "FD-000001", "Customer", "PARTY"),
                 FloatingDetail(company, "FD-000002", "Vendor", "PARTY")),
        bindings=(DetailBinding(company, "100101", "FD-000001"),
                  DetailBinding(company, "200101", "FD-000002")),
        party_links=(PartyDetailLink(company, "customer-1", "FD-000001"),
                     PartyDetailLink(company, "supplier-1", "FD-000002")),
        project_ids=("proj-1", "proj-2"),
        cost_centers=(CostCenter(company, "CC-0001", "proj-1", "Production"),),
        jobs=(JobReference(company, "job-1", "proj-1", "task-1", "CC-0001"),),
    )


def make_scopes():
    return VerifiedScopes(
        party_ids=frozenset({"customer-1", "supplier-1"}),
        project_ids=frozenset({"proj-1", "proj-2"}),
        task_scopes=frozenset({("proj-1", "task-1")}),
        independent_source_scopes=frozenset({
            ("proj-1", "cost-1"), ("proj-1", "cost-2"),
            ("proj-2", "sale-proj-2"),
        }),
    )


def make_document(company="company-A", document_id="sale-1", *, kind="sales",
                  source=None, amount=101, project_id="proj-1"):
    if source is None:
        source = JournalSource("task", "task-1", "proj-1", "task-1")
    task_attrs = (dict(task_id="task-1", job_id="job-1", cost_center_code="CC-0001")
                  if source.kind == "task" else {})
    common = dict(company_id=company, project_id=project_id, **task_attrs)
    if kind == "sales":
        party_id = "customer-1"
        lines = (
            JournalLine(PostingReference(account_code="100101", party_id=party_id,
                                         detail_code="FD-000001", **common),
                        debit_rial=amount),
            JournalLine(PostingReference(account_code="400101", **common),
                        credit_rial=amount),
        )
    else:
        party_id = "supplier-1"
        lines = (
            JournalLine(PostingReference(account_code="500101", **common),
                        debit_rial=amount),
            JournalLine(PostingReference(account_code="200101", party_id=party_id,
                                         detail_code="FD-000002", **common),
                        credit_rial=amount),
        )
    return VerifiedIssuedDocument(
        company, document_id, kind, "issued", "RIAL", amount, party_id,
        project_id, source, lines, True, "none_verified", "rial_v2_only",
    )


class FakeAuthority:
    """Trusted fake, does not use client payload for permissions or amounts."""

    def __init__(self):
        self.sessions = {
            "admin-A": TrustedAccountingPrincipal(
                "admin-A", "company-A", True,
                frozenset({"rial.read", "rial.read_all", "rial.post", "rial.post_all",
                           "rial.reverse", "rial.close_all"}),
                frozenset({"proj-1", "proj-2"})),
            "project-user": TrustedAccountingPrincipal(
                "project-user", "company-A", True,
                frozenset({"rial.read", "rial.post", "rial.reverse"}),
                frozenset({"proj-1"})),
            "read-only": TrustedAccountingPrincipal(
                "auditor", "company-A", True, frozenset({"rial.read"}),
                frozenset({"proj-1"})),
            "admin-B": TrustedAccountingPrincipal(
                "admin-B", "company-B", True,
                frozenset({"rial.read", "rial.read_all", "rial.post", "rial.post_all"}),
                frozenset({"proj-1", "proj-2"})),
        }
        self.documents = {
            "sale-1": make_document(),
            "buy-1": make_document(document_id="buy-1", kind="purchase",
                                   source=JournalSource("independent", "cost-1", "proj-1")),
            "buy-2": make_document(document_id="buy-2", kind="purchase",
                                   source=JournalSource("independent", "cost-1", "proj-1")),
            "sale-other": make_document(document_id="sale-other", project_id="proj-2",
                                        source=JournalSource("independent", "sale-proj-2", "proj-2")),
        }
        self.scopes = make_scopes()

    def authenticate(self, session):
        return self.sessions.get(session)

    def resolve_document(self, company_id, document_id):
        return self.documents[document_id]

    def resolve_chart(self, company_id):
        return make_chart(company_id)

    def resolve_scopes(self, company_id):
        return self.scopes

    def resolve_money_policy(self, company_id):
        return CompanyMoneyPolicy(company_id)


class AccountingHostV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rial-host-v2-")
        self.addCleanup(self.tmp.cleanup)
        self.store = RIALJournalStorage(Path(self.tmp.name) / "rial_v2.db")
        for company in ("company-A", "company-B"):
            self.store.commit(new_journal_state(company, (
                FiscalPeriod(company, "FY26", "2026-01-01", "2026-12-31"),
                FiscalPeriod(company, "FY27", "2027-01-01", "2027-12-31"),
            )), expected_revision=None)
        self.authority = FakeAuthority()
        self.host = RIALAccountingHost(self.store, self.authority)

    def command(self, doc_id="sale-1", *, session="admin-A", **update):
        command = {
            "type": "document.post", "companyId": "company-A", "documentId": doc_id,
            "fiscalPeriodId": "FY26", "postingDate": "2026-10-21",
            "expectedRevision": self.store.read("company-A").revision,
        }
        command.update(update)
        return self.host.command(session, command, today="2026-10-22")

    def test_exact_rial_sales_issued_task_to_journal_and_filtered_read(self):
        reply = self.command(session="project-user")
        self.assertTrue(reply["changed"])
        self.assertEqual(reply["currency"], "RIAL")
        self.assertTrue(reply["eventId"].startswith("rv2.doc."))
        view = self.host.read("project-user", company_id="company-A", project_id="proj-1")
        self.assertEqual(view["postingCount"], 1)
        self.assertEqual(view["entries"][0]["actorId"], "project-user")
        self.assertEqual(view["entries"][0]["source"]["taskId"], "task-1")
        self.assertEqual(view["entries"][0]["lines"][0]["costCenterCode"], "CC-0001")
        self.assertEqual(view["positions"][0]["debitRial"], 101)
        self.assertEqual(replay_journal(self.store.read("company-A")).posted_count, 1)

    def test_purchase_bill_credit_payable_and_source_provenance(self):
        self.command("buy-1")
        view = self.host.read("admin-A", company_id="company-A")
        self.assertEqual(view["postingCount"], 1)
        self.assertEqual(view["entries"][0]["source"]["sourceId"], "cost-1")
        self.assertEqual([l["creditRial"] for l in view["entries"][0]["lines"]], [0, 101])

    def test_posted_retry_with_new_revision_is_idempotent(self):
        first = self.command()
        second = self.command()
        self.assertFalse(second["changed"])
        self.assertEqual(first["eventId"], second["eventId"])
        self.assertEqual(len(self.store.read("company-A").events), 1)

    def test_same_verified_business_source_new_document_id_is_denied_in_sql(self):
        self.command("buy-1")
        before = self.store.read("company-A")
        with self.assertRaises(JournalV2Conflict):
            self.command("buy-2")
        self.assertEqual(self.store.read("company-A"), before)

    def test_eight_concurrent_distinct_documents_same_business_source_one_winner(self):
        for i in range(8):
            self.authority.documents["parallel-" + str(i)] = make_document(
                document_id="parallel-" + str(i), kind="purchase",
                source=JournalSource("independent", "cost-1", "proj-1"))

        def compete(i):
            try:
                self.command("parallel-" + str(i))
                return "committed"
            except JournalV2Conflict:
                return "conflicted"

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(compete, range(8)))
        self.assertEqual(results.count("committed"), 1)
        self.assertEqual(results.count("conflicted"), 7)
        self.assertEqual(replay_journal(self.store.read("company-A")).posted_count, 1)

    def test_conflicting_payload_same_document_id_fails(self):
        self.command()
        self.authority.documents["sale-1"] = make_document(amount=202)
        before = self.store.read("company-A")
        with self.assertRaises(JournalV2Conflict):
            self.command()
        self.assertEqual(self.store.read("company-A"), before)

    def test_stale_revision_and_mutation_roll_back(self):
        original = self.store.read("company-A").revision
        self.command()
        current = self.store.read("company-A")
        with self.assertRaises(JournalV2Conflict):
            self.command("buy-1", expectedRevision=original)
        self.assertEqual(self.store.read("company-A"), current)

    def test_refuse_cross_company_unauthed_and_unauthorized(self):
        for session in ("admin-B", "random", "read-only"):
            with self.assertRaises(PermissionError):
                self.command(session=session)
        with self.assertRaises(PermissionError):
            self.host.read("project-user", company_id="company-A")
        with self.assertRaises(PermissionError):
            self.host.read("project-user", company_id="company-A", project_id="proj-2")
        self.assertEqual(self.store.read("company-A").events, ())

    def test_project_user_cannot_post_or_reverse_another_project(self):
        self.command("sale-other", session="admin-A")
        with self.assertRaises(PermissionError):
            self.command("sale-other", session="project-user")
        original = self.store.read("company-A").events[0].event_id
        with self.assertRaises(PermissionError):
            self.host.command("project-user", {
                "type": "journal.reverse", "companyId": "company-A",
                "originalEventId": original, "fiscalPeriodId": "FY27",
                "postingDate": "2027-01-03", "reason": "Correction",
                "expectedRevision": self.store.read("company-A").revision,
            }, today="2027-01-04")

    def test_scoped_read_hides_unrelated_projects(self):
        self.command("sale-other")
        self.command("sale-1")
        view = self.host.read("project-user", company_id="company-A", project_id="proj-1")
        self.assertEqual(view["postingCount"], 1)
        self.assertEqual(view["entries"][0]["source"]["sourceId"], "task-1")
        self.assertEqual(view["positions"][0]["debitRial"], 101)
        self.assertEqual(self.host.read("admin-A", company_id="company-A")["postingCount"], 2)

    def test_refuse_unverified_company_party_project_or_alias_source(self):
        initial = self.store.read("company-A")
        invalid = [
            replace(make_document(), source_verified=False),
            replace(make_document(), company_id="company-B"),
            replace(make_document(), party_id="unknown-party"),
            replace(make_document(), project_id="proj-2"),
            replace(make_document(), source=JournalSource("card", "task-1", "proj-1", "task-1")),
        ]
        for bad in invalid:
            self.authority.documents["sale-1"] = bad
            with self.subTest(bad=bad):
                with self.assertRaises((RIALHostRefusal, ValueError)):
                    self.command()
                self.assertEqual(self.store.read("company-A"), initial)

    def test_refuse_legacy_toman_and_unverified_migration_state(self):
        base = make_document()
        initial = self.store.read("company-A")
        for changes in (
            {"ledger_origin": "legacy_toman"},
            {"legacy_finance_status": "linked"},
            {"legacy_finance_status": "unknown"},
            {"status": "approved"},
            {"currency": "TOMAN"},
        ):
            self.authority.documents["sale-1"] = replace(base, **changes)
            with self.subTest(changes=changes):
                with self.assertRaises(RIALHostRefusal):
                    self.command()
                self.assertEqual(self.store.read("company-A"), initial)

    def test_refuse_inexact_amount_totals_or_mismatched_receivable(self):
        base = make_document()
        bad_cases = [
            replace(base, amount_rial=101.0),
            replace(base, amount_rial=True),
            replace(base, amount_rial=102),
            replace(base, lines=tuple(replace(line, reference=replace(line.reference,
                                party_id="")) if line.reference.party_id else line
                                for line in base.lines)),
        ]
        for doc in bad_cases:
            self.authority.documents["sale-1"] = doc
            with self.subTest(amount=doc.amount_rial, lines=doc.lines):
                with self.assertRaises(ValueError):
                    self.command()
        self.assertFalse(self.store.read("company-A").events)

    def test_requires_revenue_or_purchase_business_side(self):
        source = make_document()
        wrong_sale_lines = (source.lines[0], replace(
            source.lines[1], reference=replace(source.lines[1].reference,
                                               account_code="100101")))
        # This invalid sale appears balanced and has AR, but no revenue.
        self.authority.documents["sale-1"] = replace(source, lines=wrong_sale_lines)
        with self.assertRaises(RIALHostRefusal):
            self.command()
        self.assertFalse(self.store.read("company-A").events)

    def test_ui_cannot_supply_actor_amount_scopes_or_extra_arguments(self):
        original = self.store.read("company-A")
        with self.assertRaises(RIALHostRefusal):
            self.command(actorId="admin-A", amountRial=500, projectIds=["proj-2"])
        self.assertEqual(self.store.read("company-A"), original)

    def test_journal_reversal_and_period_close_authorization(self):
        post = self.command()
        original = post["eventId"]
        after_post = self.store.read("company-A").revision
        with self.assertRaises(PermissionError):
            self.host.command("project-user", {
                "type": "period.close", "companyId": "company-A",
                "fiscalPeriodId": "FY26", "closingDate": "2027-01-01",
                "expectedRevision": after_post,
            }, today="2027-01-04")
        closed = self.host.command("admin-A", {
            "type": "period.close", "companyId": "company-A",
            "fiscalPeriodId": "FY26", "closingDate": "2027-01-01",
            "expectedRevision": after_post,
        }, today="2027-01-04")
        self.assertTrue(closed["changed"])
        with self.assertRaises(ValueError):
            self.command("buy-1")
        reversed_out = self.host.command("admin-A", {
            "type": "journal.reverse", "companyId": "company-A",
            "originalEventId": original, "fiscalPeriodId": "FY27",
            "postingDate": "2027-01-03", "reason": "Issued in error",
            "expectedRevision": self.store.read("company-A").revision,
        }, today="2027-01-04")
        self.assertTrue(reversed_out["changed"])
        replay = replay_journal(self.store.read("company-A"))
        self.assertEqual(replay.reversed_event_ids, frozenset({original}))
        self.assertEqual(sum(x.debit_minus_credit_rial for x in replay.positions), 0)
        self.assertTrue(all(x.debit_minus_credit_rial == 0 for x in replay.positions))
        with self.assertRaises(JournalV2Conflict):
            self.host.command("admin-A", {
                "type": "journal.reverse", "companyId": "company-A",
                "originalEventId": original, "fiscalPeriodId": "FY27",
                "postingDate": "2027-01-05", "reason": "Try again",
                "expectedRevision": self.store.read("company-A").revision,
            }, today="2027-01-06")


if __name__ == "__main__":
    unittest.main()
