"""E5 independent, durable, metadata-only amendment pilot.

Pure review decisions are delegated to mtr_amendment_review_preview. This
module persists local intents ONLY; it does not query/send Taraz, post a ledger
entry, mutate an original finance request, or authenticate a client.
TrustedPrincipal and current_original MUST come from a trusted host adapter.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile

from mtr_finance_workflow_contract import AmendmentDraft
from mtr_amendment_review_preview import (
    AmendmentPreviewError, FieldConflict, RelatedSnapshot, ReviewEvent,
    ScopedAmendmentDraft, preview_create_amendment, review_field_choices,
    review_changed_baseline, preview_manual_submission,
)


class AmendmentStoreError(ValueError):
    """Invalid input or corrupted persisted state."""


class AmendmentConflict(AmendmentStoreError):
    """CAS, duplicate, stale state or identity conflict."""


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}\Z", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MAX_DOC = 32768
_MAX_EVENT = 4096
_ROLE = frozenset({"editor", "admin"})
_PERM = {
    "create": "mtr.amendment.create",
    "review": "mtr.amendment.review",
    "send": "mtr.amendment.send",
    "read": "mtr.amendment.read",
}


def _id(value, name="identifier"):
    if type(value) is not str or not _ID.fullmatch(value):
        raise AmendmentStoreError("invalid " + name)
    return value


def _key(value):
    if type(value) is not str or not _KEY.fullmatch(value):
        raise AmendmentStoreError("invalid operation key")
    return value


def _revision(value):
    if type(value) is not int or not (1 <= value <= 2**31 - 1):
        raise AmendmentStoreError("invalid row revision")
    return value


def _time(value):
    if type(value) is not str or not (10 <= len(value) <= 40):
        raise AmendmentStoreError("invalid time")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AmendmentStoreError("invalid time") from None
    if dt.utcoffset() is None:
        raise AmendmentStoreError("timezone required")
    return value


def _canonical(value, max_bytes=_MAX_DOC):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        raise AmendmentStoreError("invalid JSON metadata") from None
    if not raw or len(raw) > max_bytes:
        raise AmendmentStoreError("bounded JSON metadata required")
    return raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()


def _decode(text, digest, max_bytes=_MAX_DOC):
    if type(text) is not str or len(text.encode("utf-8")) > max_bytes:
        raise AmendmentStoreError("invalid stored metadata")
    def pairs(items):
        out = {}
        for key, val in items:
            if key in out:
                raise AmendmentStoreError("duplicate stored JSON field")
            out[key] = val
        return out
    try:
        value = json.loads(text, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               AmendmentStoreError("invalid stored number")))
    except (json.JSONDecodeError, TypeError, UnicodeError):
        raise AmendmentStoreError("corrupt stored JSON") from None
    actual, computed = _canonical(value, max_bytes)
    if actual != text or computed != digest or not _DIGEST.fullmatch(digest):
        raise AmendmentStoreError("stored metadata digest mismatch")
    return value


def _secure_path(path: Path):
    for parent in (path.parent, *path.parent.parents):
        if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
            raise PermissionError("unsafe database directory link")
        if not parent.is_dir():
            raise AmendmentStoreError("trusted directory required")
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise PermissionError("unsafe database file link")
    if os.path.lexists(path):
        s = path.lstat()
        if (not stat.S_ISREG(s.st_mode) or s.st_nlink > 1
                or getattr(s, "st_file_attributes", 0) & 0x400):
            raise PermissionError("unsafe database file")


@dataclass(frozen=True, slots=True)
class TrustedPrincipal:
    """Must be issued by the authenticated host, NEVER loaded from client JSON."""

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
            _id(getattr(self, name), name)
        for name in ("project_ids", "permissions"):
            values = getattr(self, name)
            if type(values) is not frozenset:
                raise AmendmentStoreError(name + " must be frozenset")
            for item in values:
                _id(item, name)
        if any(type(getattr(self, n)) is not bool for n in
               ("authenticated", "session_valid", "active")):
            raise AmendmentStoreError("principal booleans required")


def _authorize(p, org, project, action, *, actor=None, session=None):
    if type(p) is not TrustedPrincipal:
        raise PermissionError("trusted principal required")
    if not (p.authenticated and p.session_valid and p.active
            and p.org_id == org and project in p.project_ids
            and p.role in _ROLE and _PERM[action] in p.permissions):
        raise PermissionError("amendment scope or capability denied")
    if actor is not None and (p.user_id != actor or p.session_id != session):
        raise PermissionError("amendment owner/session mismatch")


def _preview_principal(p, org, project):
    return {"userId": p.user_id, "orgId": org, "projectIds": [project],
            "canDraft": True, "canReview": True, "canSubmit": True}


def _serialize(draft: ScopedAmendmentDraft):
    c = draft.contract
    return {
        "org": draft.org_id, "project": draft.project_id,
        "original_revision": draft.original_revision,
        "proposed": dict(c.proposed_fields), "baseline": dict(c.baseline),
        "conflict_fields": sorted(c.conflicting_fields),
        "resolutions": dict(c.resolutions),
        "previous_rejected": c.previous_rejected_amendment_id,
        "conflicts": [
            [x.field, x.baseline_value, x.proposed_value,
             x.related_amendment_id, x.related_value, x.related_revision]
            for x in draft.conflicts
        ],
        "related": [[x.amendment_id, x.revision, dict(x.proposed_fields)]
                    for x in draft.related_snapshots],
        "events": [[x.user_id, x.occurred_at, x.kind, list(x.choices),
                    list(x.source_amendment_ids)] for x in draft.review_events],
    }


def _restore(row, value):
    if type(value) is not dict or set(value) != {
        "org", "project", "original_revision", "proposed", "baseline",
        "conflict_fields", "resolutions", "previous_rejected", "conflicts",
        "related", "events",
    }:
        raise AmendmentStoreError("unsupported persisted amendment snapshot")
    try:
        contract = AmendmentDraft(
            amendment_id=row["amendment_id"],
            original_request_id=row["original_id"],
            created_by=row["actor_id"],
            proposed_fields=value["proposed"], baseline=value["baseline"],
            conflicting_fields=frozenset(value["conflict_fields"]),
            resolutions=value["resolutions"],
            previous_rejected_amendment_id=value["previous_rejected"],
        )
        draft = ScopedAmendmentDraft(
            value["org"], value["project"], value["original_revision"], contract,
            tuple(FieldConflict(*item) for item in value["conflicts"]),
            tuple(RelatedSnapshot(*item) for item in value["related"]),
            tuple(ReviewEvent(x[0], x[1], x[2],
                              tuple(tuple(v) for v in x[3]), tuple(x[4]))
                  for x in value["events"]),
        )
    except (TypeError, KeyError, ValueError, IndexError):
        raise AmendmentStoreError("invalid persisted amendment snapshot") from None
    if (draft.org_id != row["org_id"] or draft.project_id != row["project_id"]
            or type(value["conflict_fields"]) is not list
            or len(value["conflict_fields"]) != len(set(value["conflict_fields"]))
            or not set(contract.resolutions).issubset(contract.conflicting_fields)
            or len(value["events"]) > 128 or len(value["related"]) > 128):
        raise AmendmentStoreError("persisted amendment scope/shape mismatch")
    return draft


_SCHEMA = """
CREATE TABLE amendments (
    amendment_id TEXT PRIMARY KEY,
    original_id TEXT NOT NULL,
    org_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    create_key TEXT NOT NULL,
    creation_json TEXT NOT NULL,
    creation_sha TEXT NOT NULL,
    original_json TEXT NOT NULL,
    original_sha TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    snapshot_sha TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision>=1),
    state TEXT NOT NULL CHECK(state IN ('DRAFT','MANUAL_SEND_INTENT','REJECTED')),
    send_key TEXT,
    rejection_id TEXT,
    rejection_json TEXT,
    rejection_sha TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(org_id,create_key),
    UNIQUE(org_id,send_key),
    UNIQUE(org_id,rejection_id)
);
CREATE TABLE operations (
    amendment_id TEXT NOT NULL REFERENCES amendments(amendment_id),
    op_key TEXT NOT NULL,
    op_hash TEXT NOT NULL,
    result_revision INTEGER NOT NULL,
    PRIMARY KEY(amendment_id,op_key)
);
CREATE TABLE audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    amendment_id TEXT NOT NULL REFERENCES amendments(amendment_id),
    actor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    details_json TEXT NOT NULL,
    details_sha TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE INDEX amendments_related ON amendments(org_id,project_id,original_id);
