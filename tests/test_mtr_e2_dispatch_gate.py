"""Disposable E2 one-shot reservation tests: no LAN, peer or money writes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from unittest.mock import patch

from mtr_e2_dispatch_gate import (
    DispatchGateConflict, DispatchGateError, OneShotDispatchGate,
)
from mtr_host_request_store import (
    HostRequestStore, StoreConflict, TrustedPrincipal,
)


ORG = "synthetic-org-alpha"
PROJECT = "synthetic-project-7"
REV = 13
PREPARE_KEY = "prepare-key-001"
SEND_KEY = "stable-send-key-001"


def principal(**changes):
    props = {
        "user_id": "synthetic-alice", "org_id": ORG,
        "session_id": "synthetic-session-primary", "role": "editor",
        "project_ids": frozenset({PROJECT}),
        "permissions": frozenset({"mtr.prepare", "mtr.manual_send", "mtr.read"}),
        "authenticated": True, "session_valid": True, "active": True,
    }
    props.update(changes)
    return TrustedPrincipal(**props)


def observer(**changes):
    props = {
        "user_id": "synthetic-taraz-adapter", "org_id": ORG,
        "session_id": "synthetic-taraz-session", "role": "taraz_adapter",
        "project_ids": frozenset({PROJECT}),
        "permissions": frozenset({"mtr.receipt_ingest"}),
        "authenticated": True, "session_valid": True, "active": True,
    }
    props.update(changes)
    return TrustedPrincipal(**props)


def _child_reserve(gate_file, source_file, request_id, digest, results):
    """Spawn-safe worker; returns no credentials, sends no packet."""
    try:
        store = HostRequestStore(Path(source_file))
        gate = OneShotDispatchGate(Path(gate_file), store)
        result = gate.reserve_once(
            principal=principal(), request_id=request_id,
            expected_payload_sha256=digest, expected_base_revision=REV,
            current_server_revision=REV, send_key=SEND_KEY,
        )
        results.put("first" if result["firstAttemptGranted"] else "not-first")
    except DispatchGateConflict:
        results.put("consumed")
    except Exception as exc:
        results.put(type(exc).__name__ + ": " + str(exc))


class OneShotGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-e2-dispatch-synthetic-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = patch.dict(os.environ, {
            "APPDATA": str(self.root), "LOCALAPPDATA": str(self.root),
            "USERPROFILE": str(self.root), "HOME": str(self.root),
            "TEMP": str(self.root), "TMP": str(self.root),
        })
        env.start()
        self.addCleanup(env.stop)
        self.outbox_path = self.root / "host-outbox.sqlite3"
        self.gate_path = self.root / "one-shot.sqlite3"
        self.source = HostRequestStore(self.outbox_path)
        self.gate = OneShotDispatchGate(self.gate_path, self.source)
        self.id = uuid.uuid4().hex
        self.identity = principal()
        self.payload = {
            "id": self.id, "schema": 1, "source": "madar",
            "taskId": "synthetic-task-1", "projectId": PROJECT,
            "title": "Synthetic only", "createdUtc": "2026-11-09T09:00:00+00:00",
        }

    def authorize(self):
        prep = self.source.prepare_request(
            principal=self.identity, request_id=self.id, payload=self.payload,
            base_revision=REV, current_server_revision=REV,
            prepare_key=PREPARE_KEY, explicit_manual_action=True,
        )
        send = self.source.manual_send(
            principal=self.identity, request_id=self.id,
            expected_payload_sha256=prep["payloadSha256"],
            expected_base_revision=REV, current_server_revision=REV,
            send_key=SEND_KEY, explicit_manual_action=True,
        )
        self.assertEqual(send["requestState"], "MANUAL_SEND_AUTHORIZED")
        return prep["payloadSha256"]

    def reserve(self, digest=None, **changes):
        params = {
            "principal": self.identity, "request_id": self.id,
            "expected_payload_sha256": digest or self.digest,
            "expected_base_revision": REV,
            "current_server_revision": REV,
            "send_key": SEND_KEY,
        }
        params.update(changes)
        return self.gate.reserve_once(**params)

    def _synthetic_observation(self, *, result="received",
                               receipt="synthetic-receipt-001"):
        return {
            "schema": 1, "source": "taraz",
            "observationId": "synthetic-observation-001",
            "requestId": self.id, "orgId": ORG, "projectId": PROJECT,
            "baseRevision": REV, "payloadSha256": self.digest,
            "sendKey": SEND_KEY, "result": result,
            "receiptId": receipt if result == "received" else None,
            "observedUtc": "2026-11-09T09:01:00+00:00",
        }

    def seed_synthetic_historical_outbox_observation(
            self, *, result="received", receipt="synthetic-receipt-001"):
        """TEST-ONLY SQLite seed for downstream gate/old-row invariants.

        It does not represent authenticated official Taraz evidence, and it
        never invokes, bypasses or weakens the production ingest API.
        """
        proof = self._synthetic_observation(result=result, receipt=receipt)
        encoded = json.dumps(proof, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.outbox_path)) as db:
            db.execute(
                "INSERT INTO observations(observation_id,request_id,evidence_json,"
                "evidence_sha256,observer_id,observed_at) VALUES(?,?,?,?,?,?)",
                (proof["observationId"], self.id, encoded, digest,
                 "synthetic-historical-fixture", proof["observedUtc"]),
            )
            db.execute(
                "UPDATE requests SET receipt_state=?,receipt_id=? WHERE request_id=?",
                (result, receipt if result == "received" else None, self.id),
            )
            db.commit()

    def test_public_receipt_ingest_cannot_invent_authority(self):
        self.digest = self.authorize()
        for result in ("received", "not_received", "unknown"):
            with self.subTest(result=result), self.assertRaises(PermissionError):
                self.source.record_query_result(
                    principal=observer(), request_id=self.id,
                    verified_by_adapter=True,
                    evidence=self._synthetic_observation(result=result),
                )
        snapshot = self.source.receipt_status(
            principal=self.identity, request_id=self.id,
            expected_base_revision=REV,
        )
        self.assertEqual(snapshot["receiptState"], "unknown")
        self.assertIsNone(snapshot["receiptId"])

    def status(self, **changes):
        params = {"principal": self.identity, "request_id": self.id,
                  "expected_base_revision": REV}
        params.update(changes)
        return self.gate.status(**params)

    def test_reserve_requires_preexisting_manual_authorized_intent(self):
        with self.assertRaises(KeyError):
            self.reserve(digest="0" * 64)
        prep = self.source.prepare_request(
            principal=self.identity, request_id=self.id, payload=self.payload,
            base_revision=REV, current_server_revision=REV,
            prepare_key=PREPARE_KEY, explicit_manual_action=True,
        )
        with self.assertRaises(PermissionError):
            self.reserve(digest=prep["payloadSha256"])
        self.assertEqual(self.gate_path.is_file(), True)
        with closing(sqlite3.connect(self.gate_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM dispatch_reservations").fetchone()[0], 0)

    def test_exactly_one_grant_and_no_second_first_attempt_even_identical(self):
        self.digest = self.authorize()
        one = self.reserve()
        self.assertTrue(one["firstAttemptGranted"])
        self.assertTrue(one["reservationConsumed"])
        self.assertEqual(one["state"], "reserved_before_network")
        self.assertTrue(one["mustQueryFirst"])
        self.assertFalse(one["mayDispatch"])
        with self.assertRaises(DispatchGateConflict):
            self.reserve()
        actual = self.status()
        self.assertNotIn("firstAttemptGranted", actual)
        self.assertEqual(actual["nextAction"], "query_taraz_first_no_automatic_retry")
        self.assertEqual([e["action"] for e in self.gate.audit_events(
            principal=self.identity, request_id=self.id, expected_base_revision=REV,
        )], ["reserved_before_network"])

    def test_crash_before_network_and_lost_response_hold_query_first(self):
        self.digest = self.authorize()
        self.reserve()
        # Intentionally discard reservation result, simulating a lost response
        # or crash BEFORE any caller transport can happen.
        self.gate = OneShotDispatchGate(self.gate_path, HostRequestStore(self.outbox_path))
        self.assertTrue(self.status()["mustQueryFirst"])
        with self.assertRaises(DispatchGateConflict):
            self.reserve()
        uncertain = self.gate.mark_unknown_after_attempt(
            principal=self.identity, request_id=self.id,
            expected_base_revision=REV, expected_version=1,
        )
        self.assertEqual(uncertain["state"], "unknown_after_attempt")
        self.assertTrue(uncertain["mustQueryFirst"])
        self.gate = OneShotDispatchGate(self.gate_path, HostRequestStore(self.outbox_path))
        self.assertEqual(self.status()["version"], 2)
        with self.assertRaises(DispatchGateConflict):
            self.reserve()
        with self.assertRaises(DispatchGateConflict):
            self.gate.mark_unknown_after_attempt(
                principal=self.identity, request_id=self.id,
                expected_base_revision=REV, expected_version=1,
            )

    def test_historical_received_never_reconciles_into_operational_confirmation(self):
        self.digest = self.authorize()
        self.reserve()
        with self.assertRaises(PermissionError):
            self.gate.observe_received(
                principal=self.identity, request_id=self.id,
                expected_base_revision=REV, expected_version=1,
            )
        self.seed_synthetic_historical_outbox_observation()
        with self.assertRaises(PermissionError):
            self.gate.observe_received(
                principal=self.identity, request_id=self.id,
                expected_base_revision=REV, expected_version=1,
            )
        observed = self.status()
        self.assertEqual(observed["state"], "reserved_before_network")
        self.assertIsNone(observed["receiptId"])
        self.assertEqual(observed["receiptVerification"], "UNVERIFIED")
        self.assertTrue(observed["mustQueryFirst"])
        self.assertFalse(observed["mayDispatch"])
        with self.assertRaises(DispatchGateConflict):
            self.reserve()
        self.assertEqual(len(self.gate.audit_events(
            principal=self.identity, request_id=self.id, expected_base_revision=REV,
        )), 1)

    def test_unknown_after_attempt_never_promotes_historical_received(self):
        self.digest = self.authorize()
        self.reserve()
        self.gate.mark_unknown_after_attempt(
            principal=self.identity, request_id=self.id,
            expected_base_revision=REV, expected_version=1,
        )
        self.seed_synthetic_historical_outbox_observation()
        with self.assertRaises(DispatchGateConflict):
            self.gate.observe_received(
                principal=self.identity, request_id=self.id,
                expected_base_revision=REV, expected_version=1,
            )
        with self.assertRaises(PermissionError):
            self.gate.observe_received(
                principal=self.identity, request_id=self.id,
                expected_base_revision=REV, expected_version=2,
            )
        self.assertEqual(self.status()["version"], 2)
        self.assertEqual(self.status()["state"], "unknown_after_attempt")
        self.assertEqual([e["action"] for e in self.gate.audit_events(
            principal=self.identity, request_id=self.id, expected_base_revision=REV,
        )], ["reserved_before_network", "unknown_after_attempt"])
        with self.assertRaises(DispatchGateConflict):
            self.gate.mark_unknown_after_attempt(
                principal=self.identity, request_id=self.id,
                expected_base_revision=REV, expected_version=2,
            )

    def test_preexisting_observed_received_is_only_forensic_not_public_confirmation(self):
        """TEST ONLY: seed old valid SQLite gate state, never use live ingest."""
        self.digest = self.authorize()
        self.reserve()
        self.seed_synthetic_historical_outbox_observation()
        receipt = "synthetic-receipt-001"
        with closing(sqlite3.connect(self.gate_path)) as db:
            db.execute(
                "UPDATE dispatch_reservations SET state='observed_received',"
                "version=2,receipt_id=? WHERE request_id=?",
                (receipt, self.id),
            )
            db.execute(
                "INSERT INTO dispatch_audit(request_id,version,action,actor_id,"
                "session_id,receipt_sha256,recorded_at) VALUES(?,?,?,?,?,?,?)",
                (self.id, 2, "observed_received", self.identity.user_id,
                 self.identity.session_id, hashlib.sha256(receipt.encode()).hexdigest(),
                 "2026-11-09T09:02:00+00:00"),
            )
            db.commit()
        result = self.status()
        self.assertEqual(result["state"], "quarantined_unverified_receipt")
        self.assertTrue(result["historicalReceiptQuarantined"])
        self.assertEqual(result["receiptVerification"], "UNVERIFIED")
        self.assertIsNone(result["receiptId"])
        self.assertTrue(result["reservationConsumed"])
        self.assertFalse(result["mayDispatch"])
        self.assertTrue(result["mustQueryFirst"])
        self.assertFalse(result["canAutoRetry"])
        self.assertEqual(result["nextAction"], "query_taraz_first_no_automatic_retry")
        self.assertNotIn(receipt, repr(result))
        with self.assertRaises(PermissionError):
            self.gate.observe_received(
                principal=self.identity, request_id=self.id,
                expected_base_revision=REV, expected_version=2,
            )
        forensic = self.gate.audit_events(
            principal=self.identity, request_id=self.id,
            expected_base_revision=REV,
        )
        self.assertEqual([event["action"] for event in forensic],
                         ["reserved_before_network", "observed_received"])
        self.assertTrue(all(event["receiptVerification"] == "UNVERIFIED"
                            and event["officialTarazReceipt"] is False
                            for event in forensic))
        with closing(sqlite3.connect(self.gate_path)) as db:
            self.assertEqual(db.execute(
                "SELECT state,receipt_id FROM dispatch_reservations WHERE request_id=?",
                (self.id,),
            ).fetchone(), ("observed_received", receipt))
        restarted = OneShotDispatchGate(self.gate_path, HostRequestStore(self.outbox_path))
        self.assertEqual(restarted.status(
            principal=self.identity, request_id=self.id,
            expected_base_revision=REV,
        )["state"], "quarantined_unverified_receipt")
        with self.assertRaises(DispatchGateConflict):
            self.reserve()

    def test_historical_not_received_before_reservation_cannot_mint_new_slot(self):
        self.digest = self.authorize()
        self.seed_synthetic_historical_outbox_observation(result="not_received")
        with self.assertRaises(DispatchGateConflict):
            self.reserve()
        with closing(sqlite3.connect(self.gate_path)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM dispatch_reservations",
            ).fetchone()[0], 0)
        public = self.source.receipt_status(
            principal=self.identity, request_id=self.id,
            expected_base_revision=REV,
        )
        self.assertEqual(public["receiptState"], "unknown")
        self.assertIsNone(public["receiptId"])
        self.assertTrue(public["historicalReceiptQuarantined"])
        self.assertEqual(public["receiptVerification"], "UNVERIFIED")
        self.assertFalse(public["canAutoRetry"])

    def test_negative_query_result_never_releases_second_dispatch(self):
        self.digest = self.authorize()
        self.reserve()
        self.seed_synthetic_historical_outbox_observation(result="not_received")
        with self.assertRaises(PermissionError):
            self.gate.observe_received(
                principal=self.identity, request_id=self.id,
                expected_base_revision=REV, expected_version=1,
            )
        with self.assertRaises(DispatchGateConflict):
            self.reserve()
        self.assertTrue(self.status()["mustQueryFirst"])

    def test_received_outbox_before_reservation_blocks_first_attempt(self):
        self.digest = self.authorize()
        self.seed_synthetic_historical_outbox_observation()
        with self.assertRaises(DispatchGateConflict):
            self.reserve()
        with closing(sqlite3.connect(self.gate_path)) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM dispatch_reservations",
            ).fetchone()[0], 0)

    def test_stale_hash_base_revision_send_key_and_server_revision(self):
        self.digest = self.authorize()
        for fields in (
            {"expected_payload_sha256": "a" * 64},
            {"expected_base_revision": REV - 1,
             "current_server_revision": REV - 1},
            {"current_server_revision": REV + 1},
            {"send_key": "different-send-key-001"},
        ):
            with self.subTest(fields=fields), self.assertRaises(
                (DispatchGateConflict, StoreConflict),
            ):
                self.reserve(**fields)
        self.assertEqual(self.reserve()["version"], 1)

    def test_principal_role_org_project_session_actor_revocation_denied(self):
        self.digest = self.authorize()
        for identity in (
            principal(role="viewer"),
            principal(permissions=frozenset({"mtr.read"})),
            principal(org_id="different-org"),
            principal(project_ids=frozenset({"other-project"})),
            principal(user_id="other-person"),
            principal(session_id="different-session"),
            principal(session_valid=False),
            principal(authenticated=False),
            principal(active=False),
        ):
            with self.subTest(identity=identity), self.assertRaises(PermissionError):
                self.reserve(principal=identity)
        self.reserve()
        for identity in (
            principal(session_id="different-session"),
            principal(project_ids=frozenset()),
        ):
            with self.assertRaises(PermissionError):
                self.status(principal=identity)

    def test_downgraded_read_only_principal_cannot_transition_reservation(self):
        self.digest = self.authorize()
        self.reserve()
        reduced = principal(
            role="finance_reviewer", permissions=frozenset({"mtr.read"}),
        )
        self.assertEqual(self.status(principal=reduced)["version"], 1)
        with self.assertRaises(PermissionError):
            self.gate.mark_unknown_after_attempt(
                principal=reduced, request_id=self.id,
                expected_base_revision=REV, expected_version=1,
            )
        self.seed_synthetic_historical_outbox_observation()
        with self.assertRaises(PermissionError):
            self.gate.observe_received(
                principal=reduced, request_id=self.id,
                expected_base_revision=REV, expected_version=1,
            )

    def test_atomic_reservation_rollback_if_audit_insert_fails(self):
        self.digest = self.authorize()
        with patch.object(OneShotDispatchGate, "_audit", side_effect=OSError("synthetic audit disk failure")):
            with self.assertRaisesRegex(OSError, "synthetic audit disk failure"):
                self.reserve()
        with closing(sqlite3.connect(self.gate_path)) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM dispatch_reservations",
            ).fetchone()[0], 0)
        self.assertTrue(self.reserve()["firstAttemptGranted"])

    def test_global_request_id_unique_across_source_databases_and_orgs(self):
        self.digest = self.authorize()
        self.reserve()
        second_source = HostRequestStore(self.root / "other-outbox.sqlite3")
        alt = principal(org_id="synthetic-second-org")
        alt_payload = {**self.payload}
        before = second_source.prepare_request(
            principal=alt, request_id=self.id, payload=alt_payload,
            base_revision=REV, current_server_revision=REV,
            prepare_key="prepare-key-second", explicit_manual_action=True,
        )
        second_source.manual_send(
            principal=alt, request_id=self.id,
            expected_payload_sha256=before["payloadSha256"],
            expected_base_revision=REV, current_server_revision=REV,
            send_key="second-org-send-key", explicit_manual_action=True,
        )
        second_gate = OneShotDispatchGate(self.gate_path, second_source)
        with self.assertRaises(DispatchGateConflict):
            second_gate.reserve_once(
                principal=alt, request_id=self.id,
                expected_payload_sha256=before["payloadSha256"],
                expected_base_revision=REV, current_server_revision=REV,
                send_key="second-org-send-key",
            )
        self.assertEqual(self.status()["state"], "reserved_before_network")

    def test_racing_threads_yield_only_one_first_dispatch_permission(self):
        self.digest = self.authorize()
        def worker(_):
            try:
                self.reserve()
                return "first"
            except DispatchGateConflict:
                return "consumed"
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(worker, range(12)))
        self.assertEqual(results.count("first"), 1, results)
        self.assertEqual(results.count("consumed"), 11, results)
        self.assertEqual(self.status()["version"], 1)

    def test_racing_windows_spawn_processes_only_one_first_permission(self):
        self.digest = self.authorize()
        context = multiprocessing.get_context("spawn")
        results = context.Queue()
        children = [
            context.Process(target=_child_reserve, args=(
                str(self.gate_path), str(self.outbox_path), self.id,
                self.digest, results,
            )) for _ in range(4)
        ]
        for child in children:
            child.start()
        outcomes = [results.get(timeout=35) for _ in children]
        for child in children:
            child.join(timeout=35)
            self.assertEqual(child.exitcode, 0)
        self.assertEqual(outcomes.count("first"), 1, outcomes)
        self.assertEqual(outcomes.count("consumed"), 3, outcomes)
        self.assertEqual(len(self.gate.audit_events(
            principal=self.identity, request_id=self.id, expected_base_revision=REV,
        )), 1)

    def test_immutable_audit_and_reservation_sql_triggers(self):
        self.digest = self.authorize()
        self.reserve()
        with closing(sqlite3.connect(self.gate_path)) as conn:
            for sql in (
                "UPDATE dispatch_audit SET action='unknown_after_attempt'",
                "DELETE FROM dispatch_audit",
                "DELETE FROM dispatch_reservations",
                "UPDATE dispatch_reservations SET actor_id='attacker'",
                "UPDATE dispatch_reservations SET version=2, state='reserved_before_network'",
            ):
                with self.subTest(sql=sql), self.assertRaises(sqlite3.DatabaseError):
                    conn.execute(sql)
                conn.rollback()
        self.assertEqual(self.status()["version"], 1)

    def test_corrupt_versions_uninitialized_and_tampered_audit_fail_closed(self):
        self.digest = self.authorize()
        self.reserve()
        with closing(sqlite3.connect(self.gate_path)) as conn:
            conn.execute("PRAGMA user_version=19")
        with self.assertRaises(DispatchGateError):
            OneShotDispatchGate(self.gate_path, self.source)
        with closing(sqlite3.connect(self.gate_path)) as conn:
            conn.execute("PRAGMA user_version=1")
            conn.execute("DROP TRIGGER immutable_dispatch_audit_delete")
            conn.execute("DELETE FROM dispatch_audit")
        with self.assertRaises(DispatchGateError):
            OneShotDispatchGate(self.gate_path, self.source)
        uninit = self.root / "existing-empty.sqlite3"
        uninit.touch()
        with self.assertRaises(DispatchGateError):
            OneShotDispatchGate(uninit, self.source)

    def test_create_only_backup_restart_no_second_reservation(self):
        self.digest = self.authorize()
        self.reserve()
        backup = self.root / "snapshot.sqlite3"
        result = self.gate.backup_to(backup)
        self.assertTrue(result["verified"])
        with self.assertRaises(FileExistsError):
            self.gate.backup_to(backup)
        restored = OneShotDispatchGate(backup, self.source)
        self.assertTrue(restored.status(
            principal=self.identity, request_id=self.id,
            expected_base_revision=REV,
        )["mustQueryFirst"])
        with self.assertRaises(PermissionError):
            restored.reserve_once(
                principal=self.identity, request_id=self.id,
                expected_payload_sha256=self.digest,
                expected_base_revision=REV,
                current_server_revision=REV, send_key=SEND_KEY,
            )

    def test_pre_reservation_backup_is_query_only_cannot_reopen_first_slot(self):
        self.digest = self.authorize()
        backup = self.root / "prior-snapshot.sqlite3"
        self.assertTrue(self.gate.backup_to(backup)["verified"])
        past = OneShotDispatchGate(backup, self.source)
        with self.assertRaises(PermissionError):
            past.reserve_once(
                principal=self.identity, request_id=self.id,
                expected_payload_sha256=self.digest,
                expected_base_revision=REV, current_server_revision=REV,
                send_key=SEND_KEY,
            )
        self.assertTrue(self.reserve()["firstAttemptGranted"])

    def test_schema_bounds_and_no_peer_ledger_or_credentials(self):
        self.digest = self.authorize()
        for bad in ("not-a-request", "B" * 32, "1" * 200):
            with self.assertRaises(DispatchGateError):
                self.reserve(request_id=bad)
        for bad in ("bad-key", "x" * 300, "../unsafe-key"):
            with self.assertRaises(DispatchGateError):
                self.reserve(send_key=bad)
        with self.assertRaises(DispatchGateError):
            self.reserve(expected_payload_sha256="wrong")
        with self.assertRaises(DispatchGateError):
            OneShotDispatchGate(self.root / "not-sqlite.db", self.source)
        self.reserve()
        self.assertEqual({p.name for p in self.root.iterdir() if p.is_file()}, {
            "host-outbox.sqlite3", "one-shot.sqlite3",
        })


if __name__ == "__main__":
    unittest.main()
