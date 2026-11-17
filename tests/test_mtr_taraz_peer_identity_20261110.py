"""Synthetic-only security tests for nonfinancial Taraz peer review identity.

No installed Taraz/Madar EXE, real account, network, filesystem ledger or
operational key is used. The identity secret below is test-only fixed data.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest

from mtr_taraz_peer_identity import (
    PeerIdentityError, make_peer_review_attestation,
    verify_peer_review_attestation,
)

_NOW = datetime(2026, 11, 10, 13, 0, tzinfo=timezone.utc)
_KEY = b"TEST-ONLY-taraz-peer-key-NEVER-USE-IN-PRODUCTION-123456"
_OTHER = b"OTHER-UNTRUSTED-key-material-for-synthetic-fixture-123456"
_ID = "1" * 32
_CHALLENGE = "a" * 32


def _bytes(value):
    return json.dumps(value, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf8")


class SyntheticPeerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "schema": 1, "source": "madar", "id": _ID,
            "taskId": "qa-task", "projectId": "qa-project",
            "title": "Synthetic manual UI proposal",
            "createdUtc": "2026-11-10T12:58:00+00:00",
        }
        self.review = {
            "schema": 1, "source": "taraz", "id": _ID,
            "taskId": "qa-task", "state": "reviewed",
            "reviewedUtc": "2026-11-10T12:59:00+00:00",
            "financialEventCreated": False,
        }
        self.source_raw = _bytes(self.source)
        self.review_raw = _bytes(self.review)
        self.challenges = {("taraz-qa-peer", _ID, _CHALLENGE)}
        self.consume_calls = []
        self.proof = self.sign()

    def sign(self, **changes):
        arguments = {
            "source_raw": self.source_raw, "review_raw": self.review_raw,
            "organization_id": "synthetic-company", "peer_id": "taraz-qa-peer",
            "key_id": "synthetic-key-1", "challenge": _CHALLENGE,
            "issued_at": _NOW, "expires_at": _NOW + timedelta(seconds=180),
            "secret": _KEY,
        }
        arguments.update(changes)
        return make_peer_review_attestation(**arguments)

    def consume(self, peer, request, challenge):
        item = (peer, request, challenge)
        self.consume_calls.append(item)
        if item not in self.challenges:
            return False
        self.challenges.remove(item)
        return True

    def verify(self, **changes):
        arguments = {
            "wire": self.proof, "source_raw": self.source_raw,
            "review_raw": self.review_raw, "secret": _KEY, "now": _NOW,
            "expected_organization_id": "synthetic-company",
            "expected_peer_id": "taraz-qa-peer",
            "expected_key_id": "synthetic-key-1",
            "expected_request_id": _ID, "expected_task_id": "qa-task",
            "expected_project_id": "qa-project",
            "expected_challenge": _CHALLENGE,
            "consume_challenge": self.consume,
        }
        arguments.update(changes)
        return verify_peer_review_attestation(**arguments)

    def test_only_valid_independently_pinned_authenticated_peer_verifies(self):
        observed = self.verify()
        self.assertIs(observed["peerVerified"], True)
        self.assertEqual(observed["reviewState"], "reviewed")
        self.assertEqual(observed["sourceDigest"],
                         hashlib.sha256(self.source_raw).hexdigest())
        self.assertEqual(observed["reviewDigest"],
                         hashlib.sha256(self.review_raw).hexdigest())
        self.assertFalse(observed["financialEventCreated"])
        self.assertFalse(observed["postingEnabled"])
        self.assertFalse(observed["ledgerPostingPerformed"])
        self.assertFalse(observed["officialFinancialReceiptVerified"])
        self.assertEqual(self.consume_calls,
                         [("taraz-qa-peer", _ID, _CHALLENGE)])

    def test_no_self_attestation_from_local_receipt_without_valid_hmac(self):
        for update in (
            {"secret": _OTHER}, {"secret": b"short"},
            {"secret": None}, {"secret": "a string"},
            {"wire": b"{}"}, {"wire": self.proof[:-3]},
        ):
            with self.subTest(update=update):
                with self.assertRaises(PeerIdentityError):
                    self.verify(**update)
                self.assertEqual(self.consume_calls, [])

    def test_altered_signed_field_and_mac_must_fail(self):
        record = json.loads(self.proof)
        for name, value in (
            ("peerId", "other-peer"), ("keyId", "other-key"),
            ("organizationId", "other-company"),
            ("reviewState", "rejected"), ("purpose", "invoice-posting"),
            ("financialEventCreated", True), ("mac", "0" * 64),
            ("sourceDigest", "0" * 64), ("reviewDigest", "0" * 64),
            ("requestId", "2" * 32), ("taskId", "other-task"),
            ("projectId", "other-project"), ("challenge", "b" * 32),
        ):
            with self.subTest(field=name):
                bad = _bytes({**record, name: value})
                with self.assertRaises(PeerIdentityError):
                    self.verify(wire=bad)
                self.assertEqual(self.consume_calls, [])

    def test_trusted_org_peer_key_and_scope_mismatch_fails(self):
        for changes in (
            {"expected_peer_id": "other-peer"},
            {"expected_key_id": "wrong-key"},
            {"expected_organization_id": "other-company"},
            {"expected_request_id": "2" * 32},
            {"expected_task_id": "another-task"},
            {"expected_project_id": "another-project"},
            {"expected_challenge": "b" * 32},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(PeerIdentityError):
                    self.verify(**changes)
                self.assertEqual(self.consume_calls, [])

    def test_raw_source_digest_and_review_digest_must_match_exact_bytes(self):
        tampered_source = dict(self.source, title="Changed after review")
        tampered_review = dict(self.review, reviewedUtc="2026-11-10T12:59:30+00:00")
        for args in (
            {"source_raw": _bytes(tampered_source)},
            {"source_raw": _bytes(self.source) + b" "},
            {"review_raw": _bytes(tampered_review)},
            {"review_raw": _bytes(self.review) + b" "},
        ):
            with self.subTest(args=args):
                with self.assertRaises(PeerIdentityError):
                    self.verify(**args)
                self.assertEqual(self.consume_calls, [])

    def test_stale_expired_future_or_long_lived_proof(self):
        for changes in (
            {"now": _NOW + timedelta(seconds=180)},
            {"now": _NOW + timedelta(days=1)},
            {"now": _NOW - timedelta(seconds=31)},
            {"now": datetime(2026, 11, 10, 13, 0)},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(PeerIdentityError):
                    self.verify(**changes)
                self.assertEqual(self.consume_calls, [])
        with self.assertRaises(PeerIdentityError):
            self.sign(expires_at=_NOW + timedelta(seconds=301))
        with self.assertRaises(PeerIdentityError):
            self.sign(expires_at=_NOW)

    def test_durable_one_time_consumer_required_and_replay_denied(self):
        self.assertTrue(self.verify()["peerVerified"])
        with self.assertRaisesRegex(PeerIdentityError, "replayed"):
            self.verify()
        self.assertEqual(len(self.consume_calls), 2)
        self.assertEqual(self.challenges, set())

    def test_challenge_consumer_must_return_literal_true(self):
        for bad in (False, 1, None, "true"):
            with self.subTest(bad=bad):
                with self.assertRaises(PeerIdentityError):
                    self.verify(consume_challenge=lambda *_: bad)
        with self.assertRaises(PeerIdentityError):
            self.verify(consume_challenge=None)
        with self.assertRaisesRegex(PeerIdentityError, "consumption"):
            self.verify(consume_challenge=lambda *_: 1 / 0)

    def test_rejected_metadata_review_may_verify_but_never_finance(self):
        rejected = dict(self.review, state="rejected")
        raw = _bytes(rejected)
        proof = self.sign(review_raw=raw)
        verified = self.verify(wire=proof, review_raw=raw)
        self.assertIs(verified["peerVerified"], True)
        self.assertEqual(verified["reviewState"], "rejected")
        self.assertFalse(verified["officialFinancialReceiptVerified"])

    def test_persisted_receipt_claims_finance_or_cross_task_fail(self):
        for modified in (
            {"financialEventCreated": True}, {"taskId": "other-task"},
            {"id": "b" * 32}, {"state": "posted"}, {"schema": 2},
        ):
            with self.subTest(modified=modified):
                forged = _bytes({**self.review, **modified})
                with self.assertRaises(PeerIdentityError):
                    self.sign(review_raw=forged)
                with self.assertRaises(PeerIdentityError):
                    self.verify(review_raw=forged)

    def test_duplicate_noncanonical_malformed_or_oversized_wire_fail(self):
        for invalid in (
            self.proof + b" ", self.proof.replace(b'"version":1',
                                                  b'"version":1,"version":1'),
            b"{", b"[]", b"null", b"\xff",
            b'{"version":NaN}', b"x" * 4097,
        ):
            with self.subTest(invalid=invalid[:30]):
                with self.assertRaises(PeerIdentityError):
                    self.verify(wire=invalid)
                self.assertEqual(self.consume_calls, [])

    def test_untrusted_proof_auth_does_not_consume_challenge(self):
        forged = self.sign(secret=_OTHER)
        with self.assertRaisesRegex(PeerIdentityError, "HMAC"):
            self.verify(wire=forged)
        self.assertEqual(self.consume_calls, [])
        self.assertIn(("taraz-qa-peer", _ID, _CHALLENGE), self.challenges)

    def test_invalid_source_and_receipt_structures_fail(self):
        for modified in (
            {"id": "2" * 32}, {"projectId": "other-project"},
            {"createdUtc": "2026-11-10T12:58:00+03:30"},
            {"schema": True}, {"amountRial": -3},
        ):
            with self.subTest(modified=modified):
                forged = _bytes({**self.source, **modified})
                with self.assertRaises(PeerIdentityError):
                    self.verify(source_raw=forged)
        with self.assertRaises(PeerIdentityError):
            self.verify(source_raw=b"{" + b" " * 32770)

    def test_review_timestamp_must_follow_proposal_and_precede_attestation(self):
        cases = (
            {"reviewedUtc": "2026-11-10T12:57:59+00:00"},
            {"reviewedUtc": "2026-11-10T13:00:01+00:00"},
            {"reviewedUtc": "2026-11-10T12:59:00+03:30"},
            {"reviewedUtc": 17},
            {"state": ["reviewed"]},
        )
        for changed in cases:
            with self.subTest(changed=changed):
                bad_review = _bytes({**self.review, **changed})
                with self.assertRaises(PeerIdentityError):
                    self.sign(review_raw=bad_review)
                with self.assertRaises(PeerIdentityError):
                    self.verify(review_raw=bad_review)

    def test_self_claimed_peerverified_true_in_proof_is_not_a_credential(self):
        forged = json.loads(self.proof)
        forged["peerVerified"] = True
        with self.assertRaises(PeerIdentityError):
            self.verify(wire=_bytes(forged))
        self.assertEqual(self.consume_calls, [])


if __name__ == "__main__":
    unittest.main()
