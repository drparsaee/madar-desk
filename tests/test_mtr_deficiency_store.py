"""Disposable-only E3 durability, ACL, CAS, concurrency and no-posting tests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from mtr_deficiency_store import DeficiencyStore, StoreConflict, StoreError
from mtr_deficiency_workflow import (
    Baseline, DeficiencyError, FinanceReceipt, Principal, ReviewCase,
)


T0 = datetime(2026, 11, 9, 10, tzinfo=timezone.utc)
D1 = "a" * 64
D2 = "b" * 64
REVIEW = "finance_deficiency_refer"
RESOLVE = "deficiency_resolve"
SEND = "finance_request_resubmit"


@contextmanager
def direct_db(path):
    """Explicitly close the SQLite handle before Windows temp-folder cleanup."""
    conn = sqlite3.connect(path)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def actor(user, *, role="madar_user", caps=(), org="org-1",
          projects=("project-1",), authenticated=True, active=True):
    return Principal(
        user_id=user, org_id=org, role=role,
        capabilities=frozenset(caps), projects=frozenset(projects),
        authenticated=authenticated, active=active,
    )


def baseline(revision=3, digest=D1, request="request-1", org="org-1",
             project="project-1"):
    return Baseline(request, org, project, revision, digest)


def finance():
    return actor("finance", role="taraz_finance_reviewer", caps=(REVIEW,))


def assignee():
    return actor("assignee", caps=(RESOLVE,))


def submitter():
    return actor("sender", caps=(SEND,))


def review(base=None, receipt_id="peer-metadata-7"):
    return ReviewCase(
        baseline=base or baseline(), expected_receipt_id=receipt_id,
        expected_receipt_generation=7,
        previous_receipt_ids=frozenset({"older-local-metadata"}),
        previous_send_keys=frozenset({"previous-manual-send"}),
    )


def receipt(base=None, receipt_id="peer-metadata-7", **updates):
    base = base or baseline()
    data = dict(
        receipt_id=receipt_id, request_id=base.request_id,
        org_id=base.org_id, project_id=base.project_id,
        revision=base.revision, digest=base.digest,
        generation=7, status="deficiency_required",
        source="taraz", verified_by_adapter=True, occurred_at=T0,
    )
    data.update(updates)
    return FinanceReceipt(**data)


class DurableDeficiencyStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mtr-e3-store-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "only-synthetic.sqlite3"
        self.store = DeficiencyStore(self.path)
        self.base = baseline()

    def refer(self, *, store=None, case=None, proof=None, reviewer=None,
              assignee_user=None, event_id="referral-1",
              deadline=None, reason="Missing supplier",
              missing_fields=None, occurred_at=None):
        return (store or self.store).refer(
            case or review(), proof or receipt(), reviewer=reviewer or finance(),
            assignee=assignee_user or assignee(),
            event_id=event_id, occurred_at=occurred_at or T0 + timedelta(minutes=1),
            deadline=deadline or T0 + timedelta(days=2),
            reason=reason,
            missing_fields=missing_fields or frozenset({"supplier", "units"}),
        )

    def resolve(self, *, store=None, event_id="resolution-1",
                expected_version=1, who=None, saved=None,
                corrections=None, result_note="Supplier information saved",
                occurred_at=None, base=None):
        return (store or self.store).resolve(
            baseline=base or self.base, actor=who or assignee(),
            saved_baseline=saved or baseline(4, D2),
            corrections=corrections if corrections is not None
            else {"supplier": "supplier-a", "units": "5"},
            result_note=result_note,
            event_id=event_id,
            occurred_at=occurred_at or T0 + timedelta(minutes=5),
            expected_version=expected_version,
        )

    def intent(self, *, store=None, event_id="intent-1",
               expected_version=2, who=None, explicit=True,
               revalidated=True, warning=False, send_key="new-approved-send",
               current=None, occurred_at=None, base=None):
        return (store or self.store).prepare_manual_intent(
            baseline=base or self.base,
            actor=who or submitter(), current_server_baseline=current or baseline(4, D2),
            server_revalidated=revalidated,
            explicit_manual_action=explicit, warning_acknowledged=warning,
            new_send_key=send_key,
            event_id=event_id, occurred_at=occurred_at or T0 + timedelta(minutes=6),
            expected_version=expected_version,
        )

    def test_referral_is_durable_scoped_and_contains_no_official_claims(self):
        result = self.refer()
        self.assertEqual(result["state"], "DEFICIENCY_ASSIGNED")
        self.assertEqual(result["version"], 1)
        self.assertEqual(result["assigneeId"], "assignee")
        self.assertEqual(result["reason"], "Missing supplier")
        self.assertEqual(result["missingFields"], ["supplier", "units"])
        self.assertEqual(result["events"][0]["actorId"], "finance")
        self.assertEqual(result["events"][0]["action"], "deficiency_referred")
        self.assertFalse(result["replayed"])
        self.assertFalse(result["peerVerified"])
        self.assertFalse(result["financeApprovalVerified"])
        self.assertIsNone(result["officialDocumentId"])
        self.assertFalse(result["financialEventCreated"])
        self.assertFalse(result["postingPerformed"])
        self.assertEqual(result["transportState"], "NOT_SENT_BY_THIS_MODULE")
        self.assertNotIn("receiptId", result)
        restarted = DeficiencyStore(self.path)
        self.assertEqual(restarted.read_case(
            baseline=self.base, principal=finance())["events"], result["events"])

    def test_resolved_ready_requires_separate_manual_action(self):
        self.refer()
        ready = self.resolve()
        self.assertEqual(ready["version"], 2)
        self.assertEqual(ready["state"], "CORRECTED_READY_FOR_RESUBMIT")
        self.assertIsNone(ready["sendIntentKey"])
        self.assertEqual(ready["remainingMissingFields"], [])
        self.assertFalse(ready["postingPerformed"])
        self.assertEqual(self.store.query_first_status(
            baseline=self.base, principal=assignee())["peerDeliveryState"],
            "UNKNOWN_REQUIRES_AUTHENTICATED_TARAZ_QUERY")
        self.assertFalse(self.store.query_first_status(
            baseline=self.base, principal=assignee())["newSendPermitted"])
        restarted = DeficiencyStore(self.path)
        self.assertEqual(restarted.read_case(
            baseline=self.base, principal=assignee())["version"], 2)
        self.assertEqual(len(ready["events"]), 2)

    def test_explicit_manual_resubmission_is_only_an_intent_never_transport(self):
        self.refer()
        self.resolve()
        result = self.intent()
        self.assertEqual(result["state"], "MANUAL_RESUBMISSION_INTENT_ONLY")
        self.assertEqual(result["version"], 3)
        self.assertEqual(result["sendIntentKey"], "new-approved-send")
        self.assertEqual([e["action"] for e in result["events"]], [
            "deficiency_referred", "deficiency_corrected_ready_only",
            "manual_resubmission_intent_only",
        ])
        self.assertFalse(result["financialEventCreated"])
        self.assertFalse(result["postingPerformed"])
        self.assertFalse(result["peerVerified"])
        restarted = DeficiencyStore(self.path)
        query = restarted.query_first_status(
            baseline=self.base, principal=submitter())
        self.assertEqual(query["peerDeliveryState"],
                         "UNKNOWN_REQUIRES_AUTHENTICATED_TARAZ_QUERY")
        self.assertFalse(query["newSendPermitted"])
        self.assertFalse(query["postingPerformed"])
        self.assertIsNone(query["officialDocumentId"])

    def test_replay_identical_referral_does_not_duplicate_audit(self):
        first = self.refer()
        second = self.refer()
        self.assertTrue(second["replayed"])
        self.assertEqual(second["version"], first["version"])
        self.assertEqual(len(second["events"]), 1)
        with direct_db(self.path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0], 1)

    def test_double_referral_with_new_event_does_not_reassign(self):
        self.refer()
        with self.assertRaises(StoreConflict):
            self.refer(event_id="referral-2",
                       assignee_user=actor("other", caps=(RESOLVE,)))
        with self.assertRaises(StoreConflict):
            self.refer(event_id="referral-2")

    def test_cross_case_receipt_or_event_id_uniqueness(self):
        self.refer()
        new_base = baseline(3, D2, request="request-2")
        with self.assertRaises(StoreConflict):
            self.refer(case=review(new_base), proof=receipt(new_base),
                       event_id="referral-2")
        with self.assertRaises(StoreConflict):
            self.refer(case=review(new_base, receipt_id="peer-metadata-8"),
                       proof=receipt(new_base, receipt_id="peer-metadata-8"),
                       event_id="referral-1")
        self.assertEqual(self.store.read_case(
            baseline=self.base, principal=finance())["version"], 1)

    def test_send_key_cannot_be_reused_between_two_scoped_cases(self):
        self.refer()
        self.resolve()
        self.intent()
        other = baseline(3, D2, request="request-2")
        self.refer(
            case=review(other, receipt_id="peer-metadata-8"),
            proof=receipt(other, receipt_id="peer-metadata-8"),
            event_id="referral-2",
        )
        self.resolve(
            base=other, saved=baseline(4, D1, request="request-2"),
            event_id="resolution-2",
        )
        with self.assertRaises(StoreConflict):
            self.intent(
                base=other, current=baseline(4, D1, request="request-2"),
                event_id="intent-2", send_key="new-approved-send",
            )
        self.assertEqual(
            self.store.read_case(baseline=other, principal=finance())["version"], 2
        )

    def test_same_event_id_changed_referral_payload_fails_closed(self):
        self.refer()
        for kwargs in (
            {"reason": "Different reason"},
            {"deadline": T0 + timedelta(days=3)},
            {"missing_fields": frozenset({"only-one"})},
            {"assignee_user": actor("someone-else", caps=(RESOLVE,))},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(StoreConflict):
                self.refer(**kwargs)

    def test_exact_resolution_replay_is_idempotent_after_restart(self):
        self.refer()
        first = self.resolve()
        same = self.resolve(store=DeficiencyStore(self.path))
        self.assertTrue(same["replayed"])
        self.assertEqual(first["version"], same["version"])
        self.assertEqual(len(same["events"]), 2)
        with self.assertRaises(StoreConflict):
            self.resolve(corrections={"supplier": "different"},
                         expected_version=1)

    def test_exact_manual_intent_replay_and_send_key_conflict(self):
        self.refer()
        self.resolve()
        first = self.intent()
        second = self.intent(store=DeficiencyStore(self.path))
        self.assertEqual(first["version"], second["version"])
        self.assertTrue(second["replayed"])
        with self.assertRaises(StoreConflict):
            self.intent(event_id="intent-new", send_key="new-approved-send")
        with self.assertRaises(StoreConflict):
            self.intent(event_id="intent-1", send_key="different-send-key")
        with self.assertRaises(StoreConflict):
            self.intent(event_id="intent-new", expected_version=2)

    def test_finance_only_reviewer_and_assignee_permissions(self):
        with self.assertRaises(PermissionError):
            self.refer(reviewer=actor("user", caps=(REVIEW,)))
        with self.assertRaises(PermissionError):
            self.refer(reviewer=actor("finance", role="taraz_finance_reviewer",
                                      caps=(REVIEW,), authenticated=False))
        with self.assertRaises(PermissionError):
            self.refer(assignee_user=actor("assignee", caps=()))
        with self.assertRaises(PermissionError):
            self.refer(assignee_user=actor("assignee", caps=(RESOLVE,),
                                           org="other-org"))
        with direct_db(self.path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0], 0)

    def test_stale_unverified_mismatched_and_corrupt_receipts_denied(self):
        for changed in (
            {"verified_by_adapter": False},
            {"source": "unknown"}, {"status": "finance_approved"},
            {"generation": 6}, {"generation": 8},
            {"digest": D2}, {"revision": 2},
            {"project_id": "other-project"}, {"org_id": "other-org"},
            {"request_id": "other-request"},
            {"receipt_id": "unexpected"},
        ):
            with self.subTest(changed=changed), self.assertRaises(
                (DeficiencyError, ValueError)
            ):
                self.refer(proof=receipt(**changed))
        with direct_db(self.path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0], 0)

    def test_cross_tenant_and_cross_project_reads_do_not_leak_case(self):
        self.refer()
        for person in (
            actor("finance", role="taraz_finance_reviewer", caps=(REVIEW,),
                  org="other-org"),
            actor("finance", role="taraz_finance_reviewer", caps=(REVIEW,),
                  projects=("project-other",)),
            actor("assignee", caps=(RESOLVE,), authenticated=False),
            actor("assignee", caps=(RESOLVE,), active=False),
            actor("stranger", caps=()),
            actor("stranger", caps=(RESOLVE,)),
        ):
            with self.subTest(person=person), self.assertRaises(PermissionError):
                self.store.read_case(baseline=self.base, principal=person)
        with self.assertRaises(PermissionError):
            self.store.query_first_status(
                baseline=self.base, principal=actor("other", caps=(SEND,),
                                                      org="other-org"))

    def test_other_user_cannot_resolve_and_unauthenticated_sender_denied(self):
        self.refer()
        with self.assertRaises(PermissionError):
            self.resolve(who=actor("different", caps=(RESOLVE,)))
        with self.assertRaises(PermissionError):
            self.resolve(who=actor("assignee", caps=(RESOLVE,),
                                   authenticated=False))
        self.resolve()
        for who in (
            actor("sender", caps=(SEND,), authenticated=False),
            actor("sender", caps=(SEND,), org="other-org"),
            actor("sender", caps=(SEND,), projects=("other",)),
            actor("sender", caps=()),
        ):
            with self.subTest(who=who), self.assertRaises(PermissionError):
                self.intent(who=who)

    def test_resolution_requires_server_saved_new_revision_and_corrected_field(self):
        self.refer()
        for updates in (
            {"saved": baseline(3, D2)},
            {"saved": baseline(4, D1)},
            {"saved": baseline(4, D2, org="other-org")},
            {"corrections": {"unrelated": "value"}},
            {"corrections": {}},
            {"result_note": ""},
        ):
            with self.subTest(updates=updates), self.assertRaises(DeficiencyError):
                self.resolve(**updates)
        self.assertEqual(self.store.read_case(
            baseline=self.base, principal=assignee())["version"], 1)

    def test_partial_correction_requires_explicit_incomplete_warning(self):
        self.refer()
        partial = self.resolve(corrections={"supplier": "fixed"})
        self.assertEqual(partial["remainingMissingFields"], ["units"])
        with self.assertRaises(DeficiencyError):
            self.intent(warning=False)
        with self.assertRaises(DeficiencyError):
            self.intent(warning=1)
        accepted = self.intent(warning=True)
        self.assertEqual(accepted["state"], "MANUAL_RESUBMISSION_INTENT_ONLY")
        self.assertFalse(accepted["postingPerformed"])

    def test_manual_action_and_fresh_server_check_are_mandatory(self):
        self.refer()
        self.resolve()
        for updates in (
            {"explicit": False}, {"explicit": 1}, {"revalidated": False},
            {"revalidated": 1}, {"current": baseline(5, D2)},
            {"current": baseline(4, D1)},
            {"send_key": "previous-manual-send"},
        ):
            with self.subTest(updates=updates), self.assertRaises(
                (PermissionError, DeficiencyError)
            ):
                self.intent(**updates)
        self.assertEqual(self.store.read_case(
            baseline=self.base, principal=assignee())["version"], 2)

    def test_stale_compare_and_swap_version_blocks_lost_updates(self):
        self.refer()
        with self.assertRaises(StoreConflict):
            self.resolve(expected_version=2)
        self.resolve()
        with self.assertRaises(StoreConflict):
            self.intent(expected_version=1)
        self.assertEqual(self.store.read_case(
            baseline=self.base, principal=assignee())["version"], 2)

    def test_racing_identical_referrals_one_write_one_replay(self):
        gate = threading.Barrier(2)
        def runner():
            gate.wait()
            return self.refer(store=DeficiencyStore(self.path))
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(runner), pool.submit(runner)
            results = (a.result(timeout=10), b.result(timeout=10))
        self.assertEqual(sorted(x["replayed"] for x in results), [False, True])
        with direct_db(self.path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], 1)

    def test_racing_different_referrals_same_case_one_rejected(self):
        gate = threading.Barrier(2)
        def runner(event):
            gate.wait()
            try:
                return ("ok", self.refer(store=DeficiencyStore(self.path),
                                          event_id=event))
            except StoreConflict:
                return ("conflict", None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(runner, "evt-a")
            b = pool.submit(runner, "evt-b")
            results = (a.result(timeout=10), b.result(timeout=10))
        self.assertEqual(sorted(x[0] for x in results), ["conflict", "ok"])

    def test_racing_resolutions_one_cas_wins_and_history_is_atomic(self):
        self.refer()
        gate = threading.Barrier(2)
        def runner(event, value):
            gate.wait()
            try:
                return ("ok", self.resolve(store=DeficiencyStore(self.path),
                                            event_id=event,
                                            corrections={"supplier": value}))
            except StoreConflict:
                return ("conflict", None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(runner, "resolve-a", "supplier-a")
            b = pool.submit(runner, "resolve-b", "supplier-b")
            results = (a.result(timeout=10), b.result(timeout=10))
        self.assertEqual(sorted(x[0] for x in results), ["conflict", "ok"])
        actual = self.store.read_case(baseline=self.base, principal=assignee())
        self.assertEqual(actual["version"], 2)
        self.assertEqual(len(actual["events"]), 2)

    def test_stored_audit_cannot_be_updated_or_deleted_through_sqlite(self):
        self.refer()
        with direct_db(self.path) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE audit_events SET action='tampered'")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM audit_events")
        self.assertEqual(self.store.read_case(
            baseline=self.base, principal=finance())["events"][0]["action"],
            "deficiency_referred")

    def test_corrupt_metadata_fails_closed_without_adding_events(self):
        self.refer()
        with direct_db(self.path) as conn:
            conn.execute("UPDATE cases SET snapshot='{}'")
        with self.assertRaises(StoreError):
            self.store.read_case(baseline=self.base, principal=finance())
        with self.assertRaises(StoreError):
            self.resolve()
        with direct_db(self.path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], 1)

    def test_corrupt_audit_mismatch_detected_on_read(self):
        self.refer()
        with direct_db(self.path) as conn:
            # A direct SQLite administrator can drop audit triggers and alter
            # metadata. That is outside the assumed trusted OS/DB boundary.
            conn.execute("DROP TRIGGER mtr_audit_no_update")
            conn.execute("UPDATE audit_events SET event_json='{}'")
        with self.assertRaises(StoreError):
            self.store.read_case(baseline=self.base, principal=finance())

    def test_failed_audit_insert_rolls_back_case_state_update_atomically(self):
        self.refer()
        with direct_db(self.path) as conn:
            conn.execute("""
                CREATE TRIGGER synthetic_fail_audit_insert
                BEFORE INSERT ON audit_events
                BEGIN SELECT RAISE(ABORT, 'synthetic crash at audit insert'); END
            """)
        with self.assertRaises(StoreConflict):
            self.resolve()
        with direct_db(self.path) as conn:
            conn.execute("DROP TRIGGER synthetic_fail_audit_insert")
        state = self.store.read_case(baseline=self.base, principal=finance())
        self.assertEqual(state["state"], "DEFICIENCY_ASSIGNED")
        self.assertEqual(state["version"], 1)
        self.assertEqual(len(state["events"]), 1)
        self.assertEqual(self.resolve()["version"], 2)

    def test_foreign_unversioned_database_is_not_adopted(self):
        foreign = Path(self.temporary.name) / "foreign.sqlite3"
        with direct_db(foreign) as conn:
            conn.execute("CREATE TABLE official_accounting (secret TEXT)")
            conn.execute("INSERT INTO official_accounting VALUES ('synthetic')")
        with self.assertRaises(StoreError):
            DeficiencyStore(foreign)
        with direct_db(foreign) as conn:
            self.assertEqual(conn.execute(
                "SELECT secret FROM official_accounting"
            ).fetchone()[0], "synthetic")
            self.assertEqual(
                conn.execute("SELECT name FROM sqlite_master WHERE name='cases'").fetchall(),
                [],
            )

    def test_untrusted_path_symlink_and_wrong_version_rejected(self):
        with self.assertRaises(StoreError):
            DeficiencyStore(Path("relative.sqlite3"))
        with self.assertRaises(StoreError):
            DeficiencyStore(Path(self.temporary.name) / "bad.txt")
        link = Path(self.temporary.name) / "linked.sqlite3"
        try:
            link.symlink_to(self.path)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaises(StoreError):
                DeficiencyStore(link)
        with direct_db(self.path) as conn:
            conn.execute("PRAGMA user_version=999")
        with self.assertRaises(StoreError):
            DeficiencyStore(self.path)

    def test_deleted_request_and_unrelated_org_fail_closed(self):
        self.refer()
        with self.assertRaises(StoreError):
            self.store.read_case(
                baseline=baseline(request="unknown"),
                principal=finance())
        with self.assertRaises(PermissionError):
            self.store.read_case(
                baseline=baseline(org="different"),
                principal=finance())


if __name__ == "__main__":
    unittest.main()
