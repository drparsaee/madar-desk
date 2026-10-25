"""Synthetic, no-IO, immutable RIAL journal and chart integration tests."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ir_chart_model import (
    ChartAccount, ChartSnapshot, CostCenter, JobReference, PostingReference,
)
from ir_journal_v2 import (
    JournalV2Conflict, JournalV2Error, FiscalPeriod, JournalSource,
    VerifiedScopes, JournalLine, PostedJournal, ClosedPeriod,
    new_journal_state, replay_journal, post_journal, reverse_journal,
    close_fiscal_period,
)
from money_policy import MAX_RIAL, CompanyMoneyPolicy
from money_policy import snapshot_sha256
import ir_journal_v2 as kernel


def chart(company="co-A", *, inactive=False, frozen=False, group_only=False):
    rows = [
        ChartAccount(company, "10", "KOL", None, "Assets", "asset"),
        ChartAccount(company, "1001", "MOEIN", "10", "Cash", "asset"),
        ChartAccount(company, "100101", "TAFSILI", "1001", "Cash leaf",
                     "asset", accountable=True, active=not inactive,
                     archived=inactive, frozen=frozen),
        ChartAccount(company, "40", "KOL", None, "Revenue", "revenue"),
        ChartAccount(company, "4001", "MOEIN", "40", "Revenue subtotal", "revenue"),
        ChartAccount(company, "400101", "TAFSILI", "4001", "Revenue leaf",
                     "revenue", accountable=True),
    ]
    if not group_only:
        rows.append(ChartAccount(company, "100102", "TAFSILI", "1001",
                                 "Project cash", "asset", accountable=True,
                                 requires_cost_center=True))
    return ChartSnapshot(
        company_id=company,
        accounts=tuple(rows),
        project_ids=("proj-A", "proj-B"),
        cost_centers=(CostCenter(company, "CC-0001", "proj-A", "Project A"),
                      CostCenter(company, "CC-0002", "proj-B", "Project B")),
        jobs=(JobReference(company, "job-A", "proj-A", "task-A", "CC-0001"),),
    )


def scopes():
    return VerifiedScopes(
        project_ids=frozenset({"proj-A", "proj-B"}),
        task_scopes=frozenset({("proj-A", "task-A")}),
        checklist_scopes=frozenset({("proj-A", "task-A", "check-1")}),
        independent_source_scopes=frozenset({
            ("", "doc-1"), ("", "doc-2"), ("", "doc-3"),
            ("proj-A", "doc-A"),
        }),
    )


def state(company="co-A", *, end="2026-03-31"):
    return new_journal_state(company, (
        FiscalPeriod(company, "FY26-Q1", "2026-01-01", end),
        FiscalPeriod(company, "FY26-Q2", "2026-04-01", "2026-06-30"),
    ))


def source(kind="independent"):
    if kind == "independent":
        return JournalSource("independent", "doc-1")
    if kind in ("task", "card"):
        return JournalSource(kind, "task-A", "proj-A", "task-A")
    if kind == "checklist":
        return JournalSource("checklist", "check-1", "proj-A", "task-A", "check-1")
    raise AssertionError("invalid fixture kind")


def lines(company="co-A", amount=101, *, task=False):
    if task:
        project = dict(project_id="proj-A", task_id="task-A", job_id="job-A",
                       cost_center_code="CC-0001")
        return (
            JournalLine(PostingReference(company, "100102", **project),
                        debit_rial=amount),
            JournalLine(PostingReference(company, "400101", **project),
                        credit_rial=amount),
        )
    return (
        JournalLine(PostingReference(company, "100101"), debit_rial=amount),
        JournalLine(PostingReference(company, "400101"), credit_rial=amount),
    )


def post(old=None, *, company="co-A", event="evt-1", journal_source=None,
         journal_lines=None, accounting_chart=None, verified=None,
         period="FY26-Q1", day="2026-02-01",
         money_policy=None, rev=None):
    old = old if old is not None else state(company)
    return post_journal(
        old, company_id=company, fiscal_period_id=period, event_id=event,
        actor_id="trusted-admin", posting_date=day,
        source=journal_source if journal_source is not None else source(),
        lines=journal_lines if journal_lines is not None else lines(company),
        chart=accounting_chart if accounting_chart is not None else chart(company),
        scopes=verified if verified is not None else scopes(),
        money_policy=money_policy if money_policy is not None else CompanyMoneyPolicy(company),
        expected_revision=rev if rev is not None else old.revision,
        today="2026-10-21",
    )


def close(old, period="FY26-Q1", event="close-1", on="2026-04-01", **kwargs):
    return close_fiscal_period(
        old, company_id=kwargs.get("company", old.company_id),
        fiscal_period_id=period, event_id=event,
        actor_id="trusted-admin", closing_date=on,
        expected_revision=kwargs.get("rev", old.revision),
        today=kwargs.get("today", "2026-10-21"),
    )


def reverse(old, *, original="evt-1", event="rev-1",
            period="FY26-Q2", date="2026-04-03", reason="Posted in error",
            rev=None):
    return reverse_journal(
        old, company_id=old.company_id, original_event_id=original,
        event_id=event, actor_id="trusted-admin", fiscal_period_id=period,
        posting_date=date, reason=reason,
        expected_revision=rev if rev is not None else old.revision,
        today="2026-10-21",
    )


class RIALJournalKernelTests(unittest.TestCase):
    def reject(self, func, error=(JournalV2Error, ValueError)):
        with self.assertRaises(error):
            func()

    def test_genesis_period_explicit_and_immutable(self):
        opening = state()
        self.assertEqual(opening.currency, "RIAL")
        self.assertEqual(len(opening.revision), 64)
        self.assertEqual(replay_journal(opening).posted_count, 0)
        self.assertEqual(replay_journal(opening).positions, ())
        self.assertEqual(opening.events, ())
        with self.assertRaises(FrozenInstanceError):
            opening.company_id = "co-B"
        self.reject(lambda: new_journal_state("co-A", ()))
        self.reject(lambda: new_journal_state("co-A", [
            FiscalPeriod("co-A", "P-1", "2026-01-01", "2026-01-31")]))

    def test_exact_one_rial_balance_and_replay(self):
        saved = post(journal_lines=lines(amount=1))
        self.assertEqual(saved.currency, "RIAL")
        self.assertEqual(saved.events[0].lines[0].debit_rial, 1)
        result = replay_journal(saved)
        self.assertEqual(result.posted_count, 1)
        self.assertEqual({p.account_code: p.debit_minus_credit_rial
                          for p in result.positions},
                         {"100101": 1, "400101": -1})
        self.assertEqual(sum(p.debit_rial for p in result.positions), 1)
        self.assertEqual(sum(p.credit_rial for p in result.positions), 1)
        with self.assertRaises(FrozenInstanceError):
            saved.events[0].lines[0].debit_rial = 0

    def test_large_safe_rial_amount_not_rounded(self):
        saved = post(journal_lines=lines(amount=MAX_RIAL))
        self.assertEqual(saved.events[0].lines[0].debit_rial, MAX_RIAL)
        self.assertEqual(replay_journal(saved).positions[0].debit_rial, MAX_RIAL)
        self.reject(lambda: post(journal_lines=lines(amount=MAX_RIAL + 1)))
        self.reject(lambda: post(journal_lines=lines(amount=1.0)))
        self.reject(lambda: post(journal_lines=lines(amount=True)))

    def test_sum_and_intermediate_account_balance_overflow_prevented(self):
        opening = post(journal_lines=lines(amount=MAX_RIAL - 2))
        self.reject(lambda: post(
            opening, event="evt-2", journal_source=JournalSource("independent", "doc-2"),
            journal_lines=lines(amount=3)))
        self.assertEqual(len(opening.events), 1)

    def test_unbalanced_and_same_side_refused(self):
        self.reject(lambda: post(journal_lines=(
            JournalLine(PostingReference("co-A", "100101"), debit_rial=100),
            JournalLine(PostingReference("co-A", "400101"), credit_rial=99))))
        self.reject(lambda: JournalLine(PostingReference("co-A", "100101"), 100, 100))
        self.reject(lambda: JournalLine(PostingReference("co-A", "100101"), 0, 0))
        self.reject(lambda: JournalLine(PostingReference("co-A", "100101"), debit_rial=-1))
        self.reject(lambda: JournalLine(PostingReference("co-A", "100101"), debit_rial=10.5))
        self.reject(lambda: post(journal_lines=(
            JournalLine(PostingReference("co-A", "100101"), debit_rial=1),)))

    def test_event_idempotency_exact_retry_is_no_op(self):
        saved = post()
        duplicate = post(saved, event="evt-1")
        self.assertIs(duplicate, saved)
        self.assertEqual(len(duplicate.events), 1)
        self.assertEqual(duplicate.revision, saved.revision)

    def test_conflict_same_event_id_different_amount_or_source(self):
        saved = post()
        self.reject(lambda: post(saved, journal_lines=lines(amount=102)),
                    JournalV2Conflict)
        self.reject(lambda: post(saved, journal_source=JournalSource("independent", "doc-2")),
                    JournalV2Conflict)
        self.assertEqual(len(saved.events), 1)

    def test_cas_rejects_stale_expected_revision_even_for_duplicate(self):
        opening = state()
        saved = post(opening)
        self.reject(lambda: post(saved, rev=opening.revision), JournalV2Conflict)
        self.reject(lambda: close(saved, rev=opening.revision), JournalV2Conflict)
        self.assertEqual(len(saved.events), 1)

    def test_two_company_replay_separation_and_cross_company_rejection(self):
        first = post()
        second = post(company="co-B")
        self.assertEqual(first.company_id, "co-A")
        self.assertEqual(second.company_id, "co-B")
        self.assertNotEqual(first.revision, second.revision)
        self.reject(lambda: post(state("co-A"), accounting_chart=chart("co-B")))
        self.reject(lambda: post(state("co-A"), journal_lines=lines("co-B")))
        self.reject(lambda: post(state("co-A"), money_policy=CompanyMoneyPolicy("co-B")))
        self.reject(lambda: post_journal(
            state("co-A"), company_id="co-B", fiscal_period_id="FY26-Q1",
            event_id="foreign", actor_id="trusted-admin", posting_date="2026-02-01",
            source=source(), lines=lines("co-B"), chart=chart("co-B"),
            scopes=scopes(), money_policy=CompanyMoneyPolicy("co-B"),
            expected_revision=state("co-A").revision, today="2026-10-21"))

    def test_period_out_of_range_future_missing_and_bad_date(self):
        self.reject(lambda: post(day="2026-04-03"))
        self.reject(lambda: post(period="UNKNOWN"))
        self.reject(lambda: post(day="2026-02-30"))
        self.reject(lambda: post(day="2026-10-22", period="FY26-Q2"))
        self.reject(lambda: FiscalPeriod("co-A", "P", "2026-02-02", "2026-01-01"))
        self.reject(lambda: new_journal_state("co-A", (
            FiscalPeriod("co-A", "P-1", "2026-01-01", "2026-03-31"),
            FiscalPeriod("co-A", "P-2", "2026-03-31", "2026-04-01"))))

    def test_period_close_is_strict_ordered_and_irreversible(self):
        saved = post()
        closed = close(saved)
        self.assertEqual(replay_journal(closed).closed_period_ids, frozenset({"FY26-Q1"}))
        self.reject(lambda: post(closed, event="evt-2",
                                 journal_source=JournalSource("independent", "doc-2")))
        self.reject(lambda: close(closed, event="close-2"))
        self.reject(lambda: close(state(), period="FY26-Q2", event="close-q2",
                                  on="2026-07-01"))
        self.assertIs(close(closed), closed)
        next_period = post(closed, event="evt-2", period="FY26-Q2",
                           day="2026-04-10",
                           journal_source=JournalSource("independent", "doc-2"))
        self.assertEqual(replay_journal(next_period).posted_count, 2)

    def test_close_rejects_early_or_future_date(self):
        self.reject(lambda: close(state(), on="2026-03-30"))
        self.reject(lambda: close(state(), on="2026-11-01"))
        self.reject(lambda: close(state(), on="2026-04-00"))

    def test_source_task_card_checklist_and_independent_provenance(self):
        for name in ("task", "card", "checklist"):
            with self.subTest(source=name):
                old = post(journal_source=source(name), journal_lines=lines(task=True))
                self.assertEqual(old.events[0].source.kind, name)
                self.assertEqual(replay_journal(old).posted_count, 1)
                self.assertEqual(old.events[0].lines[0].reference.cost_center_code,
                                 "CC-0001")
        self.assertEqual(post().events[0].source.kind, "independent")

    def test_source_must_be_host_verified(self):
        self.reject(lambda: post(verified=VerifiedScopes()))
        self.reject(lambda: post(journal_source=JournalSource("independent", "forged")))
        self.reject(lambda: post(journal_source=JournalSource(
            "independent", "doc-1", project_id="proj-A")))
        self.reject(lambda: post(journal_source=JournalSource(
            "independent", "doc-A", project_id="proj-B")))
        self.reject(lambda: post(
            journal_source=source("checklist"),
            journal_lines=lines(task=True),
            verified=replace(scopes(), checklist_scopes=frozenset())))
        self.reject(lambda: post(
            journal_source=source("task"), journal_lines=lines(task=True),
            verified=replace(scopes(), task_scopes=frozenset())))
        self.reject(lambda: JournalSource("task", "task-A", project_id="proj-A"))
        self.reject(lambda: JournalSource("checklist", "check-1", "proj-A",
                                          "task-A", "different"))

    def test_explicit_company_verified_project_independent_document_success(self):
        tag = {"project_id": "proj-A"}
        tagged = (
            JournalLine(PostingReference("co-A", "100101", **tag), debit_rial=3),
            JournalLine(PostingReference("co-A", "400101", **tag), credit_rial=3))
        posted = post(journal_source=JournalSource("independent", "doc-A", "proj-A"),
                      journal_lines=tagged)
        self.assertEqual(posted.events[0].source.project_id, "proj-A")
        self.assertEqual(replay_journal(posted).posted_count, 1)
        self.reject(lambda: post(journal_source=JournalSource(
            "independent", "doc-A", "proj-A"), journal_lines=lines(amount=3)))

    def test_foreign_project_mismatched_task_and_bad_cost_center(self):
        self.reject(lambda: post(journal_source=source("task"),
                                 journal_lines=lines(task=False)))
        bad_center = tuple(
            JournalLine(replace(line.reference, cost_center_code="CC-0002"),
                        line.debit_rial, line.credit_rial)
            for line in lines(task=True))
        self.reject(lambda: post(journal_source=source("task"), journal_lines=bad_center))
        bad_task = tuple(
            JournalLine(replace(line.reference, task_id="wrong-task"),
                        line.debit_rial, line.credit_rial)
            for line in lines(task=True))
        self.reject(lambda: post(journal_source=source("task"), journal_lines=bad_task))

    def test_no_group_archived_frozen_or_unknown_account_postings(self):
        for code in ("10", "1001", "UNKNOWN"):
            bad = (JournalLine(PostingReference("co-A", code), debit_rial=10),
                   JournalLine(PostingReference("co-A", "400101"), credit_rial=10))
            self.reject(lambda b=bad: post(journal_lines=b))
        self.reject(lambda: post(accounting_chart=chart(inactive=True)))
        self.reject(lambda: post(accounting_chart=chart(frozen=True)))

    def test_chart_and_scope_evidence_retained_and_verified_on_replay(self):
        saved = post()
        self.assertEqual(len(saved.evidence), 1)
        self.assertEqual(saved.events[0].evidence_digest,
                         saved.evidence[0].evidence_digest)
        broken = replace(saved.evidence[0], max_abs_rial=MAX_RIAL-1)
        self.reject(lambda: replay_journal(replace(saved, evidence=(broken,))))
        self.reject(lambda: replay_journal(replace(saved, evidence=())))
        another = replace(saved.evidence[0], scopes=VerifiedScopes())
        self.reject(lambda: replay_journal(replace(saved, evidence=(another,))))

    def test_history_change_detected_by_hash_replay(self):
        saved = post()
        event = saved.events[0]
        altered = replace(event, lines=lines(amount=103))
        self.reject(lambda: replay_journal(replace(saved, events=(altered,))))
        self.reject(lambda: replay_journal(replace(
            saved, events=(replace(event, event_hash="f"*64),))))
        self.reject(lambda: replay_journal(replace(
            saved, events=(replace(event, company_id="co-B"),))))
        self.assertEqual(replay_journal(saved).posted_count, 1)

    def test_business_preflight_rejects_unbalanced_event_even_with_forged_digest(self):
        saved = post()
        old = saved.events[0]
        fraud_lines = (JournalLine(old.lines[0].reference, debit_rial=102),
                       old.lines[1])
        forgery = replace(old, lines=fraud_lines)
        command = kernel._journal_command(forgery)
        forgery = replace(forgery,
                          command_digest=snapshot_sha256(command),
                          event_hash=kernel._event_hash(command, old.previous_hash))
        self.reject(lambda: replay_journal(replace(saved, events=(forgery,))))

    def test_duplicate_event_replay_is_detected_even_when_hash_recomputed(self):
        original = post()
        duplicated = replace(original, events=(original.events[0], original.events[0]))
        self.reject(lambda: replay_journal(duplicated))

    def test_reversal_is_new_signed_inverse_preserving_original(self):
        original = post()
        closed = close(original)
        reversed_state = reverse(closed)
        self.assertEqual(len(reversed_state.events), 3)
        self.assertEqual(reversed_state.events[0], original.events[0])
        reversal = reversed_state.events[-1]
        self.assertIsInstance(reversal, PostedJournal)
        self.assertEqual(reversal.reversal_of, "evt-1")
        self.assertEqual(reversal.lines[0].credit_rial, 101)
        self.assertEqual(reversal.lines[1].debit_rial, 101)
        projection = replay_journal(reversed_state)
        self.assertEqual(projection.posted_count, 2)
        self.assertEqual(projection.reversed_event_ids, frozenset({"evt-1"}))
        self.assertEqual({p.debit_minus_credit_rial for p in projection.positions}, {0})
        self.assertIs(reverse(reversed_state), reversed_state)

    def test_double_reversal_unknown_and_reverse_of_reversal_are_rejected(self):
        once = reverse(post())
        self.reject(lambda: reverse(once, event="rev-2"), JournalV2Conflict)
        self.reject(lambda: reverse(once, original="rev-1", event="rev-3"))
        self.reject(lambda: reverse(once, original="unknown", event="rev-4"))
        self.reject(lambda: reverse(post(), reason=" "))
        self.reject(lambda: reverse(post(), date="2026-01-31", period="FY26-Q1"))
        self.reject(lambda: reverse(close(post()), period="FY26-Q1", date="2026-03-31"))

    def test_reversal_reuses_historical_chart_context_without_reopening_period(self):
        original = post()
        after_close = close(original)
        new_period_reversal = reverse(after_close)
        self.assertEqual(new_period_reversal.events[0].evidence_digest,
                         new_period_reversal.events[-1].evidence_digest)
        self.assertEqual(replay_journal(new_period_reversal).closed_period_ids,
                         frozenset({"FY26-Q1"}))

    def test_company_money_ceiling_is_persisted_in_historical_evidence(self):
        small_policy = CompanyMoneyPolicy("co-A", max_abs_rial=100)
        self.reject(lambda: post(money_policy=small_policy))
        saved = post(journal_lines=lines(amount=99), money_policy=small_policy)
        self.assertEqual(saved.evidence[0].max_abs_rial, 100)
        self.assertEqual(replay_journal(saved).posted_count, 1)
        self.reject(lambda: replay_journal(replace(
            saved, evidence=(replace(saved.evidence[0], max_abs_rial=MAX_RIAL),))))

    def test_immutable_history_cannot_be_reinterpreted_as_toman(self):
        saved = post()
        self.reject(lambda: replay_journal(replace(saved, currency="TOMAN")))
        self.reject(lambda: post(saved, money_policy=CompanyMoneyPolicy(
            "co-A", accounting_currency="TOMAN")))
        self.assertEqual(saved.events[0].lines[0].debit_rial, 101)
        self.assertEqual(saved.currency, "RIAL")

    def test_scopes_strict_frozensets_and_identifiers(self):
        self.reject(lambda: VerifiedScopes(project_ids={"proj-A"}))
        self.reject(lambda: VerifiedScopes(task_scopes=frozenset({("p",)})))
        self.reject(lambda: VerifiedScopes(project_ids=frozenset({"bad project"})))
        self.reject(lambda: VerifiedScopes(
            independent_source_scopes=frozenset({("proj-A", "bad id")})))
        self.reject(lambda: VerifiedScopes(
            independent_source_scopes=frozenset({("doc-1",)})))
        self.reject(lambda: JournalSource("unsupported", "source-1"))
        self.reject(lambda: JournalSource("independent", "doc-1", task_id="task-A"))


if __name__ == "__main__":
    unittest.main()
