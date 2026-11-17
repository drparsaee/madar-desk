"""E2 re-login security audit: isolated host fixtures and no peer/network I/O.

These tests exercise the CURRENT production readers. A forged in-process
TrustedPrincipal test deliberately documents a proven trust-boundary gap; it
does NOT claim a remote caller can reach the internal API.
"""

from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from mtr_e2_dispatch_gate import (
    DispatchGateConflict, DispatchGateError, OneShotDispatchGate,
)
from mtr_account_lineage import principal_actor_id
from mtr_e2_host_peer_pilot import HostPeerPilotDenied, MtrE2HostPeerPilot
from mtr_host_request_store import HostRequestStore, StoreConflict, StoreError, TrustedPrincipal
from mtr_host_principal_provenance import (
    HostPrincipalProvenance, OUTBOX_RECOVERY, GATE_RECOVERY,
    PrincipalProvenanceDenied,
)
from mtr_lan_finance_adapter import MtrLanFinanceAdapter


ORG = "synthetic-org-recovery"
PROJECT = "synthetic-project-a"
OTHER_PROJECT = "synthetic-project-b"
TASK = "synthetic-task-one"
OLD_TOKEN = "synthetic-first-session-token"
NEW_TOKEN = "synthetic-new-session-token"
OTHER_TOKEN = "synthetic-second-user-token"
PREPARE_KEY = "synthetic-prepare-key"
SEND_KEY = "synthetic-send-key"


class SyntheticBridge:
    def __init__(self):
        self._lock = threading.RLock()
        self.state = {
            "projects": [{"id": PROJECT}, {"id": OTHER_PROJECT}],
            "tasks": [{"id": TASK, "projectId": PROJECT,
                       "title": "Original evidence only", "listId": "todo"}],
        }

    def getState(self):
        return deepcopy(self.state)


class SyntheticHost:
    """A controlled stand-in for current host authentication, never a route."""

    def __init__(self):
        self.lock = threading.RLock()
        self.bridge = SyntheticBridge()
        alice_lineage = "0123456789abcdef0123456789abcdef"
        mallory_lineage = "fedcba9876543210fedcba9876543210"
        self.users = {
            "alice": {"username": "alice", "role": "editor",
                      "financeEdit": True, "projects": [PROJECT],
                      "accountLineage": alice_lineage},
            "mallory": {"username": "mallory", "role": "editor",
                        "financeEdit": True, "projects": [PROJECT],
                        "accountLineage": mallory_lineage},
        }
        self.sessions = {OLD_TOKEN: "alice", NEW_TOKEN: "alice",
                         OTHER_TOKEN: "mallory"}

    def account_for(self, token):
        if token not in self.sessions:
            raise PermissionError("unknown or revoked host session")
        return self.users[self.sessions[token]]


class MockPeerNoNetwork:
    def __init__(self):
        self.queries = []

    def query_verified(self, signed, *, at, query_request_id):
        self.queries.append((signed, at, query_request_id))
        return {"lookupStatus": "unknown", "peerEnvelopeSha256": "e" * 64}


class ReloginRecoverySecurityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-e2-recovery-security-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = patch.dict(os.environ, {
            name: str(self.root) for name in (
                "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "HOME", "USERPROFILE"
            )
        })
        env.start()
        self.addCleanup(env.stop)

        self.host = SyntheticHost()
        self.outbox = HostRequestStore(self.root / "request-outbox.sqlite3")
        self.gate = OneShotDispatchGate(self.root / "dispatch-gate.sqlite3", self.outbox)
        self.adapter = MtrLanFinanceAdapter(self.host, self.outbox, org_id=ORG)
        self.issuer = HostPrincipalProvenance(self.host, org_id=ORG)
        self.outbox.bind_recovery_provenance(self.issuer)
        self.original, card, self.revision = self.adapter._principal_and_task(
            OLD_TOKEN, TASK,
        )
        self.id = uuid.uuid4().hex
        proposal = {
            "schema": 1, "source": "madar", "id": self.id,
            "taskId": TASK, "projectId": PROJECT, "title": card["title"],
            "createdUtc": "2026-11-10T00:00:00+00:00",
        }
        prepared = self.outbox.prepare_request(
            principal=self.original, request_id=self.id, payload=proposal,
            base_revision=self.revision, current_server_revision=self.revision,
            prepare_key=PREPARE_KEY, explicit_manual_action=True,
        )
        self.digest = prepared["payloadSha256"]
        self.outbox.manual_send(
            principal=self.original, request_id=self.id,
            expected_payload_sha256=self.digest,
            expected_base_revision=self.revision,
            current_server_revision=self.revision, send_key=SEND_KEY,
            explicit_manual_action=True,
        )
        initial = self.gate.reserve_once(
            principal=self.original, request_id=self.id,
            expected_payload_sha256=self.digest,
            expected_base_revision=self.revision,
            current_server_revision=self.revision, send_key=SEND_KEY,
        )
        self.assertTrue(initial["firstAttemptGranted"])

    def recovery(self, token=NEW_TOKEN, request_id=None, revision=None):
        principal = self.adapter._recovery_principal(token)
        return self.gate.recovery_status(
            principal=principal, request_id=request_id or self.id,
            expected_base_revision=(self.revision if revision is None else revision),
            **self.proofs(token),
        )

    def proofs(self, token):
        return {
            "token": token,
            "gate_seal": self.issuer.issue_recovery(token, audience=GATE_RECOVERY),
            "outbox_seal": self.issuer.issue_recovery(token, audience=OUTBOX_RECOVERY),
        }

    def snapshot(self, token=NEW_TOKEN, principal=None, request_id=None):
        return self.outbox.recovery_snapshot(
            principal=principal or self.adapter._recovery_principal(token),
            request_id=request_id or self.id,
            expected_base_revision=self.revision,
            token=token,
            seal=self.issuer.issue_recovery(token, audience=OUTBOX_RECOVERY),
        )

    def test_real_host_relogin_read_only_with_original_request_and_no_new_permit(self):
        fresh = self.adapter._recovery_principal(NEW_TOKEN)
        self.assertEqual(fresh.user_id, self.original.user_id)
        self.assertNotEqual(fresh.session_id, self.original.session_id)
        self.assertEqual(fresh.permissions, frozenset({"mtr.read"}))
        snapshot = self.snapshot(principal=fresh)
        self.assertEqual(snapshot["originalSessionId"], self.original.session_id)
        self.assertEqual(snapshot["payloadSha256"], self.digest)
        status = self.recovery()
        self.assertTrue(status["reservationConsumed"])
        self.assertFalse(status["mayDispatch"])
        self.assertNotIn("firstAttemptGranted", status)
        with self.assertRaises(PermissionError):
            self.gate.status(
                principal=fresh, request_id=self.id,
                expected_base_revision=self.revision,
            )
        with self.assertRaises(PermissionError):
            self.outbox.request_snapshot(
                principal=fresh, request_id=self.id,
                expected_base_revision=self.revision,
            )
        with self.assertRaises(PermissionError):
            self.gate.reserve_once(
                principal=fresh, request_id=self.id,
                expected_payload_sha256=self.digest,
                expected_base_revision=self.revision,
                current_server_revision=self.revision, send_key=SEND_KEY,
            )

    def test_current_user_role_and_finance_grant_revoked(self):
        for role, finance in (("viewer", True), ("editor", False)):
            with self.subTest(role=role, financeEdit=finance):
                account = self.host.users["alice"]
                account.update(role=role, financeEdit=finance)
                with self.assertRaises(PermissionError):
                    self.recovery()
                account.update(role="editor", financeEdit=True)

    def test_current_project_grant_or_registry_removed_denies_recovery(self):
        self.host.users["alice"]["projects"] = [OTHER_PROJECT]
        with self.assertRaises(PermissionError):
            self.recovery()
        self.host.users["alice"]["projects"] = [PROJECT]
        self.host.bridge.state["projects"] = [{"id": OTHER_PROJECT}]
        with self.assertRaises(PermissionError):
            self.recovery()

    def test_wrong_user_and_org_denied_even_with_matching_revision(self):
        with self.assertRaises(PermissionError):
            self.recovery(token=OTHER_TOKEN)
        other_adapter = MtrLanFinanceAdapter(
            self.host, self.outbox, org_id="another-organization",
        )
        wrong_org = other_adapter._recovery_principal(NEW_TOKEN)
        with self.assertRaises(PermissionError):
            self.gate.recovery_status(
                principal=wrong_org, request_id=self.id,
                expected_base_revision=self.revision,
                **self.proofs(NEW_TOKEN),
            )

    def test_expired_or_invalid_token_rejected_by_host(self):
        with self.assertRaises(PermissionError):
            self.recovery(token="unissued-token")
        self.host.sessions.pop(NEW_TOKEN)
        with self.assertRaises(PermissionError):
            self.recovery()

    def test_stale_revision_unknown_id_missing_gate_and_prepared_only_fail(self):
        with self.assertRaises(StoreConflict):
            self.recovery(revision=self.revision + 1)
        with self.assertRaises(KeyError):
            self.recovery(request_id="0" * 32)
        isolated_gate = OneShotDispatchGate(self.root / "empty-gate.sqlite3", self.outbox)
        with self.assertRaises(KeyError):
            isolated_gate.recovery_status(
                principal=self.adapter._recovery_principal(NEW_TOKEN),
                request_id=self.id, expected_base_revision=self.revision,
                **self.proofs(NEW_TOKEN),
            )
        unsigned_id = uuid.uuid4().hex
        self.outbox.prepare_request(
            principal=self.original, request_id=unsigned_id,
            payload={"schema": 1, "source": "madar", "id": unsigned_id,
                     "taskId": TASK, "projectId": PROJECT, "title": "Not sent",
                     "createdUtc": "2026-11-10T00:00:00+00:00"},
            base_revision=self.revision, current_server_revision=self.revision,
            prepare_key="different-prepare-key", explicit_manual_action=True,
        )
        with self.assertRaises(StoreConflict):
            self.outbox.recovery_snapshot(
                principal=self.adapter._recovery_principal(NEW_TOKEN),
                request_id=unsigned_id, expected_base_revision=self.revision,
                token=NEW_TOKEN,
                seal=self.issuer.issue_recovery(NEW_TOKEN, audience=OUTBOX_RECOVERY),
            )

    def test_deleted_or_renamed_card_keeps_original_queryable_but_not_sendable(self):
        card = self.host.bridge.state["tasks"][0]
        card.update(title="Changed title", listId="completed", projectId=OTHER_PROJECT)
        self.assertTrue(self.recovery()["reservationConsumed"])
        self.host.bridge.state["tasks"] = []
        self.assertFalse(self.recovery()["mayDispatch"])
        with self.assertRaises(PermissionError):
            self.adapter._principal_and_task(NEW_TOKEN, TASK)

    def test_relogin_coordinator_query_first_with_deleted_card_no_network(self):
        self.host.bridge.state["tasks"] = []
        peer = MockPeerNoNetwork()
        coordinator = object.__new__(MtrE2HostPeerPilot)
        coordinator._host = self.adapter
        coordinator._gate = self.gate
        coordinator._peer = peer
        coordinator._journal = None
        coordinator._provenance = self.issuer
        with patch.object(MtrE2HostPeerPilot, "_sign_host_only",
                          return_value=b"dummy-signed-request"), patch.object(
                              self.gate, "reserve_once",
                              side_effect=AssertionError("recovery may not grant a dispatch slot"),
                          ):
            found = coordinator.query_first(
                token=NEW_TOKEN, task_id=TASK, request_id=self.id,
                base_revision=self.revision,
            )
            self.assertEqual(found["lookupStatus"], "unknown")
            self.assertFalse(found["canAutoRetry"])
            self.assertEqual(len(peer.queries), 1)
            with self.assertRaises(HostPeerPilotDenied):
                coordinator.query_first(
                    token=NEW_TOKEN, task_id="different-card", request_id=self.id,
                    base_revision=self.revision,
                )
            self.assertEqual(len(peer.queries), 1)

    def test_privilege_flag_and_principal_structure_denials(self):
        legit = self.adapter._recovery_principal(NEW_TOKEN)
        for attributes in (
            {"authenticated": False}, {"session_valid": False},
            {"active": False}, {"permissions": frozenset()},
            {"project_ids": frozenset({OTHER_PROJECT})},
            {"role": "viewer"}, {"user_id": "another-actor"},
            {"org_id": "other-org"},
        ):
            with self.subTest(attributes=attributes), self.assertRaises(PermissionError):
                self.gate.recovery_status(
                    principal=replace(legit, **attributes), request_id=self.id,
                    expected_base_revision=self.revision,
                    **self.proofs(NEW_TOKEN),
                )
        with self.assertRaises(PermissionError):
            self.gate.recovery_status(
                principal={"user_id": "alice", "authenticated": True},
                request_id=self.id, expected_base_revision=self.revision,
                **self.proofs(NEW_TOKEN),
            )

    def test_direct_constructed_trusted_principal_is_denied_by_both_entrypoints(self):
        """F1 regression: a manually created principal never releases payload/sendKey."""
        forged = TrustedPrincipal(
            user_id=principal_actor_id(self.host.users["alice"]),
            org_id=ORG, session_id="unissued-session-hash",
            role="admin", project_ids=frozenset({PROJECT}),
            permissions=frozenset({"mtr.read"}),
            authenticated=True, session_valid=True, active=True,
        )
        with self.assertRaises(PermissionError):
            self.outbox.recovery_snapshot(
                principal=forged, request_id=self.id,
                expected_base_revision=self.revision,
            )
        with self.assertRaises(PermissionError):
            self.gate.recovery_status(
                principal=forged, request_id=self.id,
                expected_base_revision=self.revision,
            )
        # Even stealing a genuine, audience-correct proof without the matching
        # immutable principal claims must not disclose historical evidence.
        with self.assertRaises(PermissionError):
            self.outbox.recovery_snapshot(
                principal=forged, request_id=self.id,
                expected_base_revision=self.revision, token=NEW_TOKEN,
                seal=self.issuer.issue_recovery(NEW_TOKEN, audience=OUTBOX_RECOVERY),
            )
        with self.assertRaises(PermissionError):
            self.gate.recovery_status(
                principal=forged, request_id=self.id,
                expected_base_revision=self.revision,
                **self.proofs(NEW_TOKEN),
            )

    def test_proofs_are_single_use_and_strictly_audience_separated(self):
        actor = self.adapter._recovery_principal(NEW_TOKEN)
        outbox_seal = self.issuer.issue_recovery(NEW_TOKEN, audience=OUTBOX_RECOVERY)
        initial = self.outbox.recovery_snapshot(
            principal=actor, request_id=self.id,
            expected_base_revision=self.revision,
            token=NEW_TOKEN, seal=outbox_seal,
        )
        self.assertEqual(initial["sendKey"], SEND_KEY)
        with self.assertRaises(PrincipalProvenanceDenied):
            self.outbox.recovery_snapshot(
                principal=actor, request_id=self.id,
                expected_base_revision=self.revision,
                token=NEW_TOKEN, seal=outbox_seal,
            )
        gate_only = self.issuer.issue_recovery(NEW_TOKEN, audience=GATE_RECOVERY)
        with self.assertRaises(PrincipalProvenanceDenied):
            self.outbox.recovery_snapshot(
                principal=actor, request_id=self.id,
                expected_base_revision=self.revision,
                token=NEW_TOKEN, seal=gate_only,
            )
        outbox_only = self.issuer.issue_recovery(NEW_TOKEN, audience=OUTBOX_RECOVERY)
        with self.assertRaises(PrincipalProvenanceDenied):
            self.gate.recovery_status(
                principal=actor, request_id=self.id,
                expected_base_revision=self.revision,
                token=NEW_TOKEN, gate_seal=outbox_only, outbox_seal=gate_only,
            )

    def test_unbound_store_and_second_issuer_fail_closed(self):
        # Merely opening the metadata SQLite under another Python instance
        # cannot recover protected payloads without the bound live host.
        unbound = HostRequestStore(self.outbox.path)
        actor = self.adapter._recovery_principal(NEW_TOKEN)
        with self.assertRaises(PermissionError):
            unbound.recovery_snapshot(
                principal=actor, request_id=self.id,
                expected_base_revision=self.revision,
                token=NEW_TOKEN,
                seal=self.issuer.issue_recovery(NEW_TOKEN, audience=OUTBOX_RECOVERY),
            )
        second = HostPrincipalProvenance(self.host, org_id=ORG)
        with self.assertRaises(PermissionError):
            self.outbox.bind_recovery_provenance(second)
        with self.assertRaises(PrincipalProvenanceDenied):
            self.outbox.recovery_snapshot(
                principal=actor, request_id=self.id,
                expected_base_revision=self.revision,
                token=NEW_TOKEN,
                seal=second.issue_recovery(NEW_TOKEN, audience=OUTBOX_RECOVERY),
            )

    def test_revocation_after_seal_issue_before_protected_read(self):
        actor = self.adapter._recovery_principal(NEW_TOKEN)
        seal = self.issuer.issue_recovery(NEW_TOKEN, audience=OUTBOX_RECOVERY)
        self.host.users["alice"]["financeEdit"] = False
        with self.assertRaises(PrincipalProvenanceDenied):
            self.outbox.recovery_snapshot(
                principal=actor, request_id=self.id,
                expected_base_revision=self.revision,
                token=NEW_TOKEN, seal=seal,
            )
        self.host.users["alice"]["financeEdit"] = True
        self.assertFalse(self.recovery()["mayDispatch"])

    def test_recreated_username_with_new_lineage_cannot_read_old_request(self):
        """F2 fixed for host-derived identities, given unique private lineage.

        Model deletion and replacement by a DIFFERENT private account with the
        same username but a new lineage. The original request remains bound
        to the previous account incarnation, not the reused username.
        """
        self.host.sessions.pop(OLD_TOKEN)
        self.host.sessions.pop(NEW_TOKEN)
        replacement_token = "new-unrelated-account-using-alice-name"
        self.host.users["alice"] = {
            "username": "alice", "role": "editor", "financeEdit": True,
            "projects": [PROJECT],
            "accountLineage": "abcdefabcdefabcdefabcdefabcdefab",
        }
        self.host.sessions[replacement_token] = "alice"
        principal = self.adapter._recovery_principal(replacement_token)
        self.assertNotEqual(principal.session_id, self.original.session_id)
        self.assertNotEqual(principal.user_id, self.original.user_id)
        with self.assertRaises(PermissionError):
            self.outbox.recovery_snapshot(
                principal=principal, request_id=self.id,
                expected_base_revision=self.revision,
                token=replacement_token,
                seal=self.issuer.issue_recovery(replacement_token, audience=OUTBOX_RECOVERY),
            )
        with self.assertRaises(PermissionError):
            self.gate.recovery_status(
                principal=principal, request_id=self.id,
                expected_base_revision=self.revision,
                **self.proofs(replacement_token),
            )

    def test_changed_outbox_evidence_denied_even_if_canonical_json(self):
        # Test fixture mutation only. The production API never opens SQLite
        # directly. After editing original digest, the immutable gate must
        # refuse the now-disagreeing original hash.
        with closing(sqlite3.connect(self.outbox.path)) as conn:
            conn.execute("UPDATE requests SET payload_sha256=? WHERE request_id=?",
                         ("f" * 64, self.id))
            conn.commit()
        with self.assertRaises(StoreError):
            self.recovery()

    def test_mutated_dispatch_slot_denied(self):
        # In synthetic DB only: remove immutable trigger to simulate a
        # compromised/corrupt on-disk gate, not an authorized API operation.
        with closing(sqlite3.connect(self.gate.path)) as conn:
            conn.execute("DROP TRIGGER dispatch_reservation_transitions")
            conn.execute("UPDATE dispatch_reservations SET send_key=? WHERE request_id=?",
                         ("tampered-send-key", self.id))
            conn.commit()
        with self.assertRaises(DispatchGateConflict):
            self.recovery()

    def test_mutated_dispatch_audit_denied(self):
        # Another corrupt synthetic DB case: the stored history must still be
        # validated even when all reservation/outbox identity fields match.
        with closing(sqlite3.connect(self.gate.path)) as conn:
            conn.execute("DROP TRIGGER immutable_dispatch_audit_update")
            conn.execute(
                "UPDATE dispatch_audit SET action=? WHERE request_id=? AND version=1",
                ("unknown_after_attempt", self.id),
            )
            conn.commit()
        with self.assertRaises(DispatchGateError):
            self.recovery()

    def test_no_rearm_after_relogin_even_if_original_card_unchanged(self):
        principal = self.adapter._principal_and_task(NEW_TOKEN, TASK)[0]
        with self.assertRaises(PermissionError):
            self.gate.reserve_once(
                principal=principal, request_id=self.id,
                expected_payload_sha256=self.digest,
                expected_base_revision=self.revision,
                current_server_revision=self.revision, send_key=SEND_KEY,
            )
        with self.assertRaises(DispatchGateConflict):
            self.gate.reserve_once(
                principal=self.original, request_id=self.id,
                expected_payload_sha256=self.digest,
                expected_base_revision=self.revision,
                current_server_revision=self.revision, send_key=SEND_KEY,
            )


if __name__ == "__main__":
    unittest.main()
