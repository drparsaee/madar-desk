"""Disposable no-transport recovery contract and explicit re-login blocker."""

from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from mtr_e2_dispatch_gate import DispatchGateConflict, OneShotDispatchGate
from mtr_e2_recovery_policy_pilot import (
    MtrE2RecoveryPolicyPilot, RecoveryPolicyBlocked,
)
from mtr_host_request_store import HostRequestStore
from mtr_lan_finance_adapter import MtrLanFinanceAdapter


ORG = "synthetic-office"
PROJECT = "p-original"
TOKEN_1 = "synthetic-login-ticket-a"
TOKEN_2 = "synthetic-login-ticket-b"
PREPARE_KEY = "prepare-recovery-0001"
SEND_KEY = "send-recovery-000001"
CARD = "synthetic-card-A"


class FakeBridge:
    def __init__(self):
        self._lock = threading.RLock()
        self.state = {"projects": [{"id": PROJECT}, {"id": "p-new"}], "tasks": [{
            "id": CARD, "projectId": PROJECT, "title": "First title",
            "boardId": "board-one", "listId": "todo",
        }]}

    def getState(self):
        return deepcopy(self.state)


class FakeHost:
    """Tests only: represents the host authentication authority, not a route."""

    def __init__(self):
        self.lock = threading.RLock()
        self.bridge = FakeBridge()
        self.sessions = {
            TOKEN_1: {"username": "alice", "role": "editor",
                      "financeEdit": True, "projects": [PROJECT],
                      "accountLineage": "0123456789abcdef0123456789abcdef"},
            TOKEN_2: {"username": "alice", "role": "editor",
                      "financeEdit": True, "projects": [PROJECT],
                      "accountLineage": "0123456789abcdef0123456789abcdef"},
            "other-actor-ticket": {"username": "bob", "role": "editor",
                                   "financeEdit": True, "projects": [PROJECT],
                                   "accountLineage": "fedcba9876543210fedcba9876543210"},
        }

    def account_for(self, token):
        if token not in self.sessions:
            raise PermissionError("no active host session")
        return dict(self.sessions[token])


class RecoveryPolicyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-e2-relogin-recovery-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        environmental = patch.dict(os.environ, {
            name: str(self.root) for name in (
                "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "HOME", "USERPROFILE"
            )
        })
        environmental.start()
        self.addCleanup(environmental.stop)
        self.service = FakeHost()
        self.source = HostRequestStore(self.root / "mtr-outbox.sqlite3")
        self.gate = OneShotDispatchGate(self.root / "mtr-once.sqlite3", self.source)
        self.host = MtrLanFinanceAdapter(self.service, self.source, org_id=ORG)
        self.policy = MtrE2RecoveryPolicyPilot(
            finance_adapter=self.host, dispatch_gate=self.gate,
        )
        self.request_id = uuid.uuid4().hex
        self.principal, task, self.revision = self.host._principal_and_task(TOKEN_1, CARD)
        self.payload = {
            "schema": 1, "source": "madar", "id": self.request_id,
            "taskId": CARD, "projectId": PROJECT, "title": task["title"],
            "createdUtc": "2026-11-10T02:00:00+00:00",
        }
        prepared = self.source.prepare_request(
            principal=self.principal, request_id=self.request_id,
            payload=self.payload, base_revision=self.revision,
            current_server_revision=self.revision, prepare_key=PREPARE_KEY,
            explicit_manual_action=True,
        )
        self.digest = prepared["payloadSha256"]
        self.source.manual_send(
            principal=self.principal, request_id=self.request_id,
            expected_payload_sha256=self.digest,
            expected_base_revision=self.revision,
            current_server_revision=self.revision,
            send_key=SEND_KEY, explicit_manual_action=True,
        )
        reserved = self.gate.reserve_once(
            principal=self.principal, request_id=self.request_id,
            expected_payload_sha256=self.digest,
            expected_base_revision=self.revision,
            current_server_revision=self.revision,
            send_key=SEND_KEY,
        )
        self.assertTrue(reserved["firstAttemptGranted"])

    def inspect(self, token=TOKEN_1, **updates):
        args = {
            "token": token, "task_id": CARD, "request_id": self.request_id,
            "base_revision": self.revision, "payload_sha256": self.digest,
            "send_key": SEND_KEY,
        }
        args.update(updates)
        return self.policy.inspect_existing(**args)

    def test_original_authenticated_session_can_inspect_without_send(self):
        before = self.gate.audit_events(
            principal=self.principal, request_id=self.request_id,
            expected_base_revision=self.revision,
        )
        result = self.inspect()
        self.assertEqual(result["requestId"], self.request_id)
        self.assertEqual(result["payloadSha256"], self.digest)
        self.assertEqual(result["sendKeySha256"], hashlib.sha256(
            SEND_KEY.encode("utf-8")
        ).hexdigest())
        self.assertNotIn("sendKey", result)
        self.assertEqual(result["baseRevision"], self.revision)
        self.assertEqual(result["sourceProjectId"], PROJECT)
        self.assertTrue(result["reservationConsumed"])
        self.assertTrue(result["mustQueryFirst"])
        self.assertFalse(result["mayDispatch"])
        self.assertFalse(result["canAutoRetry"])
        self.assertFalse(result["canResend"])
        self.assertFalse(result["peerQueryPerformed"])
        self.assertFalse(result["transportCalled"])
        self.assertFalse(result["financialEventCreated"])
        self.assertNotIn("title", result)
        self.assertNotIn("payload", result)
        self.assertEqual(before, self.gate.audit_events(
            principal=self.principal, request_id=self.request_id,
            expected_base_revision=self.revision,
        ))
        with self.assertRaises(DispatchGateConflict):
            self.gate.reserve_once(
                principal=self.principal, request_id=self.request_id,
                expected_payload_sha256=self.digest,
                expected_base_revision=self.revision,
                current_server_revision=self.revision, send_key=SEND_KEY,
            )

    def test_saved_title_and_board_move_same_project_keep_original_readable(self):
        task = self.service.bridge.state["tasks"][0]
        task["title"] = "Renamed, does not change original evidence"
        task["boardId"] = "board-two"
        task["listId"] = "done"
        self.assertNotEqual(self.host._principal_and_task(TOKEN_1, CARD)[2], self.revision)
        self.assertEqual(self.inspect()["payloadSha256"], self.digest)
        self.assertFalse(self.inspect()["canResend"])

    def test_same_actor_relogin_blocks_without_forging_original_session(self):
        fresh, _, _ = self.host._principal_and_task(TOKEN_2, CARD)
        self.assertEqual(fresh.user_id, self.principal.user_id)
        self.assertNotEqual(fresh.session_id, self.principal.session_id)
        with self.assertRaisesRegex(RecoveryPolicyBlocked, "re-login recovery requires"):
            self.inspect(token=TOKEN_2)
        # Test the actual store and gate APIs, not a hypothetical limitation.
        with self.assertRaises(PermissionError):
            self.source.request_snapshot(
                principal=fresh, request_id=self.request_id,
                expected_base_revision=self.revision,
            )
        with self.assertRaises(PermissionError):
            self.gate.status(
                principal=fresh, request_id=self.request_id,
                expected_base_revision=self.revision,
            )

    def test_other_actor_cannot_read_even_with_matching_project_grant(self):
        with self.assertRaises(RecoveryPolicyBlocked):
            self.inspect(token="other-actor-ticket")

    def test_unknown_and_expired_session_denied(self):
        with self.assertRaises(RecoveryPolicyBlocked):
            self.inspect(token="expired-token")
        self.service.sessions.pop(TOKEN_1)
        with self.assertRaises(RecoveryPolicyBlocked):
            self.inspect()

    def test_project_grant_revocation_denied(self):
        self.service.sessions[TOKEN_1]["projects"] = []
        with self.assertRaises(RecoveryPolicyBlocked):
            self.inspect()

    def test_role_and_finance_capability_revocation_denied(self):
        self.service.sessions[TOKEN_1]["financeEdit"] = False
        with self.assertRaises(RecoveryPolicyBlocked):
            self.inspect()
        self.service.sessions[TOKEN_1]["financeEdit"] = True
        self.service.sessions[TOKEN_1]["role"] = "viewer"
        with self.assertRaises(RecoveryPolicyBlocked):
            self.inspect()

    def test_cross_project_card_move_denied_even_with_both_grants(self):
        self.service.sessions[TOKEN_1]["projects"] = [PROJECT, "p-new"]
        self.service.bridge.state["tasks"][0]["projectId"] = "p-new"
        with self.assertRaises(RecoveryPolicyBlocked):
            self.inspect()

    def test_changed_digest_key_revision_and_request_id_denied(self):
        for changes in (
            {"payload_sha256": "0" * 64},
            {"send_key": "send-different-key-001"},
            {"base_revision": self.revision + 1},
            {"request_id": "e" * 32},
        ):
            with self.subTest(changes=changes), self.assertRaises(RecoveryPolicyBlocked):
                self.inspect(**changes)

    def test_unknown_org_and_outbox_gate_mismatch_denied(self):
        other_host = MtrLanFinanceAdapter(self.service, self.source, org_id="other-org")
        other = MtrE2RecoveryPolicyPilot(
            finance_adapter=other_host, dispatch_gate=self.gate,
        )
        with self.assertRaises(RecoveryPolicyBlocked):
            other.inspect_existing(
                token=TOKEN_1, task_id=CARD, request_id=self.request_id,
                base_revision=self.revision, payload_sha256=self.digest,
                send_key=SEND_KEY,
            )
        different_source = HostRequestStore(self.root / "other-outbox.sqlite3")
        with self.assertRaises(TypeError):
            MtrE2RecoveryPolicyPilot(
                finance_adapter=self.host,
                dispatch_gate=OneShotDispatchGate(
                    self.root / "other-gate.sqlite3", different_source,
                ),
            )

    def test_no_dispatch_reservation_denied_even_if_outbox_authorized(self):
        absent_gate = OneShotDispatchGate(self.root / "unreserved-gate.sqlite3", self.source)
        policy = MtrE2RecoveryPolicyPilot(
            finance_adapter=self.host, dispatch_gate=absent_gate,
        )
        with self.assertRaises(RecoveryPolicyBlocked):
            policy.inspect_existing(
                token=TOKEN_1, task_id=CARD, request_id=self.request_id,
                base_revision=self.revision, payload_sha256=self.digest,
                send_key=SEND_KEY,
            )

    def test_changed_durable_outbox_payload_does_not_pass_original_binding(self):
        # Synthetic *test-only* corruption: the adapter itself never opens
        # private DB files. Make a fully canonical changed proposal and hash
        # so the gate must compare its ORIGINAL reservation, not just rely on
        # malformed-JSON validation.
        alternative = dict(self.payload, title="changed after reservation")
        canonical = json.dumps(alternative, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False)
        altered_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.source.path)) as conn:
            conn.execute(
                "UPDATE requests SET payload_json=?,payload_sha256=? WHERE request_id=?",
                (canonical, altered_digest, self.request_id),
            )
            conn.commit()
        with self.assertRaises(RecoveryPolicyBlocked):
            self.inspect(payload_sha256=altered_digest)
        with self.assertRaises(RecoveryPolicyBlocked):
            self.inspect()


if __name__ == "__main__":
    unittest.main()
