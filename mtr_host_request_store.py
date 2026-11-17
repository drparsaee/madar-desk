"""Isolated, metadata-only SQLite host outbox for Madar -> Taraz.

This module NEVER calls a peer, creates a financial document, or posts to a
ledger. A manual send records an immutable authorization *intent*, not a sent
message. Query results are evidence supplied by a trusted Taraz adapter, not
facts inferred from a timeout. The caller MUST derive TrustedPrincipal and
current revisions from its authenticated server authority, not browser input.

This is a versioned, stdlib-only pilot. No production LanService hookup.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from typing import Mapping


class StoreError(ValueError):
    """Invalid or corrupt store input."""


class StoreConflict(StoreError):
    """An existing identity/key/evidence disagrees with the new operation."""


_ID = re.compile(r"[0-9a-f]{32}\Z")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_PAYLOAD = 32768
_MAX_EVIDENCE = 4096
_ALLOWED_FIELDS = frozenset({
    "schema", "id", "source", "taskId", "projectId", "title",
    "createdUtc", "expenseId", "amountRial",
})
_REQUIRED_FIELDS = frozenset({
    "schema", "id", "source", "taskId", "projectId", "title", "createdUtc",
})
_EVIDENCE_KEYS = frozenset({
    "schema", "source", "observationId", "requestId", "orgId", "projectId",
    "baseRevision", "payloadSha256", "sendKey", "result", "receiptId",
    "observedUtc",
})
_PREPARE_ROLES = frozenset({"editor", "admin"})
_SEND_ROLES = frozenset({"editor", "admin", "finance_submitter"})
_READ_ROLES = frozenset({"editor", "admin", "finance_submitter", "finance_reviewer"})
_PERMISSIONS = frozenset({
    "mtr.prepare", "mtr.manual_send", "mtr.read", "mtr.receipt_ingest",
})


def _identifier(name: str, value: object, *, maximum: int = 180) -> str:
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value) > maximum or not value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise StoreError(f"invalid {name}")
    return value


def _version(value: object) -> int:
    if type(value) is not int or value < 1 or value > 2**53 - 1:
        raise StoreError("base revision must be a positive exact integer")
    return value


def _key(value: object) -> str:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise StoreError("invalid idempotency key")
    return value


def _request_id(value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise StoreError("invalid request ID")
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise StoreError("invalid SHA-256")
    return value


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or len(value) > 40:
        raise StoreError("invalid receipt timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise StoreError("invalid receipt timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StoreError("receipt timestamp must include timezone")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(data: Mapping[str, object], maximum: int) -> tuple[str, str]:
    if not isinstance(data, Mapping):
        raise StoreError("JSON metadata object required")
    try:
        encoded = json.dumps(
            dict(data), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError):
        raise StoreError("non-JSON metadata input") from None
    raw = encoded.encode("utf-8")
    if not raw or len(raw) > maximum:
        raise StoreError("JSON exceeds metadata bound")
    return encoded, hashlib.sha256(raw).hexdigest()


def _parse_canonical(encoded: object, maximum: int) -> dict:
    if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > maximum:
        raise StoreError("stored JSON exceeds bound")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise StoreError("duplicate stored JSON field")
            result[key] = value
        return result

    try:
        parsed = json.loads(encoded, object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StoreError("non-finite stored JSON")
                            ))
    except (json.JSONDecodeError, UnicodeError, TypeError):
        raise StoreError("corrupt stored JSON") from None
    if not isinstance(parsed, dict) or _canonical(parsed, maximum)[0] != encoded:
        raise StoreError("noncanonical or corrupt stored JSON")
    return parsed


def _proposal(payload: Mapping[str, object], request_id: str) -> tuple[str, str, dict]:
    encoded, digest = _canonical(payload, _MAX_PAYLOAD)
    obj = _parse_canonical(encoded, _MAX_PAYLOAD)
    if not _REQUIRED_FIELDS.issubset(obj) or not set(obj).issubset(_ALLOWED_FIELDS):
        raise StoreError("only bounded Madar metadata fields are allowed")
    if type(obj["schema"]) is not int or obj["schema"] != 1 or obj["source"] != "madar":
        raise StoreError("unsupported Madar metadata schema/source")
    if obj["id"] != request_id:
        raise StoreError("payload ID differs from request ID")
    for name, limit in (("taskId", 180), ("projectId", 180),
                        ("title", 300), ("createdUtc", 40)):
        _identifier(name, obj[name], maximum=limit)
    _timestamp(obj["createdUtc"])
    if "expenseId" in obj and obj["expenseId"] is not None:
        _identifier("expenseId", obj["expenseId"])
    if "amountRial" in obj and obj["amountRial"] is not None:
        number = obj["amountRial"]
        if (not isinstance(number, str) or not 1 <= len(number) <= 16
                or not number.isascii() or not number.isdecimal()
                or int(number) > 9007199254740991):
            raise StoreError("amountRial must be bounded decimal string")
    return encoded, digest, obj


@dataclass(frozen=True, slots=True)
class TrustedPrincipal:
    """Server-derived principal, not safe to deserialize from client JSON."""

    user_id: str
    org_id: str
    session_id: str
    role: str
    project_ids: frozenset[str]
    permissions: frozenset[str]
    authenticated: bool
    session_valid: bool
    active: bool = True

    def __post_init__(self):
        for name in ("user_id", "org_id", "session_id", "role"):
            _identifier(name, getattr(self, name))
        if not isinstance(self.project_ids, frozenset):
            raise StoreError("project grants must be frozenset")
        if not isinstance(self.permissions, frozenset):
            raise StoreError("permissions must be frozenset")
        for project in self.project_ids:
            _identifier("project grant", project)
        for permission in self.permissions:
            _identifier("permission", permission)
        if any(type(getattr(self, name)) is not bool for name in (
                "authenticated", "session_valid", "active")):
            raise StoreError("principal authentication must be explicit booleans")


def _scope(principal: TrustedPrincipal, *, permission: str,
           org_id: str, project_id: str, roles: frozenset[str]) -> None:
    if type(principal) is not TrustedPrincipal:
        raise PermissionError("trusted server principal required")
    if not principal.authenticated or not principal.session_valid or not principal.active:
        raise PermissionError("active authenticated session required")
    if (principal.org_id != org_id or project_id not in principal.project_ids
            or principal.role not in roles or permission not in principal.permissions):
        raise PermissionError("organization/project/role/capability denied")


def _safe_path(path: Path, *, expected_dir: bool | None = None):
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise PermissionError("symlink or junction database path forbidden")
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if getattr(info, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise PermissionError("reparse point forbidden")
    if expected_dir is True and not stat.S_ISDIR(info.st_mode):
        raise PermissionError("expected trusted directory")
    if expected_dir is False and not stat.S_ISREG(info.st_mode):
        raise PermissionError("expected regular file")
    if expected_dir is False and info.st_nlink > 1:
        raise PermissionError("hard-linked database file forbidden")
    return True


def _safe_ancestors(path: Path) -> None:
    # Includes intermediate Windows junctions, not just the immediate parent.
    for ancestor in (path, *path.parents):
        if not _safe_path(ancestor, expected_dir=True):
            raise StoreError("trusted existing directory chain required")


_CREATE = """
CREATE TABLE IF NOT EXISTS requests (
    request_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    prepare_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    base_revision INTEGER NOT NULL CHECK (base_revision > 0),
    state TEXT NOT NULL CHECK (state IN ('PREPARED','MANUAL_SEND_AUTHORIZED')),
    receipt_state TEXT NOT NULL CHECK (receipt_state IN ('unknown','received','not_received')),
    send_key TEXT,
    receipt_id TEXT,
    prepared_at TEXT NOT NULL,
    authorized_at TEXT,
    UNIQUE(org_id, prepare_key),
    UNIQUE(org_id, send_key)
);
CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES requests(request_id),
    evidence_json TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL,
    observer_id TEXT NOT NULL,
    observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES requests(request_id),
    actor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS requests_scope ON requests(org_id, project_id, actor_id);
