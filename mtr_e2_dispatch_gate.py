"""E2 one-shot dispatch reservation, with no transport or finance side effects.

Only a trusted host may provide TrustedPrincipal, current_server_revision and
HostRequestStore. A reservation consumes the one allowed first-dispatch slot
BEFORE an external caller considers any network I/O. Even if the caller dies
before attempting I/O, this gate permanently requires authoritative query
instead of issuing another dispatch grant. No automatic retry exists.

This SQLite journal is deliberately separate from HostRequestStore: its
reservation cannot be atomically committed with the host outbox's state or
with a peer transmission. The deployment must resolve that remaining gate.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile

from mtr_host_request_store import HostRequestStore, TrustedPrincipal


class DispatchGateError(ValueError):
    """Malformed or corrupt one-shot gate request."""


class DispatchGateConflict(DispatchGateError):
    """A stale CAS/version, different identity or consumed first slot."""


_REQUEST_ID = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}\Z", re.ASCII)
_STATES = frozenset({
    "reserved_before_network", "unknown_after_attempt", "observed_received",
})
_SEND_ROLES = frozenset({"admin", "editor", "finance_submitter"})


def _validate_string(label, value, *, limit=180):
    if (type(value) is not str or not 1 <= len(value) <= limit
            or value != value.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise DispatchGateError(f"Invalid {label}")
    return value


def _request(value):
    if type(value) is not str or _REQUEST_ID.fullmatch(value) is None:
        raise DispatchGateError("Invalid request ID")
    return value


def _sha(value):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise DispatchGateError("Invalid SHA-256")
    return value


def _key(value):
    if type(value) is not str or _KEY.fullmatch(value) is None:
        raise DispatchGateError("Invalid stable send key")
    return value


def _revision(value):
    if type(value) is not int or not 1 <= value <= 2**53 - 1:
        raise DispatchGateError("Invalid exact base revision")
    return value


def _version(value):
    if type(value) is not int or not 1 <= value <= 3:
        raise DispatchGateError("Invalid CAS version")
    return value


def _now():
    return datetime.now(timezone.utc).isoformat()


def _regular(path, *, directory):
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise PermissionError("Symbolic links or junctions are not allowed")
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if getattr(info, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise PermissionError("Reparse-point paths are not allowed")
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise PermissionError("Expected a directory")
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
        raise PermissionError("Expected an ordinary non-hardlinked database")
    return True


def _path(path):
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.suffix != ".sqlite3"):
        raise DispatchGateError("Absolute server-selected .sqlite3 path required")
    for directory in (path.parent, *path.parent.parents):
        if not _regular(directory, directory=True):
            raise DispatchGateError("Database parent must already exist")
    _regular(path, directory=False)
    return path


_SCHEMA = (
    """CREATE TABLE dispatch_control (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        first_permits_enabled INTEGER NOT NULL CHECK(first_permits_enabled IN (0,1))
    )""",
    "INSERT INTO dispatch_control(singleton,first_permits_enabled) VALUES(1,1)",
    """CREATE TABLE dispatch_reservations (
        request_id TEXT PRIMARY KEY CHECK(length(request_id)=32),
        org_id TEXT NOT NULL CHECK(length(org_id) BETWEEN 1 AND 180),
        project_id TEXT NOT NULL CHECK(length(project_id) BETWEEN 1 AND 180),
        actor_id TEXT NOT NULL CHECK(length(actor_id) BETWEEN 1 AND 180),
        session_id TEXT NOT NULL CHECK(length(session_id) BETWEEN 1 AND 180),
        payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256)=64),
        base_revision INTEGER NOT NULL CHECK(base_revision BETWEEN 1 AND 9007199254740991),
        send_key TEXT NOT NULL UNIQUE CHECK(length(send_key) BETWEEN 8 AND 128),
        state TEXT NOT NULL CHECK(state IN (
            'reserved_before_network','unknown_after_attempt','observed_received')),
        version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 3),
        receipt_id TEXT CHECK(receipt_id IS NULL OR length(receipt_id) BETWEEN 1 AND 180),
        reserved_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK((state='reserved_before_network' AND version=1 AND receipt_id IS NULL)
            OR (state='unknown_after_attempt' AND version=2 AND receipt_id IS NULL)
            OR (state='observed_received' AND version IN (2,3) AND receipt_id IS NOT NULL))
    )""",
    """CREATE TABLE dispatch_audit (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL REFERENCES dispatch_reservations(request_id),
        version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 3),
        action TEXT NOT NULL CHECK(action IN (
            'reserved_before_network','unknown_after_attempt','observed_received')),
        actor_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        receipt_sha256 TEXT,
        recorded_at TEXT NOT NULL,
        UNIQUE(request_id, version)
    )""",
    """CREATE TRIGGER immutable_dispatch_audit_update BEFORE UPDATE ON dispatch_audit
       BEGIN SELECT RAISE(ABORT, 'immutable dispatch audit'); END""",
    """CREATE TRIGGER immutable_dispatch_audit_delete BEFORE DELETE ON dispatch_audit
       BEGIN SELECT RAISE(ABORT, 'immutable dispatch audit'); END""",
    """CREATE TRIGGER immutable_dispatch_reservation_delete BEFORE DELETE ON dispatch_reservations
       BEGIN SELECT RAISE(ABORT, 'immutable dispatch reservation'); END""",
    """CREATE TRIGGER dispatch_reservation_transitions BEFORE UPDATE ON dispatch_reservations
       WHEN NEW.request_id <> OLD.request_id OR NEW.org_id <> OLD.org_id
         OR NEW.project_id <> OLD.project_id OR NEW.actor_id <> OLD.actor_id
         OR NEW.session_id <> OLD.session_id OR NEW.payload_sha256 <> OLD.payload_sha256
         OR NEW.base_revision <> OLD.base_revision OR NEW.send_key <> OLD.send_key
         OR NEW.reserved_at <> OLD.reserved_at OR NEW.version <> OLD.version + 1
         OR NOT ((OLD.state='reserved_before_network' AND
                  NEW.state IN ('unknown_after_attempt','observed_received'))
                 OR (OLD.state='unknown_after_attempt' AND NEW.state='observed_received'))
       BEGIN SELECT RAISE(ABORT, 'invalid one-shot state transition'); END""",
)

_REQUIRED_OBJECTS = {
    "dispatch_control": "table", "dispatch_reservations": "table",
    "dispatch_audit": "table",
    "immutable_dispatch_audit_update": "trigger",
    "immutable_dispatch_audit_delete": "trigger",
    "immutable_dispatch_reservation_delete": "trigger",
    "dispatch_reservation_transitions": "trigger",
}


class OneShotDispatchGate:
    """Host-owned one-time reservation; never performs a network operation."""

    def __init__(self, path: Path, outbox: HostRequestStore):
        if type(outbox) is not HostRequestStore:
            raise TypeError("HostRequestStore required")
        self.path = _path(path)
        if self.path == outbox.path:
            raise DispatchGateError("Dispatch gate and host outbox must be separate databases")
        self.outbox = outbox
        fresh = not self.path.exists()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if fresh and conn.execute("PRAGMA user_version").fetchone()[0] == 0:
                    for statement in _SCHEMA:
                        conn.execute(statement)
                    conn.execute("PRAGMA user_version=1")
                self._check_schema(conn)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @contextmanager
    def _connect(self):
        _path(self.path)
        with closing(sqlite3.connect(
            str(self.path), isolation_level=None, timeout=15,
        )) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=15000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=FULL")
            yield conn

    @staticmethod
    def _check_schema(conn):
        if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise DispatchGateError("Unexpected dispatch schema version")
        for name, kind in _REQUIRED_OBJECTS.items():
            item = conn.execute(
                "SELECT type FROM sqlite_master WHERE name=?", (name,),
            ).fetchone()
            if item is None or item[0] != kind:
                raise DispatchGateError("Missing or modified dispatch schema object")
        controls = conn.execute(
            "SELECT singleton,first_permits_enabled FROM dispatch_control",
        ).fetchall()
        if (len(controls) != 1 or controls[0][0] != 1
                or controls[0][1] not in (0, 1)):
            raise DispatchGateError("Corrupt dispatch permit authority")
        if conn.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
            raise DispatchGateError("Corrupt dispatch SQLite database")

    @contextmanager
    def _write(self):
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._check_schema(conn)
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def _snapshot(self, *, principal, request_id, expected_base_revision,
                  expected_payload_sha256=None, send_key=None, for_reservation=False):
        if type(principal) is not TrustedPrincipal:
            raise PermissionError("Server-trusted principal required")
        _request(request_id)
        _revision(expected_base_revision)
        if for_reservation and (principal.role not in _SEND_ROLES
                                or "mtr.manual_send" not in principal.permissions):
            raise PermissionError("Manual-send role and permission required")
        snapshot = self.outbox.request_snapshot(
            principal=principal, request_id=request_id,
            expected_base_revision=expected_base_revision,
        )
        if (snapshot.get("requestState") != "MANUAL_SEND_AUTHORIZED"
                or snapshot.get("orgId") != principal.org_id
                or snapshot.get("projectId") not in principal.project_ids
                or snapshot.get("baseRevision") != expected_base_revision
                or snapshot.get("payload", {}).get("id") != request_id
                or snapshot["payload"].get("projectId") != snapshot["projectId"]):
            raise PermissionError("Server request not authorized for dispatch")
        _sha(snapshot.get("payloadSha256"))
        _key(snapshot.get("sendKey"))
        if expected_payload_sha256 is not None and snapshot["payloadSha256"] != _sha(expected_payload_sha256):
            raise DispatchGateConflict("Payload SHA changed")
        if send_key is not None and snapshot["sendKey"] != _key(send_key):
            raise DispatchGateConflict("Send key changed")
        return snapshot

    @staticmethod
    def _bound(row, principal, snapshot):
        for name, expected in (
            ("org_id", principal.org_id), ("project_id", snapshot["projectId"]),
            ("actor_id", principal.user_id), ("session_id", principal.session_id),
            ("payload_sha256", snapshot["payloadSha256"]),
            ("base_revision", snapshot["baseRevision"]),
            ("send_key", snapshot["sendKey"]),
        ):
            if row[name] != expected:
                raise DispatchGateConflict("Dispatch reservation binding changed")
        if row["state"] not in _STATES or type(row["version"]) is not int:
            raise DispatchGateError("Corrupt dispatch state")
        _request(row["request_id"])
        _sha(row["payload_sha256"])
        _key(row["send_key"])

    @staticmethod
    def _audit(conn, row, action):
        receipt_hash = (hashlib.sha256(row["receipt_id"].encode("utf-8")).hexdigest()
                        if row["receipt_id"] is not None else None)
        conn.execute(
            "INSERT INTO dispatch_audit (request_id,version,action,actor_id,session_id,"
            "receipt_sha256,recorded_at) VALUES(?,?,?,?,?,?,?)",
            (row["request_id"], row["version"], action, row["actor_id"],
             row["session_id"], receipt_hash, _now()),
        )

    @staticmethod
    def _get(conn, request_id):
        row = conn.execute(
            "SELECT * FROM dispatch_reservations WHERE request_id=?", (request_id,),
        ).fetchone()
        if row is None:
            raise KeyError("No dispatch reservation")
        result = dict(row)
        events = conn.execute(
            "SELECT version,action,actor_id,session_id,receipt_sha256 FROM dispatch_audit "
            "WHERE request_id=? ORDER BY version", (request_id,),
        ).fetchall()
        if len(events) != result["version"]:
            raise DispatchGateError("Dispatch audit/version consistency failure")
        for index, event in enumerate(events, 1):
            if (event["version"] != index
                    or event["actor_id"] != result["actor_id"]
                    or event["session_id"] != result["session_id"]
                    or event["action"] not in _STATES
                    or (index == 1 and event["action"] != "reserved_before_network")
                    or (index == 2 and event["action"] not in (
                        "unknown_after_attempt", "observed_received"))
                    or (index == 3 and event["action"] != "observed_received")):
                raise DispatchGateError("Dispatch audit history corruption")
        expected_hash = (hashlib.sha256(result["receipt_id"].encode("utf-8")).hexdigest()
                         if result["receipt_id"] is not None else None)
        if (events[-1]["action"] != result["state"]
                or events[-1]["receipt_sha256"] != expected_hash):
            raise DispatchGateError("Dispatch receipt/audit state contradiction")
        return result

    @staticmethod
    def _public(row, *, snapshot=None):
        # An old observed_received row was only a local outbox claim. Until a
        # distinct official Taraz receipt verifier exists it must NOT become a
        # confirmed operational status, even when the historical gate audit is
        # internally consistent. Preserve its original SQLite row for forensics.
        old_gate_confirmation = row["state"] == "observed_received"
        quarantined = (old_gate_confirmation or
                       (snapshot is not None and
                        snapshot.get("historicalReceiptQuarantined") is True))
        return {
            "requestId": row["request_id"],
            "state": ("quarantined_unverified_receipt" if old_gate_confirmation
                      else row["state"]),
            "version": row["version"],
            "reservationConsumed": True, "mayDispatch": False,
            "mustQueryFirst": True,
            "nextAction": "query_taraz_first_no_automatic_retry",
            "receiptId": None,
            "receiptVerification": "UNVERIFIED",
            "historicalReceiptQuarantined": quarantined,
            "officialTarazReceipt": False,
            "canAutoRetry": False,
            "source": "local_dispatch_gate_unverified",
            "tarazPostingPerformed": False,
        }

    def reserve_once(self, *, principal: TrustedPrincipal, request_id: str,
                     expected_payload_sha256: str, expected_base_revision: int,
                     current_server_revision: int, send_key: str) -> dict:
        """Only first successful call returns `firstAttemptGranted=True`.

        Reservation is committed BEFORE the host can use this decision. It
        cannot be consumed twice, not even by the same caller with same key.
        """
        _sha(expected_payload_sha256)
        _key(send_key)
        _revision(current_server_revision)
        if expected_base_revision != current_server_revision:
            raise DispatchGateConflict("Stale server revision")
        with self._write() as conn:
            if conn.execute(
                "SELECT first_permits_enabled FROM dispatch_control WHERE singleton=1",
            ).fetchone()[0] != 1:
                raise PermissionError("Backup/recovery gate cannot issue dispatch permits")
            snapshot = self._snapshot(
                principal=principal, request_id=request_id,
                expected_base_revision=expected_base_revision,
                expected_payload_sha256=expected_payload_sha256,
                send_key=send_key, for_reservation=True,
            )
            if (snapshot["receiptState"] != "unknown"
                    or snapshot["receiptId"] is not None
                    or snapshot.get("historicalReceiptQuarantined") is not False):
                raise DispatchGateConflict("Quarantined historical evidence; no first dispatch")
            if conn.execute(
                "SELECT 1 FROM dispatch_reservations WHERE request_id=?", (request_id,),
            ).fetchone():
                raise DispatchGateConflict("First dispatch slot already reserved; query first")
            now = _now()
            try:
                conn.execute(
                    "INSERT INTO dispatch_reservations "
                    "(request_id,org_id,project_id,actor_id,session_id,payload_sha256,"
                    "base_revision,send_key,state,version,receipt_id,reserved_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,'reserved_before_network',1,NULL,?,?)",
                    (request_id, principal.org_id, snapshot["projectId"],
                     principal.user_id, principal.session_id, snapshot["payloadSha256"],
                     snapshot["baseRevision"], snapshot["sendKey"], now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise DispatchGateConflict("Request or send key already consumed") from exc
            row = self._get_unchecked(conn, request_id)
            self._audit(conn, row, "reserved_before_network")
            self._get(conn, request_id)
            return {
                **self._public(row, snapshot=snapshot), "firstAttemptGranted": True,
                "firstAttemptGrantIsSingleUse": True,
            }

    @staticmethod
    def _get_unchecked(conn, request_id):
        row = conn.execute(
            "SELECT * FROM dispatch_reservations WHERE request_id=?", (request_id,),
        ).fetchone()
        if row is None:
            raise DispatchGateError("Missing dispatch row")
        return dict(row)

    def _authenticated_row(self, conn, *, principal, request_id,
                           expected_base_revision, for_transition=False):
        snapshot = self._snapshot(
            principal=principal, request_id=request_id,
            expected_base_revision=expected_base_revision,
            for_reservation=for_transition,
        )
        row = self._get(conn, request_id)
        self._bound(row, principal, snapshot)
        return row, snapshot

    def status(self, *, principal: TrustedPrincipal, request_id: str,
               expected_base_revision: int) -> dict:
        """Read-only, with current HostRequestStore actor/session ACL recheck."""
        with self._connect() as conn:
            conn.execute("BEGIN")
            row, snapshot = self._authenticated_row(
                conn, principal=principal, request_id=request_id,
                expected_base_revision=expected_base_revision,
            )
            return self._public(row, snapshot=snapshot)

    def recovery_status(self, *, principal: TrustedPrincipal, request_id: str,
                        expected_base_revision: int, token: str = None,
                        gate_seal=None, outbox_seal=None) -> dict:
        """Only inspect the irreversible slot for the original actor.

        The current session is authorized by the host-owned outbox recovery
        read, while the gate still binds to the STORED original session,
        organization, project, actor, payload digest, revision and send key.
        This must never be called by reserve_once or grant a new attempt.
        """
        from mtr_host_principal_provenance import GATE_RECOVERY
        # Separate one-use gate and outbox HMAC audiences. Neither a Python
        # TrustedPrincipal nor a single reusable seal can authorize both.
        with self.outbox._sealed_recovery(
            principal=principal, token=token, seal=gate_seal,
            audience=GATE_RECOVERY,
        ) as verified:
            with self._connect() as conn:
                conn.execute("BEGIN")
                snapshot = self.outbox.recovery_snapshot(
                    principal=verified, request_id=request_id,
                    expected_base_revision=expected_base_revision,
                    token=token, seal=outbox_seal,
                )
                row = self._get(conn, request_id)
                for name, expected in (
                    ("org_id", snapshot["orgId"]),
                    ("project_id", snapshot["projectId"]),
                    ("actor_id", snapshot["actorId"]),
                    ("session_id", snapshot["originalSessionId"]),
                    ("payload_sha256", snapshot["payloadSha256"]),
                    ("base_revision", snapshot["baseRevision"]),
                    ("send_key", snapshot["sendKey"]),
                ):
                    if row[name] != expected:
                        raise DispatchGateConflict("recovery request/gate binding mismatch")
                return self._public(row, snapshot=snapshot)

    def mark_unknown_after_attempt(self, *, principal: TrustedPrincipal,
                                   request_id: str, expected_base_revision: int,
                                   expected_version: int) -> dict:
        """Record that outcome is unknown. Does NOT prove a packet was sent."""
        _version(expected_version)
        with self._write() as conn:
            row, snapshot = self._authenticated_row(
                conn, principal=principal, request_id=request_id,
                expected_base_revision=expected_base_revision,
                for_transition=True,
            )
            if row["version"] != expected_version or row["state"] != "reserved_before_network":
                raise DispatchGateConflict("Attempt already recorded or CAS changed")
            changed = conn.execute(
                "UPDATE dispatch_reservations SET state='unknown_after_attempt',"
                "version=version+1,updated_at=? "
                "WHERE request_id=? AND version=? AND state='reserved_before_network'",
                (_now(), request_id, expected_version),
            )
            if changed.rowcount != 1:
                raise DispatchGateConflict("Attempt CAS lost")
            result = self._get_unchecked(conn, request_id)
            self._audit(conn, result, "unknown_after_attempt")
            self._get(conn, request_id)
            return self._public(result, snapshot=snapshot)

    def observe_received(self, *, principal: TrustedPrincipal, request_id: str,
                         expected_base_revision: int, expected_version: int) -> dict:
        """Fail closed until an independent official finance verifier exists.

        Validated old SQLite observations and historical gate states are NOT
        official receipts. This API cannot mint or replay observed_received;
        forensic audit rows remain intact and scoped to their original actor.
        """
        _version(expected_version)
        with self._connect() as conn:
            conn.execute("BEGIN")
            row, _ = self._authenticated_row(
                conn, principal=principal, request_id=request_id,
                expected_base_revision=expected_base_revision,
                for_transition=True,
            )
            if row["version"] != expected_version:
                raise DispatchGateConflict("Receipt observation CAS changed")
            raise PermissionError("independent official Taraz receipt attestation unavailable")

    def audit_events(self, *, principal: TrustedPrincipal, request_id: str,
                     expected_base_revision: int) -> tuple[dict, ...]:
        """Inspect this request's immutable local events (no finance ledger)."""
        with self._connect() as conn:
            row, _ = self._authenticated_row(
                conn, principal=principal, request_id=request_id,
                expected_base_revision=expected_base_revision,
            )
            records = conn.execute(
                "SELECT version, action, receipt_sha256, recorded_at FROM dispatch_audit "
                "WHERE request_id=? ORDER BY version", (row["request_id"],),
            ).fetchall()
            return tuple({
                "version": event["version"], "action": event["action"],
                "receiptSha256": event["receipt_sha256"],
                "recordedAt": event["recorded_at"],
                "receiptVerification": "UNVERIFIED",
                "officialTarazReceipt": False,
            } for event in records)

    def backup_to(self, destination: Path) -> dict:
        """Create-only SQLite snapshot; backups are permanently query-only.

        Both source outbox and dispatch gate require separately coordinated
        backup epochs for a correct joined recovery. Copying a backup to a
        live path NEVER re-enables first dispatch. Only an independently
        reviewed migration may activate a new gate. This backup covers ONLY
        the local gate file and never overwrites a destination.
        """
        _path(destination)
        if destination == self.path:
            raise DispatchGateError("Backup must be a distinct database file")
        if destination.exists():
            raise FileExistsError("Backup destination exists")
        fd, temp_name = tempfile.mkstemp(
            prefix=".mtr-e2-dispatch-", suffix=".sqlite3", dir=destination.parent,
        )
        os.close(fd)
        temporary = Path(temp_name)
        try:
            with self._connect() as source:
                self._check_schema(source)
                with closing(sqlite3.connect(temporary)) as target:
                    source.backup(target)
            with closing(sqlite3.connect(temporary)) as verified:
                verified.execute("PRAGMA synchronous=FULL")
                self._check_schema(verified)
                verified.execute("BEGIN IMMEDIATE")
                verified.execute(
                    "UPDATE dispatch_control SET first_permits_enabled=0 WHERE singleton=1",
                )
                verified.commit()
                self._check_schema(verified)
            with open(temporary, "r+b") as stream:
                os.fsync(stream.fileno())
            os.link(temporary, destination)  # atomic create-if-absent
            return {"verified": True, "created": True, "path": str(destination)}
        finally:
            temporary.unlink(missing_ok=True)


__all__ = ["OneShotDispatchGate", "DispatchGateError", "DispatchGateConflict"]
