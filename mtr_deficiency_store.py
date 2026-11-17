"""Isolated, durable E3 deficiency metadata pilot; no official Taraz operations.

The caller supplies an explicit database path and trusted, server-derived
Principal, Baseline and FinanceReceipt snapshots. Nothing in this module
authenticates Taraz, sends a request, or reads/writes an accounting ledger.
All transitions run the existing mtr_deficiency_workflow pure validations
inside an SQLite BEGIN IMMEDIATE transaction. A manual resend is *intent only*.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import stat

from mtr_deficiency_workflow import (
    AssignedDeficiency, AuditEvent, Baseline, DeficiencyError,
    FinanceReceipt, ManualResubmissionIntent, Principal,
    ReadyForManualResubmission, ReviewCase, authorize_manual_resubmission,
    refer_deficiency, resolve_deficiency,
)

SCHEMA_VERSION = 1
APPLICATION_ID = 0x4D545245  # "MTRE": this pilot only, not an official schema
MAX_CASES = 2048
MAX_AUDIT_PER_CASE = 16
MAX_SNAPSHOT_BYTES = 32768
MAX_EVENT_BYTES = 8192
MAX_DATABASE_PAGES = 32768  # 32,768 * 4 KiB pages = 128 MiB ceiling
_READ_CAPABILITIES = frozenset({
    "finance_deficiency_refer", "deficiency_resolve",
    "finance_request_resubmit",
})
_STATES = frozenset({
    "DEFICIENCY_ASSIGNED", "CORRECTED_READY_FOR_RESUBMIT",
    "MANUAL_RESUBMISSION_INTENT_ONLY",
})


class StoreError(RuntimeError):
    """Corrupt, conflicting, stale or untrusted local metadata."""


class StoreConflict(StoreError):
    """A request/receipt/event key or optimistic version already changed."""


def _json_value(value):
    """Deterministic JSON for *known* pure-domain snapshots, never pickle."""
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise StoreError("timezone-aware timestamp required")
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {member.name: _json_value(getattr(value, member.name))
                for member in fields(value)}
    if type(value) is frozenset:
        return sorted(_json_value(item) for item in value)
    if type(value) in (tuple, list):
        return [_json_value(item) for item in value]
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise StoreError("non-string JSON key")
        return {key: _json_value(item) for key, item in value.items()}
    if type(value) in (str, bool, int) or value is None:
        return value
    raise StoreError("unsupported metadata type")


def _canonical(value, limit):
    try:
        blob = json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StoreError("invalid metadata JSON") from exc
    if len(blob) > limit:
        raise StoreError("metadata too large")
    return blob


def _unique(pairs):
    obj = {}
    for name, value in pairs:
        if name in obj:
            raise StoreError("duplicate stored JSON key")
        obj[name] = value
    return obj


def _bad_number(_):
    raise StoreError("non-finite stored JSON")


def _load_json(value, limit):
    if type(value) is not str or len(value.encode("utf-8")) > limit:
        raise StoreError("oversized metadata snapshot")
    try:
        result = json.loads(value, object_pairs_hook=_unique,
                            parse_constant=_bad_number)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StoreError("invalid stored JSON") from exc
    if _canonical(result, limit).decode("utf-8") != value:
        raise StoreError("stored JSON is not canonical")
    return result


def _hash(value, limit=MAX_EVENT_BYTES):
    return hashlib.sha256(_canonical(value, limit)).hexdigest()


def _dt(value):
    if type(value) is not str:
        raise StoreError("bad timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise StoreError("bad timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StoreError("naive stored timestamp")
    return parsed


def _expect(data, keys):
    if type(data) is not dict or set(data) != set(keys):
        raise StoreError("invalid stored snapshot fields")
    return data


def _construct(data, typ, overrides=None):
    _expect(data, (item.name for item in fields(typ)))
    kwargs = dict(data)
    if overrides:
        kwargs.update(overrides)
    # dataclasses with init=False state/flags must validate serialized values
    # without passing those fields to the constructor.
    expected_fixed = {item.name: kwargs.pop(item.name)
                      for item in fields(typ) if not item.init}
    try:
        result = typ(**kwargs)
    except (TypeError, ValueError, AttributeError) as exc:
        raise StoreError("corrupt stored domain model") from exc
    if any(getattr(result, name) != value
           for name, value in expected_fixed.items()):
        raise StoreError("stored state/flags differ from pure domain contract")
    return result


def _event(data):
    return _construct(data, AuditEvent, {
        "occurred_at": _dt(data["occurred_at"]),
        "details": tuple(tuple(pair) for pair in data["details"]),
    })


def _audit(data):
    if type(data) is not list or len(data) > MAX_AUDIT_PER_CASE:
        raise StoreError("audit history exceeds limit")
    return tuple(_event(item) for item in data)


def _baseline(data):
    return _construct(data, Baseline)


def _receipt(data):
    return _construct(data, FinanceReceipt, {
        "occurred_at": _dt(data["occurred_at"]),
    })


def _review(data):
    return _construct(data, ReviewCase, {
        "baseline": _baseline(data["baseline"]),
        "previous_receipt_ids": frozenset(data["previous_receipt_ids"]),
        "previous_send_keys": frozenset(data["previous_send_keys"]),
        "audit": _audit(data["audit"]),
    })


def _assigned(data):
    return _construct(data, AssignedDeficiency, {
        "review": _review(data["review"]),
        "receipt": _receipt(data["receipt"]),
        "deadline": _dt(data["deadline"]),
        "missing_fields": frozenset(data["missing_fields"]),
        "audit": _audit(data["audit"]),
    })


def _ready(data):
    return _construct(data, ReadyForManualResubmission, {
        "assigned": _assigned(data["assigned"]),
        "corrected_baseline": _baseline(data["corrected_baseline"]),
        "corrections": tuple(tuple(pair) for pair in data["corrections"]),
        "remaining_missing_fields": frozenset(data["remaining_missing_fields"]),
        "audit": _audit(data["audit"]),
    })


def _decode(data, state):
    if state == "DEFICIENCY_ASSIGNED":
        return _assigned(data)
    if state == "CORRECTED_READY_FOR_RESUBMIT":
        return _ready(data)
    if state == "MANUAL_RESUBMISSION_INTENT_ONLY":
        return _construct(data, ManualResubmissionIntent, {
            "ready": _ready(data["ready"]),
            "audit": _audit(data["audit"]),
        })
    raise StoreError("unknown state")


def _associated(model):
    if type(model) is AssignedDeficiency:
        return model, model.review.baseline, model.audit
    if type(model) is ReadyForManualResubmission:
        return model.assigned, model.assigned.review.baseline, model.audit
    if type(model) is ManualResubmissionIntent:
        return model.ready.assigned, model.ready.assigned.review.baseline, model.audit
    raise StoreError("unexpected deficiency model")


def _path_guard(path):
    if not isinstance(path, Path) or not path.is_absolute() or path.suffix != ".sqlite3":
        raise StoreError("explicit absolute .sqlite3 database file required")
    if not path.parent.is_dir():
        raise StoreError("database parent must already exist")
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise StoreError("symlinks and junctions are not accepted")
        if part.exists() and (getattr(part.lstat(), "st_file_attributes", 0)
                              & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise StoreError("reparse-point database path rejected")
    if path.exists() and not path.is_file():
        raise StoreError("database target is not a regular file")


def _identity(principal, org, project, capability=None):
    """Domain Principal MUST be provided by a trusted server-side adapter."""
    if type(principal) is not Principal or not principal.authenticated or not principal.active:
        raise PermissionError("trusted authenticated principal required")
    if principal.org_id != org or project not in principal.projects:
        raise PermissionError("organization/project access denied")
    if capability is not None and capability not in principal.capabilities:
        raise PermissionError("capability denied")
    if capability is None and not (principal.capabilities & _READ_CAPABILITIES):
        raise PermissionError("case read capability denied")


class DeficiencyStore:
    """Metadata-only SQLite store; every state mutation has a CAS and audit row.

    The explicit path, trusted principals, current saved baseline and verified
    receipt assertions are external responsibilities, not created by this API.
    """

    def __init__(self, database_path: Path):
        self.path = database_path
        _path_guard(self.path)
        with self._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise StoreError("unsupported SQLite schema version")
            app_id = conn.execute("PRAGMA application_id").fetchone()[0]
            existing_tables = {
                item[0] for item in conn.execute("""
                    SELECT name FROM sqlite_master WHERE type='table'
                    AND name NOT LIKE 'sqlite_%'""")
            }
            if version == 0:
                if app_id != 0 or existing_tables:
                    raise StoreError("unversioned/foreign database cannot be adopted")
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    org_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision > 0),
                    baseline_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version > 0),
                    snapshot TEXT NOT NULL,
                    snapshot_sha TEXT NOT NULL,
                    receipt_id TEXT NOT NULL,
                    send_key TEXT,
                    PRIMARY KEY (org_id,project_id,request_id,revision),
                    UNIQUE (org_id,receipt_id),
                    UNIQUE (org_id,send_key)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    org_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    seq INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    request_sha TEXT NOT NULL,
                    PRIMARY KEY (org_id,project_id,request_id,revision,seq),
                    UNIQUE (org_id,event_id),
                    FOREIGN KEY (org_id,project_id,request_id,revision)
                        REFERENCES cases(org_id,project_id,request_id,revision)
                );
                CREATE TRIGGER IF NOT EXISTS mtr_audit_no_update
                    BEFORE UPDATE ON audit_events BEGIN
                    SELECT RAISE(ABORT,'immutable audit');
                END;
                CREATE TRIGGER IF NOT EXISTS mtr_audit_no_delete
                    BEFORE DELETE ON audit_events BEGIN
                    SELECT RAISE(ABORT,'immutable audit');
                END;
                PRAGMA user_version = 1;
                PRAGMA application_id = 0x4D545245;
                """)
            elif app_id != APPLICATION_ID:
                raise StoreError("foreign SQLite application ID")
            registered_tables = {
                item[0] for item in conn.execute("""
                    SELECT name FROM sqlite_master WHERE type='table'
                    AND name NOT LIKE 'sqlite_%'""")
            }
            registered_triggers = {
                item[0] for item in conn.execute("""
                    SELECT name FROM sqlite_master WHERE type='trigger'""")
            }
            if (registered_tables != {"cases", "audit_events"} or
                    registered_triggers != {"mtr_audit_no_update",
                                            "mtr_audit_no_delete"}):
                raise StoreError("missing, altered or foreign store schema")
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise StoreError("corrupt SQLite database")

    @contextmanager
    def _connection(self):
        _path_guard(self.path)
        conn = sqlite3.connect(str(self.path), timeout=3, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=3000")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA trusted_schema=OFF")
            if conn.execute("PRAGMA page_size").fetchone()[0] != 4096:
                raise StoreError("unexpected SQLite page size")
            effective_pages = conn.execute(
                f"PRAGMA max_page_count={MAX_DATABASE_PAGES}"
            ).fetchone()[0]
            if effective_pages > MAX_DATABASE_PAGES:
                raise StoreError("SQLite database exceeded page quota")
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write(self):
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @staticmethod
    def _key(baseline):
        if type(baseline) is not Baseline:
            raise StoreError("trusted Baseline required")
        return (baseline.org_id, baseline.project_id,
                baseline.request_id, baseline.revision)

    @staticmethod
    def _load(conn, key):
        row = conn.execute("""
            SELECT * FROM cases WHERE org_id=? AND project_id=?
                AND request_id=? AND revision=?""", key).fetchone()
        if row is None:
            raise StoreError("scoped deficiency case not found")
        content = row["snapshot"]
        if not isinstance(content, str) or len(content.encode("utf8")) > MAX_SNAPSHOT_BYTES:
            raise StoreError("invalid stored case snapshot")
        if _hash(_load_json(content, MAX_SNAPSHOT_BYTES), MAX_SNAPSHOT_BYTES) != row["snapshot_sha"]:
            raise StoreError("case snapshot integrity mismatch")
        try:
            model = _decode(_load_json(content, MAX_SNAPSHOT_BYTES), row["state"])
        except (TypeError, KeyError, AttributeError, ValueError, DeficiencyError) as exc:
            raise StoreError("invalid stored domain state") from exc
        assigned, base, audit = _associated(model)
        if (DeficiencyStore._key(base) != key or base.digest != row["baseline_digest"] or
                assigned.receipt.receipt_id != row["receipt_id"] or
                model.state != row["state"] or
                type(row["version"]) is not int or row["version"] != len(audit) or
                not 1 <= len(audit) <= MAX_AUDIT_PER_CASE):
            raise StoreError("stored case identity/state mismatch")
        saved_key = model.new_send_key if type(model) is ManualResubmissionIntent else None
        if row["send_key"] != saved_key:
            raise StoreError("manual send intent and stored key disagree")
        events = conn.execute("""
            SELECT * FROM audit_events WHERE org_id=? AND project_id=?
                AND request_id=? AND revision=? ORDER BY seq""", key).fetchall()
        if len(events) != len(audit):
            raise StoreError("audit history length mismatch")
        for i, (record, event) in enumerate(zip(events, audit), 1):
            if (record["seq"] != i or record["event_id"] != event.event_id or
                    record["actor_id"] != event.actor_id or record["action"] != event.action or
                    record["event_json"] != _canonical(event, MAX_EVENT_BYTES).decode("utf8")):
                raise StoreError("stored audit mismatch")
        return row, model

    @staticmethod
    def _replay(conn, key, event_id, digest):
        found = conn.execute("SELECT * FROM audit_events WHERE org_id=? AND event_id=?",
                             (key[0], event_id)).fetchone()
        if found is None:
            return None
        if ((found["org_id"], found["project_id"], found["request_id"],
             found["revision"]) != key or found["request_sha"] != digest):
            raise StoreConflict("idempotency event reused for conflicting action")
        # Includes full audit/snapshot validation, not just an event-key match.
        return DeficiencyStore._load(conn, key)[1]

    @staticmethod
    def _append_event(conn, key, model, digest):
        _, _, audit = _associated(model)
        if not audit or len(audit) > MAX_AUDIT_PER_CASE:
            raise StoreError("audit event bound exceeded")
        event = audit[-1]
        conn.execute("""
            INSERT INTO audit_events(org_id,project_id,request_id,revision,seq,
                                     event_id,actor_id,action,event_json,request_sha)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (*key, len(audit), event.event_id, event.actor_id, event.action,
             _canonical(event, MAX_EVENT_BYTES).decode("utf8"), digest))

    @staticmethod
    def _save_snapshot(conn, key, model, expected_version):
        _, _, audit = _associated(model)
        data = _canonical(model, MAX_SNAPSHOT_BYTES)
        send_key = (model.new_send_key if type(model) is ManualResubmissionIntent
                    else None)
        cursor = conn.execute("""
            UPDATE cases SET state=?,version=?,snapshot=?,snapshot_sha=?,send_key=?
            WHERE org_id=? AND project_id=? AND request_id=? AND revision=?
                AND version=?""",
            (model.state, len(audit), data.decode("utf8"),
             hashlib.sha256(data).hexdigest(), send_key, *key, expected_version))
        if cursor.rowcount != 1:
            raise StoreConflict("stale case version")

    @staticmethod
    def _view(row, model, *, replayed=False):
        assigned, base, audit = _associated(model)
        ready = (model.ready if type(model) is ManualResubmissionIntent
                 else model if type(model) is ReadyForManualResubmission else None)
        return {
            "organizationId": base.org_id,
            "projectId": base.project_id,
            "requestId": base.request_id,
            "revision": base.revision,
            "state": model.state,
            "version": row["version"] if row else len(audit),
            "replayed": replayed,
            "assigneeId": assigned.assignee_id,
            "deadlineUtc": assigned.deadline.isoformat(),
            "reason": assigned.reason,
            "missingFields": sorted(assigned.missing_fields),
            "remainingMissingFields": sorted(
                ready.remaining_missing_fields if ready else assigned.missing_fields),
            "correctedRevision": ready.corrected_baseline.revision if ready else None,
            "correctionResult": ready.resolution_note if ready else None,
            "sendIntentKey": (model.new_send_key
                              if type(model) is ManualResubmissionIntent else None),
            "events": [
                {"eventId": event.event_id, "actorId": event.actor_id,
                 "action": event.action, "occurredUtc": event.occurred_at.isoformat()}
                for event in audit
            ],
            "transportState": "NOT_SENT_BY_THIS_MODULE",
            "peerVerified": False,
            "financeApprovalVerified": False,
            "officialDocumentId": None,
            "financialEventCreated": False,
            "postingPerformed": False,
        }

    def refer(self, case: ReviewCase, receipt: FinanceReceipt, *,
              reviewer: Principal, assignee: Principal, deadline: datetime,
              reason: str, missing_fields: frozenset[str],
              event_id: str, occurred_at: datetime):
        """Finance-authorized referral; duplicate receipt/ID cannot reassign."""
        model = refer_deficiency(
            case, receipt, reviewer=reviewer, assignee=assignee,
            deadline=deadline, reason=reason, missing_fields=missing_fields,
            event_id=event_id, occurred_at=occurred_at)
        if case.audit:
            raise StoreError("pilot expects a fresh review-case audit baseline")
        key = self._key(case.baseline)
        request_sha = _hash({
            "action": "refer", "case": case, "receipt": receipt,
            "reviewer": reviewer, "assignee": assignee, "deadline": deadline,
            "reason": reason, "missing": missing_fields, "event": event_id,
            "occurred": occurred_at,
        })
        with self._write() as conn:
            replay = self._replay(conn, key, event_id, request_sha)
            if replay is not None:
                row, replay = self._load(conn, key)
                return self._view(row, replay, replayed=True)
            if conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0] >= MAX_CASES:
                raise StoreError("database case quota exceeded")
            blob = _canonical(model, MAX_SNAPSHOT_BYTES)
            try:
                conn.execute("""
                    INSERT INTO cases(org_id,project_id,request_id,revision,
                        baseline_digest,state,version,snapshot,snapshot_sha,
                        receipt_id,send_key) VALUES(?,?,?,?,?,?,?,?,?,?,NULL)""",
                    (*key, case.baseline.digest, model.state, 1,
                     blob.decode("utf8"), hashlib.sha256(blob).hexdigest(),
                     receipt.receipt_id))
                self._append_event(conn, key, model, request_sha)
            except sqlite3.IntegrityError as exc:
                raise StoreConflict("existing case, receipt, or event") from exc
            return self._view(None, model)

    def resolve(self, *, baseline: Baseline, actor: Principal,
                saved_baseline: Baseline, corrections: dict[str, str],
                result_note: str, event_id: str, occurred_at: datetime,
                expected_version: int):
        key = self._key(baseline)
        _identity(actor, key[0], key[1], "deficiency_resolve")
        if type(expected_version) is not int or expected_version < 1:
            raise StoreConflict("invalid expected case version")
        request_sha = _hash({
            "action": "resolve", "key": key, "actor": actor,
            "saved": saved_baseline, "corrections": corrections,
            "note": result_note, "event": event_id,
            "occurred": occurred_at, "expected": expected_version,
        })
        with self._write() as conn:
            replay = self._replay(conn, key, event_id, request_sha)
            if replay is not None:
                row, replay = self._load(conn, key)
                return self._view(row, replay, replayed=True)
            row, current = self._load(conn, key)
            if row["version"] != expected_version:
                raise StoreConflict("stale case version")
            if type(current) is not AssignedDeficiency:
                raise StoreConflict("case is not awaiting assignee resolution")
            model = resolve_deficiency(
                current, actor=actor, corrections=corrections,
                result_note=result_note, saved_baseline=saved_baseline,
                event_id=event_id, occurred_at=occurred_at)
            try:
                self._save_snapshot(conn, key, model, expected_version)
                self._append_event(conn, key, model, request_sha)
            except sqlite3.IntegrityError as exc:
                raise StoreConflict("duplicate correction event") from exc
            return self._view(None, model)

    def prepare_manual_intent(self, *, baseline: Baseline, actor: Principal,
                              current_server_baseline: Baseline,
                              server_revalidated: bool,
                              explicit_manual_action: bool,
                              warning_acknowledged: bool, new_send_key: str,
                              event_id: str, occurred_at: datetime,
                              expected_version: int):
        """Store an intent *without* transmitting. Requires fresh trusted CAS."""
        key = self._key(baseline)
        _identity(actor, key[0], key[1], "finance_request_resubmit")
        if type(expected_version) is not int or expected_version < 1:
            raise StoreConflict("invalid expected case version")
        request_sha = _hash({
            "action": "intent", "key": key, "actor": actor,
            "current": current_server_baseline,
            "server_revalidated": server_revalidated,
            "explicit": explicit_manual_action, "warning": warning_acknowledged,
            "send_key": new_send_key, "event": event_id,
            "occurred": occurred_at, "expected": expected_version,
        })
        with self._write() as conn:
            replay = self._replay(conn, key, event_id, request_sha)
            if replay is not None:
                row, replay = self._load(conn, key)
                return self._view(row, replay, replayed=True)
            row, current = self._load(conn, key)
            if row["version"] != expected_version:
                raise StoreConflict("stale case version")
            if type(current) is not ReadyForManualResubmission:
                raise StoreConflict("resolution has not been saved")
            model = authorize_manual_resubmission(
                current, actor=actor, explicit_manual_action=explicit_manual_action,
                current_server_baseline=current_server_baseline,
                server_revalidated=server_revalidated,
                new_send_key=new_send_key,
                warning_acknowledged=warning_acknowledged,
                event_id=event_id, occurred_at=occurred_at)
            try:
                self._save_snapshot(conn, key, model, expected_version)
                self._append_event(conn, key, model, request_sha)
            except sqlite3.IntegrityError as exc:
                raise StoreConflict("send-key or audit event already used") from exc
            return self._view(None, model)

    def read_case(self, *, baseline: Baseline, principal: Principal):
        key = self._key(baseline)
        _identity(principal, key[0], key[1])
        with self._connection() as conn:
            row, model = self._load(conn, key)
        assigned, _, _ = _associated(model)
        if (principal.user_id not in (assigned.reviewer_id, assigned.assignee_id) and
                "finance_request_resubmit" not in principal.capabilities):
            raise PermissionError("case details restricted to assigned/reviewing users")
        return self._view(row, model)

    def query_first_status(self, *, baseline: Baseline, principal: Principal):
        """Only an honest local observation. This is NOT a Taraz receipt lookup."""
        state = self.read_case(baseline=baseline, principal=principal)
        return {
            "requestId": state["requestId"],
            "localState": state["state"],
            "peerAuthenticated": False,
            "receiptVerified": False,
            "peerDeliveryState": "UNKNOWN_REQUIRES_AUTHENTICATED_TARAZ_QUERY",
            "newSendPermitted": False,
            "postingPerformed": False,
            "officialDocumentId": None,
        }
