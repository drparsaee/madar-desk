"""Synthetic, durable Radar CRM store for the isolated Madar E1 pilot.

SQLite only; no network, scheduler, emails, messages, financial ledger, Taraz
party creation or party linking. Every write is an explicit human action
with a host-supplied trusted Principal, event ID, timestamp and contact CAS
version. Every read is scoped to the same organization/project.

The host MUST authenticate Principal, validate project grants and assignable
user IDs against its authoritative user registry on every call. Passing a
Principal from an untrusted browser would defeat this pilot's ACL. The host
must supply a private, access-controlled SQLite path; this module does not
manage OS file ACLs, backups, encryption or production migrations.

Schema v1: contacts + followups + append-only events. Contact keys, event keys
and follow-up keys are all composite (org_id, project_id, local_id). Existing
records are never hard-deleted. Events include actor/time/request hash and
before/after payload; triggers forbid UPDATE/DELETE on audit rows. Events are
append-only within this API/DB schema, not tamper-proof against privileged
filesystem/SQLite schema access. SQLite BEGIN IMMEDIATE serializes writers;
CAS and event-ID checks are in the same transaction, including across
separate processes. Replays return the ORIGINAL version, never reapply.

All dates are ISO-8601 with an explicit offset; use UTC for portable displays.
All contact fields are local CRM data, never official Taraz party references.
The host must run its own retention/backup/recovery and assignment checks.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from types import MappingProxyType
from typing import Callable, Iterator, Mapping


SCHEMA_VERSION = 1
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_BIDI = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
_NOT_GIVEN = object()
_CHANNELS = frozenset(("call", "meeting", "email", "other"))


class CrmError(ValueError):
    """Stable, identifier-free error code (never echo confidential input)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _check(condition: bool, code: str) -> None:
    if not condition:
        raise CrmError(code)


def _id(value: object) -> str:
    _check(type(value) is str and _ID.fullmatch(value) is not None,
           "invalid_identifier")
    return value


def _text(value: object, maximum: int, *, optional: bool = False) -> str:
    _check(type(value) is str and len(value) <= maximum and
           (optional or bool(value.strip())), "invalid_text")
    _check(not any(ord(c) < 32 or ord(c) == 127 or c in _BIDI for c in value),
           "invalid_text")
    try:
        _check(len(value.encode("utf-8")) <= maximum * 4, "invalid_text")
    except UnicodeError as error:
        raise CrmError("invalid_text") from error
    return value


