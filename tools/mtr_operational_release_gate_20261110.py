"""Fail-closed, READ-ONLY operational Madar/Taraz release decision gate.

This is a verifier, never a certificate issuer or install command. The current
production trust-anchor map is deliberately EMPTY: no official independent
source, QA, signing, Taraz-finance or recovery public keys were supplied.
Consequently current data MUST result in NO_GO. Test fixtures may explicitly
inject public keys into the pure verifier; CLI callers cannot.

External operational evidence convention, after independent authorization:
  evidence/proofs.json: {"schema":1,"proofs":[...]} (9 signed records)
  evidence/<kind>.json: signed record's SHA256-bound witness details

RSA signatures use RSASSA-PKCS1-v1_5 with SHA256 on canonical JSON excluding
the signature member. Public keys are pinned OUTSIDE the supplied proof files.
No network, installation, signing, account, profile or financial write occurs.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys

SOURCE = Path(__file__).resolve().parents[1]
QA_BUNDLE = Path(
    r"D:\CoS-Test\MTR-MADAR-TARAZ-QA-BUNDLE-20261110"
    r"\run-20261110-183506-18748-ec491e30"
)
CURRENT_QA_EXE = "Madar-Taraz-Connection-QA-20261110-NONRELEASE.exe"
QA_SHA256 = "0ba37c211f738d3d7bb9cf2a794a904f0269de128f72dfa8f1662755ac719454"
REQUIRED_KINDS = (
    "source", "build", "tests", "peer", "crash", "backup",
    "finance", "rollback", "signing",
)
OWNER_UNSIGNED_QA_KINDS = tuple(
    kind for kind in REQUIRED_KINDS if kind != "signing"
)
RELEASE_POLICIES = ("production-signed", "owner-controlled-unsigned-qa")
ROLES = {
    "source": "source-custodian",
    "build": "independent-build-auditor",
    "tests": "qa-acceptance-lead",
    "peer": "peer-security-operator",
    "crash": "crash-recovery-operator",
    "backup": "backup-restore-operator",
    "finance": "taraz-finance-authority",
    "rollback": "rollback-operator",
    "signing": "release-signing-auditor",
}
# NEVER synthesize, trust-on-first-use or import these keys from proofs.
# Empty until independently vetted issuer credentials are explicitly supplied.
PRODUCTION_TRUST_ANCHORS: dict[str, dict] = {}
EXPECTED_SNAPSHOT_KEYS = {"sourceRoot", "sourceSnapshotTreeSha256",
                          "fileCount", "files", "note"}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
KEY_ID = re.compile(r"[A-Za-z0-9_.-]{8,100}\Z")
RUN_ID = re.compile(r"[A-Za-z0-9_-]{12,100}\Z")
_DER_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")
_MAX_FILES = 20000
_MAX_SNAPSHOT_BYTES = 2_000_000_000
_MAX_JSON_BYTES = 15_000_000
_MAX_PROOF_FILE = 300_000
_MAX_PROOF_AGE = timedelta(hours=48)

DETAIL_CHECKS = {
    "source": ("committedClean", "fullSourceSnapshotMatches", "noUntrackedInputs"),
    "build": ("cumulativeInstallerVerified", "fullProvenanceVerified",
              "builtFromCommittedSource", "offlineWebview2Verified"),
    "tests": ("pythonFullSuitePassed", "javascriptFullSuitePassed",
              "all40AcGatesPassed", "zeroFailures", "zeroUnexaminedTests"),
    "peer": ("authenticatedMutualTls", "pinnedPeerIdentity",
             "hostEnforcedAuthorization", "twoPhysicalClientsVerified"),
    "crash": ("powerLossCrashInjected", "queryFirstIdempotentRecovery",
              "restartReadbackVerified", "noDuplicateFinancialEvents"),
    "backup": ("completeScopeBackupVerified", "independentRestoreVerified",
               "accountingBalancesReconciled", "snapshotFilesRehashed"),
    "finance": ("officialTarazSignedReceiptVerified", "approvedVsPostedSeparated",
                "officialLedgerReadbackMatched", "noDuplicatePosting"),
    "rollback": ("freshDisposableUpgradeVerified", "priorVersionRecoverable",
                 "rollbackRestoresAllState", "rollbackIndependentlyAudited"),
    "signing": ("authenticodeChainValid", "approvedPublisherIdentity",
                "offlinePrerequisitesSigned", "installPackageVerified"),
}
PROOF_FIELDS = {"schema", "kind", "role", "keyId", "runId", "issuedUtc",
                "expiresUtc", "sourceCommit", "sourceSha256", "artifactSha256",
                "appVersion", "evidenceSha256", "signature"}
DETAIL_FIELDS = {"schema", "kind", "runId", "sourceCommit", "sourceSha256",
                 "artifactSha256", "appVersion", "checks", "witnessFiles", "facts"}
WITNESS_NAMES = {
    "source": ("committed-source-inventory",),
    "build": ("release-binary-manifest", "offline-prerequisite-signatures"),
    "tests": ("full-python-and-node-suite", "all-40-ac-g-acceptance"),
    "peer": ("authenticated-tls-handshake", "host-authorization"),
    "crash": ("power-loss-faults", "query-first-recovery"),
    "backup": ("complete-backup-manifest", "independent-restore-readback"),
    "finance": ("official-taraz-receipt", "ledger-document-readback"),
    "rollback": ("reversible-install-trial", "rollback-state-reconciliation"),
    "signing": ("windows-authenticode", "webview2-authenticode"),
}
FACT_KEYS = {
    "source": ("sourceInventorySha256",),
    "build": ("installerSha256", "releaseManifestSha256"),
    "tests": ("executedTests", "passedAcGates"),
    "peer": ("tarazPeerCertificateSha256", "hostCertificateSha256"),
    "crash": ("testedCrashPoints",),
    "backup": ("restoredScopeCount",),
    "finance": ("officialReceiptId", "officialDocumentId"),
    "rollback": ("installedBaselineVersion", "restoredFilesCount"),
    "signing": ("authenticodeSignerThumbprint", "signedInstallerSha256"),
}


class GateError(ValueError):
    pass


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GateError("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(value):
    raise GateError("invalid_json_constant")


def _unsafe(path: Path) -> bool:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (FileNotFoundError, AttributeError):
        return False


def _safe_path(path: Path, *, directory: bool = False) -> None:
    if not path.is_absolute() or path == Path(path.anchor):
        raise GateError("absolute_nonroot_path_required")
    if any(_unsafe(part) for part in (path, *path.parents)):
        raise GateError("symlink_or_junction_path")
    if not (path.is_dir() if directory else path.is_file()):
        raise GateError("missing_expected_" + ("directory" if directory else "file"))


def _inside(root: Path, rel: str) -> Path:
    if (not isinstance(rel, str) or not rel or "\\" in rel or
            rel.startswith("/") or re.search(r"[:\x00-\x1f]", rel)):
        raise GateError("unsafe_relative_path")
    parts = PurePosixPath(rel).parts
    if (not parts or PurePosixPath(rel).as_posix() != rel or
            any(part in ("", ".", "..") for part in parts)):
        raise GateError("path_traversal")
    dest = root.joinpath(*parts)
    if any(_unsafe(part) for part in (dest, *dest.parents)):
        raise GateError("linked_input")
    return dest


def _bytes(path: Path, cap: int = _MAX_JSON_BYTES) -> bytes:
    _safe_path(path)
    before = path.stat()
    if before.st_size <= 0 or before.st_size > cap:
        raise GateError("file_empty_or_oversized")
    with path.open("rb") as source:
        data = source.read(cap + 1)
    after = path.stat()
    if (len(data) != before.st_size or len(data) > cap or
            (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)):
        raise GateError("file_changed_during_read")
    return data


def _json(path: Path, cap: int = _MAX_JSON_BYTES):
    try:
        obj = json.loads(_bytes(path, cap).decode("utf-8"),
                         object_pairs_hook=_no_duplicates,
                         parse_constant=_reject_constant)
    except GateError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise GateError("invalid_json") from exc
    if not isinstance(obj, dict):
        raise GateError("expected_object")
    return obj


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(path: Path) -> str:
    _safe_path(path)
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for segment in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(segment)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != \
            (after.st_size, after.st_mtime_ns, after.st_ino):
        raise GateError("file_changed_during_sha256")
    _safe_path(path)
    return digest.hexdigest()


def _expect_digest(value) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise GateError("invalid_sha256")
    return value


def _utc(value: str) -> datetime:
    if (type(value) is not str or len(value) > 35 or
            not value.endswith("Z")):
        raise GateError("timestamps_must_be_strict_utc")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise GateError("invalid_timestamp") from exc
    return parsed.replace(tzinfo=timezone.utc)


def _version(value: str) -> tuple[int, int, int]:
    if type(value) is not str or not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value):
        raise GateError("invalid_app_version")
    return tuple(int(x) for x in value.split("."))


def _source_version(source: Path) -> dict:
    package = _json(source / "package.json", 200_000)
    lock = _json(source / "package-lock.json", 8_000_000)
    if not (type(package.get("version")) is str and
            package["version"] == lock.get("version") ==
            lock.get("packages", {}).get("", {}).get("version")):
        raise GateError("package_lock_version_disagreement")
    version = package["version"]
    _version(version)
    update = ast.parse(_bytes(source / "madar_update.py", 2_000_000).decode("utf-8"))
    matches = [node.value.value for node in update.body
               if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and
                       target.id == "CURRENT_VERSION" for target in node.targets)
               and isinstance(node.value, ast.Constant)]
    if matches != [version]:
        raise GateError("updater_version_disagreement")
    return {"appVersion": version,
            "packageSha256": sha256(source / "package.json"),
            "lockSha256": sha256(source / "package-lock.json"),
            "updaterSha256": sha256(source / "madar_update.py")}


def _source_git(source: Path) -> dict:
    env = os.environ.copy()
    env.update({"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
                "GIT_NO_LAZY_FETCH": "1", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull})
    cmd = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
           "-c", "submodule.recurse=false", "-C", str(source)]
    def call(*args):
        result = subprocess.run(cmd + list(args), env=env, capture_output=True,
                                text=True, timeout=10, check=False)
        if result.returncode:
            raise GateError("git_metadata_unavailable")
        return result.stdout.strip()
    head = call("rev-parse", "--verify", "HEAD")
    if not HEX40.fullmatch(head):
        raise GateError("invalid_git_head")
    top = Path(call("rev-parse", "--show-toplevel"))
    if top.resolve() != source.resolve():
        raise GateError("source_not_git_toplevel")
    dirty = call("status", "--porcelain=v1", "--untracked-files=normal")
    return {"head": head, "clean": not dirty,
            "dirtyEntryCount": len(dirty.splitlines()) if dirty else 0}


def _snapshot(bundle: Path, source: Path) -> dict:
    manifest = _json(bundle / "source-input-sha256.json")
    if set(manifest) != EXPECTED_SNAPSHOT_KEYS:
        raise GateError("incomplete_source_input_manifest")
    files = manifest["files"]
    if (not isinstance(files, dict) or
            type(manifest["fileCount"]) is not int or
            len(files) != manifest["fileCount"] or
            not 10 <= len(files) <= _MAX_FILES):
        raise GateError("source_file_inventory_invalid")
    recorded = _expect_digest(manifest["sourceSnapshotTreeSha256"])
    if (not isinstance(manifest["note"], str) or
            not isinstance(manifest["sourceRoot"], str)):
        raise GateError("invalid_source_manifest_metadata")
    snapshot = bundle / "source"
    _safe_path(snapshot, directory=True)
    digest = hashlib.sha256()
    total = 0
    seen = set()
    for rel, entry in sorted(files.items()):
        if type(rel) is not str or rel.casefold() in seen:
            raise GateError("duplicate_or_ambiguous_snapshot_file")
        seen.add(rel.casefold())
        if (not isinstance(entry, dict) or
                set(entry) != {"sha256", "bytes"} or
                type(entry["bytes"]) is not int or
                not 0 <= entry["bytes"] <= 500_000_000):
            raise GateError("invalid_snapshot_file_entry")
        target = _inside(snapshot, rel)
        _safe_path(target)
        if target.stat().st_size != entry["bytes"]:
            raise GateError("snapshot_file_size_mismatch")
        file_hash = _expect_digest(entry["sha256"])
        if sha256(target) != file_hash:
            raise GateError("snapshot_file_hash_mismatch")
        total += entry["bytes"]
        if total > _MAX_SNAPSHOT_BYTES:
            raise GateError("snapshot_size_limit_exceeded")
        digest.update(f"{rel}\0{file_hash}\n".encode("utf-8"))
    if digest.hexdigest() != recorded:
        raise GateError("snapshot_tree_digest_mismatch")
    # Exact inventory, including no injected unlisted file or reparse directory.
    actual = set()
    for walk_root, dirs, names in os.walk(snapshot, followlinks=False):
        base = Path(walk_root)
        for directory in dirs:
            _safe_path(base / directory, directory=True)
        for filename in names:
            actual.add((base / filename).relative_to(snapshot).as_posix())
    if actual != set(files):
        raise GateError("snapshot_extra_or_missing_file")
    crucial = ("native_app.py", "src/App.jsx", "package.json", "package-lock.json",
               "madar_update.py")
    for rel in crucial:
        if rel not in files or sha256(_inside(source, rel)) != files[rel]["sha256"]:
            raise GateError("source_drift_from_snapshot:" + rel)
    return {"sha256": recorded, "fileCount": len(files),
            "bytes": total, "trackedCommitAttested": False,
            "nonreleaseSnapshotNote": manifest["note"]}


def _bundle(bundle: Path) -> dict:
    result = _json(bundle / "qa-build-result.json", 1_000_000)
    proof = _json(bundle / "qa-provenance.json", 1_000_000)
    ui = _json(bundle / "vite-assets-sha256.json", 2_000_000)
    if (result.get("schemaVersion") != 1 or
            result.get("status") != "QA_BUILT_NON_RELEASE" or
            result.get("purpose") != "QA_ONLY_NON_RELEASE" or
            proof.get("purpose") != "NON_RELEASE_QA" or
            proof.get("notFunctionalTestOrReleaseApproval") is not True or
            result.get("application", {}).get("releaseReady") is not False):
        raise GateError("qa_only_provenance_is_not_a_release")
    exe = bundle / "exe-dist" / CURRENT_QA_EXE
    _safe_path(exe)
    actual = sha256(exe)
    if actual != QA_SHA256 or result["application"].get("sha256") != actual or \
            result["application"].get("filename") != CURRENT_QA_EXE or \
            result["application"].get("bytes") != exe.stat().st_size or \
            proof.get("sourceSnapshotTreeSha256") != result.get("sourceSnapshotTreeSha256") or \
            proof.get("sourceFileCount") != result.get("sourceFileCount"):
        raise GateError("build_provenance_inconsistent")
    if proof.get("viteAssetsSha256") != sha256(bundle / "vite-assets-sha256.json"):
        raise GateError("vite_asset_inventory_digest_mismatch")
    if proof.get("nativeSourceSha256") != proof.get("preflight", {}).get(
            "nativeAndUiSource", {}).get("native_app.py"):
        raise GateError("native_provenance_mismatch")
    if proof.get("uiSourceSha256") != proof.get("preflight", {}).get(
            "nativeAndUiSource", {}).get("src/App.jsx"):
        raise GateError("frontend_provenance_mismatch")
    if (not isinstance(ui, dict) or not 1 <= len(ui) <= 1000 or
            not all(isinstance(x, dict) and set(x) == {"sha256", "bytes"}
                    for x in ui.values())):
        raise GateError("invalid_vite_asset_inventory")
    for rel, entry in ui.items():
        f = _inside(bundle / "vite-dist", rel)
        if (type(entry["bytes"]) is not int or entry["bytes"] < 0 or
                sha256(f) != _expect_digest(entry["sha256"]) or
                f.stat().st_size != entry["bytes"]):
            raise GateError("vite_artifact_mismatch")
    # Inspect bundled bytes via PyInstaller's *read-only* archive reader.
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(exe))
    archive_paths = {name.replace("\\", "/"): name for name in archive.toc}
    receipt_key = "qa_proof/qa-provenance.json"
    if receipt_key not in archive_paths or \
            archive.extract(archive_paths[receipt_key]) != _bytes(
                bundle / "qa-provenance.json", 1_000_000):
        raise GateError("embedded_qa_provenance_mismatch")
    for rel, entry in ui.items():
        key = "dist/" + rel
        if (key not in archive_paths or
                hashlib.sha256(archive.extract(archive_paths[key])).hexdigest()
                != entry["sha256"]):
            raise GateError("embedded_vite_asset_mismatch")
    return {"artifactSha256": actual, "sourceSnapshotSha256":
            result["sourceSnapshotTreeSha256"], "provenanceSha256": sha256(
                bundle / "qa-provenance.json"), "viteFileCount": len(ui),
            "qaOnly": True, "releaseApproved": False,
            "buildVersion": _json(bundle / "source" / "package.json",
                                  200_000).get("version")}


def _signature(executable: Path) -> dict:
    """Read-only Windows Authenticode status, no trust-on-first-use fallback."""
    if os.name != "nt":
        raise GateError("windows_authenticode_unavailable")
    escaped = str(executable).replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop';"
        "$s=Get-AuthenticodeSignature -LiteralPath '" + escaped + "';"
        "$t=if($s.SignerCertificate){$s.SignerCertificate.Thumbprint}else{''};"
        "@{status=[string]$s.Status;thumbprint=[string]$t}"
        "|ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        stdin=subprocess.DEVNULL, capture_output=True, timeout=20, text=True)
    if result.returncode:
        raise GateError("authenticode_check_failed")
    try:
        parsed = json.loads(result.stdout.strip())
    except ValueError as exc:
        raise GateError("authenticode_output_invalid") from exc
    if (not isinstance(parsed, dict) or
            parsed.get("status") not in {"Valid", "NotSigned", "UnknownError",
                                         "HashMismatch", "NotTrusted",
                                         "NotSupportedFileFormat", "Incompatible"}):
        raise GateError("authenticode_output_invalid")
    return {"status": parsed["status"],
            "thumbprint": parsed.get("thumbprint", "")}


def _rsa_verify(payload: bytes, signature: str, key: dict) -> bool:
    """Pure verification; no signing key, key-generation or private material."""
    if (not isinstance(key, dict) or set(key) != {"n", "e", "role"} or
            type(key["n"]) is not int or type(key["e"]) is not int or
            key["n"].bit_length() < 2048 or key["n"].bit_length() > 8192 or
            key["e"] != 65537 or type(signature) is not str or
            not re.fullmatch(r"[0-9a-f]+", signature)):
        return False
    width = (key["n"].bit_length() + 7) // 8
    if len(signature) != width * 2:
        return False
    integer = int(signature, 16)
    if not 0 < integer < key["n"]:
        return False
    decoded = pow(integer, key["e"], key["n"]).to_bytes(width, "big")
    trailer = _DER_SHA256 + hashlib.sha256(payload).digest()
    expected = b"\x00\x01" + b"\xff" * (width - len(trailer) - 3) + b"\x00" + trailer
    return hmac.compare_digest(decoded, expected)


def _verify_proofs(evidence: Path | None, *, anchors: dict,
                   expected: dict, now: datetime,
                   required_kinds: tuple[str, ...] = REQUIRED_KINDS) -> dict:
    """Strict authority-bound, freshly signed witness inventory.

    Injecting anchors is an in-process **test seam** only. CLI always uses the
    empty production constant, never keys carried by the evidence itself.
    """
    if evidence is None:
        raise GateError("missing_operational_proof_directory")
    if not anchors:
        raise GateError("independent_trust_anchors_not_provisioned")
    if required_kinds not in (REQUIRED_KINDS, OWNER_UNSIGNED_QA_KINDS):
        raise GateError("unsupported_attestation_policy")
    _safe_path(evidence, directory=True)
    manifest = _json(evidence / "proofs.json", 2_000_000)
    if set(manifest) != {"schema", "proofs"} or manifest["schema"] != 1:
        raise GateError("invalid_proof_manifest")
    proofs = manifest["proofs"]
    if not isinstance(proofs, list) or len(proofs) != len(required_kinds):
        raise GateError("proof_count_missing_or_extra")
    kinds, keys, key_material, run_ids = set(), set(), set(), set()
    allowed_files = {"proofs.json"} | {kind + ".json" for kind in required_kinds}
    allowed_files |= {
        kind + "." + witness + ".json"
        for kind in required_kinds for witness in WITNESS_NAMES[kind]
    }
    if {x.name for x in evidence.iterdir()} != allowed_files:
        raise GateError("proof_files_missing_or_extra")
    for proof in proofs:
        if not isinstance(proof, dict) or set(proof) != PROOF_FIELDS:
            raise GateError("extra_or_missing_proof_fields")
        kind = proof["kind"]
        if kind not in required_kinds or kind in kinds:
            raise GateError("unknown_or_duplicate_proof_kind")
        kinds.add(kind)
        if proof["schema"] != 1 or proof["role"] != ROLES[kind]:
            raise GateError("incorrect_role_or_proof_schema")
        key_id = proof["keyId"]
        if (type(key_id) is not str or not KEY_ID.fullmatch(key_id) or
                key_id in keys or key_id not in anchors):
            raise GateError("unknown_or_reused_issuer")
        keys.add(key_id)
        key = anchors[key_id]
        if key.get("role") != ROLES[kind] or (key.get("n"), key.get("e")) in key_material:
            raise GateError("untrusted_role_or_shared_public_key")
        key_material.add((key["n"], key["e"]))
        for field in ("sourceSha256", "artifactSha256", "evidenceSha256"):
            _expect_digest(proof[field])
        if (proof["artifactSha256"] != expected["artifactSha256"] or
                proof["sourceSha256"] != expected["sourceSnapshotSha256"] or
                proof["sourceCommit"] != expected["sourceCommit"] or
                proof["appVersion"] != expected["appVersion"] or
                not RUN_ID.fullmatch(proof["runId"])):
            raise GateError("stale_or_foreign_attestation_subject")
        run_ids.add(proof["runId"])
        issued, expires = _utc(proof["issuedUtc"]), _utc(proof["expiresUtc"])
        if (now.tzinfo is None or issued > now or expires <= now or
                now - issued > _MAX_PROOF_AGE or
                not timedelta(0) < expires - issued <= _MAX_PROOF_AGE):
            raise GateError("stale_future_or_expired_proof")
        encoded = _canonical({k: v for k, v in proof.items() if k != "signature"})
        if not _rsa_verify(encoded, proof["signature"], key):
            raise GateError("invalid_independent_signature")
        details = _json(evidence / (kind + ".json"), _MAX_PROOF_FILE)
        if hashlib.sha256(_bytes(evidence / (kind + ".json"),
                                 _MAX_PROOF_FILE)).hexdigest() != proof["evidenceSha256"]:
            raise GateError("witness_detail_digest_mismatch")
        if set(details) != DETAIL_FIELDS or details["schema"] != 1:
            raise GateError("incomplete_witness_detail_schema")
        for name in ("kind", "runId", "sourceCommit", "sourceSha256",
                     "artifactSha256", "appVersion"):
            if details[name] != proof[name]:
                raise GateError("witness_subject_disagreement")
        checks = details["checks"]
        if (not isinstance(checks, dict) or
                set(checks) != set(DETAIL_CHECKS[kind]) or
                any(checks[name] is not True for name in DETAIL_CHECKS[kind])):
            raise GateError("failed_or_incomplete_operational_witness")
        facts = details["facts"]
        if not isinstance(facts, dict) or set(facts) != set(FACT_KEYS[kind]):
            raise GateError("missing_or_extra_witness_facts")
        for field in ("sourceInventorySha256", "installerSha256",
                      "releaseManifestSha256", "tarazPeerCertificateSha256",
                      "hostCertificateSha256", "signedInstallerSha256"):
            if field in facts:
                _expect_digest(facts[field])
        for field in ("executedTests", "passedAcGates", "testedCrashPoints",
                      "restoredScopeCount", "restoredFilesCount"):
            if field in facts and (type(facts[field]) is not int or facts[field] <= 0):
                raise GateError("witness_count_not_positive")
        if kind == "tests" and facts["passedAcGates"] != 40:
            raise GateError("all_40_acceptance_gates_not_proven")
        if kind == "source" and (
                facts["sourceInventorySha256"] != expected["sourceInventorySha256"]):
            raise GateError("signed_source_inventory_does_not_match_build")
        if kind == "build" and facts["installerSha256"] != expected["artifactSha256"]:
            raise GateError("signed_installer_identity_mismatch")
        if kind == "signing" and (
                facts["signedInstallerSha256"] != expected["artifactSha256"] or
                facts["authenticodeSignerThumbprint"] !=
                expected["authenticodeSignerThumbprint"]):
            raise GateError("signed_publisher_identity_mismatch")
        if kind == "rollback":
            if _version(facts["installedBaselineVersion"]) >= _version(
                    expected["appVersion"]):
                raise GateError("rollback_target_not_older_than_candidate")
        if kind == "finance":
            for field in ("officialReceiptId", "officialDocumentId"):
                if (not isinstance(facts[field], str) or
                        not re.fullmatch(r"[A-Za-z0-9._:-]{12,180}", facts[field])):
                    raise GateError("official_financial_reference_missing")
        witnesses = details["witnessFiles"]
        expected_witnesses = {
            kind + "." + name + ".json" for name in WITNESS_NAMES[kind]}
        if not isinstance(witnesses, dict) or set(witnesses) != expected_witnesses:
            raise GateError("missing_or_extra_hashed_witness_files")
        for rel, recorded_sha in witnesses.items():
            asset = _inside(evidence, rel)
            if sha256(asset) != _expect_digest(recorded_sha):
                raise GateError("independent_witness_file_hash_mismatch")
    if kinds != set(required_kinds) or len(run_ids) != 1:
        raise GateError("incomplete_or_mixed_proof_run")
    return {"verifiedProofCount": len(kinds), "independentIssuerCount": len(keys),
            "runId": next(iter(run_ids))}


def audit(source: Path = SOURCE, bundle: Path = QA_BUNDLE,
          evidence: Path | None = None, *, anchors: dict | None = None,
          now: datetime | None = None, signature_probe=None,
          policy: str = "production-signed") -> dict:
    """Deterministic read-only verdict with explicit independent evidence gaps."""
    if policy not in RELEASE_POLICIES:
        raise GateError("unknown_or_unsupported_release_policy")
    unsigned_qa = policy == "owner-controlled-unsigned-qa"
    required_kinds = OWNER_UNSIGNED_QA_KINDS if unsigned_qa else REQUIRED_KINDS
    now = now or datetime.now(timezone.utc)
    trust = PRODUCTION_TRUST_ANCHORS if anchors is None else anchors
    checks: dict[str, dict] = {}
    context: dict = {}

    def record(label, action):
        try:
            value = action()
            checks[label] = {"state": "PASS", **value}
            return value
        except (OSError, ValueError, KeyError, TypeError, AttributeError,
                subprocess.TimeoutExpired, ImportError) as exc:
            checks[label] = {"state": "BLOCKED", "reason":
                             str(exc) if isinstance(exc, GateError)
                             else type(exc).__name__}
            return None

    record("safe_roots", lambda: (_safe_path(source, directory=True),
                                  _safe_path(bundle, directory=True), {})[-1])
    source_version = record("source_version", lambda: _source_version(source))
    git = record("source_git", lambda: _source_git(source))
    snapshot = record("exact_snapshot", lambda: _snapshot(bundle, source))
    build = record("complete_qa_bundle", lambda: _bundle(bundle))
    if source_version and build:
        def match_version():
            if build["buildVersion"] != source_version["appVersion"]:
                raise GateError("source_build_version_mismatch")
            # The observed installed baseline was 1.0.26. A 1.0.23
            # non-release QA build cannot silently downgrade it.
            if _version(source_version["appVersion"]) <= _version("1.0.26"):
                raise GateError("candidate_1.0.23_not_newer_than_installed_1.0.26")
            return {"sourceBuildVersion": source_version["appVersion"],
                    "observedInstalledBaseline": "1.0.26",
                    "candidateNewerThanBaseline": True}
        record("app_version_alignment", match_version)
    else:
        checks["app_version_alignment"] = {"state": "BLOCKED",
                                           "reason": "version_provenance_unavailable"}
    if build and snapshot:
        if build["sourceSnapshotSha256"] != snapshot["sha256"]:
            checks["snapshot_build_binding"] = {"state": "BLOCKED",
                                                 "reason": "snapshot_build_digest_disagreement"}
        else:
            checks["snapshot_build_binding"] = {"state": "PASS"}
    else:
        checks["snapshot_build_binding"] = {"state": "BLOCKED",
                                            "reason": "provenance_unavailable"}
    if git:
        checks["clean_committed_source"] = {
            "state": "PASS" if git["clean"] else "BLOCKED",
            "reason": "dirty_worktree_not_release_source" if not git["clean"] else
                      "clean_revision_verified",
        }
    else:
        checks["clean_committed_source"] = {"state": "BLOCKED",
                                            "reason": "missing_git_identity"}
    if build:
        checks["release_quality_artifact"] = {
            "state": "PASS" if unsigned_qa and build["qaOnly"] else
                     ("BLOCKED" if build["qaOnly"] else "PASS"),
            "reason": ("qa_artifact_eligible_for_nonproduction_evidence_review_only"
                       if unsigned_qa and build["qaOnly"] else
                       "qa_only_unsigned_nonrelease_artifact" if build["qaOnly"] else
                       "release_artifact"),
        }
        signed = record("authenticode", lambda:
                        (signature_probe or _signature)(
                            bundle / "exe-dist" / CURRENT_QA_EXE))
        if signed:
            if unsigned_qa:
                checks["authenticode"]["state"] = "PASS"
                checks["authenticode"]["policy"] = (
                    "SIGNING_DEFERRED_BY_OWNER_FOR_QA_ONLY; no release approval")
                checks["authenticode"]["signedDistributionApproved"] = False
            elif signed["status"] != "Valid":
                checks["authenticode"]["state"] = "BLOCKED"
                checks["authenticode"]["reason"] = "invalid_or_unsigned_authenticode"
    else:
        checks["release_quality_artifact"] = {"state": "BLOCKED",
                                               "reason": "build_missing"}
        checks["authenticode"] = {"state": "BLOCKED",
                                  "reason": "build_missing"}
    def proof_inventory():
        if evidence is None:
            raise GateError("missing_operational_proof_domains:" +
                            ",".join(required_kinds))
        _safe_path(evidence, directory=True)
        present = {p.name for p in evidence.iterdir()}
        expected_files = {"proofs.json"} | {
            kind + ".json" for kind in required_kinds}
        expected_files |= {
            kind + "." + witness + ".json"
            for kind in required_kinds for witness in WITNESS_NAMES[kind]
        }
        if present != expected_files:
            raise GateError("proof_missing_or_extra:" +
                            ",".join(sorted(expected_files ^ present))[:500])
        return {"requiredDomains": list(required_kinds),
                "requiredDomainCount": len(required_kinds)}
    record("operational_proof_inventory", proof_inventory)
    if source_version and build and git and snapshot:
        context = {
            "artifactSha256": build["artifactSha256"],
            "sourceSnapshotSha256": snapshot["sha256"],
            "sourceCommit": git["head"],
            "appVersion": source_version["appVersion"],
            "sourceInventorySha256": sha256(bundle / "source-input-sha256.json"),
            "authenticodeSignerThumbprint": checks["authenticode"].get("thumbprint", ""),
        }
        record("independent_operational_attestations",
               lambda: _verify_proofs(evidence, anchors=trust, expected=context,
                                      now=now, required_kinds=required_kinds))
    else:
        checks["independent_operational_attestations"] = {
            "state": "BLOCKED", "reason": "subject_provenance_unavailable"}
    # A claim of signing/receipt/rollback must NEVER substitute for the actual
    # artifact state, clean source, or owner acceptance. No install action here.
    blockers = sorted(label for label, check in checks.items()
                      if check.get("state") != "PASS")
    return {
        "schema": 1, "tool": "mtr_operational_release_gate_20261110",
        "readOnly": True,
        "decision": "NO_GO" if blockers else
                    ("QA_EVIDENCE_ACCEPTABLE_NOT_INSTALLABLE" if unsigned_qa else "GO"),
        "policy": policy,
        "signingDeferredForOwnerQaOnly": unsigned_qa,
        "mayInstall": False, "mayDeploy": False,
        "ownerInstallationApprovalStillRequired": True,
        "blockers": blockers, "checks": checks, "context": context,
        "limits": ("QA-only bundles and signed local metadata are NOT installed "
                   "production acceptance or official Taraz financial receipts. "
                   "Empty production trust roots intentionally block release."),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--bundle", type=Path, default=QA_BUNDLE)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--policy", choices=RELEASE_POLICIES,
                        default="production-signed",
                        help="The owner has deferred signing for QA-only; never for production")
    args = parser.parse_args(argv)
    try:
        result = audit(args.source, args.bundle, args.evidence, policy=args.policy)
    except Exception as exc:  # A verifier error never authorizes an install.
        result = {
            "schema": 1, "tool": "mtr_operational_release_gate_20261110",
            "readOnly": True, "decision": "NO_GO", "mayInstall": False,
            "mayDeploy": False, "blockers": ["internal_verifier_error"],
            "checks": {"internal_verifier_error":
                       {"state": "BLOCKED", "reason": type(exc).__name__}},
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")))
    return 2  # This tool NEVER performs installation, even after a GO verdict.


if __name__ == "__main__":
    sys.exit(main())
