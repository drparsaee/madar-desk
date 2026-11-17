"""Actual synthetic HTTPS loopback roundtrip between *both* source worktrees.

Not an installed-host, official finance API, or real network-identity test.
Taraz modules and public TEST-ONLY cert fixture are loaded from the explicit
MTR_TARAZ_SOURCE detached worktree. No live accounts or finance data exist.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import importlib.util
import os
from pathlib import Path
import ssl
import sys
import tempfile
import threading
import unittest

from mtr_peer_envelope import sign_request
from mtr_e2_dispatch_gate import OneShotDispatchGate, DispatchGateConflict
from mtr_host_request_store import HostRequestStore, TrustedPrincipal
from mtr_peer_https_pilot import (
    PeerLoopbackHttpsPilot, PeerPilotDenied, PeerPilotKeys,
    PeerPilotUncertain,
)


TEST_BEARER = b"synthetic-bearer-never-for-production-1234567890"
KEYS = PeerPilotKeys(
    "office-one", "madar-host-1", "madar-key",
    "taraz-peer-1", "taraz-key", b"m" * 32, b"t" * 32,
)


class MtrTwoSourceHttpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.getenv("MTR_TARAZ_SOURCE")
        if not source:
            raise unittest.SkipTest("explicit detached MTR_TARAZ_SOURCE required")
        root = Path(source).resolve()
        for path in (root / "taraz_mtr_peer_registry.py",
                     root / "taraz_mtr_peer_http.py",
                     root / "tests" / "test_taraz_mtr_peer_http.py"):
            if not path.is_file():
                raise unittest.SkipTest("Taraz detached peer pilot source missing")
        sys.path.insert(0, str(root))
        try:
            cls.registry_module = importlib.import_module("taraz_mtr_peer_registry")
            cls.http_module = importlib.import_module("taraz_mtr_peer_http")
            fixture = root / "tests" / "test_taraz_mtr_peer_http.py"
            spec = importlib.util.spec_from_file_location("taraz_test_tls_fixture_only", fixture)
            if spec is None or spec.loader is None:
                raise RuntimeError("cannot load synthetic public test certificate")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            cls.pem_cert = module._CERT
            cls.pem_key = module._KEY
        finally:
            sys.path.remove(str(root))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mtr-two-repos-tls-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        cert = self.root / "public-test-only.crt"
        key = self.root / "public-test-only.key"
        cert.write_text(self.pem_cert, encoding="ascii")
        key.write_text(self.pem_key, encoding="ascii")
        config = self.registry_module.PeerConfig(
            KEYS.organization_id, KEYS.sender_id, KEYS.sender_key_id,
            KEYS.peer_id, KEYS.peer_key_id, KEYS.sender_secret,
            KEYS.peer_secret,
        )
        self.registry = self.registry_module.TarazPeerRegistry(
            self.root / "metadata-only.sqlite3", config,
        )
        self.server = self.http_module.create_loopback_https_server(
            registry=self.registry, transport_bearer=TEST_BEARER,
            certfile=cert, keyfile=key, opt_in=True,
            port=0, read_timeout_seconds=2.0,
        )
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

        def stop():
            self.server.shutdown()
            self.thread.join(timeout=3)
            self.server.server_close()

        self.addCleanup(stop)
        self.pin = hashlib.sha256(ssl.PEM_cert_to_DER_cert(self.pem_cert)).hexdigest()
        self.client = self.make_client()
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.request_id = "a" * 32
        self.wire = sign_request(
            {"schema": 1, "source": "madar", "id": self.request_id,
             "taskId": "example-2", "projectId": "p-sample",
             "title": "synthetic no finance posting",
             "createdUtc": self.now.isoformat()},
            organization_id=KEYS.organization_id,
            sender_id=KEYS.sender_id, actor_role="editor",
            key_id=KEYS.sender_key_id, request_id=self.request_id,
            purpose="finance_review_request", issued_at=self.now,
            expires_at=self.now + timedelta(minutes=2),
            secret=KEYS.sender_secret, authorized=True,
            explicit_manual_action=True,
        )

    def make_client(self, *, pin=None, token=TEST_BEARER):
        return PeerLoopbackHttpsPilot(
            port=self.server.server_port, certificate_sha256=(pin or self.pin),
            transport_bearer=token, keys=KEYS,
            timeout=3, loopback_test_only=True,
        )

    def test_real_two_source_tls_send_and_signed_query_no_finance(self):
        first = self.client.query_verified(self.wire, at=self.now,
                                           query_request_id="b" * 32)
        self.assertEqual(first["lookupStatus"], "unknown")
        self.assertFalse(first["canAutoRetry"])
        delivered = self.client.intake_once(
            self.wire, at=self.now, explicit_human_action=True,
            host_manual_intent_persisted=True,
        )
        self.assertTrue(delivered["received"])
        self.assertFalse(delivered["idempotent"])
        self.assertFalse(delivered["financialEventCreated"])
        later = self.client.query_verified(self.wire, at=self.now,
                                           query_request_id="c" * 32)
        self.assertEqual(later["lookupStatus"], "received")
        self.assertEqual(later["requestId"], self.request_id)
        self.assertFalse(later["officialTarazReceipt"])
        self.assertFalse(later["canAutoRetry"])
        # Both applications actually exchanged HTTPS packets on localhost;
        # this is ONLY a metadata arrival and signed lookup, no ledger.
        with self.registry._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0], 2)

    def test_bad_pin_and_bearer_never_produce_a_registry_entry(self):
        with self.assertRaises(PeerPilotDenied):
            self.make_client(pin="0" * 64).intake_once(
                self.wire, at=self.now, explicit_human_action=True,
                host_manual_intent_persisted=True,
            )
        with self.assertRaises(PeerPilotDenied):
            self.make_client(token=b"synthetic-invalid-bearer-token-1234").intake_once(
                self.wire, at=self.now, explicit_human_action=True,
                host_manual_intent_persisted=True,
            )
        with self.registry._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)

    def test_same_id_conflicting_payload_rejected_and_prior_is_preserved(self):
        self.client.intake_once(self.wire, at=self.now,
                                explicit_human_action=True,
                                host_manual_intent_persisted=True)
        changed = sign_request(
            {"taskId": "synthetic-other", "projectId": "p-sample",
             "title": "changed payload"},
            organization_id=KEYS.organization_id,
            sender_id=KEYS.sender_id, actor_role="editor",
            key_id=KEYS.sender_key_id, request_id=self.request_id,
            purpose="finance_review_request", issued_at=self.now,
            expires_at=self.now + timedelta(minutes=2),
            secret=KEYS.sender_secret, authorized=True,
            explicit_manual_action=True,
        )
        with self.assertRaises(PeerPilotDenied):
            self.client.intake_once(changed, at=self.now,
                                    explicit_human_action=True,
                                    host_manual_intent_persisted=True)
        with self.registry._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)

    def test_ack_lost_after_actual_peer_commit_requires_query_first(self):
        class LoseAckAfterCommit(PeerLoopbackHttpsPilot):
            def _post(inner, route, wire, *, response_is_envelope):
                result = super()._post(route, wire,
                                       response_is_envelope=response_is_envelope)
                # Synthetic fault injected exactly AFTER a successful actual
                # HTTPS/SQLite commit. The caller loses its acknowledgement.
                raise PeerPilotUncertain("synthetic acknowledgement lost")

        broken = LoseAckAfterCommit(
            port=self.server.server_port, certificate_sha256=self.pin,
            transport_bearer=TEST_BEARER, keys=KEYS, timeout=3,
            loopback_test_only=True,
        )
        with self.assertRaises(PeerPilotUncertain):
            broken.intake_once(self.wire, at=self.now,
                               explicit_human_action=True,
                               host_manual_intent_persisted=True)
        with self.registry._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 1)

    def test_three_durable_databases_one_shot_host_then_taraz_tls(self):
        """Host outbox + host gate + detached peer registry, no real posting."""
        source_path = self.root / "host-outbox.sqlite3"
        gate_path = self.root / "host-dispatch.sqlite3"
        host_store = HostRequestStore(source_path)
        principal = TrustedPrincipal(
            user_id="synthetic-editor", org_id=KEYS.organization_id,
            session_id="synthetic-lan-session", role="editor",
            project_ids=frozenset({"p-sample"}),
            permissions=frozenset({"mtr.prepare", "mtr.manual_send", "mtr.read"}),
            authenticated=True, session_valid=True,
        )
        saved = {
            "schema": 1, "source": "madar", "id": self.request_id,
            "taskId": "example-2", "projectId": "p-sample",
            "title": "synthetic no finance posting",
            "createdUtc": self.now.isoformat(),
        }
        prepared = host_store.prepare_request(
            principal=principal, request_id=self.request_id, payload=saved,
            base_revision=13, current_server_revision=13,
            prepare_key="synthetic-prepared-key-1", explicit_manual_action=True,
        )
        authorized = host_store.manual_send(
            principal=principal, request_id=self.request_id,
            expected_payload_sha256=prepared["payloadSha256"],
            expected_base_revision=13, current_server_revision=13,
            send_key="synthetic-send-key-1", explicit_manual_action=True,
        )
        self.assertEqual(authorized["requestState"], "MANUAL_SEND_AUTHORIZED")
        gate = OneShotDispatchGate(gate_path, host_store)
        first = gate.reserve_once(
            principal=principal, request_id=self.request_id,
            expected_payload_sha256=prepared["payloadSha256"],
            expected_base_revision=13, current_server_revision=13,
            send_key="synthetic-send-key-1",
        )
        self.assertTrue(first["firstAttemptGranted"])
        self.assertFalse(first["mayDispatch"])  # Slot already consumed by reservation.
        accepted = self.client.intake_once(
            self.wire, at=self.now,
            explicit_human_action=True,
            host_manual_intent_persisted=first["firstAttemptGranted"],
        )
        self.assertTrue(accepted["received"])
        self.assertFalse(accepted["officialTarazReceipt"])
        gate.mark_unknown_after_attempt(
            principal=principal, request_id=self.request_id,
            expected_base_revision=13, expected_version=1,
        )
        observed = self.client.query_verified(
            self.wire, at=self.now, query_request_id="f" * 32,
        )
        self.assertEqual(observed["lookupStatus"], "received")
        # This is only receipt of transport metadata, never a signed official
        # finance approval; it cannot unlock a further dispatch or G-03 gate.
        status = gate.status(principal=principal, request_id=self.request_id,
                             expected_base_revision=13)
        self.assertEqual(status["state"], "unknown_after_attempt")
        self.assertFalse(status["mayDispatch"])
        self.assertTrue(status["mustQueryFirst"])
        restarted = OneShotDispatchGate(gate_path, HostRequestStore(source_path))
        with self.assertRaises(DispatchGateConflict):
            restarted.reserve_once(
                principal=principal, request_id=self.request_id,
                expected_payload_sha256=prepared["payloadSha256"],
                expected_base_revision=13, current_server_revision=13,
                send_key="synthetic-send-key-1",
            )
        with self.registry._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 1)
        # No second intake. A NEW query ID gets the signed observation.
        receipt = self.client.query_verified(self.wire, at=self.now,
                                             query_request_id="e" * 32)
        self.assertEqual(receipt["lookupStatus"], "received")
        self.assertFalse(receipt["canAutoRetry"])
        with self.registry._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
