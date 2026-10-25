"""Synthetic immutable Iranian company registry and fail-closed host GL gate tests."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ir_company_registry import (
    CompanyRegistry, CompanyBankRef, CompanyCashRef, CompanyPartyRef,
    FinanceGrant, FiscalYear, LegacyProjectLink, LegalEntity, PostedLock,
    ProjectAssignment, RegisteredCompany, RegistryCommand, RegistryConflict,
    RegistryError, UserPresentation, VerifiedRegistryAuthority,
    apply_registry_command, company_money_policy, presentation_unit,
    read_company_registry, replay_registry, resolve_project_company, stable_financial_source_id,
    verify_sale_purchase_gl_gate,
)
from ir_chart_model import ChartAccount, ChartSnapshot
from ir_journal_v2 import (
    FiscalPeriod, JournalLine, JournalSource, VerifiedScopes, PostingReference,
    new_journal_state, close_fiscal_period, post_journal,
)
from money_policy import CompanyMoneyPolicy, snapshot_sha256


def legal(name="Company Sample"):
    return LegalEntity(name)


def fy(company="co-A", year="FY26", start="2026-01-01", end="2026-12-31"):
    return FiscalYear(company, year, start, end)


def company(company_id="co-A"):
    return RegisteredCompany(company_id, legal(), (fy(company_id),))


def authority(actor="admin-A", *, admin=True, pairs=None, authenticated=True,
              verified_postings=None, registration=True):
    return VerifiedRegistryAuthority(
        actor_id=actor, authenticated=authenticated,
        registration_right=registration,
        project_company_pairs=frozenset(
            {("project-A", "co-A"), ("project-B", "co-B")}
            if pairs is None else pairs),
        bank_accounts=frozenset({("co-A", "bank-A", "iban-A")}),
        cashboxes=frozenset({("co-A", "cash-A")}),
        parties=frozenset({("co-A", "customer-A")}),
        verified_postings=frozenset(verified_postings or ()),
        verified_legacy_links=frozenset({("co-A", "project-A", "legacy-A")}),
    )


def cmd(action, payload, *, actor="admin-A", company_id="co-A", source=None):
    return RegistryCommand(action, company_id, actor,
                           source or ("src." + action.lower()), payload)


def apply(old, c, *, actor=None, expected_revision=None, host=None):
    return apply_registry_command(
        old, c, authority=host or authority(actor or c.actor_id),
        expected_revision=old.revision if expected_revision is None else expected_revision)


def base():
    old = CompanyRegistry()
    return apply(old, cmd("REGISTER", company()), host=authority())


def assigned():
    old = base()
    return apply(old, cmd("PROJECT_ASSIGN",
                          ProjectAssignment("co-A", "project-A")))


def scoped():
    old = assigned()
    return apply(old, cmd("PARTY_ADD", CompanyPartyRef("co-A", "customer-A")))


def chart(project_ids=("project-A",), company_id="co-A"):
    return ChartSnapshot(company_id=company_id, project_ids=project_ids, accounts=(
        ChartAccount(company_id, "10", "KOL", None, "Assets", "asset"),
        ChartAccount(company_id, "1001", "MOEIN", "10", "Receivables", "asset"),
        ChartAccount(company_id, "100101", "TAFSILI", "1001", "AR",
                     "asset", accountable=True),
        ChartAccount(company_id, "40", "KOL", None, "Revenue", "revenue"),
        ChartAccount(company_id, "4001", "MOEIN", "40", "Sales", "revenue"),
        ChartAccount(company_id, "400101", "TAFSILI", "4001", "Revenue",
                     "revenue", accountable=True),
    ))


def journal(company_id="co-A"):
    return new_journal_state(company_id, (
        FiscalPeriod(company_id, "P1", "2026-01-01", "2026-06-30"),
        FiscalPeriod(company_id, "P2", "2026-07-01", "2026-12-31"),
    ))


def scopes(company_id="co-A", project="project-A", party="customer-A",
           kind="sale", doc="doc-A"):
    source = stable_financial_source_id(company_id, project, kind, doc)
    return VerifiedScopes(
        project_ids=frozenset({project}),
        party_ids=frozenset({party}),
        independent_source_scopes=frozenset({(project, source)}),
    )


def gate(registry, **overrides):
    kwargs = dict(
        company_id="co-A", project_id="project-A", fiscal_year_id="FY26",
        fiscal_period_id="P1", posting_date="2026-04-01",
        actor_id="admin-A", kind="sale", document_id="doc-A",
        authority=authority(), journal_state=journal(),
        chart=chart(), scopes=scopes(), party_id="customer-A",
    )
    kwargs.update(overrides)
    return verify_sale_purchase_gl_gate(registry, **kwargs)


class RegistryTests(unittest.TestCase):
    def reject(self, callback, error=(RegistryError, ValueError, PermissionError)):
        with self.assertRaises(error):
            callback()

    def test_empty_registry_has_no_inferred_company(self):
        empty = CompanyRegistry()
        self.assertEqual(replay_registry(empty).companies, ())
        self.assertEqual(replay_registry(empty).assignments, ())
        self.reject(lambda: resolve_project_company(
            empty, "project-A",
            verified_project_company_pairs=frozenset({("project-A", "co-A")})))

    def test_registration_bootstraps_only_explicit_company_admin(self):
        state = base()
        view = replay_registry(state)
        self.assertEqual(view.companies[0].company_id, "co-A")
        self.assertEqual(view.companies[0].currency, "RIAL")
        self.assertEqual(view.companies[0].presentation_unit, "RIAL")
        self.assertEqual(view.assignments, ())
        self.assertEqual(view.grants[0], FinanceGrant("co-A", "admin-A", "finance_admin"))
        self.assertEqual(view.companies[0].legal.national_id, "")
        self.assertEqual(view.companies[0].legal.registration_number, "")
        self.assertEqual(len(state.events[0].event_hash), 64)

    def test_registration_requires_host_privilege_and_authenticated_actor(self):
        first = cmd("REGISTER", company())
        self.reject(lambda: apply(CompanyRegistry(), first,
                                  host=authority(registration=False)), PermissionError)
        self.reject(lambda: apply(CompanyRegistry(), first,
                                  host=authority(authenticated=False)), PermissionError)
        self.reject(lambda: apply(CompanyRegistry(), first,
                                  host=authority(actor="forged")), PermissionError)

    def test_legal_identifiers_remain_optional_and_never_generated(self):
        self.assertEqual(LegalEntity("Example").economic_code, "")
        supplied = LegalEntity("Example", national_id="12345678901",
                               registration_number="42", economic_code="A129", tax_id="TX/15")
        self.assertEqual(supplied.national_id, "12345678901")
        self.reject(lambda: LegalEntity(" "))
        self.reject(lambda: LegalEntity("A", national_id="incorrect id"))
        self.reject(lambda: LegalEntity("A", tax_id="a\nb"))
        self.reject(lambda: LegalEntity("A", registration_number=12))

    def test_fiscal_periods_nonoverlap_and_exact_gregorian_dates(self):
        self.reject(lambda: RegisteredCompany("co-A", legal(), (
            fy(), fy(year="FY27", start="2026-12-31", end="2027-12-31"))))
        self.reject(lambda: RegisteredCompany("co-A", legal(), (fy(), fy())))
        self.reject(lambda: fy(start="2026-02-30"))
        self.reject(lambda: fy(start="2026-07-01", end="2026-06-30"))
        self.reject(lambda: fy(company="co-A", start="۱۴۰۵-۰۱-۰۱"))
        self.reject(lambda: RegisteredCompany("co-A", legal(), (fy("co-B"),)))
        self.reject(lambda: RegisteredCompany("co-A", legal(), ()))

    def test_fiscal_year_add_and_replacement_before_posting(self):
        state = base()
        next_year = fy(year="FY27", start="2027-01-01", end="2027-12-31")
        state = apply(state, cmd("YEAR_ADD", next_year, source="add-FY27"))
        self.assertEqual(len(replay_registry(state).companies[0].fiscal_years), 2)
        revised = fy(year="FY27", start="2027-02-01", end="2027-12-31")
        state = apply(state, cmd("YEAR_REPLACE", revised, source="fix-FY27"))
        self.assertEqual(replay_registry(state).companies[0].fiscal_years[-1], revised)
        self.reject(lambda: apply(state, cmd("YEAR_ADD", revised, source="again")))
        self.reject(lambda: apply(state, cmd(
            "YEAR_REPLACE", fy(year="FY99"), source="missing-year")))

    def test_fiscal_year_overlap_prevented_across_commands(self):
        state = base()
        overlap = fy(year="FY27", start="2026-12-15", end="2027-11-30")
        self.reject(lambda: apply(state, cmd("YEAR_ADD", overlap, source="overlap")))
        self.assertEqual(len(replay_registry(state).companies[0].fiscal_years), 1)

    def test_unknown_project_no_automatic_assignment_or_fallback(self):
        state = base()
        self.reject(lambda: resolve_project_company(
            state, "project-A",
            verified_project_company_pairs=frozenset({("project-A", "co-A")})))
        self.reject(lambda: gate(state))

    def test_project_explicit_assignment_requires_authoritative_exact_mapping(self):
        state = base()
        binding = cmd("PROJECT_ASSIGN", ProjectAssignment("co-A", "project-A"))
        self.reject(lambda: apply(state, binding,
                                  host=authority(pairs={("project-A", "co-B")})),
                    PermissionError)
        state = apply(state, binding)
        self.assertEqual(resolve_project_company(
            state, "project-A", verified_project_company_pairs=frozenset(
                {("project-A", "co-A")})), "co-A")
        self.reject(lambda: resolve_project_company(
            state, "project-A",
            verified_project_company_pairs=frozenset({("project-A", "co-B")})))

    def test_project_assignment_refuses_ambiguous_host_company_owner(self):
        initial = base()
        self.reject(lambda: apply(initial, cmd(
            "PROJECT_ASSIGN", ProjectAssignment("co-A", "project-A")),
            host=authority(pairs={
                ("project-A", "co-A"), ("project-A", "co-B")})), PermissionError)

    def test_ambiguous_host_project_mapping_is_refused(self):
        state = assigned()
        self.reject(lambda: resolve_project_company(
            state, "project-A",
            verified_project_company_pairs=frozenset({
                ("project-A", "co-A"), ("project-A", "co-B")})))
        self.reject(lambda: resolve_project_company(
            state, "project-A", verified_project_company_pairs=frozenset()))
        self.reject(lambda: resolve_project_company(
            state, "project-A", verified_project_company_pairs={("project-A", "co-A")}))

    def test_duplicate_project_across_companies_rejected(self):
        state = assigned()
        b_company = RegisteredCompany("co-B", LegalEntity("Other"), (fy("co-B"),))
        state = apply(state, cmd("REGISTER", b_company,
                                 company_id="co-B", source="register-B"))
        foreign = cmd("PROJECT_ASSIGN", ProjectAssignment("co-B", "project-A"),
                      company_id="co-B", source="assign-foreign")
        self.reject(lambda: apply(state, foreign, host=authority(
            pairs={("project-A", "co-B")})), RegistryConflict)

    def test_bank_cash_and_party_only_from_verified_host_scope(self):
        state = base()
        state = apply(state, cmd("BANK_ADD", CompanyBankRef("co-A", "bank-A", "iban-A")))
        state = apply(state, cmd("CASH_ADD", CompanyCashRef("co-A", "cash-A")))
        state = apply(state, cmd("PARTY_ADD", CompanyPartyRef("co-A", "customer-A")))
        projection = replay_registry(state)
        self.assertEqual(len(projection.banks), 1)
        self.assertEqual(len(projection.cashboxes), 1)
        self.assertEqual(len(projection.parties), 1)
        self.reject(lambda: apply(base(), cmd("BANK_ADD",
                         CompanyBankRef("co-A", "bank-X", "other-iban"))), PermissionError)
        self.reject(lambda: apply(base(), cmd("PARTY_ADD",
                         CompanyPartyRef("co-A", "not-verified"))), PermissionError)
        self.reject(lambda: apply(base(), cmd("CASH_ADD",
                         CompanyCashRef("co-A", "unknown-cash"))), PermissionError)

    def test_role_grants_and_display_preference_are_company_scoped(self):
        state = base()
        state = apply(state, cmd("GRANT",
                                 FinanceGrant("co-A", "issuer-A", "finance_issuer")))
        state = apply(state, cmd("GRANT",
                                 FinanceGrant("co-A", "reader-A", "finance_reader"),
                                 source="grant-reader"))
        self.assertEqual(presentation_unit(
            state, company_id="co-A", principal_id="reader-A"), "RIAL")
        state = apply(state, cmd("COMPANY_DISPLAY", "TOMAN", source="display-co"))
        self.assertEqual(presentation_unit(
            state, company_id="co-A", principal_id="issuer-A"), "TOMAN")
        state = apply(state, cmd("USER_DISPLAY",
                                 UserPresentation("co-A", "reader-A", "RIAL"),
                                 actor="reader-A", source="display-self"),
                      host=authority(actor="reader-A"))
        self.assertEqual(presentation_unit(
            state, company_id="co-A", principal_id="reader-A"), "RIAL")
        self.assertEqual(company_money_policy(
            state, company_id="co-A", principal_id="reader-A").accounting_currency,
                         "RIAL")
        self.assertEqual(company_money_policy(
            state, company_id="co-A", principal_id="issuer-A").display_unit, "TOMAN")

    def test_scoped_company_reader_does_not_disclose_other_entity(self):
        state = base()
        foreign = RegisteredCompany(
            "co-B", LegalEntity("Private company B", national_id="01234567890"),
            (fy("co-B"),))
        state = apply(state, cmd("REGISTER", foreign, company_id="co-B",
                                 source="register-B"))
        state = apply(state, cmd("GRANT", FinanceGrant(
            "co-A", "reader-A", "finance_reader")))
        view = read_company_registry(
            state, company_id="co-A", authority=authority(actor="reader-A"))
        self.assertEqual(view.company.company_id, "co-A")
        self.assertTrue(all(grant.company_id == "co-A" for grant in view.grants))
        self.assertNotIn("co-B", repr(view))
        self.assertNotIn("Private company B", repr(view))
        self.assertNotIn("01234567890", repr(view))
        self.reject(lambda: read_company_registry(
            state, company_id="co-B", authority=authority(actor="reader-A")),
            PermissionError)
        self.reject(lambda: read_company_registry(
            state, company_id="co-A", authority=authority(actor="stranger")),
            PermissionError)

    def test_reader_cannot_escalate_or_grant_and_issuer_cannot_manage(self):
        state = base()
        state = apply(state, cmd("GRANT",
                                 FinanceGrant("co-A", "reader-A", "finance_reader")))
        state = apply(state, cmd("GRANT",
                                 FinanceGrant("co-A", "issuer-A", "finance_issuer"),
                                 source="issuer-grant"))
        self.reject(lambda: apply(state, cmd("GRANT",
                    FinanceGrant("co-A", "reader-A", "finance_admin"),
                    actor="reader-A", source="reader-escalate"),
                    host=authority(actor="reader-A")), PermissionError)
        self.reject(lambda: apply(state, cmd("COMPANY_DISPLAY", "TOMAN",
                    actor="issuer-A", source="issuer-display"),
                    host=authority(actor="issuer-A")), PermissionError)
        self.reject(lambda: apply(state, cmd(
            "USER_DISPLAY", UserPresentation("co-A", "admin-A", "TOMAN"),
            actor="reader-A", source="impersonate"),
            host=authority(actor="reader-A")), PermissionError)
        self.reject(lambda: presentation_unit(
            state, company_id="co-A", principal_id="outsider"), PermissionError)

    def test_admin_must_revoke_exact_role_no_final_admin_revocation(self):
        state = base()
        self.reject(lambda: apply(state, cmd(
            "REVOKE", FinanceGrant("co-A", "admin-A", "finance_admin"))),
            RegistryConflict)
        state = apply(state, cmd("GRANT", FinanceGrant(
            "co-A", "other-admin", "finance_admin")))
        state = apply(state, cmd("REVOKE", FinanceGrant(
            "co-A", "other-admin", "finance_admin"), source="revoke-other"))
        self.assertEqual(len(replay_registry(state).grants), 1)
        self.reject(lambda: apply(state, cmd(
            "REVOKE", FinanceGrant("co-A", "other-admin", "finance_admin"),
            source="again")), RegistryConflict)

    def test_grant_upgrade_needs_explicit_revocation_by_admin(self):
        state = apply(base(), cmd(
            "GRANT", FinanceGrant("co-A", "reader-A", "finance_reader")))
        self.reject(lambda: apply(state, cmd(
            "GRANT", FinanceGrant("co-A", "reader-A", "finance_admin"),
            source="upgrade")), RegistryConflict)
        state = apply(state, cmd(
            "REVOKE", FinanceGrant("co-A", "reader-A", "finance_reader"),
            source="revoke-reader"))
        state = apply(state, cmd(
            "GRANT", FinanceGrant("co-A", "reader-A", "finance_issuer"),
            source="authorized-issuer"))
        self.assertIn(FinanceGrant("co-A", "reader-A", "finance_issuer"),
                      replay_registry(state).grants)

    def test_legacy_links_require_explicit_mapping_and_host_evidence(self):
        state = assigned()
        link = LegacyProjectLink("co-A", "project-A", "legacy-A")
        self.reject(lambda: apply(state, cmd(
            "LEGACY_LINK", LegacyProjectLink("co-A", "project-A", "forged"))),
            PermissionError)
        state = apply(state, cmd("LEGACY_LINK", link))
        self.assertEqual(replay_registry(state).legacy_links, (link,))
        self.reject(lambda: apply(state, cmd(
            "LEGACY_LINK", link, source="duplicate-link")), RegistryConflict)
        self.reject(lambda: apply(base(), cmd(
            "LEGACY_LINK", link)), RegistryError)

    def test_posted_lock_requires_real_host_commit_proof(self):
        state = assigned()
        lock = PostedLock("co-A", "project-A", "FY26", "invoice-issued-1")
        self.reject(lambda: apply(state, cmd("POSTED_LOCK", lock)), PermissionError)
        proof = authority(verified_postings={
            ("co-A", "project-A", "FY26", "invoice-issued-1")})
        state = apply(state, cmd("POSTED_LOCK", lock), host=proof)
        self.assertEqual(replay_registry(state).posted_locks, (lock,))

    def test_posted_legal_identity_and_fiscal_period_immutable(self):
        state = assigned()
        lock = PostedLock("co-A", "project-A", "FY26", "issued-1")
        state = apply(state, cmd("POSTED_LOCK", lock), host=authority(
            verified_postings={("co-A", "project-A", "FY26", "issued-1")}))
        self.reject(lambda: apply(state, cmd(
            "LEGAL_UPDATE", LegalEntity("Changed legal identity"))), RegistryConflict)
        self.reject(lambda: apply(state, cmd(
            "YEAR_REPLACE", fy(end="2026-11-30"))), RegistryConflict)
        self.reject(lambda: apply(state, cmd(
            "POSTED_LOCK", lock, source="same-source-again"),
            host=authority(verified_postings={
                ("co-A", "project-A", "FY26", "issued-1")})), RegistryConflict)
        # Appending a future disjoint fiscal year does not rewrite posted FY26.
        state = apply(state, cmd("YEAR_ADD", fy(year="FY27",
            start="2027-01-01", end="2027-12-31")))
        self.assertEqual(len(replay_registry(state).companies[0].fiscal_years), 2)
        self.reject(lambda: apply(state, cmd(
            "YEAR_REPLACE", fy(year="FY27", start="2027-02-01",
                                end="2027-12-31"))), RegistryConflict)

    def test_unposted_legal_identity_change_is_explicit_and_audited(self):
        original = base()
        changed = apply(original, cmd(
            "LEGAL_UPDATE", LegalEntity("New legal entity", national_id="12345678901")))
        self.assertEqual(replay_registry(original).companies[0].legal.legal_name,
                         "Company Sample")
        self.assertEqual(replay_registry(changed).companies[0].legal.legal_name,
                         "New legal entity")
        self.assertNotEqual(original.revision, changed.revision)

    def test_idempotent_retry_and_changed_source_payload(self):
        state = base()
        c = state.events[0].command
        self.assertIs(apply(state, c), state)
        changed = replace(c, payload=company("co-A"))
        self.assertIs(apply(state, changed), state)
        different = replace(c, payload=replace(company(), legal=LegalEntity("Different")))
        self.reject(lambda: apply(state, different), RegistryConflict)

    def test_stale_cas_is_refused_even_for_exact_retry(self):
        baseline = CompanyRegistry()
        state = base()
        self.reject(lambda: apply(state, state.events[0].command,
                                  expected_revision=baseline.revision), RegistryConflict)

    def test_reused_business_source_different_action_rejected(self):
        state = base()
        self.reject(lambda: apply(state, cmd(
            "LEGAL_UPDATE", LegalEntity("Another"), source="src.register")),
            RegistryConflict)
        self.assertEqual(len(state.events), 1)

    def test_cross_company_command_payload_refused(self):
        self.reject(lambda: cmd("PROJECT_ASSIGN", ProjectAssignment(
            "co-B", "project-A")))
        self.reject(lambda: cmd("BANK_ADD", CompanyBankRef(
            "co-B", "bank-A", "iban-A")))
        self.reject(lambda: cmd("POSTED_LOCK", PostedLock(
            "co-B", "project-A", "FY26", "source-1")))

    def test_history_tampering_detected_and_immutable(self):
        state = base()
        with self.assertRaises(FrozenInstanceError):
            state.events = ()
        event = state.events[0]
        forged = replace(event, digest="a" * 64)
        self.reject(lambda: replay_registry(replace(state, events=(forged,))))
        changed = replace(event.command, actor_id="other")
        self.reject(lambda: replay_registry(replace(
            state, events=(replace(event, command=changed),))))
        # Hashes are integrity evidence only: full DB forgery needs external anchoring.
        digest = snapshot_sha256({"action": changed.action,
            "company": changed.company_id, "actor": changed.actor_id,
            "source": changed.source_id, "payload": {
                "company_id": "co-A",
                "legal": {"legal_name": "Company Sample",
                          "national_id": "", "registration_number": "",
                          "economic_code": "", "tax_id": "",
                          "registered_address": ""},
                "fiscal_years": [{"company_id": "co-A",
                    "fiscal_year_id": "FY26", "start_date": "2026-01-01",
                    "end_date": "2026-12-31"}],
                "presentation_unit": "RIAL", "currency": "RIAL"}})
        head = snapshot_sha256({"commandDigest": digest, "previousHash": "0" * 64})
        synthetic_forgery = replace(state, events=(
            replace(event, command=changed, digest=digest, event_hash=head),))
        self.assertNotEqual(state.revision, synthetic_forgery.revision)
        self.assertEqual(replay_registry(synthetic_forgery).companies[0].company_id,
                         "co-A")

    def test_gl_gate_happy_path_explicit_verified_project_and_period(self):
        state = scoped()
        result = gate(state)
        self.assertEqual(result.company_id, "co-A")
        self.assertEqual(result.project_id, "project-A")
        self.assertEqual(result.fiscal_year_id, "FY26")
        self.assertEqual(result.journal_source.kind, "independent")
        self.assertEqual(result.journal_source.project_id, "project-A")
        self.assertEqual(result.registry_revision, state.revision)
        self.assertEqual(result.journal_revision, journal().revision)

    def test_gl_gate_rejects_reader_and_unassigned_project(self):
        state = scoped()
        state = apply(state, cmd("GRANT",
                                 FinanceGrant("co-A", "reader-A", "finance_reader")))
        self.reject(lambda: gate(state, actor_id="reader-A",
                                 authority=authority(actor="reader-A")), PermissionError)
        self.reject(lambda: gate(state, project_id="project-B",
                                 scopes=scopes(project="project-B")))

    def test_gl_gate_rejects_unknown_company_fiscal_year_or_period(self):
        state = scoped()
        self.reject(lambda: gate(state, company_id="co-Z"))
        self.reject(lambda: gate(state, fiscal_year_id="UNKNOWN"))
        self.reject(lambda: gate(state, fiscal_period_id="UNKNOWN"))
        self.reject(lambda: gate(state, posting_date="2027-04-01"))
        self.reject(lambda: gate(state, posting_date="2026-11-01",
                                 fiscal_period_id="P1"))

    def test_gl_gate_rejects_cross_company_chart_or_journal(self):
        state = scoped()
        self.reject(lambda: gate(state, chart=chart(company_id="co-B")))
        self.reject(lambda: gate(state, journal_state=journal("co-B")))
        self.reject(lambda: gate(state, scopes=scopes(company_id="co-B")))

    def test_gl_gate_rejects_missing_party_chart_or_verified_document_source(self):
        state = scoped()
        self.reject(lambda: gate(state, party_id="unknown"))
        self.reject(lambda: gate(state, chart=chart(project_ids=())))
        self.reject(lambda: gate(state, scopes=VerifiedScopes(
            party_ids=frozenset({"customer-A"}),
            project_ids=frozenset({"project-A"}))))
        self.reject(lambda: gate(state, scopes=VerifiedScopes(
            party_ids=frozenset({"customer-A"}),
            independent_source_scopes=scopes().independent_source_scopes)))
        self.reject(lambda: gate(assigned()))

    def test_gl_gate_rejects_extra_foreign_project_or_party_in_chart_scope(self):
        state = scoped()
        self.reject(lambda: gate(state, chart=chart(
            project_ids=("project-A", "project-B"))))
        self.reject(lambda: gate(state, scopes=VerifiedScopes(
            party_ids=frozenset({"customer-A"}),
            project_ids=frozenset({"project-A", "project-B"}),
            independent_source_scopes=scopes().independent_source_scopes)))
        self.reject(lambda: gate(state, scopes=VerifiedScopes(
            party_ids=frozenset({"customer-A", "foreign-party"}),
            project_ids=frozenset({"project-A"}),
            independent_source_scopes=scopes().independent_source_scopes)))
        self.reject(lambda: gate(state, scopes=VerifiedScopes(
            party_ids=frozenset({"customer-A"}),
            project_ids=frozenset({"project-A"}),
            independent_source_scopes=frozenset({
                ("project-A", stable_financial_source_id(
                    "co-A", "project-A", "sale", "doc-A")),
                ("project-B", "hidden-doc"),
            }))))

    def test_gl_gate_closed_period_fails_closed(self):
        state = scoped()
        jrn = journal()
        closed = close_fiscal_period(
            jrn, company_id="co-A", fiscal_period_id="P1",
            event_id="close-FY1", actor_id="admin-A",
            closing_date="2026-07-01",
            expected_revision=jrn.revision, today="2026-10-22",
        )
        self.reject(lambda: gate(state, journal_state=closed))

    def test_gl_gate_rejects_ambiguous_project_proof(self):
        state = scoped()
        self.reject(lambda: gate(state, authority=authority(pairs={
            ("project-A", "co-A"), ("project-A", "co-B")})))
        self.reject(lambda: gate(state, authority=authority(pairs={
            ("project-A", "co-B")})))

    def test_gl_gate_rejects_reused_sales_source_under_new_journal_event(self):
        state = scoped()
        jrn = journal()
        source = stable_financial_source_id("co-A", "project-A", "sale", "doc-A")
        jrn = post_journal(
            jrn, company_id="co-A", fiscal_period_id="P1", event_id="other-event",
            actor_id="admin-A", posting_date="2026-04-01",
            source=JournalSource("independent", source, "project-A"),
            lines=(
                JournalLine(PostingReference("co-A", "100101", project_id="project-A"),
                            debit_rial=100),
                JournalLine(PostingReference("co-A", "400101", project_id="project-A"),
                            credit_rial=100),
            ), chart=chart(), scopes=scopes(), money_policy=CompanyMoneyPolicy("co-A"),
            expected_revision=jrn.revision, today="2026-10-22",
        )
        self.reject(lambda: gate(state, journal_state=jrn), RegistryConflict)

    def test_gl_gate_rejects_source_that_registry_marks_posted(self):
        state = scoped()
        source = stable_financial_source_id("co-A", "project-A", "sale", "doc-A")
        lock = PostedLock("co-A", "project-A", "FY26", source)
        state = apply(state, cmd("POSTED_LOCK", lock), host=authority(
            verified_postings={("co-A", "project-A", "FY26", source)}))
        self.reject(lambda: gate(state), RegistryConflict)

    def test_purchase_source_is_distinct_from_sale_without_implicit_currency(self):
        sale = stable_financial_source_id("co-A", "project-A", "sale", "doc-A")
        purchase = stable_financial_source_id("co-A", "project-A", "purchase", "doc-A")
        self.assertNotEqual(sale, purchase)
        self.assertEqual(sale, stable_financial_source_id(
            "co-A", "project-A", "sale", "doc-A"))
        self.assertLessEqual(len(sale), 96)
        self.reject(lambda: stable_financial_source_id(
            "co-A", "project-A", "invoice", "doc-A"))

    def test_purchase_gl_gate_valid_with_explicit_source(self):
        state = scoped()
        result = gate(state, kind="purchase", scopes=scopes(kind="purchase"))
        self.assertEqual(result.action, "purchase")


if __name__ == "__main__":
    unittest.main()
