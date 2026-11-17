"""E1 synthetic AI usage/budget authority: stdlib SQLite, no API/network/keys.

Host contract (not an HTTP API):
  store = AiUsageStore(absolute_private_sqlite_path)
  p = AiPrincipal(user_id, org_id, project_ids=frozenset(...),
                  role="admin"|"editor"|"viewer", authenticated=True,
                  active=True, manageable_user_ids=frozenset(...),
                  approved_cloud_request_ids=frozenset(...),
                  proven_local_nonexecution_ids=frozenset(...))
  store.set_grant(admin, ..., expected_version=0, event_id=..., at_utc=...)
  store.grant_cloud_consent(user, ..., request_id=..., payload_digest=...,
                            expires_at_utc=..., explicit_human_consent=True,
                            event_id=..., at_utc=...)
  store.reserve(user, ..., request_id=..., payload_digest=...,
                estimated_tokens=..., max_cost_micro=..., event_id=...,
                at_utc=...)
  store.mark_dispatched(user, ..., expected_version=1, event_id=...,
                        at_utc=...)
  store.complete(user, ..., expected_version=2, actual_tokens=...,
                 actual_cost_micro=..., event_id=..., at_utc=...)

The pure madar_ai_provider_policy.py remains independent and is NOT used as a
substitute for host authentication/ACL/consent. This store does not know prompt
text, real user records, API keys or price lists. payload_digest is a fixed
64-character host-origin digest of ONLY the explicitly selected text. A digest
is potentially linkable metadata: production should use a host-keyed HMAC,
never an unkeyed hash of low-entropy PII. No content, tokens, email, addresses,
credentials, customer names, provider secret or actual API response is stored.

Conservative financial rule: *reserved ceilings remain charged* after normal
completion and cancellation, even if actual use is lower. This can underutilize
budgets; it prevents trusting a client/provider claim to make spend room.
Cloud consent is consumed atomically with reserve and NEVER refunded. Only
an undispatched, cancelled LOCAL reservation may be refunded, and only with
host-verified nonexecution evidence. Request IDs are unique per organization
for all time; even a refunded ID cannot be recycled. Dispatch after grant
revocation/expiry or version change is rejected, and the hold remains charged.
Actual usage beyond reserved token/cost ceilings is rejected fail-closed, but
this alone cannot stop a separately implemented external provider from billing
more than an estimate. Real cloud transport MUST independently enforce output
ceilings, ensure dispatch only once, reconcile invoices and handle crashed
in-flight sends. This module does not perform paid/model work or scheduling.

Callers supply CURRENT trusted principal and host UTC timestamps; passing
browser-controlled identities, timestamps, proof flags or consent gestures
would violate the integration contract. DB OS ACL, encryption, backups,
trusted clocks, real Taraz/accounting and production integration are outside
the pilot. Audit triggers prevent ordinary UPDATE/DELETE, not privileged DB
schema modification. No automatic retry/fallback, account mutation or
effect on the manual (AI-off) entry workflow exists here.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Iterator


PROVIDERS = frozenset(("local_ollama", "openai", "gemini", "anthropic"))
CLOUD = PROVIDERS - {"local_ollama"}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_REQUEST = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z", re.ASCII)
MAX_REQUESTS = 100_000
MAX_TOKENS = 100_000_000
MAX_MICRO = 10**12
MAX_ACTUAL = 2**63 - 1


class AiUsageError(ValueError):
    """A safe, bounded error code without tenant or user identifiers."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise AiUsageError(code)


def _id(value: object, code: str = "invalid_id") -> str:
    _require(type(value) is str and _ID.fullmatch(value) is not None, code)
    return value


def _request_id(value: object) -> str:
    _require(type(value) is str and _REQUEST.fullmatch(value) is not None,
             "invalid_request_id")
    return value


def _digest(value: object) -> str:
    _require(type(value) is str and _DIGEST.fullmatch(value) is not None,
             "invalid_digest")
    return value


def _provider(value: object) -> str:
    _require(type(value) is str and value in PROVIDERS, "invalid_provider")
    return value


def _amount(value: object, upper: int, code: str, *, positive: bool = False) -> int:
    _require(type(value) is int and (0 < value if positive else 0 <= value <= upper)
             and value <= upper, code)
    return value


