"""Disposable live LanService credential/session provenance for signed finance origins.

Never starts a LAN listener, reads an installed profile, changes a real ledger,
or posts a Taraz invoice. The independent Taraz peer verifier is loaded from
the isolated source as a read-only interoperability check.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from lan import LanService, make_account
from mtr_account_lineage import principal_actor_id
from taraz_exchange import queue_saved_task
from mtr_finance_authenticated_origin import (
    FinanceOriginDenied, HostAuthenticatedFinanceOrigin, SealedFinanceOrigin,
)
from mtr_peer_envelope import (
    canonical_json, sign_request, verify_request, verify_receipt_query,
)


TARAZ_PEER_MODULE = Path(
    r"D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109"
) / "taraz_mtr_peer_registry.py"


def _taraz_peer():
    if not TARAZ_PEER_MODULE.is_file() or TARAZ_PEER_MODULE.is_symlink():
        raise RuntimeError("real read-only Taraz peer verifier required")
    spec = importlib.util.spec_from_file_location(
        "qa_taraz_finance_authenticated_origin_peer", TARAZ_PEER_MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TARAZ_PEER = _taraz_peer()


class MemoryBridge:
    def __init__(self):
        self._lock = threading.RLock()
        self.state = {
            "projects": [{"id": "project-a"}, {"id": "project-b"}],
            "tasks": [{
                "id": "card-1", "projectId": "project-a",
                "title": "Synthetic selected finance expense",
                "checklist": [{
                    "expenseItems": [{
                        "id": "expense-1", "currency": "RIAL",
                        "quantity": 2, "unitPrice": 750,
                    }],
                }],
            }],
        }

    def getState(self):
        return deepcopy(self.state)


class AuthenticatedFinanceOriginTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-finance-origin-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bridge = MemoryBridge()
        self.host = LanService(self.bridge, self.root / "users.json")
        # All accounts and tokens exist only inside this disposable LanService.
        alice = make_account("alice", "qa-password-1", "editor", ["project-a"])
        alice["financeEdit"] = True
        mallory = make_account("mallory", "qa-password-2", "editor", ["project-a"])
        mallory["financeEdit"] = True
        self.host.users = {"alice": alice, "mallory": mallory}
        self.token = secrets.token_urlsafe(32)
        self.mallory_token = secrets.token_urlsafe(32)
        self.host.sessions[self.token] = ("alice", time.time() + 3600)
        self.host.sessions[self.mallory_token] = ("mallory", time.time() + 3600)
        self.request_id = secrets.token_hex(16)
        self.company_id = secrets.token_hex(16)
        self.invoice_id = "invoice-1"
        self.event_id = "issue-1"
        self.secret = secrets.token_bytes(48)
        self.issuer = HostAuthenticatedFinanceOrigin(
            self.host, organization_id="qa-madar-org",
            sender_id="qa-madar-peer", key_id="qa-madar-key",
            signing_key=self.secret, company_id=self.company_id)
        self.proposal = {
            "schema": 1, "source": "madar", "id": self.request_id,
            "taskId": "card-1", "projectId": "project-a",
            "title": "Synthetic selected finance expense",
            "createdUtc": datetime.now(timezone.utc).isoformat(),
            "expenseId": "expense-1", "amountRial": "1500",
        }
        self.raw = json.dumps(self.proposal, ensure_ascii=False,
                              separators=(",", ":")).encode("utf8")

    def prepare(self, *, token=None, raw=None, explicit_manual_action=True,
                invoice_id=None, issue_event_id=None):
        return self.issuer.prepare_manual(
            self.token if token is None else token,
            self.raw if raw is None else raw,
            invoice_id=self.invoice_id if invoice_id is None else invoice_id,
            issue_event_id=self.event_id if issue_event_id is None else issue_event_id,
            explicit_manual_action=explicit_manual_action)

    def signed(self, *, token=None, seal=None, raw=None,
               explicit_manual_action=True):
        if seal is None:
            seal = self.prepare()
        return self.issuer.sign_original_manual(
            self.token if token is None else token, seal,
            self.raw if raw is None else raw,
            explicit_manual_action=explicit_manual_action)

    def query(self, original, *, token=None, raw=None,
              challenge=None, explicit_manual_action=True):
        return self.issuer.sign_query_manual(
            self.token if token is None else token, original,
            self.raw if raw is None else raw,
            query_request_id=secrets.token_hex(16) if challenge is None else challenge,
            explicit_manual_action=explicit_manual_action)

    def verify_madar(self, raw):
        return verify_request(
            raw, secret=self.secret, now=datetime.now(timezone.utc).replace(microsecond=0),
            expected_organization_id="qa-madar-org",
            expected_sender_id="qa-madar-peer",
            expected_key_id="qa-madar-key", purpose="finance_review_request",
            allowed_actor_roles=frozenset({"admin", "editor"}))

    def taraz_config(self):
        return TARAZ_PEER.PeerConfig(
            organization_id="qa-madar-org", madar_sender_id="qa-madar-peer",
            madar_key_id="qa-madar-key", taraz_sender_id="qa-taraz-peer",
            taraz_key_id="qa-taraz-key", madar_secret=self.secret,
            taraz_secret=secrets.token_bytes(48))

    def test_live_lan_private_lineage_signs_exact_taraz_compatible_original_and_query(self):
        self.assertIs(self.host.account_for(self.token),
                      self.host.users["alice"])
        seal = self.prepare()
        self.assertIs(type(seal), SealedFinanceOrigin)
        self.assertNotIn("accountLineage", repr(seal))
        original_wire = self.signed(seal=seal)
        original = self.verify_madar(original_wire)
        self.assertEqual(original.actor_role, "editor")
        self.assertEqual(original.organization_id, "qa-madar-org")
        self.assertEqual(original.payload, {
            "id": self.request_id, "taskId": "card-1",
            "projectId": "project-a", "sourceDigest": hashlib.sha256(self.raw).hexdigest(),
            "companyId": self.company_id,
            "actorId": principal_actor_id(self.host.users["alice"]),
            "invoiceId": self.invoice_id, "issueEventId": self.event_id,
            "journalId": "J:" + self.event_id,
        })
        self.assertNotIn(self.token, original_wire.decode("utf-8"))
        self.assertNotIn("accountLineage", original_wire.decode("utf-8"))
        peer = self.taraz_config()
        from_taraz = TARAZ_PEER._verify(
            original_wire, config=peer,
            now=datetime.now(timezone.utc).replace(microsecond=0),
            expected_kind="request", purpose="finance_review_request")
        self.assertEqual(from_taraz["payload"], original.payload)
        query_wire = self.query(original_wire)
        verified_query = verify_receipt_query(
            query_wire, secret=self.secret,
            now=datetime.now(timezone.utc).replace(microsecond=0),
            expected_organization_id="qa-madar-org",
            expected_sender_id="qa-madar-peer",
            expected_key_id="qa-madar-key",
            allowed_actor_roles=frozenset({"editor"}))
        self.assertEqual(verified_query.payload["originalRequestId"], self.request_id)
        self.assertEqual(verified_query.payload["originalPayloadSha256"],
                         original.payload_sha256)
        self.assertEqual(TARAZ_PEER._verify(
            query_wire, config=peer,
            now=datetime.now(timezone.utc).replace(microsecond=0),
            expected_kind="query", purpose="receipt_lookup")["requestId"],
            verified_query.request_id)
        with self.assertRaisesRegex(FinanceOriginDenied, "consumed"):
            self.query(original_wire)
        with self.assertRaisesRegex(FinanceOriginDenied, "consumed"):
            self.signed(seal=seal)

    def test_actual_exported_on_disk_proposal_is_accepted_byte_for_byte(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.root)}):
            outcome = queue_saved_task(
                self.bridge.getState(), "card-1", "expense-1",
                request_id=self.request_id)
        self.assertTrue(outcome["queued"])
        persisted = (self.root / "Madar-Taraz-Bridge" / "pending" /
                     (self.request_id + ".json")).read_bytes()
        self.assertEqual(persisted, json.dumps(
            json.loads(persisted), ensure_ascii=False,
            separators=(",", ":")).encode("utf8"))
        self.assertNotEqual(persisted, canonical_json(json.loads(persisted)))
        seal = self.prepare(raw=persisted)
        signed = self.signed(seal=seal, raw=persisted)
        verified = self.verify_madar(signed)
        self.assertEqual(verified.payload["sourceDigest"],
                         hashlib.sha256(persisted).hexdigest())
        query = self.query(signed, raw=persisted)
        self.assertEqual(verify_receipt_query(
            query, secret=self.secret,
            now=datetime.now(timezone.utc).replace(microsecond=0),
            expected_organization_id="qa-madar-org",
            expected_sender_id="qa-madar-peer",
            expected_key_id="qa-madar-key",
            allowed_actor_roles=frozenset({"editor"})).payload["originalRequestId"],
            self.request_id)

    def test_current_taraz_username_gate_cannot_accept_lineage_actor(self):
        # A forced username mapping would destroy host-private lineage
        # provenance. Taraz's current local identity regex is <=40 chars.
        actor = principal_actor_id(self.host.users["alice"])
        self.assertEqual(len(actor), len("mtr-actor-v1-") + 64)
        self.assertGreater(len(actor), 40)
        self.assertNotEqual(actor, self.host.users["alice"]["username"])

    def test_missing_manual_action_and_forged_seal_denied(self):
        with self.assertRaisesRegex(FinanceOriginDenied, "manual"):
            self.prepare(explicit_manual_action=False)
        seal = self.prepare()
        with self.assertRaisesRegex(FinanceOriginDenied, "manual"):
            self.signed(seal=seal, explicit_manual_action=False)
        with self.assertRaisesRegex(FinanceOriginDenied, "forged"):
            self.signed(seal=replace(seal, mac=b"0" * 32))
        with self.assertRaisesRegex(FinanceOriginDenied, "private finance seal"):
            self.signed(seal=replace(seal, issued_ns=1 << 200))
        with self.assertRaisesRegex(FinanceOriginDenied, "forged"):
            self.signed(seal=replace(seal, claims_bytes=seal.claims_bytes + b" "))
        with self.assertRaisesRegex(FinanceOriginDenied, "private finance seal"):
            self.signed(seal={"authenticated": True})
        original = self.signed(seal=seal)
        self.assertEqual(self.verify_madar(original).actor_role, "editor")
        with self.assertRaisesRegex(FinanceOriginDenied, "manual"):
            self.query(original, explicit_manual_action=False)
        self.query(original)

    def test_cross_user_token_and_revocation_before_signing(self):
        seal = self.prepare()
        with self.assertRaisesRegex(FinanceOriginDenied, "changed"):
            self.signed(token=self.mallory_token, seal=seal)
        self.host.sessions.pop(self.token)
        with self.assertRaises(PermissionError):
            self.signed(seal=seal)

    def test_viewer_role_finance_permission_and_project_grants_fail(self):
        seal = self.prepare()
        alice = self.host.users["alice"]
        alice["role"] = "viewer"
        with self.assertRaises(PermissionError):
            self.signed(seal=seal)
        alice["role"] = "editor"
        alice["financeEdit"] = False
        with self.assertRaises(PermissionError):
            self.signed(seal=seal)
        alice["financeEdit"] = True
        alice["projects"] = ["project-b"]
        with self.assertRaises(PermissionError):
            self.signed(seal=seal)
        alice["projects"] = ["project-a"]
        self.signed(seal=seal)

    def test_bad_and_duplicate_lineage_or_fake_registry_copy_denied(self):
        with self.assertRaises(PermissionError):
            self.host.users["alice"]["accountLineage"] = "invalid"
            self.prepare()
        self.host.users["alice"]["accountLineage"] = secrets.token_hex(16)
        self.host.users["mallory"]["accountLineage"] = self.host.users["alice"]["accountLineage"]
        with self.assertRaises(PermissionError):
            self.prepare()
        self.host.users["mallory"]["accountLineage"] = secrets.token_hex(16)
        original = self.host.users["alice"]
        with patch.object(self.host, "account_for", return_value=original.copy()):
            with self.assertRaises(FinanceOriginDenied):
                self.prepare()

    def test_source_digest_recomputed_from_saved_task_expense_and_project(self):
        for mutation in (
            {"amountRial": "1501"}, {"projectId": "project-b"},
            {"title": "forged-title"}, {"taskId": "other-card"},
            {"expenseId": "other-expense"}, {"id": "invalid"},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(
                    (FinanceOriginDenied, ValueError)):
                self.prepare(raw=canonical_json({**self.proposal, **mutation}))
        with self.assertRaises(FinanceOriginDenied):
            self.prepare(raw=self.raw + b" ")
        with self.assertRaises(FinanceOriginDenied):
            self.prepare(raw=self.raw.replace(b'"id":', b'"id":"oops","id":'))
        seal = self.prepare()
        self.bridge.state["tasks"][0]["checklist"][0]["expenseItems"][0]["unitPrice"] = 5000
        with self.assertRaises((FinanceOriginDenied, ValueError)):
            self.signed(seal=seal)

    def test_changed_source_raw_or_private_identity_after_preflight_denies(self):
        seal = self.prepare()
        changed = canonical_json({**self.proposal, "amountRial": "2000"})
        with self.assertRaises((FinanceOriginDenied, ValueError)):
            self.signed(seal=seal, raw=changed)
        self.host.users["alice"]["accountLineage"] = secrets.token_hex(16)
        with self.assertRaises(FinanceOriginDenied):
            self.signed(seal=seal)

    def test_original_replay_fresh_nonce_and_forged_external_hmac_denied(self):
        original = self.signed()
        with self.assertRaises(FinanceOriginDenied):
            self.prepare()
        now = datetime.now(timezone.utc).replace(microsecond=0)
        external = sign_request(
            self.verify_madar(original).payload,
            organization_id="qa-madar-org", sender_id="qa-madar-peer",
            actor_role="editor", key_id="qa-madar-key", request_id=self.request_id,
            purpose="finance_review_request", issued_at=now,
            expires_at=now + timedelta(seconds=119),
            secret=self.secret, authorized=True, explicit_manual_action=True)
        # A caller-created original, even if it knows the HMAC key, was not
        # issued by the private one-time host authority.
        self.assertNotEqual(external, original)
        with self.assertRaisesRegex(FinanceOriginDenied, "not issued"):
            self.query(external)
        self.query(original)
        with self.assertRaisesRegex(FinanceOriginDenied, "consumed"):
            self.query(original)

    def test_query_unknown_original_cross_org_wrong_token_and_repeated_challenge(self):
        original = self.signed()
        with self.assertRaises(PermissionError):
            self.query(original, token=self.mallory_token)
        forged = sign_request(
            self.verify_madar(original).payload,
            organization_id="foreign-org", sender_id="qa-madar-peer",
            actor_role="editor", key_id="qa-madar-key",
            request_id=secrets.token_hex(16), purpose="finance_review_request",
            issued_at=datetime.now(timezone.utc).replace(microsecond=0),
            expires_at=datetime.now(timezone.utc).replace(microsecond=0) +
                       timedelta(seconds=120),
            secret=self.secret, authorized=True, explicit_manual_action=True)
        with self.assertRaises(ValueError):
            self.query(forged)
        challenge = secrets.token_hex(16)
        self.query(original, challenge=challenge)
        with self.assertRaises(FinanceOriginDenied):
            self.query(original, challenge=challenge)
        with self.assertRaises(FinanceOriginDenied):
            self.query(original)

    def test_concurrent_signing_same_seal_only_one_wins(self):
        seal = self.prepare()
        def once(_):
            try:
                return self.signed(seal=seal)
            except FinanceOriginDenied:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            signed = list(pool.map(once, range(8)))
        self.assertEqual(sum(item is not None for item in signed), 1)

    def test_time_expiry_and_secret_redaction(self):
        seal = self.prepare()
        with patch("mtr_finance_authenticated_origin.time.monotonic_ns",
                   return_value=seal.issued_ns + 31_000_000_000):
            with self.assertRaisesRegex(FinanceOriginDenied, "expired"):
                self.signed(seal=seal)
        self.assertEqual(repr(self.issuer),
                         "<HostAuthenticatedFinanceOrigin host-only redacted>")
        with self.assertRaises(TypeError):
            __import__("pickle").dumps(seal)
        with self.assertRaises(TypeError):
            __import__("pickle").dumps(self.issuer)

    def test_other_issuer_same_hmac_secret_cannot_query_unissued_original(self):
        original = self.signed()
        second = HostAuthenticatedFinanceOrigin(
            self.host, organization_id="qa-madar-org",
            sender_id="qa-madar-peer", key_id="qa-madar-key",
            signing_key=self.secret, company_id=self.company_id)
        with self.assertRaisesRegex(FinanceOriginDenied, "not issued"):
            second.sign_query_manual(
                self.token, original, self.raw,
                query_request_id=secrets.token_hex(16),
                explicit_manual_action=True)
        # This also demonstrates a remaining limitation: another signer can
        # mint a new original if improperly instantiated in the host. There
        # is no durable cross-process replay authority in this isolated code.
        self.assertIsNot(second, self.issuer)

    def test_role_claim_cannot_be_promoted_by_a_preverified_peer_object(self):
        original = self.signed()
        original_view = self.verify_madar(original)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        impostor_admin = sign_request(
            original_view.payload, organization_id="qa-madar-org",
            sender_id="qa-madar-peer", actor_role="admin",
            key_id="qa-madar-key", request_id=original_view.request_id,
            purpose="finance_review_request", issued_at=now,
            expires_at=now + timedelta(seconds=120), secret=self.secret,
            authorized=True, explicit_manual_action=True)
        with self.assertRaisesRegex(FinanceOriginDenied, "not issued"):
            self.query(impostor_admin)
        self.query(original)


if __name__ == "__main__":
    unittest.main()
