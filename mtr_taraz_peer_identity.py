"""Pure fail-closed peer authentication for NON-FINANCIAL Taraz reviews.

No real identity is established by an installed EXE, local JSON, or HMAC alone.
The verifier MUST obtain its expected peer/org/key ID and secret from an
independently authenticated trusted channel, and atomically consume a
verifier-issued one-time challenge. Without these proofs peerVerified is NEVER
true. This module does no I/O, networking, ledger posting or key persistence.

make_peer_review_attestation is a low-level signing primitive, not an authority
check. Only an authenticated, role-authorized Taraz issuer should call it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import re

_DOMAIN = b"MTR-Taraz-peer-review-v1\x00"
_ID = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_UTC = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z", re.ASCII)
_FIELDS = frozenset({
    "protocol", "version", "algorithm", "purpose", "audience",
    "peerId", "keyId", "organizationId", "requestId", "taskId", "projectId",
    "challenge", "issuedUtc", "expiresUtc", "sourceDigest", "reviewDigest",
    "reviewState", "reviewedUtc", "financialEventCreated",
})
_PROPOSAL_REQUIRED = frozenset({
    "schema", "source", "id", "taskId", "projectId", "title", "createdUtc",
})
_REVIEW_FIELDS = frozenset({
    "schema", "source", "id", "taskId", "state", "reviewedUtc",
    "financialEventCreated",
})
_STATES = frozenset({"reviewed", "rejected"})
MAX_RECORD_BYTES = 32768
MAX_PROOF_BYTES = 4096
MAX_AGE_SECONDS = 300
FUTURE_SKEW_SECONDS = 30


class PeerIdentityError(ValueError):
    """An identity assertion could not be independently verified."""


def _token(value, name):
    if type(value) is not str or not _TOKEN.fullmatch(value):
        raise PeerIdentityError("invalid " + name)
    return value


def _id(value, name):
    if type(value) is not str or not _ID.fullmatch(value):
        raise PeerIdentityError("invalid " + name)
    return value


def _sha(value, name):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise PeerIdentityError("invalid " + name)
    return value


def _key(secret):
    if type(secret) is not bytes or not 32 <= len(secret) <= 4096:
        raise PeerIdentityError("independently provisioned secret must be 32+ bytes")
    return secret


def _unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise PeerIdentityError("duplicate JSON key")
        result[k] = v
    return result


def _reject_constant(_):
    raise PeerIdentityError("nonfinite JSON value")


def _canonical(record):
    if type(record) is not dict:
        raise PeerIdentityError("JSON object required")
    try:
        return json.dumps(record, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf8")
    except (UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise PeerIdentityError("invalid JSON value") from exc


def _decode(raw, limit, *, canonical=False):
    if type(raw) is not bytes or not 1 <= len(raw) <= limit:
        raise PeerIdentityError("missing, oversized or non-byte record")
    try:
        record = json.loads(raw.decode("utf8"), object_pairs_hook=_unique,
                            parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PeerIdentityError("malformed JSON record") from exc
    if type(record) is not dict:
        raise PeerIdentityError("JSON object required")
    if canonical and _canonical(record) != raw:
        raise PeerIdentityError("noncanonical signed proof")
    return record


def _utc(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise PeerIdentityError("aware UTC timestamp required")
    converted = value.astimezone(timezone.utc)
    if converted.microsecond:
        raise PeerIdentityError("second-precision UTC required")
    return converted.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value):
    if type(value) is not str or not _UTC.fullmatch(value):
        raise PeerIdentityError("noncanonical UTC timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError as exc:
        raise PeerIdentityError("invalid UTC timestamp") from exc


def _local_utc(value):
    if type(value) is not str or not 1 <= len(value) <= 50:
        raise PeerIdentityError("invalid persisted UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PeerIdentityError("malformed persisted UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise PeerIdentityError("persisted UTC must contain explicit zero offset")
    return parsed.astimezone(timezone.utc)


def _time_gate(issued, expires, now):
    start, end = _parse_utc(issued), _parse_utc(expires)
    current = _parse_utc(_utc(now))
    life = (end - start).total_seconds()
    if not 0 < life <= MAX_AGE_SECONDS:
        raise PeerIdentityError("unbounded proof lifetime")
    if (start - current).total_seconds() > FUTURE_SKEW_SECONDS:
        raise PeerIdentityError("future peer proof")
    if current >= end:
        raise PeerIdentityError("stale peer proof")


def _record_pair(source_raw, review_raw):
    source = _decode(source_raw, MAX_RECORD_BYTES)
    review = _decode(review_raw, MAX_RECORD_BYTES)
    if (not _PROPOSAL_REQUIRED <= source.keys() or
            not source.keys() <= _PROPOSAL_REQUIRED | {"expenseId", "amountRial"} or
            type(source.get("schema")) is not int or source["schema"] != 1 or
            source.get("source") != "madar" or
            type(source.get("title")) is not str or
            not 1 <= len(source["title"].strip()) <= 300 or
            set(review) != _REVIEW_FIELDS or
            type(review.get("schema")) is not int or review["schema"] != 1 or
            review.get("source") != "taraz" or
            type(review.get("state")) is not str or
            review["state"] not in _STATES or
            review.get("financialEventCreated") is not False):
        raise PeerIdentityError("source or review is not schema-1 metadata")
    _id(source["id"], "source id")
    _id(review["id"], "review id")
    for name in ("taskId", "projectId"):
        if (type(source.get(name)) is not str or
                not 1 <= len(source[name]) <= 180 or not source[name].strip()):
            raise PeerIdentityError("invalid source " + name)
    if (type(review.get("taskId")) is not str or
            review["id"] != source["id"] or
            review["taskId"] != source["taskId"]):
        raise PeerIdentityError("source/review identity mismatch")
    if "expenseId" in source and (type(source["expenseId"]) is not str or
                                   not source["expenseId"]):
        raise PeerIdentityError("invalid optional expense")
    if "amountRial" in source and (type(source["amountRial"]) is not str or
                                    not re.fullmatch(r"[1-9][0-9]{0,15}", source["amountRial"])):
        raise PeerIdentityError("invalid optional amount")
    created = _local_utc(source["createdUtc"])
    reviewed = _local_utc(review["reviewedUtc"])
    if reviewed < created:
        raise PeerIdentityError("Taraz review predates its source proposal")
    return source, review


def _mac(body, secret):
    return hmac.new(_key(secret), _DOMAIN + _canonical(body), hashlib.sha256).hexdigest()


def make_peer_review_attestation(*, source_raw, review_raw, organization_id,
                                 peer_id, key_id, challenge, issued_at,
                                 expires_at, secret):
    """Pure signer; requires separate actual Taraz issuer authentication."""
    source, review = _record_pair(source_raw, review_raw)
    body = {
        "protocol": "mtr-taraz-review-proof", "version": 1,
        "algorithm": "HMAC-SHA256", "purpose": "metadata-review",
        "audience": "madar", "peerId": _token(peer_id, "peer"),
        "keyId": _token(key_id, "key slot"),
        "organizationId": _token(organization_id, "organization"),
        "requestId": source["id"], "taskId": source["taskId"],
        "projectId": source["projectId"],
        "challenge": _id(challenge, "challenge"),
        "issuedUtc": _utc(issued_at), "expiresUtc": _utc(expires_at),
        "sourceDigest": hashlib.sha256(source_raw).hexdigest(),
        "reviewDigest": hashlib.sha256(review_raw).hexdigest(),
        "reviewState": review["state"], "reviewedUtc": review["reviewedUtc"],
        "financialEventCreated": False,
    }
    _time_gate(body["issuedUtc"], body["expiresUtc"], issued_at)
    if _local_utc(review["reviewedUtc"]) > issued_at.astimezone(timezone.utc):
        raise PeerIdentityError("Taraz review is newer than its signed proof")
    wire = _canonical({**body, "mac": _mac(body, secret)})
    if len(wire) > MAX_PROOF_BYTES:
        raise PeerIdentityError("oversized proof")
    return wire


def verify_peer_review_attestation(*, wire, source_raw, review_raw, secret, now,
                                   expected_organization_id, expected_peer_id,
                                   expected_key_id, expected_request_id,
                                   expected_task_id, expected_project_id,
                                   expected_challenge, consume_challenge):
    """Verify independently pinned HMAC+scope+source bytes+fresh one-time nonce.

    The challenge consumer must be trusted and atomically reject replays. Its
    return value must be literal True. Exceptions mean NOT verified. This API
    verifies only who reviewed metadata, NEVER any finance posting.
    """
    _key(secret)
    for field, value in (("organization", expected_organization_id),
                         ("peer", expected_peer_id), ("key slot", expected_key_id)):
        _token(value, "trusted " + field)
    _id(expected_request_id, "expected request")
    _id(expected_challenge, "expected challenge")
    for field, value in (("task", expected_task_id), ("project", expected_project_id)):
        if type(value) is not str or not 1 <= len(value) <= 180 or not value.strip():
            raise PeerIdentityError("invalid trusted " + field)
    if not callable(consume_challenge):
        raise PeerIdentityError("trusted one-time challenge consumer required")
    source, review = _record_pair(source_raw, review_raw)
    if (source["id"] != expected_request_id or
            source["taskId"] != expected_task_id or
            source["projectId"] != expected_project_id):
        raise PeerIdentityError("unexpected source/card scope")
    attestation = _decode(wire, MAX_PROOF_BYTES, canonical=True)
    if set(attestation) != _FIELDS | {"mac"}:
        raise PeerIdentityError("missing or extra proof field")
    if (type(attestation["version"]) is not int or attestation["version"] != 1 or
            attestation["financialEventCreated"] is not False):
        raise PeerIdentityError("wrong protocol or financial claim")
    expected_fields = {
        "protocol": "mtr-taraz-review-proof", "algorithm": "HMAC-SHA256",
        "purpose": "metadata-review", "audience": "madar",
        "organizationId": expected_organization_id, "peerId": expected_peer_id,
        "keyId": expected_key_id, "requestId": expected_request_id,
        "taskId": expected_task_id, "projectId": expected_project_id,
        "challenge": expected_challenge, "reviewState": review["state"],
        "reviewedUtc": review["reviewedUtc"],
    }
    if any(type(attestation[k]) is not str or attestation[k] != v
           for k, v in expected_fields.items()):
        raise PeerIdentityError("peer identity, challenge, or review mismatch")
    for name, raw in (("sourceDigest", source_raw), ("reviewDigest", review_raw)):
        digest = _sha(attestation[name], name)
        if not hmac.compare_digest(digest, hashlib.sha256(raw).hexdigest()):
            raise PeerIdentityError(name + " differs from persisted bytes")
    _time_gate(attestation["issuedUtc"], attestation["expiresUtc"], now)
    if _local_utc(review["reviewedUtc"]) > _parse_utc(attestation["issuedUtc"]):
        raise PeerIdentityError("review occurred after claimed issuance")
    mac = _sha(attestation["mac"], "MAC")
    body = {field: attestation[field] for field in _FIELDS}
    if not hmac.compare_digest(bytes.fromhex(mac), bytes.fromhex(_mac(body, secret))):
        raise PeerIdentityError("peer HMAC verification failed")
    # Consume only after all cryptographic checks. The verifier owns this
    # operation; no self-asserted nonce cache or key from the wire is trusted.
    try:
        consumed = consume_challenge(expected_peer_id, expected_request_id,
                                     expected_challenge)
    except Exception as exc:
        raise PeerIdentityError("trusted challenge consumption failed") from exc
    if consumed is not True:
        raise PeerIdentityError("replayed, expired or unissued challenge")
    return {
        "peerVerified": True,
        "requestId": expected_request_id,
        "taskId": expected_task_id,
        "projectId": expected_project_id,
        "reviewState": review["state"],
        "sourceDigest": attestation["sourceDigest"],
        "reviewDigest": attestation["reviewDigest"],
        "financialEventCreated": False,
        "officialFinancialReceiptVerified": False,
        "postingEnabled": False,
        "ledgerPostingPerformed": False,
    }


__all__ = [
    "PeerIdentityError", "make_peer_review_attestation",
    "verify_peer_review_attestation",
]
