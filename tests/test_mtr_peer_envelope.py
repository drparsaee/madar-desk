"""Pure E2 v2 HMAC envelope protocol tests with distinct TEST-ONLY keys."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest

from mtr_peer_envelope import (
    MAX_ENVELOPE_BYTES, MAX_PAYLOAD_BYTES, EnvelopeError,
    canonical_json, check_replay_binding, query_first_recovery_decision,
    sign_peer_receipt, sign_receipt_query, sign_request,
    verify_peer_receipt, verify_receipt_query, verify_request,
)


# Synthetic keys: caller-injected only; neither key is read from or persisted to disk.
MADAR_TEST_SECRET = b"m" * 32
TARAZ_TEST_SECRET = b"t" * 32
NOW = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
ORIGINAL_ID = "a" * 32
QUERY_ID = "b" * 32


class PeerEnvelopeTests(unittest.TestCase):
    def sign_original(self, **overrides):
        args = {
            "payload": {
                "taskId": "synthetic-task",
                "projectId": "synthetic-project",
                "title": "synthetic review metadata",
            },
            "organization_id": "org.demo",
            "sender_id": "madar.user-1",
            "actor_role": "editor",
            "key_id": "madar.test.v1",
            "request_id": ORIGINAL_ID,
            "purpose": "finance_review_request",
            "issued_at": NOW,
            "expires_at": NOW + timedelta(minutes=4),
            "secret": MADAR_TEST_SECRET,
            "authorized": True,
            "explicit_manual_action": True,
        }
        args.update(overrides)
        return sign_request(**args)

    def verify_original(self, wire=None, **overrides):
        args = {
            "wire": wire if wire is not None else self.sign_original(),
            "secret": MADAR_TEST_SECRET,
            "now": NOW + timedelta(seconds=1),
            "expected_organization_id": "org.demo",
            "expected_sender_id": "madar.user-1",
            "expected_key_id": "madar.test.v1",
            "purpose": "finance_review_request",
            "allowed_actor_roles": frozenset({"editor"}),
        }
        args.update(overrides)
        return verify_request(**args)

    def query(self, original=None, **overrides):
        original = original or self.verify_original()
        args = {
            "original": original,
            "query_request_id": QUERY_ID,
            "key_id": "madar.test.v1",
            "issued_at": NOW,
            "expires_at": NOW + timedelta(minutes=4),
            "secret": MADAR_TEST_SECRET,
        }
        args.update(overrides)
        return sign_receipt_query(**args)

    def verify_query(self, original=None, **overrides):
        args = {
            "wire": self.query(original),
            "secret": MADAR_TEST_SECRET,
            "now": NOW + timedelta(seconds=1),
            "expected_organization_id": "org.demo",
            "expected_sender_id": "madar.user-1",
            "expected_key_id": "madar.test.v1",
            "allowed_actor_roles": frozenset({"editor"}),
        }
        args.update(overrides)
        return verify_receipt_query(**args)

    def receipt(self, query, status="unknown", **overrides):
        args = {
            "query": query,
            "lookup_status": status,
            "sender_id": "taraz.test.peer",
            "key_id": "taraz.test.v1",
            "issued_at": NOW,
            "expires_at": NOW + timedelta(minutes=4),
            "secret": TARAZ_TEST_SECRET,
        }
        args.update(overrides)
        return sign_peer_receipt(**args)

    def verify_response(self, original, query, status="unknown", **overrides):
        args = {
            "wire": self.receipt(query, status),
            "original": original,
            "query": query,
            "secret": TARAZ_TEST_SECRET,
            "now": NOW + timedelta(seconds=1),
            "expected_peer_id": "taraz.test.peer",
            "expected_peer_key_id": "taraz.test.v1",
        }
        args.update(overrides)
        return verify_peer_receipt(**args)

    def test_signing_is_canonical_and_independent_verification_succeeds(self):
        wire = self.sign_original()
        self.assertEqual(wire, canonical_json(json.loads(wire)))
        self.assertTrue(wire.startswith(b"{"))
        self.assertNotIn(MADAR_TEST_SECRET, wire)
        self.assertLessEqual(len(wire), MAX_ENVELOPE_BYTES)
        verified = self.verify_original(wire)
        self.assertEqual(verified.kind, "request")
        self.assertEqual(verified.organization_id, "org.demo")
        self.assertEqual(verified.request_id, ORIGINAL_ID)
        self.assertEqual(verified.sender_role, "madar_sender")
        self.assertEqual(verified.payload_sha256,
                         hashlib.sha256(canonical_json(verified.payload)).hexdigest())
        self.assertEqual(verified.envelope_sha256, hashlib.sha256(wire).hexdigest())
        fresh = verified.payload
        fresh["title"] = "tampered caller view"
        self.assertEqual(verified.payload["title"], "synthetic review metadata")

    def test_payload_canonicalization_independent_of_key_order(self):
        a = {"projectId": "p", "taskId": "t", "title": "تست"}
        b = {"title": "تست", "taskId": "t", "projectId": "p"}
        self.assertEqual(self.sign_original(payload=a),
                         self.sign_original(payload=b))

    def test_manual_auth_and_role_denial_before_any_signed_message(self):
        for edits in (
            {"authorized": False}, {"authorized": None},
            {"authorized": 1}, {"explicit_manual_action": False},
            {"explicit_manual_action": 1}, {"actor_role": "viewer"},
            {"actor_role": "peer"}, {"actor_role": ""},
        ):
            with self.subTest(edits=edits), self.assertRaises(EnvelopeError):
                self.sign_original(**edits)

    def test_wrong_org_sender_key_id_purpose_and_actor_acl_rejected(self):
        scenarios = (
            {"expected_organization_id": "org.other"},
            {"expected_sender_id": "madar.user-2"},
            {"expected_key_id": "taraz.test.v1"},
            {"purpose": "party_creation_proposal"},
            {"allowed_actor_roles": frozenset({"admin"})},
        )
        for edits in scenarios:
            with self.subTest(edits=edits), self.assertRaises(EnvelopeError):
                self.verify_original(**edits)
        with self.assertRaises(EnvelopeError):
            self.verify_original(allowed_actor_roles=frozenset())
        with self.assertRaises(EnvelopeError):
            self.verify_original(allowed_actor_roles={"editor"})

    def test_direction_separation_wrong_mac_and_mutated_payload(self):
        wire = self.sign_original()
        with self.assertRaises(EnvelopeError):
            self.verify_original(wire, secret=TARAZ_TEST_SECRET)
        value = json.loads(wire)
        for key, replacement in (
            ("organizationId", "org.other"),
            ("senderRole", "taraz_peer"),
            ("actorRole", "admin"),
            ("purpose", "catalog_read_query"),
            ("requestId", "c" * 32),
            ("payloadSha256", "0" * 64),
        ):
            variant = dict(value)
            variant[key] = replacement
            with self.subTest(key=key), self.assertRaises(EnvelopeError):
                self.verify_original(canonical_json(variant))
        variant = dict(value)
        variant["payload"] = dict(value["payload"], title="changed")
        with self.assertRaises(EnvelopeError):
            self.verify_original(canonical_json(variant))
        variant = dict(value)
        variant["mac"] = "0" * 64
        with self.assertRaises(EnvelopeError):
            self.verify_original(canonical_json(variant))

    def test_unauthorized_protocol_purposes_and_schema_version_rejected(self):
        for purpose in ("receipt_lookup_result", "receipt_lookup",
                        "official_finance_posting", "ledger_write"):
            with self.subTest(purpose=purpose), self.assertRaises(EnvelopeError):
                self.sign_original(purpose=purpose)
        wire = json.loads(self.sign_original())
        for name, replacement in (
            ("version", 3), ("version", True),
            ("algorithm", "none"), ("protocol", "other"),
        ):
            data = dict(wire, **{name: replacement})
            with self.subTest(name=name), self.assertRaises(EnvelopeError):
                self.verify_original(canonical_json(data))
        data = dict(wire, unexpected="value")
        with self.assertRaises(EnvelopeError):
            self.verify_original(canonical_json(data))
        for name in ("kind", "purpose"):
            data = dict(wire, **{name: ["malformed", "unhashable"]})
            with self.subTest(unhashable=name), self.assertRaises(EnvelopeError):
                self.verify_original(canonical_json(data))
        with self.assertRaises(EnvelopeError):
            self.sign_original(purpose=["malformed"])

    def test_rejects_short_keys_and_invalid_request_id(self):
        with self.assertRaises(EnvelopeError):
            self.sign_original(secret=b"short")
        with self.assertRaises(EnvelopeError):
            self.verify_original(secret=b"short")
        for identifier in ("", "A" * 32, "../escape", "z" * 32):
            with self.subTest(identifier=identifier), self.assertRaises(EnvelopeError):
                self.sign_original(request_id=identifier)

    def test_noncanonical_duplicate_key_json_and_invalid_types_rejected(self):
        wire = self.sign_original()
        for bad in (
            wire + b"\n", b" " + wire, b"{}",
            b'{"protocol":"mtr-peer","protocol":"mtr-peer"}',
            b'{"version":NaN}', b'{"version":Infinity}',
            b"\xff" + wire, b"[" + wire + b"]",
        ):
            with self.subTest(bad=bad[:20]), self.assertRaises(EnvelopeError):
                self.verify_original(bad)
        with self.assertRaises(EnvelopeError):
            self.verify_original(wire.decode("utf8"))
        with self.assertRaises(EnvelopeError):
            self.verify_original(wire + (b"x" * MAX_ENVELOPE_BYTES))

    def test_rejects_oversized_nested_nonfinite_or_invalid_json(self):
        for payload in (
            {"notes": "x" * (MAX_PAYLOAD_BYTES + 1)},
            {"value": float("nan")},
            {"value": 1.1},
            {"value": 2 ** 80},
            {1: "invalid-key"},
            {"x": object()},
            {"x": ["a"] * 65},
            {"x": "\ud800"},
        ):
            with self.subTest(payload=str(type(payload))), self.assertRaises(EnvelopeError):
                self.sign_original(payload=payload)
        deeply_nested = {"ok": "start"}
        for _ in range(10):
            deeply_nested = {"nested": deeply_nested}
        with self.assertRaises(EnvelopeError):
            self.sign_original(payload=deeply_nested)

    def test_timestamps_expiration_clock_and_precision_fail_closed(self):
        with self.assertRaises(EnvelopeError):
            self.sign_original(expires_at=NOW + timedelta(minutes=6))
        with self.assertRaises(EnvelopeError):
            self.sign_original(expires_at=NOW)
        with self.assertRaises(EnvelopeError):
            self.sign_original(issued_at=NOW.replace(tzinfo=None))
        with self.assertRaises(EnvelopeError):
            self.sign_original(issued_at=NOW + timedelta(microseconds=1))
        with self.assertRaises(EnvelopeError):
            self.verify_original(now=NOW + timedelta(minutes=4))
        with self.assertRaises(EnvelopeError):
            self.verify_original(now=NOW - timedelta(minutes=2))
        self.assertEqual(self.verify_original(now=NOW - timedelta(seconds=30)).kind,
                         "request")

    def test_query_has_distinct_id_and_verifies_independently(self):
        original = self.verify_original()
        query_wire = self.query(original)
        query = self.verify_query(original, wire=query_wire)
        self.assertEqual(query.request_id, QUERY_ID)
        self.assertEqual(query.kind, "query")
        self.assertEqual(query.payload["originalRequestId"], ORIGINAL_ID)
        self.assertEqual(query.payload["originalPayloadSha256"],
                         original.payload_sha256)
        self.assertNotIn(b"finance_posted", query_wire)
        with self.assertRaises(EnvelopeError):
            self.query(original, query_request_id=ORIGINAL_ID)
        with self.assertRaises(EnvelopeError):
            self.verify_query(original, wire=query_wire, secret=TARAZ_TEST_SECRET)
        with self.assertRaises(EnvelopeError):
            self.verify_original(query_wire)

    def test_signed_peer_lookup_is_only_a_lookup_not_finance_receipt(self):
        original = self.verify_original()
        query = self.verify_query(original)
        wire = self.receipt(query, "received")
        receipt = self.verify_response(original, query, "received", wire=wire)
        self.assertEqual(receipt.sender_role, "taraz_peer")
        self.assertEqual(receipt.purpose, "receipt_lookup_result")
        self.assertEqual(receipt.payload["lookupStatus"], "received")
        self.assertNotIn("financialDocumentId", receipt.payload)
        self.assertNotIn("postingApproved", receipt.payload)
        self.assertNotIn(TARAZ_TEST_SECRET, wire)
        with self.assertRaises(EnvelopeError):
            self.verify_response(original, query, "received", wire=wire,
                                 secret=MADAR_TEST_SECRET)
        with self.assertRaises(EnvelopeError):
            self.verify_response(original, query, "received", wire=wire,
                                 expected_peer_id="taraz.another")
        with self.assertRaises(EnvelopeError):
            self.verify_response(original, query, "received", wire=wire,
                                 expected_peer_key_id="taraz.old")
        with self.assertRaises(EnvelopeError):
            self.verify_response(original, query, "received", wire=wire,
                                 now=NOW + timedelta(minutes=4))

    def test_receipt_binds_exact_query_org_and_original(self):
        original = self.verify_original()
        query = self.verify_query(original)
        reply = self.receipt(query, "not_received")
        other_request = self.verify_original(self.sign_original(
            request_id="c" * 32))
        other_query = self.verify_query(other_request, wire=self.query(
            other_request, query_request_id="d" * 32))
        for wrong_original, wrong_query in (
            (other_request, query), (original, other_query),
        ):
            with self.assertRaises(EnvelopeError):
                self.verify_response(wrong_original, wrong_query,
                                     wire=reply)
        with self.assertRaises(EnvelopeError):
            self.verify_response(original, query, wire=reply,
                                 original=self.verify_original(
                                     self.sign_original(organization_id="org.other")))
        with self.assertRaises(EnvelopeError):
            self.receipt(query, "finance_approved")

    def test_status_recovery_is_explicit_query_first_and_never_sends(self):
        original = self.verify_original()
        query = self.verify_query(original)
        def decision(receipt=None, **kwargs):
            data = {
                "original": original, "query": query, "receipt": receipt,
                "prior_manual_authorized": True,
                "prior_request_id": original.request_id,
                "prior_payload_sha256": original.payload_sha256,
            }
            data.update(kwargs)
            return query_first_recovery_decision(**data)

        self.assertEqual(decision(), "hold_query_required")
        self.assertEqual(decision(prior_manual_authorized=False),
                         "hold_manual_authorization_mismatch")
        self.assertEqual(decision(prior_request_id="f" * 32),
                         "hold_manual_authorization_mismatch")
        self.assertEqual(decision(prior_payload_sha256="0" * 64),
                         "hold_manual_authorization_mismatch")
        for state, expected in (
            ("received", "observe_peer_claim_received"),
            # This signed metadata peer is NOT the official Taraz ledger.
            # Even a signed nonreceipt claim cannot rearm a consumed slot.
            ("not_received", "hold_unverified_nonreceipt"),
            ("unknown", "hold_uncertain"),
        ):
            with self.subTest(state=state):
                receipt = self.verify_response(original, query, state)
                self.assertEqual(decision(receipt), expected)
        # The result is a decision string; no transport or financial event occurs.

    def test_replay_idempotency_and_conflicting_payload_fail_closed(self):
        original = self.verify_original()
        registry = {}
        self.assertEqual(check_replay_binding(original, previous=registry), "new")
        name = (original.organization_id, original.kind, original.request_id)
        original_binding = (
            original.sender_id, original.sender_role, original.actor_role,
            original.purpose, original.key_id, original.payload_sha256,
        )
        registry[name] = original_binding
        self.assertEqual(check_replay_binding(original, previous=registry),
                         "identical")
        changed = self.verify_original(self.sign_original(
            payload={"taskId": "different synthetic card"}))
        with self.assertRaises(EnvelopeError):
            check_replay_binding(changed, previous=registry)
        alternate_sender = self.verify_original(
            self.sign_original(sender_id="madar.user-2"),
            expected_sender_id="madar.user-2",
        )
        with self.assertRaises(EnvelopeError):
            check_replay_binding(alternate_sender, previous=registry)
        different_actor = self.verify_original(
            self.sign_original(actor_role="admin"),
            allowed_actor_roles=frozenset({"admin"}),
        )
        with self.assertRaises(EnvelopeError):
            check_replay_binding(different_actor, previous=registry)
        receipt1 = self.verify_response(original, self.verify_query(original),
                                        "received")
        receipt2 = self.verify_response(original, self.verify_query(original),
                                        "not_received")
        rkey = (receipt1.organization_id, receipt1.kind, receipt1.request_id)
        receipt_binding = (
            receipt1.sender_id, receipt1.sender_role, receipt1.actor_role,
            receipt1.purpose, receipt1.key_id, receipt1.payload_sha256,
        )
        with self.assertRaises(EnvelopeError):
            check_replay_binding(receipt2,
                                 previous={rkey: receipt_binding})
        self.assertEqual(check_replay_binding(receipt1,
                                              previous={rkey: receipt_binding}),
                         "identical")
        with self.assertRaises(EnvelopeError):
            check_replay_binding(original, previous={name: "invalid"})

    def test_mismatched_query_and_peer_response_never_authorize_recovery(self):
        original = self.verify_original()
        query = self.verify_query(original)
        other = self.verify_original(self.sign_original(request_id="c" * 32))
        another_query = self.verify_query(other, wire=self.query(
            other, query_request_id="d" * 32))
        receipt = self.verify_response(original, query, "not_received")
        with self.assertRaises(EnvelopeError):
            query_first_recovery_decision(
                original=original, query=another_query, receipt=receipt,
                prior_manual_authorized=True, prior_request_id=ORIGINAL_ID,
                prior_payload_sha256=original.payload_sha256)
        wrong = self.verify_response(other, another_query, "not_received")
        with self.assertRaises(EnvelopeError):
            query_first_recovery_decision(
                original=original, query=query, receipt=wrong,
                prior_manual_authorized=True, prior_request_id=ORIGINAL_ID,
                prior_payload_sha256=original.payload_sha256)


if __name__ == "__main__":
    unittest.main()
