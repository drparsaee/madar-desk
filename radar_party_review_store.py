"""E4 isolated human candidate-review journal, not a Taraz party interface.

The authenticated host, NOT this file, owns sessions, organization membership,
project grants, candidate row/field ACL and source provenance. These are
explicit trusted-adapter inputs. No official party is created, linked, merged,
updated or verified by this module. SQLite contains bounded, permitted preview
fields and a human's local decision only.
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
import stat

from radar_party_match_preview import FIELDS, preview_party_matches

SCHEMA_VERSION = 1
APPLICATION_ID = 0x4D545234  # MTR4, isolated metadata pilot
MAX_CASES = 2048
MAX_CANDIDATES = 64
MAX_SNAPSHOT_BYTES = 49152
MAX_AUDIT_BYTES = 4096
MAX_PAGES = 32768
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ACTIONS = frozenset({"select_candidate", "reject_all"})
_REVIEW_ROLE = "taraz_finance_reviewer"
_CAP_READ = "party_match_read"
_CAP_DECIDE = "party_match_decide"
_FIELD_CODES = frozenset({
    "missing_both", "missing_temporary", "missing_candidate",
    "equal_after_heuristic_normalization", "different", "not_authorized",
})
_KNOWN_CONFLICT = "conflicting_upstream_claimed_verified_official_ids"


class ReviewStoreError(ValueError):
    """Closed protocol or storage validation failure."""


class ReviewConflict(ReviewStoreError):
    """Stale version, duplicate event, changed snapshot or contested decision."""


@dataclass(frozen=True, slots=True)
class HostPrincipal:
    """A trusted adapter snapshot, not independently verified credentials."""
    user_id: str
    organization_id: str
    session_id: str
    role: str
    project_grants: frozenset[str]
    capabilities: frozenset[str]
    visible_fields: frozenset[str]
    allowed_candidate_ids: frozenset[str]
    authenticated: bool
    active: bool = True

    def __post_init__(self):
        for field in ("user_id", "organization_id", "session_id", "role"):
            _token(getattr(self, field), field)
        if (type(self.project_grants) is not frozenset or
                type(self.capabilities) is not frozenset or
                type(self.visible_fields) is not frozenset or
                type(self.allowed_candidate_ids) is not frozenset or
                not all(type(v) is str and _TOKEN.fullmatch(v)
                        for v in self.project_grants | self.capabilities |
                        self.allowed_candidate_ids) or
                not self.visible_fields <= frozenset(FIELDS)):
            raise ReviewStoreError("explicit immutable project/capability grants required")
        if type(self.authenticated) is not bool or type(self.active) is not bool:
            raise ReviewStoreError("explicit authentication/active booleans required")


def _token(value, label):
    if type(value) is not str or not _TOKEN.fullmatch(value):
        raise ReviewStoreError("invalid " + label)
    return value


def _digest(value, label):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise ReviewStoreError("invalid " + label)
    return value


def _time(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ReviewStoreError("timezone-aware timestamp required")
    if value.microsecond:
        raise ReviewStoreError("timestamps must have whole-second precision")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_json(value, *, depth=0, tally=None):
    if tally is None:
        tally = [0]
    tally[0] += 1
    if depth > 8 or tally[0] > 4096:
        raise ReviewStoreError("JSON structure exceeds bound")
    if value is None or type(value) is bool:
        return
    if type(value) is str and len(value) <= 2048 and not any(
        ord(c) < 32 for c in value
    ):
        return
    if type(value) is int and 0 <= value <= 1_000_000:
        return
    if type(value) is list and len(value) <= MAX_CANDIDATES:
        for item in value:
            _check_json(item, depth=depth + 1, tally=tally)
        return
    if type(value) is dict and len(value) <= 64:
        for key, item in value.items():
            if type(key) is not str or not key or len(key) > 128:
                raise ReviewStoreError("invalid JSON property")
            _check_json(item, depth=depth + 1, tally=tally)
        return
    raise ReviewStoreError("unsupported JSON value, size or number")


def _json(value, limit=MAX_SNAPSHOT_BYTES):
    _check_json(value)
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ReviewStoreError("invalid Unicode JSON") from exc
    if len(raw) > limit:
        raise ReviewStoreError("JSON too large")
    return raw.decode("utf-8")


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReviewStoreError("duplicate JSON property")
        result[key] = value
    return result


def _parse(raw, limit=MAX_SNAPSHOT_BYTES):
    if type(raw) is not str or len(raw.encode("utf-8")) > limit:
        raise ReviewStoreError("oversized or invalid stored JSON")
    try:
        value = json.loads(raw, object_pairs_hook=_no_duplicates)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ReviewStoreError("corrupt stored JSON") from exc
    if _json(value, limit) != raw:
        raise ReviewStoreError("noncanonical stored JSON")
    return value


def _hash(blob):
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _scope(principal, project, capability):
    if type(principal) is not HostPrincipal:
        raise PermissionError("trusted host Principal required")
    if not principal.authenticated or not principal.active:
        raise PermissionError("authenticated active session required")
    if principal.role != _REVIEW_ROLE or capability not in principal.capabilities:
        raise PermissionError("finance review role and capability required")
    _token(project, "project")
    if project not in principal.project_grants:
        raise PermissionError("project grant denied")
    return principal.organization_id


def _safe_path(path):
    if not isinstance(path, Path) or not path.is_absolute() or path.suffix != ".sqlite3":
        raise ReviewStoreError("explicit absolute .sqlite3 path required")
    if not path.parent.is_dir():
        raise ReviewStoreError("database parent must exist")
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise ReviewStoreError("symlink/junction path refused")
        if item.exists() and (
            getattr(item.lstat(), "st_file_attributes", 0) &
            getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise ReviewStoreError("reparse point refused")
    if path.exists() and not path.is_file():
        raise ReviewStoreError("database path is not a regular file")


def _validate_preview(preview, permitted_fields, allowed_ids):
    if type(preview) is not dict or set(preview) != {
        "kind", "organization_id", "temporary_customer_id", "candidates",
        "candidate_count", "manual_financial_review_required",
        "official_id_verified_by_engine", "automatic_link_or_creation_performed",
        "comparison_normalization",
    }:
        raise ReviewStoreError("unexpected preview schema")
    if (preview["kind"] != "synthetic_party_match_preview" or
            preview["manual_financial_review_required"] is not True or
            preview["official_id_verified_by_engine"] is not False or
            preview["automatic_link_or_creation_performed"] is not False or
            preview["comparison_normalization"] != "heuristic_not_official_verification"):
        raise ReviewStoreError("preview must be nonauthoritative/manual-only")
    if type(permitted_fields) is not tuple or not permitted_fields or (
        len(set(permitted_fields)) != len(permitted_fields)
    ) or not set(permitted_fields) <= set(FIELDS):
        raise PermissionError("explicit unambiguous visible-field grant required")
    if type(allowed_ids) is not tuple or not 1 <= len(allowed_ids) <= MAX_CANDIDATES:
        raise ReviewStoreError("bounded, nonempty authorized candidate list required")
    if (len(set(allowed_ids)) != len(allowed_ids) or
            any(type(pid) is not str or not _TOKEN.fullmatch(pid) for pid in allowed_ids)):
        raise ReviewStoreError("duplicate/invalid candidate ID")
    candidates = preview["candidates"]
    if (type(candidates) is not list or len(candidates) != len(allowed_ids) or
            type(preview["candidate_count"]) is not int or
            preview["candidate_count"] != len(candidates)):
        raise ReviewStoreError("candidate count mismatch")
    if tuple(c.get("party_id") if type(c) is dict else None
             for c in candidates) != allowed_ids:
        raise ReviewStoreError("authorized candidate enumeration mismatch")
    for candidate in candidates:
        if type(candidate) is not dict or set(candidate) != {
            "party_id", "fields", "conflicts", "requires_human_financial_decision",
        } or candidate["requires_human_financial_decision"] is not True:
            raise ReviewStoreError("malformed candidate preview")
        if type(candidate["fields"]) is not dict or set(candidate["fields"]) != set(FIELDS):
            raise ReviewStoreError("field-level preview incomplete")
        if (type(candidate["conflicts"]) is not list or
                not all(type(v) is str for v in candidate["conflicts"]) or
                len(candidate["conflicts"]) != len(set(candidate["conflicts"])) or
                any(v != _KNOWN_CONFLICT for v in candidate["conflicts"])):
            raise ReviewStoreError("unrecognized candidate conflict explanation")
        for field in FIELDS:
            details = candidate["fields"][field]
            if (type(details) is not dict or
                    type(details.get("comparison")) is not str or
                    details["comparison"] not in _FIELD_CODES):
                raise ReviewStoreError("invalid comparison details")
            if field not in permitted_fields:
                if details != {"comparison": "not_authorized"}:
                    raise PermissionError("unauthorized field in stored candidate preview")
            elif details["comparison"] == "not_authorized":
                raise ReviewStoreError("authorized field unexpectedly redacted")


class PartyReviewStore:
    """Local pending review and audited human decision, NEVER Taraz mutation."""

    def __init__(self, database_path: Path):
        self.path = database_path
        _safe_path(self.path)
        with self._connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            app = conn.execute("PRAGMA application_id").fetchone()[0]
            existing = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )}
            if version == 0:
                if existing or app:
                    raise ReviewStoreError("foreign/unversioned SQLite DB cannot be adopted")
                conn.executescript("""
                    CREATE TABLE reviews (
                      org TEXT NOT NULL, project TEXT NOT NULL,
                      review_id TEXT NOT NULL,
                      temp_customer_id TEXT NOT NULL,
                      source_ref TEXT NOT NULL, source_revision INTEGER NOT NULL,
                      source_digest TEXT NOT NULL, source_binding_confirmed INTEGER NOT NULL,
                      visible_fields_json TEXT NOT NULL,
                      candidate_ids_json TEXT NOT NULL,
                      snapshot_json TEXT NOT NULL, snapshot_sha TEXT NOT NULL,
                      status TEXT NOT NULL, version INTEGER NOT NULL,
                      decision_action TEXT, decision_candidate TEXT,
                      decision_actor TEXT, decision_session TEXT, decided_utc TEXT,
                      PRIMARY KEY(org,project,review_id)
                    );
                    CREATE TABLE audit (
                      org TEXT NOT NULL, project TEXT NOT NULL,
                      review_id TEXT NOT NULL, seq INTEGER NOT NULL,
                      event_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                      session_id TEXT NOT NULL, action TEXT NOT NULL,
                      details_json TEXT NOT NULL, input_sha TEXT NOT NULL,
                      PRIMARY KEY(org,project,review_id,seq),
                      UNIQUE(org,event_id),
                      FOREIGN KEY(org,project,review_id)
                        REFERENCES reviews(org,project,review_id)
                    );
                    CREATE TRIGGER audit_immutable_update BEFORE UPDATE ON audit
                    BEGIN SELECT RAISE(ABORT,'immutable review audit'); END;
                    CREATE TRIGGER audit_immutable_delete BEFORE DELETE ON audit
                    BEGIN SELECT RAISE(ABORT,'immutable review audit'); END;
                    PRAGMA user_version=1;
                    PRAGMA application_id=0x4D545234;
                """)
            elif version != SCHEMA_VERSION or app != APPLICATION_ID:
                raise ReviewStoreError("unsupported database version/app ID")
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )}
            triggers = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )}
            if tables != {"reviews", "audit"} or triggers != {
                "audit_immutable_update", "audit_immutable_delete"
            }:
                raise ReviewStoreError("missing or foreign SQLite schema")
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ReviewStoreError("SQLite integrity check failed")

    @contextmanager
    def _connect(self):
        _safe_path(self.path)
        conn = sqlite3.connect(str(self.path), timeout=3.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=3000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA trusted_schema=OFF")
            conn.execute("PRAGMA synchronous=FULL")
            if conn.execute("PRAGMA page_size").fetchone()[0] != 4096:
                raise ReviewStoreError("unexpected SQLite page size")
            pages = conn.execute(f"PRAGMA max_page_count={MAX_PAGES}").fetchone()[0]
            if pages > MAX_PAGES:
                raise ReviewStoreError("SQLite page limit exceeded")
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

    @staticmethod
    def _key(org, project, review_id):
        return org, _token(project, "project"), _token(review_id, "review ID")

    @staticmethod
    def _read_row(conn, key):
        row = conn.execute(
            "SELECT * FROM reviews WHERE org=? AND project=? AND review_id=?", key
        ).fetchone()
        if row is None:
            raise ReviewStoreError("scoped review not found")
        preview = _parse(row["snapshot_json"])
        candidate_ids = _parse(row["candidate_ids_json"], 8192)
        visible = _parse(row["visible_fields_json"], 1024)
        if (type(candidate_ids) is not list or type(visible) is not list or
                _hash(row["snapshot_json"]) != row["snapshot_sha"] or
                row["source_digest"] != row["snapshot_sha"] or
                row["org"] != preview.get("organization_id") or
                row["temp_customer_id"] != preview.get("temporary_customer_id") or
                type(row["source_revision"]) is not int or row["source_revision"] < 1):
            raise ReviewStoreError("review snapshot integrity mismatch")
        _validate_preview(preview, tuple(visible), tuple(candidate_ids))
        if (type(row["version"]) is not int or row["version"] not in (1, 2) or
                row["status"] not in ("PENDING_HUMAN_REVIEW", "DECISION_RECORDED") or
                row["source_binding_confirmed"] not in (0, 1)):
            raise ReviewStoreError("corrupt review state")
        audit = conn.execute(
            "SELECT * FROM audit WHERE org=? AND project=? AND review_id=? "
            "ORDER BY seq", key
        ).fetchall()
        if len(audit) != row["version"]:
            raise ReviewStoreError("stored audit/version length mismatch")
        for i, item in enumerate(audit, 1):
            details = _parse(item["details_json"], MAX_AUDIT_BYTES)
            if (item["seq"] != i or item["org"] != key[0] or
                    item["project"] != key[1] or item["review_id"] != key[2] or
                    type(details) is not dict or
                    item["actor_id"] != details.get("actorId") or
                    item["session_id"] != details.get("sessionId") or
                    item["action"] != details.get("action") or
                    _hash(_json(details, MAX_AUDIT_BYTES)) != item["input_sha"]):
                raise ReviewStoreError("audit integrity mismatch")
            if details.get("reviewId") != row["review_id"]:
                raise ReviewStoreError("audit not bound to review")
        first_details = _parse(audit[0]["details_json"], MAX_AUDIT_BYTES)
        if (audit[0]["action"] != "review_opened" or
                first_details.get("snapshotSha256") != row["snapshot_sha"] or
                first_details.get("sourceRef") != row["source_ref"] or
                first_details.get("sourceRevision") != row["source_revision"] or
                first_details.get("sourceBindingHostAsserted") is not
                    bool(row["source_binding_confirmed"])):
            raise ReviewStoreError("opening audit/source binding mismatch")
        if row["status"] == "PENDING_HUMAN_REVIEW":
            if (row["version"] != 1 or any(row[col] is not None for col in (
                "decision_action", "decision_candidate", "decision_actor",
                "decision_session", "decided_utc"
            )) or audit[0]["action"] != "review_opened"):
                raise ReviewStoreError("pending review state mismatch")
        else:
            decision_details = _parse(audit[1]["details_json"], MAX_AUDIT_BYTES)
            if (row["version"] != 2 or row["decision_action"] not in _ACTIONS or
                    audit[1]["action"] != "human_decision_recorded" or
                    row["decision_actor"] != audit[1]["actor_id"] or
                    row["decision_session"] != audit[1]["session_id"] or
                    type(row["decided_utc"]) is not str or
                    row["decided_utc"] != decision_details.get("occurredUtc") or
                    decision_details.get("decision") != row["decision_action"] or
                    decision_details.get("candidateId") != row["decision_candidate"] or
                    decision_details.get("snapshotSha256") != row["snapshot_sha"] or
                    decision_details.get("sourceDigest") != row["source_digest"] or
                    decision_details.get("sourceRef") != row["source_ref"] or
                    decision_details.get("sourceRevision") != row["source_revision"]):
                raise ReviewStoreError("decision/audit state mismatch")
            if row["decision_action"] == "select_candidate":
                if row["decision_candidate"] not in candidate_ids:
                    raise ReviewStoreError("selected party not in original snapshot")
            elif row["decision_candidate"] is not None:
                raise ReviewStoreError("rejection cannot contain candidate link")
        return row, preview, candidate_ids, visible, audit

    @staticmethod
    def _view(row, preview, candidates, visible, audit, *, replayed=False):
        return {
            "reviewId": row["review_id"], "organizationId": row["org"],
            "projectId": row["project"], "temporaryCustomerId": row["temp_customer_id"],
            "state": row["status"], "version": row["version"],
            "sourceRef": row["source_ref"], "sourceRevision": row["source_revision"],
            "sourceDigest": row["source_digest"],
            "sourceBindingHostAsserted": bool(row["source_binding_confirmed"]),
            "sourceAuthenticityVerifiedByThisModule": False,
            "snapshotSha256": row["snapshot_sha"],
            "visibleFields": list(visible),
            "authorizedCandidateIds": list(candidates),
            "preview": preview,
            "decision": None if row["status"] == "PENDING_HUMAN_REVIEW" else {
                "action": row["decision_action"],
                "selectedCandidateId": row["decision_candidate"],
                "actorId": row["decision_actor"],
                "sessionId": row["decision_session"],
                "occurredUtc": row["decided_utc"],
            },
            "audit": [
                {"eventId": e["event_id"], "actorId": e["actor_id"],
                 "sessionId": e["session_id"], "action": e["action"],
                 "details": _parse(e["details_json"], MAX_AUDIT_BYTES)}
                for e in audit
            ],
            "replayed": replayed,
            "officialTarazPartyCreated": False,
            "officialPartyLinked": False,
            "officialPartyUpdated": False,
            "automaticMergePerformed": False,
            "networkUsed": False,
        }

    @staticmethod
    def _existing_event(conn, key, event_id, fingerprint):
        event = conn.execute(
            "SELECT * FROM audit WHERE org=? AND event_id=?",
            (key[0], event_id)
        ).fetchone()
        if event is None:
            return None
        if ((event["org"], event["project"], event["review_id"]) != key or
                event["input_sha"] != fingerprint):
            raise ReviewConflict("event ID reused for different review or payload")
        return PartyReviewStore._read_row(conn, key)

    @staticmethod
    def _audit_insert(conn, key, seq, event_id, principal, action, details):
        blob = _json(details, MAX_AUDIT_BYTES)
        conn.execute(
            "INSERT INTO audit(org,project,review_id,seq,event_id,actor_id,"
            "session_id,action,details_json,input_sha) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (*key, seq, event_id, principal.user_id, principal.session_id,
             action, blob, _hash(blob))
        )

    def open_pending(self, *, principal: HostPrincipal, project_id: str,
                     review_id: str, temporary_customer: dict,
                     candidate_records: list[dict], visible_fields: tuple[str, ...],
                     authorized_candidate_ids: tuple[str, ...],
                     source_ref: str, source_revision: int,
                     expected_source_digest: str,
                     source_binding_host_confirmed: bool,
                     event_id: str, occurred_at: datetime):
        """Persist ALL authorized candidates and explanations, no decision."""
        org = _scope(principal, project_id, _CAP_READ)
        if _CAP_DECIDE not in principal.capabilities:
            raise PermissionError("finance review permission ambiguity")
        key = self._key(org, project_id, review_id)
        _token(source_ref, "source reference")
        _token(event_id, "event")
        when = _time(occurred_at)
        if type(source_revision) is not int or source_revision < 1:
            raise ReviewStoreError("positive source revision required")
        _digest(expected_source_digest, "source digest")
        if type(source_binding_host_confirmed) is not bool:
            raise ReviewStoreError("explicit host source binding claim required")
        if (type(visible_fields) is not tuple or
                type(authorized_candidate_ids) is not tuple or
                type(candidate_records) is not list or
                len(candidate_records) > MAX_CANDIDATES or
                type(temporary_customer) is not dict):
            raise ReviewStoreError("bounded trusted source snapshot required")
        if (not set(visible_fields) <= principal.visible_fields or
                not set(authorized_candidate_ids) <= principal.allowed_candidate_ids):
            raise PermissionError("host current field/candidate grants do not cover snapshot")
        scope = {
            "organization_id": org, "server_scoped": True,
            "party_read_authorized": True, "finance_review_authorized": True,
            "visible_fields": visible_fields,
        }
        preview = preview_party_matches(temporary_customer, candidate_records, scope=scope)
        _validate_preview(preview, visible_fields, authorized_candidate_ids)
        preview_blob = _json(preview)
        snapshot_sha = _hash(preview_blob)
        # A trusted host must bind this to the independently authenticated
        # catalog source. The expected digest is NOT itself proof of provenance.
        if expected_source_digest != snapshot_sha:
            raise ReviewConflict("stale or unmatched candidate-source digest")
        details = {
            "action": "review_opened", "actorId": principal.user_id,
            "sessionId": principal.session_id, "occurredUtc": when,
            "reviewId": review_id, "snapshotSha256": snapshot_sha,
            "sourceRef": source_ref, "sourceRevision": source_revision,
            "sourceBindingHostAsserted": source_binding_host_confirmed,
        }
        fingerprint = _hash(_json(details, MAX_AUDIT_BYTES))
        with self._write() as conn:
            prior = self._existing_event(conn, key, event_id, fingerprint)
            if prior is not None:
                return self._view(*prior, replayed=True)
            if conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] >= MAX_CASES:
                raise ReviewStoreError("review store quota reached")
            try:
                conn.execute(
                    "INSERT INTO reviews(org,project,review_id,temp_customer_id,"
                    "source_ref,source_revision,source_digest,source_binding_confirmed,"
                    "visible_fields_json,candidate_ids_json,snapshot_json,snapshot_sha,"
                    "status,version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (*key, preview["temporary_customer_id"], source_ref,
                     source_revision, snapshot_sha, int(source_binding_host_confirmed),
                     _json(list(visible_fields), 1024),
                     _json(list(authorized_candidate_ids), 8192),
                     preview_blob, snapshot_sha, "PENDING_HUMAN_REVIEW", 1)
                )
                self._audit_insert(conn, key, 1, event_id, principal,
                                   "review_opened", details)
            except sqlite3.IntegrityError as exc:
                raise ReviewConflict("review or event already exists") from exc
            row = self._read_row(conn, key)
            return self._view(*row)

    def read_review(self, *, principal: HostPrincipal, project_id: str,
                    review_id: str):
        org = _scope(principal, project_id, _CAP_READ)
        key = self._key(org, project_id, review_id)
        with self._connect() as conn:
            row, preview, candidates, visible, audit = self._read_row(conn, key)
            if (not set(visible) <= principal.visible_fields or
                    not set(candidates) <= principal.allowed_candidate_ids):
                raise PermissionError("field/candidate access was revoked")
            return self._view(row, preview, candidates, visible, audit)

    def list_pending(self, *, principal: HostPrincipal, project_id: str,
                     limit: int = 32):
        """Query-only index: never selects, changes or merges a candidate."""
        org = _scope(principal, project_id, _CAP_READ)
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ReviewStoreError("bounded pending query limit required")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT review_id FROM reviews WHERE org=? AND project=? "
                "AND status='PENDING_HUMAN_REVIEW' "
                "ORDER BY review_id LIMIT ?", (org, project_id, limit)
            ).fetchall()
            results = []
            for row in rows:
                valid, preview, candidates, visible, _ = self._read_row(
                    conn, self._key(org, project_id, row["review_id"]))
                if (not set(visible) <= principal.visible_fields or
                        not set(candidates) <= principal.allowed_candidate_ids):
                    continue
                results.append({
                    "reviewId": valid["review_id"],
                    "temporaryCustomerId": valid["temp_customer_id"],
                    "candidateCount": preview["candidate_count"],
                    "state": valid["status"],
                    "sourceAuthenticityVerifiedByThisModule": False,
                })
            return results

    def record_decision(self, *, principal: HostPrincipal, project_id: str,
                        review_id: str, action: str, candidate_id: str | None,
                        expected_version: int, expected_snapshot_sha256: str,
                        current_source_digest: str, current_source_ref: str,
                        current_source_revision: int,
                        source_binding_host_confirmed: bool,
                        acknowledge_conflicts: bool, event_id: str,
                        occurred_at: datetime, note: str | None = None):
        """Record explicit human selection/rejection, no Taraz side effect."""
        org = _scope(principal, project_id, _CAP_DECIDE)
        key = self._key(org, project_id, review_id)
        if type(action) is not str or action not in _ACTIONS:
            raise ReviewStoreError("unknown human decision")
        if type(expected_version) is not int or expected_version != 1:
            raise ReviewConflict("stale expected review version")
        _digest(expected_snapshot_sha256, "expected snapshot digest")
        _digest(current_source_digest, "current source digest")
        _token(current_source_ref, "current source reference")
        if type(current_source_revision) is not int or current_source_revision < 1:
            raise ReviewStoreError("invalid current source revision")
        if type(source_binding_host_confirmed) is not bool or (
            source_binding_host_confirmed is not True
        ):
            raise PermissionError("source provenance not independently host-bound")
        if type(acknowledge_conflicts) is not bool:
            raise ReviewStoreError("explicit conflict acknowledgement boolean required")
        _token(event_id, "decision event")
        if note is not None and (
            type(note) is not str or len(note) > 512 or
            any(ord(c) < 32 for c in note)
        ):
            raise ReviewStoreError("invalid optional human note")
        if action == "select_candidate":
            _token(candidate_id, "selected party")
        elif candidate_id is not None:
            raise ReviewStoreError("reject_all cannot select a party")
        when = _time(occurred_at)
        details = {
            "action": "human_decision_recorded", "actorId": principal.user_id,
            "sessionId": principal.session_id, "occurredUtc": when,
            "reviewId": review_id, "decision": action,
            "candidateId": candidate_id, "note": note,
            "expectedVersion": expected_version,
            "snapshotSha256": expected_snapshot_sha256,
            "sourceDigest": current_source_digest,
            "sourceRef": current_source_ref,
            "sourceRevision": current_source_revision,
            "acknowledgedConflicts": acknowledge_conflicts,
        }
        fingerprint = _hash(_json(details, MAX_AUDIT_BYTES))
        with self._write() as conn:
            prior = self._existing_event(conn, key, event_id, fingerprint)
            if prior is not None:
                return self._view(*prior, replayed=True)
            row, preview, ids, visible, _ = self._read_row(conn, key)
            if (not set(visible) <= principal.visible_fields or
                    not set(ids) <= principal.allowed_candidate_ids):
                raise PermissionError("field/candidate access was revoked")
            if row["status"] != "PENDING_HUMAN_REVIEW" or row["version"] != expected_version:
                raise ReviewConflict("decision already exists or version changed")
            if (row["snapshot_sha"] != expected_snapshot_sha256 or
                    row["source_digest"] != current_source_digest or
                    row["source_ref"] != current_source_ref or
                    row["source_revision"] != current_source_revision):
                raise ReviewConflict("candidate snapshot/revision changed")
            if row["source_binding_confirmed"] != 1:
                raise PermissionError("candidate source binding not confirmed by host")
            if action == "select_candidate":
                if candidate_id not in ids:
                    raise PermissionError("candidate not in authorized snapshot")
                selected = next(item for item in preview["candidates"]
                                if item["party_id"] == candidate_id)
                if selected["conflicts"] and acknowledge_conflicts is not True:
                    raise ReviewConflict("conflict explanation requires human acknowledgement")
            try:
                cur = conn.execute(
                    "UPDATE reviews SET status='DECISION_RECORDED', version=2,"
                    "decision_action=?,decision_candidate=?,decision_actor=?,"
                    "decision_session=?,decided_utc=? "
                    "WHERE org=? AND project=? AND review_id=? AND version=1 "
                    "AND snapshot_sha=? AND source_digest=? AND source_revision=?",
                    (action, candidate_id, principal.user_id, principal.session_id,
                     when, *key, expected_snapshot_sha256,
                     current_source_digest, current_source_revision)
                )
                if cur.rowcount != 1:
                    raise ReviewConflict("stale decision compare-and-swap")
                self._audit_insert(conn, key, 2, event_id, principal,
                                   "human_decision_recorded", details)
            except sqlite3.IntegrityError as exc:
                raise ReviewConflict("audit insertion failed; decision rolled back") from exc
            return self._view(*self._read_row(conn, key))
