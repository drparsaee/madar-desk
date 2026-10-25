"""Isolated temporary SQLite CAS/security/input tests; no live Madar data."""
import json
import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ir_chart_model import ChartAccount, ChartSnapshot, PostingReference
from ir_journal_v2 import (
    FiscalPeriod, JournalLine, JournalSource, VerifiedScopes,
    new_journal_state, post_journal, replay_journal, JournalV2Conflict,
)
from ir_journal_sqlite import RIALJournalStorage
from money_policy import CompanyMoneyPolicy


def _chart(company):
    return ChartSnapshot(company, accounts=(
        ChartAccount(company, "10", "KOL", None, "Assets", "asset"),
        ChartAccount(company, "1001", "MOEIN", "10", "Bank", "asset"),
        ChartAccount(company, "100101", "TAFSILI", "1001", "Cash", "asset",
                     accountable=True),
        ChartAccount(company, "40", "KOL", None, "Sales", "revenue"),
        ChartAccount(company, "4001", "MOEIN", "40", "Sales", "revenue"),
        ChartAccount(company, "400101", "TAFSILI", "4001", "Sales", "revenue",
                     accountable=True),
    ))


def _init(company):
    return new_journal_state(company, (
        FiscalPeriod(company, "FY26", "2026-01-01", "2026-12-31"),))


def _post(state, company, event="ev-1", amount=1, source="invoice-1"):
    return post_journal(
        state, company_id=company, fiscal_period_id="FY26",
        event_id=event, actor_id="admin", posting_date="2026-10-21",
        source=JournalSource("independent", source),
        lines=(JournalLine(PostingReference(company, "100101"), debit_rial=amount),
               JournalLine(PostingReference(company, "400101"), credit_rial=amount)),
        chart=_chart(company), scopes=VerifiedScopes(
            independent_source_scopes=frozenset({("", source)})),
        money_policy=CompanyMoneyPolicy(company),
        expected_revision=state.revision, today="2026-10-21",
    )


class JournalSQLiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-rial-sqlite-test-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "journal.sqlite3"
        self.store = RIALJournalStorage(self.path)

    def test_initialization_post_read_exact_one_rial(self):
        state = _init("company-A")
        self.store.commit(state, expected_revision=None)
        output = self.store.mutate("company-A", state.revision,
                                   lambda old: _post(old, "company-A"))
        self.assertEqual(output.events[0].lines[0].debit_rial, 1)
        again = self.store.read("company-A")
        self.assertEqual(again, output)
        self.assertEqual(replay_journal(again).posted_count, 1)

    def test_idempotent_retry_does_not_duplicate_post(self):
        state = _init("company-A")
        self.store.commit(state, expected_revision=None)
        posted = self.store.mutate("company-A", state.revision,
                                   lambda old: _post(old, "company-A"))
        retry = self.store.mutate("company-A", posted.revision,
                                  lambda old: _post(old, "company-A"))
        self.assertEqual(posted, retry)
        self.assertEqual(len(self.store.read("company-A").events), 1)

    def test_stale_revision_is_rejected_no_partial_mutation(self):
        state = _init("company-A")
        self.store.commit(state, expected_revision=None)
        posted = self.store.mutate("company-A", state.revision,
                                   lambda old: _post(old, "company-A"))
        with self.assertRaises(JournalV2Conflict):
            self.store.mutate("company-A", state.revision,
                              lambda old: _post(old, "company-A", "ev-2"))
        self.assertEqual(self.store.read("company-A"), posted)

    def test_isolation_company_and_wrong_company_mutation(self):
        left, right = _init("company-A"), _init("company-B")
        self.store.commit(left, expected_revision=None)
        self.store.commit(right, expected_revision=None)
        with self.assertRaises(ValueError):
            self.store.mutate("company-A", left.revision,
                              lambda old: _post(old, "company-B"))
        self.assertEqual(self.store.read("company-A"), left)
        self.assertEqual(self.store.read("company-B"), right)

    def test_conflicting_event_same_id_fails_atomically(self):
        state = _init("company-A")
        self.store.commit(state, expected_revision=None)
        posted = self.store.mutate("company-A", state.revision,
                                   lambda old: _post(old, "company-A"))
        with self.assertRaises(JournalV2Conflict):
            self.store.mutate("company-A", posted.revision,
                              lambda old: _post(old, "company-A", amount=2))
        self.assertEqual(self.store.read("company-A"), posted)

    def test_same_business_source_with_new_event_id_blocked_in_sql(self):
        initial = _init("company-A")
        self.store.commit(initial, expected_revision=None)
        once = self.store.mutate("company-A", initial.revision,
                                 lambda old: _post(old, "company-A"))
        with self.assertRaises(JournalV2Conflict):
            self.store.mutate("company-A", once.revision,
                              lambda old: _post(old, "company-A", event="ev-new"))
        self.assertEqual(self.store.read("company-A"), once)

    def test_competing_sql_cas_only_one_commit_wins(self):
        start = _init("company-A")
        self.store.commit(start, expected_revision=None)

        def racing(i):
            contender = RIALJournalStorage(self.path)
            try:
                contender.mutate("company-A", start.revision,
                                 lambda old: _post(
                                     old, "company-A", event="ev-"+str(i),
                                     source="invoice-"+str(i)))
                return "won"
            except JournalV2Conflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(racing, range(6)))
        self.assertEqual(results.count("won"), 1)
        self.assertEqual(results.count("conflict"), 5)
        self.assertEqual(replay_journal(self.store.read("company-A")).posted_count, 1)

    def test_sql_quoted_company_identifier_cannot_change_other_company(self):
        first, second = _init("company-A"), _init("company-B")
        self.store.commit(first, expected_revision=None)
        self.store.commit(second, expected_revision=None)
        self.assertIsNone(self.store.read("company-A' OR 1=1 --"))
        self.assertEqual(self.store.read("company-B"), second)

    def test_invalid_unbalanced_business_operation_does_not_commit(self):
        state = _init("company-A")
        self.store.commit(state, expected_revision=None)
        with self.assertRaises(ValueError):
            self.store.mutate("company-A", state.revision,
                              lambda old: post_journal(
                                  old, company_id="company-A", fiscal_period_id="FY26",
                                  event_id="bad", actor_id="admin",
                                  posting_date="2026-10-21",
                                  source=JournalSource("independent", "invoice-1"),
                                  lines=(
                                      JournalLine(PostingReference(
                                          "company-A", "100101"), debit_rial=10),
                                      JournalLine(PostingReference(
                                          "company-A", "400101"), credit_rial=9)),
                                  chart=_chart("company-A"),
                                  scopes=VerifiedScopes(
                                      independent_source_scopes=frozenset({
                                          ("", "invoice-1")})),
                                  money_policy=CompanyMoneyPolicy("company-A"),
                                  expected_revision=old.revision,
                                  today="2026-10-21"))
        self.assertEqual(self.store.read("company-A"), state)

    def test_sql_payload_corruption_detected(self):
        state = _init("company-A")
        self.store.commit(state, expected_revision=None)
        db = sqlite3.connect(self.path)
        try:
            db.execute("UPDATE rial_journal_v2 SET payload=? WHERE company_id=?",
                       (b"{}", "company-A"))
            db.commit()
        finally:
            db.close()
        with self.assertRaises(ValueError):
            self.store.read("company-A")

    def test_dedicated_db_refuses_duplicate_initialization(self):
        state = _init("company-A")
        self.store.commit(state, expected_revision=None)
        with self.assertRaises(JournalV2Conflict):
            self.store.commit(state, expected_revision=None)
        self.assertEqual(self.store.read("company-A"), state)

    def test_mutation_failure_rolls_back_all_fields(self):
        state = _init("company-A")
        self.store.commit(state, expected_revision=None)
        def fail(_):
            raise RuntimeError("simulated database business failure")
        with self.assertRaises(RuntimeError):
            self.store.mutate("company-A", state.revision, fail)
        self.assertEqual(self.store.read("company-A"), state)

    def test_cas_does_not_allow_rewriting_issued_journal_with_valid_revision(self):
        genesis = _init("company-A")
        self.store.commit(genesis, expected_revision=None)
        posted = self.store.mutate("company-A", genesis.revision,
                                   lambda old: _post(old, "company-A"))
        with self.assertRaises(ValueError):
            self.store.commit(genesis, expected_revision=posted.revision)
        with self.assertRaises(ValueError):
            self.store.mutate("company-A", posted.revision,
                              lambda old: replace(old, events=()))
        self.assertEqual(self.store.read("company-A"), posted)

    def test_unverified_business_scope_rejected_atomically(self):
        state = _init("company-A")
        self.store.commit(state, expected_revision=None)
        with self.assertRaises(ValueError):
            self.store.mutate("company-A", state.revision,
                              lambda old: post_journal(
                                  old, company_id="company-A", fiscal_period_id="FY26",
                                  event_id="untrusted", actor_id="admin",
                                  posting_date="2026-10-21",
                                  source=JournalSource("independent", "wrong"),
                                  lines=(
                                      JournalLine(PostingReference(
                                          "company-A", "100101"), debit_rial=1),
                                      JournalLine(PostingReference(
                                          "company-A", "400101"), credit_rial=1)),
                                  chart=_chart("company-A"),
                                  scopes=VerifiedScopes(),
                                  money_policy=CompanyMoneyPolicy("company-A"),
                                  expected_revision=old.revision,
                                  today="2026-10-21"))
        self.assertEqual(self.store.read("company-A"), state)


if __name__ == "__main__":
    unittest.main()
