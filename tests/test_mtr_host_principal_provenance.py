"""Synthetic E2 host-only principal provenance seal/security contract.

All users, sessions and projects are disposable in-memory fixtures. No actual
LanService, account database, peer, HTTPS or financial adapter is started.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import pickle
import tempfile
import threading
import unittest
from unittest.mock import patch

from mtr_account_lineage import principal_actor_id
from mtr_host_request_store import TrustedPrincipal
from mtr_host_principal_provenance import (
    GATE_RECOVERY, OUTBOX_RECOVERY, HostPrincipalProvenance,
    PrincipalProvenanceDenied, SealedRecoveryPrincipal,
)


ORG = "synthetic-organization"
PROJECT = "synthetic-project-a"
OTHER = "synthetic-project-b"
OLD = "initial-synthetic-session-token"
RELOGIN = "second-synthetic-session-token"
MALLORY = "another-user-session-token"
LINEAGE_ALICE = "0123456789abcdef0123456789abcdef"
LINEAGE_MALLORY = "fedcba9876543210fedcba9876543210"


class MemoryBridge:
    def __init__(self):
        self._lock = threading.RLock()
        self.state = {
            "projects": [{"id": PROJECT}, {"id": OTHER}],
            "tasks": [],
        }

    def getState(self):
        return deepcopy(self.state)


class MemoryHost:
    """Mirrors the crucial LanService private registry identity boundary."""

    def __init__(self):
        self.lock = threading.RLock()
        self.bridge = MemoryBridge()
        self.users = {
            "alice": {"username": "alice", "role": "editor",
                      "financeEdit": True, "projects": [PROJECT],
                      "accountLineage": LINEAGE_ALICE},
            "mallory": {"username": "mallory", "role": "editor",
                        "financeEdit": True, "projects": [PROJECT],
                        "accountLineage": LINEAGE_MALLORY},
        }
        # Each session is represented by the username in the private registry.
        self.sessions = {OLD: "alice", RELOGIN: "alice", MALLORY: "mallory"}

    def account_for(self, token):
        with self.lock:
            username = self.sessions.get(token)
            if username is None or username not in self.users:
                raise PermissionError("current session/account unavailable")
            return self.users[username]  # NOT a constructed public-profile copy


class HostPrincipalProvenanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-principal-provenance-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        fake_profile = patch.dict(os.environ, {
            name: str(self.root) for name in (
                "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "HOME", "USERPROFILE"
            )
        })
        fake_profile.start()
        self.addCleanup(fake_profile.stop)
        self.host = MemoryHost()
        self.issuer = HostPrincipalProvenance(self.host, org_id=ORG)

    def issued(self, token=OLD, audience=GATE_RECOVERY):
        return self.issuer.issue_recovery(token, audience=audience)

    def verify(self, seal, token=OLD, audience=GATE_RECOVERY):
        return self.issuer.verify_and_consume(token, seal, audience=audience)

    def test_per_instance_secret_and_nonce_are_cryptographic_random_length(self):
        with patch("mtr_host_principal_provenance.secrets.token_bytes",
                   wraps=__import__("secrets").token_bytes) as rng:
            host = HostPrincipalProvenance(self.host, org_id=ORG)
            seal = host.issue_recovery(OLD, audience=GATE_RECOVERY)
        self.assertEqual(rng.call_args_list[0].args, (32,))
        self.assertEqual(rng.call_args_list[1].args, (16,))
        self.assertEqual(len(seal.nonce), 16)
        self.assertEqual(len(seal.mac), 32)
        self.assertEqual(len(set(
            host.issue_recovery(OLD, audience=GATE_RECOVERY).nonce
            for _ in range(48)
        )), 48)

    def test_issued_principal_is_derived_only_from_host_private_account(self):
        seal = self.issued()
        principal = self.verify(seal)
        self.assertIs(type(principal), TrustedPrincipal)
        self.assertEqual(principal.user_id, principal_actor_id(self.host.users["alice"]))
        self.assertEqual(principal.org_id, ORG)
        self.assertEqual(principal.role, "editor")
        self.assertEqual(principal.project_ids, frozenset({PROJECT}))
        self.assertEqual(principal.permissions, frozenset({"mtr.read"}))
        self.assertTrue(principal.authenticated)
        self.assertTrue(principal.session_valid)
        self.assertTrue(principal.active)
        self.assertNotEqual(principal.user_id, "alice")

    def test_plain_forged_principal_and_fake_client_dict_never_count_as_seal(self):
        forged = TrustedPrincipal(
            user_id=principal_actor_id(self.host.users["alice"]), org_id=ORG,
            session_id="totally-forged-session", role="admin",
            project_ids=frozenset({PROJECT}), permissions=frozenset({"mtr.read"}),
            authenticated=True, session_valid=True,
        )
        for fake in (forged, {"principal": forged, "authenticated": True}, None):
            with self.subTest(kind=type(fake).__name__):
                with self.assertRaises(PrincipalProvenanceDenied):
                    self.verify(fake)

    def test_manual_construction_without_issuer_mac_does_not_authenticate(self):
        real = self.issued()
        fake = SealedRecoveryPrincipal(
            principal=real.principal, audience=GATE_RECOVERY,
            issued_monotonic_ns=real.issued_monotonic_ns,
            nonce=real.nonce, mac=b"0" * 32,
        )
        with self.assertRaises(PrincipalProvenanceDenied):
            self.verify(fake)
        self.assertEqual(self.verify(real).role, "editor")

    def test_modified_actor_org_session_project_role_and_permission_are_denied(self):
        good = self.issued()
        altered = (
            {"user_id": "different-actor"}, {"org_id": "different-org"},
            {"session_id": "another-session"},
            {"project_ids": frozenset({OTHER})},
            {"project_ids": frozenset({PROJECT, OTHER})},
            {"role": "admin"},
            {"permissions": frozenset({"mtr.read", "mtr.manual_send"})},
            {"permissions": frozenset()},
            {"authenticated": False}, {"session_valid": False},
            {"active": False},
        )
        for attrs in altered:
            with self.subTest(attrs=attrs), self.assertRaises(PrincipalProvenanceDenied):
                self.verify(replace(good, principal=replace(good.principal, **attrs)))
        self.assertEqual(self.verify(good).role, "editor")

    def test_modified_nonce_time_signature_and_audience_denied(self):
        seal = self.issued()
        modifications = (
            {"nonce": b"z" * 16}, {"nonce": b"z" * 4},
            {"issued_monotonic_ns": seal.issued_monotonic_ns + 1},
            {"issued_monotonic_ns": True},
            {"mac": b"z" * 32}, {"mac": b"z"},
            {"audience": OUTBOX_RECOVERY},
        )
        for change in modifications:
            with self.subTest(change=change), self.assertRaises(PrincipalProvenanceDenied):
                self.verify(replace(seal, **change))
        self.verify(seal)

    def test_one_shot_replay_is_denied_and_second_audience_requires_new_seal(self):
        seal = self.issued()
        self.verify(seal)
        with self.assertRaises(PrincipalProvenanceDenied):
            self.verify(seal)
        outbox = self.issued(audience=OUTBOX_RECOVERY)
        with self.assertRaises(PrincipalProvenanceDenied):
            self.verify(outbox, audience=GATE_RECOVERY)
        self.verify(outbox, audience=OUTBOX_RECOVERY)

    def test_same_actor_relogin_must_issue_a_new_session_seal(self):
        old_proof = self.issued()
        with self.assertRaises(PrincipalProvenanceDenied):
            self.verify(old_proof, token=RELOGIN)
        fresh = self.issued(token=RELOGIN)
        new_principal = self.verify(fresh, token=RELOGIN)
        self.assertEqual(new_principal.user_id, old_proof.principal.user_id)
        self.assertNotEqual(new_principal.session_id, old_proof.principal.session_id)
        self.assertEqual(new_principal.permissions, frozenset({"mtr.read"}))

    def test_token_revoked_between_issue_and_verify_fails(self):
        proof = self.issued()
        self.host.sessions.pop(OLD)
        with self.assertRaises(PermissionError):
            self.verify(proof)

    def test_role_or_finance_grant_revoked_fails_before_consumption(self):
        for key, value in (("role", "viewer"), ("financeEdit", False),
                           ("active", False)):
            with self.subTest(key=key):
                proof = self.issued()
                original = self.host.users["alice"].get(key, True)
                self.host.users["alice"][key] = value
                with self.assertRaises(PrincipalProvenanceDenied):
                    self.verify(proof)
                self.host.users["alice"][key] = original

    def test_project_revoked_or_removed_from_registry_denies(self):
        proof = self.issued()
        self.host.users["alice"]["projects"] = [OTHER]
        with self.assertRaises(PrincipalProvenanceDenied):
            self.verify(proof)
        self.host.users["alice"]["projects"] = [PROJECT]
        self.host.bridge.state["projects"] = [{"id": OTHER}]
        with self.assertRaises(PrincipalProvenanceDenied):
            self.verify(proof)

    def test_password_reset_same_lineage_preserves_identity_but_revoked_token_denied(self):
        proof = self.issued()
        actor = proof.principal.user_id
        self.host.users["alice"]["passwordHash"] = "new-hash-after-reset"
        self.assertEqual(self.verify(proof).user_id, actor)
        second = self.issued()
        self.host.sessions.pop(OLD)
        with self.assertRaises(PermissionError):
            self.verify(second)

    def test_account_deletion_recreation_same_username_different_lineage_denies(self):
        old_seal = self.issued()
        self.host.users["alice"] = {
            "username": "alice", "role": "editor", "financeEdit": True,
            "projects": [PROJECT], "accountLineage": "abcdef" * 5 + "ab",
        }
        with self.assertRaises(PrincipalProvenanceDenied):
            self.verify(old_seal)
        fresh = self.issued(token=RELOGIN)
        fresh_actor = self.verify(fresh, token=RELOGIN).user_id
        self.assertNotEqual(fresh_actor, old_seal.principal.user_id)

    def test_legacy_missing_malformed_and_duplicate_lineage_all_fail_closed(self):
        for value in (None, "G" * 32, "0" * 32, "a" * 31):
            with self.subTest(value=value):
                saved = self.host.users["alice"].get("accountLineage")
                self.host.users["alice"]["accountLineage"] = value
                with self.assertRaises(PermissionError):
                    self.issued()
                self.host.users["alice"]["accountLineage"] = saved
        self.host.users["mallory"]["accountLineage"] = LINEAGE_ALICE
        with self.assertRaises(PrincipalProvenanceDenied):
            self.issued()

    def test_private_registry_identity_check_rejects_fake_account_copy(self):
        original = self.host.account_for

        def forged_copy(token):
            return deepcopy(original(token))

        with patch.object(self.host, "account_for", side_effect=forged_copy):
            with self.assertRaises(PrincipalProvenanceDenied):
                self.issued()

    def test_other_actor_cannot_reuse_seal_or_mint_another_actors_identity(self):
        seal = self.issued()
        with self.assertRaises(PrincipalProvenanceDenied):
            self.verify(seal, token=MALLORY)
        mallory = self.issued(token=MALLORY)
        self.assertNotEqual(mallory.principal.user_id, seal.principal.user_id)

    def test_new_issuer_or_host_restart_invalidates_old_capability(self):
        seal = self.issued()
        next_instance = HostPrincipalProvenance(self.host, org_id=ORG)
        with self.assertRaises(PrincipalProvenanceDenied):
            next_instance.verify_and_consume(OLD, seal, audience=GATE_RECOVERY)
        self.verify(seal)

    def test_monotonic_timeout_and_future_issued_tokens_are_denied(self):
        with patch("mtr_host_principal_provenance.time.monotonic_ns",
                   return_value=1_000_000_000_000):
            proof = self.issued()
        with patch("mtr_host_principal_provenance.time.monotonic_ns",
                   return_value=1_000_000_000_000 + 31_000_000_000):
            with self.assertRaises(PrincipalProvenanceDenied):
                self.verify(proof)
        with patch("mtr_host_principal_provenance.time.monotonic_ns",
                   return_value=1_000_000_000_000 - 1):
            with self.assertRaises(PrincipalProvenanceDenied):
                self.verify(proof)

    def test_concurrent_verification_only_one_consumer_wins(self):
        proof = self.issued()

        def consume(_):
            try:
                self.verify(proof)
                return "permitted"
            except PrincipalProvenanceDenied:
                return "denied"

        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(consume, range(8)))
        self.assertEqual(results.count("permitted"), 1)
        self.assertEqual(results.count("denied"), 7)

    def test_replay_tracking_capacity_fails_closed_without_reissuing_a_permit(self):
        seals = [self.issued() for _ in range(3)]
        with patch("mtr_host_principal_provenance._MAX_USED", 2):
            self.verify(seals[0])
            self.verify(seals[1])
            with self.assertRaises(PrincipalProvenanceDenied):
                self.verify(seals[2])
            with self.assertRaises(PrincipalProvenanceDenied):
                self.verify(seals[0])

    def test_no_secret_in_repr_pickle_or_json(self):
        proof = self.issued()
        self.assertEqual(repr(proof), "<SealedRecoveryPrincipal redacted>")
        self.assertEqual(repr(self.issuer),
                         "<HostPrincipalProvenance host-only redacted>")
        self.assertNotIn(LINEAGE_ALICE, repr(proof))
        self.assertNotIn(OLD, repr(proof))
        self.assertFalse(hasattr(self.issuer, "__dict__"))
        with self.assertRaises(TypeError):
            pickle.dumps(self.issuer)
        with self.assertRaises(TypeError):
            pickle.dumps(proof)
        with self.assertRaises(TypeError):
            json.dumps(proof)

    def test_invalid_issuer_host_org_rng_token_and_audience_fail(self):
        for org in ("", "bad space", "x" * 121, None):
            with self.subTest(org=org), self.assertRaises(PrincipalProvenanceDenied):
                HostPrincipalProvenance(self.host, org_id=org)
        with self.assertRaises(PrincipalProvenanceDenied):
            HostPrincipalProvenance(object(), org_id=ORG)
        with patch("mtr_host_principal_provenance.secrets.token_bytes",
                   return_value=b"bad"):
            with self.assertRaises(PrincipalProvenanceDenied):
                HostPrincipalProvenance(self.host, org_id=ORG)
        for token in (None, "", b"token", "bad token", "x" * 513):
            with self.subTest(token=repr(token)[:50]), self.assertRaises(PermissionError):
                self.issued(token)
        for audience in ("", "mtr.manual_send", "other.audience", None):
            with self.subTest(audience=audience), self.assertRaises(PrincipalProvenanceDenied):
                self.issued(audience=audience)

    def test_manual_send_or_prepared_claim_cannot_be_minted_from_read_seal(self):
        proof = self.issued()
        self.assertEqual(proof.principal.permissions, frozenset({"mtr.read"}))
        for audience in ("mtr.manual_send", "mtr.prepare", "mtr.receipt_ingest"):
            with self.assertRaises(PrincipalProvenanceDenied):
                self.verify(proof, audience=audience)


if __name__ == "__main__":
    unittest.main()
