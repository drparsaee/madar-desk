"""Host-only, short-lived provenance seals for E2 *read-only* recovery.

The real LanService owns an instance of this issuer and MUST be the only
authority accepted by future store/gate entry points. A plain constructed
TrustedPrincipal is NOT proof. No routes, private-registry writes, transport,
finance posting, persistence, or long-lived bearer tokens are provided here.

The proof and the per-instance secret are process-local. A restart requires
fresh login and reissuance, never replay of an older capability. Python code
already executing with unrestricted host-process privileges can inspect
private memory; this module cannot sandbox arbitrary malicious Python code.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import secrets
import threading
import time

from mtr_account_lineage import principal_actor_id
from mtr_host_request_store import TrustedPrincipal


OUTBOX_RECOVERY = "mtr.e2.recovery.outbox"
GATE_RECOVERY = "mtr.e2.recovery.gate"
_AUDIENCES = frozenset((OUTBOX_RECOVERY, GATE_RECOVERY))
_SECRET_BYTES = 32
_NONCE_BYTES = 16
_TTL_NS = 30_000_000_000
_MAX_USED = 4096
_NAME = re.compile(r"[A-Za-z0-9._-]{3,40}\Z", re.ASCII)


class PrincipalProvenanceDenied(PermissionError):
    """No verifiable, current and unused host-recovery authority."""


@dataclass(frozen=True, slots=True, repr=False)
class SealedRecoveryPrincipal:
    """Process-only opaque capability, NOT a TrustedPrincipal or wire value.

    Its fields can be forged/modified in Python; verification checks a full
    HMAC and current authenticated host state. `repr` deliberately redacts.
    """

    principal: TrustedPrincipal
    audience: str
    issued_monotonic_ns: int
    nonce: bytes
    mac: bytes

    def __repr__(self):
        return "<SealedRecoveryPrincipal redacted>"

    def __reduce__(self):
        raise TypeError("host-only recovery capabilities are not serializable")


class HostPrincipalProvenance:
    """Single trusted LanService-bound issuer/verifier, never user-created.

    `service.account_for(token)` MUST return the exact dict held in the
    service's private `users` registry, under `service.lock`; the actor is
    derived only from that dict's existing immutable `accountLineage`.

    A verifier consumes one nonce for a specific read-only audience, even if
    the caller later fails a store operation. Store/gate must require this
    *bound* authority's verification at their host-only entry point; adding
    this helper does not modify or secure their older plain-principal APIs.
    """

    __slots__ = ("_service", "_org_id", "__secret", "_guard", "_used")

    def __init__(self, service, *, org_id: str):
        if (type(org_id) is not str or not 1 <= len(org_id) <= 120
                or any(ord(ch) < 33 or ord(ch) > 126 for ch in org_id)):
            raise PrincipalProvenanceDenied("invalid host-owned organization")
        if (not callable(getattr(service, "account_for", None))
                or type(getattr(service, "users", None)) is not dict
                or not hasattr(service, "lock")
                or not hasattr(getattr(service, "bridge", None), "_lock")
                or not callable(getattr(service.bridge, "getState", None))):
            raise PrincipalProvenanceDenied("trusted private host contract required")
        secret = secrets.token_bytes(_SECRET_BYTES)
        if type(secret) is not bytes or len(secret) != _SECRET_BYTES or not any(secret):
            raise PrincipalProvenanceDenied("host CSPRNG secret generation failed")
        self._service = service
        self._org_id = org_id
        self.__secret = secret
        self._guard = threading.RLock()
        self._used: dict[bytes, int] = {}

    def __repr__(self):
        return "<HostPrincipalProvenance host-only redacted>"

    def __reduce__(self):
        raise TypeError("host-only provenance authority cannot be serialized")

    @staticmethod
    def _validate_token(token):
        if (type(token) is not str or not 1 <= len(token) <= 512
                or token != token.strip()
                or any(ord(ch) < 33 or ord(ch) > 126 for ch in token)):
            raise PrincipalProvenanceDenied("valid current host token required")

    @staticmethod
    def _audience(value):
        if type(value) is not str or value not in _AUDIENCES:
            raise PrincipalProvenanceDenied("unsupported read-only audience")

    def _current_principal(self, token: str) -> TrustedPrincipal:
        """Must be called with host lock + bridge lock already held."""
        self._validate_token(token)
        account = self._service.account_for(token)
        if type(account) is not dict:
            raise PrincipalProvenanceDenied("host private account missing")
        username = account.get("username")
        if (type(username) is not str or _NAME.fullmatch(username) is None
                or account is not self._service.users.get(username)):
            raise PrincipalProvenanceDenied("account did not originate in private registry")

        role = account.get("role")
        if role not in ("admin", "editor"):
            raise PrincipalProvenanceDenied("current recovery role denied")
        if role == "editor" and account.get("financeEdit") is not True:
            raise PrincipalProvenanceDenied("current recovery finance grant denied")
        if account.get("active", True) is not True:
            raise PrincipalProvenanceDenied("inactive account")

        actor = principal_actor_id(account)  # Missing/legacy fails closed.
        lineage = account["accountLineage"]
        # Duplicate private account lineage is an ambiguous identity, never
        # an occasion to fall back to username or silently re-issue a key.
        for other_name, other in self._service.users.items():
            if (other_name != username and type(other) is dict
                    and other.get("accountLineage") == lineage):
                raise PrincipalProvenanceDenied("duplicate private account lineage")

        grants = account.get("projects")
        if grants is not None and (
            type(grants) is not list or len(grants) > 1000
            or any(type(project) is not str or not 1 <= len(project) <= 180
                   or project != project.strip() for project in grants)
            or len(set(grants)) != len(grants)
        ):
            raise PrincipalProvenanceDenied("invalid private project grants")
        state = self._service.bridge.getState()
        projects = state.get("projects") if type(state) is dict else None
        if type(projects) is not list or len(projects) > 1000:
            raise PrincipalProvenanceDenied("current project registry missing")
        known = []
        for project in projects:
            if (type(project) is not dict or type(project.get("id")) is not str
                    or not 1 <= len(project["id"]) <= 180
                    or project["id"] != project["id"].strip()):
                raise PrincipalProvenanceDenied("invalid host project registry")
            known.append(project["id"])
        if len(set(known)) != len(known):
            raise PrincipalProvenanceDenied("duplicate host project IDs")
        permitted = frozenset(project for project in known
                              if grants is None or project in grants)
        if not permitted:
            raise PrincipalProvenanceDenied("no current project visibility")
        return TrustedPrincipal(
            user_id=actor, org_id=self._org_id,
            session_id=hashlib.sha256(token.encode("ascii")).hexdigest(),
            role=role, project_ids=permitted,
            permissions=frozenset({"mtr.read"}),
            authenticated=True, session_valid=True, active=True,
        )

    @staticmethod
    def _payload(seal: SealedRecoveryPrincipal) -> bytes:
        if type(seal) is not SealedRecoveryPrincipal:
            raise PrincipalProvenanceDenied("host-issued seal required")
        principal = seal.principal
        if type(principal) is not TrustedPrincipal:
            raise PrincipalProvenanceDenied("unexpected principal object")
        if (type(seal.audience) is not str or seal.audience not in _AUDIENCES
                or type(seal.issued_monotonic_ns) is not int
                or type(seal.nonce) is not bytes or len(seal.nonce) != _NONCE_BYTES
                or type(seal.mac) is not bytes or len(seal.mac) not in (0, 32)):
            raise PrincipalProvenanceDenied("malformed host seal")
        details = {
            "version": 1, "audience": seal.audience,
            "issuedNs": seal.issued_monotonic_ns, "nonce": seal.nonce.hex(),
            "actor": principal.user_id, "org": principal.org_id,
            "session": principal.session_id, "role": principal.role,
            "projects": sorted(principal.project_ids),
            "permissions": sorted(principal.permissions),
            "authenticated": principal.authenticated,
            "sessionValid": principal.session_valid,
            "active": principal.active,
        }
        try:
            raw = json.dumps(details, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")
        except (ValueError, TypeError, OverflowError) as exc:
            raise PrincipalProvenanceDenied("invalid sealed claims") from exc
        if len(raw) > 20000:
            raise PrincipalProvenanceDenied("unbounded sealed claims")
        return b"mtr.e2.host.recovery.seal.v1\x00" + raw

    def issue_recovery(self, token: str, *, audience: str) -> SealedRecoveryPrincipal:
        """Host-only: mint short-lived, single-use permission for ONE reader."""
        self._audience(audience)
        with self._service.lock, self._service.bridge._lock, self._guard:
            principal = self._current_principal(token)
            nonce = secrets.token_bytes(_NONCE_BYTES)
            if type(nonce) is not bytes or len(nonce) != _NONCE_BYTES or not any(nonce):
                raise PrincipalProvenanceDenied("host nonce generation failed")
            candidate = SealedRecoveryPrincipal(
                principal=principal, audience=audience,
                issued_monotonic_ns=time.monotonic_ns(), nonce=nonce, mac=b"",
            )
            signature = hmac.new(self.__secret, self._payload(candidate),
                                 hashlib.sha256).digest()
            return SealedRecoveryPrincipal(
                principal=principal, audience=audience,
                issued_monotonic_ns=candidate.issued_monotonic_ns,
                nonce=nonce, mac=signature,
            )

    def verify_and_consume(self, token: str, seal: SealedRecoveryPrincipal,
                           *, audience: str) -> TrustedPrincipal:
        """Recheck current host authorization and consume proof exactly once.

        Do not hand this returned TrustedPrincipal to a client. Future store/
        gate integration MUST require this verification itself at its entry
        point, not merely accept a caller-supplied principal/``verified`` flag.
        """
        self._audience(audience)
        with self._service.lock, self._service.bridge._lock, self._guard:
            if type(seal) is not SealedRecoveryPrincipal or seal.audience != audience:
                raise PrincipalProvenanceDenied("wrong or missing recovery seal")
            payload = self._payload(seal)
            if len(seal.mac) != 32 or not hmac.compare_digest(
                seal.mac, hmac.new(self.__secret, payload, hashlib.sha256).digest()
            ):
                raise PrincipalProvenanceDenied("invalid host seal provenance")
            now = time.monotonic_ns()
            age = now - seal.issued_monotonic_ns
            if not 0 <= age <= _TTL_NS:
                raise PrincipalProvenanceDenied("expired or future-issued host seal")
            # Rechecking account_for(token) protects against expired logins,
            # account deletion, password reset session revocation, and changes
            # to role, finance capability, original project grants or lineage.
            current = self._current_principal(token)
            if current != seal.principal:
                raise PrincipalProvenanceDenied("current host principal changed")
            # Local replay journal expires with the per-instance CSPRNG key.
            # A bounded fail-closed limit avoids unbounded process-memory use.
            stale = [nonce for nonce, consumed_at in self._used.items()
                     if now - consumed_at > _TTL_NS]
            for nonce in stale:
                del self._used[nonce]
            if seal.nonce in self._used:
                raise PrincipalProvenanceDenied("host recovery seal already used")
            if len(self._used) >= _MAX_USED:
                raise PrincipalProvenanceDenied("host replay capacity exhausted")
            self._used[seal.nonce] = now
            return current


__all__ = [
    "HostPrincipalProvenance", "SealedRecoveryPrincipal",
    "PrincipalProvenanceDenied", "OUTBOX_RECOVERY", "GATE_RECOVERY",
]
