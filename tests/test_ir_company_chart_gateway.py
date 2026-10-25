"""Independent synthetic-only authorization preflight tests. No persistent IO."""
from dataclasses import replace
import unittest

from ir_chart_model import (
    ChartAccount, ChartSnapshot, FloatingDetail, DetailBinding,
    PartyDetailLink, PostingReference, CostCenter, JobReference,
)
from ir_company_chart_gateway import (
    CompanyChartGatewayError, preflight_company_chart_source,
)
from ir_company_registry import (
    CompanyRegistry, CompanyPartyRef, FiscalYear, FinanceGrant, LegalEntity,
    ProjectAssignment, RegisteredCompany, RegistryCommand,
    VerifiedRegistryAuthority, apply_registry_command, stable_financial_source_id,
)
from ir_journal_v2 import (
    FiscalPeriod, VerifiedScopes, new_journal_state, close_fiscal_period,
    JournalLine, JournalSource, post_journal,
)
from ir_inventory_rial import (
    BusinessSource, ItemSpec, StockAuthority, StockEvent,
    append_stock_event, new_inventory_state,
)
from money_policy import CompanyMoneyPolicy


CO, P, PARTY, ACTOR = "co-A", "project-A", "customer-A", "admin-A"
DOC = "doc-1"
DAY = "2026-04-08"
TODAY = "2026-10-22"


def host(*, actor=ACTOR, pairs=None, parties=None, authenticated=True):
    return VerifiedRegistryAuthority(
        actor, authenticated, registration_right=True,
        project_company_pairs=frozenset(pairs if pairs is not None else {(P, CO)}),
        parties=frozenset(parties if parties is not None else {(CO, PARTY)}),
    )


def registry(*, add_party=True, role=None):
    result = CompanyRegistry()
    commands = [
        RegistryCommand("REGISTER", CO, ACTOR, "create-co",
                        RegisteredCompany(CO, LegalEntity("Company A"), (
                            FiscalYear(CO, "FY26", "2026-01-01", "2026-12-31"),))),
        RegistryCommand("PROJECT_ASSIGN", CO, ACTOR, "assign-project",
                        ProjectAssignment(CO, P)),
    ]
    if add_party:
        commands.append(RegistryCommand(
            "PARTY_ADD", CO, ACTOR, "party-added", CompanyPartyRef(CO, PARTY)))
    if role is not None:
        commands.append(RegistryCommand(
            "GRANT", CO, ACTOR, "add-role", FinanceGrant(CO, "reader-A", role)))
    for command in commands:
        result = apply_registry_command(
            result, command, authority=host(),
            expected_revision=result.revision)
    return result


def chart(*, company=CO, frozen=False, archived=False, projects=(P,)):
    accounts = (
        ChartAccount(company, "10", "KOL", None, "Asset", "asset"),
        ChartAccount(company, "1001", "MOEIN", "10", "Receivable", "asset"),
        ChartAccount(company, "100101", "TAFSILI", "1001", "AR", "asset",
                     accountable=True, frozen=frozen, archived=archived,
                     active=not archived, requires_detail=True),
        ChartAccount(company, "40", "KOL", None, "Sales", "revenue"),
        ChartAccount(company, "4001", "MOEIN", "40", "Revenue", "revenue"),
        ChartAccount(company, "400101", "TAFSILI", "4001", "Revenue", "revenue",
                     accountable=True),
    )
    return ChartSnapshot(
        company, accounts=accounts,
        details=(FloatingDetail(company, "FD-000001", "Customer", "PARTY"),),
        party_links=(PartyDetailLink(company, PARTY, "FD-000001"),),
        bindings=(() if archived else (
            DetailBinding(company, "100101", "FD-000001"),)),
        project_ids=projects)


def journal(*, company=CO):
    return new_journal_state(company, (
        FiscalPeriod(company, "period-1", "2026-01-01", "2026-06-30"),
        FiscalPeriod(company, "period-2", "2026-07-01", "2026-12-31"),
    ))


