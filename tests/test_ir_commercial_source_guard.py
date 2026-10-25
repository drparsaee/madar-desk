"""Synthetic, read-only commercial source identity and cross-ledger checks."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ir_commercial_source_guard import (
    CommercialCandidate, CommercialEvidence, CommercialIdentity,
    CommercialSourceConflict, CommercialSourceError, CommercialV2Binding,
    LegacyCommercialPosting, MirrorAuthorization, normalize_commercial_kind,
    preflight_commercial_source,
)
from ir_company_registry import (
    CompanyRegistry, FiscalYear, LegalEntity, ProjectAssignment, PostedLock,
    RegisteredCompany, RegistryCommand, VerifiedRegistryAuthority,
    apply_registry_command,
)
from ir_chart_model import ChartAccount, ChartSnapshot, JobReference, PostingReference
from ir_journal_v2 import (
    FiscalPeriod, JournalLine, JournalSource, VerifiedScopes, new_journal_state,
    post_journal, reverse_journal,
)
from money_policy import CompanyMoneyPolicy, MAX_RIAL


def identity(company="company-A", project="project-A", kind="sale", doc="invoice-1"):
    return CommercialIdentity(company, project, kind, doc)


def registry(*, second=False):
    state = CompanyRegistry()
    for company, project, actor in (
            [("company-A", "project-A", "admin-A")] +
            ([("company-B", "project-B", "admin-B")] if second else [])):
        authority = VerifiedRegistryAuthority(
            actor, True, True, frozenset({(project, company)}))
        registered = RegisteredCompany(
            company, LegalEntity("Synthetic " + company),
            (FiscalYear(company, "FY1", "2026-01-01", "2026-12-31"),))
        state = apply_registry_command(
            state, RegistryCommand("REGISTER", company, actor,
                                   "register." + company, registered),
            authority=authority, expected_revision=state.revision)
        state = apply_registry_command(
            state, RegistryCommand("PROJECT_ASSIGN", company, actor,
                                   "assign." + company,
                                   ProjectAssignment(company, project)),
            authority=authority, expected_revision=state.revision)
    return state


def source(ident, *, type_="independent", source_id=None):
    if source_id is None:
        source_id = ident.registry_source_id
    if type_ == "task":
        return JournalSource("task", source_id, ident.project_id, task_id=source_id)
    return JournalSource(type_, source_id, ident.project_id)


def legacy(ident=None, *, event="legacy-1", ledger=None, amount=10, party="party-1"):
    ident = ident or identity()
    return LegacyCommercialPosting(
        ident, ledger or ("finance.sales" if ident.kind == "sale"
                         else "accounting.bill"),
        event, amount, party)


def candidate(ident=None, *, event="v2-1", ledger="rial_v2",
              amount=100, src=None, party="party-1"):
    ident = ident or identity()
    return CommercialCandidate(
        ident, ledger, event, amount,
        src if ledger == "rial_v2" else None, party)


def mirror(ident=None, *, legacy_event="legacy-1", v2_event="v2-1",
           src=None, amount=100, party="party-1", ledger=None):
    ident = ident or identity()
    return MirrorAuthorization(
        ident, ledger or ("finance.sales" if ident.kind == "sale"
                         else "accounting.bill"),
        legacy_event, v2_event, src or source(ident), amount, party)


def chart(company="company-A", project="project-A", task_id=""):
    return ChartSnapshot(company, accounts=(
        ChartAccount(company, "10", "KOL", None, "Asset", "asset"),
        ChartAccount(company, "1001", "MOEIN", "10", "Asset 1", "asset"),
        ChartAccount(company, "100101", "TAFSILI", "1001",
                     "Receivable", "asset", accountable=True),
        ChartAccount(company, "20", "KOL", None, "Liability", "liability"),
        ChartAccount(company, "2001", "MOEIN", "20", "Liability 1", "liability"),
        ChartAccount(company, "200101", "TAFSILI", "2001",
                     "Payable", "liability", accountable=True),
        ChartAccount(company, "40", "KOL", None, "Revenue", "revenue"),
        ChartAccount(company, "4001", "MOEIN", "40", "Revenue 1", "revenue"),
        ChartAccount(company, "400101", "TAFSILI", "4001",
                     "Sales", "revenue", accountable=True),
        ChartAccount(company, "50", "KOL", None, "Expenses", "expense"),
        ChartAccount(company, "5001", "MOEIN", "50", "Expense 1", "expense"),
        ChartAccount(company, "500101", "TAFSILI", "5001",
                     "Purchase", "expense", accountable=True),
    ), project_ids=(project,),
        jobs=(JobReference(company, "job-" + task_id, project, task_id),)
        if task_id else ())


def blank_journal(company="company-A"):
    return new_journal_state(
        company, (FiscalPeriod(company, "P1", "2026-01-01", "2026-12-31"),))


def posted(journal=None, ident=None, *, event="v2-1", src=None, amount=100):
    ident = ident or identity()
    journal = journal or blank_journal(ident.company_id)
    src = src or source(ident)
    debit, credit = (("100101", "400101") if ident.kind == "sale"
                     else ("500101", "200101"))
    return post_journal(
        journal, company_id=ident.company_id,
        fiscal_period_id="P1", event_id=event,
        actor_id="admin-A", posting_date="2026-06-01",
        source=src,
        lines=(JournalLine(PostingReference(
            ident.company_id, debit, project_id=ident.project_id,
            task_id=src.task_id,
            job_id=("job-" + src.task_id) if src.task_id else ""), debit_rial=amount),
               JournalLine(PostingReference(
                   ident.company_id, credit, project_id=ident.project_id,
                   task_id=src.task_id,
                   job_id=("job-" + src.task_id) if src.task_id else ""),
                   credit_rial=amount)),
        chart=chart(ident.company_id, ident.project_id, src.task_id),
        scopes=VerifiedScopes(
            project_ids=frozenset({ident.project_id}),
            independent_source_scopes=frozenset(
                {(ident.project_id, src.source_id)} if src.kind == "independent"
                else set()),
            task_scopes=frozenset(
                {(ident.project_id, src.source_id)} if src.kind == "task"
                else set()),
        ),
        money_policy=CompanyMoneyPolicy(ident.company_id),
        expected_revision=journal.revision, today="2026-10-22")


def context(*, reg=None, old=(), journals=(), bindings=(), mirrors=(),
            excluded=frozenset(), second=False, pairs=None, actor="admin-A",
            authenticated=True):
    return CommercialEvidence(
        actor, authenticated, reg or registry(second=second),
        frozenset(pairs if pairs is not None else (
            {("project-A", "company-A"),
             ("project-B", "company-B")} if second
            else {("project-A", "company-A")})),
        tuple(old), tuple(journals), tuple(bindings),
        frozenset(excluded), tuple(mirrors),
    )


class CommercialSourceGuardTests(unittest.TestCase):
    def refuse(self, fn, error=(CommercialSourceError, PermissionError)):
        with self.assertRaises(error):
            fn()

    def test_kind_aliases_normalized_strictly(self):
        self.assertEqual(normalize_commercial_kind("sale"), "sale")
        self.assertEqual(normalize_commercial_kind("sales"), "sale")
        self.assertEqual(normalize_commercial_kind("purchase"), "purchase")
        for bad in ("SALE", "sales ", "invoice", "bill", "buy", "refund",
                    "inventory", "", None, [], True, 1):
            with self.subTest(bad=bad):
                self.refuse(lambda: normalize_commercial_kind(bad))

    def test_sale_and_sales_yield_same_registry_hash(self):
        one = identity(kind="sale")
        other = identity(kind="sales")
        self.assertEqual(one, other)
        self.assertEqual(one.registry_source_id, other.registry_source_id)
        self.assertTrue(one.registry_source_id.startswith("co."))
        self.assertEqual(len(one.registry_source_id), 67)

    def test_different_kind_or_project_or_company_never_alias(self):
        base = identity()
        for different in (identity(kind="purchase"),
                          identity(project="project-B"),
                          identity(company="company-B")):
            self.assertNotEqual(base.registry_source_id, different.registry_source_id)

    def test_new_legacy_issued_sale_only_requires_exact_registered_owner(self):
        proposed = candidate(event="legacy-new", ledger="finance.sales",
                             amount=100)
        result = preflight_commercial_source(context(), proposed)
        self.assertEqual(result.disposition, "NEW")
        self.assertEqual(result.registry_source_id, identity().registry_source_id)

    def test_new_purchase_from_verified_project(self):
        ident = identity(kind="purchase", doc="bill-1")
        intent = candidate(ident, ledger="accounting.bill", event="bill-issue-1")
        self.assertEqual(preflight_commercial_source(
            context(), intent).disposition, "NEW")

    def test_new_v2_requires_explicit_source_binding(self):
        ident = identity()
        src = source(ident)
        intent = candidate(ident, src=src)
        self.refuse(lambda: preflight_commercial_source(
            context(journals=(blank_journal(),)), intent))
        ready = context(journals=(blank_journal(),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),))
        self.assertEqual(preflight_commercial_source(
            ready, intent).disposition, "NEW")

    def test_idempotent_retry_identical_existing_sale_event(self):
        original = legacy()
        ready = context(old=(original,))
        intent = candidate(event=original.issue_event_id, ledger=original.ledger)
        self.assertEqual(preflight_commercial_source(
            ready, intent).disposition, "RETRY")

    def test_same_invoice_new_legacy_event_id_fails(self):
        ready = context(old=(legacy(event="issued-1"),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ledger="finance.sales", event="issued-2")),
            CommercialSourceConflict)

    def test_same_purchase_bill_different_event_id_fails(self):
        ident = identity(kind="purchase", doc="bill-1")
        ready = context(old=(legacy(ident, event="bill-event-1"),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ident, ledger="accounting.bill",
                             event="bill-event-2")), CommercialSourceConflict)

    def test_amount_mutation_under_same_legacy_event_denied(self):
        ready = context(old=(legacy(),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(event="legacy-1", ledger="finance.sales", amount=101)),
            CommercialSourceConflict)

    def test_party_change_under_same_legacy_event_denied(self):
        ready = context(old=(legacy(),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(event="legacy-1", ledger="finance.sales",
                             party="other-party")), CommercialSourceConflict)

    def test_legacy_amount_bool_fraction_negative_and_overflow_refused(self):
        for value in (True, 0, -1, 1.5, MAX_RIAL // 10 + 1):
            with self.subTest(value=value):
                self.refuse(lambda: legacy(amount=value))

    def test_journal_replay_different_event_id_same_source_refused(self):
        ident = identity()
        src = source(ident)
        jrn = posted(ident=ident, event="other-v2-event", src=src)
        ready = context(journals=(jrn,),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ident, event="new-v2-event", src=src)),
            CommercialSourceConflict)

    def test_idempotent_v2_retry_after_original_posting(self):
        ident = identity()
        src = source(ident)
        jrn = posted(ident=ident, event="v2-1")
        ready = context(journals=(jrn,),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),))
        self.assertEqual(preflight_commercial_source(
            ready, candidate(ident, src=src)).disposition, "RETRY")

    def test_different_v2_amount_under_same_event_refused(self):
        ident = identity()
        src = source(ident)
        ready = context(journals=(posted(ident=ident),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ident, src=src, amount=300)), CommercialSourceConflict)

    def test_unpaired_legacy_plus_v2_refused(self):
        ident = identity()
        src = source(ident)
        ready = context(old=(legacy(ident),), journals=(blank_journal(),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ident, src=src)), CommercialSourceConflict)

    def test_intended_atomic_legacy_to_rial_mirror_allowed_with_exact_proof(self):
        ident = identity()
        src = source(ident)
        ready = context(old=(legacy(ident),), journals=(blank_journal(),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),),
                        mirrors=(mirror(ident, src=src),))
        decision = preflight_commercial_source(
            ready, candidate(ident, src=src))
        self.assertEqual(decision.disposition, "PAIRED_MIRROR")

    def test_intended_atomic_rial_to_legacy_mirror_allowed(self):
        ident = identity()
        src = source(ident)
        ready = context(journals=(posted(ident=ident),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),),
                        mirrors=(mirror(ident, src=src),))
        proposed = candidate(ident, event="legacy-1", ledger="finance.sales")
        self.assertEqual(preflight_commercial_source(
            ready, proposed).disposition, "PAIRED_MIRROR")

    def test_already_mirrored_pair_can_be_retried(self):
        ident = identity()
        src = source(ident)
        ready = context(old=(legacy(ident),), journals=(posted(ident=ident),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),),
                        mirrors=(mirror(ident, src=src),))
        self.assertEqual(preflight_commercial_source(
            ready, candidate(ident, src=src)).disposition, "RETRY")
        self.assertEqual(preflight_commercial_source(
            ready, candidate(ident, event="legacy-1",
                             ledger="finance.sales")).disposition, "RETRY")

    def test_existing_paired_postings_without_proof_denied(self):
        ident = identity()
        src = source(ident)
        ready = context(old=(legacy(ident),), journals=(posted(ident=ident),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ident, src=src)), CommercialSourceConflict)

    def test_mirror_wrong_legacy_event_refused(self):
        ident = identity()
        src = source(ident)
        ready = context(old=(legacy(ident),), journals=(blank_journal(),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),),
                        mirrors=(mirror(ident, legacy_event="fake", src=src),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ident, src=src)), CommercialSourceConflict)

    def test_mirror_wrong_v2_event_refused(self):
        ident = identity()
        src = source(ident)
        ready = context(old=(legacy(ident),), journals=(blank_journal(),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),),
                        mirrors=(mirror(ident, v2_event="forged", src=src),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ident, src=src)), CommercialSourceConflict)

    def test_mirror_amount_or_party_mismatch_refused(self):
        ident = identity()
        src = source(ident)
        for proof in (
                mirror(ident, amount=101, src=src),
                mirror(ident, party="other-party", src=src)):
            with self.subTest(proof=proof):
                ready = context(old=(legacy(ident),), journals=(blank_journal(),),
                                bindings=(CommercialV2Binding(ident, src, "party-1"),),
                                mirrors=(proof,))
                self.refuse(lambda: preflight_commercial_source(
                    ready, candidate(ident, src=src)), CommercialSourceConflict)

    def test_mirror_ledger_kind_mismatch_refused(self):
        ident = identity()
        self.refuse(lambda: mirror(ident, ledger="accounting.bill"))
        self.refuse(lambda: candidate(
            ident, ledger="accounting.bill", event="purchase-masquerade"))

    def test_purchase_bill_plus_v2_verified_mirror(self):
        ident = identity(kind="purchase", doc="bill-1")
        src = source(ident)
        ready = context(old=(legacy(ident, event="legacy-1"),),
                        journals=(blank_journal(),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),),
                        mirrors=(mirror(ident, src=src),))
        self.assertEqual(preflight_commercial_source(
            ready, candidate(ident, src=src)).disposition, "PAIRED_MIRROR")

    def test_sale_source_task_alias_requires_explicit_binding(self):
        ident = identity()
        src = source(ident, type_="task", source_id="card-1")
        ready = context(old=(legacy(ident),), journals=(blank_journal(),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),),
                        mirrors=(mirror(ident, src=src),))
        self.assertEqual(preflight_commercial_source(
            ready, candidate(ident, src=src)).disposition, "PAIRED_MIRROR")
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ident, src=source(ident, type_="task",
                                               source_id="wrong-card"))))

    def test_registry_co_hash_must_match_exact_company_project_kind_doc(self):
        ident = identity()
        foreign = source(identity(doc="another"))
        self.refuse(lambda: CommercialV2Binding(ident, foreign))
        self.refuse(lambda: candidate(ident, src=foreign))
        self.refuse(lambda: CommercialV2Binding(
            ident, source(ident, type_="task", source_id=ident.registry_source_id)))

    def test_duplicate_v2_source_link_to_two_documents_refused(self):
        one = identity()
        another = identity(doc="invoice-2")
        task_source = source(one, type_="task", source_id="task-1")
        ready = context(journals=(blank_journal(),), bindings=(
            CommercialV2Binding(one, task_source),
            CommercialV2Binding(another, task_source)))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(one, src=task_source, party="")), CommercialSourceConflict)

    def test_duplicate_v2_document_aliases_refused(self):
        one = identity()
        ready = context(journals=(blank_journal(),), bindings=(
            CommercialV2Binding(one, source(one)),
            CommercialV2Binding(one, source(one, type_="task", source_id="task-1"))))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(one, src=source(one), party="")),
            CommercialSourceConflict)

    def test_duplicate_legacy_issue_events_same_document_alternate_ids_refused(self):
        ready = context(old=(legacy(event="legacy-1"),
                             legacy(event="legacy-2")))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(event="legacy-1", ledger="finance.sales")),
            CommercialSourceConflict)

    def test_duplicate_legacy_ledger_for_one_source_refused(self):
        ready = context(old=(legacy(event="finance-1"),
                             legacy(event="accounting-1",
                                    ledger="accounting.invoice")))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(event="finance-1", ledger="finance.sales")),
            CommercialSourceConflict)

    def test_event_id_reused_across_other_legacy_documents_refused(self):
        ready = context(old=(legacy(event="shared", party="party-1"),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(identity(doc="invoice-2"),
                             ledger="finance.sales", event="shared")),
            CommercialSourceConflict)

    def test_cross_company_same_invoice_number_not_duplicate(self):
        other = identity("company-B", "project-B", "sales", "invoice-1")
        ready = context(old=(legacy(identity(), event="existing-A"),),
                        second=True, journals=(blank_journal("company-A"),
                                              blank_journal("company-B")),
                        bindings=(CommercialV2Binding(other, source(other), "party-1"),))
        result = preflight_commercial_source(
            ready, candidate(other, src=source(other), event="existing-A"))
        self.assertEqual(result.disposition, "NEW")
        self.assertNotEqual(result.registry_source_id, identity().registry_source_id)

    def test_cross_company_project_claim_denied(self):
        forged = identity("company-B", "project-A", "sale", "invoice-1")
        self.refuse(lambda: preflight_commercial_source(
            context(second=True), candidate(forged, ledger="finance.sales")))

    def test_ambiguous_host_project_owner_denied(self):
        bogus_pairs = {("project-A", "company-A"),
                       ("project-A", "company-B")}
        self.refuse(lambda: preflight_commercial_source(
            context(pairs=bogus_pairs), candidate(
                ledger="finance.sales", event="new")))

    def test_unregistered_project_fails_closed(self):
        self.refuse(lambda: preflight_commercial_source(
            context(), candidate(identity(project="unknown"),
                                 ledger="finance.sales")))

    def test_unverified_client_context_refused(self):
        self.refuse(lambda: preflight_commercial_source(
            context(authenticated=False), candidate(ledger="finance.sales")),
            PermissionError)

    def test_missing_v2_classification_fails_closed_even_for_other_documents(self):
        ident = identity()
        ready = context(journals=(posted(ident=ident),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ledger="finance.sales")))

    def test_explicit_noncommercial_v2_source_not_confused_with_invoice(self):
        ident = identity()
        src = source(ident, type_="task", source_id="noncommercial-task")
        jrn = posted(ident=ident, src=src, event="noncommercial-event")
        ready = context(journals=(jrn,), excluded={
            ("company-A", src)})
        self.assertEqual(preflight_commercial_source(
            ready, candidate(ledger="finance.sales", event="new")).disposition, "NEW")

    def test_cannot_mark_commercial_v2_source_noncommercial(self):
        ident = identity()
        src = source(ident)
        ready = context(journals=(blank_journal(),),
                        bindings=(CommercialV2Binding(ident, src),),
                        excluded={("company-A", src)})
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ident, src=src, party="")))

    def test_legacy_post_with_unknown_company_rejected_in_history(self):
        foreign = identity("unknown", "project-A")
        ready = context(old=(legacy(foreign),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ledger="finance.sales")))

    def test_legacy_same_doc_id_different_project_rejected(self):
        # An original committed company document cannot silently change project.
        reg = registry()
        attested = VerifiedRegistryAuthority(
            "admin-A", True, False,
            frozenset({("project-C", "company-A")}))
        reg = apply_registry_command(reg, RegistryCommand(
            "PROJECT_ASSIGN", "company-A", "admin-A", "assign.project-C",
            ProjectAssignment("company-A", "project-C")),
            authority=attested, expected_revision=reg.revision)
        original = identity()
        changed = identity(project="project-C")
        ready = context(reg=reg, old=(legacy(original),),
                        pairs={("project-A", "company-A"), ("project-C", "company-A")})
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(changed, ledger="finance.sales", event="other")),
            CommercialSourceConflict)

    def test_v2_reversal_does_not_permit_second_issue_by_new_event(self):
        ident = identity()
        src = source(ident)
        base = posted(ident=ident, event="v2-1")
        reversed_state = reverse_journal(
            base, company_id=ident.company_id, original_event_id="v2-1",
            event_id="reversal-v2-1", actor_id="admin-A",
            fiscal_period_id="P1", posting_date="2026-06-02",
            reason="void", expected_revision=base.revision,
            today="2026-10-22")
        ready = context(journals=(reversed_state,),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ident, event="reissue", src=src)), CommercialSourceConflict)

    def test_duplicate_journal_snapshots_for_one_company_refused(self):
        ready = context(journals=(blank_journal(), blank_journal()))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ledger="finance.sales")))

    def test_registry_posted_lock_with_missing_v2_event_fails_closed(self):
        ident = identity()
        reg = registry()
        auth = VerifiedRegistryAuthority(
            "admin-A", True, False,
            frozenset({("project-A", "company-A")}),
            verified_postings=frozenset({(
                "company-A", "project-A", "FY1", ident.registry_source_id)}))
        reg = apply_registry_command(
            reg, RegistryCommand("POSTED_LOCK", "company-A", "admin-A",
                                 "lock-sale", PostedLock(
                                     "company-A", "project-A", "FY1",
                                     ident.registry_source_id)),
            authority=auth, expected_revision=reg.revision)
        self.refuse(lambda: preflight_commercial_source(
            context(reg=reg), candidate(ident, ledger="finance.sales")),
            CommercialSourceConflict)

    def test_registry_orphan_lock_cannot_be_laundered_as_verified_mirror(self):
        ident = identity()
        reg = registry()
        host = VerifiedRegistryAuthority(
            "admin-A", True, False,
            frozenset({("project-A", "company-A")}),
            verified_postings=frozenset({
                ("company-A", "project-A", "FY1", ident.registry_source_id)}))
        reg = apply_registry_command(
            reg, RegistryCommand("POSTED_LOCK", "company-A", "admin-A",
                                 "lock-sale", PostedLock(
                                     "company-A", "project-A", "FY1",
                                     ident.registry_source_id)),
            authority=host, expected_revision=reg.revision)
        src = source(ident)
        ready = context(reg=reg, old=(legacy(ident),),
                        journals=(blank_journal(),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),),
                        mirrors=(mirror(ident, src=src),))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ident, src=src)), CommercialSourceConflict)

    def test_two_historical_mirror_pairs_remain_independent(self):
        first = identity()
        second = identity(doc="invoice-2")
        first_source, second_source = source(first), source(second)
        journal = posted(ident=first, event="v2-1")
        journal = posted(journal=journal, ident=second, event="v2-2")
        ready = context(
            old=(legacy(first), legacy(second, event="legacy-2")),
            journals=(journal,),
            bindings=(CommercialV2Binding(first, first_source, "party-1"),
                      CommercialV2Binding(second, second_source, "party-1")),
            mirrors=(mirror(first),
                     mirror(second, legacy_event="legacy-2", v2_event="v2-2")))
        self.assertEqual(preflight_commercial_source(
            ready, candidate(first, src=first_source)).disposition, "RETRY")
        self.assertEqual(preflight_commercial_source(
            ready, candidate(second, event="legacy-2",
                             ledger="finance.sales")).disposition, "RETRY")

    def test_duplicate_mirror_attestation_for_same_document_refused(self):
        ident = identity()
        src = source(ident)
        ready = context(old=(legacy(ident),), journals=(blank_journal(),),
                        bindings=(CommercialV2Binding(ident, src, "party-1"),),
                        mirrors=(mirror(ident), mirror(ident)))
        self.refuse(lambda: preflight_commercial_source(
            ready, candidate(ident, src=src)), CommercialSourceConflict)

    def test_cannot_mix_noninteger_rial_candidate(self):
        for amount in (True, 0, -1, MAX_RIAL + 1, 100.5):
            with self.subTest(amount=amount):
                self.refuse(lambda: candidate(ledger="finance.sales", amount=amount))

    def test_evidence_is_immutable_and_preflight_has_no_mutations(self):
        ready = context(old=(legacy(),))
        before = repr(ready)
        with self.assertRaises(FrozenInstanceError):
            ready.authenticated = False
        try:
            preflight_commercial_source(
                ready, candidate(ledger="finance.sales", event="different"))
        except CommercialSourceConflict:
            pass
        self.assertEqual(repr(ready), before)


if __name__ == "__main__":
    unittest.main()
