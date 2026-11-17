"""Real source-to-source MTR peer v2 interop; synthetic, no LAN or finance."""
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

from mtr_peer_envelope import (
    EnvelopeError, query_first_recovery_decision, sign_peer_receipt,
    sign_receipt_query, sign_request, verify_peer_receipt,
    verify_receipt_query, verify_request,
)


NOW = datetime(2026, 11, 9, 15, 0, 0, tzinfo=timezone.utc)


class TwoSourceSyntheticPeerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("MTR_TARAZ_SOURCE")
        if not source:
            raise unittest.SkipTest("MTR_TARAZ_SOURCE detached Taraz worktree required")
        location = Path(source) / "taraz_mtr_peer_registry.py"
        if not location.is_file():
            raise unittest.SkipTest("Taraz isolated peer registry unavailable")
        spec = importlib.util.spec_from_file_location("isolated_taraz_mtr_registry_v2", location)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load Taraz registry from explicit source")
        cls.taraz = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.taraz
        spec.loader.exec_module(cls.taraz)

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-two-source-v2-")
        self.addCleanup(temp.cleanup)
        conf = self.taraz.PeerConfig(
            "office-one", "madar-host-1", "madar-key",
            "taraz-peer-1", "taraz-key", b"m" * 32, b"t" * 32,
        )
        self.registry = self.taraz.TarazPeerRegistry(
            Path(temp.name) / "peer.sqlite3", conf,
        )
        self.original_id = "a" * 32
        self.payload = {
            "schema": 1, "source": "madar", "id": self.original_id,
            "taskId": "example-2", "projectId": "p-sample", "title": "synthetic",
            "createdUtc": NOW.isoformat(),
        }
        self.wire = sign_request(
            self.payload, organization_id="office-one", sender_id="madar-host-1",
            actor_role="editor", key_id="madar-key", request_id=self.original_id,
            purpose="finance_review_request", issued_at=NOW,
            expires_at=NOW + timedelta(seconds=60), secret=b"m" * 32,
            authorized=True, explicit_manual_action=True,
        )
        self.original = verify_request(
            self.wire, secret=b"m" * 32, now=NOW,
            expected_organization_id="office-one", expected_sender_id="madar-host-1",
            expected_key_id="madar-key", purpose="finance_review_request",
            allowed_actor_roles=frozenset({"admin", "editor"}),
        )

    def query(self):
        wire = sign_receipt_query(
            self.original, query_request_id="b" * 32, key_id="madar-key",
            issued_at=NOW, expires_at=NOW + timedelta(seconds=60),
            secret=b"m" * 32,
        )
        checked = verify_receipt_query(
            wire, secret=b"m" * 32, now=NOW,
            expected_organization_id="office-one", expected_sender_id="madar-host-1",
            expected_key_id="madar-key", allowed_actor_roles=frozenset({"editor"}),
        )
        return wire, checked

    def verify_peer(self, wire, verified_query):
        return verify_peer_receipt(
            wire, original=self.original, query=verified_query,
            secret=b"t" * 32, now=NOW, expected_peer_id="taraz-peer-1",
            expected_peer_key_id="taraz-key",
        )

    def test_two_real_modules_sign_intake_query_verify_with_no_finance(self):
        received = self.registry.intake(self.wire, now=NOW, verified_transport_peer=True)
        self.assertFalse(received["financialEventCreated"])
        self.assertFalse(received["idempotent"])
        self.assertTrue(self.registry.intake(self.wire, now=NOW,
                                             verified_transport_peer=True)["idempotent"])
        wire, checked = self.query()
        lookup = self.registry.query_receipt(wire, now=NOW,
                                             verified_transport_peer=True)
        response = self.verify_peer(lookup, checked)
        self.assertEqual(response.payload["lookupStatus"], "received")
        self.assertEqual(query_first_recovery_decision(
            original=self.original, query=checked, receipt=response,
            prior_manual_authorized=True, prior_request_id=self.original_id,
            prior_payload_sha256=self.original.payload_sha256,
        ), "observe_peer_claim_received")

    def test_unknown_remains_unknown_and_cannot_justify_automatic_replay(self):
        wire, checked = self.query()
        lookup = self.registry.query_receipt(wire, now=NOW,
                                             verified_transport_peer=True)
        receipt = self.verify_peer(lookup, checked)
        self.assertEqual(receipt.payload["lookupStatus"], "unknown")
        self.assertEqual(query_first_recovery_decision(
            original=self.original, query=checked, receipt=receipt,
            prior_manual_authorized=True, prior_request_id=self.original_id,
            prior_payload_sha256=self.original.payload_sha256,
        ), "hold_uncertain")

    def test_no_authenticated_transport_or_wrong_direction_key(self):
        with self.assertRaises(PermissionError):
            self.registry.intake(self.wire, now=NOW, verified_transport_peer=False)
        wire, checked = self.query()
        unsigned = sign_peer_receipt(
            checked, lookup_status="received", sender_id="taraz-peer-1",
            key_id="taraz-key", issued_at=NOW,
            expires_at=NOW + timedelta(seconds=60), secret=b"m" * 32,
        )
        with self.assertRaises(EnvelopeError):
            self.verify_peer(unsigned, checked)


if __name__ == "__main__":
    unittest.main()
