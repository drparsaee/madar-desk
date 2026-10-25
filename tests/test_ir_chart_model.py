"""Synthetic-only domain checks for an additive Iranian chart model."""

from dataclasses import FrozenInstanceError, replace
import unittest

from ir_chart_model import (
    ChartAccount, ChartSnapshot, CostCenter, DetailBinding, FloatingDetail,
    JobReference, LegacyAccountLink, PartyDetailLink, PostingReference,
    add_account, lock_posted_account, resolve_legacy_account, reverse_legacy_account,
    revise_account, validate_chart, validate_chart_transition,
    validate_external_references,
    validate_posting_reference,
)


COMPANY = "company-A"
OTHER = "company-B"


def kol(code="10", kind="asset", **changes):
    return ChartAccount(COMPANY, code, "KOL", None, "حساب کل", kind, **changes)


def moein(code="1001", kind="asset", **changes):
    return ChartAccount(COMPANY, code, "MOEIN", code[:2], "حساب معین", kind, **changes)


def tafsili(code="100101", kind="asset", **changes):
    return ChartAccount(COMPANY, code, "TAFSILI", code[:4], "حساب تفصیلی",
                        kind, accountable=True, **changes)


def full_chart():
    return ChartSnapshot(
        company_id=COMPANY,
        accounts=(
            tafsili("100102", requires_detail=True, requires_cost_center=True,
                    requires_job=True),
            kol(),
            moein(),
            tafsili(),
        ),
        details=(
            FloatingDetail(COMPANY, "FD-000001", "مشتری نمونه", "PARTY"),
            FloatingDetail(COMPANY, "FD-000002", "تفصیلی عمومی"),
        ),
        bindings=(
            DetailBinding(COMPANY, "100102", "FD-000001"),
            DetailBinding(COMPANY, "100102", "FD-000002"),
        ),
        party_links=(PartyDetailLink(COMPANY, "client-1", "FD-000001"),),
        project_ids=("project-2", "project-1"),
        cost_centers=(CostCenter(COMPANY, "CC-0001", "project-1", "مرکز پروژه ۱"),),
        jobs=(JobReference(COMPANY, "job-1", "project-1", "task-1", "CC-0001"),),
        legacy_links=(LegacyAccountLink(COMPANY, "1000", "100101", "asset"),),
    )


def valid_posting(account_code="100102", **changes):
    defaults = dict(company_id=COMPANY, account_code=account_code,
                    detail_code="FD-000001", party_id="client-1",
                    project_id="project-1", cost_center_code="CC-0001",
                    job_id="job-1", task_id="task-1")
    defaults.update(changes)
    return PostingReference(**defaults)


def check(chart, reference, *, parties=frozenset({"client-1"}),
          projects=frozenset({"project-1", "project-2"}),
          tasks=frozenset({("project-1", "task-1")})):
    return validate_posting_reference(
        chart, reference, verified_party_ids=parties,
        verified_project_ids=projects, verified_task_scopes=tasks)


