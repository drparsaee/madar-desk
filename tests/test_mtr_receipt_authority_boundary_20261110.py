"""F1/E2 receipt-ingest authority DENY regression, local temporary SQLite only.

This module first reproduced a forgeable in-process receipt-ingest boundary.
After owner-approved mitigation, every synthetic forged receipt must be denied
without a production bypass; it does not sign real Taraz receipts, start
services, access profiles or establish an unauthenticated HTTP exploit.
"""

from __future__ import annotations

import ast
from pathlib import Path
from contextlib import closing
from dataclasses import replace
import hashlib
import json
import sqlite3
import tempfile
import unittest

from mtr_e2_dispatch_gate import OneShotDispatchGate
from mtr_host_request_store import HostRequestStore, TrustedPrincipal


ORG = "qa-only-org"
PROJECT = "qa-only-project"
REQUEST = "a" * 32
REVISION = 9
SEND_KEY = "qa-send-key-0001"
RECEIPT_ID = "qa-fake-receipt-not-from-taraz"


def _principal(*, role="editor", permissions=None, user="qa-owner"):
    return TrustedPrincipal(
        user_id=user, org_id=ORG, session_id="qa-session", role=role,
        project_ids=frozenset({PROJECT}),
        permissions=frozenset(permissions if permissions is not None else (
            "mtr.prepare", "mtr.manual_send", "mtr.read"
        )),
        authenticated=True, session_valid=True, active=True,
    )