CREATE INDEX IF NOT EXISTS observations_request ON observations(request_id);
"""


class HostRequestStore:
    """One SQLite file in an OS-ACL-protected, server-selected directory.

    HostRequestStore(path) creates only the metadata DB (never a finance DB).
    Each action opens its own connection; writes use BEGIN IMMEDIATE.
    """

    def __init__(self, path: Path):
        if not isinstance(path, Path) or not path.is_absolute() or path.suffix != ".sqlite3":
            raise StoreError("trusted absolute .sqlite3 path required")
        _safe_ancestors(path.parent)
        _safe_path(path, expected_dir=False)
        self.path = path
        # F1: recovery has NO principal-only fallback. This instance must be
        # explicitly bound to the live host's per-process HMAC issuer first.
        self._recovery_provenance = None
        new = not path.exists()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version == 0 and new:
                    # The schema is newly created by the host, not imported from
                    # arbitrary application data.
                    for statement in _CREATE.split(";"):
                        if statement.strip():
                            conn.execute(statement)
                    conn.execute("PRAGMA user_version=1")
                elif version != 1:
                    raise StoreError("unexpected schema version or uninitialized file")
                for table in ("requests", "observations", "audit"):
                    found = conn.execute(
                        "SELECT type FROM sqlite_master WHERE name=?", (table,)
                    ).fetchone()
                    if found is None or found["type"] != "table":
                        raise StoreError("missing metadata table")
                if conn.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                    raise StoreError("SQLite integrity check failed")
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @contextmanager
    def _connect(self):
        _safe_ancestors(self.path.parent)
        _safe_path(self.path, expected_dir=False)
        conn = sqlite3.connect(str(self.path), timeout=8, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=8000")
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=FULL")
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write(self):
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def _get(self, conn: sqlite3.Connection, request_id: str):
        row = conn.execute(
            "SELECT * FROM requests WHERE request_id=?", (request_id,)
        ).fetchone()
        if row is None:
            raise KeyError("request not found")
        result = self._validate_row(row)
        self._validate_observations(conn, result)
        return result

    def _validate_row(self, row):
        obj = dict(row)
        _request_id(obj["request_id"])
        encoded, digest, proposal = _proposal(
            _parse_canonical(obj["payload_json"], _MAX_PAYLOAD), obj["request_id"],
        )
        if (encoded != obj["payload_json"] or digest != obj["payload_sha256"]
                or proposal["projectId"] != obj["project_id"]):
            raise StoreError("stored request payload corruption")
        for name in ("org_id", "project_id", "actor_id", "session_id"):
            _identifier(name, obj[name])
        _key(obj["prepare_key"])
        _version(obj["base_revision"])
        if obj["state"] not in {"PREPARED", "MANUAL_SEND_AUTHORIZED"}:
            raise StoreError("corrupt request state")
        if obj["receipt_state"] not in {"unknown", "received", "not_received"}:
            raise StoreError("corrupt receipt state")
        if obj["state"] == "PREPARED" and (obj["send_key"] is not None
                or obj["authorized_at"] is not None or obj["receipt_id"] is not None
                or obj["receipt_state"] != "unknown"):
            raise StoreError("unjustified send or receipt on prepared request")
        if obj["state"] == "MANUAL_SEND_AUTHORIZED":
            _key(obj["send_key"])
            _timestamp(obj["authorized_at"])
        if obj["receipt_state"] == "received":
            _identifier("receipt ID", obj["receipt_id"])
        elif obj["receipt_id"] is not None:
            raise StoreError("receipt ID without confirmed receipt")
        _timestamp(obj["prepared_at"])
        return obj

    @staticmethod
    def _validate_observations(conn: sqlite3.Connection, row: dict):
        observations = conn.execute(
            "SELECT observation_id,request_id,evidence_json,evidence_sha256"
            " FROM observations WHERE request_id=? ORDER BY rowid LIMIT 257",
            (row["request_id"],),
        ).fetchall()
        if len(observations) > 256:
            raise StoreError("receipt observation count exceeds safety bound")
        state = "unknown"
        receipt_id = None
        if observations and row["state"] != "MANUAL_SEND_AUTHORIZED":
            raise StoreError("receipt observation without manual authorization")
        for entry in observations:
            proof = _parse_canonical(entry["evidence_json"], _MAX_EVIDENCE)
            if (set(proof) != _EVIDENCE_KEYS
                    or _canonical(proof, _MAX_EVIDENCE)[1] != entry["evidence_sha256"]
                    or entry["request_id"] != row["request_id"]
                    or proof["observationId"] != entry["observation_id"]
                    or type(proof["schema"]) is not int or proof["schema"] != 1
                    or proof["source"] != "taraz"
                    or proof["requestId"] != row["request_id"]
                    or proof["orgId"] != row["org_id"]
                    or proof["projectId"] != row["project_id"]
                    or proof["baseRevision"] != row["base_revision"]
                    or proof["payloadSha256"] != row["payload_sha256"]
                    or proof["sendKey"] != row["send_key"]
                    or type(proof["result"]) is not str
                    or proof["result"] not in {"unknown", "received", "not_received"}):
                raise StoreError("corrupt or unrelated stored receipt observation")
            _key(proof["observationId"])
            _timestamp(proof["observedUtc"])
            if proof["result"] == "received":
                _identifier("receipt ID", proof["receiptId"])
                if state == "received" and receipt_id != proof["receiptId"]:
                    raise StoreError("conflicting stored receipts")
                state = "received"
                receipt_id = proof["receiptId"]
            elif proof["result"] == "not_received":
                if proof["receiptId"] is not None or state == "received":
                    raise StoreError("stored receipt state downgraded")
                state = "not_received"
            elif proof["receiptId"] is not None or state != "unknown":
                raise StoreError("stored unknown result contradicts known state")
        if state != row["receipt_state"] or receipt_id != row["receipt_id"]:
            raise StoreError("receipt status not supported by stored observations")

    @staticmethod
    def _audit(conn, row, principal, kind: str, details: dict):
        encoded, _ = _canonical(details, _MAX_EVIDENCE)
        conn.execute(
            "INSERT INTO audit(request_id,actor_id,session_id,kind,detail_json,occurred_at)"
            " VALUES(?,?,?,?,?,?)",
            (row["request_id"], principal.user_id, principal.session_id,
             kind, encoded, _now()),
        )

    @staticmethod
    def _as_status(row: dict) -> dict:
        """Operational view only; pre-verifier receipt claims are quarantined.

        ``_get`` still validates the original stored row and every historical
        observation. No official Taraz receipt authority is configured, so a
        past local claim of received/not_received can NEVER justify a receipt
        confirmation, a negative receipt, or a resend suggestion. Do not
        rewrite the forensic original SQLite values to achieve this view.
        """
        quarantined = row["receipt_state"] != "unknown"
        if row["state"] == "PREPARED":
            next_action = "explicit_manual_send_required"
        else:
            next_action = "query_taraz_first_hold_unknown"
        return {
            "requestId": row["request_id"],
            "requestState": row["state"],
            "receiptState": "unknown",
            "receiptId": None,
            "receiptVerification": "UNVERIFIED",
            "historicalReceiptQuarantined": quarantined,
            "sendKey": row["send_key"],
            "nextAction": next_action,
            "canAutoRetry": False,
            "officialTarazReceipt": False,
            "transportCalled": False,
            "financialEventCreated": False,
        }

    @staticmethod
    def _human_scope(principal, row, permission: str, roles):
        _scope(principal, permission=permission, org_id=row["org_id"],
               project_id=row["project_id"], roles=roles)
        if (principal.user_id != row["actor_id"]
                or principal.session_id != row["session_id"]):
            raise PermissionError("request actor/session mismatch")

    def prepare_request(
        self, *, principal: TrustedPrincipal, request_id: str,
        payload: Mapping[str, object], base_revision: int,
        current_server_revision: int, prepare_key: str,
        explicit_manual_action: bool,
    ) -> dict:
        """Persist one bounded metadata proposal; do not authorize transmission."""
        _request_id(request_id)
        _version(base_revision)
        _version(current_server_revision)
        _key(prepare_key)
        if explicit_manual_action is not True:
            raise PermissionError("manual prepare action required")
        if base_revision != current_server_revision:
            raise StoreConflict("stale server revision")
        encoded, digest, obj = _proposal(payload, request_id)
        if type(principal) is not TrustedPrincipal:
            raise PermissionError("trusted server principal required")
        _scope(principal, permission="mtr.prepare", org_id=principal.org_id,
               project_id=obj["projectId"], roles=_PREPARE_ROLES)
        with self._write() as conn:
            existing_key = conn.execute(
                "SELECT * FROM requests WHERE org_id=? AND prepare_key=?",
                (principal.org_id, prepare_key),
            ).fetchone()
            existing_id = conn.execute(
                "SELECT * FROM requests WHERE request_id=?", (request_id,)
            ).fetchone()
            if existing_key is not None or existing_id is not None:
                if existing_key is None or existing_id is None:
                    raise StoreConflict("request ID or prepare key already used")
                old = self._validate_row(existing_key)
                if old["request_id"] != request_id or existing_key["request_id"] != existing_id["request_id"]:
                    raise StoreConflict("idempotency key reused for different request")
                if (
                    old["payload_sha256"] != digest
                    or old["payload_json"] != encoded
                    or old["base_revision"] != base_revision
                    or old["actor_id"] != principal.user_id
                    or old["session_id"] != principal.session_id
                    or old["org_id"] != principal.org_id
                    or old["project_id"] != obj["projectId"]
                ):
                    raise StoreConflict("prepared request conflicts with previous intent")
                return self._as_status(old) | {
                    "payloadSha256": old["payload_sha256"],
                    "baseRevision": old["base_revision"],
                    "idempotent": True,
                }
            now = _now()
            conn.execute(
                "INSERT INTO requests(request_id,org_id,project_id,actor_id,session_id,"
                "prepare_key,payload_json,payload_sha256,base_revision,state,receipt_state,"
                "prepared_at) VALUES(?,?,?,?,?,?,?,?,?,'PREPARED','unknown',?)",
                (request_id, principal.org_id, obj["projectId"], principal.user_id,
                 principal.session_id, prepare_key, encoded, digest, base_revision, now),
            )
            inserted = self._get(conn, request_id)
            self._audit(conn, inserted, principal, "manual_prepare", {
                "baseRevision": base_revision, "payloadSha256": digest,
            })
            return self._as_status(inserted) | {
                "payloadSha256": digest,
                "baseRevision": base_revision,
                "idempotent": False,
            }

    def manual_send(
        self, *, principal: TrustedPrincipal, request_id: str,
        expected_payload_sha256: str, expected_base_revision: int,
        current_server_revision: int, send_key: str,
        explicit_manual_action: bool,
    ) -> dict:
        """Persist an unsent, explicit send authorization; NEVER call Taraz."""
        _request_id(request_id)
        _digest(expected_payload_sha256)
        _version(expected_base_revision)
        _version(current_server_revision)
        _key(send_key)
        if explicit_manual_action is not True:
            raise PermissionError("manual send action required")
        with self._write() as conn:
            row = self._get(conn, request_id)
            self._human_scope(principal, row, "mtr.manual_send", _SEND_ROLES)
            if (row["base_revision"] != expected_base_revision
                    or row["base_revision"] != current_server_revision
                    or row["payload_sha256"] != expected_payload_sha256):
                raise StoreConflict("stale or mismatched payload/revision")
            other = conn.execute(
                "SELECT request_id FROM requests WHERE org_id=? AND send_key=?",
                (principal.org_id, send_key),
            ).fetchone()
            if other is not None and other["request_id"] != request_id:
                raise StoreConflict("send key already belongs to another request")
            if row["state"] == "MANUAL_SEND_AUTHORIZED":
                if row["send_key"] != send_key:
                    raise StoreConflict("cannot change stable send key")
                return self._as_status(row) | {"idempotent": True}
            conn.execute(
                "UPDATE requests SET state='MANUAL_SEND_AUTHORIZED',send_key=?,"
                "authorized_at=? WHERE request_id=? AND state='PREPARED'",
                (send_key, _now(), request_id),
            )
            updated = self._get(conn, request_id)
            self._audit(conn, updated, principal, "manual_send_intent_only", {
                "sendKey": send_key,
                "baseRevision": updated["base_revision"],
                "payloadSha256": updated["payload_sha256"],
            })
            return self._as_status(updated) | {"idempotent": False}

    def record_query_result(
        self, *, principal: TrustedPrincipal, request_id: str,
        evidence: Mapping[str, object], verified_by_adapter: bool,
    ) -> dict:
        """Refuse all untrusted official-receipt promotions (E2 fail-closed).

        Neither a caller-constructed ``TrustedPrincipal(role='taraz_adapter')``
        nor ``verified_by_adapter=True`` authenticates official Taraz finance
        evidence. The current peer's signed metadata lookup is *not* an
        official financial receipt. Until an independently authenticated
        authority is integrated, even well-formed legacy observations (including
        ``not_received`` and ``unknown``) cannot mutate the receipt registry.

        Existing historical rows are still integrity-checked by read methods;
        this public method never grants an operational write or resend.
        The legacy arguments remain only to reject callers predictably.
        """
        raise PermissionError(
            "official Taraz receipt authority not configured; "
            "caller verified_by_adapter and TrustedPrincipal are not evidence"
        )

    def receipt_status(
        self, *, principal: TrustedPrincipal,
        request_id: str, expected_base_revision: int,
    ) -> dict:
        """Read-only. 'unknown' is NOT 'not_received'; never perform a query."""
        _request_id(request_id)
        _version(expected_base_revision)
        with self._connect() as conn:
            conn.execute("BEGIN")
            row = self._get(conn, request_id)
            self._human_scope(principal, row, "mtr.read", _READ_ROLES)
            if row["base_revision"] != expected_base_revision:
                raise StoreConflict("stale request revision")
            return self._as_status(row)

    def request_snapshot(
        self, *, principal: TrustedPrincipal,
        request_id: str, expected_base_revision: int,
    ) -> dict:
        """Read metadata and digest without exposing a separate tenant."""
        _request_id(request_id)
        _version(expected_base_revision)
        with self._connect() as conn:
            conn.execute("BEGIN")
            row = self._get(conn, request_id)
            self._human_scope(principal, row, "mtr.read", _READ_ROLES)
            if row["base_revision"] != expected_base_revision:
                raise StoreConflict("stale request revision")
            return self._as_status(row) | {
                "orgId": row["org_id"],
                "projectId": row["project_id"],
                "payload": _parse_canonical(row["payload_json"], _MAX_PAYLOAD),
                "payloadSha256": row["payload_sha256"],
                "baseRevision": row["base_revision"],
            }

    def bind_recovery_provenance(self, issuer) -> None:
        """Bind exactly one host-owned recovery authority for this store.

        Ordinary prepare/send/read APIs remain unchanged. The raw recovery
        payload/sendKey is NEVER accessible to an unsealed TrustedPrincipal.
        """
        from mtr_host_principal_provenance import HostPrincipalProvenance
        if type(issuer) is not HostPrincipalProvenance:
            raise PermissionError("HostPrincipalProvenance issuer required")
        if self._recovery_provenance is not None:
            if self._recovery_provenance is not issuer:
                raise PermissionError("host recovery authority already bound")
            return
        self._recovery_provenance = issuer

    @contextmanager
    def _sealed_recovery(self, *, principal, token, seal, audience):
        """Keep live host account and project locks THROUGH protected reads."""
        issuer = self._recovery_provenance
        if issuer is None:
            raise PermissionError("host recovery provenance not bound")
        with issuer._service.lock, issuer._service.bridge._lock:
            verified = issuer.verify_and_consume(token, seal, audience=audience)
            if type(principal) is not TrustedPrincipal or principal != verified:
                raise PermissionError("forged or stale host principal")
            yield verified

    def recovery_snapshot(
        self, *, principal: TrustedPrincipal, request_id: str,
        expected_base_revision: int, token: str = None, seal=None,
    ) -> dict:
        """Host-injected SAME-ACTOR read of a previously authorized request.

        A fresh authenticated session may differ from the historical author
        session, but only the ORIGINAL actor with current role, original
        organization and original project grant can read the immutable
        snapshot. This method never creates a send permit or records a
        finance receipt. The older mutation/read APIs remain session-bound.
        """
        from mtr_host_principal_provenance import OUTBOX_RECOVERY
        with self._sealed_recovery(
            principal=principal, token=token, seal=seal, audience=OUTBOX_RECOVERY,
        ) as verified:
            _request_id(request_id)
            _version(expected_base_revision)
            with self._connect() as conn:
                conn.execute("BEGIN")
                row = self._get(conn, request_id)
                _scope(verified, permission="mtr.read", org_id=row["org_id"],
                       project_id=row["project_id"], roles=_READ_ROLES)
                if verified.user_id != row["actor_id"]:
                    raise PermissionError("original request actor required for recovery")
                if row["base_revision"] != expected_base_revision:
                    raise StoreConflict("stale original request revision")
                if row["state"] != "MANUAL_SEND_AUTHORIZED":
                    raise StoreConflict("no prior manual authorization to recover")
                return self._as_status(row) | {
                    "orgId": row["org_id"], "projectId": row["project_id"],
                    "actorId": row["actor_id"],
                    "originalSessionId": row["session_id"],
                    "payload": _parse_canonical(row["payload_json"], _MAX_PAYLOAD),
                    "payloadSha256": row["payload_sha256"],
                    "baseRevision": row["base_revision"],
                }

    def audit_events(
        self, *, principal: TrustedPrincipal, request_id: str,
        expected_base_revision: int,
    ) -> tuple[dict, ...]:
        """Read-only, scoped host action history; no official finance audit."""
        _request_id(request_id)
        _version(expected_base_revision)
        with self._connect() as conn:
            row = self._get(conn, request_id)
            self._human_scope(principal, row, "mtr.read", _READ_ROLES)
            if row["base_revision"] != expected_base_revision:
                raise StoreConflict("stale request revision")
            history = conn.execute(
                "SELECT seq,actor_id,session_id,kind,detail_json,occurred_at"
                " FROM audit WHERE request_id=? ORDER BY seq", (request_id,),
            ).fetchall()
            return tuple({
                "seq": event["seq"],
                "actorId": event["actor_id"],
                "sessionId": event["session_id"],
                "kind": event["kind"],
                "detail": _parse_canonical(event["detail_json"], _MAX_EVIDENCE),
                "occurredAt": event["occurred_at"],
                "receiptVerification": "UNVERIFIED",
                "officialTarazReceipt": False,
            } for event in history)

    def backup_to(self, destination: Path) -> dict:
        """Create-only, consistent SQLite backup at caller-selected safe path.

        Caller must choose an independently OS-ACL-protected backup directory.
        Recovery is deliberately off-line into a NEW store path, never an
        in-place overwrite of a live host DB.
        """
        if (not isinstance(destination, Path) or not destination.is_absolute()
                or destination.suffix != ".sqlite3" or destination == self.path):
            raise StoreError("different absolute backup .sqlite3 path required")
        _safe_ancestors(destination.parent)
        if _safe_path(destination, expected_dir=False):
            raise FileExistsError("backup destination already exists")
        fd, tmp_name = tempfile.mkstemp(
            prefix=".mtr-backup-", suffix=".sqlite3", dir=destination.parent,
        )
        os.close(fd)
        temporary = Path(tmp_name)
        try:
            with self._connect() as original:
                with closing(sqlite3.connect(temporary)) as copy:
                    original.backup(copy)
            with closing(sqlite3.connect(temporary)) as check:
                if check.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                    raise StoreError("backup integrity check failed")
                if check.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise StoreError("backup schema mismatch")
            with open(temporary, "r+b") as stream:
                os.fsync(stream.fileno())
            # Hardlink is atomic CREATE-IF-ABSENT; never overwrites a backup.
            os.link(temporary, destination)
            return {"created": True, "path": str(destination), "verified": True}
        finally:
            temporary.unlink(missing_ok=True)