class ChartModelTests(unittest.TestCase):
    def assert_invalid(self, work, fragment=None):
        with self.assertRaises(ValueError) as caught:
            work()
        if fragment:
            self.assertIn(fragment, str(caught.exception))

    def test_deterministic_order_canonicalization_and_immutability(self):
        a = full_chart()
        b = replace(a, accounts=tuple(reversed(a.accounts)),
                    project_ids=tuple(reversed(a.project_ids)),
                    bindings=tuple(reversed(a.bindings)))
        self.assertEqual(a, b)
        self.assertTrue(validate_chart(a))
        self.assertEqual(tuple(item.code for item in a.accounts),
                         ("10", "1001", "100101", "100102"))
        with self.assertRaises(FrozenInstanceError):
            a.company_id = "forged"
        with self.assertRaises(FrozenInstanceError):
            a.accounts[0].name = "forged"
        self.assert_invalid(lambda: ChartSnapshot(COMPANY, accounts=[kol()]),
                            "immutable tuple")
        self.assert_invalid(lambda: ChartSnapshot(COMPANY, project_ids=["project-1"]),
                            "immutable tuple")

    def test_strict_code_lengths_ascii_only_and_zero_segments(self):
        for code in ["1", "000", "1a", "۱۰", "01 ", "00", "1000", "100101"]:
            self.assert_invalid(lambda c=code: kol(c))
        for code in ["100", "10000", "1000", "۱۰۱۰", "0001", "100001"]:
            self.assert_invalid(lambda c=code: moein(c))
        for code in ["1001011", "100100", "١٠٠١٠١", "1001a1"]:
            self.assert_invalid(lambda c=code: tafsili(c))
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(tafsili("000101"),)), "parent")
        self.assert_invalid(lambda: ChartAccount(COMPANY, "100101", "WRONG",
                                                "1001", "نام", "asset"))
        self.assert_invalid(lambda: ChartAccount(COMPANY, "100101", "TAFSILI",
                                                "1101", "نام", "asset", accountable=True))

    def test_parent_missing_wrong_level_and_kind_mismatch(self):
        self.assert_invalid(lambda: ChartSnapshot(COMPANY, accounts=(tafsili(),)))
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(kol(), moein("1001"), tafsili("100201"))))
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(kol(), moein("1001", "liability"))),
            "kind")
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(kol(active=False), moein("1001"))),
            "active under inactive")

    def test_group_and_leaf_posting_invariants(self):
        self.assert_invalid(lambda: kol(accountable=True), "KOL")
        self.assert_invalid(lambda: ChartAccount(COMPANY, "100101", "TAFSILI",
                                                "1001", "تفصیلی", "asset",
                                                accountable=False), "accountable")
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(kol(), moein(accountable=True), tafsili())),
            "group")
        empty = ChartSnapshot(COMPANY, accounts=(kol(), moein(accountable=True)))
        self.assertEqual(check(empty, PostingReference(COMPANY, "1001")), check(
            empty, PostingReference(COMPANY, "1001")))
        self.assert_invalid(lambda: check(full_chart(), PostingReference(COMPANY, "10")),
                            "group")
        self.assert_invalid(lambda: check(full_chart(), PostingReference(COMPANY, "1001")),
                            "group")

    def test_account_closed_archived_frozen_and_posted_semantics(self):
        self.assert_invalid(lambda: tafsili(active=True, archived=True), "Archived")
        self.assert_invalid(lambda: tafsili(active=False, has_postings=True), "postings")
        self.assert_invalid(lambda: kol(requires_detail=True), "accountable")
        chart = full_chart()
        locked = lock_posted_account(chart, "100101")
        self.assertFalse(next(a.has_postings for a in chart.accounts if a.code == "100101"))
        self.assertTrue(next(a.has_postings for a in locked.accounts if a.code == "100101"))
        self.assert_invalid(lambda: validate_chart_transition(chart, locked),
                            "needs host verification")
        self.assertTrue(validate_chart_transition(
            chart, locked, verified_new_posting_codes=frozenset({"100101"})))
        self.assertIs(lock_posted_account(locked, "100101"), locked)
        self.assert_invalid(lambda: revise_account(
            locked, replace(next(a for a in locked.accounts if a.code == "100101"),
                            name="نام جدید")), "cannot be modified")
        self.assert_invalid(lambda: lock_posted_account(chart, "10"), "accountable")
        # Posted does not mean frozen: another valid posting remains possible.
        self.assertEqual(check(locked, PostingReference(COMPANY, "100101")).account_code,
                         "100101")
        account = next(a for a in chart.accounts if a.code == "100101")
        frozen = revise_account(chart, replace(account, frozen=True))
        self.assert_invalid(lambda: revise_account(
            frozen, replace(account, name="ویرایش")), "cannot be modified")
        self.assert_invalid(lambda: check(frozen, PostingReference(COMPANY, "100101")),
                            "unavailable")
        # A legacy mapping is itself a live reference and must be removed only
        # through a separately approved migration. Use an unmapped account here.
        no_mapping = replace(chart, legacy_links=())
        archived = revise_account(no_mapping, replace(account, active=False, archived=True))
        self.assert_invalid(lambda: revise_account(archived, account), "cannot be modified")
        self.assert_invalid(lambda: check(archived, PostingReference(COMPANY, "100101")),
                            "unavailable")

    def test_account_transition_prevents_delete_reparent_and_legacy_rewrite(self):
        chart = full_chart()
        added = add_account(chart, tafsili("100103"))
        self.assert_invalid(lambda: validate_chart_transition(
            added, replace(added, accounts=tuple(a for a in added.accounts
                                                 if a.code != "100103"))), "deletion")
        # Updates cannot change immutable code identity by omitting the old row.
        self.assert_invalid(lambda: revise_account(
            chart, tafsili("100103")), "Unknown account")
        self.assert_invalid(lambda: validate_chart_transition(
            chart, replace(chart, legacy_links=(LegacyAccountLink(
                COMPANY, "1000", "100102", "asset"),))), "mapping")

    def test_transition_preserves_historical_party_project_and_job_references(self):
        original = full_chart()
        self.assert_invalid(lambda: validate_chart_transition(
            original, replace(original, party_links=(
                PartyDetailLink(COMPANY, "other-party", "FD-000001"),))),
            "floating detail link")
        self.assert_invalid(lambda: validate_chart_transition(
            original, replace(original, project_ids=("project-1",))),
            "Removing project")
        self.assert_invalid(lambda: validate_chart_transition(
            original, replace(original, cost_centers=(
                replace(original.cost_centers[0], project_id="project-2"),),
                jobs=(replace(original.jobs[0], project_id="project-2"),))),
            "project reassignment")
        self.assert_invalid(lambda: validate_chart_transition(
            original, replace(original, jobs=(
                replace(original.jobs[0], task_id="task-2"),))),
            "reference reassignment")
        self.assert_invalid(lambda: validate_chart_transition(
            original, replace(original, details=(
                original.details[1],))), "PARTY")
        inactive = replace(original, cost_centers=(
            replace(original.cost_centers[0], active=False),))
        self.assertTrue(validate_chart_transition(original, inactive))
        self.assertEqual(original.cost_centers[0].active, True)

    def test_add_account_rejects_collisions_and_does_not_mutate_original(self):
        original = ChartSnapshot(COMPANY, accounts=(kol(),))
        later = add_account(original, moein(accountable=True))
        self.assertEqual(len(original.accounts), 1)
        self.assertEqual(len(later.accounts), 2)
        self.assert_invalid(lambda: add_account(later, moein(accountable=True)),
                            "duplicate")
        self.assert_invalid(lambda: add_account(original, replace(
            moein(accountable=True), company_id=OTHER)), "Cross-company")

    def test_floating_detail_and_party_mapping_are_distinct_from_party_records(self):
        chart = full_chart()
        self.assertEqual(len(chart.party_links), 1)
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(kol(), moein(), tafsili()),
            details=(FloatingDetail(COMPANY, "FD-000001", "مشتری", "PARTY"),)),
            "party link")
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, details=(FloatingDetail(COMPANY, "FD-000001", "سایر"),),
            party_links=(PartyDetailLink(COMPANY, "client-1", "FD-000001"),)),
            "PARTY")
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(kol(), moein(), tafsili()),
            details=(FloatingDetail(COMPANY, "FD-000001", "مشتری", "PARTY"),),
            party_links=(PartyDetailLink(COMPANY, "client-1", "FD-000001"),
                         PartyDetailLink(COMPANY, "client-2", "FD-000001"))),
            "duplicate")
        self.assert_invalid(lambda: FloatingDetail(COMPANY, "FD-۱۲۳۴۵۶", "نام"))
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(kol(), moein(), tafsili()),
            bindings=(DetailBinding(COMPANY, "100101", "FD-000009"),)),
            "unknown detail")

    def test_dimension_preflight_rejects_missing_required_fields(self):
        chart = full_chart()
        self.assertEqual(check(chart, valid_posting()), valid_posting())
        for key in ("detail_code", "cost_center_code", "job_id"):
            self.assert_invalid(lambda k=key: check(chart, valid_posting(**{k: ""})))
        self.assert_invalid(lambda: check(chart, valid_posting(project_id="")),
                            "project")
        self.assert_invalid(lambda: check(chart, valid_posting(party_id="")),
                            "PARTY")
        self.assert_invalid(lambda: check(chart, valid_posting(
            detail_code="FD-000002", party_id="client-1")), "Party")

    def test_identity_attestation_is_mandatory_for_party_project_and_task(self):
        chart = full_chart()
        self.assert_invalid(lambda: validate_posting_reference(
            chart, valid_posting()), "Party")
        self.assert_invalid(lambda: check(chart, valid_posting(),
                                          parties=frozenset()), "Party")
        self.assert_invalid(lambda: check(chart, valid_posting(),
                                          projects=frozenset()), "Project")
        self.assert_invalid(lambda: check(chart, valid_posting(),
                                          tasks=frozenset()), "Task")
        self.assert_invalid(lambda: check(chart, valid_posting(),
                                          tasks=frozenset({("project-2", "task-1")})),
                            "Task")
        self.assert_invalid(lambda: validate_posting_reference(
            chart, valid_posting(), verified_party_ids={"client-1"},
            verified_project_ids=frozenset({"project-1"}),
            verified_task_scopes=frozenset({("project-1", "task-1")})),
            "frozen set")

    def test_full_snapshot_external_reference_validation_precedes_persistence(self):
        chart = full_chart()
        sources = dict(
            verified_party_ids=frozenset({"client-1"}),
            verified_project_ids=frozenset({"project-1", "project-2"}),
            verified_task_scopes=frozenset({("project-1", "task-1")}),
        )
        self.assertTrue(validate_external_references(chart, **sources))
        self.assert_invalid(lambda: validate_external_references(
            chart, **{**sources, "verified_party_ids": frozenset()}),
            "Party")
        self.assert_invalid(lambda: validate_external_references(
            chart, **{**sources, "verified_project_ids": frozenset({"project-1"})}),
            "Project")
        self.assert_invalid(lambda: validate_external_references(
            chart, **{**sources, "verified_task_scopes": frozenset({
                ("project-2", "task-1")})}),
            "Job")
        self.assert_invalid(lambda: validate_external_references(
            chart, **{**sources, "verified_task_scopes": {"project-1", "task-1"}}),
            "frozen set")

    def test_company_scope_and_cross_project_references(self):
        chart = full_chart()
        self.assert_invalid(lambda: check(chart, valid_posting(company_id=OTHER)),
                            "Cross-company")
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(replace(kol(), company_id=OTHER),)),
            "cross-company")
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, project_ids=("project-1",),
            cost_centers=(CostCenter(COMPANY, "CC-0001", "project-2", "نام"),)),
            "project")
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, project_ids=("project-1", "project-2"),
            cost_centers=(CostCenter(COMPANY, "CC-0001", "project-1", "نام"),),
            jobs=(JobReference(COMPANY, "job-x", "project-2", cost_center_code="CC-0001"),)),
            "same project")
        self.assert_invalid(lambda: check(chart, valid_posting(project_id="project-2")),
                            "cross-project")
        self.assert_invalid(lambda: check(chart, valid_posting(
            cost_center_code="CC-9999")), "cost center")
        self.assert_invalid(lambda: check(chart, valid_posting(job_id="job-99")),
                            "job")
        self.assert_invalid(lambda: check(chart, valid_posting(task_id="task-99")),
                            "task")

    def test_disabled_dimension_cannot_be_used_for_posting(self):
        chart = full_chart()
        disabled_center = replace(chart, cost_centers=(
            replace(chart.cost_centers[0], active=False),))
        self.assert_invalid(lambda: check(disabled_center, valid_posting()),
                            "cost center")
        disabled_job = replace(chart, jobs=(replace(chart.jobs[0], active=False),))
        self.assert_invalid(lambda: check(disabled_job, valid_posting()), "job")
        disabled_detail = replace(chart, details=(
            replace(chart.details[0], active=False), chart.details[1]))
        self.assert_invalid(lambda: check(disabled_detail, valid_posting()), "Detail")

    def test_legacy_mapping_has_explicit_company_kind_and_leaf_guard(self):
        chart = full_chart()
        self.assertEqual(resolve_legacy_account(chart, COMPANY, "1000"), "100101")
        self.assertEqual(reverse_legacy_account(chart, COMPANY, "100101"), "1000")
        self.assert_invalid(lambda: reverse_legacy_account(chart, COMPANY, "100102"),
                            "no verified legacy mapping")
        self.assert_invalid(lambda: reverse_legacy_account(chart, OTHER, "100101"),
                            "Cross-company")
        self.assert_invalid(lambda: resolve_legacy_account(chart, OTHER, "1000"),
                            "Cross-company")
        self.assert_invalid(lambda: resolve_legacy_account(chart, COMPANY, "9999"),
                            "Unmapped")
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(kol(), moein(), tafsili()),
            legacy_links=(LegacyAccountLink(COMPANY, "1000", "10", "asset"),)),
            "accountable")
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(kol(), moein(), tafsili()),
            legacy_links=(LegacyAccountLink(COMPANY, "1000", "100101", "liability"),)),
            "Legacy kind")
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(kol(), moein(), tafsili()),
            legacy_links=(LegacyAccountLink(COMPANY, "1000", "100101", "asset"),
                          LegacyAccountLink(COMPANY, "1010", "100101", "asset"))),
            "duplicate")

    def test_duplicate_and_wrong_type_values_fail_closed(self):
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, accounts=(kol(), kol())), "duplicate")
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, project_ids=("project-1", "project-1")), "duplicate")
        self.assert_invalid(lambda: ChartSnapshot(
            COMPANY, cost_centers=(CostCenter(OTHER, "CC-0001", "p", "نام"),)),
            "cross-company")
        self.assert_invalid(lambda: ChartAccount(
            COMPANY, "100101", "TAFSILI", "1001", "نام", "asset",
            accountable=1), "boolean")
        self.assert_invalid(lambda: ChartAccount(
            COMPANY, "10", "KOL", None, "نام", [], accountable=False),
            "kind")
        self.assert_invalid(lambda: LegacyAccountLink(COMPANY, "1000", "100101", []),
                            "kind")
        self.assert_invalid(lambda: FloatingDetail(COMPANY, "FD-000001", "X\u202eY"))
        self.assert_invalid(lambda: PostingReference(COMPANY, "100101", detail_code=True),
                            "detail")
        self.assert_invalid(lambda: PostingReference(COMPANY, "100101", project_id=True),
                            "project")
        self.assert_invalid(lambda: JobReference(
            COMPANY, "job", "project-1", cost_center_code=True),
            "cost center")
        self.assert_invalid(lambda: JobReference(
            COMPANY, "job", "project-1", task_id=0), "task_id")
        self.assert_invalid(lambda: DetailBinding(COMPANY, 100101, "FD-000001"),
                            "account code")
        self.assert_invalid(lambda: PartyDetailLink(COMPANY, "client-1", None),
                            "detail")
        self.assert_invalid(lambda: add_account(
            ChartSnapshot(COMPANY, accounts=(kol(), moein())),
            tafsili(has_postings=True)), "cannot claim")
        chart = full_chart()
        old = next(a for a in chart.accounts if a.code == "100101")
        self.assert_invalid(lambda: revise_account(
            chart, replace(old, has_postings=True)), "Only lock_posted")


if __name__ == "__main__":
    unittest.main()
