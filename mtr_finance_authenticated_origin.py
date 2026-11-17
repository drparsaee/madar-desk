"""Host-only manual Madar finance proposal and one-use v2 lookup signer.

This NEW source is intentionally not wired into LanService, any HTTP route,
dispatch, accounting ledger, or the Taraz application. A trusted composition
root must own this single object and its server-provisioned peer key. No
public caller may set actor/role/organization/company or claim identity.

This is Madar identity *attestation to a signed metadata proposal*, NOT an
official finance receipt and NOT Taraz accounting authorization. In the
currently inspected Taraz authority, actorId must equal a Taraz username
(maximum 40 characters); Madar's correct account-lineage actorId is 77
characters. Production cross-app verification remains blocked until a
real, separately authenticated actor mapping exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
import threading
import time

from lan import LanService
from mtr_account_lineage import principal_actor_id
from mtr_peer_envelope import (
    canonical_json, sign_request, sign_receipt_query, verify_request,
)
from taraz_exchange import _build_proposal


_HEX32 = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_ID = re.compile(r"[A-Za-z0-9._-]{1,100}\Z", re.ASCII)
_PEER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_FIELDS = frozenset({"schema", "source", "id", "taskId", "projectId",
                     "title", "createdUtc", "expenseId", "amountRial"})
_DOMAIN = b"madar.mtr.finance.authenticated-origin.v1\x00"
_SEAL_LIFETIME_NS = 30_000_000_000
_USED_LIMIT = 4096
_ACTIVE_LIMIT = 256


class FinanceOriginDenied(PermissionError):
    """No authenticated, in-scope one-time finance proposal was signed."""


def _deny(message: str):
    raise FinanceOriginDenied(message)


@dataclass(frozen=True, slots=True, repr=False)
class SealedFinanceOrigin:
    """Private process-local preflight capability, not wire data or a token."""
    claims_bytes: bytes
    issued_ns: int
    nonce: bytes
    mac: bytes

    def __repr__(self):
        return "<SealedFinanceOrigin redacted>"

    def __reduce__(self):
        raise TypeError("private finance preflight seals cannot be serialized")


def _proposal_bytes(raw: bytes):
    if type(raw) is not bytes or not 1 <= len(raw) <= 32768:
        _deny("exact bounded source bytes required")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _deny("duplicate source field")
            result[key] = value
        return result

    try:
        obj = json.loads(raw.decode("utf8"), object_pairs_hook=unique,
                         parse_constant=lambda _: _deny("non-finite source"))
        # taraz_exchange._publish_proposal persists json.dump(...,
        # ensure_ascii=False, separators=(',', ':')) in insertion order.
        # Canonical sorted-key JSON is used by *signed peer envelopes*, not
        # the source proposal. Requiring canonical_json(obj) == raw rejects
        # real Madar on-disk proposals. Bind the exact original bytes instead.
        exported = json.dumps(obj, ensure_ascii=False,
                              separators=(",", ":"), allow_nan=False).encode("utf8")
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise FinanceOriginDenied("invalid source proposal JSON") from exc
    if type(obj) is not dict or set(obj) != _FIELDS or exported != raw:
        _deny("exact compact UTF-8 Madar source proposal required")
    if (type(obj["schema"]) is not int or obj["schema"] != 1
            or obj["source"] != "madar"
            or type(obj["id"]) is not str or not _HEX32.fullmatch(obj["id"])
            or type(obj["expenseId"]) is not str
            or type(obj["amountRial"]) is not str or not obj["amountRial"].isascii()
            or not obj["amountRial"].isdecimal()
            or len(obj["amountRial"]) > 16
            or not 0 < int(obj["amountRial"]) <= 9007199254740991):
        _deny("source has no valid authenticated positive RIAL expense")
    try:
        instant = datetime.fromisoformat(obj["createdUtc"].replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError) as exc:
        raise FinanceOriginDenied("source time is malformed") from exc
    if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
        _deny("source must have an explicit UTC timestamp")
    return obj, instant.astimezone(timezone.utc)


class HostAuthenticatedFinanceOrigin:
    """Owner-controlled one-instance-only signer. No side effects at creation."""

    __slots__ = ("_service", "_org", "_sender", "_key_id", "_secret",
                 "_company", "_seal_secret", "_lock", "_used_seals",
                 "_issued", "_consumed_queries")

    def __init__(self, service: LanService, *, organization_id: str,
                 sender_id: str, key_id: str, signing_key: bytes,
                 company_id: str):
        if type(service) is not LanService:
            _deny("real current LanService required; fabricated host forbidden")
        if (type(organization_id) is not str or not _PEER.fullmatch(organization_id)
                or type(sender_id) is not str or not _PEER.fullmatch(sender_id)
                or type(key_id) is not str or not _PEER.fullmatch(key_id)
                or type(company_id) is not str or not _HEX32.fullmatch(company_id)
                or type(signing_key) is not bytes or not 32 <= len(signing_key) <= 4096):
            _deny("trusted operator-provisioned peer/company configuration required")
        self._service = service
        self._org, self._sender, self._key_id = organization_id, sender_id, key_id
        self._company = company_id
        self._secret = signing_key
        self._seal_secret = secrets.token_bytes(32)
        if (type(self._seal_secret) is not bytes or len(self._seal_secret) != 32
                or not any(self._seal_secret)):
            _deny("host seal RNG unavailable")
        self._lock = threading.RLock()
        self._used_seals: set[bytes] = set()
        self._issued: dict[str, tuple[str, bytes]] = {}
        self._consumed_queries: set[str] = set()

    def __repr__(self):
        return "<HostAuthenticatedFinanceOrigin host-only redacted>"

    def __reduce__(self):
        raise TypeError("host-only finance signer cannot be serialized")

    def _private_snapshot(self, token: str, raw: bytes,
                          invoice_id: str, issue_event_id: str):
        """Caller holds both service.lock and bridge._lock throughout."""
        if type(token) is not str or not 1 <= len(token) <= 512:
            _deny("live authenticated host session required")
        account = self._service.account_for(token)
        if type(account) is not dict:
            _deny("private registry account required")
        name = account.get("username")
        if (type(name) is not str or self._service.users.get(name) is not account
                or account.get("active", True) is not True):
            _deny("account was not returned from private host registry")
        role = account.get("role")
        if role not in ("admin", "editor"):
            _deny("current finance editor/admin role required")
        if role == "editor" and account.get("financeEdit") is not True:
            _deny("current editor lacks finance edit grant")
        if (type(invoice_id) is not str or not _ID.fullmatch(invoice_id)
                or type(issue_event_id) is not str or not _ID.fullmatch(issue_event_id)):
            _deny("operator-selected bounded Taraz journal IDs required")
        actor_id = principal_actor_id(account)
        lineage = account["accountLineage"]
        if any(other_name != name and type(other) is dict
               and other.get("accountLineage") == lineage
               for other_name, other in self._service.users.items()):
            _deny("duplicate immutable account lineage")
        state = self._service.bridge.getState()
        if (type(state) is not dict or type(state.get("tasks")) is not list
                or type(state.get("projects")) is not list
                or len(state["tasks"]) > 100000 or len(state["projects"]) > 1000):
            _deny("current saved card/project registry missing")
        projects = state["projects"]
        if (any(type(p) is not dict or type(p.get("id")) is not str
                or not 1 <= len(p["id"]) <= 180 for p in projects)
                or len({p["id"] for p in projects}) != len(projects)):
            _deny("invalid current project IDs")
        grants = account.get("projects")
        if grants is not None and (
                type(grants) is not list or len(grants) > 1000
                or any(type(p) is not str or not 1 <= len(p) <= 180
                       or p != p.strip() for p in grants)
                or len(set(grants)) != len(grants)):
            _deny("invalid private project grants")
        proposal, source_created = _proposal_bytes(raw)
        matching = [task for task in state["tasks"] if type(task) is dict
                    and task.get("id") == proposal["taskId"]]
        if len(matching) != 1 or matching[0].get("deleted") is True:
            _deny("selected saved task is missing, deleted, or ambiguous")
        task = matching[0]
        if (proposal["projectId"] != task.get("projectId")
                or proposal["projectId"] not in {p["id"] for p in projects}
                or (grants is not None and proposal["projectId"] not in grants)):
            _deny("task project is not in current private grants")
        # This helper only reads the saved host task and its selected expense.
        # Its creation time is intentionally ignored and compared separately.
        calculated = _build_proposal(
            state, proposal["taskId"], proposal["expenseId"], proposal["id"])
        if ({k: v for k, v in calculated.items() if k != "createdUtc"}
                != {k: v for k, v in proposal.items() if k != "createdUtc"}):
            _deny("source expense/title/project differs from saved host task")
        if not 0 < int(proposal["amountRial"]) <= 9007199254740991:
            _deny("no bounded positive RIAL amount")
        now = datetime.now(timezone.utc)
        if abs((now - source_created).total_seconds()) > 300:
            _deny("original finance proposal must be freshly host-attested")
        state_fingerprint = hashlib.sha256(canonical_json(task)).hexdigest()
        visible = sorted(p["id"] for p in projects
                         if grants is None or p["id"] in grants)
        return {
            "id": proposal["id"], "taskId": proposal["taskId"],
            "projectId": proposal["projectId"],
            "sourceDigest": hashlib.sha256(raw).hexdigest(),
            "companyId": self._company,
            "actorId": actor_id,
            "invoiceId": invoice_id,
            "issueEventId": issue_event_id,
            "journalId": "J:" + issue_event_id,
            "actorRole": role, "sessionDigest": hashlib.sha256(token.encode("utf8")).hexdigest(),
            "savedTaskDigest": state_fingerprint,
            "visibleProjects": visible,
        }

    @staticmethod
    def _peer_payload(snapshot):
        return {name: snapshot[name] for name in (
            "id", "taskId", "projectId", "sourceDigest", "companyId",
            "actorId", "invoiceId", "issueEventId", "journalId")}

    def _mac(self, claims: bytes, nonce: bytes, issued_ns: int):
        return hmac.new(self._seal_secret, _DOMAIN + issued_ns.to_bytes(8, "big")
                        + nonce + claims, hashlib.sha256).digest()

    def prepare_manual(self, token: str, source_raw: bytes, *,
                       invoice_id: str, issue_event_id: str,
                       explicit_manual_action: bool) -> SealedFinanceOrigin:
        """Issue a short-lived private proof bound to current saved finance data."""
        if explicit_manual_action is not True:
            _deny("explicit manual operator action required")
        with self._service.lock, self._service.bridge._lock, self._lock:
            claims = self._private_snapshot(token, source_raw, invoice_id, issue_event_id)
            if claims["id"] in self._issued:
                _deny("one Madar original request may be signed only once per host signer")
            candidate = canonical_json(claims)
            now = time.monotonic_ns()
            nonce = secrets.token_bytes(16)
            if type(nonce) is not bytes or len(nonce) != 16 or not any(nonce):
                _deny("source seal RNG failed")
            return SealedFinanceOrigin(candidate, now, nonce,
                                       self._mac(candidate, nonce, now))

    def sign_original_manual(self, token: str, seal: SealedFinanceOrigin,
                             source_raw: bytes, *,
                             explicit_manual_action: bool) -> bytes:
        """Consume the private proof once; return only the v2 original wire."""
        if explicit_manual_action is not True:
            _deny("manual signing confirmation required")
        with self._service.lock, self._service.bridge._lock, self._lock:
            if (type(seal) is not SealedFinanceOrigin
                    or type(seal.claims_bytes) is not bytes
                    or len(seal.claims_bytes) > 16384
                    or type(seal.issued_ns) is not int
                    or not 0 <= seal.issued_ns < (1 << 64)
                    or type(seal.nonce) is not bytes or len(seal.nonce) != 16
                    or type(seal.mac) is not bytes or len(seal.mac) != 32):
                _deny("host-issued private finance seal required")
            if not hmac.compare_digest(
                    seal.mac, self._mac(seal.claims_bytes, seal.nonce, seal.issued_ns)):
                _deny("forged finance provenance seal")
            age = time.monotonic_ns() - seal.issued_ns
            if not 0 <= age <= _SEAL_LIFETIME_NS:
                _deny("expired/future finance authorization")
            if seal.nonce in self._used_seals:
                _deny("single-use finance proof was consumed")
            try:
                claims = json.loads(seal.claims_bytes)
                current = self._private_snapshot(
                    token, source_raw, claims["invoiceId"], claims["issueEventId"])
            except (ValueError, TypeError, KeyError, UnicodeError) as exc:
                raise FinanceOriginDenied("malformed or stale private finance proof") from exc
            if canonical_json(current) != seal.claims_bytes:
                _deny("role/session/lineage/grants/task/source changed before signing")
            if claims["id"] in self._issued:
                _deny("Madar original request already signed")
            if len(self._issued) >= _ACTIVE_LIMIT or len(self._used_seals) >= _USED_LIMIT:
                _deny("host signer memory replay capacity exhausted")
            issued = datetime.now(timezone.utc).replace(microsecond=0)
            raw = sign_request(
                self._peer_payload(claims), organization_id=self._org,
                sender_id=self._sender, actor_role=claims["actorRole"],
                key_id=self._key_id, request_id=claims["id"],
                purpose="finance_review_request", issued_at=issued,
                expires_at=issued + timedelta(seconds=120),
                secret=self._secret, authorized=True,
                explicit_manual_action=True)
            self._used_seals.add(seal.nonce)
            self._issued[claims["id"]] = (hashlib.sha256(raw).hexdigest(),
                                          seal.claims_bytes)
            return raw

    def sign_query_manual(self, token: str, original_wire: bytes,
                          source_raw: bytes, *, query_request_id: str,
                          explicit_manual_action: bool) -> bytes:
        """One signed query/challenge per signed original in this live signer."""
        if explicit_manual_action is not True:
            _deny("explicit one-time manual query confirmation required")
        if type(query_request_id) is not str or not _HEX32.fullmatch(query_request_id):
            _deny("fresh 128-bit challenge ID required")
        with self._service.lock, self._service.bridge._lock, self._lock:
            # The local issuer itself must have signed the exact original;
            # verification of arbitrary HMAC content alone is insufficient.
            stamp = datetime.now(timezone.utc).replace(microsecond=0)
            verified = verify_request(
                original_wire, secret=self._secret, now=stamp,
                expected_organization_id=self._org,
                expected_sender_id=self._sender, expected_key_id=self._key_id,
                purpose="finance_review_request",
                allowed_actor_roles=frozenset({"admin", "editor"}))
            previously = self._issued.get(verified.request_id)
            if (previously is None
                    or not hmac.compare_digest(
                        previously[0], hashlib.sha256(original_wire).hexdigest())):
                _deny("original not issued by this authenticated host instance")
            claims = json.loads(previously[1])
            if (canonical_json(self._private_snapshot(
                    token, source_raw, claims["invoiceId"], claims["issueEventId"]))
                    != previously[1]):
                _deny("current host actor/session/task/grants no longer match original")
            if (verified.actor_role != claims["actorRole"]
                    or verified.payload != self._peer_payload(claims)):
                _deny("original role/company/source/actor was modified")
            if (verified.request_id in self._consumed_queries
                    or query_request_id in self._consumed_queries
                    or query_request_id == verified.request_id):
                _deny("query challenge already consumed or subject duplicated")
            if len(self._consumed_queries) >= _ACTIVE_LIMIT:
                _deny("host query replay capacity exhausted")
            query = sign_receipt_query(
                verified, query_request_id=query_request_id,
                key_id=self._key_id, issued_at=stamp,
                expires_at=stamp + timedelta(seconds=90),
                secret=self._secret)
            self._consumed_queries.add(verified.request_id)
            self._consumed_queries.add(query_request_id)
            return query


__all__ = [
    "HostAuthenticatedFinanceOrigin", "FinanceOriginDenied", "SealedFinanceOrigin",
]
