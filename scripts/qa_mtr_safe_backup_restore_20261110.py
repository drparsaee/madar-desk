"""Synthetic *metadata-only* 3-DB backup/restore validation for Madar/Taraz.

Strictly a disposable, independent QA rehearsal: no real profiles, service,
installed app, network, ledger, financial receipt, or deployment. The gate's
backup deliberately disables FIRST dispatch permits. A restored backup MUST
NEVER be treated as permission to replay a send.

All paths are created under a fresh TemporaryDirectory *owned by this process*.
Backups use each production class's create-only SQLite backup/archive API.
Restore makes a verified NEW SQLite file via sqlite3.backup plus atomic
create-if-absent hardlink. Neither an existing file nor a linked path is
overwritten. The JSON manifest is consistency evidence, not a signature or
independent official backup attestation.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import tempfile
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # Running a script from scripts/ does not automatically expose root modules.
    sys.path.insert(0, str(ROOT))
TARAZ_REGISTRY_SOURCE = Path(
    r"D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109"
    r"\taraz_mtr_peer_registry.py"
)
NAMES = ("outbox", "dispatch", "peer")
TABLES = {
    "outbox": ("requests", "observations", "audit"),
    "dispatch": ("dispatch_control", "dispatch_reservations", "dispatch_audit"),
    "peer": ("requests", "queries", "audit"),
}
PREFIX = "mtr-safe-three-db-qa-"
MANIFEST = "three-db-metadata-backup-manifest.json"
MAX_FILE_BYTES = 24 * 1024 * 1024
MAX_ROWS_PER_TABLE = 25000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class QABackupDenied(ValueError):
    """The synthetic QA backup/restore cannot be justified by available data."""


def _no_duplicate_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise QABackupDenied("duplicate_json_key")
        data[key] = value
    return data


def _unsafe(path: Path) -> bool:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        return bool(getattr(path.lstat(), "st_file_attributes", 0) &
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except FileNotFoundError:
        return False


def _no_links(path: Path):
    if not isinstance(path, Path) or not path.is_absolute():
        raise QABackupDenied("absolute_path_required")
    if any(_unsafe(item) for item in (path, *path.parents)):
        raise QABackupDenied("linked_or_junction_path")


def _safe_file(path: Path, *, missing_ok=False) -> bool:
    _no_links(path)
    if not path.exists():
        if missing_ok:
            return False
        raise QABackupDenied("required_file_missing")
    meta = path.lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
        raise QABackupDenied("nonregular_or_hardlinked_file")
    if not 0 < meta.st_size <= MAX_FILE_BYTES:
        raise QABackupDenied("empty_or_oversized_file")
    return True


def _sha(path: Path) -> str:
    _safe_file(path)
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    after = path.stat()
    if ((before.st_size, before.st_mtime_ns, before.st_ino) !=
            (after.st_size, after.st_mtime_ns, after.st_ino)):
        raise QABackupDenied("file_changed_while_hashing")
    return digest.hexdigest()


def _json(path: Path) -> dict:
    _safe_file(path)
    if path.stat().st_size > 16000:
        raise QABackupDenied("manifest_too_large")
    raw = path.read_bytes()
    try:
        record = json.loads(raw.decode("utf-8"),
                            object_pairs_hook=_no_duplicate_keys,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                QABackupDenied("invalid_numeric_constant")))
    except (UnicodeError, ValueError) as exc:
        raise QABackupDenied("manifest_invalid_json") from exc
    if not isinstance(record, dict):
        raise QABackupDenied("manifest_must_be_object")
    return record


def _json_bytes(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _fingerprint_rows(rows) -> str:
    # All row content (including blob bytes) participates in a canonical,
    # deterministic digest; unordered SQL insertion order is not trusted.
    def field(value):
        if isinstance(value, bytes):
            return {"blobHex": value.hex()}
        if value is None or type(value) in (str, int, float):
            return value
        raise QABackupDenied("unexpected_sqlite_column_type")
    encoded = [_json_bytes([field(value) for value in row]) for row in rows]
    digest = hashlib.sha256()
    for entry in sorted(encoded):
        digest.update(len(entry).to_bytes(8, "big") + entry)
    return digest.hexdigest()


def _sqlite_readback(path: Path, kind: str) -> dict:
    _safe_file(path)
    if kind not in NAMES:
        raise QABackupDenied("unsupported_store_kind")
    # mode=ro, SQLite query_only: this probe never creates/replaces a DB.
    uri = "file:" + quote(path.as_posix(), safe="/:\\") + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise QABackupDenied("sqlite_integrity_check_failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise QABackupDenied("sqlite_foreign_key_check_failed")
        if db.execute("PRAGMA user_version").fetchone() != (1,):
            raise QABackupDenied("unexpected_sqlite_schema_version")
        named = {name: entity for name, entity in db.execute(
            "SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
        for table in TABLES[kind]:
            if named.get(table) != "table":
                raise QABackupDenied("missing_required_sqlite_table:" + table)
        if kind == "peer":
            for table in TABLES[kind]:
                for op in ("update", "delete"):
                    if named.get(f"deny_{table}_{op}") != "trigger":
                        raise QABackupDenied("peer_immutability_trigger_missing")
        metrics = {}
        for table in TABLES[kind]:
            count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if type(count) is not int or count > MAX_ROWS_PER_TABLE:
                raise QABackupDenied("sqlite_table_row_limit_exceeded")
            digest = _fingerprint_rows(db.execute(f"SELECT * FROM {table}").fetchall())
            metrics[table] = {"rows": count, "rowsSha256": digest}
        if kind == "dispatch":
            controls = db.execute(
                "SELECT singleton,first_permits_enabled FROM dispatch_control").fetchall()
            if controls != [(1, 0)]:
                raise QABackupDenied("restored_dispatch_gate_not_permanently_disabled")
        return {"userVersion": 1, "tables": metrics, "bytes": path.stat().st_size,
                "sha256": _sha(path), "integrity": "ok", "queryOnly": True}


class DisposableQAScope:
    """Owns every path; no method can accept an arbitrary real user data path."""

    def __init__(self):
        self._temporary = tempfile.TemporaryDirectory(prefix=PREFIX)
        self.root = Path(self._temporary.name)
        self.active = True
        for name in ("live", "backups", "restored"):
            (self.root / name).mkdir(exist_ok=False)

    def close(self):
        if self.active:
            self._temporary.cleanup()
            self.active = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def location(self, group: str, kind: str) -> Path:
        self.check()
        if group not in ("live", "backups", "restored") or kind not in NAMES:
            raise QABackupDenied("invalid_disposable_path_selector")
        directory = self.root / group
        _no_links(directory)
        if not directory.is_dir():
            raise QABackupDenied("missing_disposable_directory")
        return directory / (kind + ".sqlite3")

    def check(self):
        if not self.active or not self.root.is_dir() or not self.root.name.startswith(PREFIX):
            raise QABackupDenied("closed_or_non_disposable_scope")
        _no_links(self.root)

    def manifest(self):
        self.check()
        return self.root / "backups" / MANIFEST


def _source_module(path: Path):
    _safe_file(path)
    spec = importlib.util.spec_from_file_location(
        "mtr_synthetic_peer_backup_source", path)
    if spec is None or spec.loader is None:
        raise QABackupDenied("isolated_peer_source_unavailable")
    module = importlib.util.module_from_spec(spec)
    # dataclasses need an importlib-registered module during class creation.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        for name in ("TarazPeerRegistry", "PeerConfig"):
            if not isinstance(getattr(module, name, None), type):
                raise QABackupDenied("isolated_peer_capability_missing")
        if not callable(getattr(module.TarazPeerRegistry, "archive_to", None)):
            raise QABackupDenied("peer_archive_capability_missing")
        return module
    finally:
        sys.modules.pop(spec.name, None)


def verify_capabilities(outbox, dispatch, peer):
    for instance, method in ((outbox, "backup_to"), (dispatch, "backup_to"),
                             (peer, "archive_to")):
        if not callable(getattr(instance, method, None)):
            raise QABackupDenied("required_create_only_backup_api_missing:" + method)


def make_backups(scope: DisposableQAScope, outbox, dispatch, peer) -> dict:
    """Create 3 snapshots; never store a hash-only manifest as authority."""
    scope.check()
    verify_capabilities(outbox, dispatch, peer)
    sources = (outbox.path, dispatch.path, peer.path)
    if any(source != scope.location("live", kind)
           for source, kind in zip(sources, NAMES)):
        raise QABackupDenied("source_database_outside_disposable_scope")
    if len(set(sources)) != 3:
        raise QABackupDenied("duplicate_source_database_path")
    for source in sources:
        _safe_file(source)
    if scope.manifest().exists() or scope.manifest().is_symlink():
        raise FileExistsError("existing_backup_manifest")
    for kind in NAMES:
        _safe_file(scope.location("backups", kind), missing_ok=True)
        if scope.location("backups", kind).exists():
            raise FileExistsError("backup_already_exists")
    results = {}
    for kind, instance in zip(NAMES, (outbox, dispatch, peer)):
        target = scope.location("backups", kind)
        issued = (instance.archive_to(target) if kind == "peer"
                  else instance.backup_to(target))
        if not isinstance(issued, dict) or issued.get(
                "created") is not True or kind == "peer" and (
                issued.get("liveQueryCapacityReleased") is not False):
            raise QABackupDenied("source_backup_api_did_not_prove_create_only")
        results[kind] = _sqlite_readback(target, kind)
        if kind == "outbox" and issued.get("verified") is not True:
            raise QABackupDenied("source_outbox_backup_not_verified")
        if kind == "dispatch" and issued.get("verified") is not True:
            raise QABackupDenied("source_dispatch_backup_not_verified")
        if kind == "peer" and issued.get("archiveSha256") != results[kind]["sha256"]:
            raise QABackupDenied("peer_archive_report_digest_mismatch")
    doc = {"schema": 1, "scope": "DISPOSABLE_NONFINANCIAL_QA_ONLY",
           "kinds": list(NAMES), "snapshots": results,
           "restoreActivationAllowed": False, "financialReceiptVerified": False,
           "peerOfficiallyAuthenticated": False}
    with scope.manifest().open("xb") as file:
        file.write(_json_bytes(doc))
        file.flush()
        os.fsync(file.fileno())
    return doc


def validate_backups(scope: DisposableQAScope) -> dict:
    scope.check()
    manifest = _json(scope.manifest())
    if (set(manifest) != {"schema", "scope", "kinds", "snapshots",
                         "restoreActivationAllowed", "financialReceiptVerified",
                         "peerOfficiallyAuthenticated"} or
            manifest["schema"] != 1 or
            manifest["scope"] != "DISPOSABLE_NONFINANCIAL_QA_ONLY" or
            manifest["kinds"] != list(NAMES) or
            manifest["restoreActivationAllowed"] is not False or
            manifest["financialReceiptVerified"] is not False or
            manifest["peerOfficiallyAuthenticated"] is not False or
            type(manifest["snapshots"]) is not dict or
            set(manifest["snapshots"]) != set(NAMES)):
        raise QABackupDenied("backup_manifest_incomplete_or_ambiguous")
    actual = {x.name for x in (scope.root / "backups").iterdir()}
    if actual != {MANIFEST} | {kind + ".sqlite3" for kind in NAMES}:
        raise QABackupDenied("backup_missing_extra_or_duplicate_file")
    for kind in NAMES:
        current = _sqlite_readback(scope.location("backups", kind), kind)
        if current != manifest["snapshots"][kind]:
            raise QABackupDenied("backup_sha_integrity_or_content_mismatch:" + kind)
    return manifest


def _restore_new_file(source: Path, target: Path):
    """Read-only verified SQLite source to *create-only* distinct destination."""
    _safe_file(source)
    _no_links(target)
    if target.exists() or target.is_symlink():
        raise FileExistsError("restore_target_already_exists")
    if not target.parent.is_dir():
        raise QABackupDenied("restore_directory_missing")
    fd, tmp_name = tempfile.mkstemp(prefix=".mtr-restore-", suffix=".sqlite3",
                                     dir=target.parent)
    os.close(fd)
    temp = Path(tmp_name)
    try:
        uri = "file:" + quote(source.as_posix(), safe="/:\\") + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as read:
            read.execute("PRAGMA query_only=ON")
            with closing(sqlite3.connect(str(temp))) as output:
                read.backup(output)
        with temp.open("r+b") as output:
            os.fsync(output.fileno())
        # No overwrites even after late unexpected race.
        os.link(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def restore_backups(scope: DisposableQAScope) -> dict:
    """All source backups revalidated before making ANY restored destination."""
    manifest = validate_backups(scope)
    for kind in NAMES:
        target = scope.location("restored", kind)
        if target.exists() or target.is_symlink():
            raise FileExistsError("restore_target_already_exists")
    restored = {}
    for kind in NAMES:
        _restore_new_file(scope.location("backups", kind),
                          scope.location("restored", kind))
        verified = _sqlite_readback(scope.location("restored", kind), kind)
        # SQLite rebackup can rewrite page layout; demand full table fingerprints
        # rather than wrongly treating byte-hash equality as a requirement.
        if (verified["userVersion"] != manifest["snapshots"][kind]["userVersion"] or
                verified["tables"] != manifest["snapshots"][kind]["tables"]):
            raise QABackupDenied("restored_metadata_not_identical_to_backup:" + kind)
        restored[kind] = verified
    return {"restoredCount": len(restored), "restored": restored,
            "restoreIntoNewDistinctFilesOnly": True,
            "reEnabledFirstDispatch": False,
            "officialFinanceReceiptVerified": False}


def exercise_synthetic_roundtrip(scope: DisposableQAScope) -> dict:
    """One realistic fixed synthetic state transition, no peer/network call."""
    scope.check()
    from mtr_host_request_store import HostRequestStore, TrustedPrincipal
    from mtr_e2_dispatch_gate import OneShotDispatchGate, DispatchGateConflict
    taraz = _source_module(TARAZ_REGISTRY_SOURCE)
    from mtr_peer_envelope import (sign_request, verify_request, sign_receipt_query,
                                   verify_receipt_query, verify_peer_receipt,
                                   query_first_recovery_decision)
    if not callable(getattr(taraz.TarazPeerRegistry, "archive_to", None)):
        raise QABackupDenied("peer_archive_unsupported")
    actor = TrustedPrincipal(
        user_id="synthetic-editor", org_id="synthetic-org",
        session_id="synthetic-login", role="editor",
        project_ids=frozenset({"synthetic-project"}),
        permissions=frozenset({"mtr.prepare", "mtr.manual_send", "mtr.read"}),
        authenticated=True, session_valid=True)
    outbox = HostRequestStore(scope.location("live", "outbox"))
    gate = OneShotDispatchGate(scope.location("live", "dispatch"), outbox)
    conf = taraz.PeerConfig(
        "synthetic-org", "synthetic-madar-host", "synthetic-m-key",
        "synthetic-taraz-peer", "synthetic-t-key", b"m" * 32, b"t" * 32)
    peer = taraz.TarazPeerRegistry(scope.location("live", "peer"), conf)
    request_id = "a" * 32
    now = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
    payload = {"schema": 1, "source": "madar", "id": request_id,
               "taskId": "synthetic-task", "projectId": "synthetic-project",
               "title": "Synthetic packaging QA nonfinancial",
               "createdUtc": now.isoformat()}
    prepared = outbox.prepare_request(
        principal=actor, request_id=request_id, payload=payload,
        base_revision=7, current_server_revision=7,
        prepare_key="synthetic-prep-0001", explicit_manual_action=True)
    sent = outbox.manual_send(
        principal=actor, request_id=request_id,
        expected_payload_sha256=prepared["payloadSha256"],
        expected_base_revision=7, current_server_revision=7,
        send_key="synthetic-send-0001", explicit_manual_action=True)
    grant = gate.reserve_once(
        principal=actor, request_id=request_id,
        expected_payload_sha256=prepared["payloadSha256"],
        expected_base_revision=7, current_server_revision=7,
        send_key="synthetic-send-0001")
    if grant.get("firstAttemptGranted") is not True:
        raise QABackupDenied("one_shot_reservation_not_created")
    uncertain = gate.mark_unknown_after_attempt(
        principal=actor, request_id=request_id,
        expected_base_revision=7, expected_version=1)
    if not uncertain.get("mustQueryFirst"):
        raise QABackupDenied("post_crash_query_first_not_retained")
    wire = sign_request(
        payload, organization_id="synthetic-org",
        sender_id="synthetic-madar-host", actor_role="editor",
        key_id="synthetic-m-key", request_id=request_id,
        purpose="finance_review_request", issued_at=now,
        expires_at=now + timedelta(seconds=60), secret=b"m" * 32,
        authorized=True, explicit_manual_action=True)
    # Synthetic in-process verified transport flag is NOT actual TLS evidence.
    verified = verify_request(
        wire, secret=b"m" * 32, now=now,
        expected_organization_id="synthetic-org",
        expected_sender_id="synthetic-madar-host",
        expected_key_id="synthetic-m-key", purpose="finance_review_request",
        allowed_actor_roles=frozenset({"editor"}))
    accepted = peer.intake(wire, now=now, verified_transport_peer=True)
    if accepted.get("financialEventCreated") is not False:
        raise QABackupDenied("synthetic_peer_claimed_finance")
    query_wire = sign_receipt_query(
        verified, query_request_id="b" * 32,
        key_id="synthetic-m-key", issued_at=now,
        expires_at=now + timedelta(seconds=60), secret=b"m" * 32)
    query = verify_receipt_query(
        query_wire, secret=b"m" * 32, now=now,
        expected_organization_id="synthetic-org",
        expected_sender_id="synthetic-madar-host",
        expected_key_id="synthetic-m-key",
        allowed_actor_roles=frozenset({"editor"}))
    signed_reply = peer.query_receipt(
        query_wire, now=now, verified_transport_peer=True)
    peer_result = verify_peer_receipt(
        signed_reply, original=verified, query=query,
        secret=b"t" * 32, now=now,
        expected_peer_id="synthetic-taraz-peer",
        expected_peer_key_id="synthetic-t-key")
    if query_first_recovery_decision(
            original=verified, query=query, receipt=peer_result,
            prior_manual_authorized=True, prior_request_id=request_id,
            prior_payload_sha256=verified.payload_sha256) != "observe_peer_claim_received":
        raise QABackupDenied("synthetic_query_first_not_received")
    backups = make_backups(scope, outbox, gate, peer)
    proof = restore_backups(scope)
    restarted_outbox = HostRequestStore(scope.location("restored", "outbox"))
    restarted_gate = OneShotDispatchGate(scope.location("restored", "dispatch"),
                                          restarted_outbox)
    restarted_peer = taraz.TarazPeerRegistry(scope.location("restored", "peer"), conf)
    if (restarted_outbox.receipt_status(
            principal=actor, request_id=request_id,
            expected_base_revision=7)["receiptState"] != "unknown" or
            restarted_outbox.request_snapshot(
                principal=actor, request_id=request_id,
                expected_base_revision=7)["payloadSha256"] !=
            prepared["payloadSha256"]):
        raise QABackupDenied("restored_outbox_identity_or_unknown_receipt_lost")
    gate_status = restarted_gate.status(
        principal=actor, request_id=request_id, expected_base_revision=7)
    if (gate_status.get("mustQueryFirst") is not True or
            gate_status.get("canAutoRetry") is not False or
            gate_status.get("state") != "unknown_after_attempt"):
        raise QABackupDenied("restored_dispatch_query_first_not_enforced")
    try:
        restarted_gate.reserve_once(
            principal=actor, request_id=request_id,
            expected_payload_sha256=prepared["payloadSha256"],
            expected_base_revision=7, current_server_revision=7,
            send_key="synthetic-send-0001")
    except (PermissionError, DispatchGateConflict):
        second_dispatch_denied = True
    else:
        raise QABackupDenied("restored_gate_minted_second_dispatch")
    if restarted_peer.intake(wire, now=now, verified_transport_peer=True).get(
            "idempotent") is not True:
        raise QABackupDenied("restored_peer_request_replay_not_idempotent")
    repeated = restarted_peer.query_receipt(
        query_wire, now=now, verified_transport_peer=True)
    verified_repeat = verify_peer_receipt(
        repeated, original=verified, query=query,
        secret=b"t" * 32, now=now,
        expected_peer_id="synthetic-taraz-peer",
        expected_peer_key_id="synthetic-t-key")
    if verified_repeat.payload["lookupStatus"] != "received":
        raise QABackupDenied("restored_peer_query_first_lost")
    if (restarted_peer.query_capacity_status()["used"] != 1 or
            restarted_peer.query_capacity_status()["automaticPruningAllowed"]):
        raise QABackupDenied("restored_peer_query_replay_binding_missing")
    return {
        "syntheticOnly": True, "threeBackupsVerified": True,
        "threeRestoresNewAndDistinct": proof["restoredCount"] == 3,
        "sourceBackupManifestSha256": _sha(scope.manifest()),
        "backupSha256": {key: value["sha256"]
                         for key, value in backups["snapshots"].items()},
        "restoredRowsMatchBackup": True,
        "restartedUnknownStillQueryFirst": True,
        "secondFirstDispatchDenied": second_dispatch_denied,
        "peerRequestIdempotentAfterRestart": True,
        "peerQueryBindingSurvivesRestart": True,
        "officialFinanceReceiptVerified": False,
        "realTlsTransportAuthenticated": False,
        "restoredDispatchEnabled": False,
        "threeDatabaseAtomicEpochVerified": False,
        "realServiceRestartOrPowerLossVerified": False,
        "peerRuntimeSecretsBackedUp": False,
    }


def main() -> int:
    try:
        with DisposableQAScope() as scope:
            result = exercise_synthetic_roundtrip(scope)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({
            "syntheticOnly": True, "status": "FAIL_CLOSED",
            "reason": type(exc).__name__ + ": " + str(exc)[:200],
            "officialFinanceReceiptVerified": False,
            "restoredDispatchEnabled": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
