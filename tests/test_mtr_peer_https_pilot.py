"""Pinned TLS client pilot tests: synthetic localhost server and ephemeral data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
from http.client import HTTPSConnection
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from mtr_peer_envelope import (
    EnvelopeError, canonical_json, sign_peer_receipt, sign_request,
    verify_receipt_query, verify_request,
)
from mtr_peer_https_pilot import (
    BoundedLoopbackTlsTestServer, PeerLoopbackHttpsPilot, PeerPilotDenied,
    PeerPilotProtocolError, PeerPilotUncertain, PeerPilotKeys,
)
from tests.test_lan_tls import _CERT, _KEY


NOW = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
BEARER = b"synthetic-only-peer-transport-token-42-chars"
KEYS = PeerPilotKeys("test-org", "madar-synthetic", "madar-key-1",
                     "taraz-synthetic", "taraz-key-1", b"m" * 32, b"t" * 32)


class FakePeerHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        self.server.calls.append(self.path)
        header = self.headers.get("Authorization")
        if header != "Bearer " + BEARER.decode("ascii"):
            self.respond(403, canonical_json({"error": "forbidden"}), "application/json")
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.server.force_close:
            self.close_connection = True
            return
        if self.path == "/mtr/peer/v2/intake":
            record = verify_request(
                body, secret=b"m" * 32, now=NOW,
                expected_organization_id="test-org",
                expected_sender_id="madar-synthetic",
                expected_key_id="madar-key-1", purpose="finance_review_request",
                allowed_actor_roles=frozenset({"editor"}),
            )
            duplicate = record.request_id in self.server.arrived
            self.server.arrived.add(record.request_id)
            if self.server.hold_ack:
                self.server.received_before_ack.set()
                self.server.release_ack.wait(timeout=2)
            self.respond(200, canonical_json({
                "requestId": record.request_id, "received": True,
                "idempotent": duplicate, "financialEventCreated": False,
            }), "application/json")
        elif self.path == "/mtr/peer/v2/query":
            query = verify_receipt_query(
                body, secret=b"m" * 32, now=NOW,
                expected_organization_id="test-org",
                expected_sender_id="madar-synthetic",
                expected_key_id="madar-key-1",
                allowed_actor_roles=frozenset({"editor"}),
            )
            raw = sign_peer_receipt(
                query, lookup_status=("received" if query.payload["originalRequestId"]
                                      in self.server.arrived else "unknown"),
                sender_id="taraz-synthetic", key_id="taraz-key-1",
                issued_at=NOW, expires_at=NOW + timedelta(seconds=60),
                secret=(b"x" * 32 if self.server.bad_peer_mac else b"t" * 32),
            )
            self.respond(200, raw, "application/vnd.mtr-peer+json")
        else:
            self.respond(404, canonical_json({"error": "missing"}), "application/json")

    def respond(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ssl.SSLEOFError):
            # A deliberate lost-ack test has already closed the client socket.
            pass


class LoopbackPeerTlsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-peer-tls-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        cert, key = root / "test.crt", root / "test.key"
        cert.write_text(_CERT, encoding="ascii")
        key.write_text(_KEY, encoding="ascii")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(key))
        server = BoundedLoopbackTlsTestServer(
            FakePeerHandler, context=ctx, max_connections=2,
            handshake_timeout=0.9, read_timeout=2.0,
            loopback_test_only=True,
        )
        server.calls, server.arrived = [], set()
        server.force_close = False
        server.bad_peer_mac = False
        server.hold_ack = False
        server.received_before_ack = threading.Event()
        server.release_ack = threading.Event()
        self.server = server
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def stop():
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)

        self.addCleanup(stop)
        self.pin = hashlib.sha256(ssl.PEM_cert_to_DER_cert(_CERT)).hexdigest()
        self.client = self.make_client()
        self.original_id = "a" * 32
        self.original = self.sign()

    def make_client(self, pin=None, token=BEARER, timeout=3):
        return PeerLoopbackHttpsPilot(
            port=self.server.server_port,
            certificate_sha256=self.pin if pin is None else pin,
            transport_bearer=token, keys=KEYS, timeout=timeout,
            loopback_test_only=True,
        )

    def sign(self):
        return sign_request(
            {"source": "madar", "taskId": "synthetic", "title": "test"},
            organization_id="test-org", sender_id="madar-synthetic",
            actor_role="editor", key_id="madar-key-1",
            request_id=self.original_id, purpose="finance_review_request",
            issued_at=NOW, expires_at=NOW + timedelta(seconds=60),
            secret=b"m" * 32, authorized=True, explicit_manual_action=True,
        )

    def intake(self, client=None, *, manual=True, persisted=True):
        return (client or self.client).intake_once(
            self.original, at=NOW, explicit_human_action=manual,
            host_manual_intent_persisted=persisted,
        )

    def test_signed_synthetic_intake_query_and_observation_are_not_finance(self):
        unknown = self.client.query_verified(self.original, at=NOW,
                                             query_request_id="b" * 32)
        self.assertEqual(unknown["lookupStatus"], "unknown")
        self.assertFalse(unknown["canAutoRetry"])
        delivered = self.intake()
        self.assertTrue(delivered["received"])
        self.assertFalse(delivered["idempotent"])
        self.assertFalse(delivered["officialTarazReceipt"])
        received = self.client.query_verified(self.original, at=NOW,
                                              query_request_id="c" * 32)
        self.assertEqual(received["lookupStatus"], "received")
        self.assertFalse(received["canAutoRetry"])
        self.assertFalse(received["officialTarazReceipt"])
        self.assertEqual(len(self.server.calls), 3)

    def test_wrong_pin_never_transmits_bearer_to_http_handler(self):
        client = self.make_client(pin="0" * 64)
        with self.assertRaises(PeerPilotDenied):
            self.intake(client)
        self.assertEqual(self.server.calls, [])

    def test_explicit_manual_and_host_persisted_authorization_are_required(self):
        for manual, persisted in ((False, True), (True, False), (False, False)):
            with self.subTest(manual=manual, persisted=persisted), self.assertRaises(PeerPilotDenied):
                self.intake(manual=manual, persisted=persisted)
        self.assertEqual(self.server.calls, [])

    def test_wrong_transport_token_fails_closed(self):
        client = self.make_client(token=b"wrong-synthetic-bearer-test-token-1234")
        with self.assertRaises(PeerPilotDenied):
            self.intake(client)
        self.assertNotIn(self.original_id, self.server.arrived)

    def test_signed_query_http_409_json_error_is_explicit_denial_not_envelope_failure(self):
        """A bounded pinned-peer rejection can use JSON, not a signed receipt."""
        def denied(handler):
            handler.server.calls.append(handler.path)
            handler.respond(409, canonical_json({"error": "role_denied"}),
                            "application/json")

        with patch.object(FakePeerHandler, "do_POST", denied):
            with self.assertRaisesRegex(PeerPilotDenied, r"HTTP 409"):
                self.client.query_verified(
                    self.original, at=NOW, query_request_id="f" * 32,
                )
        self.assertEqual(self.server.calls, ["/mtr/peer/v2/query"])
        self.assertEqual(self.server.arrived, set())

    def test_signed_query_http_503_json_error_remains_uncertain_without_retry(self):
        """A bounded peer failure never proves request nonreceipt."""
        def unavailable(handler):
            handler.server.calls.append(handler.path)
            handler.respond(503, canonical_json({"error": "unavailable"}),
                            "application/json")

        with patch.object(FakePeerHandler, "do_POST", unavailable):
            with self.assertRaisesRegex(PeerPilotUncertain, "peer status uncertain"):
                self.client.query_verified(
                    self.original, at=NOW, query_request_id="e" * 32,
                )
        self.assertEqual(self.server.calls, ["/mtr/peer/v2/query"])
        self.assertEqual(self.server.arrived, set())

    def test_signed_peer_response_wrong_direction_key_is_refused(self):
        self.intake()
        self.server.bad_peer_mac = True
        with self.assertRaises(EnvelopeError):
            self.client.query_verified(self.original, at=NOW,
                                       query_request_id="d" * 32)

    def test_aborted_response_must_never_auto_retry(self):
        self.server.force_close = True
        with self.assertRaises(PeerPilotUncertain):
            self.intake()
        self.assertEqual(self.server.calls, ["/mtr/peer/v2/intake"])

    def test_timeout_after_metadata_arrival_requires_query_without_automatic_resend(self):
        self.server.hold_ack = True
        try:
            with self.assertRaises(PeerPilotUncertain):
                self.intake(self.make_client(timeout=0.25))
            self.assertTrue(self.server.received_before_ack.is_set())
            self.assertEqual(self.server.calls, ["/mtr/peer/v2/intake"])
        finally:
            self.server.release_ack.set()
        observation = self.client.query_verified(
            self.original, at=NOW, query_request_id="e" * 32,
        )
        self.assertEqual(observation["lookupStatus"], "received")
        self.assertFalse(observation["canAutoRetry"])
        self.assertEqual(self.server.calls,
                         ["/mtr/peer/v2/intake", "/mtr/peer/v2/query"])

    def test_wrong_org_key_and_expired_wire_block_before_http(self):
        with self.assertRaises(EnvelopeError):
            self.client.intake_once(self.original, at=NOW + timedelta(minutes=5),
                                    explicit_human_action=True,
                                    host_manual_intent_persisted=True)
        self.assertEqual(self.server.calls, [])

    def test_non_test_mode_and_weak_keys_rejected(self):
        with self.assertRaises(PeerPilotDenied):
            PeerLoopbackHttpsPilot(port=self.server.server_port,
                certificate_sha256=self.pin, transport_bearer=BEARER,
                keys=KEYS, loopback_test_only=False)
        with self.assertRaises(PeerPilotDenied):
            PeerPilotKeys("test-org", "madar-synthetic", "madar-key-1",
                          "taraz-synthetic", "taraz-key-1", b"m" * 32, b"m" * 32)

    def test_sender_slots_bound_pre_handshake_work_and_recover_after_failure(self):
        entered = threading.Event()
        release = threading.Event()
        guard = threading.Lock()
        attempts = []

        def stalled_connect(connection):
            with guard:
                attempts.append(connection)
                if len(attempts) == 4:
                    entered.set()
            release.wait(timeout=3)
            raise socket.timeout("synthetic connection stalled before TLS")

        try:
            with patch.object(HTTPSConnection, "connect", stalled_connect):
                with ThreadPoolExecutor(max_workers=4) as workers:
                    inflight = [workers.submit(self.intake) for _ in range(4)]
                    self.assertTrue(entered.wait(timeout=2))
                    before = time.monotonic()
                    with self.assertRaisesRegex(PeerPilotUncertain, "capacity"):
                        self.intake()
                    self.assertLess(time.monotonic() - before, 0.5)
                    self.assertEqual(len(attempts), 4)
                    self.assertEqual(self.server.calls, [])
                    release.set()
                    for attempt in inflight:
                        with self.assertRaises(PeerPilotUncertain):
                            attempt.result(timeout=3)
        finally:
            release.set()
        self.assertTrue(self.intake()["received"])
        self.assertEqual(self.server.calls, ["/mtr/peer/v2/intake"])

    def test_unauthenticated_slow_tls_cannot_monopolize_accept_or_worker_slots(self):
        entered = threading.Event()
        finished = threading.Event()
        guard = threading.Lock()
        counts = {"entered": 0, "finished": 0}
        original = self.server.process_request_thread

        def observed_worker(request, address):
            with guard:
                counts["entered"] += 1
                if counts["entered"] == 2:
                    entered.set()
            try:
                original(request, address)
            finally:
                with guard:
                    counts["finished"] += 1
                    if counts["finished"] == 2:
                        finished.set()

        self.server.process_request_thread = observed_worker
        stalled = []
        try:
            for _ in range(2):
                raw = socket.create_connection(("127.0.0.1", self.server.server_port),
                                               timeout=1)
                stalled.append(raw)
            self.assertTrue(entered.wait(timeout=1.5))
            started = time.monotonic()
            with self.assertRaises(PeerPilotUncertain):
                self.intake()
            self.assertLess(time.monotonic() - started, 0.85,
                            "a full peer must reject promptly without blocking accept")
            self.assertEqual(counts["entered"], 2,
                             "no third handshake worker may start at capacity")
            self.assertEqual(self.server.calls, [],
                             "an unpinned or unhandshaken peer must not see a bearer")
            self.assertTrue(finished.wait(timeout=2.5),
                            "idle TLS handshakes must expire without client cooperation")
        finally:
            for raw in stalled:
                raw.close()
        self.assertTrue(self.intake()["received"])
        self.assertEqual(self.server.calls, ["/mtr/peer/v2/intake"])


if __name__ == "__main__":
    unittest.main()
