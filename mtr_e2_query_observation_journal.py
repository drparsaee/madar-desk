"""Host-owned append-only E2 signed-query *metadata* evidence.

The host must call this with a freshly authenticated principal, both directional
secrets and the actual signed wires, after peer transport. A digest or a
caller-provided "verified" flag alone is never evidence. This journal does not
perform transport, issue finance receipts or grant a new dispatch attempt.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import stat

from mtr_e2_dispatch_gate import OneShotDispatchGate
from mtr_host_request_store import HostRequestStore, TrustedPrincipal
from mtr_peer_envelope import (
    verify_peer_receipt, verify_receipt_query, verify_request,
)


class QueryJournalError(ValueError):
    """Invalid or corrupt host-owned query observation store."""


class QueryJournalConflict(QueryJournalError):
    """A query ID is already committed with contradictory evidence."""


_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_GENESIS = "0" * 64
_MAX_RECORDS = 10_000

_TABLE = """CREATE TABLE query_observations (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id TEXT NOT NULL UNIQUE CHECK(length(query_id)=32),
    request_id TEXT NOT NULL CHECK(length(request_id)=32),
    original_payload_sha256 TEXT NOT NULL CHECK(length(original_payload_sha256)=64),
    original_envelope_sha256 TEXT NOT NULL CHECK(length(original_envelope_sha256)=64),
    query_payload_sha256 TEXT NOT NULL CHECK(length(query_payload_sha256)=64),
    query_envelope_sha256 TEXT NOT NULL CHECK(length(query_envelope_sha256)=64),
    peer_payload_sha256 TEXT NOT NULL CHECK(length(peer_payload_sha256)=64),
    peer_envelope_sha256 TEXT NOT NULL CHECK(length(peer_envelope_sha256)=64),
    org_id TEXT NOT NULL CHECK(length(org_id) BETWEEN 1 AND 180),
    project_id TEXT NOT NULL CHECK(length(project_id) BETWEEN 1 AND 180),
    actor_id TEXT NOT NULL CHECK(length(actor_id) BETWEEN 1 AND 180),
    actor_role TEXT NOT NULL CHECK(actor_role IN ('admin','editor')),
    session_id TEXT NOT NULL CHECK(length(session_id) BETWEEN 1 AND 180),
    sender_id TEXT NOT NULL CHECK(length(sender_id) BETWEEN 1 AND 128),
    sender_key_id TEXT NOT NULL CHECK(length(sender_key_id) BETWEEN 1 AND 128),
    peer_id TEXT NOT NULL CHECK(length(peer_id) BETWEEN 1 AND 128),
    peer_key_id TEXT NOT NULL CHECK(length(peer_key_id) BETWEEN 1 AND 128),
    observed_state TEXT NOT NULL CHECK(observed_state IN ('received','unknown')),
    recorded_utc TEXT NOT NULL CHECK(length(recorded_utc) BETWEEN 20 AND 40),
    previous_sha256 TEXT NOT NULL CHECK(length(previous_sha256)=64),
    event_sha256 TEXT NOT NULL CHECK(length(event_sha256)=64)
)"""
_SCHEMA = {
    "query_observations": ("table", _TABLE),
    "query_observations_request": ("index",
        "CREATE INDEX query_observations_request ON query_observations(request_id,seq)"),
    "immutable_query_observation_update": ("trigger",
        """CREATE TRIGGER immutable_query_observation_update
           BEFORE UPDATE ON query_observations
           BEGIN SELECT RAISE(ABORT, 'immutable query evidence'); END"""),
    "immutable_query_observation_delete": ("trigger",
        """CREATE TRIGGER immutable_query_observation_delete
           BEFORE DELETE ON query_observations
           BEGIN SELECT RAISE(ABORT, 'immutable query evidence'); END"""),
}
_FIELDS = (
    "query_id", "request_id", "original_payload_sha256",
    "original_envelope_sha256", "query_payload_sha256",
    "query_envelope_sha256", "peer_payload_sha256", "peer_envelope_sha256",
    "org_id", "project_id", "actor_id", "actor_role", "session_id",
    "sender_id", "sender_key_id", "peer_id", "peer_key_id",
    "observed_state", "recorded_utc", "previous_sha256",
)


def _path(path):
    if not isinstance(path, Path) or path.suffix not in (".sqlite3", ".db"):
        raise QueryJournalError("explicit SQLite Path required")
    # Reject special files, links and Windows junctions along the whole path.
    for ancestor in (path.parent, *path.parent.parents):
        if ancestor.is_symlink() or getattr(ancestor, "is_junction", lambda: False)():
            raise QueryJournalError("linked parent forbidden")
        try:
            mode = ancestor.lstat().st_mode
        except FileNotFoundError as exc:
            raise QueryJournalError("existing parent required") from exc
        if not stat.S_ISDIR(mode):
            raise QueryJournalError("non-directory parent")
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise QueryJournalError("linked database forbidden")
    if path.exists():
        entry = path.lstat()
        if not stat.S_ISREG(entry.st_mode) or entry.st_nlink > 1:
            raise QueryJournalError("unsafe database file")
    return path


def _clock(now):
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise QueryJournalError("timezone-aware verification clock required")
    return now


def _event_hash(seq, values):
    encoded = json.dumps(
        {"seq": seq, **values}, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(b"MTR-E2-observation-v1\x00" + encoded).hexdigest()


def _under_live_host_lock(operation):
    """Never allow a journal read or write outside current host ACL locks."""
    @wraps(operation)
    def guarded(self, *args, **kwargs):
        issuer = self.outbox._recovery_provenance
        if issuer is None:
            raise PermissionError("journal recovery provenance not bound")
        with issuer._service.lock, issuer._service.bridge._lock:
            return operation(self, *args, **kwargs)
    return guarded


class QueryObservationJournal:
    """Never reuses a query ID, even for another tenant or original request.

    Only metadata digests and scope are stored. Signed wires and secrets are
    verified in memory and are never written to the database.
    """

    def __init__(self, path: Path, *, outbox: HostRequestStore,
                 gate: OneShotDispatchGate, max_records: int = _MAX_RECORDS):
        if (type(outbox) is not HostRequestStore or
                type(gate) is not OneShotDispatchGate or gate.outbox is not outbox):
            raise TypeError("same host-owned outbox and one-shot gate required")
        if type(max_records) is not int or not 1 <= max_records <= _MAX_RECORDS:
            raise QueryJournalError("invalid bounded journal capacity")
        self.path = _path(path)
        if self.path in (outbox.path, gate.path):
            raise QueryJournalError("journal database must be separate")
        self.outbox = outbox
        self.gate = gate
        self.max_records = max_records
        fresh = not self.path.exists()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if fresh:
                    for _, sql in _SCHEMA.values():
                        conn.execute(sql)
                    conn.execute("PRAGMA user_version=1")
                self._audit_integrity(conn)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @contextmanager
    def _connect(self):
        _path(self.path)
        with closing(sqlite3.connect(str(self.path), timeout=15,
                                     isolation_level=None)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=15000")
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn

    @staticmethod
    def _audit_integrity(conn):
        if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise QueryJournalError("unrecognized journal version")
        objects = {
            row["name"]: (row["type"], row["sql"]) for row in conn.execute(
                "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        }
        if objects != _SCHEMA:
            raise QueryJournalError("modified or missing journal schema/immutability")
        if conn.execute("PRAGMA integrity_check(1)").fetchone()[0] != "ok":
            raise QueryJournalError("SQLite integrity check failed")
        previous = _GENESIS
        count = 0
        for row in conn.execute("SELECT * FROM query_observations ORDER BY seq"):
            count += 1
            record = dict(row)
            if (record["seq"] != count or
                    record["previous_sha256"] != previous or
                    type(record["event_sha256"]) is not str or
                    not _SHA.fullmatch(record["event_sha256"])):
                raise QueryJournalError("broken append-only sequence or hash chain")
            for field in _FIELDS:
                if type(record[field]) is not str or not record[field]:
                    raise QueryJournalError("malformed stored observation")
            if (not _ID.fullmatch(record["query_id"]) or
                    not _ID.fullmatch(record["request_id"]) or
                    any(not _SHA.fullmatch(record[field]) for field in (
                        "original_payload_sha256", "original_envelope_sha256",
                        "query_payload_sha256", "query_envelope_sha256",
                        "peer_payload_sha256", "peer_envelope_sha256",
                        "previous_sha256",
                    )) or record["observed_state"] not in ("received", "unknown") or
                    record["actor_role"] not in ("admin", "editor")):
                raise QueryJournalError("invalid stored evidence encoding")
            values = {key: record[key] for key in _FIELDS}
            if _event_hash(count, values) != record["event_sha256"]:
                raise QueryJournalError("stored evidence digest changed")
            previous = record["event_sha256"]
        if count > _MAX_RECORDS:
            raise QueryJournalError("journal row count exceeded hard limit")
        high_water = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='query_observations'"
        ).fetchone()
        if (0 if high_water is None else high_water[0]) != count:
            # AUTOINCREMENT's high-water mark catches an erased final event
            # even when someone briefly disabled the DELETE trigger via DDL.
            raise QueryJournalError("append-only sequence high-water mismatch")
        return count, previous

    @contextmanager
    def _write(self):
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                count, previous = self._audit_integrity(conn)
                yield conn, count, previous
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def _authorized(self, *, principal, token, request_id, expected_base_revision):
        if type(principal) is not TrustedPrincipal or principal.role not in ("admin", "editor"):
            raise PermissionError("current trusted host actor required")
        if type(request_id) is not str or not _ID.fullmatch(request_id):
            raise QueryJournalError("invalid original request ID")
        if type(expected_base_revision) is not int or not 1 <= expected_base_revision <= 2**53-1:
            raise QueryJournalError("invalid original revision")
        issuer = self.outbox._recovery_provenance
        if issuer is None:
            raise PermissionError("journal recovery provenance not bound")
        from mtr_host_principal_provenance import OUTBOX_RECOVERY, GATE_RECOVERY
        # Every protected read consumes its own freshly issued single-use HMAC
        # proof, scoped to the issuer's real active host session and audience.
        outbox_seal = issuer.issue_recovery(token, audience=OUTBOX_RECOVERY)
        gate_seal = issuer.issue_recovery(token, audience=GATE_RECOVERY)
        nested_outbox_seal = issuer.issue_recovery(token, audience=OUTBOX_RECOVERY)
        snapshot = self.outbox.recovery_snapshot(
            principal=principal, request_id=request_id,
            expected_base_revision=expected_base_revision,
            token=token, seal=outbox_seal,
        )
        gate = self.gate.recovery_status(
            principal=principal, request_id=request_id,
            expected_base_revision=expected_base_revision,
            token=token, gate_seal=gate_seal, outbox_seal=nested_outbox_seal,
        )
        if gate.get("reservationConsumed") is not True or gate.get("mayDispatch") is not False:
            raise PermissionError("prior one-shot reservation required")
        if (snapshot["orgId"] != principal.org_id or
                snapshot["projectId"] not in principal.project_ids or
                snapshot["actorId"] != principal.user_id):
            raise PermissionError("original actor or project was revoked")
        return snapshot

    @_under_live_host_lock
    def record(self, *, principal: TrustedPrincipal, request_id: str,
               expected_base_revision: int, original_wire: bytes,
               query_wire: bytes, peer_receipt_wire: bytes,
               sender_secret: bytes, peer_secret: bytes, now: datetime,
               sender_id: str, sender_key_id: str, peer_id: str,
               peer_key_id: str, token: str = None) -> dict:
        """Verify three linked HMAC envelopes and commit one immutable row.

        This must be invoked by the trusted host following a signed peer query.
        Re-login is allowed only for the same currently authorized original actor.
        An identical query ID + signed *payload* is idempotent, including a
        re-signed equivalent envelope; contradictory IDs always fail closed.
        """
        instant = _clock(now)
        snapshot = self._authorized(
            principal=principal, token=token, request_id=request_id,
            expected_base_revision=expected_base_revision,
        )
        original = verify_request(
            original_wire, secret=sender_secret, now=instant,
            expected_organization_id=snapshot["orgId"],
            expected_sender_id=sender_id, expected_key_id=sender_key_id,
            purpose="finance_review_request",
            allowed_actor_roles=frozenset({principal.role}),
        )
        if (original.request_id != request_id or
                original.payload_sha256 != snapshot["payloadSha256"] or
                original.payload != snapshot["payload"]):
            raise QueryJournalConflict("signed original does not match saved intent")
        query = verify_receipt_query(
            query_wire, secret=sender_secret, now=instant,
            expected_organization_id=snapshot["orgId"],
            expected_sender_id=sender_id, expected_key_id=sender_key_id,
            allowed_actor_roles=frozenset({principal.role}),
        )
        receipt = verify_peer_receipt(
            peer_receipt_wire, original=original, query=query, secret=peer_secret,
            now=instant, expected_peer_id=peer_id,
            expected_peer_key_id=peer_key_id,
        )
        observed_state = ("received" if receipt.payload["lookupStatus"] == "received"
                          else "unknown")
        binding = {
            "query_id": query.request_id,
            "request_id": request_id,
            "original_payload_sha256": original.payload_sha256,
            "original_envelope_sha256": original.envelope_sha256,
            "query_payload_sha256": query.payload_sha256,
            "query_envelope_sha256": query.envelope_sha256,
            "peer_payload_sha256": receipt.payload_sha256,
            "peer_envelope_sha256": receipt.envelope_sha256,
            "org_id": principal.org_id,
            "project_id": snapshot["projectId"],
            "actor_id": principal.user_id,
            "actor_role": principal.role,
            "session_id": principal.session_id,
            "sender_id": original.sender_id,
            "sender_key_id": original.key_id,
            "peer_id": receipt.sender_id,
            "peer_key_id": receipt.key_id,
            "observed_state": observed_state,
            "recorded_utc": datetime.now(timezone.utc).isoformat(),
        }
        with self._write() as (conn, count, previous):
            # Re-check after acquiring the SQLite write lock. The integration
            # host must also hold its own live account/card ACL lock here.
            latest = self._authorized(
                principal=principal, token=token, request_id=request_id,
                expected_base_revision=expected_base_revision,
            )
            if (latest["payloadSha256"] != snapshot["payloadSha256"] or
                    latest["projectId"] != snapshot["projectId"]):
                raise QueryJournalConflict("authoritative source changed")
            old = conn.execute("SELECT * FROM query_observations WHERE query_id=?",
                               (query.request_id,)).fetchone()
            if old is not None:
                # Re-signed envelopes with the exact same payload are the same
                # observation; never replace the original forensic witness.
                for field in (
                    "request_id", "original_payload_sha256",
                    "query_payload_sha256", "peer_payload_sha256",
                    "org_id", "project_id", "actor_id", "actor_role",
                    "sender_id", "sender_key_id", "peer_id", "peer_key_id",
                    "observed_state",
                ):
                    if old[field] != binding[field]:
                        raise QueryJournalConflict("query ID reused or contradictory")
                return self._public(old, idempotent=True)
            if count >= self.max_records:
                raise QueryJournalError("journal capacity reached: archive operationally, never reuse IDs")
            binding["previous_sha256"] = previous
            seq = count + 1
            digest = _event_hash(seq, binding)
            keys = ("seq", *_FIELDS, "event_sha256")
            values = (seq, *(binding[key] for key in _FIELDS), digest)
            conn.execute(
                "INSERT INTO query_observations (" + ",".join(keys) + ") VALUES (" +
                ",".join("?" for _ in keys) + ")", values,
            )
            self._audit_integrity(conn)
            return self._public(
                conn.execute("SELECT * FROM query_observations WHERE seq=?", (seq,)).fetchone(),
                idempotent=False,
            )

    @staticmethod
    def _public(row, *, idempotent):
        return {
            "queryRequestId": row["query_id"],
            "requestId": row["request_id"],
            "originalPayloadSha256": row["original_payload_sha256"],
            "queryPayloadSha256": row["query_payload_sha256"],
            "signedPeerEnvelopeSha256": row["peer_envelope_sha256"],
            "lookupStatus": row["observed_state"],
            "recordedUtc": row["recorded_utc"],
            "idempotent": idempotent,
            "canAutoRetry": False,
            "officialTarazReceipt": False,
            "financialEventCreated": False,
        }

    @_under_live_host_lock
    def observations(self, *, principal: TrustedPrincipal, request_id: str,
                     expected_base_revision: int, limit: int = 100,
                     token: str = None) -> tuple[dict, ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise QueryJournalError("invalid bounded observation limit")
        self._authorized(
            principal=principal, token=token, request_id=request_id,
            expected_base_revision=expected_base_revision,
        )
        with self._connect() as conn:
            conn.execute("BEGIN")
            self._audit_integrity(conn)
            return tuple(self._public(row, idempotent=False) for row in conn.execute(
                "SELECT * FROM query_observations WHERE request_id=? "
                "ORDER BY seq DESC LIMIT ?", (request_id, limit),
            ))


__all__ = [
    "QueryObservationJournal", "QueryJournalError", "QueryJournalConflict",
]