def refs(*, company=CO, project=P, party=PARTY, asset_code="100101"):
    return (
        PostingReference(company, asset_code, detail_code="FD-000001",
                         party_id=party, project_id=project),
        PostingReference(company, "400101", project_id=project),
    )


def scopes(*, project=P, party=PARTY, source=None):
    sid = source or stable_financial_source_id(CO, P, "sale", DOC)
    return VerifiedScopes(
        project_ids=frozenset({project}),
        party_ids=frozenset({party}),
        independent_source_scopes=frozenset({(project, sid)}),
    )


def stock(*, source="inventory-biz", company=CO, project=P,
          kind="RECEIPT", cost=120, job="", center="", actor=ACTOR):
    state = new_inventory_state(
        company, (ItemSpec(company, "paper", "sheet", 1),), ("warehouse-1",))
    event = StockEvent("stock-event-1", company, actor, kind,
                       BusinessSource(kind.lower(), source),
                       "warehouse-1", "paper", "sheet", 1, 3,
                       cost_rial=cost, project_id=project,
                       job_id=job, cost_center_id=center)
    proof = StockAuthority(
        company, frozenset({actor}), frozenset({"warehouse-1"}),
        frozenset({"paper"}), frozenset({(kind.lower(), source)}),
        project_ids=frozenset({project}),
        work_scopes=frozenset({(project, job, center)}) if job or center
        else frozenset())
    return append_stock_event(state, event, proof, expected_revision=state.revision)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.registry = registry()
        self.chart = chart()
        self.journal = journal()
        self.authority = host()
        self.scopes = scopes()

    def gateway(self, **changes):
        args = dict(
            authority=self.authority, company_id=CO, actor_id=ACTOR,
            project_id=P, fiscal_year_id="FY26", fiscal_period_id="period-1",
            posting_date=DAY, today=TODAY,
            chart=self.chart, scopes=self.scopes, journal_state=self.journal,
            source_kind="sale", document_id=DOC, party_id=PARTY,
            references=refs(),
        )
        args.update(changes)
        return preflight_company_chart_source(self.registry, **args)

    def reject(self, **changes):
        with self.assertRaises((ValueError, PermissionError, TypeError)):
            self.gateway(**changes)

    def test_sale_delegates_registered_source_and_preserves_revisions(self):
        checked = self.gateway()
        self.assertEqual(checked.source_kind, "sale")
        self.assertEqual(checked.journal_source.kind, "independent")
        self.assertEqual(checked.journal_source.source_id,
                         stable_financial_source_id(CO, P, "sale", DOC))
        self.assertEqual(checked.journal_source.project_id, P)
        self.assertEqual(checked.registry_revision, self.registry.revision)
        self.assertEqual(checked.journal_revision, self.journal.revision)
        self.assertEqual(self.journal.events, ())
        self.assertEqual(self.registry.events[-1].command.action, "PARTY_ADD")

    def test_purchase_uses_purchase_stable_identity(self):
        purchase_scopes = scopes(source=stable_financial_source_id(
            CO, P, "purchase", DOC))
        result = self.gateway(source_kind="purchase", scopes=purchase_scopes)
        self.assertEqual(result.source_kind, "purchase")
        self.assertNotEqual(result.journal_source.source_id,
                            self.gateway().journal_source.source_id)

    def test_missing_wrong_and_ambiguous_company_project_denied(self):
        self.reject(company_id="co-B")
        self.reject(project_id="not-assigned")
        self.reject(chart=chart(company="co-B"))
        self.reject(journal_state=journal(company="co-B"))
        self.reject(authority=host(pairs={(P, "co-B")}))
        self.reject(authority=host(pairs={(P, CO), (P, "co-B")}))
        self.reject(chart=chart(projects=(P, "unassigned-project")))
        self.reject(scopes=scopes(project="unassigned-project"))
        with self.assertRaises(ValueError):
            preflight_company_chart_source(
                CompanyRegistry(), authority=self.authority,
                company_id=CO, actor_id=ACTOR, project_id=P,
                fiscal_year_id="FY26", fiscal_period_id="period-1",
                posting_date=DAY, today=TODAY, chart=self.chart,
                scopes=self.scopes, journal_state=self.journal,
                source_kind="sale", document_id=DOC, party_id=PARTY,
                references=refs())

    def test_authenticated_host_actor_and_role_required(self):
        self.reject(authority=host(authenticated=False))
        self.reject(authority=host(actor="other"))
        self.reject(actor_id="other")
        self.reject(authority=None)
        self.reject(authority={"authenticated": True, "actor_id": ACTOR})
        restricted = registry(role="finance_reader")
        with self.assertRaises(PermissionError):
            preflight_company_chart_source(
                restricted, authority=host(actor="reader-A"),
                company_id=CO, actor_id="reader-A", project_id=P,
                fiscal_year_id="FY26", fiscal_period_id="period-1",
                posting_date=DAY, today=TODAY, chart=self.chart,
                scopes=self.scopes, journal_state=self.journal,
                source_kind="sale", document_id=DOC, party_id=PARTY,
                references=refs())

    def test_party_must_be_registered_and_host_verified(self):
        self.reject(authority=host(parties=set()))
        self.reject(party_id="another-party")
        self.reject(scopes=scopes(party="another-party"))
        self.reject(references=refs(party="another-party"))
        self.reject(references=(PostingReference(
            CO, "100101", detail_code="FD-000001", project_id=P),
            refs()[1]))
        self.reject(references=(refs()[1], refs()[1]))
        with self.assertRaises(ValueError):
            preflight_company_chart_source(
                registry(add_party=False), authority=self.authority,
                company_id=CO, actor_id=ACTOR, project_id=P,
                fiscal_year_id="FY26", fiscal_period_id="period-1",
                posting_date=DAY, today=TODAY, chart=self.chart,
                scopes=self.scopes, journal_state=self.journal,
                source_kind="sale", document_id=DOC, party_id=PARTY,
                references=refs())

    def test_wrong_or_closed_year_period_future_or_invalid_date_denied(self):
        self.reject(fiscal_year_id="FY25")
        self.reject(fiscal_period_id="period-2")
        self.reject(posting_date="2026-02-30")
        self.reject(posting_date="۱۴۰۵-۰۱-۰۱")
        self.reject(posting_date="2027-01-01")
        self.reject(today="2026-01-01")
        self.reject(today="invalid")
        closed = close_fiscal_period(
            self.journal, company_id=CO, fiscal_period_id="period-1",
            event_id="close-1", actor_id=ACTOR,
            closing_date="2026-06-30", expected_revision=self.journal.revision,
            today=TODAY)
        self.reject(journal_state=closed)

    def test_schema_scope_leaf_frozen_and_archived_rejected(self):
        self.reject(chart=chart(frozen=True))
        self.reject(chart=chart(archived=True))
        self.reject(references=(PostingReference(CO, "10", project_id=P), refs()[1]))
        self.reject(references=[*refs()])
        self.reject(references=(refs()[0],))
        self.reject(references=({ "account_code": "100101" }, refs()[1]))
        self.reject(scopes=VerifiedScopes(
            party_ids=frozenset({PARTY}), project_ids=frozenset({P}),
            independent_source_scopes=frozenset()))
        self.reject(scopes=VerifiedScopes(project_ids=frozenset({P}),
                                         party_ids=frozenset({PARTY})))
        self.reject(source_kind="journal")
        self.reject(source_kind="inventory", document_id=DOC)

    def test_duplicate_source_under_different_event_id_denied(self):
        source = self.gateway().journal_source
        posted = post_journal(
            self.journal, company_id=CO, fiscal_period_id="period-1",
            event_id="event-A", actor_id=ACTOR, posting_date=DAY,
            source=source, lines=(
                JournalLine(refs()[0], debit_rial=100),
                JournalLine(refs()[1], credit_rial=100),
            ), chart=self.chart, scopes=self.scopes,
            money_policy=CompanyMoneyPolicy(CO),
            expected_revision=self.journal.revision, today=TODAY)
        self.reject(journal_state=posted)
        self.assertEqual(len(posted.events), 1)

    def test_inventory_event_uses_only_replayed_recorded_business_source(self):
        inv = stock()
        selected = scopes(source="inventory-biz")
        result = self.gateway(
            source_kind="inventory", inventory_state=inv,
            inventory_event_id="stock-event-1", document_id="", party_id="",
            scopes=selected)
        self.assertEqual(result.journal_source.source_id, "inventory-biz")
        self.assertEqual(result.inventory_revision, inv.revision)
        self.assertEqual(result.source_kind, "inventory")
        self.assertEqual(inv.events[0].event.source.source_id, "inventory-biz")
        self.reject(source_kind="inventory", inventory_state=inv,
                    inventory_event_id="unknown", document_id="", party_id="",
                    scopes=selected)
        self.reject(source_kind="inventory", inventory_state=inv,
                    inventory_event_id="stock-event-1", document_id="client-doc",
                    party_id="", scopes=selected)
        self.reject(source_kind="inventory", inventory_state=inv,
                    inventory_event_id="stock-event-1", document_id="", party_id="",
                    scopes=self.scopes)

    def test_inventory_cross_company_and_cross_project_denied(self):
        foreign = stock(company="co-B")
        self.reject(source_kind="inventory", inventory_state=foreign,
                    inventory_event_id="stock-event-1", document_id="", party_id="",
                    scopes=scopes(source="inventory-biz"))

    def test_inventory_work_dimensions_must_match_recorded_movement(self):
        stock_state = stock(job="job-1", center="CC-0001")
        scoped = scopes(source="inventory-biz")
        scoped = replace(scoped, task_scopes=frozenset({(P, "task-1")}))
        valid_chart = replace(
            self.chart,
            cost_centers=(CostCenter(CO, "CC-0001", P, "Project cost"),),
            jobs=(JobReference(CO, "job-1", P, "task-1", "CC-0001"),))
        good_refs = (
            replace(refs()[0], job_id="job-1", cost_center_code="CC-0001",
                    task_id="task-1"),
            replace(refs()[1], job_id="job-1", cost_center_code="CC-0001",
                    task_id="task-1"),
        )
        good = dict(source_kind="inventory", document_id="", party_id="",
                    inventory_state=stock_state, inventory_event_id="stock-event-1",
                    scopes=scoped, chart=valid_chart)
        self.assertEqual(self.gateway(references=good_refs, **good).source_kind,
                         "inventory")
        self.reject(references=refs(), **good)
        self.reject(references=(replace(good_refs[0], job_id=""), good_refs[1]),
                    **good)
        self.reject(references=(replace(good_refs[0], cost_center_code=""),
                                good_refs[1]), **good)
        self.reject(scopes=replace(scoped, task_scopes=frozenset()),
                    references=good_refs, **{k: v for k, v in good.items()
                                            if k != "scopes"})

    def test_orphan_checklist_scope_is_not_accepted(self):
        rogue = replace(
            self.scopes, checklist_scopes=frozenset({(P, "missing-task", "step-1")}))
        self.reject(scopes=rogue)
        self.reject(source_kind="inventory", inventory_state=stock(project="other"),
                    inventory_event_id="stock-event-1", document_id="", party_id="",
                    scopes=scopes(source="inventory-biz"))

    def test_inventory_accounting_actor_must_match_recorded_authority(self):
        alternate = stock(actor="another-stock-actor")
        self.reject(source_kind="inventory", inventory_state=alternate,
                    inventory_event_id="stock-event-1", document_id="", party_id="",
                    scopes=scopes(source="inventory-biz"))

    def test_unpriced_or_nonposting_inventory_does_not_get_false_gl_approval(self):
        self.reject(source_kind="inventory", inventory_state=stock(cost=None),
                    inventory_event_id="stock-event-1", document_id="", party_id="",
                    scopes=scopes(source="inventory-biz"))

    def test_frozen_snapshot_result_is_not_an_authority_credential(self):
        result = self.gateway()
        with self.assertRaises(Exception):
            result.company_id = "co-B"
        self.assertEqual(result.company_id, CO)


if __name__ == "__main__":
    unittest.main()
