"""Madar-to-Taraz *synthetic loopback* pinned TLS transport (NOT DEPLOYED).

This module never starts a process, discovers peers, reads a real credential,
contacts the LAN, posts finance, or automatically retries a request. Only an
explicit Python caller can construct it with host-owned, ephemeral test keys.
It can speak to an opt-in *metadata-only* Taraz test peer on 127.0.0.1.

Transport assertions are not organizational authorization. The host must
authenticate a human, persist an exact UNSENT manual authorization, recheck
the saved request and reserve a one-shot dispatch before using this client.
The separate E2 test coordinator owns that gate; a direct call to this
low-level transport does not enforce it. Both remain synthetic-only,
NOT for operational forwarding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import hmac
from http.client import HTTPSConnection, HTTPException
from http.server import ThreadingHTTPServer
import json
import re
import socket
import ssl
import threading

from mtr_peer_envelope import (
    EnvelopeError, canonical_json, sign_receipt_query, verify_peer_receipt, verify_receipt_query,
    verify_request,
)


_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_CONTENT_TYPE = "application/vnd.mtr-peer+json"
_MAX_RESULT = 32768
_MAX_ACTIVE_SENDS = 4
_send_slots = threading.BoundedSemaphore(_MAX_ACTIVE_SENDS)


class PeerPilotDenied(ValueError):
    """A configured local identity, TLS pin or human action was not authorized."""


class PeerPilotUncertain(ConnectionError):
    """Outcome is unknown: never retry a submission without peer query first."""


class PeerPilotProtocolError(ValueError):
    """The test peer supplied a malformed or contradictory response."""


class BoundedLoopbackTlsTestServer(ThreadingHTTPServer):
    """Opt-in test listener: reserve a worker slot before starting TLS.

    The listening socket stays plain TCP. TLS handshakes run only in bounded
    worker threads, so a stalled unauthenticated client cannot block accept().
    This is a synthetic Madar fixture; it does not patch the Taraz listener.
    """

    address_family = socket.AF_INET
    request_queue_size = 8
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, handler, *, context: ssl.SSLContext, port=0,
                 max_connections=4, handshake_timeout=1.0, read_timeout=2.0,
                 loopback_test_only=False):
        if loopback_test_only is not True:
            raise PeerPilotDenied("synthetic TLS listener requires explicit opt-in")
        if (not isinstance(context, ssl.SSLContext) or
                type(port) is not int or not 0 <= port <= 65535 or
                type(max_connections) is not int or not 1 <= max_connections <= 8 or
                type(handshake_timeout) not in (int, float) or
                not 0.1 <= handshake_timeout <= 2.0 or
                type(read_timeout) not in (int, float) or
                not 0.1 <= read_timeout <= 5.0):
            raise PeerPilotDenied("invalid bounded test listener configuration")
        self._tls_context = context
        self._handshake_timeout = float(handshake_timeout)
        self._read_timeout = float(read_timeout)
        self._admission_slots = threading.BoundedSemaphore(max_connections)
        super().__init__(("127.0.0.1", port), handler)

    def process_request(self, request, client_address):
        # This runs on the accept thread, BEFORE allocating a worker or TLS.
        if not self._admission_slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            request.close()
            self._admission_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(self._handshake_timeout)
            with self._tls_context.wrap_socket(request, server_side=True) as tls:
                tls.settimeout(self._read_timeout)
                super().process_request_thread(tls, client_address)
        except (OSError, TimeoutError, ssl.SSLError):
            # No HTTP handler or bearer processing occurs on failed handshakes.
            pass
        finally:
            request.close()
            self._admission_slots.release()


@dataclass(frozen=True, slots=True)
class PeerPilotKeys:
    """Trusted *caller-provided* secret context. Not persisted by this module."""

    organization_id: str
    sender_id: str
    sender_key_id: str
    peer_id: str
    peer_key_id: str
    sender_secret: bytes = field(repr=False)
    peer_secret: bytes = field(repr=False)

    def __post_init__(self):
        for value in (self.organization_id, self.sender_id, self.sender_key_id,
                      self.peer_id, self.peer_key_id):
            if type(value) is not str or not _TOKEN.fullmatch(value):
                raise PeerPilotDenied("invalid configured peer identity")
        if (type(self.sender_secret) is not bytes or
                type(self.peer_secret) is not bytes or
                not 32 <= len(self.sender_secret) <= 4096 or
                not 32 <= len(self.peer_secret) <= 4096 or
                hmac.compare_digest(self.sender_secret, self.peer_secret)):
            raise PeerPilotDenied("missing or reused directional secret")


class PeerLoopbackHttpsPilot:
    """Explicit test-only 127.0.0.1 sender with pinned cert before bearer."""

    def __init__(self, *, port: int, certificate_sha256: str,
                 transport_bearer: bytes, keys: PeerPilotKeys, timeout=5.0,
                 loopback_test_only: bool):
        if loopback_test_only is not True:
            raise PeerPilotDenied("pilot is not authorized for operational transport")
        if type(port) is not int or not 1 <= port <= 65535:
            raise PeerPilotDenied("explicit loopback port required")
        if type(certificate_sha256) is not str or not _SHA.fullmatch(certificate_sha256):
            raise PeerPilotDenied("exact SHA-256 certificate pin required")
        if (type(transport_bearer) is not bytes or
                not 32 <= len(transport_bearer) <= 4096 or
                any(byte < 33 or byte > 126 for byte in transport_bearer)):
            raise PeerPilotDenied("valid in-memory transport bearer required")
        if type(keys) is not PeerPilotKeys:
            raise PeerPilotDenied("trusted key context required")
        if type(timeout) not in (int, float) or not 0.25 <= timeout <= 10:
            raise PeerPilotDenied("bounded timeout required")
        self._port = port
        self._pin = bytes.fromhex(certificate_sha256)
        self._bearer = transport_bearer
        self._keys = keys
        self._timeout = float(timeout)

    def _post(self, route: str, wire: bytes, *, response_is_envelope: bool) -> bytes:
        if type(wire) is not bytes or not 0 < len(wire) <= _MAX_RESULT:
            raise PeerPilotProtocolError("invalid signed wire size")
        if route not in ("/mtr/peer/v2/intake", "/mtr/peer/v2/query"):
            raise PeerPilotDenied("unknown pilot route")
        # Admission precedes both TCP connect and the pinned TLS handshake.
        # One sender process cannot create unlimited in-flight TLS connections.
        if not _send_slots.acquire(blocking=False):
            raise PeerPilotUncertain("test peer connection capacity exhausted; no request sent")
        connection = None
        sent = False
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            # This test-only transport uses pinning, not the machine CA store.
            # The *peer certificate is compared before sending any bearer/header*.
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            connection = HTTPSConnection("127.0.0.1", self._port, timeout=self._timeout,
                                         context=context)
            connection.connect()
            actual = hashlib.sha256(connection.sock.getpeercert(binary_form=True)).digest()
            if not hmac.compare_digest(actual, self._pin):
                raise PeerPilotDenied("test peer certificate pin mismatch")
            headers = {
                "Host": f"127.0.0.1:{self._port}",
                "Authorization": "Bearer " + self._bearer.decode("ascii"),
                "Content-Type": _CONTENT_TYPE,
                "Accept": _CONTENT_TYPE if response_is_envelope else "application/json",
                "Connection": "close",
            }
            # Mark uncertainty *before* the write. A network failure gives no
            # proof that the peer did not persist the request.
            sent = True
            connection.request("POST", route, body=wire, headers=headers)
            response = connection.getresponse()
            length = response.getheader("Content-Length")
            try:
                bounded = int(length) if length is not None else None
            except (TypeError, ValueError) as exc:
                raise PeerPilotProtocolError("invalid peer content length") from exc
            if bounded is None or not 0 < bounded <= _MAX_RESULT:
                raise PeerPilotProtocolError("missing/oversized peer response")
            body = response.read(bounded + 1)
            if len(body) != bounded:
                raise PeerPilotUncertain("peer response was truncated")
            if response.status != 200:
                # A pinned peer can return bounded application/json errors to
                # an envelope query. Interpret the HTTP denial *before* the
                # success-only envelope Content-Type, never as a signed receipt.
                # Especially for a timeout or 5xx, do not assume nonreceipt.
                if response.status in (400, 401, 403, 404, 409, 413, 415):
                    raise PeerPilotDenied(f"peer rejected request (HTTP {response.status})")
                raise PeerPilotUncertain("peer status uncertain")
            expected_type = _CONTENT_TYPE if response_is_envelope else "application/json"
            if response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != expected_type:
                raise PeerPilotProtocolError("unexpected peer content type")
            return body
        except PeerPilotUncertain:
            # PeerPilotUncertain extends ConnectionError/OSError; do not
            # accidentally relabel a deliberate bounded HTTP 5xx decision
            # as a socket exception in the broad transport handler below.
            raise
        except (OSError, HTTPException, ssl.SSLError, socket.timeout) as exc:
            raise PeerPilotUncertain(
                "peer transport uncertain after attempt" if sent else
                "peer transport unavailable; no request sent by this client"
            ) from exc
        finally:
            try:
                if connection is not None:
                    connection.close()
            finally:
                _send_slots.release()

    def intake_once(self, original_wire: bytes, *, at: datetime,
                    explicit_human_action: bool, host_manual_intent_persisted: bool) -> dict:
        """One deliberate synthetic attempt, no auto retry and no finance write."""
        if explicit_human_action is not True or host_manual_intent_persisted is not True:
            raise PeerPilotDenied("persisted manually authorized host intent required")
        original = verify_request(
            original_wire, secret=self._keys.sender_secret, now=at,
            expected_organization_id=self._keys.organization_id,
            expected_sender_id=self._keys.sender_id,
            expected_key_id=self._keys.sender_key_id,
            purpose="finance_review_request",
            allowed_actor_roles=frozenset({"admin", "editor", "finance_submitter"}),
        )
        raw = self._post("/mtr/peer/v2/intake", original_wire,
                         response_is_envelope=False)
        def unique_pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise PeerPilotProtocolError("duplicate peer response field")
                result[key] = value
            return result

        def reject_nonfinite(_):
            raise PeerPilotProtocolError("nonfinite peer response")

        try:
            record = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                                parse_constant=reject_nonfinite)
            if canonical_json(record) != raw:
                raise PeerPilotProtocolError("noncanonical peer metadata response")
        except (ValueError, UnicodeError, EnvelopeError) as exc:
            raise PeerPilotProtocolError("malformed peer receipt metadata") from exc
        if (type(record) is not dict or set(record) != {
                "requestId", "received", "idempotent", "financialEventCreated"
            } or record["requestId"] != original.request_id or
                record["received"] is not True or
                type(record["idempotent"]) is not bool or
                record["financialEventCreated"] is not False):
            raise PeerPilotProtocolError("unbound or financial peer result")
        # HTTP 200 and this JSON are *metadata-only* delivery hints, not a
        # Taraz-signed receipt or finance acknowledgement. Query separately.
        return {**record, "officialTarazReceipt": False}

    def query_verified(self, original_wire: bytes, *, at: datetime,
                       query_request_id: str, evidence_sink=None) -> dict:
        """Independent signed lookup; optional trusted in-process audit sink.

        The three signed raw wires are passed only after HMAC verification to
        a Python callback explicitly injected by the host, never to HTTP/UI.
        A failed evidence sink fails the query; no automatic retry is issued.
        """
        if evidence_sink is not None and not callable(evidence_sink):
            raise PeerPilotDenied("trusted signed evidence sink must be callable")
        if type(query_request_id) is not str or not _ID.fullmatch(query_request_id):
            raise PeerPilotDenied("unique query identity required")
        original = verify_request(
            original_wire, secret=self._keys.sender_secret, now=at,
            expected_organization_id=self._keys.organization_id,
            expected_sender_id=self._keys.sender_id,
            expected_key_id=self._keys.sender_key_id,
            purpose="finance_review_request",
            allowed_actor_roles=frozenset({"admin", "editor", "finance_submitter"}),
        )
        query_wire = sign_receipt_query(
            original, query_request_id=query_request_id,
            key_id=self._keys.sender_key_id, issued_at=at,
            expires_at=at + timedelta(seconds=60),
            secret=self._keys.sender_secret,
        )
        query = verify_receipt_query(
            query_wire, secret=self._keys.sender_secret, now=at,
            expected_organization_id=self._keys.organization_id,
            expected_sender_id=self._keys.sender_id,
            expected_key_id=self._keys.sender_key_id,
            allowed_actor_roles=frozenset({"admin", "editor", "finance_submitter"}),
        )
        receipt_wire = self._post("/mtr/peer/v2/query", query_wire,
                                  response_is_envelope=True)
        verified = verify_peer_receipt(
            receipt_wire, original=original, query=query,
            secret=self._keys.peer_secret, now=at,
            expected_peer_id=self._keys.peer_id,
            expected_peer_key_id=self._keys.peer_key_id,
        )
        if evidence_sink is not None:
            evidence_sink(original_wire, query_wire, receipt_wire)
        status = verified.payload["lookupStatus"]
        return {
            "requestId": original.request_id,
            "queryRequestId": query_request_id,
            "originalPayloadSha256": original.payload_sha256,
            "lookupStatus": status,
            "peerEnvelopeSha256": verified.envelope_sha256,
            "canAutoRetry": False,
            "financialEventCreated": False,
            "officialTarazReceipt": False,
        }


__all__ = ["PeerPilotKeys", "PeerLoopbackHttpsPilot", "PeerPilotDenied",
           "PeerPilotUncertain", "PeerPilotProtocolError",
           "BoundedLoopbackTlsTestServer"]