class ReceiptAuthorityBoundaryCharacterization(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-receipt-authority-qa-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = HostRequestStore(self.root / "synthetic-outbox.sqlite3")
        self.owner = _principal()
        self.payload = {
            "schema": 1, "source": "madar", "id": REQUEST,
            "taskId": "synthetic-task", "projectId": PROJECT,
            "title": "QA only, no real financial receipt",
            "createdUtc": "2026-11-10T00:00:00+00:00",
        }
        self.prepared = self.store.prepare_request(
            principal=self.owner, request_id=REQUEST, payload=self.payload,
            base_revision=REVISION, current_server_revision=REVISION,
            prepare_key="qa-prepare-key-0001", explicit_manual_action=True,
        )
        self.sent = self.store.manual_send(
            principal=self.owner, request_id=REQUEST,
            expected_payload_sha256=self.prepared["payloadSha256"],
            expected_base_revision=REVISION, current_server_revision=REVISION,
            send_key=SEND_KEY, explicit_manual_action=True,
        )
        self.assertEqual(self.sent["receiptState"], "unknown")

    @staticmethod
    def fake_adapter():
        # Anyone with access to this Python API can construct this object.
        return _principal(
            user="impostor-taraz-adapter", role="taraz_adapter",
            permissions={"mtr.receipt_ingest"},
        )

    def fabricated_evidence(self, *, result="received", **changes):
        obj = {
            "schema": 1, "source": "taraz", "observationId": "qa-observation-0001",
            "requestId": REQUEST, "orgId": ORG, "projectId": PROJECT,
            "baseRevision": REVISION,
            "payloadSha256": self.prepared["payloadSha256"],
            "sendKey": SEND_KEY, "result": result,
            "receiptId": RECEIPT_ID if result == "received" else None,
            "observedUtc": "2026-11-10T00:01:00+00:00",
        }
        obj.update(changes)
        return obj

    def ingest(self, *, principal=None, verified_by_adapter=True, evidence=None):
        return self.store.record_query_result(
            principal=self.fake_adapter() if principal is None else principal,
            request_id=REQUEST,
            evidence=self.fabricated_evidence() if evidence is None else evidence,
            verified_by_adapter=verified_by_adapter,
        )

    def status(self):
        return self.store.receipt_status(
            principal=self.owner, request_id=REQUEST,
            expected_base_revision=REVISION,
        )

    def seed_historical_unverified(self, result):
        """TEST ONLY. Insert a consistent pre-verifier observation into temp DB."""
        self.assertIn(result, ("received", "not_received"))
        evidence = self.fabricated_evidence(result=result)
        encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.store.path)) as db:
            db.execute(
                "INSERT INTO observations(observation_id,request_id,evidence_json,"
                "evidence_sha256,observer_id,observed_at) VALUES(?,?,?,?,?,?)",
                (evidence["observationId"], REQUEST, encoded, digest,
                 "synthetic-pre-verifier", evidence["observedUtc"]),
            )
            db.execute(
                "UPDATE requests SET receipt_state=?,receipt_id=? WHERE request_id=?",
                (result, evidence["receiptId"], REQUEST),
            )
            db.commit()
        return evidence

    def test_historical_received_row_quarantined_in_all_public_store_reads(self):
        self.seed_historical_unverified("received")
        for reader in (
            lambda: self.status(),
            lambda: self.store.request_snapshot(
                principal=self.owner, request_id=REQUEST,
                expected_base_revision=REVISION,
            ),
            lambda: HostRequestStore(self.store.path).receipt_status(
                principal=self.owner, request_id=REQUEST,
                expected_base_revision=REVISION,
            ),
        ):
            with self.subTest(reader=reader):
                result = reader()
                self.assertEqual(result["receiptState"], "unknown")
                self.assertIsNone(result["receiptId"])
                self.assertEqual(result["receiptVerification"], "UNVERIFIED")
                self.assertTrue(result["historicalReceiptQuarantined"])
                self.assertEqual(result["nextAction"], "query_taraz_first_hold_unknown")
                self.assertFalse(result["canAutoRetry"])
                self.assertNotIn(RECEIPT_ID, repr(result))
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertEqual(db.execute(
                "SELECT receipt_state,receipt_id FROM requests WHERE request_id=?",
                (REQUEST,),
            ).fetchone(), ("received", RECEIPT_ID))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 1)

    def test_historical_not_received_row_never_creates_resend_hint(self):
        self.seed_historical_unverified("not_received")
        result = self.status()
        self.assertEqual(result["receiptState"], "unknown")
        self.assertIsNone(result["receiptId"])
        self.assertTrue(result["historicalReceiptQuarantined"])
        self.assertEqual(result["receiptVerification"], "UNVERIFIED")
        self.assertFalse(result["canAutoRetry"])
        self.assertNotEqual(result["nextAction"],
                            "same_key_replay_only_after_authoritative_query")
        self.assertEqual(result["nextAction"], "query_taraz_first_hold_unknown")

    def test_normal_unknown_remains_non_confirmed_and_no_quarantine(self):
        result = self.status()
        self.assertEqual(result["receiptState"], "unknown")
        self.assertIsNone(result["receiptId"])
        self.assertFalse(result["historicalReceiptQuarantined"])
        self.assertEqual(result["receiptVerification"], "UNVERIFIED")
        self.assertFalse(result["canAutoRetry"])
        self.assertEqual(result["nextAction"], "query_taraz_first_hold_unknown")

    def test_normal_unknown_can_still_reserve_exactly_one_first_slot(self):
        gate = OneShotDispatchGate(self.root / "clean-one-shot.sqlite3", self.store)
        first = gate.reserve_once(
            principal=self.owner, request_id=REQUEST,
            expected_payload_sha256=self.prepared["payloadSha256"],
            expected_base_revision=REVISION, current_server_revision=REVISION,
            send_key=SEND_KEY,
        )
        self.assertTrue(first["firstAttemptGranted"])
        self.assertTrue(first["reservationConsumed"])
        self.assertFalse(first["historicalReceiptQuarantined"])
        self.assertFalse(first["mayDispatch"])
        with self.assertRaises((ValueError, PermissionError)):
            gate.reserve_once(
                principal=self.owner, request_id=REQUEST,
                expected_payload_sha256=self.prepared["payloadSha256"],
                expected_base_revision=REVISION, current_server_revision=REVISION,
                send_key=SEND_KEY,
            )

    def test_historical_quarantine_preserves_original_actor_acl(self):
        self.seed_historical_unverified("received")
        gate = OneShotDispatchGate(self.root / "acl-one-shot.sqlite3", self.store)
        own = replace(self.owner, user_id="unrelated-synthetic-actor")
        with self.assertRaises(PermissionError):
            self.store.receipt_status(
                principal=own, request_id=REQUEST,
                expected_base_revision=REVISION,
            )
        with self.assertRaises(PermissionError):
            self.store.request_snapshot(
                principal=own, request_id=REQUEST,
                expected_base_revision=REVISION,
            )
        with self.assertRaises(PermissionError):
            gate.reserve_once(
                principal=own, request_id=REQUEST,
                expected_payload_sha256=self.prepared["payloadSha256"],
                expected_base_revision=REVISION, current_server_revision=REVISION,
                send_key=SEND_KEY,
            )

    def test_history_does_not_authorize_new_dispatch_or_gate_confirmation(self):
        gate = OneShotDispatchGate(self.root / "historical-one-shot.sqlite3", self.store)
        first = gate.reserve_once(
            principal=self.owner, request_id=REQUEST,
            expected_payload_sha256=self.prepared["payloadSha256"],
            expected_base_revision=REVISION, current_server_revision=REVISION,
            send_key=SEND_KEY,
        )
        self.assertTrue(first["firstAttemptGranted"])
        self.seed_historical_unverified("received")
        with self.assertRaises(PermissionError):
            gate.observe_received(
                principal=self.owner, request_id=REQUEST,
                expected_base_revision=REVISION, expected_version=1,
            )
        public = gate.status(principal=self.owner, request_id=REQUEST,
                             expected_base_revision=REVISION)
        self.assertEqual(public["state"], "reserved_before_network")
        self.assertIsNone(public["receiptId"])
        self.assertTrue(public["historicalReceiptQuarantined"])
        self.assertFalse(public["mayDispatch"])
        self.assertTrue(public["mustQueryFirst"])
        self.assertEqual(public["receiptVerification"], "UNVERIFIED")
        with self.assertRaises((PermissionError, ValueError)):
            gate.reserve_once(
                principal=self.owner, request_id=REQUEST,
                expected_payload_sha256=self.prepared["payloadSha256"],
                expected_base_revision=REVISION, current_server_revision=REVISION,
                send_key=SEND_KEY,
            )

    def test_historical_received_before_first_reservation_refuses_new_slot(self):
        self.seed_historical_unverified("received")
        gate = OneShotDispatchGate(self.root / "unreserved-one-shot.sqlite3", self.store)
        with self.assertRaises((PermissionError, ValueError)):
            gate.reserve_once(
                principal=self.owner, request_id=REQUEST,
                expected_payload_sha256=self.prepared["payloadSha256"],
                expected_base_revision=REVISION, current_server_revision=REVISION,
                send_key=SEND_KEY,
            )
        with closing(sqlite3.connect(gate.path)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM dispatch_reservations",
            ).fetchone()[0], 0)

    def test_forged_constructed_adapter_true_flag_cannot_promote_received(self):
        """Former bug: direct forged adapter used to record a fake local receipt."""
        with self.assertRaisesRegex(PermissionError, "authority not configured"):
            self.ingest()
        self.assertEqual(self.status()["receiptState"], "unknown")
        self.assertIsNone(self.status()["receiptId"])
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 2)
        reopened = HostRequestStore(self.store.path)
        self.assertEqual(reopened.receipt_status(
            principal=self.owner, request_id=REQUEST,
            expected_base_revision=REVISION,
        )["receiptState"], "unknown")

    def test_forged_not_received_cannot_mint_false_replay_recommendation(self):
        with self.assertRaises(PermissionError):
            self.ingest(evidence=self.fabricated_evidence(result="not_received"))
        self.assertEqual(self.status()["receiptState"], "unknown")
        self.assertEqual(self.status()["nextAction"], "query_taraz_first_hold_unknown")

    def test_all_caller_flags_and_roles_fail_even_with_valid_metadata(self):
        for flag in (False, None, 0, 1, True):
            with self.subTest(flag=flag), self.assertRaises(PermissionError):
                self.ingest(verified_by_adapter=flag)
        for invalid_actor in (
            self.owner, self.fake_adapter().__class__(
                user_id="impostor", org_id=ORG, session_id="fake-session",
                role="editor", project_ids=frozenset({PROJECT}),
                permissions=frozenset({"mtr.receipt_ingest"}),
                authenticated=True, session_valid=True, active=True,
            ),
        ):
            with self.assertRaises(PermissionError):
                self.ingest(principal=invalid_actor)
        self.assertEqual(self.status()["receiptState"], "unknown")

    def test_downstream_dispatch_gate_cannot_accept_forged_local_received(self):
        """No downstream receipt transition without an upstream trusted receipt.

        This never performs a dispatch, sends packets, or changes finance books.
        """
        gate = OneShotDispatchGate(self.root / "synthetic-one-shot.sqlite3", self.store)
        first = gate.reserve_once(
            principal=self.owner, request_id=REQUEST,
            expected_payload_sha256=self.prepared["payloadSha256"],
            expected_base_revision=REVISION, current_server_revision=REVISION,
            send_key=SEND_KEY,
        )
        self.assertTrue(first["firstAttemptGranted"])
        self.assertFalse(first["mayDispatch"])
        with self.assertRaises(PermissionError):
            self.ingest()
        with self.assertRaises(PermissionError):
            gate.observe_received(
                principal=self.owner, request_id=REQUEST,
                expected_base_revision=REVISION, expected_version=1,
            )
        self.assertFalse(gate.status(
            principal=self.owner, request_id=REQUEST,
            expected_base_revision=REVISION,
        )["mayDispatch"])

    def test_incorrect_and_exactly_matched_metadata_both_fail_without_authority(self):
        with self.assertRaises(PermissionError):
            self.ingest(evidence=self.fabricated_evidence(
                payloadSha256="0" * 64,
            ))
        with self.assertRaises(PermissionError):
            self.ingest(evidence=self.fabricated_evidence(
                sendKey="different-synthetic-send-key",
            ))
        self.assertEqual(self.status()["receiptState"], "unknown")
        with self.assertRaises(PermissionError):
            self.ingest()

    def test_desired_security_contract_rejects_forged_adapter_without_verifier(self):
        """Now an ordinary passing deny assertion; no expected-failure masking."""
        with self.assertRaises(PermissionError):
            self.ingest()

    def test_unknown_metadata_must_not_be_promoted_to_official_receipt_log(self):
        with self.assertRaises(PermissionError):
            self.ingest(evidence=self.fabricated_evidence(result="unknown"))
        self.assertEqual(self.status()["receiptState"], "unknown")
        self.assertFalse(self.status()["financialEventCreated"])

    def test_static_lan_route_and_integration_boundary_not_receipt_ingest(self):
        """Source inspection, NOT a penetration test of running HTTP service."""
        repo = Path(__file__).resolve().parents[1]
        lan_source = (repo / "lan.py").read_text(encoding="utf-8")
        adapter_source = (repo / "mtr_lan_finance_adapter.py").read_text(
            encoding="utf-8")
        lan_ast = ast.parse(lan_source)
        lan_names = {n.value for n in ast.walk(lan_ast)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertTrue({
            "/api/mtr/v2/prepare", "/api/mtr/v2/manual-send",
            "/api/mtr/v2/status",
        }.issubset(lan_names))
        self.assertNotIn("record_query_result", lan_source)
        self.assertNotIn("record_query_result", adapter_source)
        from mtr_lan_finance_adapter import _ROUTES
        self.assertEqual(_ROUTES, frozenset({"prepare", "manual-send", "status"}))


if __name__ == "__main__":
    unittest.main()
