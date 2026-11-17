"""Synthetic Madar/Taraz upgrade -> exact-checkpoint rollback; NEVER install.

Only disposable, newly created 3-DB metadata files. Uses the existing
qa_mtr_safe_backup_restore_20261110 module READ-ONLY for native create-only
backup generation and validation. Both immutable *non-release* QA artifacts
and their source/provenance reports must match the independent external
SHA-256 pins below. They are NEVER executed or promoted to release builds.

The upgrade is an explicit, local metadata-mutation simulation, NOT a real
application-version migration, service restart, power failure, TLS, ledger or
installer. Rollback copies already disabled-gate SQLite checkpoint bytes into
THREE NEW DISTINCT PATHS, with independent SQLite/row/byte digest readback.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
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
    sys.path.insert(0, str(ROOT))

from scripts import qa_mtr_safe_backup_restore_20261110 as base

MADAR_BUNDLE = Path(
    r"D:\CoS-Test\MTR-MADAR-TARAZ-QA-BUNDLE-20261110"
    r"\run-20261110-144128-10416-207ce8ba"
)
TARAZ_BUNDLE = Path(
    r"D:\CoS-Test\MTR-TARAZ-QA-BUNDLE-20261110"
    r"\qa-52f6b2776362"
)
EXE_SHA = {
    "madar": "11a9726f976bd633c6eb120b939e1d7aab63c6ca99a3e3b5a5cc57bd967ed4f9",
    "taraz": "f3c4d65418d8f9d80a40618c01bb1534841ca18bf863fd9d09d5ca0fb8449662",
}
REPORT_SHA = {
    "madar": "6123ca4e8f21673073e5644d2d09aa7ee721870ff51e92879dd3396cdc5c45dc",
    "madar_provenance": "030ddf338b968c9d10647ffff8e234ed1ee02ea81680472aaccf56fa8a4010ab",
    "madar_source_inventory": "36623655d272ba3cb85f63bc7a8ea3233ab1ca0f26b99b5e453757b357ad7262",
    "taraz": "bd1d642a11991d9ab20dd99c2d47af66a1f5f76751d403535cad67f2fd03b16c",
}
PACKAGE_SHA = {
    "madar": "8964aa5f58020b8459fea983a18de6533704114109eaf2af3c573e5b9cba1b77",
    "taraz": "5833140a29b7e8fd18640e2c54108723d052f8fb9fccc16bf675868cd2fa52c5",
}
SNAPSHOT_SHA = {
    "madar": "f1fcade603d985d7755990422748b6b83428343c6de6e60e869b651afa3c8c18",
    "taraz": "cedd3c8cc51802afe0270cbd08971a1f67347ed3a269d7ec5908fe4c62b6f0cc",
}
VERSION = {"madar": "1.0.23", "taraz": "1.0.0"}
PEER_SOURCE_SHA = "cf423bc58bc6dd8fd78d76c1c28e24b8646356f172f084a3b954339602241ade"
MADAR_EXE = MADAR_BUNDLE / "exe-dist" / (
    "Madar-Taraz-Connection-QA-20261110-NONRELEASE.exe")
TARAZ_EXE = TARAZ_BUNDLE / "pyinstaller" / "dist" / (
    "Taraz-MTR-QA-52f6b2776362.exe")
REQUEST_ID = "a" * 32
UPGRADED_REQUEST_ID = "c" * 32
ROLLBACK_FOLDER = "rollback-new-disposable"
UPGRADE_FOLDER = "upgrade-simulation"
PLAN_NAME = "synthetic-upgrade-plan.json"
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_META = 2_000_000


class RollbackDenied(ValueError):
    """An untrusted candidate, unsafe destination or changed checkpoint."""


def _safe_read(path: Path, expected_sha: str, *, max_size: int) -> bytes:
    if not isinstance(expected_sha, str) or not _HEX64.fullmatch(expected_sha):
        raise RollbackDenied("unknown_or_missing_source_sha256_pin")
    base._no_links(path)
    if not path.is_file() or path.is_symlink():
        raise RollbackDenied("source_artifact_file_missing_or_linked")
    meta = path.lstat()
    if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or
            not 0 < meta.st_size <= max_size):
        raise RollbackDenied("source_artifact_invalid_or_oversized")
    digest = hashlib.sha256()
    chunks = []
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
            if max_size <= _MAX_META:
                chunks.append(block)
    after = path.lstat()
    if (meta.st_size, meta.st_mtime_ns, meta.st_ino) != (
            after.st_size, after.st_mtime_ns, after.st_ino):
        raise RollbackDenied("source_artifact_changed_during_read")
    if digest.hexdigest() != expected_sha:
        raise RollbackDenied("source_artifact_or_manifest_pin_mismatch")
    return b"".join(chunks)


def _read_json(path: Path, expected_sha: str, *, cap: int = _MAX_META) -> dict:
    content = _safe_read(path, expected_sha, max_size=cap)
    try:
        obj = json.loads(content.decode("utf-8"),
                         object_pairs_hook=base._no_duplicate_keys,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             RollbackDenied("invalid_json_constant")))
    except (UnicodeError, ValueError) as exc:
        raise RollbackDenied("invalid_pinned_source_report_json") from exc
    if not isinstance(obj, dict):
        raise RollbackDenied("expected_source_manifest_object")
    return obj


def _validate_artifact_reports(madar: dict, provenance: dict,
                               inventory: dict, taraz: dict,
                               madar_package: dict, taraz_package: dict) -> dict:
    """Pure metadata contract check; testing seam cannot bypass file SHA pins."""
    if not all(type(data) is dict for data in (
            madar, provenance, inventory, taraz, madar_package, taraz_package)):
        raise RollbackDenied("invalid_pinned_report_type")
    application = madar.get("application")
    if (madar.get("purpose") != "QA_ONLY_NON_RELEASE" or
            madar.get("status") != "QA_BUILT_NON_RELEASE" or
            madar.get("schemaVersion") != 1 or
            madar.get("sourceSnapshotTreeSha256") != SNAPSHOT_SHA["madar"] or
            madar.get("sourceFileCount") != 6501 or
            not isinstance(application, dict) or
            application.get("sha256") != EXE_SHA["madar"] or
            application.get("releaseReady") is not False or
            application.get("filename") != MADAR_EXE.name or
            provenance.get("purpose") != "NON_RELEASE_QA" or
            provenance.get("notFunctionalTestOrReleaseApproval") is not True or
            provenance.get("sourceSnapshotTreeSha256") != SNAPSHOT_SHA["madar"] or
            provenance.get("sourceFileCount") != 6501 or
            inventory.get("sourceSnapshotTreeSha256") != SNAPSHOT_SHA["madar"] or
            inventory.get("fileCount") != 6501 or
            not isinstance(inventory.get("files"), dict) or
            len(inventory["files"]) != 6501):
        raise RollbackDenied("unknown_or_incomplete_madar_qa_source_provenance")
    files = inventory["files"]
    if (files.get("package.json", {}).get("sha256") != PACKAGE_SHA["madar"] or
            files.get("native_app.py", {}).get("sha256") !=
            provenance.get("nativeSourceSha256") or
            files.get("src/App.jsx", {}).get("sha256") !=
            provenance.get("uiSourceSha256")):
        raise RollbackDenied("madar_qa_source_file_pin_disagreement")
    fingerprint = hashlib.sha256()
    for relative, record in sorted(files.items()):
        if (not isinstance(relative, str) or
                not isinstance(record, dict) or
                not _HEX64.fullmatch(str(record.get("sha256"))) or
                type(record.get("bytes")) is not int or record["bytes"] < 0):
            raise RollbackDenied("invalid_pinned_source_inventory_entry")
        fingerprint.update((relative + "\0" + record["sha256"] + "\n").encode("utf-8"))
    if fingerprint.hexdigest() != SNAPSHOT_SHA["madar"]:
        raise RollbackDenied("madar_source_tree_inventory_digest_invalid")
    if (taraz.get("status") != "QA_BUNDLE_VERIFIED" or
            taraz.get("qaOnly") is not True or
            taraz.get("releaseReady") is not False or
            taraz.get("installed") is not False or
            taraz.get("realLedgerAccessed") is not False or
            taraz.get("sourceInputCount") != 120 or
            taraz.get("sourceSnapshotSha256") != SNAPSHOT_SHA["taraz"] or
            taraz.get("exeSha256") != EXE_SHA["taraz"] or
            taraz.get("packedNativeInboxMethods", {}).get(
                "tarazIntegrationRecover") is not True or
            taraz.get("packedDurableReview", {}).get(
                "sourceBoundDurableIntentCode") is not True):
        raise RollbackDenied("unknown_or_incomplete_taraz_qa_source_provenance")
    if (madar_package.get("name") != "madar-desk" or
            taraz_package.get("name") != "taraz-accounting" or
            madar_package.get("version") != VERSION["madar"] or
            taraz_package.get("version") != VERSION["taraz"]):
        raise RollbackDenied("unknown_or_mismatched_source_application_version")
    return {
        "versions": VERSION.copy(), "qaOnly": True,
        "installerOrProductionReleaseVerified": False,
        "artifactSha256": EXE_SHA.copy(), "sourceSnapshotSha256": SNAPSHOT_SHA.copy(),
        "madarSourceFileCount": 6501, "tarazReportedSourceFileCount": 120,
    }


def verify_both_artifact_pins() -> dict:
    """External pinned files only; never open or run an executable."""
    _safe_read(MADAR_EXE, EXE_SHA["madar"], max_size=32_000_000)
    _safe_read(TARAZ_EXE, EXE_SHA["taraz"], max_size=32_000_000)
    madar = _read_json(MADAR_BUNDLE / "qa-build-result.json", REPORT_SHA["madar"])
    provenance = _read_json(
        MADAR_BUNDLE / "qa-provenance.json", REPORT_SHA["madar_provenance"])
    inventory = _read_json(
        MADAR_BUNDLE / "source-input-sha256.json",
        REPORT_SHA["madar_source_inventory"])
    taraz = _read_json(TARAZ_BUNDLE / "qa-build-report.json", REPORT_SHA["taraz"])
    madar_pkg = _read_json(
        MADAR_BUNDLE / "source" / "package.json", PACKAGE_SHA["madar"])
    taraz_pkg = _read_json(
        TARAZ_BUNDLE / "snapshot" / "package.json", PACKAGE_SHA["taraz"])
    _safe_read(TARAZ_BUNDLE / "snapshot" / "taraz_mtr_peer_registry.py",
               PEER_SOURCE_SHA, max_size=1_000_000)
    _safe_read(base.TARAZ_REGISTRY_SOURCE, PEER_SOURCE_SHA, max_size=1_000_000)
    return _validate_artifact_reports(
        madar, provenance, inventory, taraz, madar_pkg, taraz_pkg)


def _qa_principal():
    from mtr_host_request_store import TrustedPrincipal
    return TrustedPrincipal(
        user_id="qa-editor", org_id="qa-org", session_id="qa-session",
        role="editor", project_ids=frozenset({"qa-project"}),
        permissions=frozenset({"mtr.prepare", "mtr.manual_send", "mtr.read"}),
        authenticated=True, session_valid=True)


def _payload(request_id: str):
    return {"schema": 1, "source": "madar", "id": request_id,
            "taskId": "qa-task-" + request_id[:8], "projectId": "qa-project",
            "title": "QA synthetic-only MTR rollback row",
            "createdUtc": "2026-11-10T12:00:00+00:00"}


def _authorize_and_consume(outbox, gate, request_id: str) -> dict:
    who = _qa_principal()
    prepared = outbox.prepare_request(
        principal=who, request_id=request_id, payload=_payload(request_id),
        base_revision=7, current_server_revision=7,
        prepare_key="qa-prepare-" + request_id[:8],
        explicit_manual_action=True)
    outbox.manual_send(
        principal=who, request_id=request_id,
        expected_payload_sha256=prepared["payloadSha256"],
        expected_base_revision=7, current_server_revision=7,
        send_key="qa-send-" + request_id[:8], explicit_manual_action=True)
    first = gate.reserve_once(
        principal=who, request_id=request_id,
        expected_payload_sha256=prepared["payloadSha256"],
        expected_base_revision=7, current_server_revision=7,
        send_key="qa-send-" + request_id[:8])
    if first.get("firstAttemptGranted") is not True:
        raise RollbackDenied("synthetic_initial_dispatch_not_reserved")
    second = gate.mark_unknown_after_attempt(
        principal=who, request_id=request_id,
        expected_base_revision=7, expected_version=1)
    if (second.get("mustQueryFirst") is not True or
            second.get("canAutoRetry") is not False):
        raise RollbackDenied("synthetic_query_first_precondition_not_met")
    return prepared


def _peer_config(taraz):
    return taraz.PeerConfig(
        "qa-org", "qa-madar", "qa-m-key", "qa-taraz",
        "qa-t-key", b"m" * 32, b"t" * 32)


def _peer_metadata(peer, request_id: str, query_id: str, now: datetime) -> dict:
    from mtr_peer_envelope import (
        sign_request, verify_request, sign_receipt_query,
        verify_receipt_query, verify_peer_receipt, query_first_recovery_decision,
    )
    wire = sign_request(
        _payload(request_id), organization_id="qa-org", sender_id="qa-madar",
        actor_role="editor", key_id="qa-m-key", request_id=request_id,
        purpose="finance_review_request", issued_at=now,
        expires_at=now + timedelta(seconds=60),
        secret=b"m" * 32, authorized=True, explicit_manual_action=True)
    original = verify_request(
        wire, secret=b"m" * 32, now=now,
        expected_organization_id="qa-org", expected_sender_id="qa-madar",
        expected_key_id="qa-m-key", purpose="finance_review_request",
        allowed_actor_roles=frozenset({"editor"}))
    received = peer.intake(wire, now=now, verified_transport_peer=True)
    if received.get("financialEventCreated") is not False:
        raise RollbackDenied("synthetic_peer_claimed_finance")
    query_wire = sign_receipt_query(
        original, query_request_id=query_id, key_id="qa-m-key",
        issued_at=now, expires_at=now + timedelta(seconds=60), secret=b"m" * 32)
    query = verify_receipt_query(
        query_wire, secret=b"m" * 32, now=now,
        expected_organization_id="qa-org", expected_sender_id="qa-madar",
        expected_key_id="qa-m-key", allowed_actor_roles=frozenset({"editor"}))
    receipt = peer.query_receipt(query_wire, now=now, verified_transport_peer=True)
    checked = verify_peer_receipt(
        receipt, original=original, query=query, secret=b"t" * 32,
        now=now, expected_peer_id="qa-taraz", expected_peer_key_id="qa-t-key")
    if (query_first_recovery_decision(
            original=original, query=query, receipt=checked,
            prior_manual_authorized=True, prior_request_id=request_id,
            prior_payload_sha256=original.payload_sha256)
            != "observe_peer_claim_received"):
        raise RollbackDenied("synthetic_peer_query_first_not_preserved")
    return {"requestWire": wire, "queryWire": query_wire,
            "clock": now, "lookupStatus": checked.payload["lookupStatus"]}


def _first_state(scope: base.DisposableQAScope):
    from mtr_host_request_store import HostRequestStore
    from mtr_e2_dispatch_gate import OneShotDispatchGate
    scope.check()
    taraz = base._source_module(base.TARAZ_REGISTRY_SOURCE)
    outbox = HostRequestStore(scope.location("live", "outbox"))
    gate = OneShotDispatchGate(scope.location("live", "dispatch"), outbox)
    peer = taraz.TarazPeerRegistry(
        scope.location("live", "peer"), _peer_config(taraz))
    first = _authorize_and_consume(outbox, gate, REQUEST_ID)
    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    peer_seed = _peer_metadata(peer, REQUEST_ID, "b" * 32, now)
    return {"outbox": outbox, "gate": gate, "peer": peer,
            "taraz": taraz, "prepared": first, "peerSeed": peer_seed}


def make_upgrade_plan(pins: dict, checkpoint_sha: str) -> dict:
    if not isinstance(pins, dict) or not _HEX64.fullmatch(str(checkpoint_sha)):
        raise RollbackDenied("missing_synthetic_checkpoint_provenance")
    return {
        "schema": 1, "scope": "DISPOSABLE_QA_NO_INSTALL",
        "fromMetadataEpoch": 1, "toMetadataEpoch": 2,
        "sourceAppVersions": dict(pins["versions"]),
        "sourceArtifactSha256": dict(pins["artifactSha256"]),
        "sourceSnapshotSha256": dict(pins["sourceSnapshotSha256"]),
        "checkpointManifestSha256": checkpoint_sha,
        "mutations": ["synthetic_outbox_intent", "synthetic_consumed_dispatch_slot",
                      "synthetic_peer_query"],
        "officialFinancePosting": False,
        "actualInstallerOrMigrationRun": False,
        "crossStoreAtomicityVerified": False,
    }


def validate_upgrade_plan(plan: dict, pins: dict, checkpoint_sha: str):
    if (type(plan) is not dict or
            set(plan) != {
                "schema", "scope", "fromMetadataEpoch", "toMetadataEpoch",
                "sourceAppVersions", "sourceArtifactSha256",
                "sourceSnapshotSha256", "checkpointManifestSha256",
                "mutations", "officialFinancePosting",
                "actualInstallerOrMigrationRun", "crossStoreAtomicityVerified",
            } or plan["schema"] != 1 or
            plan["scope"] != "DISPOSABLE_QA_NO_INSTALL" or
            plan["fromMetadataEpoch"] != 1 or plan["toMetadataEpoch"] != 2 or
            plan["sourceAppVersions"] != VERSION or
            plan["sourceAppVersions"] != pins.get("versions") or
            plan["sourceArtifactSha256"] != EXE_SHA or
            plan["sourceArtifactSha256"] != pins.get("artifactSha256") or
            plan["sourceSnapshotSha256"] != SNAPSHOT_SHA or
            plan["sourceSnapshotSha256"] != pins.get("sourceSnapshotSha256") or
            plan["checkpointManifestSha256"] != checkpoint_sha or
            plan["mutations"] != [
                "synthetic_outbox_intent", "synthetic_consumed_dispatch_slot",
                "synthetic_peer_query"] or
            plan["officialFinancePosting"] is not False or
            plan["actualInstallerOrMigrationRun"] is not False or
            plan["crossStoreAtomicityVerified"] is not False):
        raise RollbackDenied("unknown_source_or_version_or_untrusted_upgrade_plan")


def _plan_file(scope: base.DisposableQAScope, plan: dict) -> Path:
    scope.check()
    target = scope.root / UPGRADE_FOLDER
    base._no_links(target)
    target.mkdir(exist_ok=False)
    result = target / PLAN_NAME
    with result.open("xb") as file:
        file.write(base._json_bytes(plan))
        file.flush()
        os.fsync(file.fileno())
    return result


def verify_disposable_upgrade_plan_file(
        scope: base.DisposableQAScope, expected_sha: str,
        pins: dict, checkpoint_sha: str) -> dict:
    """Read/rehash a local synthetic plan, never treat it as a signed approval."""
    scope.check()
    path = scope.root / UPGRADE_FOLDER / PLAN_NAME
    base._no_links(path)
    if not _HEX64.fullmatch(str(expected_sha)) or base._sha(path) != expected_sha:
        raise RollbackDenied("synthetic_upgrade_plan_changed_or_unknown")
    plan = base._json(path)
    validate_upgrade_plan(plan, pins, checkpoint_sha)
    if base._sha(path) != expected_sha:
        raise RollbackDenied("synthetic_upgrade_plan_changed_during_validation")
    return plan


def _synthetic_upgrade(scope, state, plan, pins, checkpoint_sha) -> dict:
    validate_upgrade_plan(plan, pins, checkpoint_sha)
    scope.check()
    for kind in base.NAMES:
        instance = state["gate"] if kind == "dispatch" else state[kind]
        if instance.path != scope.location("live", kind):
            raise RollbackDenied("attempted_upgrade_outside_disposable_scope")
    later_prepared = _authorize_and_consume(
        state["outbox"], state["gate"], UPGRADED_REQUEST_ID)
    now = state["peerSeed"]["clock"]
    changed_peer = _peer_metadata(state["peer"], UPGRADED_REQUEST_ID, "d" * 32, now)
    if changed_peer["lookupStatus"] != "received":
        raise RollbackDenied("synthetic_upgraded_peer_query_unknown")
    now_snapshots = {}
    for kind in base.NAMES:
        if kind == "dispatch":
            with closing(sqlite3.connect(
                    "file:" + quote(scope.location("live", kind).as_posix(),
                                    safe="/:\\") + "?mode=ro", uri=True)) as conn:
                conn.execute("PRAGMA query_only=ON")
                num = conn.execute(
                    "SELECT COUNT(*) FROM dispatch_reservations").fetchone()[0]
        else:
            with closing(sqlite3.connect(
                    "file:" + quote(scope.location("live", kind).as_posix(),
                                    safe="/:\\") + "?mode=ro", uri=True)) as conn:
                conn.execute("PRAGMA query_only=ON")
                num = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        if num != 2:
            raise RollbackDenied("synthetic_upgrade_did_not_mutate_" + kind)
        now_snapshots[kind] = {"requestRows": num, "sha256": base._sha(
            scope.location("live", kind))}
    now_snapshots["postBackupPreparedSha256"] = later_prepared["payloadSha256"]
    return now_snapshots


def _independent_sqlite_readback(path: Path, kind: str) -> dict:
    """Independent SQLite inspection, not delegated to the source helper."""
    base._safe_file(path)
    if kind not in base.NAMES:
        raise RollbackDenied("unsupported_rollback_database")
    uri = "file:" + quote(path.as_posix(), safe="/:\\") + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as conn:
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RollbackDenied("independent_sqlite_integrity_failed")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RollbackDenied("independent_foreign_key_check_failed")
        if conn.execute("PRAGMA user_version").fetchone() != (1,):
            raise RollbackDenied("independent_schema_version_mismatch")
        schema = {
            name: typ for name, typ in conn.execute(
                "SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
        counts = {}
        for table in base.TABLES[kind]:
            if schema.get(table) != "table":
                raise RollbackDenied("independent_required_table_missing")
            value = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if type(value) is not int or value > base.MAX_ROWS_PER_TABLE:
                raise RollbackDenied("independent_row_limit_breached")
            counts[table] = value
        if kind == "peer":
            for table in base.TABLES[kind]:
                for action in ("update", "delete"):
                    if schema.get(f"deny_{table}_{action}") != "trigger":
                        raise RollbackDenied("independent_peer_immutable_trigger_missing")
        if kind == "dispatch":
            control = conn.execute(
                "SELECT singleton,first_permits_enabled FROM dispatch_control").fetchall()
            if control != [(1, 0)]:
                raise RollbackDenied("rollback_would_reenable_first_dispatch")
        return {"counts": counts,
                "schemaObjectsSha256": hashlib.sha256(base._json_bytes(
                    sorted(schema.items()))).hexdigest(),
                "sqliteIntegrity": "ok", "schemaVersion": 1,
                "sha256": base._sha(path)}


def _checkpoint_observations(scope, checkpoint: dict) -> dict:
    observations = {}
    for kind in base.NAMES:
        original = scope.location("backups", kind)
        independent = _independent_sqlite_readback(original, kind)
        expected = checkpoint["snapshots"][kind]
        if (independent["sha256"] != expected["sha256"] or
                independent["counts"] != {
                    table: item["rows"] for table, item in expected["tables"].items()}):
            raise RollbackDenied("pre_upgrade_original_snapshot_disagreement")
        observations[kind] = independent
    return observations


def _copy_exact_new(source: Path, destination: Path, expected_sha: str):
    """Byte-exact, fsync'd, atomic create-if-absent rollback to a NEW path."""
    base._safe_file(source)
    base._no_links(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("rollback_target_exists_no_overwrite")
    if not destination.parent.is_dir():
        raise RollbackDenied("rollback_destination_missing")
    if base._sha(source) != expected_sha:
        raise RollbackDenied("original_checkpoint_has_changed_before_copy")
    fd, tmp_name = tempfile.mkstemp(
        prefix=".mtr-rollback-copy-", suffix=".sqlite3", dir=destination.parent)
    temporary = Path(tmp_name)
    try:
        with source.open("rb") as reader, os.fdopen(fd, "wb") as writer:
            for chunk in iter(lambda: reader.read(1 << 20), b""):
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        if base._sha(temporary) != expected_sha:
            raise RollbackDenied("rollback_copy_sha256_disagrees_with_checkpoint")
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    if base._sha(destination) != expected_sha:
        raise RollbackDenied("published_rollback_sha256_mismatch")


def rollback_new_destinations(
        scope: base.DisposableQAScope, original_checkpoint: dict,
        reference_observations: dict) -> dict:
    """Verify ALL backups before creating *any* rollback target."""
    validated = base.validate_backups(scope)
    if validated != original_checkpoint:
        raise RollbackDenied("checkpoint_manifest_changed_since_original_backup")
    if (type(reference_observations) is not dict or
            set(reference_observations) != set(base.NAMES)):
        raise RollbackDenied("missing_independent_pre_upgrade_observations")
    root = scope.root / ROLLBACK_FOLDER
    base._no_links(root)
    if root.exists() or root.is_symlink():
        raise FileExistsError("rollback_folder_exists_no_overwrite")
    for kind in base.NAMES:
        if _independent_sqlite_readback(
                scope.location("backups", kind), kind) != reference_observations[kind]:
            raise RollbackDenied("original_checkpoint_changed_or_corrupted")
    root.mkdir(exist_ok=False)
    restored = {}
    for kind in base.NAMES:
        destination = root / (kind + ".sqlite3")
        source = scope.location("backups", kind)
        _copy_exact_new(source, destination, reference_observations[kind]["sha256"])
        independent = _independent_sqlite_readback(destination, kind)
        if independent != reference_observations[kind]:
            raise RollbackDenied("independent_restored_snapshot_digest_mismatch")
        source_rows = base._sqlite_readback(source, kind)
        dest_rows = base._sqlite_readback(destination, kind)
        if dest_rows != source_rows:
            raise RollbackDenied("restored_row_fingerprints_not_identical")
        restored[kind] = {
            "sha256": independent["sha256"],
            "sourceSnapshotSha256": reference_observations[kind]["sha256"],
            "exactBytes": True, "rowDigestMatches": True,
            "schemaDigestMatches": True, "integrityCheck": "ok",
            "destinationNewAndDistinct": destination != source,
        }
    return restored


def _verify_no_replay(scope, state, upgraded):
    """Open only newly restored synthetic DBs; NEVER an installed profile."""
    from mtr_host_request_store import HostRequestStore
    from mtr_e2_dispatch_gate import OneShotDispatchGate, DispatchGateConflict
    root = scope.root / ROLLBACK_FOLDER
    restored_outbox = HostRequestStore(root / "outbox.sqlite3")
    restored_gate = OneShotDispatchGate(root / "dispatch.sqlite3", restored_outbox)
    restored_peer = state["taraz"].TarazPeerRegistry(
        root / "peer.sqlite3", _peer_config(state["taraz"]))
    who = _qa_principal()
    original_status = restored_gate.status(
        principal=who, request_id=REQUEST_ID, expected_base_revision=7)
    if (original_status.get("mustQueryFirst") is not True or
            original_status.get("canAutoRetry") is not False or
            original_status.get("state") != "unknown_after_attempt" or
            original_status.get("receiptVerification") != "UNVERIFIED"):
        raise RollbackDenied("previously_consumed_dispatch_replay_not_blocked")
    try:
        restored_gate.reserve_once(
            principal=who, request_id=REQUEST_ID,
            expected_payload_sha256=state["prepared"]["payloadSha256"],
            expected_base_revision=7, current_server_revision=7,
            send_key="qa-send-" + REQUEST_ID[:8])
    except (DispatchGateConflict, PermissionError):
        denied_prior = True
    else:
        raise RollbackDenied("previously_consumed_slot_replayed")
    # A synthetic request created *after* the checkpoint does not come back.
    try:
        restored_outbox.receipt_status(
            principal=who, request_id=UPGRADED_REQUEST_ID,
            expected_base_revision=7)
    except KeyError:
        post_backup_request_not_restored = True
    else:
        raise RollbackDenied("upgrade_only_row_contaminated_original_checkpoint")
    # A request consumed *after* checkpoint also cannot issue a new permit
    # even if its row no longer exists: the restored gate disables all first
    # grants BEFORE looking up an outbox entry. NEVER alter restored bytes.
    try:
        restored_gate.reserve_once(
            principal=who, request_id=UPGRADED_REQUEST_ID,
            expected_payload_sha256=upgraded["postBackupPreparedSha256"],
            expected_base_revision=7, current_server_revision=7,
            send_key="qa-send-" + UPGRADED_REQUEST_ID[:8])
    except PermissionError:
        denied_new = True
    else:
        raise RollbackDenied("rollback_minted_new_dispatch_slot")
    if restored_peer.intake(
            state["peerSeed"]["requestWire"],
            now=state["peerSeed"]["clock"],
            verified_transport_peer=True).get("idempotent") is not True:
        raise RollbackDenied("rollback_peer_request_replay_not_idempotent")
    response = restored_peer.query_receipt(
        state["peerSeed"]["queryWire"],
        now=state["peerSeed"]["clock"], verified_transport_peer=True)
    from mtr_peer_envelope import (
        verify_request, verify_receipt_query, verify_peer_receipt)
    original = verify_request(
        state["peerSeed"]["requestWire"], secret=b"m" * 32,
        now=state["peerSeed"]["clock"], expected_organization_id="qa-org",
        expected_sender_id="qa-madar", expected_key_id="qa-m-key",
        purpose="finance_review_request",
        allowed_actor_roles=frozenset({"editor"}))
    query = verify_receipt_query(
        state["peerSeed"]["queryWire"], secret=b"m" * 32,
        now=state["peerSeed"]["clock"], expected_organization_id="qa-org",
        expected_sender_id="qa-madar", expected_key_id="qa-m-key",
        allowed_actor_roles=frozenset({"editor"}))
    verified = verify_peer_receipt(
        response, original=original, query=query,
        secret=b"t" * 32, now=state["peerSeed"]["clock"],
        expected_peer_id="qa-taraz", expected_peer_key_id="qa-t-key")
    if (verified.payload["lookupStatus"] != "received" or
            restored_peer.query_capacity_status()["used"] != 1):
        raise RollbackDenied("rollback_lost_original_peer_query_binding")
    # Independently show query/replay checks made NO changes to any restored
    # bytes. This is crucial for claiming exact original snapshot digests.
    checkpoint = base.validate_backups(scope)
    for kind in base.NAMES:
        restored_path = root / (kind + ".sqlite3")
        if base._sha(restored_path) != checkpoint["snapshots"][kind]["sha256"]:
            raise RollbackDenied("restored_checkpoint_mutated_during_replay_probe")
    return {
        "previouslyConsumedHostSlotDenied": denied_prior,
        "newFirstDispatchDeniedAfterRollback": denied_new,
        "upgradeOnlyRequestNotRestored": post_backup_request_not_restored,
        "rollbackGatePermanentlyDisabled": True,
        "queryFirstNoAutoRetry": True,
        "peerQueryReplayBindingRetained": True,
        "financialReceiptVerified": False,
    }


def run() -> dict:
    """Pinned QA artifacts + one complete disposable upgrade/rollback drill."""
    pins = verify_both_artifact_pins()
    with base.DisposableQAScope() as scope:
        state = _first_state(scope)
        manifest = base.make_backups(
            scope, state["outbox"], state["gate"], state["peer"])
        checkpoint_sha = base._sha(scope.manifest())
        original = _checkpoint_observations(scope, manifest)
        plan = make_upgrade_plan(pins, checkpoint_sha)
        validate_upgrade_plan(plan, pins, checkpoint_sha)
        plan_path = _plan_file(scope, plan)
        plan_sha = base._sha(plan_path)
        plan = verify_disposable_upgrade_plan_file(
            scope, plan_sha, pins, checkpoint_sha)
        upgraded = _synthetic_upgrade(
            scope, state, plan, pins, checkpoint_sha)
        # Important: the checkpoint MUST predate all mutations above.
        if not all(upgraded[kind]["sha256"] != original[kind]["sha256"]
                   for kind in base.NAMES):
            raise RollbackDenied("synthetic_upgrade_had_no_detectable_changes")
        restored = rollback_new_destinations(scope, manifest, original)
        no_replay = _verify_no_replay(scope, state, upgraded)
        return {
            "status": "SYNTHETIC_ROLLBACK_PASS_NOT_RELEASE",
            "releaseDecision": "NO_GO",
            "signingPolicy": "UNSIGNED_QA_ONLY",
            "sourceArtifactPinsVerified": True,
            "sourceVersions": pins["versions"],
            "artifactPins": pins["artifactSha256"],
            "nonReleaseQAArtifactsOnly": True,
            "upgradePlanSha256": plan_sha,
            "immutableCheckpointManifestSha256": checkpoint_sha,
            "originalSnapshotFileSha256": {
                kind: original[kind]["sha256"] for kind in base.NAMES},
            "upgradedLiveSnapshotFileSha256": {
                kind: upgraded[kind]["sha256"] for kind in base.NAMES},
            "rollbackIntoNewPaths": True,
            "exactOriginalSnapshotDigestRestored": all(
                restored[k]["sha256"] == original[k]["sha256"]
                for k in base.NAMES),
            "threeIndependentSQLiteIntegrityChecksPassed": True,
            "restoredStoreCount": len(restored),
            "priorDispatchReplayDenied": no_replay["previouslyConsumedHostSlotDenied"],
            "freshDispatchAfterRollbackDenied":
                no_replay["newFirstDispatchDeniedAfterRollback"],
            "queryFirstAfterRollback": no_replay["queryFirstNoAutoRetry"],
            "peerReplayMetadataRetained": no_replay["peerQueryReplayBindingRetained"],
            "threeDatabaseAtomicEpochVerified": False,
            "powerLossOrRealServiceRestartVerified": False,
            "realInstallerExecuted": False,
            "realNetworkOrLedgerAccess": False,
            "officialFinancialReceiptVerified": False,
            "realCrossAppActorBindingVerified": False,
            "realProfilesOrInstalledAppsTouched": False,
            "signingOrProductionAcceptanceVerified": False,
            "mayInstall": False,
        }


def main() -> int:
    try:
        result = run()
    except Exception as exc:
        result = {
            "status": "FAIL_CLOSED", "syntheticOnly": True,
            "releaseDecision": "NO_GO", "signingPolicy": "UNSIGNED_QA_ONLY",
            "reason": type(exc).__name__ + ": " + str(exc)[:170],
            "realInstallerExecuted": False, "mayInstall": False,
            "officialFinancialReceiptVerified": False,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
