"""Offline E5 amendment store tests: synthetic temp SQLite, no peer or ledger."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import multiprocessing
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mtr_amendment_store import (
    AmendmentStore, AmendmentStoreError, AmendmentConflict, TrustedPrincipal,
)
from mtr_amendment_review_preview import AmendmentPreviewError


T0 = "2026-11-09T15:00:00Z"
T1 = "2026-11-09T15:01:00Z"
T2 = "2026-11-09T15:02:00Z"


def principal(**updates):
    value = dict(
        user_id="editor-a", org_id="org-a", session_id="session-a",
        role="editor", project_ids=frozenset({"project-1"}),
        permissions=frozenset({
            "mtr.amendment.create", "mtr.amendment.review",
            "mtr.amendment.read", "mtr.amendment.send",
        }),
        authenticated=True, session_valid=True, active=True,
    )
    value.update(updates)
    return TrustedPrincipal(**value)


def adapter(**updates):
    value = dict(
        user_id="bridge", org_id="org-a", session_id="bridge-session",
        role="taraz_adapter", project_ids=frozenset({"project-1"}),
        permissions=frozenset({"mtr.amendment.rejection"}),
        authenticated=True, session_valid=True, active=True,
    )
    value.update(updates)
    return TrustedPrincipal(**value)


def _child_create(path, original, queue):
    """Cross-process test entrypoint with synthetic-only inputs."""
    try:
        store = AmendmentStore(Path(path))
        result = store.create_amendment(
            principal=principal(), original=original,
            amendment_id="amendment-first",
            proposed_fields={"partyId": "new"},
            create_key="create-key-0001",
            acknowledged_open=False, acknowledged_duplicate=False,
            acknowledged_at=T0,
        )
        queue.put("replay" if result["idempotent"] else "created")
    except Exception as exc:
        queue.put(type(exc).__name__ + ":" + str(exc))


class E5StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mtr-e5-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "amendment.sqlite3"
        self.store = AmendmentStore(self.path)
        self.user = principal()
        self.original = {
            "requestId": "request-original", "orgId": "org-a",
            "projectId": "project-1", "submitted": True,
            "revision": "rev-1",
            "fields": {"partyId": "old", "quantity": 2, "notes": "original"},
        }

    def create(self, **updates):
        args = dict(
            principal=self.user, original=self.original,
            amendment_id="amendment-first", proposed_fields={"partyId": "new"},
            create_key="create-key-0001",
            acknowledged_open=False, acknowledged_duplicate=False,
            acknowledged_at=T0,
        )
        args.update(updates)
        return self.store.create_amendment(**args)

    def choose(self, **updates):
        args = dict(
            principal=self.user, amendment_id="amendment-second",
            expected_row_revision=1, chosen_values={"partyId": "resolved"},
            operation_key="choice-key-0001", occurred_at=T1,
        )
        args.update(updates)
        return self.store.choose_fields(**args)

    def send(self, **updates):
        args = dict(
            principal=self.user, amendment_id="amendment-first",
            expected_row_revision=1, current_original=self.original,
            send_key="send-key-0001", explicit_manual_action=True,
            current_server_verified=True, occurred_at=T1,
        )
        args.update(updates)
        return self.store.manual_send_intent(**args)

    def receipt(self, **updates):
        data = {
            "amendmentId": "amendment-first",
            "originalRequestId": "request-original",
            "orgId": "org-a", "projectId": "project-1",
            "status": "rejected", "verifiedTarazSource": True,
            "reason": {"text": "Wrong counterparty", "affectedFields": ["partyId"],
                       "structured": True},
        }
        data.update(updates)
        return data

    def reject(self, **updates):
        args = dict(
            adapter=adapter(), amendment_id="amendment-first",
            expected_row_revision=2, observation_id="receipt-event-01",
            receipt=self.receipt(), verified_by_adapter=True,
            occurred_at=T2,
        )
        args.update(updates)
        return self.store.record_rejection(**args)

    def seed_historical_rejection(self):
        """Test-only archived v1 row; do not call the disabled transition API."""
        self.create()
        self.send()
        receipt_json = json.dumps(
            self.receipt(), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False)
        details_json = json.dumps({
            "observationId": "receipt-event-01",
            "guidanceStatus": "verified_structured_fields",
            "suggestedFieldNames": ["partyId"],
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.path)) as raw:
            raw.execute(
                "UPDATE amendments SET state='REJECTED',revision=3,"
                "rejection_id=?,rejection_json=?,rejection_sha=? "
                "WHERE amendment_id=? AND revision=2",
                ("receipt-event-01", receipt_json, digest(receipt_json),
                 "amendment-first"))
            raw.execute(
                "INSERT INTO audit(amendment_id,actor_id,session_id,kind,"
                "details_json,details_sha,occurred_at) VALUES(?,?,?,?,?,?,?)",
                ("amendment-first", "bridge", "bridge-session",
                 "verified_rejection_observed", details_json,
                 digest(details_json), T2))
            raw.commit()

    def get(self, amendment_id="amendment-first", **updates):
        kwargs = dict(principal=self.user, amendment_id=amendment_id)
        kwargs.update(updates)
        return self.store.get_amendment(**kwargs)

    def history(self, amendment_id="amendment-first", **updates):
        kwargs = dict(principal=self.user, amendment_id=amendment_id)
        kwargs.update(updates)
        return self.store.audit_events(**kwargs)

    def test_independent_draft_and_immutable_original(self):
        item = self.create()
        self.assertEqual(item["state"], "DRAFT")
        self.assertEqual(item["rowRevision"], 1)
        self.assertEqual(item["originalRequestId"], "request-original")
        self.assertFalse(item["sentToTaraz"])
        self.assertFalse(item["officialFinancePosted"])
        snapshot = self.get()
        self.assertEqual(snapshot["original"], self.original)
        self.assertEqual(snapshot["proposedFields"], {"partyId": "new"})
        self.assertEqual(snapshot["auditCount"], 1)
        self.original["fields"]["partyId"] = "caller-change"
        self.assertEqual(self.get()["original"]["fields"]["partyId"], "old")
        with closing(sqlite3.connect(self.path)) as db:
            names = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse({"ledger", "invoices", "payments"} & names)

    def test_independent_separate_warning_acknowledgments(self):
        self.create()
        kwargs = dict(
            amendment_id="amendment-second",
            proposed_fields={"partyId": "new"},
            create_key="create-key-0002",
        )
        with self.assertRaisesRegex(AmendmentConflict, "open_amendment_ack_required"):
            self.create(**kwargs)
        with self.assertRaisesRegex(AmendmentConflict, "possible_duplicate_ack_required"):
            self.create(**kwargs, acknowledged_open=True)
        with self.assertRaisesRegex(AmendmentConflict, "open_amendment_ack_required"):
            self.create(**kwargs, acknowledged_duplicate=True)
        created = self.create(**kwargs, acknowledged_open=True,
                              acknowledged_duplicate=True)
        self.assertEqual(created["state"], "DRAFT")
        history = self.history("amendment-second")
        self.assertEqual([x["action"] for x in history], [
            "amendment_created", "acknowledge_open_amendment",
            "acknowledge_possible_duplicate",
        ])
        self.assertEqual(len(self.store.related_amendments(
            principal=self.user, org_id="org-a",
            project_id="project-1", original_id="request-original",
        )), 2)

    def test_open_conflict_uses_pure_choice_and_blocks_send_before_choice(self):
        self.create()
        second = self.create(
            amendment_id="amendment-second", proposed_fields={"partyId": "other"},
            create_key="create-key-0002", acknowledged_open=True,
        )
        self.assertEqual(second["unresolvedFields"], ["partyId"])
        with self.assertRaisesRegex(AmendmentConflict, "unresolved"):
            self.send(amendment_id="amendment-second",
                      send_key="send-key-0002")
        resolved = self.choose()
        self.assertEqual(resolved["rowRevision"], 2)
        self.assertEqual(resolved["unresolvedFields"], [])
        sent = self.send(amendment_id="amendment-second",
                         expected_row_revision=2, send_key="send-key-0002")
        self.assertEqual(sent["state"], "MANUAL_SEND_INTENT")
        self.assertFalse(sent["sentToTaraz"])
        self.assertEqual(self.get("amendment-second")["proposedFields"],
                         {"partyId": "resolved"})

    def test_choice_idempotence_restart_and_wrong_replay(self):
        self.create()
        self.create(amendment_id="amendment-second",
                    proposed_fields={"partyId": "other"},
                    create_key="create-key-0002", acknowledged_open=True)
        first = self.choose()
        self.store = AmendmentStore(self.path)
        self.assertTrue(self.choose()["idempotent"])
        self.assertEqual(self.choose()["rowRevision"], first["rowRevision"])
        with self.assertRaises(AmendmentConflict):
            self.choose(chosen_values={"partyId": "another"})
        with self.assertRaises(AmendmentConflict):
            self.choose(operation_key="choice-key-0002")

    def test_stale_original_revision_blocks_intent_and_re_review_only_changed(self):
        self.create()
        latest = {**self.original, "revision": "rev-2",
                  "fields": {**self.original["fields"], "notes": "updated"}}
        with self.assertRaisesRegex(AmendmentConflict, "stale"):
            self.send(current_original=latest)
        with self.assertRaises(AmendmentPreviewError):
            self.store.re_review_baseline(
                principal=self.user, amendment_id="amendment-first",
                expected_row_revision=1, current_original=latest,
                chosen_values={}, acknowledged_dependency_fields=[],
                acknowledged_revision_change=True,
                operation_key="rereview-key-01", occurred_at=T1)
        rereview = self.store.re_review_baseline(
            principal=self.user, amendment_id="amendment-first",
            expected_row_revision=1, current_original=latest,
            chosen_values={}, acknowledged_dependency_fields=["notes"],
            acknowledged_revision_change=True,
            operation_key="rereview-key-01", occurred_at=T1)
        self.assertEqual(rereview["rowRevision"], 2)
        self.assertEqual(self.get()["original"]["revision"], "rev-1")
        self.assertEqual(self.get()["originalRevisionAtReview"], "rev-2")
        sent = self.send(expected_row_revision=2, current_original=latest)
        self.assertEqual(sent["state"], "MANUAL_SEND_INTENT")

    def test_stale_amendment_revision_and_unknown_baseline_refused(self):
        self.create()
        with self.assertRaisesRegex(AmendmentConflict, "stale"):
            self.send(expected_row_revision=2)
        with self.assertRaisesRegex(AmendmentConflict, "stale"):
            self.send(current_original={**self.original, "revision": "rev-2"})
        with self.assertRaisesRegex(AmendmentConflict, "stale"):
            self.send(current_original={**self.original,
                                        "fields": {**self.original["fields"],
                                                   "quantity": 200}})

    def test_intent_replay_still_requires_current_matching_original(self):
        self.create()
        self.send()
        with self.assertRaisesRegex(AmendmentConflict, "stale"):
            self.send(expected_row_revision=2, current_original={
                **self.original, "revision": "rev-changed",
            })
        self.assertTrue(self.send(expected_row_revision=2)["idempotent"])

    def test_send_requires_human_and_trusted_current_snapshot(self):
        self.create()
        for manual, verified in ((False, True), (True, False), (1, True),
                                 (True, 1), (None, True)):
            with self.subTest(manual=manual, verified=verified), self.assertRaises(
                    PermissionError):
                self.send(explicit_manual_action=manual,
                          current_server_verified=verified)
        self.assertEqual(self.get()["state"], "DRAFT")
        result = self.send()
        self.assertEqual(result["state"], "MANUAL_SEND_INTENT")
        self.assertEqual(result["rowRevision"], 2)
        self.assertTrue(self.send(expected_row_revision=2)["idempotent"])
        self.assertEqual(len(self.history()), 2)

    def test_send_intent_never_calls_network_and_no_autosend_after_restart(self):
        self.create()
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            result = self.send()
        self.assertFalse(result["sentToTaraz"])
        self.store = AmendmentStore(self.path)
        self.assertEqual(self.get()["state"], "MANUAL_SEND_INTENT")
        self.assertFalse(self.get()["sentToTaraz"])
        with self.assertRaises(AmendmentConflict):
            self.send(expected_row_revision=2, send_key="changed-send-key")

    def test_official_rejection_is_blocked_without_independent_verification(self):
        self.create()
        self.send()
        with self.assertRaisesRegex(
                PermissionError, "official Taraz rejection verification unavailable"):
            self.reject()
        self.store = AmendmentStore(self.path)
        self.assertEqual(self.get()["state"], "MANUAL_SEND_INTENT")
        self.assertEqual(self.get()["rowRevision"], 2)
        with self.assertRaises(PermissionError):
            self.reject(expected_row_revision=2, observation_id="different-event")
        self.assertTrue(self.send(expected_row_revision=2)["idempotent"])
        self.assertEqual([x["action"] for x in self.history()], [
            "amendment_created", "manual_send_intent_only"])

    def test_archived_rejected_history_kept_without_new_verification_claim(self):
        self.seed_historical_rejection()
        with closing(sqlite3.connect(self.path)) as raw:
            before = (
                raw.execute("SELECT * FROM amendments WHERE amendment_id=?",
                            ("amendment-first",)).fetchone(),
                raw.execute("SELECT * FROM audit ORDER BY seq").fetchall(),
            )
        self.store = AmendmentStore(self.path)
        self.assertEqual(self.get()["state"], "REJECTION_UNVERIFIED")
        self.assertEqual(self.get()["rowRevision"], 3)
        self.assertFalse(self.get()["officialTarazRejectionVerified"])
        with self.assertRaises(PermissionError):
            self.reject(expected_row_revision=3)
        with self.assertRaises(PermissionError):
            self.reject(expected_row_revision=3, observation_id="different-event")
        with self.assertRaises(AmendmentConflict):
            self.send(expected_row_revision=3)
        self.assertEqual([x["action"] for x in self.history()], [
            "amendment_created", "manual_send_intent_only",
            "historical_rejection_unverified"])
        self.assertEqual(self.history()[-1]["details"], {
            "historicalStoredEvent": True,
            "officialTarazRejectionVerified": False,
        })
        self.assertEqual(
            self.store.related_amendments(
                principal=self.user, org_id="org-a", project_id="project-1",
                original_id="request-original")[0]["status"],
            "rejection_unverified")
        with closing(sqlite3.connect(self.path)) as raw:
            after = (
                raw.execute("SELECT * FROM amendments WHERE amendment_id=?",
                            ("amendment-first",)).fetchone(),
                raw.execute("SELECT * FROM audit ORDER BY seq").fetchall(),
            )
        self.assertEqual(after, before)

    def test_ambiguous_rejection_metadata_cannot_change_state(self):
        self.create()
        self.send()
        with self.assertRaises(PermissionError):
            self.reject(receipt=self.receipt(reason={
                "text": "unclear error", "affectedFields": [], "structured": False,
            }))
        self.assertEqual(self.get()["state"], "MANUAL_SEND_INTENT")

    def test_rejection_claims_cannot_create_taras_provenance(self):
        self.create()
        self.send()
        for item in (
            adapter(),
            adapter(org_id="other-org"), adapter(project_ids=frozenset()),
            adapter(role="editor"), adapter(authenticated=False),
            adapter(session_valid=False), adapter(active=False),
            adapter(permissions=frozenset()),
            self.user,
        ):
            with self.subTest(adapter=item), self.assertRaises(PermissionError):
                self.reject(adapter=item)
        for flag in (False, 0, 1, None):
            with self.subTest(flag=flag), self.assertRaises(PermissionError):
                self.reject(verified_by_adapter=flag)
        for receipt in (
            self.receipt(verifiedTarazSource=False),
            self.receipt(orgId="other-org"),
            self.receipt(originalRequestId="other-request"),
            self.receipt(amendmentId="other-amendment"),
            self.receipt(status="approved"),
        ):
            with self.subTest(receipt=receipt), self.assertRaises(PermissionError):
                self.reject(receipt=receipt)
        self.assertEqual(self.get()["state"], "MANUAL_SEND_INTENT")

    def test_rejection_before_manual_intent_refused(self):
        self.create()
        with self.assertRaises(PermissionError):
            self.reject(expected_row_revision=1)

    def test_unverified_historical_rejection_stays_independent(self):
        self.seed_historical_rejection()
        with self.assertRaises(AmendmentPreviewError):
            self.create(
                amendment_id="amendment-after-rejection",
                create_key="create-key-0002",
                proposed_fields={"partyId": "new"},
                acknowledged_open=True, acknowledged_duplicate=True,
                previous_rejected_amendment_id="amendment-first",
            )
        next_item = self.create(
            amendment_id="amendment-after-rejection",
            create_key="create-key-0002",
            proposed_fields={"partyId": "new"},
            acknowledged_open=True, acknowledged_duplicate=True,
        )
        self.assertIsNone(next_item["previousRejectedAmendmentId"])
        self.assertEqual(self.get()["state"], "REJECTION_UNVERIFIED")
        self.assertEqual(self.get()["original"]["fields"]["partyId"], "old")
        with self.assertRaises(AmendmentPreviewError):
            self.create(
                amendment_id="amendment-third",
                create_key="create-key-0003",
                previous_rejected_amendment_id="not-a-rejected-reference",
                acknowledged_open=True,
            )

    def test_related_amendment_created_later_forces_fresh_re_review(self):
        self.create()
        self.create(
            amendment_id="amendment-second",
            create_key="create-key-0002",
            proposed_fields={"partyId": "other"},
            acknowledged_open=True,
        )
        with self.assertRaisesRegex(AmendmentConflict, "changed_related"):
            self.send()
        reviewed = self.store.re_review_baseline(
            principal=self.user, amendment_id="amendment-first",
            expected_row_revision=1, current_original=self.original,
            chosen_values={"partyId": "resolved-after-new"},
            acknowledged_dependency_fields=[],
            acknowledged_revision_change=False,
            operation_key="rereview-key-01", occurred_at=T1,
        )
        self.assertEqual(reviewed["rowRevision"], 2)
        self.assertEqual(reviewed["unresolvedFields"], [])
        result = self.send(expected_row_revision=2, occurred_at=T2)
        self.assertEqual(result["state"], "MANUAL_SEND_INTENT")

    def test_original_and_audit_immutability_enforced_by_sqlite(self):
        self.create()
        with closing(sqlite3.connect(self.path)) as raw:
            with self.assertRaises(sqlite3.IntegrityError):
                raw.execute(
                    "UPDATE amendments SET original_id=? WHERE amendment_id=?",
                    ("rewritten", "amendment-first"))
            raw.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                raw.execute("UPDATE audit SET actor_id='forge' WHERE seq=1")
            raw.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                raw.execute("DELETE FROM audit WHERE seq=1")
            raw.rollback()
        self.assertEqual(len(self.history()), 1)

    def test_corrupt_snapshot_digest_refused_after_restart(self):
        self.create()
        with closing(sqlite3.connect(self.path)) as raw:
            raw.execute(
                "UPDATE amendments SET snapshot_sha=? WHERE amendment_id=?",
                ("0" * 64, "amendment-first"))
            raw.commit()
        self.store = AmendmentStore(self.path)
        with self.assertRaises(AmendmentStoreError):
            self.get()
        with self.assertRaises(AmendmentStoreError):
            self.send()

    def test_corrupt_added_audit_event_fails_closed(self):
        self.create()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                "INSERT INTO audit(amendment_id,actor_id,session_id,kind,"
                "details_json,details_sha,occurred_at) VALUES(?,?,?,?,?,?,?)",
                ("amendment-first", "editor-a", "session-a", "injected",
                 '{"fake":true}', "0" * 64, T1),
            )
            db.commit()
        self.store = AmendmentStore(self.path)
        with self.assertRaises(AmendmentStoreError):
            self.get()
        with self.assertRaises(AmendmentStoreError):
            self.send()

    def test_idempotent_create_replay_conflict_and_unique_identity(self):
        self.create()
        self.store = AmendmentStore(self.path)
        self.assertTrue(self.create()["idempotent"])
        for changes in (
            {"create_key": "new-create-key"},
            {"proposed_fields": {"partyId": "different"}},
            {"principal": principal(session_id="another-session")},
            {"principal": principal(user_id="another-user")},
        ):
            with self.subTest(changes=changes), self.assertRaises(
                (AmendmentConflict, PermissionError)):
                self.create(**changes)
        with self.assertRaises(AmendmentConflict):
            self.create(amendment_id="another-amendment")

    def test_cross_org_project_actor_session_role_acl(self):
        self.create()
        other_project = principal(project_ids=frozenset({"other-project"}))
        for actor in (
            principal(org_id="other-org"), other_project,
            principal(user_id="foreign"), principal(session_id="other-session"),
            principal(authenticated=False), principal(session_valid=False),
            principal(active=False), principal(role="viewer"),
            principal(permissions=frozenset()),
        ):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.get(principal=actor)
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.send(principal=actor)
        with self.assertRaises(PermissionError):
            self.store.related_amendments(
                principal=other_project, org_id="org-a",
                project_id="project-1", original_id="request-original")
        with self.assertRaises(PermissionError):
            self.create(principal=other_project, amendment_id="other-amendment",
                        create_key="create-key-0002")
        self.assertEqual(self.get()["state"], "DRAFT")

    def test_session_change_rejects_review_and_send(self):
        self.create()
        self.create(amendment_id="amendment-second",
                    create_key="create-key-0002",
                    proposed_fields={"partyId": "another"}, acknowledged_open=True)
        with self.assertRaises(PermissionError):
            self.choose(principal=principal(session_id="new-session"))
        with self.assertRaises(PermissionError):
            self.send(principal=principal(session_id="new-session"))

    def test_race_same_create_only_one_audit_and_one_insert(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = [task.result(timeout=20) for task in
                    (pool.submit(self.create) for _ in range(8))]
        self.assertEqual(sum(not x["idempotent"] for x in rows), 1)
        self.assertEqual(len(self.history()), 1)

    def test_multiple_windows_processes_create_once(self):
        ctx = multiprocessing.get_context("spawn")
        q = ctx.Queue()
        procs = [
            ctx.Process(target=_child_create,
                        args=(str(self.path), dict(self.original), q))
            for _ in range(4)
        ]
        for process in procs:
            process.start()
        results = [q.get(timeout=30) for _ in procs]
        for process in procs:
            process.join(timeout=30)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(results.count("created"), 1, results)
        self.assertEqual(results.count("replay"), 3, results)
        self.assertEqual(len(self.history()), 1)

    def test_race_conflicting_send_keys_only_one_wins(self):
        self.create()
        def send_key(key):
            return self.send(send_key=key)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(send_key, "send-key-first"),
                       pool.submit(send_key, "send-key-second")]
            outcomes = []
            for fut in futures:
                try:
                    outcomes.append(fut.result(timeout=20)["sendKey"])
                except AmendmentConflict:
                    outcomes.append("conflict")
        self.assertEqual(outcomes.count("conflict"), 1)
        self.assertEqual(len(self.history()), 2)

    def test_fault_between_update_and_audit_rolls_back(self):
        self.create()
        with patch.object(AmendmentStore, "_audit", side_effect=RuntimeError("fault")):
            with self.assertRaisesRegex(RuntimeError, "fault"):
                self.send()
        self.assertEqual(self.get()["state"], "DRAFT")
        self.assertEqual(self.get()["rowRevision"], 1)
        self.assertEqual(len(self.history()), 1)
        self.assertEqual(self.send()["state"], "MANUAL_SEND_INTENT")

    def test_invalid_schema_and_unsafe_path(self):
        raw = Path(self.temporary.name) / "rogue.sqlite3"
        with closing(sqlite3.connect(raw)) as conn:
            conn.execute("CREATE TABLE random_data (x INTEGER)")
            conn.commit()
        with self.assertRaises(AmendmentStoreError):
            AmendmentStore(raw)
        symlink = Path(self.temporary.name) / "link.sqlite3"
        try:
            symlink.symlink_to(self.path)
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(PermissionError):
            AmendmentStore(symlink)

    def test_consistent_create_only_backup_restart_and_recovery(self):
        self.create()
        self.send()
        backups = Path(self.temporary.name) / "backups"
        backups.mkdir()
        destination = backups / "e5-snapshot.sqlite3"
        info = self.store.backup_to(destination)
        self.assertTrue(info["verified"])
        self.assertTrue(destination.is_file())
        with self.assertRaises(FileExistsError):
            self.store.backup_to(destination)
        recovered = AmendmentStore(destination)
        item = recovered.get_amendment(
            principal=self.user, amendment_id="amendment-first")
        self.assertEqual(item["state"], "MANUAL_SEND_INTENT")
        self.assertEqual(item["original"]["fields"]["partyId"], "old")
        self.assertEqual(len(recovered.audit_events(
            principal=self.user, amendment_id="amendment-first")), 2)

    def test_backup_existing_path_is_not_overwritten(self):
        destination = Path(self.temporary.name) / "existing.sqlite3"
        destination.write_bytes(b"keep-this-data")
        with self.assertRaises(FileExistsError):
            self.store.backup_to(destination)
        self.assertEqual(destination.read_bytes(), b"keep-this-data")

    def test_missing_identifier_and_inaccessible_identifier_both_denied(self):
        self.create()
        with self.assertRaises(PermissionError):
            self.get(amendment_id="missing-record")
        with self.assertRaises(PermissionError):
            self.get(principal=principal(org_id="foreign-org"))


if __name__ == "__main__":
    unittest.main()
