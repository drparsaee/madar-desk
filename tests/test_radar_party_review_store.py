"""Synthetic-only E4 durable human decision tests, disposable Windows SQLite."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from radar_party_match_preview import preview_party_matches
from radar_party_review_store import (
    HostPrincipal, PartyReviewStore, ReviewConflict, ReviewStoreError,
    _json,
)

T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
ORG = "synthetic-org"
PROJECT = "synthetic-project"
REVIEW = "review-1"
READ = "party_match_read"
DECIDE = "party_match_decide"
FIELDS = ("official_id", "name", "phone", "address")


def principal(user="finance", *, org=ORG, project=PROJECT,
              role="taraz_finance_reviewer", session="session-1",
              caps=(READ, DECIDE), fields=FIELDS, candidate_ids=None,
              authenticated=True, active=True):
    return HostPrincipal(
        user_id=user, organization_id=org, session_id=session, role=role,
        project_grants=frozenset({project}),
        capabilities=frozenset(caps),
        visible_fields=frozenset(fields),
        allowed_candidate_ids=frozenset(
            candidate_ids if candidate_ids is not None else
            ("party-equal", "party-conflicting-id", "party-unrelated",
             "party-private")),
        authenticated=authenticated, active=active,
    )


CUSTOMER = {
    "organization_id": ORG, "customer_id": "temporary-7",
    "official_id": "۰۰۱۲۳", "official_id_source_verified": True,
    "name": "شرکت آفتاب گستر", "phone": "۰۹۱۲ ۳۴۵-۶۷۸۹",
    "address": "تهران خیابان بهار",
}


def candidate(party_id, **extra):
    return {
        "organization_id": ORG,
        "party_id": party_id,
        "read_authorized": True,
        **extra,
    }


CANDIDATES = [
    candidate("party-equal", official_id="00123",
              official_id_source_verified=True, name="شرکت آفتاب گستر",
              phone="0912 (345) 6789", address="تهران خیابان بهار"),
    candidate("party-conflicting-id", official_id="00999",
              official_id_source_verified=True, name="شرکت آفتاب گستر"),
    candidate("party-unrelated", name="نام دیگر", phone="021000000"),
]


@contextmanager
def direct_db(path):
    """Close Windows SQLite connections before TemporaryDirectory cleanup."""
    conn = sqlite3.connect(path)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


class PartyReviewStoreTests(unittest.TestCase):
    def setUp(self):
        sandbox = tempfile.TemporaryDirectory(prefix="mtr-e4-review-synthetic-")
        self.addCleanup(sandbox.cleanup)
        self.db = Path(sandbox.name) / "synthetic-party-review.sqlite3"
        self.store = PartyReviewStore(self.db)

    def preview(self, *, candidates=None, customer=None, visible=FIELDS):
        return preview_party_matches(
            CUSTOMER if customer is None else customer,
            CANDIDATES if candidates is None else candidates,
            scope={
                "organization_id": ORG, "server_scoped": True,
                "party_read_authorized": True,
                "finance_review_authorized": True,
                "visible_fields": visible,
            },
        )

    def digest(self, **kwargs):
        output = self.preview(**kwargs)
        return hashlib.sha256(_json(output).encode("utf-8")).hexdigest()

    def open(self, *, store=None, reviewer=None, review_id=REVIEW,
             project_id=PROJECT, customer=None, candidates=None, visible=FIELDS,
             allowed=None, source="synthetic-source-1", revision=7,
             expected_digest=None, bound=True, event_id="open-1",
             when=T0):
        candidates = list(CANDIDATES if candidates is None else candidates)
        actual_customer = CUSTOMER if customer is None else customer
        return (store or self.store).open_pending(
            principal=reviewer or principal(), project_id=project_id,
            review_id=review_id, temporary_customer=actual_customer,
            candidate_records=candidates, visible_fields=visible,
            authorized_candidate_ids=allowed if allowed is not None else tuple(
                row["party_id"] for row in candidates),
            source_ref=source, source_revision=revision,
            expected_source_digest=(
                expected_digest if expected_digest is not None else
                self.digest(candidates=candidates, customer=actual_customer, visible=visible)
            ),
            source_binding_host_confirmed=bound, event_id=event_id,
            occurred_at=when,
        )

    def decide(self, *, store=None, reviewer=None, review_id=REVIEW,
               project_id=PROJECT, action="select_candidate",
               selected=None, version=1, digest=None,
               source_digest=None, source="synthetic-source-1",
               revision=7, bound=True,
               acknowledge=False, event_id="decision-1",
               when=T0 + timedelta(minutes=1), note=None):
        if action == "select_candidate" and selected is None:
            selected = "party-equal"
        return (store or self.store).record_decision(
            principal=reviewer or principal(),
            project_id=project_id, review_id=review_id,
            action=action, candidate_id=selected,
            expected_version=version,
            expected_snapshot_sha256=digest or self.digest(),
            current_source_digest=source_digest or self.digest(),
            current_source_ref=source,
            current_source_revision=revision,
            source_binding_host_confirmed=bound,
            acknowledge_conflicts=acknowledge,
            event_id=event_id, occurred_at=when, note=note,
        )

    def read(self, *, store=None, reviewer=None, review_id=REVIEW, project_id=PROJECT):
        return (store or self.store).read_review(
            principal=reviewer or principal(), project_id=project_id,
            review_id=review_id,
        )

    def test_open_pending_preserves_every_candidate_and_conflict_explanation(self):
        state = self.open()
        self.assertEqual(state["state"], "PENDING_HUMAN_REVIEW")
        self.assertEqual(state["version"], 1)
        self.assertEqual(state["authorizedCandidateIds"], [
            "party-equal", "party-conflicting-id", "party-unrelated",
        ])
        self.assertEqual(state["preview"]["candidate_count"], 3)
        self.assertEqual(
            state["preview"]["candidates"][1]["conflicts"],
            ["conflicting_upstream_claimed_verified_official_ids"],
        )
        self.assertEqual(state["preview"]["candidates"][2]["fields"]["name"]["comparison"],
                         "different")
        self.assertIsNone(state["decision"])
        self.assertFalse(state["officialTarazPartyCreated"])
        self.assertFalse(state["officialPartyLinked"])
        self.assertFalse(state["officialPartyUpdated"])
        self.assertFalse(state["automaticMergePerformed"])
        self.assertFalse(state["networkUsed"])
        self.assertFalse(state["sourceAuthenticityVerifiedByThisModule"])

    def test_restart_readback_and_query_only_pending_does_not_modify(self):
        first = self.open()
        store = PartyReviewStore(self.db)
        pending = store.list_pending(principal=principal(), project_id=PROJECT)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["candidateCount"], 3)
        self.assertEqual(pending[0]["reviewId"], REVIEW)
        restored = self.read(store=store)
        self.assertEqual(restored["preview"], first["preview"])
        self.assertEqual(restored["version"], 1)
        self.assertEqual(self.read()["version"], 1)
        with direct_db(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 1)

    def test_explicit_human_selection_records_actor_session_time_and_audit(self):
        self.open()
        selected = self.decide(note="")
        self.assertEqual(selected["state"], "DECISION_RECORDED")
        self.assertEqual(selected["version"], 2)
        self.assertEqual(selected["decision"], {
            "action": "select_candidate",
            "selectedCandidateId": "party-equal",
            "actorId": "finance",
            "sessionId": "session-1",
            "occurredUtc": "2026-11-09T12:01:00Z",
        })
        self.assertEqual([entry["action"] for entry in selected["audit"]],
                         ["review_opened", "human_decision_recorded"])
        self.assertEqual(self.store.list_pending(
            principal=principal(), project_id=PROJECT), [])
        reopened = self.read(store=PartyReviewStore(self.db))
        self.assertEqual(reopened["decision"], selected["decision"])
        self.assertFalse(reopened["officialPartyLinked"])

    def test_explicit_rejection_never_attaches_a_party(self):
        self.open()
        result = self.decide(action="reject_all", selected=None)
        self.assertEqual(result["decision"]["action"], "reject_all")
        self.assertIsNone(result["decision"]["selectedCandidateId"])
        self.assertFalse(result["officialPartyLinked"])
        self.assertFalse(result["officialTarazPartyCreated"])

    def test_conflicting_claims_remain_visible_and_require_acknowledgement(self):
        self.open()
        with self.assertRaises(ReviewConflict):
            self.decide(selected="party-conflicting-id", acknowledge=False)
        self.assertEqual(self.read()["state"], "PENDING_HUMAN_REVIEW")
        result = self.decide(selected="party-conflicting-id", acknowledge=True)
        self.assertEqual(result["decision"]["selectedCandidateId"],
                         "party-conflicting-id")
        self.assertEqual(result["preview"]["candidates"][1]["conflicts"],
                         ["conflicting_upstream_claimed_verified_official_ids"])
        self.assertFalse(result["officialPartyLinked"])

    def test_no_decision_when_source_binding_not_confirmed(self):
        self.open(bound=False)
        pending = self.read()
        self.assertFalse(pending["sourceBindingHostAsserted"])
        with self.assertRaises(PermissionError):
            self.decide(bound=False)
        with self.assertRaises(PermissionError):
            self.decide(bound=True)
        self.assertEqual(self.read()["version"], 1)

    def test_wrong_candidate_cross_org_and_project_denied(self):
        self.open()
        with self.assertRaises(PermissionError):
            self.decide(selected="invented-party")
        with self.assertRaises((PermissionError, ReviewStoreError)):
            self.decide(reviewer=principal(org="other-org"))
        with self.assertRaises((PermissionError, ReviewStoreError)):
            self.read(reviewer=principal(org="other-org"))
        with self.assertRaises(PermissionError):
            self.read(reviewer=principal(project="other-project"))
        with self.assertRaises(PermissionError):
            self.decide(project_id="other-project")
        self.assertEqual(
            self.store.list_pending(principal=principal(org="other-org"),
                                    project_id=PROJECT), [],
        )
        self.assertEqual(self.read()["state"], "PENDING_HUMAN_REVIEW")

    def test_client_flags_and_ambiguous_permission_fail_closed(self):
        for p in (
            principal(authenticated=False),
            principal(active=False),
            principal(role="madar_user"),
            principal(caps=(READ,)),
            principal(caps=(DECIDE,)),
            principal(project="other-project"),
        ):
            with self.subTest(p=p), self.assertRaises(PermissionError):
                self.open(reviewer=p)
        self.open()
        for p in (
            principal(authenticated=False), principal(active=False),
            principal(role="madar_user"), principal(caps=(READ,)),
        ):
            with self.subTest(p=p), self.assertRaises(PermissionError):
                self.decide(reviewer=p)

    def test_revoked_field_or_candidate_grant_blocks_read_and_decision(self):
        self.open()
        for current in (
            principal(fields=("name",)),
            principal(candidate_ids=("party-equal", "party-unrelated")),
        ):
            with self.subTest(current=current), self.assertRaises(PermissionError):
                self.read(reviewer=current)
            with self.subTest(current=current), self.assertRaises(PermissionError):
                self.decide(reviewer=current)
            self.assertEqual(
                self.store.list_pending(principal=current, project_id=PROJECT), [],
            )
        self.assertEqual(self.read()["state"], "PENDING_HUMAN_REVIEW")

    def test_open_requires_current_host_field_and_candidate_grants(self):
        with self.assertRaises(PermissionError):
            self.open(reviewer=principal(fields=("name",)))
        with self.assertRaises(PermissionError):
            self.open(reviewer=principal(
                candidate_ids=("party-equal", "party-unrelated")))

    def test_missing_visible_fields_or_unauthorized_candidate_is_rejected(self):
        with self.assertRaises((PermissionError, ReviewStoreError)):
            self.open(visible=())
        with self.assertRaises(PermissionError):
            self.open(candidates=[
                CANDIDATES[0],
                {**CANDIDATES[1], "organization_id": "other-tenant"},
            ])
        with self.assertRaises(PermissionError):
            self.open(candidates=[
                {**CANDIDATES[0], "read_authorized": False},
            ])
        with self.assertRaises(ReviewStoreError):
            self.open(allowed=("party-equal", "party-unrelated", "party-conflicting-id"))
        with self.assertRaises(ReviewStoreError):
            self.open(allowed=("party-equal", "party-equal", "party-unrelated"))
        with self.assertRaises(ReviewStoreError):
            self.open(allowed=("party-equal",))
        self.assertEqual(self.store.list_pending(
            principal=principal(), project_id=PROJECT), [])

    def test_field_acl_redacts_unpermitted_values_even_from_stored_snapshot(self):
        candidates = [candidate("party-private", name="hello",
                                phone="SENSITIVE-PHONE-123",
                                address="SENSITIVE-ADDRESS-456",
                                official_id="SENSITIVE-ID-789")]
        result = self.open(candidates=candidates, visible=("name",))
        raw = repr(result)
        for marker in ("SENSITIVE-PHONE", "SENSITIVE-ADDRESS", "SENSITIVE-ID"):
            self.assertNotIn(marker, raw)
        for field in ("official_id", "phone", "address"):
            self.assertEqual(
                result["preview"]["candidates"][0]["fields"][field],
                {"comparison": "not_authorized"})
        with direct_db(self.db) as conn:
            stored = conn.execute("SELECT snapshot_json FROM reviews").fetchone()[0]
            self.assertNotIn("SENSITIVE-PHONE", stored)
            self.assertNotIn("SENSITIVE-ADDRESS", stored)
            self.assertNotIn("SENSITIVE-ID", stored)

    def test_source_digest_and_revision_staleness_rejected(self):
        with self.assertRaises(ReviewConflict):
            self.open(expected_digest="0" * 64)
        self.open()
        for arguments in (
            {"source_digest": "0" * 64},
            {"digest": "0" * 64},
            {"source": "different-source"},
            {"revision": 8},
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ReviewConflict):
                self.decide(**arguments)
        self.assertEqual(self.read()["state"], "PENDING_HUMAN_REVIEW")

    def test_no_untrusted_auto_merge_or_create_action_is_allowed(self):
        self.open()
        for action in ("auto_merge", "official_create", "link_taraz_party", "approve"):
            with self.subTest(action=action), self.assertRaises(ReviewStoreError):
                self.decide(action=action)
        with self.assertRaises(ReviewStoreError):
            self.decide(action="reject_all", selected="party-equal")
        self.assertEqual(self.read()["version"], 1)

    def test_idempotent_open_and_changed_open_event_conflict(self):
        first = self.open()
        second = self.open(store=PartyReviewStore(self.db))
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(second["version"], 1)
        with self.assertRaises(ReviewConflict):
            self.open(event_id="open-2")
        with self.assertRaises(ReviewConflict):
            self.open(source="changed-source")
        with direct_db(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 1)

    def test_idempotent_decision_and_conflicting_event_or_second_decision(self):
        self.open()
        self.decide()
        replay = self.decide(store=PartyReviewStore(self.db))
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["version"], 2)
        with self.assertRaises(ReviewConflict):
            self.decide(selected="party-unrelated")
        with self.assertRaises(ReviewConflict):
            self.decide(event_id="different-decision")
        with direct_db(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 2)

    def test_same_event_id_cannot_be_used_on_another_review(self):
        self.open()
        with self.assertRaises(ReviewConflict):
            self.open(review_id="review-2", event_id="open-1")
        self.open(review_id="review-2", event_id="open-2")
        with self.assertRaises(ReviewConflict):
            self.decide(review_id="review-2", event_id="open-1")
        self.assertEqual(self.read(review_id="review-2")["version"], 1)

    def test_identical_concurrent_open_one_create_one_replay(self):
        gate = threading.Barrier(2)
        def run():
            gate.wait()
            return self.open(store=PartyReviewStore(self.db))
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(run), pool.submit(run)
            outcomes = [a.result(timeout=10), b.result(timeout=10)]
        self.assertEqual(sorted(x["replayed"] for x in outcomes), [False, True])
        self.assertEqual(len(self.store.list_pending(
            principal=principal(), project_id=PROJECT)), 1)

    def test_different_concurrent_decisions_only_one_wins(self):
        self.open()
        gate = threading.Barrier(2)
        def run(event, selected):
            gate.wait()
            try:
                return ("saved", self.decide(
                    store=PartyReviewStore(self.db), event_id=event,
                    selected=selected))
            except ReviewConflict:
                return ("conflict", None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(run, "decide-a", "party-equal")
            b = pool.submit(run, "decide-b", "party-unrelated")
            outcomes = [a.result(timeout=10), b.result(timeout=10)]
        self.assertEqual(sorted(x[0] for x in outcomes), ["conflict", "saved"])
        self.assertEqual(self.read()["version"], 2)
        with direct_db(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 2)

    def test_audit_immutable_sqlite_triggers(self):
        self.open()
        self.decide()
        with direct_db(self.db) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE audit SET action='tampered'")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM audit")
        self.assertEqual(len(self.read()["audit"]), 2)

    def test_failed_audit_write_rolls_back_decision_atomically(self):
        self.open()
        with direct_db(self.db) as conn:
            conn.execute("""
                CREATE TRIGGER synthetic_abort_second_event
                BEFORE INSERT ON audit WHEN NEW.seq=2
                BEGIN SELECT RAISE(ABORT,'synthetic audit insert failure'); END;
            """)
        with self.assertRaises(ReviewConflict):
            self.decide()
        with direct_db(self.db) as conn:
            conn.execute("DROP TRIGGER synthetic_abort_second_event")
        unchanged = self.read()
        self.assertEqual(unchanged["state"], "PENDING_HUMAN_REVIEW")
        self.assertEqual(unchanged["version"], 1)
        self.assertEqual(len(unchanged["audit"]), 1)
        self.assertEqual(self.decide()["version"], 2)

    def test_changed_candidate_digest_even_same_candidate_ids_is_rejected(self):
        self.open()
        alternate = list(CANDIDATES)
        alternate[0] = {**alternate[0], "name": "A different synthetic name"}
        changed_digest = self.digest(candidates=alternate)
        self.assertNotEqual(changed_digest, self.digest())
        with self.assertRaises(ReviewConflict):
            self.decide(source_digest=changed_digest)
        self.assertEqual(self.read()["state"], "PENDING_HUMAN_REVIEW")

    def test_audit_decision_row_tampering_is_detected(self):
        self.open()
        self.decide()
        with direct_db(self.db) as conn:
            conn.execute(
                "UPDATE reviews SET decision_action='reject_all', "
                "decision_candidate=NULL"
            )
        with self.assertRaises(ReviewStoreError):
            self.read()

    def test_broken_snapshot_hash_and_audit_rows_fail_closed(self):
        self.open()
        with direct_db(self.db) as conn:
            conn.execute("UPDATE reviews SET snapshot_sha='0'")
        with self.assertRaises(ReviewStoreError):
            self.read()
        with self.assertRaises(ReviewStoreError):
            self.decide()

    def test_corrupted_decision_rejected_without_false_official_link(self):
        self.open()
        self.decide()
        with direct_db(self.db) as conn:
            conn.execute("UPDATE reviews SET decision_candidate='foreign-party'")
        with self.assertRaises(ReviewStoreError):
            self.read()

    def test_unversioned_foreign_database_never_adopted(self):
        path = self.db.parent / "foreign.sqlite3"
        with direct_db(path) as conn:
            conn.execute("CREATE TABLE accounting (data TEXT)")
            conn.execute("INSERT INTO accounting VALUES ('synthetic')")
        with self.assertRaises(ReviewStoreError):
            PartyReviewStore(path)
        with direct_db(path) as conn:
            self.assertEqual(
                conn.execute("SELECT data FROM accounting").fetchone()[0],
                "synthetic",
            )

    def test_relative_path_wrong_extension_and_symlink_rejected(self):
        with self.assertRaises(ReviewStoreError):
            PartyReviewStore(Path("relative.sqlite3"))
        with self.assertRaises(ReviewStoreError):
            PartyReviewStore(self.db.parent / "wrong.txt")
        linked = self.db.parent / "alias.sqlite3"
        try:
            linked.symlink_to(self.db)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaises(ReviewStoreError):
                PartyReviewStore(linked)

    def test_candidate_limit_and_empty_list_cannot_implicitly_select(self):
        with self.assertRaises(ReviewStoreError):
            self.open(candidates=[], allowed=())
        many = [candidate(f"party-{i}") for i in range(65)]
        with self.assertRaises(ReviewStoreError):
            self.open(candidates=many)

    def test_pending_query_bounded_and_requires_authenticated_finance_reader(self):
        self.open()
        with self.assertRaises(ReviewStoreError):
            self.store.list_pending(principal=principal(), project_id=PROJECT, limit=0)
        with self.assertRaises(ReviewStoreError):
            self.store.list_pending(principal=principal(), project_id=PROJECT, limit=1000)
        with self.assertRaises(PermissionError):
            self.store.list_pending(principal=principal(caps=(DECIDE,)),
                                    project_id=PROJECT)


if __name__ == "__main__":
    unittest.main()