CREATE TRIGGER immutable_audit_update BEFORE UPDATE ON audit
BEGIN SELECT RAISE(ABORT,'immutable audit'); END;
CREATE TRIGGER immutable_audit_delete BEFORE DELETE ON audit
BEGIN SELECT RAISE(ABORT,'immutable audit'); END;
CREATE TRIGGER immutable_original BEFORE UPDATE ON amendments
WHEN NEW.original_id!=OLD.original_id OR NEW.org_id!=OLD.org_id
 OR NEW.project_id!=OLD.project_id OR NEW.actor_id!=OLD.actor_id
 OR NEW.session_id!=OLD.session_id OR NEW.original_json!=OLD.original_json
 OR NEW.original_sha!=OLD.original_sha OR NEW.creation_json!=OLD.creation_json
 OR NEW.creation_sha!=OLD.creation_sha OR NEW.create_key!=OLD.create_key
BEGIN SELECT RAISE(ABORT,'immutable amendment identity'); END;
CREATE TRIGGER immutable_amendment_delete BEFORE DELETE ON amendments
BEGIN SELECT RAISE(ABORT,'immutable amendment record'); END;
"""


class AmendmentStore:
    def __init__(self, path: Path):
        if not isinstance(path, Path) or not path.is_absolute() or path.suffix != ".sqlite3":
            raise AmendmentStoreError("absolute .sqlite3 host path required")
        _secure_path(path)
        self.path = path
        new = not path.exists()
        with self._write(new_database=new) as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if new and version == 0:
                pending = ""
                for line in _SCHEMA.splitlines(keepends=True):
                    pending += line
                    if sqlite3.complete_statement(pending):
                        conn.execute(pending)
                        pending = ""
                if pending.strip():
                    raise AmendmentStoreError("incomplete schema statement")
                conn.execute("PRAGMA user_version=1")
                version = 1
            if version != 1:
                raise AmendmentStoreError("unknown or uninitialized amendment schema")
            for name in ("amendments", "operations", "audit"):
                record = conn.execute(
                    "SELECT type FROM sqlite_master WHERE name=?", (name,)
                ).fetchone()
                if record is None or record["type"] != "table":
                    raise AmendmentStoreError("missing store table")
            if conn.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                raise AmendmentStoreError("corrupt SQLite database")

    @contextmanager
    def _connect(self):
        _secure_path(self.path)
        conn = sqlite3.connect(self.path, timeout=8, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=8000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=FULL")
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write(self, *, new_database=False):
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @staticmethod
    def _audit(conn, row, principal, kind, detail, when):
        encoded, digest = _canonical(detail, _MAX_EVENT)
        conn.execute(
            "INSERT INTO audit(amendment_id,actor_id,session_id,kind,"
            "details_json,details_sha,occurred_at) VALUES(?,?,?,?,?,?,?)",
            (row["amendment_id"], principal.user_id, principal.session_id,
             kind, encoded, digest, _time(when)),
        )

    def _get(self, conn, amendment_id):
        row = conn.execute(
            "SELECT * FROM amendments WHERE amendment_id=?", (_id(amendment_id),)
        ).fetchone()
        if row is None:
            # Same class as an inaccessible amendment: no existence oracle.
            raise PermissionError("amendment access denied")
        result = self._validate(row)
        self._history(conn, result[0])
        return result

    @staticmethod
    def _history(conn, row):
        history = conn.execute(
            "SELECT * FROM audit WHERE amendment_id=? ORDER BY seq LIMIT 257",
            (row["amendment_id"],),
        ).fetchall()
        if len(history) > 256:
            raise AmendmentStoreError("audit history bound exceeded")
        for item in history:
            if (item["amendment_id"] != row["amendment_id"]
                    or not isinstance(_decode(
                        item["details_json"], item["details_sha"], _MAX_EVENT), dict)):
                raise AmendmentStoreError("invalid stored audit evidence")
            _id(item["actor_id"], "audit actor")
            _id(item["session_id"], "audit session")
            _id(item["kind"], "audit kind")
            _time(item["occurred_at"])
        return history

    @staticmethod
    def _validate(row):
        data = dict(row)
        for col in ("amendment_id", "original_id", "org_id", "project_id",
                    "actor_id", "session_id"):
            _id(data[col], col)
        _key(data["create_key"])
        _revision(data["revision"])
        original = _decode(data["original_json"], data["original_sha"])
        creation = _decode(data["creation_json"], data["creation_sha"])
        draft = _restore(data, _decode(data["snapshot_json"], data["snapshot_sha"]))
        if (not isinstance(original, dict)
                or (original.get("requestId"), original.get("orgId"),
                    original.get("projectId")) !=
                   (data["original_id"], data["org_id"], data["project_id"])
                or not isinstance(creation, dict)
                or creation.get("amendmentId") != data["amendment_id"]
                or creation.get("createKey") != data["create_key"]):
            raise AmendmentStoreError("corrupted immutable original or creation record")
        if data["state"] not in ("DRAFT", "MANUAL_SEND_INTENT", "REJECTED"):
            raise AmendmentStoreError("invalid amendment state")
        if data["state"] == "DRAFT" and any(
                data[key] is not None for key in
                ("send_key", "rejection_id", "rejection_json", "rejection_sha")):
            raise AmendmentStoreError("premature send/rejection on draft")
        if data["state"] != "DRAFT":
            _key(data["send_key"])
        if data["state"] == "REJECTED":
            _key(data["rejection_id"])
            proof = _decode(data["rejection_json"], data["rejection_sha"])
            if (type(proof) is not dict or proof.get("status") != "rejected"
                    or proof.get("verifiedTarazSource") is not True
                    or proof.get("amendmentId") != data["amendment_id"]
                    or proof.get("originalRequestId") != data["original_id"]
                    or proof.get("orgId") != data["org_id"]
                    or proof.get("projectId") != data["project_id"]):
                raise AmendmentStoreError("invalid rejection evidence")
        elif any(data[k] is not None for k in (
                "rejection_id", "rejection_json", "rejection_sha")):
            raise AmendmentStoreError("rejection fields on active amendment")
        _time(data["created_at"])
        return data, original, draft

    def _related(self, conn, org, project, original_id, *,
                 exclude=None, for_preview=False):
        rows = conn.execute(
            "SELECT * FROM amendments WHERE org_id=? AND project_id=?"
            " AND original_id=? ORDER BY amendment_id LIMIT 129",
            (org, project, original_id),
        ).fetchall()
        if len(rows) > 128:
            raise AmendmentStoreError("related amendment snapshot exceeds bound")
        result = []
        for row in rows:
            data, _, draft = self._validate(row)
            if data["amendment_id"] == exclude:
                continue
            # Legacy REJECTED rows contain only self-asserted adapter proof.
            # Treat them as open in policy previews (conservative conflicts)
            # and disclose their unverified provenance in public related reads.
            status = (("pending" if for_preview else "rejection_unverified")
                      if data["state"] == "REJECTED"
                      else {"DRAFT": "draft", "MANUAL_SEND_INTENT": "pending"}[
                          data["state"]])
            result.append({
                "amendmentId": data["amendment_id"],
                "originalRequestId": data["original_id"],
                "orgId": data["org_id"], "projectId": data["project_id"],
                "revision": "r" + str(data["revision"]),
                "status": status,
                "proposedFields": dict(draft.contract.proposed_fields),
            })
        return result

    @staticmethod
    def _result(data, draft, *, idempotent=False):
        return {
            "amendmentId": data["amendment_id"],
            "originalRequestId": data["original_id"],
            "rowRevision": data["revision"],
            "state": ("REJECTION_UNVERIFIED"
                      if data["state"] == "REJECTED" else data["state"]),
            "unresolvedFields": sorted(
                draft.contract.conflicting_fields -
                set(draft.contract.resolutions)),
            "sendKey": data["send_key"],
            "previousRejectedAmendmentId": (
                draft.contract.previous_rejected_amendment_id),
            "sentToTaraz": False,
            "officialFinancePosted": False,
            "officialTarazRejectionVerified": False,
            "idempotent": idempotent,
        }

    @staticmethod
    def _replay(conn, row, key, fingerprint, expected_previous_revision):
        old = conn.execute(
            "SELECT op_hash,result_revision FROM operations"
            " WHERE amendment_id=? AND op_key=?",
            (row["amendment_id"], key),
        ).fetchone()
        if old is None:
            return False
        if (old["op_hash"] != fingerprint
                or old["result_revision"] != row["revision"]
                or old["result_revision"] != expected_previous_revision + 1):
            raise AmendmentConflict("conflicting or stale operation replay")
        return True

    def create_amendment(
        self, *, principal: TrustedPrincipal, original: dict,
        amendment_id: str, proposed_fields: dict, create_key: str,
        acknowledged_open: bool, acknowledged_duplicate: bool,
        acknowledged_at: str | None = None,
        previous_rejected_amendment_id: str | None = None,
    ):
        """Create independently; read existing related items inside transaction."""
        _id(amendment_id, "amendment ID")
        _key(create_key)
        if type(original) is not dict:
            raise AmendmentStoreError("original snapshot must be trusted dict")
        org = _id(original.get("orgId"))
        project = _id(original.get("projectId"))
        _authorize(principal, org, project, "create")
        if type(acknowledged_open) is not bool or type(acknowledged_duplicate) is not bool:
            raise AmendmentStoreError("independent acknowledgment booleans required")
        creation = {
            "amendmentId": amendment_id, "original": original,
            "proposedFields": proposed_fields, "createKey": create_key,
            "ackOpen": acknowledged_open, "ackDuplicate": acknowledged_duplicate,
            "ackAt": acknowledged_at, "previousRejected": previous_rejected_amendment_id,
        }
        creation_json, creation_sha = _canonical(creation)
        original_json, original_sha = _canonical(original)
        with self._write() as conn:
            existing = conn.execute(
                "SELECT * FROM amendments WHERE amendment_id=? OR"
                " (org_id=? AND create_key=?)",
                (amendment_id, org, create_key),
            ).fetchall()
            if existing:
                if len(existing) != 1:
                    raise AmendmentConflict("amendment ID/create key collision")
                data, _, draft = self._validate(existing[0])
                if (data["amendment_id"] != amendment_id
                        or data["creation_sha"] != creation_sha
                        or data["creation_json"] != creation_json
                        or data["actor_id"] != principal.user_id
                        or data["session_id"] != principal.session_id
                        or data["org_id"] != org or data["project_id"] != project):
                    raise AmendmentConflict("conflicting amendment creation replay")
                return self._result(data, draft, idempotent=True)
            related = self._related(
                conn, org, project, _id(original.get("requestId")),
                for_preview=True)
            preview = preview_create_amendment(
                principal=_preview_principal(principal, org, project),
                original=original, amendment_id=amendment_id,
                proposed_fields=proposed_fields, related_amendments=related,
                acknowledged_open=acknowledged_open,
                acknowledged_duplicate=acknowledged_duplicate,
                acknowledged_at=acknowledged_at,
                previous_rejected_amendment_id=previous_rejected_amendment_id,
            )
            if not preview.allowed:
                raise AmendmentConflict(",".join(preview.blocked_by))
            snap_json, snap_sha = _canonical(_serialize(preview.draft))
            now = _time(acknowledged_at) if acknowledged_at is not None else (
                datetime.now().astimezone().isoformat())
            conn.execute(
                "INSERT INTO amendments(amendment_id,original_id,org_id,project_id,"
                "actor_id,session_id,create_key,creation_json,creation_sha,"
                "original_json,original_sha,snapshot_json,snapshot_sha,revision,"
                "state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,'DRAFT',?)",
                (amendment_id, original["requestId"], org, project,
                 principal.user_id, principal.session_id, create_key,
                 creation_json, creation_sha, original_json, original_sha,
                 snap_json, snap_sha, now),
            )
            row, _, draft = self._get(conn, amendment_id)
            self._audit(conn, row, principal, "amendment_created", {
                "openAcknowledged": bool(preview.open_amendment_ids),
                "duplicateAcknowledged": bool(preview.possible_duplicate_ids),
                "openIds": list(preview.open_amendment_ids),
                "duplicateIds": list(preview.possible_duplicate_ids),
            }, now)
            for event in preview.draft.review_events:
                self._audit(conn, row, principal, event.kind, {
                    "relatedIds": list(event.source_amendment_ids),
                }, event.occurred_at)
            return self._result(row, draft)

    def choose_fields(
        self, *, principal: TrustedPrincipal, amendment_id: str,
        expected_row_revision: int, chosen_values: dict,
        operation_key: str, occurred_at: str,
    ):
        """Resolve only flagged conflicts via existing pure review_field_choices."""
        _revision(expected_row_revision)
        _key(operation_key)
        _time(occurred_at)
        encoded, fingerprint = _canonical({
            "action": "choose", "values": chosen_values,
            "occurredAt": occurred_at, "actor": principal.user_id,
            "session": principal.session_id,
        }, _MAX_EVENT)
        with self._write() as conn:
            row, _, draft = self._get(conn, amendment_id)
            _authorize(principal, row["org_id"], row["project_id"], "review",
                       actor=row["actor_id"], session=row["session_id"])
            if self._replay(conn, row, operation_key, fingerprint,
                            expected_row_revision):
                return self._result(row, draft, idempotent=True)
            if row["state"] != "DRAFT" or row["revision"] != expected_row_revision:
                raise AmendmentConflict("stale or noneditable amendment")
            changed = review_field_choices(
                draft, principal=_preview_principal(
                    principal, row["org_id"], row["project_id"]),
                chosen_values=chosen_values, occurred_at=occurred_at,
            )
            return self._advance(
                conn, row, changed, principal, operation_key, fingerprint,
                "conflict_choice", {"fields": sorted(chosen_values)}, occurred_at,
            )

    def re_review_baseline(
        self, *, principal: TrustedPrincipal, amendment_id: str,
        expected_row_revision: int, current_original: dict,
        chosen_values: dict, acknowledged_dependency_fields: list[str],
        acknowledged_revision_change: bool, operation_key: str,
        occurred_at: str,
    ):
        """Reopen only affected fields/dependencies using the pure re-review."""
        _revision(expected_row_revision)
        _key(operation_key)
        _time(occurred_at)
        _, fingerprint = _canonical({
            "action": "rereview", "original": current_original,
            "choices": chosen_values,
            "dependencies": acknowledged_dependency_fields,
            "revisionAck": acknowledged_revision_change,
            "actor": principal.user_id, "session": principal.session_id,
            "occurredAt": occurred_at,
        })
        with self._write() as conn:
            row, _, draft = self._get(conn, amendment_id)
            _authorize(principal, row["org_id"], row["project_id"], "review",
                       actor=row["actor_id"], session=row["session_id"])
            if self._replay(conn, row, operation_key, fingerprint,
                            expected_row_revision):
                return self._result(row, draft, idempotent=True)
            if row["revision"] != expected_row_revision or row["state"] != "DRAFT":
                raise AmendmentConflict("stale or noneditable amendment")
            current_related = self._related(
                conn, row["org_id"], row["project_id"], row["original_id"],
                exclude=amendment_id, for_preview=True,
            )
            changed = review_changed_baseline(
                draft, principal=_preview_principal(
                    principal, row["org_id"], row["project_id"]),
                current_original=current_original,
                current_related_amendments=current_related,
                chosen_values=chosen_values,
                acknowledged_dependency_fields=acknowledged_dependency_fields,
                acknowledged_revision_change=acknowledged_revision_change,
                occurred_at=occurred_at,
            )
            return self._advance(
                conn, row, changed, principal, operation_key, fingerprint,
                "baseline_rereview",
                {"fieldChoices": sorted(chosen_values),
                 "dependencies": sorted(acknowledged_dependency_fields)},
                occurred_at,
            )

    def _advance(self, conn, row, draft, principal, key, fingerprint, kind,
                 detail, occurred_at):
        payload, digest = _canonical(_serialize(draft))
        new_rev = row["revision"] + 1
        conn.execute(
            "UPDATE amendments SET snapshot_json=?,snapshot_sha=?,revision=?"
            " WHERE amendment_id=? AND state='DRAFT' AND revision=?",
            (payload, digest, new_rev, row["amendment_id"], row["revision"]),
        )
        if conn.execute("SELECT changes()").fetchone()[0] != 1:
            raise AmendmentConflict("lost amendment CAS race")
        conn.execute(
            "INSERT INTO operations(amendment_id,op_key,op_hash,result_revision)"
            " VALUES(?,?,?,?)",
            (row["amendment_id"], key, fingerprint, new_rev),
        )
        updated, _, result = self._get(conn, row["amendment_id"])
        self._audit(conn, updated, principal, kind, detail, occurred_at)
        return self._result(updated, result)

    def manual_send_intent(
        self, *, principal: TrustedPrincipal, amendment_id: str,
        expected_row_revision: int, current_original: dict,
        send_key: str, explicit_manual_action: bool,
        current_server_verified: bool, occurred_at: str,
    ):
        """One manual intent after fresh original/related comparisons; NEVER send."""
        _revision(expected_row_revision)
        _key(send_key)
        _time(occurred_at)
        if explicit_manual_action is not True or current_server_verified is not True:
            raise PermissionError("manual action and trusted current snapshot required")
        with self._write() as conn:
            row, _, draft = self._get(conn, amendment_id)
            _authorize(principal, row["org_id"], row["project_id"], "send",
                       actor=row["actor_id"], session=row["session_id"])
            if row["revision"] != expected_row_revision:
                raise AmendmentConflict("stale amendment revision")
            if row["state"] not in ("DRAFT", "MANUAL_SEND_INTENT"):
                raise AmendmentConflict("amendment not available for manual send")
            related = self._related(
                conn, row["org_id"], row["project_id"], row["original_id"],
                exclude=amendment_id, for_preview=True,
            )
            preview = preview_manual_submission(
                draft, principal=_preview_principal(
                    principal, row["org_id"], row["project_id"]),
                current_original=current_original,
                current_related_amendments=related,
                explicit_manual_action=True,
            )
            if not preview.allowed:
                raise AmendmentConflict(",".join(preview.blocked_by))
            if row["state"] == "MANUAL_SEND_INTENT":
                if row["send_key"] != send_key:
                    raise AmendmentConflict("cannot replace existing manual send intent")
                return self._result(row, draft, idempotent=True)
            collision = conn.execute(
                "SELECT amendment_id FROM amendments WHERE org_id=? AND send_key=?",
                (row["org_id"], send_key),
            ).fetchone()
            if collision is not None:
                raise AmendmentConflict("send key already used")
            conn.execute(
                "UPDATE amendments SET state='MANUAL_SEND_INTENT',send_key=?,"
                "revision=revision+1 WHERE amendment_id=? AND revision=?",
                (send_key, amendment_id, expected_row_revision),
            )
            updated, _, final = self._get(conn, amendment_id)
            self._audit(conn, updated, principal, "manual_send_intent_only", {
                "sendKey": send_key, "originalRevision": draft.original_revision,
                "previewAllowed": True, "transmitted": False,
            }, occurred_at)
            return self._result(updated, final)

    def record_rejection(
        self, *, adapter: TrustedPrincipal, amendment_id: str,
        expected_row_revision: int, observation_id: str, receipt: dict,
        verified_by_adapter: bool, occurred_at: str,
    ):
        """Reject all official-rejection claims until host Taraz attestation exists.

        TrustedPrincipal is a constructible data object, and neither a caller's
        verified_by_adapter boolean nor receipt.verifiedTarazSource authenticates
        Taraz. Keep this API shape for callers, but make no state/audit writes.
        Historical REJECTED rows remain readable through the existing store.
        """
        raise PermissionError("official Taraz rejection verification unavailable")

    def get_amendment(self, *, principal: TrustedPrincipal, amendment_id: str):
        with self._connect() as conn:
            conn.execute("BEGIN")
            row, original, draft = self._get(conn, amendment_id)
            _authorize(principal, row["org_id"], row["project_id"], "read",
                       actor=row["actor_id"], session=row["session_id"])
            return self._result(row, draft) | {
                "original": original,
                "proposedFields": dict(draft.contract.proposed_fields),
                "originalRevisionAtReview": draft.original_revision,
                "auditCount": conn.execute(
                    "SELECT COUNT(*) FROM audit WHERE amendment_id=?",
                    (amendment_id,),
                ).fetchone()[0],
            }

    def audit_events(self, *, principal: TrustedPrincipal, amendment_id: str):
        with self._connect() as conn:
            conn.execute("BEGIN")
            row, _, _ = self._get(conn, amendment_id)
            _authorize(principal, row["org_id"], row["project_id"], "read",
                       actor=row["actor_id"], session=row["session_id"])
            events = self._history(conn, row)
            return tuple({
                "seq": x["seq"], "actorId": x["actor_id"],
                "action": ("historical_rejection_unverified"
                           if x["kind"] == "verified_rejection_observed"
                           else x["kind"]),
                "details": ({
                    "historicalStoredEvent": True,
                    "officialTarazRejectionVerified": False,
                } if x["kind"] == "verified_rejection_observed"
                    else _decode(x["details_json"], x["details_sha"], _MAX_EVENT)),
                "occurredAt": x["occurred_at"],
            } for x in events)

    def related_amendments(self, *, principal: TrustedPrincipal,
                           org_id: str, project_id: str, original_id: str):
        _id(original_id)
        _authorize(principal, org_id, project_id, "read")
        with self._connect() as conn:
            conn.execute("BEGIN")
            return tuple(self._related(conn, org_id, project_id, original_id))

    def backup_to(self, destination: Path):
        """Create-only verified SQLite snapshot; no in-place restore or upload.

        The host must separately authorize destination storage/retention and
        stop writers for any future independently reviewed recovery cutover.
        """
        if (not isinstance(destination, Path) or not destination.is_absolute()
                or destination.suffix != ".sqlite3"
                or destination == self.path):
            raise AmendmentStoreError("new absolute SQLite backup path required")
        _secure_path(destination)
        if os.path.lexists(destination):
            raise FileExistsError("backup destination already exists")
        fd, filename = tempfile.mkstemp(
            prefix=".mtr-e5-backup-", suffix=".sqlite3", dir=destination.parent,
        )
        os.close(fd)
        temporary = Path(filename)
        try:
            with self._connect() as original:
                with closing(sqlite3.connect(temporary)) as copy:
                    original.backup(copy)
            with closing(sqlite3.connect(temporary)) as check:
                if check.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                    raise AmendmentStoreError("backup SQLite quick_check failed")
                if check.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise AmendmentStoreError("backup schema not supported")
            with open(temporary, "r+b") as stream:
                os.fsync(stream.fileno())
            # Atomic CREATE-ONLY publication, including on Windows NTFS.
            os.link(temporary, destination)
            return {"created": True, "verified": True, "path": str(destination)}
        finally:
            temporary.unlink(missing_ok=True)