def _time(value: object) -> str:
    _check(type(value) is str and 20 <= len(value) <= 40 and "T" in value,
           "invalid_time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CrmError("invalid_time") from error
    _check(parsed.tzinfo is not None and parsed.utcoffset() is not None,
           "invalid_time")
    # SQLite compares timestamps lexically. Normalize all storage to the
    # same UTC format so an offset cannot reorder a reminder incorrectly.
    return (parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
            .replace("+00:00", "Z"))


def _limit(value: object, *, maximum: int = 100) -> int:
    _check(type(value) is int and 1 <= value <= maximum, "invalid_limit")
    return value


@dataclass(frozen=True, slots=True)
class Principal:
    """Host-verified capability, never to be constructed from client claims.

    can_manage gives scope-wide dossier access and the ability to assign
    eligible users; it does not bypass can_create/can_edit/can_delete flags.
    assignable_user_ids MUST be validated by the host for the same tenant and
    project before issuance; user IDs alone do not prove org membership.
    """

    user_id: str
    org_id: str
    project_ids: frozenset[str]
    assignable_user_ids: frozenset[str]
    can_create: bool = False
    can_edit: bool = False
    can_follow_up: bool = False
    can_delete: bool = False
    can_manage: bool = False
    active: bool = False


@dataclass(frozen=True, slots=True)
class Contact:
    contact_id: str
    org_id: str
    project_id: str
    name: str
    contact_detail: str
    owner_id: str
    assignee_id: str
    version: int
    deleted: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class FollowUp:
    followup_id: str
    contact_id: str
    assigned_to: str
    due_at: str
    subject: str
    state: str
    created_at: str
    resolved_at: str | None


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    contact_id: str
    version: int
    actor_id: str
    kind: str
    occurred_at: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class WriteResult:
    contact_id: str
    event_id: str
    version: int
    replayed: bool


def _principal(p: object, project_id: object) -> Principal:
    _check(type(p) is Principal, "permission_denied")
    _id(p.user_id)
    _id(p.org_id)
    _id(project_id)
    _check(type(p.project_ids) is frozenset and
           0 < len(p.project_ids) <= 1000 and
           all(type(x) is str and _ID.fullmatch(x) for x in p.project_ids),
           "permission_denied")
    _check(type(p.assignable_user_ids) is frozenset and
           len(p.assignable_user_ids) <= 1000 and
           all(type(x) is str and _ID.fullmatch(x)
               for x in p.assignable_user_ids), "permission_denied")
    _check(all(type(getattr(p, name)) is bool for name in (
        "can_create", "can_edit", "can_follow_up", "can_delete",
        "can_manage", "active")), "permission_denied")
    _check(p.active and project_id in p.project_ids, "permission_denied")
    return p


def _assignable(p: Principal, member: str) -> None:
    _id(member)
    _check(member == p.user_id or
           (p.can_manage and member in p.assignable_user_ids),
           "assignment_denied")


def _contact(row: sqlite3.Row) -> Contact:
    return Contact(
        row["contact_id"], row["org_id"], row["project_id"], row["name"],
        row["contact_detail"], row["owner_id"], row["assignee_id"],
        row["version"], bool(row["deleted"]), row["created_at"],
        row["updated_at"],
    )


def _viewable(p: Principal, row: sqlite3.Row) -> None:
    _check(p.can_manage or p.user_id in (row["owner_id"], row["assignee_id"]),
           "not_found")


def _freeze(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item)
                                 for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


class RadarCrmStore:
    """A small persistent SQLite repository. All API scopes come from Principal."""

    def __init__(self, database_path: str | Path) -> None:
        _check(isinstance(database_path, (str, Path)),
               "invalid_database_path")
        self.path = Path(database_path)
        _check(self.path.is_absolute() and
               self.path.suffix.lower() in (".sqlite", ".db") and
               self.path.parent.is_dir() and not self.path.is_symlink(),
               "invalid_database_path")
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS crm_contacts (
                    org_id TEXT NOT NULL, project_id TEXT NOT NULL,
                    contact_id TEXT NOT NULL, name TEXT NOT NULL,
                    contact_detail TEXT NOT NULL, owner_id TEXT NOT NULL,
                    assignee_id TEXT NOT NULL, version INTEGER NOT NULL
                      CHECK (version > 0), deleted INTEGER NOT NULL DEFAULT 0
                      CHECK (deleted IN (0,1)),
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(org_id, project_id, contact_id)
                );
                CREATE TABLE IF NOT EXISTS crm_followups (
                    org_id TEXT NOT NULL, project_id TEXT NOT NULL,
                    followup_id TEXT NOT NULL, contact_id TEXT NOT NULL,
                    assigned_to TEXT NOT NULL, due_at TEXT NOT NULL,
                    subject TEXT NOT NULL, state TEXT NOT NULL
                      CHECK (state IN ('scheduled','completed')),
                    created_at TEXT NOT NULL, resolved_at TEXT,
                    PRIMARY KEY(org_id, project_id, followup_id),
                    FOREIGN KEY(org_id, project_id, contact_id)
                      REFERENCES crm_contacts(org_id, project_id, contact_id)
                );
                CREATE TABLE IF NOT EXISTS crm_events (
                    org_id TEXT NOT NULL, project_id TEXT NOT NULL,
                    event_id TEXT NOT NULL, contact_id TEXT NOT NULL,
                    version INTEGER NOT NULL, actor_id TEXT NOT NULL,
                    kind TEXT NOT NULL, occurred_at TEXT NOT NULL,
                    request_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
                    PRIMARY KEY(org_id, project_id, event_id),
                    UNIQUE(org_id, project_id, contact_id, version),
                    FOREIGN KEY(org_id, project_id, contact_id)
                      REFERENCES crm_contacts(org_id, project_id, contact_id)
                );
                CREATE TRIGGER IF NOT EXISTS crm_events_no_update
                  BEFORE UPDATE ON crm_events BEGIN
                    SELECT RAISE(ABORT, 'crm audit is append-only');
                  END;
                CREATE TRIGGER IF NOT EXISTS crm_events_no_delete
                  BEFORE DELETE ON crm_events BEGIN
                    SELECT RAISE(ABORT, 'crm audit is append-only');
                  END;
                CREATE INDEX IF NOT EXISTS crm_due_lookup
                  ON crm_followups(org_id, project_id, assigned_to,
                                   state, due_at);
                CREATE INDEX IF NOT EXISTS crm_contact_lookup
                  ON crm_contacts(org_id, project_id, deleted, contact_id);
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(str(self.path), isolation_level=None, timeout=5.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
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
    def _row(db: sqlite3.Connection, p: Principal, project_id: str,
             contact_id: str) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM crm_contacts WHERE org_id=? AND project_id=? AND contact_id=?",
            (p.org_id, project_id, contact_id),
        ).fetchone()
        _check(row is not None, "not_found")
        _viewable(p, row)
        return row

    @staticmethod
    def _digest(kind: str, p: Principal, project_id: str, contact_id: str,
                expected_version: int | None, occurred_at: str,
                payload: dict) -> str:
        raw = json.dumps(
            [kind, p.user_id, project_id, contact_id, expected_version,
             occurred_at, payload], sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _replay(db: sqlite3.Connection, p: Principal, project_id: str,
                contact_id: str, event_id: str, digest: str) -> WriteResult | None:
        event = db.execute(
            "SELECT contact_id, version, request_hash FROM crm_events"
            " WHERE org_id=? AND project_id=? AND event_id=?",
            (p.org_id, project_id, event_id),
        ).fetchone()
        if event is None:
            return None
        _check(event["contact_id"] == contact_id and
               event["request_hash"] == digest, "event_conflict")
        return WriteResult(contact_id, event_id, event["version"], True)

    @staticmethod
    def _log(db: sqlite3.Connection, p: Principal, project_id: str,
             contact_id: str, event_id: str, version: int, kind: str,
             occurred_at: str, digest: str, payload: dict) -> WriteResult:
        db.execute(
            "INSERT INTO crm_events VALUES (?,?,?,?,?,?,?,?,?,?)",
            (p.org_id, project_id, event_id, contact_id, version, p.user_id,
             kind, occurred_at, digest,
             json.dumps(payload, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), allow_nan=False)),
        )
        return WriteResult(contact_id, event_id, version, False)

    def create_contact(self, *, principal: Principal, project_id: str,
                       contact_id: str, event_id: str, occurred_at: str,
                       name: str, contact_detail: str = "",
                       owner_id: str | None = None,
                       assignee_id: str | None = None) -> WriteResult:
        p = _principal(principal, project_id)
        _check(p.can_create, "permission_denied")
        _id(contact_id)
        _id(event_id)
        at = _time(occurred_at)
        title = _text(name, 160)
        detail = _text(contact_detail, 500, optional=True)
        owner = p.user_id if owner_id is None else _id(owner_id)
        assignee = p.user_id if assignee_id is None else _id(assignee_id)
        _assignable(p, owner)
        _assignable(p, assignee)
        data = {"name": title, "contact_detail": detail,
                "owner_id": owner, "assignee_id": assignee}
        digest = self._digest("contact_created", p, project_id, contact_id,
                              None, at, data)
        with self._write() as db:
            replay = self._replay(db, p, project_id, contact_id, event_id, digest)
            if replay:
                row = self._row(db, p, project_id, contact_id)
                return replay
            existing = db.execute(
                "SELECT 1 FROM crm_contacts WHERE org_id=? AND project_id=? AND contact_id=?",
                (p.org_id, project_id, contact_id),
            ).fetchone()
            _check(existing is None, "contact_exists")
            db.execute(
                "INSERT INTO crm_contacts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (p.org_id, project_id, contact_id, title, detail, owner,
                 assignee, 1, 0, at, at),
            )
            return self._log(db, p, project_id, contact_id, event_id, 1,
                             "contact_created", at, digest, {"after": data})

    def _mutation(self, *, principal: Principal, project_id: str,
                  contact_id: str, event_id: str, occurred_at: str,
                  expected_version: int, kind: str, request_data: dict,
                  permission: str,
                  apply: Callable[[sqlite3.Connection, sqlite3.Row, Principal, str], dict],
                  ) -> WriteResult:
        p = _principal(principal, project_id)
        _check(getattr(p, permission) is True, "permission_denied")
        _id(contact_id)
        _id(event_id)
        at = _time(occurred_at)
        _check(type(expected_version) is int and 1 <= expected_version <= 2**63-2,
               "invalid_version")
        digest = self._digest(kind, p, project_id, contact_id,
                              expected_version, at, request_data)
        with self._write() as db:
            row = self._row(db, p, project_id, contact_id)
            replay = self._replay(db, p, project_id, contact_id, event_id, digest)
            if replay:
                return replay
            _check(row["deleted"] == 0, "contact_deleted")
            _check(row["version"] == expected_version, "version_conflict")
            event_payload = apply(db, row, p, at)
            changed = db.execute(
                "UPDATE crm_contacts SET version=version+1, updated_at=?"
                " WHERE org_id=? AND project_id=? AND contact_id=?"
                " AND version=?",
                (at, p.org_id, project_id, contact_id, expected_version),
            )
            _check(changed.rowcount == 1, "version_conflict")
            return self._log(db, p, project_id, contact_id, event_id,
                             expected_version + 1, kind, at, digest,
                             event_payload)

    def update_contact(self, *, principal: Principal, project_id: str,
                       contact_id: str, event_id: str, occurred_at: str,
                       expected_version: int, name: object = _NOT_GIVEN,
                       contact_detail: object = _NOT_GIVEN,
                       owner_id: object = _NOT_GIVEN,
                       assignee_id: object = _NOT_GIVEN) -> WriteResult:
        changes: dict = {}
        for key, value in (("name", name), ("contact_detail", contact_detail),
                           ("owner_id", owner_id), ("assignee_id", assignee_id)):
            if value is _NOT_GIVEN:
                continue
            changes[key] = (_text(value, 160 if key == "name" else 500,
                                   optional=key == "contact_detail")
                            if key in ("name", "contact_detail") else _id(value))
        _check(bool(changes), "no_changes")

        def apply(db: sqlite3.Connection, row: sqlite3.Row,
                  p: Principal, at: str) -> dict:
            _check(p.can_manage or row["owner_id"] == p.user_id,
                   "permission_denied")
            if "owner_id" in changes or "assignee_id" in changes:
                _check(p.can_manage, "assignment_denied")
                for key in ("owner_id", "assignee_id"):
                    if key in changes:
                        _assignable(p, changes[key])
            before = {key: row[key] for key in changes}
            _check(any(row[key] != value for key, value in changes.items()),
                   "no_changes")
            columns = ", ".join(f"{key}=?" for key in changes)
            db.execute(
                f"UPDATE crm_contacts SET {columns} "
                "WHERE org_id=? AND project_id=? AND contact_id=?",
                (*changes.values(), p.org_id, project_id, contact_id),
            )
            return {"before": before, "after": changes}

        return self._mutation(
            principal=principal, project_id=project_id, contact_id=contact_id,
            event_id=event_id, occurred_at=occurred_at,
            expected_version=expected_version, kind="contact_updated",
            request_data=changes, permission="can_edit", apply=apply,
        )

    def record_note(self, *, principal: Principal, project_id: str,
                    contact_id: str, event_id: str, occurred_at: str,
                    expected_version: int, note: str,
                    channel: str = "other") -> WriteResult:
        note = _text(note, 1200)
        _check(type(channel) is str and channel in _CHANNELS,
               "invalid_channel")
        data = {"note": note, "channel": channel}
        return self._mutation(
            principal=principal, project_id=project_id, contact_id=contact_id,
            event_id=event_id, occurred_at=occurred_at,
            expected_version=expected_version, kind="interaction_recorded",
            request_data=data, permission="can_follow_up",
            apply=lambda db, row, p, at: data,
        )

    def schedule_followup(self, *, principal: Principal, project_id: str,
                          contact_id: str, event_id: str, occurred_at: str,
                          expected_version: int, followup_id: str,
                          due_at: str, subject: str,
                          assigned_to: str | None = None) -> WriteResult:
        fid = _id(followup_id)
        due = _time(due_at)
        title = _text(subject, 200)
        assignee = _id(assigned_to) if assigned_to is not None else None
        data = {"followup_id": fid, "due_at": due, "subject": title,
                "assigned_to": assignee}

        def apply(db: sqlite3.Connection, row: sqlite3.Row,
                  p: Principal, at: str) -> dict:
            target = assignee if assignee is not None else row["assignee_id"]
            _check(target == row["assignee_id"] or p.can_manage,
                   "assignment_denied")
            _check(target == row["assignee_id"] or
                   target in p.assignable_user_ids, "assignment_denied")
            existing = db.execute(
                "SELECT 1 FROM crm_followups WHERE org_id=? AND project_id=?"
                " AND followup_id=?",
                (p.org_id, project_id, fid),
            ).fetchone()
            _check(existing is None, "followup_exists")
            # Explicit human scheduler is either owner, the assigned worker
            # or a manager. No background schedule/run/send API exists.
            db.execute(
                "INSERT INTO crm_followups VALUES (?,?,?,?,?,?,?,?,?,?)",
                (p.org_id, project_id, fid, contact_id, target, due,
                 title, "scheduled", at, None),
            )
            return {**data, "assigned_to": target, "state": "scheduled"}

        return self._mutation(
            principal=principal, project_id=project_id, contact_id=contact_id,
            event_id=event_id, occurred_at=occurred_at,
            expected_version=expected_version, kind="followup_scheduled",
            request_data=data, permission="can_follow_up", apply=apply,
        )

    def complete_followup(self, *, principal: Principal, project_id: str,
                          contact_id: str, event_id: str, occurred_at: str,
                          expected_version: int, followup_id: str,
                          outcome: str) -> WriteResult:
        fid = _id(followup_id)
        summary = _text(outcome, 1200)
        data = {"followup_id": fid, "outcome": summary}

        def apply(db: sqlite3.Connection, row: sqlite3.Row,
                  p: Principal, at: str) -> dict:
            followup = db.execute(
                "SELECT assigned_to,state FROM crm_followups"
                " WHERE org_id=? AND project_id=? AND contact_id=?"
                " AND followup_id=?",
                (p.org_id, project_id, contact_id, fid),
            ).fetchone()
            _check(followup is not None, "not_found")
            _check(followup["assigned_to"] == p.user_id or p.can_manage,
                   "permission_denied")
            _check(followup["state"] == "scheduled", "followup_closed")
            db.execute(
                "UPDATE crm_followups SET state='completed', resolved_at=?"
                " WHERE org_id=? AND project_id=? AND followup_id=?",
                (at, p.org_id, project_id, fid),
            )
            return {**data, "state": "completed"}

        return self._mutation(
            principal=principal, project_id=project_id, contact_id=contact_id,
            event_id=event_id, occurred_at=occurred_at,
            expected_version=expected_version, kind="followup_completed",
            request_data=data, permission="can_follow_up", apply=apply,
        )

    def soft_delete_contact(self, *, principal: Principal, project_id: str,
                            contact_id: str, event_id: str,
                            occurred_at: str,
                            expected_version: int) -> WriteResult:
        def apply(db: sqlite3.Connection, row: sqlite3.Row,
                  p: Principal, at: str) -> dict:
            _check(p.can_manage or row["owner_id"] == p.user_id,
                   "permission_denied")
            pending_ids = [x["followup_id"] for x in db.execute(
                "SELECT followup_id FROM crm_followups"
                " WHERE org_id=? AND project_id=? AND contact_id=?"
                " AND state='scheduled' ORDER BY followup_id",
                (p.org_id, project_id, contact_id),
            ).fetchall()]
            db.execute(
                "UPDATE crm_contacts SET deleted=1 WHERE org_id=?"
                " AND project_id=? AND contact_id=?",
                (p.org_id, project_id, contact_id),
            )
            # Pending reminders stay in the historical table but disappear
            # from due queries because the parent is soft-deleted.
            return {"deleted": True, "suppressed_pending_followups": pending_ids}

        return self._mutation(
            principal=principal, project_id=project_id, contact_id=contact_id,
            event_id=event_id, occurred_at=occurred_at,
            expected_version=expected_version, kind="contact_soft_deleted",
            request_data={}, permission="can_delete", apply=apply,
        )

    def get_contact(self, *, principal: Principal, project_id: str,
                    contact_id: str, include_deleted: bool = False) -> Contact:
        p = _principal(principal, project_id)
        _check(type(include_deleted) is bool, "invalid_option")
        _id(contact_id)
        with self._connect() as db:
            row = self._row(db, p, project_id, contact_id)
            _check(not row["deleted"] or include_deleted, "not_found")
            return _contact(row)

    def list_contacts(self, *, principal: Principal, project_id: str,
                      after_id: str | None = None, limit: int = 50,
                      include_deleted: bool = False) -> tuple[Contact, ...]:
        p = _principal(principal, project_id)
        cap = _limit(limit)
        _check(type(include_deleted) is bool, "invalid_option")
        cursor = "" if after_id is None else _id(after_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM crm_contacts WHERE org_id=? AND project_id=?"
                " AND (?=1 OR deleted=0) AND contact_id>?"
                " AND (?=1 OR owner_id=? OR assignee_id=?)"
                " ORDER BY contact_id LIMIT ?",
                (p.org_id, project_id, int(include_deleted), cursor,
                 int(p.can_manage), p.user_id, p.user_id, cap),
            ).fetchall()
        return tuple(_contact(row) for row in rows)

    def list_history(self, *, principal: Principal, project_id: str,
                     contact_id: str, after_version: int = 0,
                     limit: int = 50) -> tuple[AuditEvent, ...]:
        p = _principal(principal, project_id)
        _id(contact_id)
        _check(type(after_version) is int and after_version >= 0,
               "invalid_version")
        cap = _limit(limit)
        with self._connect() as db:
            self._row(db, p, project_id, contact_id)
            rows = db.execute(
                "SELECT * FROM crm_events WHERE org_id=? AND project_id=?"
                " AND contact_id=? AND version>? ORDER BY version LIMIT ?",
                (p.org_id, project_id, contact_id, after_version, cap),
            ).fetchall()
        return tuple(AuditEvent(
            row["event_id"], row["contact_id"], row["version"],
            row["actor_id"], row["kind"], row["occurred_at"],
            _freeze(json.loads(row["payload_json"])),
        ) for row in rows)

    def list_due_reminders(self, *, principal: Principal, project_id: str,
                           as_of: str, limit: int = 50) -> tuple[FollowUp, ...]:
        p = _principal(principal, project_id)
        stamp = _time(as_of)
        cap = _limit(limit)
        # Restrict to the authenticated assignee. Neither owner-only nor
        # org-wide viewing creates a reminder for someone else.
        with self._connect() as db:
            rows = db.execute(
                "SELECT f.* FROM crm_followups AS f JOIN crm_contacts AS c"
                " ON c.org_id=f.org_id AND c.project_id=f.project_id"
                " AND c.contact_id=f.contact_id"
                " WHERE f.org_id=? AND f.project_id=? AND f.assigned_to=?"
                " AND f.state='scheduled' AND c.deleted=0"
                " AND (c.owner_id=? OR c.assignee_id=?)"
                " AND f.due_at<=? ORDER BY f.due_at,f.followup_id LIMIT ?",
                (p.org_id, project_id, p.user_id, p.user_id,
                 p.user_id, stamp, cap),
            ).fetchall()
        return tuple(FollowUp(
            r["followup_id"], r["contact_id"], r["assigned_to"], r["due_at"],
            r["subject"], r["state"], r["created_at"], r["resolved_at"],
        ) for r in rows)
