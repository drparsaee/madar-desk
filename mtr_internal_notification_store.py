"""E6 pilot: durable LOCAL SQLite inbox for internal-only policy decisions.

This adapter is deliberately NOT a MadarHost API, an authorization provider,
an authenticated Taraz adapter, a sender, or an official financial ledger.
It accepts only server-attested principals and recipients, and the narrow
output of plan_internal_notifications. Neither the dataclasses nor the
boolean attestation can authenticate an untrusted caller on their own.
The trusted host MUST construct these objects after authenticating the peer
and revalidating tenant, project, related request and field ACLs.

All inbox bodies are immutable. Read acknowledgement is an append-only event,
not an UPDATE on notices. SQLite serializes concurrent writers by BEGIN
IMMEDIATE, UNIQUE(org, recipient, event_key), and full-sync WAL transactions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from mtr_internal_notification_policy import EVENT_KINDS, ROLES, STATUS_VALUES


class NoticeContractError(ValueError):
    """An invalid plan, ID or payload was refused."""


class NoticeConflictError(NoticeContractError):
    """The same recipient+event key was reused with different immutable data."""


_VISIBLE_FIELDS = frozenset({"status", "amendment_id", "deficiency_summary", "actor_id"})
_PAYLOAD_KEYS = frozenset({
    "channel", "event_key", "recipient_id", "original_request_id",
    "event_kind", *_VISIBLE_FIELDS,
})
_PLAN_KEYS = frozenset({
    "kind", "event_key", "duplicate_event", "meaningful_change",
    "notifications", "external_deliveries", "send_or_resend_performed",
    "any_mutation_performed",
})
_MAX_NOTICES = 256
_MAX_TEXT = 2000


def _identifier(value, label):
    if (type(value) is not str or not value or value != value.strip()
            or len(value) > 180 or any(ord(character) < 32 for character in value)):
        raise NoticeContractError(f"Invalid {label}")
    return value


def _identifiers(value, label):
    if type(value) is not frozenset or any(type(x) is not str for x in value):
        raise PermissionError(f"Trusted {label} set required")
    for item in value:
        _identifier(item, label)
    return value


def _fields(value):
    fields = _identifiers(value, "visible_fields")
    if fields - _VISIBLE_FIELDS:
        raise PermissionError("Unknown or forbidden notification field")
    return fields


@dataclass(frozen=True)
class HostPrincipal:
    """Host assertion about the ACTING user, not a client-supplied identity.

    The host must authenticate/revalidate this object at every call.
    verified_event_actor_id is the source actor for a publish event, which
    may differ from the service user persisting the event.
    """

    organization_id: str
    user_id: str
    role: str
    readable_project_ids: frozenset[str]
    visible_fields: frozenset[str]
    host_verified: bool
    authenticated: bool
    can_publish: bool = False
    can_read: bool = False
    can_mark_read: bool = False
    verified_event_actor_id: str | None = None


@dataclass(frozen=True)
class HostRecipientGrant:
    """Authenticated host-side recipient entitlement for ONE incoming plan."""

    organization_id: str
    user_id: str
    role: str
    readable_project_ids: frozenset[str]
    related_request_ids: frozenset[str]
    visible_fields: frozenset[str]
    host_verified: bool
    notifications_enabled: bool


def _principal(principal, *, operation, project_id=None):
    if (type(principal) is not HostPrincipal
            or principal.host_verified is not True
            or principal.authenticated is not True
            or type(principal.role) is not str
            or principal.role not in ROLES):
        raise PermissionError("Authenticated, host-verified principal required")
    _identifier(principal.organization_id, "organization")
    _identifier(principal.user_id, "principal user")
    _identifiers(principal.readable_project_ids, "project")
    _fields(principal.visible_fields)
    if project_id is not None and _identifier(project_id, "project") not in principal.readable_project_ids:
        raise PermissionError("Project access denied")
    if operation == "publish":
        if principal.can_publish is not True or principal.role not in {"admin", "editor"}:
            raise PermissionError("Host publisher permission required")
        _identifier(principal.verified_event_actor_id, "verified event actor")
    elif operation == "read" and principal.can_read is not True:
        raise PermissionError("Host inbox reader permission required")
    elif operation == "mark" and principal.can_mark_read is not True:
        raise PermissionError("Host inbox read-ack permission required")
    return principal


def _recipient_grants(grants, *, principal, project_id):
    if type(grants) not in (list, tuple):
        raise PermissionError("Explicit host recipient grants required")
    result = {}
    for grant in grants:
        if (type(grant) is not HostRecipientGrant
                or grant.host_verified is not True
                or grant.notifications_enabled is not True
                or grant.organization_id != principal.organization_id
                or type(grant.role) is not str or grant.role not in ROLES):
            raise PermissionError("Recipient host/organization/role/consent unknown")
        _identifier(grant.user_id, "recipient")
        if grant.user_id in result:
            raise NoticeContractError("Duplicate recipient grant")
        projects = _identifiers(grant.readable_project_ids, "recipient project")
        requests = _identifiers(grant.related_request_ids, "related request")
        _fields(grant.visible_fields)
        if project_id not in projects:
            raise PermissionError("Recipient is not entitled to related project")
        result[grant.user_id] = grant
    return result


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )


def _validate_plan(plan, *, principal):
    if (type(plan) is not dict or set(plan) != _PLAN_KEYS
            or plan["kind"] != "internal_notification_plan_pilot"
            or plan["external_deliveries"] != []
            or plan["send_or_resend_performed"] is not False
            or plan["any_mutation_performed"] is not False
            or type(plan["duplicate_event"]) is not bool
            or type(plan["meaningful_change"]) is not bool):
        raise PermissionError("Untrusted or external delivery plan")
    event_key = _identifier(plan["event_key"], "event key")
    messages = plan.get("notifications")
    if type(messages) is not list or len(messages) > _MAX_NOTICES:
        raise NoticeContractError("Invalid notification batch")
    if messages and (plan["duplicate_event"] or not plan["meaningful_change"]):
        raise NoticeContractError("Duplicate or unchanged event cannot create notices")
    seen = set()
    result = []
    for message in messages:
        if type(message) is not dict or set(message) != _PAYLOAD_KEYS:
            raise NoticeContractError("Unrecognized message field, including finance reference")
        if message["channel"] != "internal_only" or message["event_key"] != event_key:
            raise PermissionError("Only same-event internal notices may be recorded")
        user = _identifier(message["recipient_id"], "recipient ID")
        if user in seen:
            raise NoticeContractError("Duplicate recipient in one plan")
        seen.add(user)
        _identifier(message["original_request_id"], "original request")
        if type(message["event_kind"]) is not str or message["event_kind"] not in EVENT_KINDS:
            raise NoticeContractError("Invalid event kind")
        for field in _VISIBLE_FIELDS:
            value = message[field]
            if value is not None:
                if type(value) is not str or len(value) > _MAX_TEXT or not value.strip():
                    raise NoticeContractError("Invalid visible notification field")
                if field == "status" and value not in STATUS_VALUES:
                    raise NoticeContractError("Unknown status")
        if message["actor_id"] is not None and message["actor_id"] != principal.verified_event_actor_id:
            raise PermissionError("Visible event actor differs from trusted host actor")
        if (message["event_kind"] != "amendment_status_changed"
                and message["amendment_id"] is not None):
            raise NoticeContractError("Amendment ID on unrelated event")
        if (message["event_kind"] != "deficiency_assigned"
                and message["deficiency_summary"] is not None):
            raise NoticeContractError("Deficiency details on unrelated event")
        result.append((user, message["original_request_id"], message))
    return result


def _checked_path(file):
    file = Path(file)
    if not file.is_absolute() or file.suffix.lower() not in (".sqlite", ".db", ".sqlite3"):
        raise NoticeContractError("An explicit absolute SQLite database path is required")
    parent = file.parent
    if not parent.exists() or not parent.is_dir():
        raise PermissionError("Database directory must already exist")
    for path in (parent, file):
        if (path.is_symlink() or getattr(path, "is_junction", lambda: False)()):
            raise PermissionError("Symlink/junction database paths are forbidden")
        if path.exists():
            info = path.lstat()
            if (getattr(info, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                raise PermissionError("Reparse-point database path denied")
    if file.exists() and not file.is_file():
        raise PermissionError("SQLite database must be a regular file")
    return file


class InternalNotificationStore:
    """A host-owned SQLite inbox; instantiate with an explicit disposable path."""

    def __init__(self, db_path):
        self.db_path = _checked_path(db_path)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS inbox_notices (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        organization_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        recipient_id TEXT NOT NULL,
                        event_key TEXT NOT NULL,
                        original_request_id TEXT NOT NULL,
                        event_kind TEXT NOT NULL,
                        event_actor_id TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL,
                        stored_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                        UNIQUE (organization_id, recipient_id, event_key)
                    );
                    CREATE INDEX IF NOT EXISTS inbox_lookup
                    ON inbox_notices (organization_id, recipient_id, project_id, id);
                    CREATE TABLE IF NOT EXISTS inbox_reads (
                        notice_id INTEGER PRIMARY KEY REFERENCES inbox_notices(id),
                        organization_id TEXT NOT NULL,
                        recipient_id TEXT NOT NULL,
                        actor_id TEXT NOT NULL,
                        read_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                    );
                    CREATE TABLE IF NOT EXISTS inbox_audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        notice_id INTEGER NOT NULL REFERENCES inbox_notices(id),
                        organization_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        recipient_id TEXT NOT NULL,
                        action TEXT NOT NULL CHECK(action IN ('insert', 'mark_read')),
                        actor_id TEXT NOT NULL,
                        event_key TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL,
                        recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                    );
                    CREATE TRIGGER IF NOT EXISTS immutable_notice_update
                    BEFORE UPDATE ON inbox_notices BEGIN SELECT RAISE(ABORT, 'immutable notice'); END;
                    CREATE TRIGGER IF NOT EXISTS immutable_notice_delete
                    BEFORE DELETE ON inbox_notices BEGIN SELECT RAISE(ABORT, 'immutable notice'); END;
                    CREATE TRIGGER IF NOT EXISTS immutable_read_update
                    BEFORE UPDATE ON inbox_reads BEGIN SELECT RAISE(ABORT, 'immutable read'); END;
                    CREATE TRIGGER IF NOT EXISTS immutable_read_delete
                    BEFORE DELETE ON inbox_reads BEGIN SELECT RAISE(ABORT, 'immutable read'); END;
                    CREATE TRIGGER IF NOT EXISTS immutable_audit_update
                    BEFORE UPDATE ON inbox_audit BEGIN SELECT RAISE(ABORT, 'immutable audit'); END;
                    CREATE TRIGGER IF NOT EXISTS immutable_audit_delete
                    BEFORE DELETE ON inbox_audit BEGIN SELECT RAISE(ABORT, 'immutable audit'); END;
                """)
                if conn.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
                    raise NoticeContractError("Unsupported inbox schema version")
                conn.execute("PRAGMA user_version = 1")
                if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("Corrupt inbox database")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @contextmanager
    def _connection(self):
        _checked_path(self.db_path)
        with closing(sqlite3.connect(
            str(self.db_path), timeout=15, isolation_level=None,
        )) as conn:
            conn.execute("PRAGMA busy_timeout = 15000")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA synchronous = FULL")
            conn.execute("PRAGMA journal_mode = WAL")
            yield conn

    def publish_plan(self, plan, *, principal, project_id, recipient_grants):
        """Append-only transaction. Same recipient+event+bytes replay is idempotent."""
        principal = _principal(principal, operation="publish", project_id=project_id)
        messages = _validate_plan(plan, principal=principal)
        grants = _recipient_grants(
            recipient_grants, principal=principal, project_id=project_id,
        )
        prepared = []
        for recipient_id, request_id, payload in messages:
            grant = grants.get(recipient_id)
            if grant is None:
                raise PermissionError("Missing server entitlement for a recipient")
            if request_id not in grant.related_request_ids:
                raise PermissionError("Recipient is not related to this request")
            for field in _VISIBLE_FIELDS:
                if payload[field] is not None and field not in grant.visible_fields:
                    raise PermissionError("Plan exposed a field outside recipient ACL")
            body = _canonical(payload)
            if len(body.encode("utf-8")) > 12_000:
                raise NoticeContractError("Notice payload exceeds size budget")
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            prepared.append((recipient_id, request_id, payload["event_kind"], body, digest))
        inserted, replayed = 0, 0
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for recipient_id, request_id, kind, body, digest in prepared:
                    existing = conn.execute(
                        """SELECT id, project_id, original_request_id, event_kind,
                                  event_actor_id, payload_json, payload_sha256
                           FROM inbox_notices
                           WHERE organization_id=? AND recipient_id=? AND event_key=?""",
                        (principal.organization_id, recipient_id, plan["event_key"]),
                    ).fetchone()
                    if existing:
                        _, old_project, old_request, old_kind, old_actor, old_body, old_hash = existing
                        if (old_project != project_id or old_request != request_id
                                or old_kind != kind or old_actor != principal.verified_event_actor_id
                                or old_body != body or old_hash != digest):
                            raise NoticeConflictError("Event key already bound to different data")
                        replayed += 1
                        continue
                    row = conn.execute(
                        """INSERT INTO inbox_notices
                           (organization_id, project_id, recipient_id, event_key,
                            original_request_id, event_kind, event_actor_id,
                            payload_json, payload_sha256)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (principal.organization_id, project_id, recipient_id,
                         plan["event_key"], request_id, kind,
                         principal.verified_event_actor_id, body, digest),
                    )
                    conn.execute(
                        """INSERT INTO inbox_audit
                           (notice_id, organization_id, project_id, recipient_id,
                            action, actor_id, event_key, payload_sha256)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (row.lastrowid, principal.organization_id, project_id,
                         recipient_id, "insert", principal.user_id,
                         plan["event_key"], digest),
                    )
                    inserted += 1
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return {
            "kind": "internal_only_persistence_result",
            "inserted": inserted, "replayed": replayed, "external_deliveries": [],
            "taraz_posting_performed": False,
        }

    def list_notifications(self, *, principal, project_id=None, recipient_id=None, limit=100):
        """Read only this user's authorized projects, re-redacting current ACL."""
        principal = _principal(principal, operation="read", project_id=project_id)
        if recipient_id is not None and recipient_id != principal.user_id:
            raise PermissionError("Reading another user's inbox is forbidden")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise NoticeContractError("Invalid read limit")
        projects = (
            (project_id,) if project_id is not None
            else tuple(sorted(principal.readable_project_ids))
        )
        if not projects:
            return []
        placeholders = ",".join("?" for _ in projects)
        with self._connection() as conn:
            rows = conn.execute(
                f"""SELECT n.id, n.organization_id, n.project_id, n.event_key,
                           n.payload_json, n.stored_at, r.read_at
                    FROM inbox_notices n LEFT JOIN inbox_reads r ON r.notice_id=n.id
                    WHERE n.organization_id=? AND n.recipient_id=?
                      AND n.project_id IN ({placeholders})
                    ORDER BY n.id DESC LIMIT ?""",
                (principal.organization_id, principal.user_id, *projects, limit),
            ).fetchall()
        notices = []
        for note_id, org, project, event, body, created, read in rows:
            payload = json.loads(body)
            public = {
                "notice_id": note_id, "organization_id": org,
                "project_id": project, "event_key": event,
                "recipient_id": principal.user_id,
                "original_request_id": payload["original_request_id"],
                "event_kind": payload["event_kind"],
                "channel": "internal_only",
                "stored_at": created, "read_at": read,
                "is_read": read is not None,
            }
            for field in _VISIBLE_FIELDS:
                public[field] = payload[field] if field in principal.visible_fields else None
            # Deliberately no receipt/document IDs, URLs, emails, SMS or ledger.
            notices.append(public)
        return notices

    def mark_read(self, notice_id, *, principal):
        """Read acknowledgement is append-only; no notice or audit UPDATE."""
        principal = _principal(principal, operation="mark")
        if type(notice_id) is not int or notice_id < 1:
            raise NoticeContractError("Invalid notice identifier")
        projects = tuple(sorted(principal.readable_project_ids))
        if not projects:
            raise PermissionError("Notice not authorized")
        placeholders = ",".join("?" for _ in projects)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                note = conn.execute(
                    f"""SELECT id, organization_id, project_id, recipient_id,
                               event_key, payload_sha256
                        FROM inbox_notices
                        WHERE id=? AND organization_id=? AND recipient_id=?
                          AND project_id IN ({placeholders})""",
                    (notice_id, principal.organization_id, principal.user_id, *projects),
                ).fetchone()
                if note is None:
                    raise PermissionError("Notice not authorized")
                first = conn.execute(
                    "SELECT 1 FROM inbox_reads WHERE notice_id=?", (notice_id,),
                ).fetchone() is None
                if first:
                    conn.execute(
                        """INSERT INTO inbox_reads
                           (notice_id, organization_id, recipient_id, actor_id)
                           VALUES (?,?,?,?)""",
                        (notice_id, principal.organization_id, principal.user_id,
                         principal.user_id),
                    )
                    conn.execute(
                        """INSERT INTO inbox_audit
                           (notice_id, organization_id, project_id, recipient_id,
                            action, actor_id, event_key, payload_sha256)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (note[0], note[1], note[2], note[3], "mark_read",
                         principal.user_id, note[4], note[5]),
                    )
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return {"notice_id": notice_id, "marked_read": first, "already_read": not first}
