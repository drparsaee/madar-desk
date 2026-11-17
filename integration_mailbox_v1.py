"""Durable, host-owned Madar -> paired Taraz Counterparties read-only mailbox.

The caller is a trusted Python HTTPS host. It MUST derive actor, workspace,
installation, company, grant and authenticated peer key from its own server-side
session/registry, never from browser flags or unverified request JSON.

No routes, listeners, finance DB reads, CRM mutations or credentials are here.
The authorizer checks CURRENT pairing and actor/company/project policy on every
operation, including retry, reply, read and ACK. Stored requested grants are
descriptions of intent, NEVER authorization.

The authenticated Taraz peer signs a response with HMAC-SHA256 using its
currently valid raw integration bearer (UTF-8 bytes). The server supplies this
same bearer only after its normal HTTPS integration-key validation; the mailbox
does not persist it. Response signatures include the entire immutable queued
envelope and exact allowlisted result, binding the actor, install, request and
company and preventing cross-company/replay substitutions.

SQLite uses a protected DB and protected persistent TRUNCATE journal. Windows
DACL enforcement and non-delete-share file handles are reused from the existing
integration registry; non-Windows operation fails closed. The trusted host must
place this file in a private, dedicated, backed-up directory.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import unicodedata

from integration_key_registry import _private_windows_guard


_HEX32 = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_KEY = re.compile(r"ik_[0-9a-f]{24}\Z", re.ASCII)
_PARTY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_CURSOR = re.compile(r"[A-Za-z0-9_-]{1,2048}\Z", re.ASCII)
_KIND = frozenset(("all", "customer", "vendor", "both"))
_PARTY_KIND = _KIND - {"all"}
_METHODS = frozenset(("Counterparties.Search", "Counterparties.Get"))
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MAX_REQUEST_BYTES = 4096
_MAX_REPLY_BYTES = 32768
_MAX_RECORDS = 20000
_MAX_OPEN = 1000
_SIGNING_PREFIX = b"MADAR.MAILBOX.REPLY.v1\x00"


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _text(value, maximum, *, empty=False):
    if type(value) is not str or len(value) > maximum or (not empty and not value):
        raise ValueError("Invalid mailbox text")
    try:
        value.encode("utf-8", "strict")
    except UnicodeError:
        raise ValueError("Invalid mailbox text") from None
    if any(ord(c) < 32 or ord(c) == 127 or
           (unicodedata.category(c) == "Cf" and c != "\u200c")
           for c in value):
        raise ValueError("Invalid mailbox text")
    return value


def _hex32(value):
    if type(value) is not str or not _HEX32.fullmatch(value):
        raise ValueError("Invalid mailbox identifier")
    return value


def _query_parameters(operation, parameters):
    if type(parameters) is not dict:
        raise ValueError("Invalid counterparties request")
    if operation == "Counterparties.Get":
        if (set(parameters) != {"partyId"} or
                type(parameters["partyId"]) is not str or
                not _PARTY.fullmatch(parameters["partyId"]) or
                parameters["partyId"].startswith("ps.parsian.")):
            raise ValueError("Invalid Get parameters")
    elif operation == "Counterparties.Search":
        if set(parameters) != {"query", "kind", "limit", "cursor"}:
            raise ValueError("Invalid Search parameters")
        _text(parameters["query"], 120, empty=True)
        if type(parameters["kind"]) is not str or parameters["kind"] not in _KIND:
            raise ValueError("Invalid Search kind")
        if type(parameters["limit"]) is not int or not 1 <= parameters["limit"] <= 50:
            raise ValueError("Invalid Search limit")
        cursor = parameters["cursor"]
        if cursor is not None and (type(cursor) is not str or not _CURSOR.fullmatch(cursor)):
            raise ValueError("Invalid Search cursor")
    else:
        raise ValueError("Unsupported counterparties operation")
    if len(_canonical(parameters)) > _MAX_REQUEST_BYTES:
        raise ValueError("Oversized counterparties request")
    return parameters


def _party(value):
    if (type(value) is not dict or set(value) != {"partyId", "name", "kind"}
            or type(value["partyId"]) is not str or
            not _PARTY.fullmatch(value["partyId"])
            or value["partyId"].startswith("ps.parsian.")
            or type(value["kind"]) is not str or
            value["kind"] not in _PARTY_KIND):
        raise ValueError("Invalid party projection")
    _text(value["name"], 256)


def _result(operation, result):
    if type(result) is not dict:
        raise ValueError("Invalid counterparties reply")
    if operation == "Counterparties.Get":
        if set(result) != {"party"}:
            raise ValueError("Invalid Get reply")
        if result["party"] is not None:
            _party(result["party"])
    elif operation == "Counterparties.Search":
        if set(result) != {"parties", "hasMore", "nextCursor"}:
            raise ValueError("Invalid Search reply")
        parties = result["parties"]
        if type(parties) is not list or len(parties) > 50:
            raise ValueError("Invalid party page size")
        for entry in parties:
            _party(entry)
        ids = [entry["partyId"] for entry in parties]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate party projection")
        if type(result["hasMore"]) is not bool:
            raise ValueError("Invalid pagination flag")
        cursor = result["nextCursor"]
        if (result["hasMore"] and
                (not parties or type(cursor) is not str or not _CURSOR.fullmatch(cursor))):
            raise ValueError("Invalid next cursor")
        if not result["hasMore"] and cursor is not None:
            raise ValueError("Unexpected next cursor")
    else:
        raise ValueError("Unsupported reply operation")
    if len(_canonical(result)) > _MAX_REPLY_BYTES:
        raise ValueError("Oversized counterparties reply")
    return result


def sign_counterparties_reply(peer_secret, request_envelope, result):
    """Reference signing contract for the Taraz HTTPS client.

    peer_secret is the active paired integration bearer encoded as UTF-8 bytes.
    Must never be stored or logged. Host checks pairing/key revocation separately.
    """
    if type(peer_secret) is not bytes or len(peer_secret) < 32:
        raise ValueError("Invalid active peer secret")
    if type(request_envelope) is not dict or type(result) is not dict:
        raise ValueError("Invalid signed reply")
    payload = _SIGNING_PREFIX + _canonical({"request": request_envelope, "result": result})
    return hmac.new(peer_secret, payload, hashlib.sha256).hexdigest()


class IntegrationMailbox:
    """Trusted-host store; all public methods reauthorize live server state.

    authorizer(action=..., workspace_id=..., installation_id=...,
               peer_key_id=..., company_id=..., requested_actor=...,
               requested_grant=..., request_id=..., operation=...)
    MUST return exact True. Host must derive live identity/pairing/ACL, not
    merely trust stored grant, peer IDs or mutable web client supplied flags.
    """

    def __init__(self, db_path, *, authorizer):
        if not callable(authorizer):
            raise TypeError("Trusted host authorizer required")
        path = Path(db_path)
        if not path.is_absolute() or path.suffix != ".sqlite3":
            raise ValueError("Absolute SQLite mailbox path required")
        self.path = path
        self.journal = Path(str(path) + "-journal")
        self.authorizer = authorizer
        self._check_paths()

    def _check_paths(self):
        for folder in (self.path.parent, *self.path.parent.parents):
            if (folder.is_symlink() or not folder.is_dir() or
                    getattr(folder.lstat(), "st_file_attributes", 0) & _REPARSE):
                raise PermissionError("Unsafe mailbox directory")
        for path in (self.path, self.journal):
            if os.path.lexists(path):
                info = path.lstat()
                if (path.is_symlink() or not stat.S_ISREG(info.st_mode) or
                        info.st_nlink != 1 or
                        getattr(info, "st_file_attributes", 0) & _REPARSE):
                    raise PermissionError("Unsafe mailbox SQLite file")
        for extra in (str(self.path) + "-wal", str(self.path) + "-shm"):
            if os.path.lexists(extra):
                raise PermissionError("Unexpected SQLite sidecar")

    @staticmethod
    def _create_empty(path):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR |
                                 getattr(os, "O_BINARY", 0), 0o600)
        except FileExistsError:
            return
        else:
            os.close(descriptor)

    @contextmanager
    def _connect(self, *, writable):
        if os.name != "nt":
            raise PermissionError("Protected Windows mailbox storage required")
        self._check_paths()
        if not writable and not self.path.exists():
            yield None
            return
        if writable:
            self._create_empty(self.path)
            self._create_empty(self.journal)
        self._check_paths()
        if not self.journal.exists():
            raise PermissionError("Missing protected mailbox journal")
        with ExitStack() as stack:
            stack.enter_context(_private_windows_guard(self.path))
            stack.enter_context(_private_windows_guard(self.journal))
            self._check_paths()
            if writable:
                db = sqlite3.connect(self.path, timeout=8, isolation_level=None)
            else:
                db = sqlite3.connect(self.path.as_uri() + "?mode=ro",
                                     timeout=8, isolation_level=None, uri=True)
            try:
                db.execute("PRAGMA busy_timeout=8000")
                db.execute("PRAGMA temp_store=MEMORY")
                if writable:
                    mode = db.execute("PRAGMA journal_mode=TRUNCATE").fetchone()[0]
                    if mode.lower() != "truncate":
                        raise PermissionError("Secure journal mode required")
                    db.execute("PRAGMA synchronous=FULL")
                    db.execute("BEGIN IMMEDIATE")
                    self._create_schema(db)
                else:
                    if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                        raise RuntimeError("Unknown mailbox schema")
                self._check_paths()
                yield db
                if writable:
                    db.execute("COMMIT")
            except BaseException:
                if writable and db.in_transaction:
                    db.execute("ROLLBACK")
                raise
            finally:
                db.close()
        self._check_paths()

    @staticmethod
    def _create_schema(db):
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            db.execute("""CREATE TABLE mailbox (
                request_id TEXT PRIMARY KEY, envelope TEXT NOT NULL,
                scope_hash TEXT NOT NULL, workspace_id TEXT NOT NULL,
                installation_id TEXT NOT NULL, company_id TEXT NOT NULL,
                created_at REAL NOT NULL, expires_at REAL NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','completed')),
                result TEXT, result_hash TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                delivery_ack_at REAL, result_ack_at REAL)""")
            db.execute("""CREATE INDEX mailbox_peer_pending ON mailbox(
                workspace_id,installation_id,company_id,status,created_at)""")
            db.execute("PRAGMA user_version=1")
        elif version != 1:
            raise RuntimeError("Unknown mailbox schema")

    @staticmethod
    def _now(now):
        value = time.time() if now is None else now
        if type(value) not in (float, int) or not math.isfinite(value) or value < 1:
            raise ValueError("Invalid trusted timestamp")
        return float(value)

    def _authorize(self, action, envelope, *, peer_key_id=None):
        try:
            approved = self.authorizer(
                action=action, workspace_id=envelope["workspaceId"],
                installation_id=envelope["installationId"],
                company_id=envelope["companyId"],
                requested_actor=envelope.get("requestedActor"),
                requested_grant=envelope.get("requestedGrant"),
                peer_key_id=peer_key_id, request_id=envelope.get("requestId"),
                operation=envelope.get("operation"))
        except Exception:
            raise PermissionError("Mailbox permission denied") from None
        if approved is not True:
            raise PermissionError("Mailbox permission denied")

    @staticmethod
    def _status(row, now):
        if row["status"] == "completed":
            return "completed"
        return "expired" if now >= row["expires_at"] else "pending"

    @staticmethod
    def _record(row):
        return dict(zip(("envelope", "scope_hash", "workspace_id",
                         "installation_id", "company_id", "created_at",
                         "expires_at", "status", "result", "result_hash",
                         "attempts", "delivery_ack_at", "result_ack_at"), row))

    @staticmethod
    def _find(db, request_id):
        row = db.execute(
            """SELECT envelope,scope_hash,workspace_id,installation_id,
                company_id,created_at,expires_at,status,result,result_hash,
                attempts,delivery_ack_at,result_ack_at FROM mailbox WHERE request_id=?""",
            (request_id,)).fetchone()
        if row is None:
            return None
        entry = IntegrationMailbox._record(row)
        try:
            raw = entry["envelope"]
            if type(raw) is not str or len(raw.encode("utf-8")) > _MAX_REQUEST_BYTES:
                raise ValueError("Bad mailbox envelope")
            envelope = json.loads(raw)
            if (type(envelope) is not dict or set(envelope) != {
                    "workspaceId", "installationId", "companyId", "requestId",
                    "requestedActor", "requestedGrant", "operation", "parameters"}):
                raise ValueError("Bad mailbox envelope fields")
            for name in ("workspaceId", "installationId", "companyId", "requestId"):
                _hex32(envelope[name])
            _text(envelope["requestedActor"], 128)
            if (envelope["requestedGrant"] != "counterparties.read"
                    or type(envelope["operation"]) is not str or
                    envelope["operation"] not in _METHODS):
                raise ValueError("Bad mailbox authorization scope")
            _query_parameters(envelope["operation"], envelope["parameters"])
            if (_canonical(envelope).decode("utf-8") != raw or
                    hashlib.sha256(raw.encode("utf-8")).hexdigest() !=
                    entry["scope_hash"] or
                    envelope["requestId"] != request_id or
                    (envelope["workspaceId"], envelope["installationId"],
                     envelope["companyId"]) !=
                    (entry["workspace_id"], entry["installation_id"],
                     entry["company_id"])):
                raise ValueError("Mailbox scope checksum failed")
            if (type(entry["created_at"]) not in (float, int) or
                    type(entry["expires_at"]) not in (float, int) or
                    not math.isfinite(entry["created_at"]) or
                    not math.isfinite(entry["expires_at"]) or
                    entry["expires_at"] <= entry["created_at"] or
                    type(entry["attempts"]) is not int or entry["attempts"] < 0):
                raise ValueError("Bad mailbox timestamps")
            if entry["status"] == "pending":
                if (entry["result"] is not None or
                        entry["result_hash"] is not None or
                        entry["result_ack_at"] is not None):
                    raise ValueError("Unexpected pending result")
            elif entry["status"] == "completed":
                payload = entry["result"]
                if (type(payload) is not str or
                        len(payload.encode("utf-8")) > _MAX_REPLY_BYTES):
                    raise ValueError("Bad completed mailbox result")
                decoded = json.loads(payload)
                _result(envelope["operation"], decoded)
                if (_canonical(decoded).decode("utf-8") != payload or
                        hashlib.sha256(payload.encode("utf-8")).hexdigest() !=
                        entry["result_hash"]):
                    raise ValueError("Mailbox result checksum failed")
            else:
                raise ValueError("Bad mailbox state")
        except (ValueError, UnicodeError, TypeError, KeyError, OverflowError):
            raise RuntimeError("Mailbox record integrity failure") from None
        return entry

    def enqueue(self, *, workspace_id, installation_id, company_id, request_id,
                requested_actor, requested_grant, operation, parameters,
                ttl_seconds=180, now=None):
        """Queue by stable host-issued idempotency request ID; no new ID on retry."""
        for value in (workspace_id, installation_id, company_id, request_id):
            _hex32(value)
        _text(requested_actor, 128)
        if requested_grant != "counterparties.read":
            raise ValueError("Unsupported requested grant")
        if type(operation) is not str or operation not in _METHODS:
            raise ValueError("Unsupported counterparties operation")
        _query_parameters(operation, parameters)
        if type(ttl_seconds) is not int or not 15 <= ttl_seconds <= 900:
            raise ValueError("Invalid mailbox TTL")
        moment = self._now(now)
        scope = {"workspaceId": workspace_id, "installationId": installation_id,
                 "companyId": company_id, "requestId": request_id,
                 "requestedActor": requested_actor, "requestedGrant": requested_grant,
                 "operation": operation, "parameters": parameters}
        blob = _canonical(scope)
        if len(blob) > _MAX_REQUEST_BYTES:
            raise ValueError("Oversized queued request")
        self._authorize("enqueue", scope)
        fingerprint = hashlib.sha256(blob).hexdigest()
        with self._connect(writable=True) as db:
            previous = self._find(db, request_id)
            if previous is not None:
                if previous["scope_hash"] != fingerprint or previous["envelope"] != blob.decode("utf-8"):
                    raise ValueError("Mailbox idempotency collision")
                state = self._status(previous, moment)
            else:
                total, pending = db.execute(
                    """SELECT COUNT(*), SUM(CASE WHEN status='pending'
                        AND expires_at>? THEN 1 ELSE 0 END) FROM mailbox""",
                    (moment,)).fetchone()
                if total >= _MAX_RECORDS or (pending or 0) >= _MAX_OPEN:
                    raise RuntimeError("Mailbox capacity exceeded")
                db.execute("""INSERT INTO mailbox(request_id,envelope,scope_hash,
                    workspace_id,installation_id,company_id,created_at,expires_at,status)
                    VALUES(?,?,?,?,?,?,?,?, 'pending')""",
                    (request_id, blob.decode("utf-8"), fingerprint, workspace_id,
                     installation_id, company_id, moment, moment + ttl_seconds))
                state = "pending"
            self._authorize("enqueue", scope)
        return {"requestId": request_id, "status": state, "reused": previous is not None}

    def poll(self, *, workspace_id, installation_id, company_id, peer_key_id,
             limit=10, now=None):
        """Paired Taraz retries all pending deliveries until a durable reply."""
        for value in (workspace_id, installation_id, company_id):
            _hex32(value)
        if type(peer_key_id) is not str or not _KEY.fullmatch(peer_key_id):
            raise ValueError("Invalid paired peer key")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Invalid poll size")
        moment = self._now(now)
        base = {"workspaceId": workspace_id, "installationId": installation_id,
                "companyId": company_id}
        self._authorize("poll", base, peer_key_id=peer_key_id)
        out = []
        with self._connect(writable=True) as db:
            rows = db.execute(
                """SELECT request_id,envelope FROM mailbox
                    WHERE workspace_id=? AND installation_id=? AND company_id=?
                    AND status='pending' AND expires_at>?
                    ORDER BY created_at,request_id LIMIT ?""",
                (workspace_id, installation_id, company_id, moment, limit)).fetchall()
            for request_id, _envelope_json in rows:
                record = self._find(db, request_id)
                envelope = json.loads(record["envelope"])
                self._authorize("poll", envelope, peer_key_id=peer_key_id)
                db.execute("UPDATE mailbox SET attempts=attempts+1 WHERE request_id=?",
                           (request_id,))
                out.append(envelope)
            self._authorize("poll", base, peer_key_id=peer_key_id)
            for envelope in out:
                self._authorize("poll", envelope, peer_key_id=peer_key_id)
        return out

    def acknowledge_delivery(self, *, workspace_id, installation_id, company_id,
                             request_id, peer_key_id, now=None):
        """Optional peer receipt. ACK does NOT suppress retries before reply."""
        moment = self._now(now)
        envelope = self._peer_record(workspace_id, installation_id, company_id,
                                     request_id, peer_key_id, "delivery_ack", moment,
                                     update_ack=True)
        return {"requestId": request_id, "status": envelope}

    def _peer_record(self, workspace_id, installation_id, company_id, request_id,
                     peer_key_id, action, moment, *, result=None, signature=None,
                     peer_secret=None, update_ack=False):
        for value in (workspace_id, installation_id, company_id, request_id):
            _hex32(value)
        if type(peer_key_id) is not str or not _KEY.fullmatch(peer_key_id):
            raise ValueError("Invalid paired peer key")
        base = {"workspaceId": workspace_id, "installationId": installation_id,
                "companyId": company_id, "requestId": request_id}
        self._authorize(action, base, peer_key_id=peer_key_id)
        with self._connect(writable=True) as db:
            row = self._find(db, request_id)
            if (row is None or (row["workspace_id"], row["installation_id"],
                                row["company_id"]) !=
                    (workspace_id, installation_id, company_id)):
                raise PermissionError("Mailbox request unavailable")
            envelope = json.loads(row["envelope"])
            self._authorize(action, envelope, peer_key_id=peer_key_id)
            state = self._status(row, moment)
            if update_ack:
                if state == "pending":
                    db.execute("""UPDATE mailbox SET delivery_ack_at=COALESCE(
                        delivery_ack_at,?) WHERE request_id=?""", (moment, request_id))
            else:
                _result(envelope["operation"], result)
                if (type(signature) is not str or not re.fullmatch(
                        r"[0-9a-f]{64}\Z", signature, re.ASCII)):
                    raise PermissionError("Invalid authenticated reply")
                expected = sign_counterparties_reply(peer_secret, envelope, result)
                if not hmac.compare_digest(signature, expected):
                    raise PermissionError("Invalid authenticated reply")
                if state == "expired":
                    raise ValueError("Expired mailbox request")
                body = _canonical(result).decode("utf-8")
                digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
                if state == "completed":
                    if row["result_hash"] != digest or row["result"] != body:
                        raise ValueError("Conflicting duplicate reply")
                else:
                    db.execute("""UPDATE mailbox SET status='completed',
                        result=?,result_hash=? WHERE request_id=? AND status='pending'""",
                        (body, digest, request_id))
            self._authorize(action, envelope, peer_key_id=peer_key_id)
            return state if update_ack else "completed"

    def submit_reply(self, *, workspace_id, installation_id, company_id,
                     request_id, peer_key_id, result, signature, peer_secret,
                     now=None):
        """Authenticated HMAC reply, persisted before HTTP caller sees success."""
        state = self._peer_record(workspace_id, installation_id, company_id,
                                  request_id, peer_key_id, "reply", self._now(now),
                                  result=result, signature=signature,
                                  peer_secret=peer_secret)
        return {"requestId": request_id, "status": state}

    def reconcile(self, *, workspace_id, installation_id, company_id, request_id,
                  requested_actor, now=None):
        """Madar host can recover an already completed reply after restart/loss."""
        for value in (workspace_id, installation_id, company_id, request_id):
            _hex32(value)
        _text(requested_actor, 128)
        moment = self._now(now)
        base = {"workspaceId": workspace_id, "installationId": installation_id,
                "companyId": company_id, "requestId": request_id,
                "requestedActor": requested_actor}
        self._authorize("reconcile", base)
        with self._connect(writable=False) as db:
            if db is None:
                raise PermissionError("Mailbox request unavailable")
            row = self._find(db, request_id)
            if (row is None or (row["workspace_id"], row["installation_id"],
                                row["company_id"]) !=
                    (workspace_id, installation_id, company_id)):
                raise PermissionError("Mailbox request unavailable")
            envelope = json.loads(row["envelope"])
            if envelope["requestedActor"] != requested_actor:
                raise PermissionError("Mailbox request unavailable")
            self._authorize("reconcile", envelope)
            state = self._status(row, moment)
            result = json.loads(row["result"]) if state == "completed" else None
            self._authorize("reconcile", envelope)
            return {"requestId": request_id, "status": state, "result": result,
                    "acknowledged": row["result_ack_at"] is not None if state == "completed"
                    else False}

    def acknowledge_result(self, *, workspace_id, installation_id, company_id,
                           request_id, requested_actor, now=None):
        """Idempotent Madar host ACK; durable reply remains for lost-ACK recovery."""
        for value in (workspace_id, installation_id, company_id, request_id):
            _hex32(value)
        _text(requested_actor, 128)
        moment = self._now(now)
        base = {"workspaceId": workspace_id, "installationId": installation_id,
                "companyId": company_id, "requestId": request_id,
                "requestedActor": requested_actor}
        self._authorize("result_ack", base)
        with self._connect(writable=True) as db:
            row = self._find(db, request_id)
            if (row is None or (row["workspace_id"], row["installation_id"],
                                row["company_id"]) !=
                    (workspace_id, installation_id, company_id)):
                raise PermissionError("Mailbox request unavailable")
            envelope = json.loads(row["envelope"])
            if envelope["requestedActor"] != requested_actor:
                raise PermissionError("Mailbox request unavailable")
            self._authorize("result_ack", envelope)
            if self._status(row, moment) != "completed":
                raise ValueError("Cannot ACK an incomplete request")
            db.execute("""UPDATE mailbox SET result_ack_at=COALESCE(result_ack_at,?)
                WHERE request_id=?""", (moment, request_id))
            self._authorize("result_ack", envelope)
        return {"requestId": request_id, "status": "completed", "acknowledged": True}


__all__ = ["IntegrationMailbox", "sign_counterparties_reply"]