def _when(value: object) -> datetime:
    _require(type(value) is str and _UTC.fullmatch(value) is not None,
             "invalid_utc")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise AiUsageError("invalid_utc") from exc
    return parsed.replace(tzinfo=timezone.utc)


def _month(instant: datetime) -> str:
    return instant.strftime("%Y-%m")


@dataclass(frozen=True, slots=True)
class AiPrincipal:
    """Trusted HOST-INJECTED identity, never constructed from user JSON."""

    user_id: str
    org_id: str
    project_ids: frozenset[str]
    role: str
    authenticated: bool
    active: bool
    manageable_user_ids: frozenset[str] = frozenset()
    approved_cloud_request_ids: frozenset[str] = frozenset()
    proven_local_nonexecution_ids: frozenset[str] = frozenset()


def _principal(p: object, project: object, *, mutation: bool = False,
               admin: bool = False) -> AiPrincipal:
    _require(type(p) is AiPrincipal, "access_denied")
    _id(p.user_id, "access_denied")
    _id(p.org_id, "access_denied")
    _id(project, "access_denied")
    _require(type(p.role) is str and p.role in ("admin", "editor", "viewer") and
             type(p.authenticated) is bool and p.authenticated and
             type(p.active) is bool and p.active and
             type(p.project_ids) is frozenset and
             0 < len(p.project_ids) <= 1000 and
             all(type(item) is str and _ID.fullmatch(item)
                 for item in p.project_ids) and
             type(p.manageable_user_ids) is frozenset and
             len(p.manageable_user_ids) <= 1000 and
             all(type(item) is str and _ID.fullmatch(item)
                 for item in p.manageable_user_ids) and
             type(p.approved_cloud_request_ids) is frozenset and
             len(p.approved_cloud_request_ids) <= 128 and
             all(type(item) is str and _REQUEST.fullmatch(item)
                 for item in p.approved_cloud_request_ids) and
             type(p.proven_local_nonexecution_ids) is frozenset and
             len(p.proven_local_nonexecution_ids) <= 128 and
             all(type(item) is str and _REQUEST.fullmatch(item)
                 for item in p.proven_local_nonexecution_ids) and
             project in p.project_ids, "access_denied")
    if admin:
        _require(p.role == "admin", "access_denied")
    elif mutation:
        _require(p.role in ("admin", "editor"), "access_denied")
    return p


@dataclass(frozen=True, slots=True)
class Grant:
    user_id: str
    project_id: str
    provider: str
    version: int
    enabled: bool
    cloud_enabled: bool
    monthly_requests: int
    monthly_tokens: int
    monthly_cost_micro: int
    expires_at_utc: str | None


@dataclass(frozen=True, slots=True)
class Reservation:
    request_id: str
    project_id: str
    provider: str
    month_utc: str
    status: str
    version: int
    reserved_tokens: int
    reserved_cost_micro: int
    actual_tokens: int | None
    actual_cost_micro: int | None
    refunded: bool
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class Usage:
    month_utc: str
    charged_requests: int
    charged_tokens: int
    charged_cost_micro: int
    remaining_requests: int
    remaining_tokens: int
    remaining_cost_micro: int


