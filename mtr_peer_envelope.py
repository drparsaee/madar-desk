"""Pure, signed MTR v2 pilot. Never sends, posts, stores keys or opens a ledger.

HMAC does not itself establish a real Taraz identity. Only an externally
authenticated and ACL-enforcing host may provision the two directional keys,
trust the caller's role, or persist idempotency and manual-authorization state.
All peer lookup statuses in this module remain untrusted FINANCIAL assertions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
from typing import Mapping

VERSION = 2
MAX_PAYLOAD_BYTES = 16384
MAX_ENVELOPE_BYTES = 32768
MAX_TTL_SECONDS = 300
_DOMAIN = b"MTR-peer-envelope-v2\x00"
_ID = re.compile(r"[0-9a-f]{32}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_PURPOSES = {
    "request": frozenset({"finance_review_request", "catalog_read_query",
                          "party_creation_proposal"}),
    "query": frozenset({"receipt_lookup"}),
    "receipt": frozenset({"receipt_lookup_result"}),
}
_REQUEST_ROLES = frozenset({"admin", "editor", "finance_submitter"})
_STATUSES = frozenset({"received", "not_received", "unknown"})
_SUBJECT_FIELDS = frozenset({"originalRequestId", "originalPayloadSha256",
                             "originalPurpose"})
_RECEIPT_FIELDS = _SUBJECT_FIELDS | {
    "queryRequestId", "queryPayloadSha256", "lookupStatus",
}
_BODY_FIELDS = frozenset({
    "protocol", "version", "algorithm", "kind", "purpose",
    "organizationId", "senderId", "senderRole", "actorRole", "audience",
    "keyId", "requestId", "issuedUtc", "expiresUtc", "payloadSha256", "payload",
})


class EnvelopeError(ValueError):
    """Closed protocol gate, including mismatched authorization assumptions."""


@dataclass(frozen=True)
class VerifiedEnvelope:
    """Scalar fields obtained from HMAC verification, not a security token.

    A Python caller can construct this type; externally enforce access
    controls, and only use instances from the explicit verification methods.
    """
    kind: str
    organization_id: str
    sender_id: str
    sender_role: str
    actor_role: str
    key_id: str
    request_id: str
    purpose: str
    payload_sha256: str
    payload_bytes: bytes
    envelope_sha256: str

    @property
    def payload(self) -> dict:
        return json.loads(self.payload_bytes.decode("utf-8"))


def _token(value, field):
    if type(value) is not str or not _TOKEN.fullmatch(value):
        raise EnvelopeError("invalid " + field)
    return value


def _request_id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise EnvelopeError("invalid request ID")
    return value


def _sha(value, field):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise EnvelopeError("invalid " + field)
    return value


def _key(value):
    if type(value) is not bytes or not 32 <= len(value) <= 4096:
        raise EnvelopeError("an explicit 32-byte minimum secret is required")
    return value


def _check_tree(value, depth=0, count=None):
    if count is None:
        count = [0]
    count[0] += 1
    if depth > 8 or count[0] > 512:
        raise EnvelopeError("JSON nesting/count exceeded")
    if value is None or type(value) is bool:
        return
    if type(value) is int and abs(value) <= (1 << 53) - 1:
        return
    if type(value) is str and len(value) <= 4096:
        return
    if type(value) is list and len(value) <= 64:
        for item in value:
            _check_tree(item, depth + 1, count)
        return
    if type(value) is dict and len(value) <= 64:
        for name, item in value.items():
            if type(name) is not str or not name or len(name) > 128:
                raise EnvelopeError("invalid JSON property name")
            _check_tree(item, depth + 1, count)
        return
    raise EnvelopeError("unsupported JSON field type, size, or float")


def canonical_json(value):
    """Deterministic UTF-8 JSON, strict integers, finite bounded plain types."""
    _check_tree(value)
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode("utf8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise EnvelopeError("invalid UTF-8 JSON value") from exc


def _unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise EnvelopeError("duplicate JSON property")
        result[name] = value
    return result


def _bad_constant(_):
    raise EnvelopeError("non-finite JSON number")


def _read(wire):
    if type(wire) is not bytes or len(wire) > MAX_ENVELOPE_BYTES:
        raise EnvelopeError("oversized/non-byte envelope")
    try:
        value = json.loads(wire.decode("utf8"), object_pairs_hook=_unique,
                           parse_constant=_bad_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise EnvelopeError("invalid JSON wire envelope") from exc
    if type(value) is not dict or canonical_json(value) != wire:
        raise EnvelopeError("noncanonical envelope")
    return value


def _utc(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise EnvelopeError("timezone-aware UTC timestamp required")
    utc = value.astimezone(timezone.utc)
    if utc.microsecond:
        raise EnvelopeError("timestamps must have second precision")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value):
    if type(value) is not str or not _UTC.fullmatch(value):
        raise EnvelopeError("noncanonical UTC timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError as exc:
        raise EnvelopeError("invalid UTC date") from exc


def _check_times(issued, expires, now):
    start, end = _parse_utc(issued), _parse_utc(expires)
    current = _parse_utc(_utc(now))
    seconds = (end - start).total_seconds()
    if seconds <= 0 or seconds > MAX_TTL_SECONDS:
        raise EnvelopeError("unbounded or invalid lifetime")
    if (start - current).total_seconds() > 30:
        raise EnvelopeError("message issued too far in the future")
    if current >= end:
        raise EnvelopeError("expired message")


def _mac(body, secret):
    return hmac.new(_key(secret), _DOMAIN + canonical_json(body),
                    hashlib.sha256).hexdigest()


def _build(payload, *, kind, purpose, organization_id, sender_id,
           sender_role, actor_role, audience, key_id, request_id,
           issued_at, expires_at, secret):
    if (type(kind) is not str or kind not in _PURPOSES or
            type(purpose) is not str or purpose not in _PURPOSES[kind]):
        raise EnvelopeError("unapproved kind/purpose")
    if type(payload) is not dict or len(canonical_json(payload)) > MAX_PAYLOAD_BYTES:
        raise EnvelopeError("invalid or oversized payload")
    if (kind in ("request", "query") and
        (sender_role != "madar_sender" or audience != "taraz_peer" or
         actor_role not in _REQUEST_ROLES)):
        raise EnvelopeError("invalid Madar sender/actor")
    if (kind == "receipt" and
        (sender_role != "taraz_peer" or audience != "madar_sender" or
         actor_role != "peer")):
        raise EnvelopeError("invalid Taraz sender/actor")
    body = {
        "protocol": "mtr-peer", "version": VERSION, "algorithm": "HMAC-SHA256",
        "kind": kind, "purpose": purpose,
        "organizationId": _token(organization_id, "organization"),
        "senderId": _token(sender_id, "sender"),
        "senderRole": sender_role, "actorRole": actor_role,
        "audience": audience, "keyId": _token(key_id, "key"),
        "requestId": _request_id(request_id),
        "issuedUtc": _utc(issued_at), "expiresUtc": _utc(expires_at),
        "payloadSha256": hashlib.sha256(canonical_json(payload)).hexdigest(),
        "payload": payload,
    }
    _check_times(body["issuedUtc"], body["expiresUtc"], issued_at)
    wire = canonical_json({**body, "mac": _mac(body, secret)})
    if len(wire) > MAX_ENVELOPE_BYTES:
        raise EnvelopeError("oversized signed envelope")
    return wire


def sign_request(payload, *, organization_id, sender_id, actor_role, key_id,
                 request_id, purpose, issued_at, expires_at, secret,
                 authorized, explicit_manual_action):
    """Sign user-authorized proposal metadata. Does NOT submit it."""
    if authorized is not True or explicit_manual_action is not True:
        raise EnvelopeError("explicit authorized manual action required")
    return _build(payload, kind="request", purpose=purpose,
                  organization_id=organization_id, sender_id=sender_id,
                  sender_role="madar_sender", actor_role=actor_role,
                  audience="taraz_peer", key_id=key_id, request_id=request_id,
                  issued_at=issued_at, expires_at=expires_at, secret=secret)


def _validate_subject(payload):
    if type(payload) is not dict or set(payload) != _SUBJECT_FIELDS:
        raise EnvelopeError("invalid receipt-query subject")
    _request_id(payload["originalRequestId"])
    _sha(payload["originalPayloadSha256"], "original payload SHA")
    if payload["originalPurpose"] != "finance_review_request":
        raise EnvelopeError("invalid original purpose")


def _validate_result(payload):
    if type(payload) is not dict or set(payload) != _RECEIPT_FIELDS:
        raise EnvelopeError("invalid peer lookup result")
    _validate_subject({name: payload[name] for name in _SUBJECT_FIELDS})
    _request_id(payload["queryRequestId"])
    _sha(payload["queryPayloadSha256"], "query payload SHA")
    if type(payload["lookupStatus"]) is not str or payload["lookupStatus"] not in _STATUSES:
        raise EnvelopeError("unrecognized lookup status")


def _verify(wire, *, secret, now, expected_organization_id, expected_sender_id,
            expected_key_id, expected_role, expected_kind, expected_purpose,
            allowed_actor_roles):
    record = _read(wire)
    if set(record) != _BODY_FIELDS | {"mac"}:
        raise EnvelopeError("missing/unknown envelope field")
    if (type(record["version"]) is not int or record["version"] != VERSION or
        record["protocol"] != "mtr-peer" or record["algorithm"] != "HMAC-SHA256"):
        raise EnvelopeError("unsupported version or algorithm")
    kind, purpose = record["kind"], record["purpose"]
    if (type(kind) is not str or kind != expected_kind or
        type(purpose) is not str or
        purpose not in _PURPOSES.get(kind, ()) or purpose != expected_purpose):
        raise EnvelopeError("wrong kind or purpose")
    if (type(record["senderRole"]) is not str or
        record["senderRole"] != expected_role or
        type(record["actorRole"]) is not str or
        record["actorRole"] not in allowed_actor_roles or
        record["audience"] !=
            ("madar_sender" if kind == "receipt" else "taraz_peer")):
        raise EnvelopeError("role or audience mismatch")
    if (record["organizationId"] != _token(expected_organization_id, "expected org") or
        record["senderId"] != _token(expected_sender_id, "expected sender") or
        record["keyId"] != _token(expected_key_id, "expected key")):
        raise EnvelopeError("organization, sender or keyId mismatch")
    for field in ("organizationId", "senderId", "keyId"):
        _token(record[field], field)
    _request_id(record["requestId"])
    _check_times(record["issuedUtc"], record["expiresUtc"], now)
    content = record["payload"]
    if type(content) is not dict:
        raise EnvelopeError("invalid payload type")
    payload_bytes = canonical_json(content)
    if len(payload_bytes) > MAX_PAYLOAD_BYTES:
        raise EnvelopeError("oversized payload")
    digest = hashlib.sha256(payload_bytes).hexdigest()
    _sha(record["payloadSha256"], "payload SHA")
    if not hmac.compare_digest(digest, record["payloadSha256"]):
        raise EnvelopeError("payload digest mismatch")
    supplied_mac = record["mac"]
    if type(supplied_mac) is not str or not _SHA.fullmatch(supplied_mac):
        raise EnvelopeError("invalid MAC encoding")
    expected_mac = _mac({name: record[name] for name in _BODY_FIELDS}, secret)
    if not hmac.compare_digest(bytes.fromhex(supplied_mac),
                               bytes.fromhex(expected_mac)):
        raise EnvelopeError("signature mismatch")
    if kind == "query":
        _validate_subject(content)
    if kind == "receipt":
        _validate_result(content)
    return VerifiedEnvelope(
        kind=kind, organization_id=record["organizationId"],
        sender_id=record["senderId"], sender_role=record["senderRole"],
        actor_role=record["actorRole"], key_id=record["keyId"],
        request_id=record["requestId"], purpose=purpose,
        payload_sha256=digest, payload_bytes=payload_bytes,
        envelope_sha256=hashlib.sha256(wire).hexdigest(),
    )


def _roles(value):
    if type(value) is not frozenset or not value or not value <= _REQUEST_ROLES:
        raise EnvelopeError("explicit allowed actor roles required")
    return value


def verify_request(wire, *, secret, now, expected_organization_id,
                   expected_sender_id, expected_key_id, purpose,
                   allowed_actor_roles):
    """Independently verify HMAC, roles, tenant, key ID, time, purpose and bytes."""
    return _verify(
        wire, secret=secret, now=now,
        expected_organization_id=expected_organization_id,
        expected_sender_id=expected_sender_id,
        expected_key_id=expected_key_id,
        expected_role="madar_sender", expected_kind="request",
        expected_purpose=purpose, allowed_actor_roles=_roles(allowed_actor_roles))


def _original(value):
    if (type(value) is not VerifiedEnvelope or value.kind != "request" or
        value.purpose != "finance_review_request" or
        value.sender_role != "madar_sender"):
        raise EnvelopeError("verified original finance proposal required")
    _request_id(value.request_id)
    _sha(value.payload_sha256, "original SHA")


def sign_receipt_query(original, *, query_request_id, key_id, issued_at,
                       expires_at, secret):
    """Pure signed lookup for an earlier authorized request, no resend."""
    _original(original)
    if query_request_id == original.request_id:
        raise EnvelopeError("query ID cannot reuse original request ID")
    payload = {
        "originalRequestId": original.request_id,
        "originalPayloadSha256": original.payload_sha256,
        "originalPurpose": original.purpose,
    }
    return _build(
        payload, kind="query", purpose="receipt_lookup",
        organization_id=original.organization_id, sender_id=original.sender_id,
        sender_role="madar_sender", actor_role=original.actor_role,
        audience="taraz_peer", key_id=key_id, request_id=query_request_id,
        issued_at=issued_at, expires_at=expires_at, secret=secret)


def verify_receipt_query(wire, *, secret, now, expected_organization_id,
                         expected_sender_id, expected_key_id, allowed_actor_roles):
    return _verify(
        wire, secret=secret, now=now,
        expected_organization_id=expected_organization_id,
        expected_sender_id=expected_sender_id,
        expected_key_id=expected_key_id, expected_role="madar_sender",
        expected_kind="query", expected_purpose="receipt_lookup",
        allowed_actor_roles=_roles(allowed_actor_roles))


def sign_peer_receipt(query, *, lookup_status, sender_id, key_id, issued_at,
                      expires_at, secret):
    """Sign a peer lookup claim. Never assert financial approval or posting."""
    if (type(query) is not VerifiedEnvelope or query.kind != "query" or
        query.purpose != "receipt_lookup" or query.sender_role != "madar_sender"):
        raise EnvelopeError("verified lookup query required")
    _validate_subject(query.payload)
    if type(lookup_status) is not str or lookup_status not in _STATUSES:
        raise EnvelopeError("invalid peer lookup status")
    payload = {
        **query.payload, "queryRequestId": query.request_id,
        "queryPayloadSha256": query.payload_sha256,
        "lookupStatus": lookup_status,
    }
    return _build(
        payload, kind="receipt", purpose="receipt_lookup_result",
        organization_id=query.organization_id, sender_id=sender_id,
        sender_role="taraz_peer", actor_role="peer", audience="madar_sender",
        key_id=key_id, request_id=query.request_id, issued_at=issued_at,
        expires_at=expires_at, secret=secret)


def _linked(original, query):
    _original(original)
    if (type(query) is not VerifiedEnvelope or
        query.kind != "query" or query.purpose != "receipt_lookup" or
        query.organization_id != original.organization_id or
        query.sender_id != original.sender_id or
        query.actor_role != original.actor_role or
        query.request_id == original.request_id or
        query.payload != {
            "originalRequestId": original.request_id,
            "originalPayloadSha256": original.payload_sha256,
            "originalPurpose": original.purpose,
        }):
        raise EnvelopeError("query and original are not bound together")


def verify_peer_receipt(wire, *, original, query, secret, now,
                        expected_peer_id, expected_peer_key_id):
    """Verify response with separate Taraz-direction key and exact query ID."""
    _linked(original, query)
    receipt = _verify(
        wire, secret=secret, now=now,
        expected_organization_id=original.organization_id,
        expected_sender_id=expected_peer_id, expected_key_id=expected_peer_key_id,
        expected_role="taraz_peer", expected_kind="receipt",
        expected_purpose="receipt_lookup_result",
        allowed_actor_roles=frozenset({"peer"}))
    if (receipt.request_id != query.request_id or receipt.payload != {
        **query.payload, "queryRequestId": query.request_id,
        "queryPayloadSha256": query.payload_sha256,
        "lookupStatus": receipt.payload.get("lookupStatus"),
    }):
        raise EnvelopeError("unrelated peer lookup response")
    return receipt


def check_replay_binding(verified, *, previous: Mapping):
    """Pure caller-supplied replay index check. Does not persist/lock the map.

    Index key: (organization, kind, requestId).
    Value: (senderId, senderRole, actorRole, purpose, keyId, payloadSHA256).
    Same-ID changes to sender, purpose, role, key or content are conflicts.
    Concurrency/atomicity must be enforced by the real host store.
    """
    if type(verified) is not VerifiedEnvelope or not isinstance(previous, Mapping):
        raise EnvelopeError("verified envelope and replay registry required")
    binding = (verified.organization_id, verified.kind, verified.request_id)
    if binding not in previous:
        return "new"
    old = previous[binding]
    if type(old) is not tuple or len(old) != 6:
        raise EnvelopeError("invalid saved replay binding")
    expected = (
        verified.sender_id, verified.sender_role, verified.actor_role,
        verified.purpose, verified.key_id, verified.payload_sha256,
    )
    old_digest = _sha(old[-1], "saved replay digest")
    if old[:-1] != expected[:-1] or not hmac.compare_digest(
        old_digest, expected[-1]
    ):
        raise EnvelopeError("conflicting replay with the same request ID")
    return "identical"


def query_first_recovery_decision(*, original, query, receipt,
                                  prior_manual_authorized, prior_request_id,
                                  prior_payload_sha256):
    """Pure query-first gate, never performs a query, retry or finance action.

    Only call with independently verified request/query/peer receipt values.
    Approval, original ID/hash and any durable replay map must come from a
    trusted host; an HMAC lookup claim is not official nonreceipt proof.
    """
    _linked(original, query)
    if (prior_manual_authorized is not True or
        prior_request_id != original.request_id or
        prior_payload_sha256 != original.payload_sha256):
        return "hold_manual_authorization_mismatch"
    if receipt is None:
        return "hold_query_required"
    if (type(receipt) is not VerifiedEnvelope or
        receipt.kind != "receipt" or receipt.sender_role != "taraz_peer" or
        receipt.purpose != "receipt_lookup_result" or
        receipt.organization_id != original.organization_id or
        receipt.request_id != query.request_id or
        receipt.payload.get("originalRequestId") != original.request_id or
        receipt.payload.get("originalPayloadSha256") != original.payload_sha256 or
        receipt.payload.get("queryPayloadSha256") != query.payload_sha256):
        raise EnvelopeError("unmatched peer lookup response")
    status = receipt.payload.get("lookupStatus")
    if status == "received":
        return "observe_peer_claim_received"
    if status == "not_received":
        # The peer HMAC proves a response from the configured *metadata test*
        # peer, not an official Taraz ledger nonreceipt attestation. It must
        # never turn a consumed dispatch gate into resend eligibility.
        return "hold_unverified_nonreceipt"
    if status == "unknown":
        return "hold_uncertain"
    raise EnvelopeError("unrecognized peer lookup status")
