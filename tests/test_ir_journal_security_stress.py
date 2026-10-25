"""Adversarial RIAL V2 SQLite/kernel checks using isolated temporary databases.

No production application state, old TOMAN ledger, network, or real business IDs.
Run: python -m unittest discover -s tests -p test_ir_journal_security_stress.py -v
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from threading import Barrier
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ir_chart_model import ChartAccount, ChartSnapshot, PostingReference
from ir_journal_sqlite import RIALJournalStorage, _deserialize, _serialize
from ir_journal_v2 import (
    FiscalPeriod, JournalLine, JournalSource, JournalV2Conflict,
    MAX_EVENTS, MAX_CHART_EVIDENCE,
    VerifiedScopes, close_fiscal_period, new_journal_state, post_journal,
    replay_journal, reverse_journal,
)
from money_policy import CompanyMoneyPolicy, MAX_RIAL, snapshot_sha256


COMPANY = "stress-A"
OTHER = "stress-B"
TODAY = "2026-10-21"


def chart(company=COMPANY):
    return ChartSnapshot(company, accounts=(
        ChartAccount(company, "10", "KOL", None, "Assets", "asset"),
        ChartAccount(company, "1001", "MOEIN", "10", "Cash", "asset"),
        ChartAccount(company, "100101", "TAFSILI", "1001", "Cash", "asset",
                     accountable=True),
        ChartAccount(company, "40", "KOL", None, "Revenue", "revenue"),
        ChartAccount(company, "4001", "MOEIN", "40", "Revenue", "revenue"),
        ChartAccount(company, "400101", "TAFSILI", "4001", "Revenue", "revenue",
                     accountable=True),
    ))


def initial(company=COMPANY, *, split=False):
    if split:
        periods = (
            FiscalPeriod(company, "Q1", "2026-01-01", "2026-03-31"),
            FiscalPeriod(company, "Q2", "2026-04-01", "2026-06-30"),
        )
    else:
        periods = (FiscalPeriod(company, "FY26", "2026-01-01", "2026-12-31"),)
    return new_journal_state(company, periods)


def post(old, *, company=None, event="event-1", source="invoice-1",
         amount=1, period="FY26", date=TODAY, scope=None,
         account_company=None, actor="trusted-actor", policy=None):
    company = company or old.company_id
    account_company = account_company or company
    verified = scope if scope is not None else VerifiedScopes(
        independent_source_scopes=frozenset({("", source)}))
    return post_journal(
        old, company_id=company, fiscal_period_id=period, event_id=event,
        actor_id=actor, posting_date=date,
        source=JournalSource("independent", source),
        lines=(
            JournalLine(PostingReference(account_company, "100101"),
                        debit_rial=amount),
            JournalLine(PostingReference(account_company, "400101"),
                        credit_rial=amount),
        ),
        chart=chart(company), scopes=verified,
        money_policy=policy or CompanyMoneyPolicy(company),
        expected_revision=old.revision, today=TODAY,
    )


class JournalSecurityStressTests(unittest.TestCase):
    def setUp(self):
        # Keep all synthetic scratch files in this project's tests directory.
        temp = tempfile.TemporaryDirectory(
            prefix="madar-rial-security-stress-",
            dir=Path(__file__).resolve().parent)
        self.addCleanup(temp.cleanup)
        self.database = Path(temp.name) / "synthetic-rial.sqlite3"
        self.storage = RIALJournalStorage(self.database)

    def seed(self, company=COMPANY, *, split=False):
        opening = initial(company, split=split)
        self.storage.commit(opening, expected_revision=None)
        return opening

    def snapshot(self, company=COMPANY):
        return self.storage.read(company)

    def row(self, company=COMPANY):
        with closing(sqlite3.connect(self.database)) as db:
            return db.execute(
                "SELECT revision,payload,digest FROM rial_journal_v2 WHERE company_id=?",
                (company,)).fetchone()

    def replace_payload(self, payload, *, company=COMPANY, update_digest=True):
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        with closing(sqlite3.connect(self.database)) as db:
            if update_digest:
                db.execute("UPDATE rial_journal_v2 SET payload=?,digest=? "
                           "WHERE company_id=?",
                           (encoded, snapshot_sha256(payload), company))
            else:
                db.execute("UPDATE rial_journal_v2 SET payload=? WHERE company_id=?",
                           (encoded, company))
            db.commit()

    def test_high_contention_single_revision_exactly_one_winner(self):
        opening = self.seed()
        workers = 16
        ready = Barrier(workers)

        def attempt(index):
            peer = RIALJournalStorage(self.database)
            ready.wait(timeout=12)
            try:
                peer.mutate(COMPANY, opening.revision, lambda state: post(
                    state, event=f"race-{index}", source=f"race-invoice-{index}"))
                return "won"
            except JournalV2Conflict:
                return "cas-conflict"

        with ThreadPoolExecutor(max_workers=workers) as executor:
            outcomes = list(executor.map(attempt, range(workers)))
        self.assertEqual(outcomes.count("won"), 1, outcomes)
        self.assertEqual(outcomes.count("cas-conflict"), workers - 1, outcomes)
        final = self.snapshot()
        self.assertEqual(replay_journal(final).posted_count, 1)
        self.assertEqual(len(final.events), 1)

    def test_multi_writer_retry_stress_no_lost_post_and_balanced_replay(self):
        self.seed()
        writers, each = 5, 7

        def worker(index):
            peer = RIALJournalStorage(self.database)
            conflicts = 0
            for sequence in range(each):
                event = f"batch-{index}-{sequence}"
                source = f"bill-{index}-{sequence}"
                for attempt in range(150):
                    current = peer.read(COMPANY)
                    try:
                        peer.mutate(COMPANY, current.revision, lambda state: post(
                            state, event=event, source=source, amount=index + 1))
                        break
                    except JournalV2Conflict:
                        conflicts += 1
                else:
                    self.fail(f"CAS retries exhausted: {event}")
            return conflicts

        with ThreadPoolExecutor(max_workers=writers) as executor:
            collisions = list(executor.map(worker, range(writers)))
        final = self.snapshot()
        projected = replay_journal(final)
        self.assertEqual(projected.posted_count, writers * each)
        self.assertEqual(len({e.event_id for e in final.events}), writers * each)
        self.assertEqual(len({e.source.source_id for e in final.events}), writers * each)
        total = each * sum(range(1, writers + 1))
        self.assertEqual(sum(position.debit_rial for position in projected.positions), total)
        self.assertEqual(sum(position.credit_rial for position in projected.positions), total)
        self.assertTrue(all(c >= 0 for c in collisions))

    def test_same_source_different_event_rejected_across_sql_mutate_and_commit(self):
        opening = self.seed()
        once = self.storage.mutate(COMPANY, opening.revision,
                                   lambda old: post(old, event="first"))
        with self.assertRaises(JournalV2Conflict):
            self.storage.mutate(COMPANY, once.revision,
                                lambda old: post(old, event="second", amount=2))
        forged = post(once, event="second", amount=2)
        # The pure kernel currently permits reusing a source under a new ID.
        self.assertEqual(len(forged.events), 2)
        with self.assertRaises(JournalV2Conflict):
            self.storage.commit(forged, expected_revision=once.revision)
        self.assertEqual(self.snapshot(), once)

    def test_racing_duplicate_source_with_distinct_event_ids(self):
        opening = self.seed()
        writers = 8
        ready = Barrier(writers)

        def duplicate(i):
            ready.wait(timeout=12)
            try:
                return self.storage.mutate(COMPANY, opening.revision,
                    lambda old: post(old, event=f"fraud-{i}", source="one-invoice")
                              ).events[-1].event_id
            except JournalV2Conflict:
                return "rejected"

        with ThreadPoolExecutor(max_workers=writers) as executor:
            results = list(executor.map(duplicate, range(writers)))
        self.assertEqual(results.count("rejected"), writers - 1)
        self.assertEqual(len(self.snapshot().events), 1)
        current = self.snapshot()
        with self.assertRaises(JournalV2Conflict):
            self.storage.mutate(COMPANY, current.revision,
                lambda old: post(old, event="fraud-later", source="one-invoice"))
        self.assertEqual(self.snapshot(), current)

    def test_exact_retry_is_idempotent_and_stale_retry_rejected(self):
        opening = self.seed()
        once = self.storage.mutate(COMPANY, opening.revision, lambda old: post(old))
        twice = self.storage.mutate(COMPANY, once.revision, lambda old: post(old))
        self.assertEqual(twice, once)
        with self.assertRaises(JournalV2Conflict):
            self.storage.mutate(COMPANY, opening.revision, lambda old: post(old))
        with self.assertRaises(JournalV2Conflict):
            self.storage.mutate(COMPANY, once.revision,
                                lambda old: post(old, amount=3))
        self.assertEqual(self.snapshot(), once)

    def test_cross_company_write_rejects_forged_chart_line_state(self):
        left, right = self.seed(COMPANY), self.seed(OTHER)
        with self.assertRaises(ValueError):
            self.storage.mutate(COMPANY, left.revision,
                lambda old: post(old, account_company=OTHER))
        with self.assertRaises(ValueError):
            self.storage.mutate(COMPANY, left.revision,
                lambda old: post(old, company=OTHER))
        with self.assertRaises(ValueError):
            self.storage.mutate(COMPANY, left.revision,
                lambda old: replace(old, company_id=OTHER))
        with self.assertRaises(ValueError):
            self.storage.commit(right, expected_revision=left.revision)
        self.assertEqual(self.snapshot(COMPANY), left)
        self.assertEqual(self.snapshot(OTHER), right)

    def test_parallel_independent_companies_preserve_company_boundaries(self):
        companies = tuple(f"isolate-{index}" for index in range(6))
        for company in companies:
            self.seed(company)

        def save(company):
            peer = RIALJournalStorage(self.database)
            base = peer.read(company)
            return peer.mutate(company, base.revision,
                lambda old: post(old, event="same-event", source="same-invoice"))

        with ThreadPoolExecutor(max_workers=len(companies)) as executor:
            states = list(executor.map(save, companies))
        self.assertEqual({state.company_id for state in states}, set(companies))
        for company in companies:
            saved = self.snapshot(company)
            self.assertEqual(saved.company_id, company)
            self.assertEqual(saved.events[0].company_id, company)
            self.assertEqual(replay_journal(saved).posted_count, 1)

    def test_sql_injection_strings_are_data_not_operators(self):
        opening = self.seed()
        crafted = "stress-A' OR 1=1 --"
        self.assertIsNone(self.storage.read(crafted))
        with self.assertRaises(ValueError):
            self.storage.mutate(crafted, opening.revision,
                                lambda old: post(old))
        self.assertEqual(self.snapshot(), opening)

    def test_bad_money_inputs_rejected_before_any_commit(self):
        opening = self.seed()
        bad_values = (True, False, 1.0, float("nan"), float("inf"),
                      "10", -1, MAX_RIAL + 1, 10**100, None, 0)
        for value in bad_values:
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    self.storage.mutate(COMPANY, opening.revision,
                        lambda old, number=value: post(old, amount=number))
                self.assertEqual(self.snapshot(), opening)

    def test_overflow_after_prior_post_is_atomic(self):
        opening = self.seed()
        first = self.storage.mutate(COMPANY, opening.revision,
            lambda old: post(old, amount=MAX_RIAL - 1))
        with self.assertRaises(ValueError):
            self.storage.mutate(COMPANY, first.revision,
                lambda old: post(old, event="overflow", source="next-invoice", amount=2))
        self.assertEqual(self.snapshot(), first)

    def test_bad_identifiers_untrusted_scopes_and_unbalanced_input(self):
        opening = self.seed()
        operations = (
            lambda old: post(old, event="bad id"),
            lambda old: post(old, source="bad/source"),
            lambda old: post(old, actor="untrusted actor"),
            lambda old: post(old, scope=VerifiedScopes()),
            lambda old: post(old, policy=CompanyMoneyPolicy(OTHER)),
            lambda old: post(old, date="2026-02-30"),
            lambda old: post(old, date="2026-10-22"),
        )
        for index, op in enumerate(operations):
            with self.subTest(operation=index):
                with self.assertRaises(ValueError):
                    self.storage.mutate(COMPANY, opening.revision, op)
                self.assertEqual(self.snapshot(), opening)

        def unbalanced(old):
            return post_journal(
                old, company_id=COMPANY, fiscal_period_id="FY26",
                event_id="fraud-balance", actor_id="trusted-actor",
                posting_date=TODAY, source=JournalSource("independent", "invoice-1"),
                lines=(JournalLine(PostingReference(COMPANY, "100101"), 2, 0),
                       JournalLine(PostingReference(COMPANY, "400101"), 0, 1)),
                chart=chart(), scopes=VerifiedScopes(
                    independent_source_scopes=frozenset({("", "invoice-1")})),
                money_policy=CompanyMoneyPolicy(COMPANY),
                expected_revision=old.revision, today=TODAY)

        with self.assertRaises(ValueError):
            self.storage.mutate(COMPANY, opening.revision, unbalanced)
        self.assertEqual(self.snapshot(), opening)

    def test_append_only_denies_event_removal_reorder_and_currency_flip(self):
        opening = self.seed()
        first = self.storage.mutate(COMPANY, opening.revision,
            lambda old: post(old, event="one"))
        second = self.storage.mutate(COMPANY, first.revision,
            lambda old: post(old, event="two", source="invoice-2"))
        attempted = (
            replace(second, events=(second.events[1], second.events[0])),
            replace(second, events=second.events[:1]),
            replace(second, currency="TOMAN"),
            replace(second, evidence=()),
        )
        for candidate in attempted:
            with self.subTest(candidate=str(candidate.currency) + str(len(candidate.events))):
                with self.assertRaises(ValueError):
                    self.storage.commit(candidate, expected_revision=second.revision)
                self.assertEqual(self.snapshot(), second)

    def test_rehashed_tampered_event_fails_domain_replay(self):
        opening = self.seed()
        correct = self.storage.mutate(COMPANY, opening.revision,
                                      lambda old: post(old, amount=3))
        _, binary, _ = self.row()
        malicious = json.loads(binary)
        malicious["events"][0]["body"]["lines"][0]["debit_rial"] = 99
        self.replace_payload(malicious, update_digest=True)
        with self.assertRaises(ValueError):
            self.storage.read(COMPANY)
        with self.assertRaises(ValueError):
            self.storage.mutate(COMPANY, correct.revision, lambda old: old)

    def test_direct_database_writer_can_replace_entire_valid_history(self):
        """Threat demonstration: an untrusted DB writer can recompute plain hashes.

        A PASS here means the missing external authenticity anchor is reproduced,
        not that unauthenticated DB rewriting is secure or acceptable.
        """
        opening = self.seed()
        actual = self.storage.mutate(COMPANY, opening.revision,
            lambda old: post(old, amount=2))
        alternate = post(opening, amount=900)
        self.assertNotEqual(alternate.revision, actual.revision)
        # This attacker bypasses the host's commit API and already has write
        # access to the isolated synthetic database file.
        forged_payload = _serialize(alternate)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("UPDATE rial_journal_v2 SET revision=?,payload=?,digest=? "
                       "WHERE company_id=?", (
                           alternate.revision, forged_payload,
                           snapshot_sha256(json.loads(forged_payload)), COMPANY))
            db.commit()
        accepted = self.storage.read(COMPANY)
        self.assertEqual(accepted, alternate)
        self.assertNotEqual(accepted, actual)
        self.assertEqual(accepted.events[0].lines[0].debit_rial, 900)

    def test_checksum_and_schema_fraud_are_detected(self):
        opening = self.seed()
        old_row = self.row()
        cases = (
            ("checksum", lambda payload: payload.update(currency="TOMAN"), False),
            ("currency-rehashed", lambda payload: payload.update(currency="TOMAN"), True),
            ("company-rehashed", lambda payload: payload.update(company_id=OTHER), True),
            ("schema-rehashed", lambda payload: payload.update(extra="hidden"), True),
        )
        for name, attack, recalc in cases:
            with self.subTest(case=name):
                obj = json.loads(old_row[1])
                attack(obj)
                self.replace_payload(obj, update_digest=recalc)
                with self.assertRaises(ValueError):
                    self.storage.read(COMPANY)
                with closing(sqlite3.connect(self.database)) as db:
                    db.execute("UPDATE rial_journal_v2 SET revision=?,payload=?,digest=? "
                               "WHERE company_id=?", (*old_row, COMPANY))
                    db.commit()
                self.assertEqual(self.snapshot(), opening)

    def test_serialized_float_injection_cannot_hash_or_deserialize(self):
        opening = self.seed()
        posted = self.storage.mutate(COMPANY, opening.revision,
                                     lambda old: post(old))
        _, blob, _ = self.row()
        payload = json.loads(blob)
        payload["events"][0]["body"]["lines"][0]["debit_rial"] = 1.5
        with self.assertRaises(ValueError):
            snapshot_sha256(payload)
        with self.assertRaises(ValueError):
            _deserialize(json.dumps(payload).encode("utf-8"))
        self.replace_payload(payload, update_digest=False)
        with self.assertRaises(ValueError):
            self.storage.read(COMPANY)
        with self.assertRaises(ValueError):
            self.storage.commit(posted, expected_revision=posted.revision)

    def test_line_count_boundary_100_allowed_102_rejected(self):
        opening = self.seed()

        def event_with_lines(old, count, event):
            entries = tuple(
                JournalLine(PostingReference(COMPANY,
                            "100101" if i % 2 == 0 else "400101"),
                            debit_rial=1 if i % 2 == 0 else 0,
                            credit_rial=1 if i % 2 else 0)
                for i in range(count))
            return post_journal(
                old, company_id=COMPANY, fiscal_period_id="FY26",
                event_id=event, actor_id="trusted-actor", posting_date=TODAY,
                source=JournalSource("independent", event), lines=entries,
                chart=chart(), scopes=VerifiedScopes(
                    independent_source_scopes=frozenset({("", event)})),
                money_policy=CompanyMoneyPolicy(COMPANY),
                expected_revision=old.revision, today=TODAY)

        allowed = self.storage.mutate(COMPANY, opening.revision,
            lambda old: event_with_lines(old, 100, "bulk-100"))
        self.assertEqual(len(allowed.events[0].lines), 100)
        with self.assertRaises(ValueError):
            self.storage.mutate(COMPANY, allowed.revision,
                lambda old: event_with_lines(old, 102, "bulk-102"))
        self.assertEqual(self.snapshot(), allowed)

    def test_replay_event_and_evidence_resource_limits(self):
        opening = self.seed()
        once = self.storage.mutate(COMPANY, opening.revision, lambda old: post(old))
        excess_events = replace(once,
            events=once.events * (MAX_EVENTS + 1))
        excess_evidence = replace(once,
            evidence=once.evidence * (MAX_CHART_EVIDENCE + 1))
        for candidate in (excess_events, excess_evidence):
            with self.assertRaises(ValueError):
                replay_journal(candidate)
            with self.assertRaises(ValueError):
                self.storage.commit(candidate, expected_revision=once.revision)
        self.assertEqual(self.snapshot(), once)

    def test_transaction_rollback_on_callback_and_validation_exceptions(self):
        opening = self.seed()

        def aborted(_):
            raise RuntimeError("synthetic operation aborted")

        with self.assertRaises(RuntimeError):
            self.storage.mutate(COMPANY, opening.revision, aborted)
        with self.assertRaises(ValueError):
            self.storage.mutate(COMPANY, opening.revision, lambda old: None)
        with self.assertRaises(ValueError):
            self.storage.mutate(COMPANY, opening.revision,
                lambda old: replace(old, currency="TOMAN"))
        self.assertEqual(self.snapshot(), opening)
        self.assertEqual(self.row()[0], opening.revision)
        saved = self.storage.mutate(COMPANY, opening.revision,
                                    lambda old: post(old))
        self.assertEqual(replay_journal(saved).posted_count, 1)

    def test_period_close_reversal_then_stale_period_post_refused(self):
        opening = self.seed(split=True)
        first = self.storage.mutate(COMPANY, opening.revision,
            lambda old: post(old, period="Q1", date="2026-02-10"))
        closed = self.storage.mutate(COMPANY, first.revision,
            lambda old: close_fiscal_period(old, company_id=COMPANY,
                fiscal_period_id="Q1", event_id="close-q1",
                actor_id="trusted-actor", closing_date="2026-04-01",
                expected_revision=old.revision, today=TODAY))
        with self.assertRaises(ValueError):
            self.storage.mutate(COMPANY, closed.revision,
                lambda old: post(old, event="backdate", source="invoice-2",
                                 period="Q1", date="2026-03-01"))
        reversed_state = self.storage.mutate(COMPANY, closed.revision,
            lambda old: reverse_journal(old, company_id=COMPANY,
                original_event_id="event-1", event_id="reverse-1",
                actor_id="trusted-actor", fiscal_period_id="Q2",
                posting_date="2026-04-03", reason="synthetic cancellation",
                expected_revision=old.revision, today=TODAY))
        replay = replay_journal(self.snapshot())
        self.assertEqual(replay.posted_count, 2)
        self.assertEqual(replay.closed_period_ids, frozenset({"Q1"}))
        self.assertEqual(replay.reversed_event_ids, frozenset({"event-1"}))
        self.assertEqual(len(reversed_state.events), 3)
        self.assertTrue(all(p.debit_minus_credit_rial == 0 for p in replay.positions))


if __name__ == "__main__":
    unittest.main()