class AiUsageStore:
    """Durable per-user/provider reservation ledger, NOT an AI dispatcher."""

    def __init__(self, path: str | Path):
        _require(isinstance(path, (Path, str)), "invalid_path")
        self.path = Path(path)
        _require(self.path.is_absolute() and self.path.parent.is_dir() and
                 self.path.suffix.lower() in (".db", ".sqlite") and
                 not self.path.is_symlink(), "invalid_path")
        with self._connect() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS ai_grants (
                org TEXT NOT NULL, project TEXT NOT NULL, user TEXT NOT NULL,
                provider TEXT NOT NULL, version INTEGER NOT NULL,
                enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                cloud_enabled INTEGER NOT NULL CHECK(cloud_enabled IN (0,1)),
                requests_cap INTEGER NOT NULL, tokens_cap INTEGER NOT NULL,
                cost_cap INTEGER NOT NULL, expires TEXT,
                PRIMARY KEY(org,project,user,provider)
              );
              CREATE TABLE IF NOT EXISTS ai_consents (
                org TEXT NOT NULL, request_id TEXT NOT NULL,
                project TEXT NOT NULL, user TEXT NOT NULL,
                provider TEXT NOT NULL, digest TEXT NOT NULL,
                expires TEXT NOT NULL, grant_version INTEGER NOT NULL,
                state TEXT NOT NULL
                  CHECK(state IN ('granted','revoked','consumed')),
                PRIMARY KEY(org,request_id)
              );
              CREATE TABLE IF NOT EXISTS ai_reservations (
                org TEXT NOT NULL, request_id TEXT NOT NULL,
                project TEXT NOT NULL, user TEXT NOT NULL,
                provider TEXT NOT NULL, month TEXT NOT NULL,
                digest TEXT NOT NULL, grant_version INTEGER NOT NULL,
                reserved_tokens INTEGER NOT NULL, reserved_cost INTEGER NOT NULL,
                actual_tokens INTEGER, actual_cost INTEGER,
                status TEXT NOT NULL
                  CHECK(status IN ('reserved','dispatched','completed',
                                   'cancelled','refunded')),
                version INTEGER NOT NULL, was_dispatched INTEGER NOT NULL
                  CHECK(was_dispatched IN (0,1)),
                PRIMARY KEY(org,request_id)
              );
              CREATE INDEX IF NOT EXISTS ai_usage_month
                ON ai_reservations(org,project,user,provider,month,status);
              CREATE TABLE IF NOT EXISTS ai_audit (
                org TEXT NOT NULL, event_id TEXT NOT NULL,
                actor TEXT NOT NULL, project TEXT NOT NULL, kind TEXT NOT NULL,
                occurred TEXT NOT NULL, payload_hash TEXT NOT NULL,
                result_ref TEXT NOT NULL, result_version INTEGER NOT NULL,
                PRIMARY KEY(org,event_id)
              );
              CREATE TRIGGER IF NOT EXISTS ai_audit_no_update
                BEFORE UPDATE ON ai_audit BEGIN
                  SELECT RAISE(ABORT,'AI audit append-only');
                END;
              CREATE TRIGGER IF NOT EXISTS ai_audit_no_delete
                BEFORE DELETE ON ai_audit BEGIN
                  SELECT RAISE(ABORT,'AI audit append-only');
                END;
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(str(self.path), isolation_level=None, timeout=6)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=6000")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    @staticmethod
    def _event(db: sqlite3.Connection, p: AiPrincipal, event_id: str,
               project: str, kind: str, at_utc: str, args: dict,
               result_ref: str | None = None, version: int | None = None) -> int | None:
        """Return replay version or None. Append only after mutation succeeds."""
        _id(event_id, "invalid_event_id")
        raw = json.dumps((p.user_id, project, kind, at_utc, args),
                         sort_keys=True, ensure_ascii=True, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        existing = db.execute(
            "SELECT payload_hash,result_ref,result_version FROM ai_audit"
            " WHERE org=? AND event_id=?", (p.org_id, event_id),
        ).fetchone()
        if existing:
            _require(existing["payload_hash"] == digest, "event_conflict")
            return existing["result_version"]
        if result_ref is not None:
            db.execute(
                "INSERT INTO ai_audit VALUES (?,?,?,?,?,?,?, ?,?)",
                (p.org_id, event_id, p.user_id, project, kind, at_utc,
                 digest, result_ref, version),
            )
        return None

    @staticmethod
    def _grant_row(db, p, project, provider, user):
        return db.execute(
            "SELECT * FROM ai_grants WHERE org=? AND project=?"
            " AND user=? AND provider=?",
            (p.org_id, project, user, provider),
        ).fetchone()

    @staticmethod
    def _read_grant(row) -> Grant:
        return Grant(row["user"], row["project"], row["provider"],
                     row["version"], bool(row["enabled"]),
                     bool(row["cloud_enabled"]), row["requests_cap"],
                     row["tokens_cap"], row["cost_cap"], row["expires"])

    @staticmethod
    def _reservation(row, *, replayed=False) -> Reservation:
        return Reservation(row["request_id"], row["project"], row["provider"],
                           row["month"], row["status"], row["version"],
                           row["reserved_tokens"], row["reserved_cost"],
                           row["actual_tokens"], row["actual_cost"],
                           row["status"] == "refunded", replayed)

    def set_grant(
        self, *, principal: AiPrincipal, project_id: str, user_id: str,
        provider: str, enabled: bool, cloud_enabled: bool,
        monthly_requests: int, monthly_tokens: int,
        monthly_cost_micro: int, expected_version: int,
        event_id: str, at_utc: str, expires_at_utc: str | None = None,
    ) -> Grant:
        p = _principal(principal, project_id, admin=True)
        user = _id(user_id)
        _require(user == p.user_id or user in p.manageable_user_ids,
                 "access_denied")
        prov = _provider(provider)
        _require(type(enabled) is bool and type(cloud_enabled) is bool,
                 "invalid_grant")
        _require(prov in CLOUD or not cloud_enabled, "invalid_grant")
        caps = (
            _amount(monthly_requests, MAX_REQUESTS, "invalid_budget"),
            _amount(monthly_tokens, MAX_TOKENS, "invalid_budget"),
            _amount(monthly_cost_micro, MAX_MICRO, "invalid_budget"),
        )
        _require(type(expected_version) is int and 0 <= expected_version < 2**63-1,
                 "invalid_version")
        at = _when(at_utc)
        if expires_at_utc is not None:
            _require(_when(expires_at_utc) > at, "invalid_expiration")
        args = {"user": user, "provider": prov, "enabled": enabled,
                "cloud_enabled": cloud_enabled, "caps": caps,
                "expires": expires_at_utc, "expected": expected_version}
        with self._write() as db:
            replay = self._event(db, p, event_id, project_id, "grant_set",
                                 at_utc, args)
            if replay is not None:
                # Historical response: an old replay does not report a
                # newer/revoked grant as though it belonged to this event.
                return Grant(user, project_id, prov, replay, enabled,
                             cloud_enabled, *caps, expires_at_utc)
            row = self._grant_row(db, p, project_id, prov, user)
            _require((row["version"] if row else 0) == expected_version,
                     "version_conflict")
            new_version = expected_version + 1
            db.execute(
                "INSERT INTO ai_grants VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(org,project,user,provider) DO UPDATE SET"
                " version=excluded.version, enabled=excluded.enabled,"
                " cloud_enabled=excluded.cloud_enabled,"
                " requests_cap=excluded.requests_cap,"
                " tokens_cap=excluded.tokens_cap, cost_cap=excluded.cost_cap,"
                " expires=excluded.expires",
                (p.org_id, project_id, user, prov, new_version, int(enabled),
                 int(cloud_enabled), *caps, expires_at_utc),
            )
            self._event(db, p, event_id, project_id, "grant_set", at_utc, args,
                        f"grant:{user}:{prov}", new_version)
            return self._read_grant(self._grant_row(db, p, project_id, prov, user))

    def get_grant(self, *, principal: AiPrincipal, project_id: str,
                  user_id: str, provider: str) -> Grant | None:
        p = _principal(principal, project_id)
        _id(user_id)
        prov = _provider(provider)
        _require(p.user_id == user_id or
                 (p.role == "admin" and user_id in p.manageable_user_ids),
                 "access_denied")
        with self._connect() as db:
            row = self._grant_row(db, p, project_id, prov, user_id)
            return self._read_grant(row) if row else None

    @staticmethod
    def _active(row, provider, at):
        _require(row is not None and row["enabled"] == 1 and
                 (provider == "local_ollama" or row["cloud_enabled"] == 1)
                 and (row["expires"] is None or _when(row["expires"]) > at),
                 "grant_denied")

    def grant_cloud_consent(
        self, *, principal: AiPrincipal, project_id: str, provider: str,
        request_id: str, payload_digest: str, expires_at_utc: str,
        explicit_human_consent: bool, event_id: str, at_utc: str,
    ) -> str:
        p = _principal(principal, project_id, mutation=True)
        prov = _provider(provider)
        _require(prov in CLOUD, "cloud_only")
        request = _request_id(request_id)
        digest = _digest(payload_digest)
        at = _when(at_utc)
        expiry = _when(expires_at_utc)
        _require(type(explicit_human_consent) is bool and
                 explicit_human_consent and
                 request in p.approved_cloud_request_ids, "consent_required")
        _require(at < expiry <= at + timedelta(minutes=15),
                 "invalid_expiration")
        args = {"request": request, "provider": prov, "digest": digest,
                "expires": expires_at_utc, "human": True}
        with self._write() as db:
            replay = self._event(db, p, event_id, project_id,
                                 "cloud_consent", at_utc, args)
            if replay is not None:
                return "recorded_replay"
            grant = self._grant_row(db, p, project_id, prov, p.user_id)
            self._active(grant, prov, at)
            existing = db.execute(
                "SELECT 1 FROM ai_consents WHERE org=? AND request_id=?",
                (p.org_id, request),
            ).fetchone()
            used = db.execute(
                "SELECT 1 FROM ai_reservations WHERE org=? AND request_id=?",
                (p.org_id, request),
            ).fetchone()
            _require(existing is None and used is None, "request_exists")
            db.execute(
                "INSERT INTO ai_consents VALUES (?,?,?,?,?,?,?,?,?)",
                (p.org_id, request, project_id, p.user_id, prov, digest,
                 expires_at_utc, grant["version"], "granted"),
            )
            self._event(db, p, event_id, project_id, "cloud_consent", at_utc,
                        args, request, 1)
            return "recorded"

    def revoke_cloud_consent(
        self, *, principal: AiPrincipal, project_id: str, request_id: str,
        event_id: str, at_utc: str,
    ) -> str:
        p = _principal(principal, project_id, mutation=True)
        request = _request_id(request_id)
        _when(at_utc)
        args = {"request": request}
        with self._write() as db:
            replay = self._event(db, p, event_id, project_id,
                                 "consent_revoked", at_utc, args)
            if replay is not None:
                return "revoked_replay"
            row = db.execute(
                "SELECT * FROM ai_consents WHERE org=? AND request_id=?"
                " AND project=? AND user=?",
                (p.org_id, request, project_id, p.user_id),
            ).fetchone()
            _require(row is not None, "not_found")
            _require(row["state"] == "granted", "consent_not_active")
            db.execute(
                "UPDATE ai_consents SET state='revoked' WHERE org=? AND request_id=?",
                (p.org_id, request),
            )
            self._event(db, p, event_id, project_id, "consent_revoked", at_utc,
                        args, request, 1)
            return "revoked"

    @staticmethod
    def _month_used(db, p, project, provider, month):
        row = db.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(reserved_tokens),0) AS t,"
            " COALESCE(SUM(reserved_cost),0) AS c FROM ai_reservations"
            " WHERE org=? AND project=? AND user=? AND provider=? AND month=?"
            " AND status<>'refunded'",
            (p.org_id, project, p.user_id, provider, month),
        ).fetchone()
        return row["n"], row["t"], row["c"]

    def reserve(
        self, *, principal: AiPrincipal, project_id: str, provider: str,
        request_id: str, payload_digest: str, estimated_tokens: int,
        max_cost_micro: int, event_id: str, at_utc: str,
    ) -> Reservation:
        p = _principal(principal, project_id, mutation=True)
        prov = _provider(provider)
        request = _request_id(request_id)
        digest = _digest(payload_digest)
        tokens = _amount(estimated_tokens, MAX_TOKENS, "invalid_budget",
                         positive=True)
        cost = _amount(max_cost_micro, MAX_MICRO, "invalid_budget")
        _require(prov in CLOUD or cost == 0, "invalid_budget")
        _require(prov not in CLOUD or cost > 0, "invalid_budget")
        at = _when(at_utc)
        month = _month(at)
        args = {"request": request, "provider": prov, "digest": digest,
                "tokens": tokens, "cost": cost}
        with self._write() as db:
            replay = self._event(db, p, event_id, project_id,
                                 "reserve", at_utc, args)
            if replay is not None:
                row = db.execute(
                    "SELECT * FROM ai_reservations WHERE org=? AND request_id=?"
                    " AND user=? AND project=? AND provider=? AND digest=?",
                    (p.org_id, request, p.user_id, project_id, prov, digest),
                ).fetchone()
                _require(row is not None, "request_conflict")
                return self._reservation(row, replayed=True)
            grant = self._grant_row(db, p, project_id, prov, p.user_id)
            self._active(grant, prov, at)
            used_request = db.execute(
                "SELECT 1 FROM ai_reservations WHERE org=? AND request_id=?",
                (p.org_id, request),
            ).fetchone()
            _require(used_request is None, "request_conflict")
            if prov in CLOUD:
                consent = db.execute(
                    "SELECT * FROM ai_consents WHERE org=? AND request_id=?",
                    (p.org_id, request),
                ).fetchone()
                _require(consent is not None and
                         consent["project"] == project_id and
                         consent["user"] == p.user_id and
                         consent["provider"] == prov and
                         consent["digest"] == digest and
                         consent["state"] == "granted" and
                         consent["grant_version"] == grant["version"] and
                         _when(consent["expires"]) > at, "consent_required")
            counts = self._month_used(db, p, project_id, prov, month)
            _require(counts[0] + 1 <= grant["requests_cap"] and
                     counts[1] + tokens <= grant["tokens_cap"] and
                     counts[2] + cost <= grant["cost_cap"], "budget_exceeded")
            db.execute(
                "INSERT INTO ai_reservations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.org_id, request, project_id, p.user_id, prov, month, digest,
                 grant["version"], tokens, cost, None, None, "reserved", 1, 0),
            )
            if prov in CLOUD:
                db.execute(
                    "UPDATE ai_consents SET state='consumed'"
                    " WHERE org=? AND request_id=? AND state='granted'",
                    (p.org_id, request),
                )
            self._event(db, p, event_id, project_id, "reserve", at_utc, args,
                        request, 1)
            return self._reservation(db.execute(
                "SELECT * FROM ai_reservations WHERE org=? AND request_id=?",
                (p.org_id, request),
            ).fetchone())

    @staticmethod
    def _owned(db, p, project, request):
        row = db.execute(
            "SELECT * FROM ai_reservations WHERE org=? AND project=?"
            " AND user=? AND request_id=?",
            (p.org_id, project, p.user_id, request),
        ).fetchone()
        _require(row is not None, "not_found")
        return row

    def _transition(
        self, *, principal: AiPrincipal, project_id: str, request_id: str,
        expected_version: int, event_id: str, at_utc: str, kind: str,
        actual_tokens: int | None = None, actual_cost_micro: int | None = None,
        verified_no_execution: bool | None = None,
    ) -> Reservation:
        p = _principal(principal, project_id, mutation=True)
        request = _request_id(request_id)
        at = _when(at_utc)
        _require(type(expected_version) is int and
                 1 <= expected_version < 2**63-1, "invalid_version")
        args = {"request": request, "expected": expected_version}
        if kind == "complete":
            args["actual_tokens"] = _amount(actual_tokens, MAX_TOKENS,
                                            "invalid_usage")
            args["actual_cost_micro"] = _amount(actual_cost_micro, MAX_MICRO,
                                                "invalid_usage")
        if kind == "refund":
            _require(verified_no_execution is True,
                     "verified_nonexecution_required")
            _require(request in p.proven_local_nonexecution_ids,
                     "verified_nonexecution_required")
            args["proof"] = True
        with self._write() as db:
            row = self._owned(db, p, project_id, request)
            replay = self._event(db, p, event_id, project_id, kind,
                                 at_utc, args)
            if replay is not None:
                return self._reservation(row, replayed=True)
            _require(row["version"] == expected_version, "version_conflict")
            status = row["status"]
            next_status = ""
            was_sent = row["was_dispatched"]
            if kind == "dispatch":
                _require(status == "reserved", "invalid_state")
                grant = self._grant_row(db, p, project_id, row["provider"],
                                        p.user_id)
                self._active(grant, row["provider"], at)
                _require(grant["version"] == row["grant_version"],
                         "grant_changed")
                if row["provider"] in CLOUD:
                    consent = db.execute(
                        "SELECT * FROM ai_consents WHERE org=? AND request_id=?",
                        (p.org_id, request),
                    ).fetchone()
                    _require(consent is not None and
                             consent["state"] == "consumed" and
                             consent["project"] == project_id and
                             consent["user"] == p.user_id and
                             consent["provider"] == row["provider"] and
                             consent["digest"] == row["digest"] and
                             consent["grant_version"] == grant["version"] and
                             _when(consent["expires"]) > at,
                             "consent_expired")
                next_status, was_sent = "dispatched", 1
            elif kind == "complete":
                _require(status == "dispatched", "invalid_state")
                _require(actual_tokens <= row["reserved_tokens"] and
                         actual_cost_micro <= row["reserved_cost"],
                         "usage_exceeds_reservation")
                next_status = "completed"
            elif kind == "cancel":
                _require(status in ("reserved", "dispatched"), "invalid_state")
                next_status = "cancelled"
            elif kind == "refund":
                _require(status == "cancelled" and
                         row["provider"] == "local_ollama" and
                         not row["was_dispatched"], "refund_denied")
                next_status = "refunded"
            else:
                raise AiUsageError("invalid_transition")
            update = db.execute(
                "UPDATE ai_reservations SET status=?,version=version+1,"
                " was_dispatched=?,actual_tokens=?,actual_cost=?"
                " WHERE org=? AND request_id=? AND user=? AND project=?"
                " AND version=?",
                (next_status, was_sent, actual_tokens if kind == "complete"
                 else row["actual_tokens"], actual_cost_micro if kind == "complete"
                 else row["actual_cost"], p.org_id, request, p.user_id,
                 project_id, expected_version),
            )
            _require(update.rowcount == 1, "version_conflict")
            self._event(db, p, event_id, project_id, kind, at_utc, args,
                        request, expected_version + 1)
            return self._reservation(self._owned(db, p, project_id, request))

    def mark_dispatched(self, *, principal: AiPrincipal, project_id: str,
                        request_id: str, expected_version: int, event_id: str,
                        at_utc: str) -> Reservation:
        """Accounting intent only: DOES NOT SEND ANYTHING."""
        return self._transition(
            principal=principal, project_id=project_id, request_id=request_id,
            expected_version=expected_version, event_id=event_id,
            at_utc=at_utc, kind="dispatch")

    def complete(self, *, principal: AiPrincipal, project_id: str,
                 request_id: str, expected_version: int, actual_tokens: int,
                 actual_cost_micro: int, event_id: str,
                 at_utc: str) -> Reservation:
        return self._transition(
            principal=principal, project_id=project_id, request_id=request_id,
            expected_version=expected_version, event_id=event_id,
            at_utc=at_utc, kind="complete", actual_tokens=actual_tokens,
            actual_cost_micro=actual_cost_micro)

    def cancel(self, *, principal: AiPrincipal, project_id: str,
               request_id: str, expected_version: int, event_id: str,
               at_utc: str) -> Reservation:
        return self._transition(
            principal=principal, project_id=project_id, request_id=request_id,
            expected_version=expected_version, event_id=event_id,
            at_utc=at_utc, kind="cancel")

    def refund_undispatched_local(
        self, *, principal: AiPrincipal, project_id: str, request_id: str,
        expected_version: int, verified_no_execution: bool, event_id: str,
        at_utc: str,
    ) -> Reservation:
        return self._transition(
            principal=principal, project_id=project_id, request_id=request_id,
            expected_version=expected_version, event_id=event_id,
            at_utc=at_utc, kind="refund",
            verified_no_execution=verified_no_execution)

    def read_reservation(self, *, principal: AiPrincipal,
                         project_id: str, request_id: str) -> Reservation:
        p = _principal(principal, project_id)
        request = _request_id(request_id)
        with self._connect() as db:
            return self._reservation(self._owned(db, p, project_id, request))

    def usage(self, *, principal: AiPrincipal, project_id: str,
              provider: str, at_utc: str) -> Usage:
        p = _principal(principal, project_id)
        prov = _provider(provider)
        month = _month(_when(at_utc))
        with self._connect() as db:
            grant = self._grant_row(db, p, project_id, prov, p.user_id)
            _require(grant is not None, "grant_denied")
            n, t, c = self._month_used(db, p, project_id, prov, month)
            return Usage(
                month, n, t, c, max(0, grant["requests_cap"] - n),
                max(0, grant["tokens_cap"] - t),
                max(0, grant["cost_cap"] - c),
            )


__all__ = [
    "AiPrincipal", "AiUsageStore", "AiUsageError", "Grant",
    "Reservation", "Usage", "PROVIDERS", "CLOUD",
]
