"""Synthetic and isolated E2 SQLite host metadata outbox tests.

Every database is inside TemporaryDirectory. No live profile, finance ledger,
network, Taraz app or hosting service is accessed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import multiprocessing
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mtr_host_request_store import (  # noqa: E402
    HostRequestStore, StoreConflict, StoreError, TrustedPrincipal,
)


ORGANIZATION = "org-alpha"
PROJECT = "project-7"
REVISION = 9


def _process_prepare(db_path, request_id, payload, outcome_queue):
    """Child-process synthetic test worker; creates no profile or other files."""
    try:
        store = HostRequestStore(Path(db_path))
        result = store.prepare_request(
            principal=actor(), request_id=request_id, payload=payload,
            base_revision=REVISION, current_server_revision=REVISION,
            prepare_key="prepare-key-001", explicit_manual_action=True,
        )
        outcome_queue.put("reused" if result["idempotent"] else "inserted")
    except Exception as error:
        outcome_queue.put(type(error).__name__ + ": " + str(error))


def actor(**kwargs):
    props = {
        "user_id": "alice", "org_id": ORGANIZATION, "session_id": "session-primary",
        "role": "editor", "project_ids": frozenset({PROJECT}),
        "permissions": frozenset({"mtr.prepare", "mtr.manual_send", "mtr.read"}),
        "authenticated": True, "session_valid": True, "active": True,
    }
    props.update(kwargs)
    return TrustedPrincipal(**props)


def adapter(**kwargs):
    props = {
        "user_id": "taraz-bridge", "org_id": ORGANIZATION,
        "session_id": "adapter-session", "role": "taraz_adapter",
        "project_ids": frozenset({PROJECT}),
        "permissions": frozenset({"mtr.receipt_ingest"}),
        "authenticated": True, "session_valid": True, "active": True,
    }
    props.update(kwargs)
    return TrustedPrincipal(**props)


class StorePilotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mtr-host-store-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.db = self.directory / "outbox.sqlite3"
        self.store = HostRequestStore(self.db)
        self.request_id = uuid.uuid4().hex
        self.identity = actor()
        self.message = {
            "id": self.request_id,
            "schema": 1,
            "source": "madar",
            "taskId": "task-synthetic",
            "projectId": PROJECT,
            "title": "Illustrative printing task",
            "createdUtc": "2026-11-09T08:00:00+00:00",
            "amountRial": "15000",
        }

    def prepare(self, **kwargs):
        params = {
            "principal": self.identity, "request_id": self.request_id,
            "payload": self.message, "base_revision": REVISION,
            "current_server_revision": REVISION,
            "prepare_key": "prepare-key-001",
            "explicit_manual_action": True,
        }
        params.update(kwargs)
        return self.store.prepare_request(**params)

    def send(self, **kwargs):
        before = self.prepare()
        params = {
            "principal": self.identity, "request_id": self.request_id,
            "expected_payload_sha256": before["payloadSha256"],
            "expected_base_revision": REVISION,
            "current_server_revision": REVISION,
            "send_key": "stable-send-key-001",
            "explicit_manual_action": True,
        }
        params.update(kwargs)
        return self.store.manual_send(**params)

    def evidence(self, *, result="received", receipt_id="receipt-01", **overrides):
        sent = self.send()
        data = {
            "schema": 1, "source": "taraz", "observationId": "obs-00000001",
            "requestId": self.request_id, "orgId": ORGANIZATION, "projectId": PROJECT,
            "baseRevision": REVISION,
            "payloadSha256": self.prepare()["payloadSha256"],
            "sendKey": sent["sendKey"], "result": result,
            "receiptId": receipt_id if result == "received" else None,
            "observedUtc": "2026-11-09T08:00:01+00:00",
        }
        data.update(overrides)
        return data

    def ingest(self, evidence=None, **kwargs):
        params = {
            "principal": adapter(), "request_id": self.request_id,
            "evidence": self.evidence() if evidence is None else evidence,
            "verified_by_adapter": True,
        }
        params.update(kwargs)
        return self.store.record_query_result(**params)

    def seed_synthetic_historical_observation(self, *, result="received",
                                              receipt_id="receipt-01"):
        """TEST ONLY: direct SQLite fixture for historical-row integrity tests.

        Does NOT authenticate Taraz or simulate a successful official API;
        production ``record_query_result`` must NEVER call this helper.
        Only selected read/recovery/immutability tests inspect these rows.
        """
        proof = self.evidence(result=result, receipt_id=receipt_id)
        encoded = json.dumps(proof, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.db)) as raw:
            raw.execute(
                "INSERT INTO observations(observation_id,request_id,evidence_json,"
                "evidence_sha256,observer_id,observed_at) VALUES(?,?,?,?,?,?)",
                (proof["observationId"], self.request_id, encoded, digest,
                 "synthetic-legacy-fixture", proof["observedUtc"]),
            )
            raw.execute(
                "UPDATE requests SET receipt_state=?,receipt_id=? WHERE request_id=?",
                (result, receipt_id if result == "received" else None, self.request_id),
            )
            raw.commit()
        return proof

    def status(self, **kwargs):
        opts = {
            "principal": self.identity, "request_id": self.request_id,
            "expected_base_revision": REVISION,
        }
        opts.update(kwargs)
        return self.store.receipt_status(**opts)

    def test_prepare_persists_metadata_only_no_send(self):
        outcome = self.prepare()
        self.assertEqual(outcome["requestId"], self.request_id)
        self.assertEqual(outcome["requestState"], "PREPARED")
        self.assertEqual(outcome["receiptState"], "unknown")
        self.assertEqual(outcome["nextAction"], "explicit_manual_send_required")
        self.assertFalse(outcome["transportCalled"])
        self.assertFalse(outcome["financialEventCreated"])
        snapshot = self.store.request_snapshot(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )
        self.assertEqual(snapshot["payload"], self.message)
        self.assertEqual(snapshot["baseRevision"], REVISION)
        self.assertEqual(len(snapshot["payloadSha256"]), 64)
        self.assertEqual(len(self.store.audit_events(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )), 1)
        with closing(sqlite3.connect(self.db)) as db:
            tables = {x[0] for x in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        self.assertTrue({"requests", "observations", "audit"}.issubset(tables))
        for forbidden in ("finance_ledger", "invoices", "payments", "gl_entries"):
            self.assertNotIn(forbidden, tables)

    def test_prepare_identical_retry_idempotent_after_restart(self):
        self.assertFalse(self.prepare()["idempotent"])
        restarted = HostRequestStore(self.db)
        self.store = restarted
        self.assertTrue(self.prepare()["idempotent"])
        self.assertEqual(len(self.store.audit_events(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )), 1)

    def test_prepare_is_exclusive_on_request_id_prepare_key_or_actor(self):
        original = self.prepare()
        self.assertTrue(self.prepare()["idempotent"])
        for overrides in (
            {"prepare_key": "prepare-key-other"},
            {"payload": {**self.message, "title": "changed"}},
            {"base_revision": REVISION + 1, "current_server_revision": REVISION + 1},
            {"principal": actor(user_id="other")},
            {"principal": actor(session_id="different-session")},
        ):
            with self.subTest(change=overrides), self.assertRaises(
                (StoreConflict, PermissionError),
            ):
                self.prepare(**overrides)
        other_id = uuid.uuid4().hex
        with self.assertRaises(StoreConflict):
            self.prepare(
                request_id=other_id, payload={**self.message, "id": other_id},
                prepare_key="prepare-key-001",
            )
        self.assertEqual(original["payloadSha256"], self.prepare()["payloadSha256"])

    def test_session_role_capability_org_and_project_acls(self):
        other_org = actor(org_id="org-other")
        without_project = actor(project_ids=frozenset({"other-project"}))
        no_prepare = actor(permissions=frozenset({"mtr.read"}))
        wrong_role = actor(role="finance_reviewer")
        for bad in (
            without_project, no_prepare, wrong_role,
            actor(authenticated=False), actor(session_valid=False), actor(active=False),
        ):
            with self.subTest(principal=bad), self.assertRaises(PermissionError):
                self.prepare(principal=bad)
        self.prepare()
        with self.assertRaises(StoreConflict):
            self.prepare(principal=other_org)
        for bad in (
            other_org, without_project, actor(user_id="eve"),
            actor(session_id="other-session"), actor(authenticated=False),
            actor(session_valid=False), actor(active=False),
            actor(permissions=frozenset({"mtr.prepare"})),
        ):
            with self.subTest(principal=bad), self.assertRaises(PermissionError):
                self.status(principal=bad)
        with self.assertRaises(StoreConflict):
            self.status(expected_base_revision=REVISION + 1)

    def test_prepare_and_send_require_explicit_manual_actions(self):
        for value in (False, None, 0, 1):
            with self.subTest(value=value), self.assertRaises(PermissionError):
                self.prepare(explicit_manual_action=value)
        self.assertFalse(self.prepare()["idempotent"])
        for value in (False, None, 0, 1):
            with self.subTest(value=value), self.assertRaises(PermissionError):
                self.send(explicit_manual_action=value)
        self.assertEqual(self.status()["requestState"], "PREPARED")
        sent = self.send()
        self.assertEqual(sent["requestState"], "MANUAL_SEND_AUTHORIZED")
        self.assertEqual(sent["receiptState"], "unknown")
        self.assertEqual(sent["nextAction"], "query_taraz_first_hold_unknown")
        self.assertFalse(sent["transportCalled"])
        self.assertFalse(sent["financialEventCreated"])
        self.assertTrue(self.send()["idempotent"])
        self.assertEqual(len(self.store.audit_events(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )), 2)

    def test_manual_send_rejects_wrong_session_actor_role_and_revision(self):
        initial = self.prepare()
        for overrides in (
            {"principal": actor(user_id="eve")},
            {"principal": actor(session_id="other-session")},
            {"principal": actor(role="finance_reviewer")},
            {"principal": actor(permissions=frozenset({"mtr.prepare", "mtr.read"}))},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(PermissionError):
                self.send(**overrides)
        for overrides in (
            {"current_server_revision": REVISION + 1},
            {"expected_base_revision": REVISION - 1},
            {"expected_payload_sha256": "0" * 64},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(StoreConflict):
                self.send(**overrides)
        self.assertEqual(initial["requestState"], self.status()["requestState"])

    def test_send_key_conflict_and_same_send_key_immutable(self):
        self.send()
        with self.assertRaises(StoreConflict):
            self.send(send_key="different-send-key")
        second_id = uuid.uuid4().hex
        self.prepare(
            request_id=second_id,
            payload={**self.message, "id": second_id},
            prepare_key="prepare-key-002",
        )
        second = self.store.request_snapshot(
            principal=self.identity, request_id=second_id,
            expected_base_revision=REVISION,
        )
        with self.assertRaises(StoreConflict):
            self.store.manual_send(
                principal=self.identity, request_id=second_id,
                expected_payload_sha256=second["payloadSha256"],
                expected_base_revision=REVISION, current_server_revision=REVISION,
                send_key="stable-send-key-001", explicit_manual_action=True,
            )

    def test_query_first_unknown_is_not_authoritative_nonreceipt(self):
        self.send()
        self.assertEqual(self.status()["receiptState"], "unknown")
        self.assertEqual(self.status()["nextAction"], "query_taraz_first_hold_unknown")
        unknown = self.evidence(result="unknown", receipt_id=None)
        with self.assertRaises(PermissionError):
            self.ingest(unknown)
        self.assertEqual(self.status()["receiptState"], "unknown")
        self.assertEqual(self.status()["nextAction"], "query_taraz_first_hold_unknown")

    def test_unverified_received_cannot_promote_local_receipt_state(self):
        self.send()
        proof = self.evidence()
        with self.assertRaises(PermissionError):
            self.ingest(proof)
        with self.assertRaises(PermissionError):
            self.ingest(proof)
        self.assertIsNone(self.status()["receiptId"])
        self.assertEqual(self.status()["receiptState"], "unknown")
        self.assertEqual(len(self.store.audit_events(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )), 2)

    def test_unverified_not_received_is_not_authoritative_or_a_send(self):
        self.send()
        no_receipt = self.evidence(result="not_received")
        with self.assertRaises(PermissionError):
            self.ingest(no_receipt)
        self.assertEqual(
            self.status()["nextAction"],
            "query_taraz_first_hold_unknown",
        )
        self.assertFalse(self.status()["transportCalled"])
        with self.assertRaises(PermissionError):
            self.ingest(self.evidence(
                result="unknown", observationId="obs-00000002",
            ))
        confirmed = self.evidence(observationId="obs-00000003")
        with self.assertRaises(PermissionError):
            self.ingest(confirmed)
        self.assertEqual(self.status()["receiptState"], "unknown")

    def test_cannot_downgrade_or_replace_synthetic_historical_received_receipt(self):
        self.seed_synthetic_historical_observation()
        for new in (
            self.evidence(result="unknown", observationId="obs-00000002"),
            self.evidence(result="not_received", observationId="obs-00000003"),
            self.evidence(receiptId="receipt-OTHER", observationId="obs-00000004"),
        ):
            with self.subTest(new=new), self.assertRaises(PermissionError):
                self.ingest(new)
        self.assertIsNone(self.status()["receiptId"])
        self.assertEqual(self.status()["receiptState"], "unknown")
        self.assertEqual(self.status()["receiptVerification"], "UNVERIFIED")
        self.assertTrue(self.status()["historicalReceiptQuarantined"])
        with closing(sqlite3.connect(self.db)) as raw:
            self.assertEqual(raw.execute(
                "SELECT receipt_state,receipt_id FROM requests WHERE request_id=?",
                (self.request_id,),
            ).fetchone(), ("received", "receipt-01"))
        forensic = self.store.audit_events(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )
        self.assertTrue(all(event["receiptVerification"] == "UNVERIFIED"
                            and event["officialTarazReceipt"] is False
                            for event in forensic))

    def test_receipt_intake_rejects_all_caller_flags_including_true(self):
        self.send()
        for bad in (
            actor(),
            adapter(permissions=frozenset()),
            adapter(role="editor"),
            adapter(project_ids=frozenset()),
            adapter(org_id="other-org"),
            adapter(session_valid=False),
            adapter(authenticated=False),
            adapter(active=False),
        ):
            with self.subTest(bad=bad), self.assertRaises(PermissionError):
                self.ingest(principal=bad)
        for flag in (False, 0, 1, None, True):
            with self.subTest(flag=flag), self.assertRaises(PermissionError):
                self.ingest(verified_by_adapter=flag)
        self.assertEqual(self.status()["receiptState"], "unknown")

    def test_receipt_promotion_disabled_with_good_or_bad_request_binding(self):
        self.send()
        for field, value in (
            ("requestId", uuid.uuid4().hex), ("orgId", "other-org"),
            ("projectId", "other-project"), ("baseRevision", REVISION + 1),
            ("payloadSha256", "b" * 64), ("sendKey", "wrong-send-key"),
        ):
            with self.subTest(field=field), self.assertRaises(PermissionError):
                self.ingest(self.evidence(**{field: value}))
        with self.assertRaises(PermissionError):
            self.ingest(self.evidence())
        self.assertEqual(self.status()["receiptState"], "unknown")

    def test_malformed_receipt_and_unverified_schema_are_all_denied(self):
        self.send()
        data = self.evidence()
        samples = (
            {**data, "schema": 2},
            {**data, "source": "madar"},
            {**data, "result": "posted"},
            {**data, "result": "received", "receiptId": None},
            {**data, "result": "not_received", "receiptId": "receipt-forged"},
            {**data, "observedUtc": "not-a-date"},
            {**data, "baseRevision": True},
            {**data, "receiptId": "receipt\nforged"},
            {**data, "unrecognized": 1},
            {k: v for k, v in data.items() if k != "sendKey"},
            {"schema": 1, "state": "received"},
        )
        for bad in samples:
            with self.subTest(bad=bad), self.assertRaises(PermissionError):
                self.ingest(bad)
        self.assertEqual(self.status()["receiptState"], "unknown")

    def test_synthetic_historical_observation_cannot_be_replaced_by_disabled_ingest(self):
        initial = self.evidence(result="unknown")
        self.seed_synthetic_historical_observation(result="unknown")
        with self.assertRaises(PermissionError):
            self.ingest(self.evidence(
                result="received", receiptId="receipt-01",
                observationId=initial["observationId"],
            ))
        self.assertEqual(self.status()["receiptState"], "unknown")

    def test_historical_observation_replay_disallowed_for_any_claimed_adapter(self):
        proof = self.evidence(result="unknown")
        self.seed_synthetic_historical_observation(result="unknown")
        with self.assertRaises(PermissionError):
            self.ingest(proof, principal=adapter(user_id="other-taraz-adapter"))
        with self.assertRaises(PermissionError):
            self.ingest(proof)
        self.assertEqual(self.status()["receiptState"], "unknown")

    def test_observation_without_manual_send_is_denied(self):
        self.prepare()
        # Build evidence without invoking self.evidence (which sends).
        observed = {
            "schema": 1, "source": "taraz", "observationId": "obs-00000001",
            "requestId": self.request_id, "orgId": ORGANIZATION,
            "projectId": PROJECT, "baseRevision": REVISION,
            "payloadSha256": self.prepare()["payloadSha256"],
            "sendKey": "stable-send-key-001", "result": "received",
            "receiptId": "receipt-01", "observedUtc": "2026-11-09T08:00:01Z",
        }
        with self.assertRaises(PermissionError):
            self.ingest(observed)

    def test_corrupted_payload_and_receipt_observation_fail_closed(self):
        proof = self.seed_synthetic_historical_observation()
        with closing(sqlite3.connect(self.db)) as raw:
            raw.execute("UPDATE requests SET payload_json=? WHERE request_id=?",
                        ('{"unexpected":"tamper"}', self.request_id))
            raw.commit()
        with self.assertRaises(StoreError):
            self.status()
        with self.assertRaises(StoreError):
            self.prepare()
        # Restore original metadata to isolate evidence corruption test.
        # Derive canonical payload, not a user financial file.
        encoded = json.dumps(self.message, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False)
        with closing(sqlite3.connect(self.db)) as raw:
            raw.execute("UPDATE requests SET payload_json=? WHERE request_id=?",
                        (encoded, self.request_id))
            raw.execute(
                "UPDATE observations SET evidence_json=? WHERE request_id=?",
                ('{"corrupt":true}', self.request_id),
            )
            raw.commit()
        with self.assertRaises(PermissionError):
            self.ingest(proof)
        with self.assertRaises(StoreError):
            self.status()

    def test_missing_observation_cannot_support_confirmed_receipt_status(self):
        self.seed_synthetic_historical_observation()
        with closing(sqlite3.connect(self.db)) as raw:
            raw.execute(
                "DELETE FROM observations WHERE request_id=?", (self.request_id,),
            )
            raw.commit()
        with self.assertRaisesRegex(StoreError, "not supported"):
            self.status()

    def test_malformed_observation_cannot_become_readable_after_restart(self):
        self.seed_synthetic_historical_observation()
        with closing(sqlite3.connect(self.db)) as raw:
            raw.execute(
                "UPDATE observations SET evidence_sha256=? WHERE request_id=?",
                ("0" * 64, self.request_id),
            )
            raw.commit()
        another = HostRequestStore(self.db)
        with self.assertRaisesRegex(StoreError, "corrupt|unrelated"):
            another.receipt_status(
                principal=self.identity, request_id=self.request_id,
                expected_base_revision=REVISION,
            )

    def test_receipt_status_cannot_be_forged_without_evidence(self):
        self.send()
        with closing(sqlite3.connect(self.db)) as raw:
            raw.execute(
                "UPDATE requests SET receipt_state='received',receipt_id=? "
                "WHERE request_id=?",
                ("fake-receipt", self.request_id),
            )
            raw.commit()
        with self.assertRaises(StoreError):
            self.status()

    def test_receipt_result_is_not_allowed_to_exceed_observation_limit(self):
        self.send()
        # A corrupted database with excessive rows must fail closed rather than
        # scanning an unbounded history; this is not a performance benchmark.
        valid = self.evidence(result="unknown")
        canonical = json.dumps(valid, separators=(",", ":"), sort_keys=True)
        import hashlib
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.db)) as raw:
            raw.executemany(
                "INSERT INTO observations(observation_id,request_id,evidence_json,"
                "evidence_sha256,observer_id,observed_at) VALUES(?,?,?,?,?,?)",
                [(
                    f"obs-bulk-{i:08d}", self.request_id,
                    canonical.replace("obs-00000001", f"obs-bulk-{i:08d}"),
                    digest, "taraz-bridge", "2026-11-09T08:00:01Z",
                ) for i in range(257)],
            )
            raw.commit()
        with self.assertRaisesRegex(StoreError, "count exceeds"):
            self.status()

    def test_atomic_transaction_rolls_back_on_injected_db_audit_failure(self):
        self.prepare()
        with patch.object(HostRequestStore, "_audit", side_effect=RuntimeError("simulated failure")):
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                self.send()
        self.assertEqual(self.status()["requestState"], "PREPARED")
        self.assertEqual(len(self.store.audit_events(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )), 1)
        self.assertFalse(self.send()["idempotent"])

    def test_disabled_receipt_ingest_never_enters_audit_or_writes_observations(self):
        self.send()
        proof = self.evidence()
        with patch.object(HostRequestStore, "_audit", side_effect=OSError("audit fault")):
            with self.assertRaises(PermissionError):
                self.ingest(proof)
        self.assertEqual(self.status()["receiptState"], "unknown")
        with closing(sqlite3.connect(self.db)) as raw:
            self.assertEqual(raw.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 0)
        with self.assertRaises(PermissionError):
            self.ingest(proof)

    def test_sqlite_backup_is_consistent_nonoverwriting_and_restartable(self):
        self.seed_synthetic_historical_observation()
        backups = self.directory / "backups"
        backups.mkdir()
        destination = backups / "snap.sqlite3"
        result = self.store.backup_to(destination)
        self.assertTrue(result["verified"])
        self.assertTrue(destination.is_file())
        with self.assertRaises(FileExistsError):
            self.store.backup_to(destination)
        recovered = HostRequestStore(destination)
        restored_status = recovered.receipt_status(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )
        self.assertEqual(restored_status["receiptState"], "unknown")
        self.assertIsNone(restored_status["receiptId"])
        self.assertEqual(restored_status["receiptVerification"], "UNVERIFIED")
        self.assertTrue(restored_status["historicalReceiptQuarantined"])
        with closing(sqlite3.connect(destination)) as raw:
            self.assertEqual(raw.execute(
                "SELECT receipt_state,receipt_id FROM requests WHERE request_id=?",
                (self.request_id,),
            ).fetchone(), ("received", "receipt-01"))
        self.assertEqual(recovered.audit_events(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )[-1]["kind"], "manual_send_intent_only")

    def test_backup_does_not_overwrite_existing_data(self):
        self.prepare()
        dest = self.directory / "different.sqlite3"
        dest.write_bytes(b"KEEP_ORIGINAL")
        with self.assertRaises(FileExistsError):
            self.store.backup_to(dest)
        self.assertEqual(dest.read_bytes(), b"KEEP_ORIGINAL")

    def test_no_database_or_ledger_created_outside_synthetic_directory(self):
        with self.assertRaises(PermissionError):
            self.ingest()
        files = set(path.name for path in self.directory.rglob("*") if path.is_file())
        self.assertIn("outbox.sqlite3", files)
        self.assertFalse(any(name.endswith((".db", ".bak", ".ledger", ".json"))
                             for name in files))
        self.assertTrue(all("taraz" not in name.lower() for name in files))

    def test_schema_version_or_uninitialized_database_is_rejected(self):
        bad = self.directory / "uninitialized.sqlite3"
        with closing(sqlite3.connect(bad)) as conn:
            conn.execute("CREATE TABLE malicious (x INTEGER)")
            conn.commit()
        with self.assertRaises(StoreError):
            HostRequestStore(bad)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("PRAGMA user_version=66")
            conn.commit()
        with self.assertRaises(StoreError):
            HostRequestStore(self.db)

    def test_symlinked_database_or_parent_refused(self):
        alternative = self.directory / "not-store.sqlite3"
        try:
            alternative.symlink_to(self.db)
        except (OSError, NotImplementedError) as error:
            self.skipTest("Windows symlink privilege unavailable: " + str(error))
        with self.assertRaises(PermissionError):
            HostRequestStore(alternative)
        shortcut = self.directory / "shortcut"
        shortcut.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(PermissionError):
            HostRequestStore(shortcut / "outbox.sqlite3")

    def test_oversized_or_nonmetadata_payload_is_rejected(self):
        for bad in (
            {**self.message, "title": "x" * 40000},
            {**self.message, "ledger": "do-not-post"},
            {**self.message, "schema": True},
            {**self.message, "amountRial": 500},
            {**self.message, "amountRial": "0.1"},
            {**self.message, "amountRial": "9007199254740992"},
            {**self.message, "projectId": "other-project"},
            {**self.message, "title": float("nan")},
        ):
            with self.subTest(bad=list(bad)), self.assertRaises(
                (StoreError, PermissionError),
            ):
                self.prepare(payload=bad)
        self.assertEqual(self.db.is_file(), True)

    def test_concurrent_identical_prepare_and_send_only_once(self):
        with ThreadPoolExecutor(max_workers=10) as pool:
            tasks = [pool.submit(self.prepare) for _ in range(10)]
            outcomes = [task.result(timeout=20) for task in tasks]
        self.assertEqual(sum(not result["idempotent"] for result in outcomes), 1)
        self.assertEqual(len({result["payloadSha256"] for result in outcomes}), 1)
        with ThreadPoolExecutor(max_workers=10) as pool:
            tasks = [pool.submit(self.send) for _ in range(10)]
            sent = [task.result(timeout=20) for task in tasks]
        self.assertEqual(sum(not result["idempotent"] for result in sent), 1)
        self.assertEqual(len(self.store.audit_events(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )), 2)

    def test_concurrent_conflicting_send_key_only_one_wins(self):
        before = self.prepare()
        def authorize(key):
            return self.store.manual_send(
                principal=self.identity, request_id=self.request_id,
                expected_payload_sha256=before["payloadSha256"],
                expected_base_revision=REVISION, current_server_revision=REVISION,
                send_key=key, explicit_manual_action=True,
            )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(authorize, "send-key-A1"),
                       pool.submit(authorize, "send-key-B2")]
            outcomes = []
            for future in results:
                try:
                    outcomes.append(future.result(timeout=20)["sendKey"])
                except StoreConflict:
                    outcomes.append("conflict")
        self.assertEqual(outcomes.count("conflict"), 1)
        self.assertEqual(len([x for x in outcomes if x != "conflict"]), 1)

    def test_multiple_windows_processes_prepare_once_with_immediate_lock(self):
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        children = [
            context.Process(target=_process_prepare, args=(
                str(self.db), self.request_id, dict(self.message), queue,
            ))
            for _ in range(4)
        ]
        for child in children:
            child.start()
        results = [queue.get(timeout=30) for _ in children]
        for child in children:
            child.join(timeout=30)
            self.assertEqual(child.exitcode, 0)
        self.assertEqual(results.count("inserted"), 1, results)
        self.assertEqual(results.count("reused"), 3, results)
        self.assertEqual(len(self.store.audit_events(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )), 1)

    def test_restart_after_prepare_or_unknown_preserves_query_first(self):
        self.prepare()
        first = HostRequestStore(self.db)
        self.assertEqual(first.receipt_status(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )["requestState"], "PREPARED")
        self.send()
        again = HostRequestStore(self.db)
        self.assertEqual(again.receipt_status(
            principal=self.identity, request_id=self.request_id,
            expected_base_revision=REVISION,
        )["nextAction"], "query_taraz_first_hold_unknown")
        proof = self.evidence(result="not_received")
        with self.assertRaises(PermissionError):
            again.record_query_result(
                principal=adapter(), request_id=self.request_id,
                evidence=proof, verified_by_adapter=True,
            )
        self.store = HostRequestStore(self.db)
        self.assertEqual(self.status()["receiptState"], "unknown")


if __name__ == "__main__":
    unittest.main()
