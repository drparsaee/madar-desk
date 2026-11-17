"""Read-only, fail-closed Madar version and pinned QA candidate attestation.

This checks version coherence and artifact identity, NOT publisher authenticity,
functional QA, installation readiness, signing, or permission to release.
Use externally recorded SHA256 pins; a file's self-reported hash is not a pin.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import stat


DEFAULT_SOURCE = Path(__file__).resolve().parents[1]
OBSERVED_INSTALLED_BASELINE = "1.0.26"  # Reported on 2026-11-10; not live discovery.
# Prime-supplied QA-only pins from 2026-11-10 18:35; neither is release authority.
LATEST_QA_BUNDLE = Path(
    r"D:\CoS-Test\MTR-MADAR-TARAZ-QA-BUNDLE-20261110"
    r"\run-20261110-183506-18748-ec491e30"
)
LATEST_QA_EXE = LATEST_QA_BUNDLE / "exe-dist" / "Madar-Taraz-Connection-QA-20261110-NONRELEASE.exe"
LATEST_QA_SHA256 = "0ba37c211f738d3d7bb9cf2a794a904f0269de128f72dfa8f1662755ac719454"
LATEST_QA_PROVENANCE_SHA256 = "0689d26c3a554bef7995abf51b038c49af050adb44a86563a3227a6da92ee297"
LATEST_QA_SNAPSHOT_SHA256 = "1f4853ff34db15dbe49281003f15cbe0ec1ea39689ac7dafe267409bc3409617"
SEMVER = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
BUILD_ROUTE = re.compile(
    r"python -B scripts/build_integrated_v([0-9]+)\.py --webview2 "
    r"release/\.madar-inno-prereq/MicrosoftEdgeWebView2RuntimeInstallerX64\.exe\Z"
)
BASE_FILES = (
    "package.json", "package-lock.json", "madar_update.py",
    "scripts/build_p0_release_candidate.py", "scripts/madar-update.iss",
    "scripts/Madar-Activate-Version.ps1", "scripts/Madar-Upgrade-Preflight.ps1",
    "native_app.py", "src/App.jsx",
)
MAX_METADATA_BYTES = 8_000_000
MAX_QA_BYTES = 400_000_000


class ParityError(ValueError):
    """An untrusted source or release artifact cannot be attested."""


def _version(value: str) -> tuple[int, int, int]:
    if type(value) is not str or not SEMVER.fullmatch(value):
        raise ParityError("invalid_strict_semver")
    return tuple(int(part) for part in value.split("."))


def _no_duplicates(pairs):
    parsed = {}
    for key, value in pairs:
        if key in parsed:
            raise ParityError("duplicate_json_key")
        parsed[key] = value
    return parsed


def _reject_constant(_):
    raise ParityError("invalid_json_constant")


def _safe_path(path: Path, *, folder: bool = False):
    if not path.is_absolute() or path == Path(path.anchor) or ".." in path.parts:
        raise ParityError("absolute_nonroot_path_required")
    if str(path).startswith("\\\\"):
        raise ParityError("network_paths_not_allowed")
    for component in (path, *path.parents):
        if component.is_symlink() or getattr(component, "is_junction", lambda: False)():
            raise ParityError("linked_or_junction_path")
        try:
            if component.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ParityError("linked_or_junction_path")
        except (FileNotFoundError, AttributeError):
            pass
    if not (path.is_dir() if folder else path.is_file()):
        raise ParityError("required_path_missing")


def _inside(root: Path, relative: str) -> Path:
    if (type(relative) is not str or not re.fullmatch(r"[A-Za-z0-9._/-]+", relative)
            or relative.startswith("/") or ".." in relative.split("/")
            or "//" in relative or "/./" in relative):
        raise ParityError("unsafe_relative_path")
    return root.joinpath(*relative.split("/"))


def _bytes(path: Path, *, cap: int = MAX_METADATA_BYTES) -> bytes:
    _safe_path(path)
    before = path.stat()
    if not 0 < before.st_size <= cap:
        raise ParityError("missing_or_oversized_input")
    with path.open("rb") as source:
        content = source.read(cap + 1)
    after = path.stat()
    if (len(content) != before.st_size or
            (before.st_size, before.st_mtime_ns, before.st_ino) !=
            (after.st_size, after.st_mtime_ns, after.st_ino)):
        raise ParityError("input_changed_during_read")
    _safe_path(path)
    return content


def _json(path: Path) -> dict:
    try:
        value = json.loads(_bytes(path).decode("utf-8"),
                           object_pairs_hook=_no_duplicates,
                           parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ParityError("invalid_json") from exc
    if type(value) is not dict:
        raise ParityError("expected_json_object")
    return value


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_hash(path: Path, *, cap: int = MAX_QA_BYTES) -> tuple[str, int]:
    _safe_path(path)
    before = path.stat()
    if not 0 < before.st_size <= cap:
        raise ParityError("missing_or_oversized_artifact")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if ((before.st_size, before.st_mtime_ns, before.st_ino) !=
            (after.st_size, after.st_mtime_ns, after.st_ino)):
        raise ParityError("artifact_changed_during_hash")
    _safe_path(path)
    return digest.hexdigest(), before.st_size


def _literal_assignment(source: str, name: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ParityError("invalid_python_version_source") from exc
    assignments = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            label = (target.id if isinstance(target, ast.Name) else
                     f"{target.value.id}.{target.attr}" if
                     isinstance(target, ast.Attribute) and
                     isinstance(target.value, ast.Name) else None)
            if label == name:
                assignments.append(node.value.value if isinstance(node.value, ast.Constant)
                                   and type(node.value.value) is str else None)
    if len(assignments) != 1 or assignments[0] is None:
        raise ParityError("missing_duplicate_or_dynamic_assignment:" + name)
    return assignments[0]


def inspect_source(root: Path) -> dict:
    """Pin every selected release input, without writing or importing project code."""
    _safe_path(root, folder=True)
    package = _json(_inside(root, "package.json"))
    lock = _json(_inside(root, "package-lock.json"))
    version = package.get("version")
    _version(version)
    if (lock.get("version") != version or
            lock.get("packages", {}).get("", {}).get("version") != version or
            package.get("name") != lock.get("name") or
            package.get("name") != lock.get("packages", {}).get("", {}).get("name") or
            any(package.get(key) != lock.get("packages", {}).get("", {}).get(key)
                for key in ("dependencies", "devDependencies"))):
        raise ParityError("package_lock_version_or_dependency_mismatch")
    updater = _literal_assignment(_bytes(_inside(root, "madar_update.py")).decode("utf-8"),
                                  "CURRENT_VERSION")
    if updater != version:
        raise ParityError("updater_version_mismatch")
    route = package.get("scripts", {}).get("dist:rc")
    match = BUILD_ROUTE.fullmatch(route) if type(route) is str else None
    if not match:
        raise ParityError("invalid_default_build_route")
    # Historical wrapper naming is v123 for 1.0.23, and v127 for 1.0.27.
    major, minor, patch = _version(version)
    expected_suffix = f"{major}{patch}" if minor == 0 else f"{major}{minor}{patch}"
    if match.group(1) != expected_suffix:
        raise ParityError("build_route_version_mismatch")
    wrapper_name = f"scripts/build_integrated_v{match.group(1)}.py"
    wrapper = _bytes(_inside(root, wrapper_name)).decode("utf-8")
    if _literal_assignment(wrapper, "builder.VERSION") != version:
        raise ParityError("wrapper_version_mismatch")
    # A wrapper can only attest this version if the named immutable outputs
    # include it and its build script passes the version into Inno.
    wrapper_outputs = {}
    for node in ast.parse(wrapper).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                key = (target.id if isinstance(target, ast.Name) else
                       f"{target.value.id}.{target.attr}" if
                       isinstance(target, ast.Attribute) and
                       isinstance(target.value, ast.Name) else None)
                if key in ("builder.PROGRAM", "builder.QA", "builder.PROD", "MANIFEST"):
                    wrapper_outputs.setdefault(key, []).append([
                        child.value for child in ast.walk(node.value)
                        if isinstance(child, ast.Constant) and type(child.value) is str])
    for label in ("builder.PROGRAM", "builder.QA", "builder.PROD", "MANIFEST"):
        entries = wrapper_outputs.get(label)
        if (entries is None or len(entries) != 1 or
                not any(version in value for value in entries[0])):
            raise ParityError("wrapper_artifact_version_mismatch:" + label)
    builder = _bytes(_inside(root, "scripts/build_p0_release_candidate.py")).decode("utf-8")
    inno = _bytes(_inside(root, "scripts/madar-update.iss")).decode("utf-8")
    if ('"/DMadarVersion=" + VERSION' not in builder or
            '"/DExeFile=" + PROGRAM.name' not in builder or
            "#ifndef MadarVersion" not in inno or
            "AppVersion={#MadarVersion}" not in inno or
            "VersionInfoVersion={#MadarVersion}.0" not in inno):
        raise ParityError("inno_version_override_contract_missing")
    paths = (*BASE_FILES, wrapper_name)
    inventory = {}
    for rel in paths:
        data = _bytes(_inside(root, rel))
        inventory[rel] = {"sha256": _digest(data), "bytes": len(data)}
    fingerprint = _digest("".join(
        f"{rel}\0{inventory[rel]['sha256']}\n" for rel in sorted(inventory)
    ).encode("utf-8"))
    return {"version": version, "buildEntrypoint": wrapper_name,
            "sourceFingerprintSha256": fingerprint, "files": inventory}


def inspect_qa_bundle(bundle: Path, artifact: Path, expected_sha256: str,
                      expected_snapshot_sha256: str, source: dict,
                      expected_provenance_sha256: str,
                      *, archive_reader=None) -> dict:
    """Pin a complete QA bundle and inspect actual PyInstaller archive bytes."""
    _safe_path(bundle, folder=True)
    _safe_path(artifact)
    if artifact.parent != bundle / "exe-dist":
        raise ParityError("qa_executable_outside_expected_bundle")
    if type(expected_sha256) is not str or not SHA256.fullmatch(expected_sha256):
        raise ParityError("missing_or_invalid_external_qa_pin")
    if type(expected_snapshot_sha256) is not str or not SHA256.fullmatch(expected_snapshot_sha256):
        raise ParityError("missing_or_invalid_external_snapshot_pin")
    if (type(expected_provenance_sha256) is not str or
            not SHA256.fullmatch(expected_provenance_sha256)):
        raise ParityError("missing_or_invalid_external_provenance_pin")
    actual_hash, size = _file_hash(artifact)
    with artifact.open("rb") as reader:
        pe_marker = reader.read(2)
    if actual_hash != expected_sha256 or pe_marker != b"MZ":
        raise ParityError("qa_executable_sha256_or_pe_mismatch")
    if _file_hash(bundle / "qa-provenance.json")[0] != expected_provenance_sha256:
        raise ParityError("qa_provenance_sha256_mismatch")
    result = _json(bundle / "qa-build-result.json")
    proof = _json(bundle / "qa-provenance.json")
    snapshot = _json(bundle / "source-input-sha256.json")
    manifest_version = _json(bundle / "source" / "package.json").get("version")
    installed_lock = _json(bundle / "source" / "package-lock.json")
    installed_updater = _literal_assignment(
        _bytes(bundle / "source" / "madar_update.py").decode("utf-8"),
        "CURRENT_VERSION")
    version = source["version"]
    if (result.get("schemaVersion") != 1 or
            result.get("status") != "QA_BUILT_NON_RELEASE" or
            result.get("purpose") != "QA_ONLY_NON_RELEASE" or
            proof.get("purpose") != "NON_RELEASE_QA" or
            proof.get("notFunctionalTestOrReleaseApproval") is not True or
            result.get("application", {}).get("releaseReady") is not False):
        raise ParityError("not_an_explicit_nonrelease_qa_bundle")
    application = result.get("application", {})
    if (application.get("sha256") != actual_hash or
            application.get("filename") != artifact.name or
            application.get("bytes") != size or
            result.get("sourceSnapshotTreeSha256") != expected_snapshot_sha256 or
            proof.get("sourceSnapshotTreeSha256") != expected_snapshot_sha256 or
            snapshot.get("sourceSnapshotTreeSha256") != expected_snapshot_sha256):
        raise ParityError("qa_artifact_or_snapshot_pin_mismatch")
    # Current 1.0.23 QA bundle predates embedded appVersion. It MUST block,
    # rather than infer an embedded version from filenames or source metadata.
    if (result.get("appVersion") != version or proof.get("appVersion") != version or
            manifest_version != version or installed_updater != version or
            installed_lock.get("version") != version or
            installed_lock.get("packages", {}).get("", {}).get("version") != version):
        raise ParityError("missing_or_mismatched_qa_embedded_version")
    listed = snapshot.get("files")
    if not isinstance(listed, dict) or snapshot.get("fileCount") != len(listed):
        raise ParityError("invalid_snapshot_inventory")
    for rel, recorded in source["files"].items():
        if listed.get(rel) != recorded:
            raise ParityError("source_has_drifted_since_qa_snapshot:" + rel)
    tree_hash = _digest("".join(
        f"{rel}\0{info['sha256']}\n" for rel, info in sorted(listed.items())
    ).encode("utf-8"))
    if (tree_hash != expected_snapshot_sha256 or
            proof.get("sourceFileCount") != len(listed) or
            result.get("sourceFileCount") != len(listed)):
        raise ParityError("snapshot_inventory_digest_mismatch")
    assets = _json(bundle / "vite-assets-sha256.json")
    if (not 1 <= len(assets) <= 1000 or
            proof.get("viteAssetsSha256") != _file_hash(
                bundle / "vite-assets-sha256.json")[0]):
        raise ParityError("vite_asset_manifest_mismatch")
    if archive_reader is None:
        try:
            from PyInstaller.archive.readers import CArchiveReader
        except ImportError as exc:
            raise ParityError("pyinstaller_archive_reader_unavailable") from exc
        archive_reader = CArchiveReader
    archive = archive_reader(str(artifact))
    toc = {name.replace("\\", "/"): name for name in archive.toc}
    if ("qa_proof/qa-provenance.json" not in toc or
            archive.extract(toc["qa_proof/qa-provenance.json"]) !=
            _bytes(bundle / "qa-provenance.json")):
        raise ParityError("embedded_qa_provenance_bytes_mismatch")
    for rel, item in assets.items():
        path = _inside(bundle / "vite-dist", rel)
        if (not isinstance(item, dict) or
                set(item) != {"sha256", "bytes"} or
                type(item["bytes"]) is not int or item["bytes"] < 0 or
                not isinstance(item["sha256"], str) or
                not SHA256.fullmatch(item["sha256"])):
            raise ParityError("invalid_vite_asset_record")
        digest, file_size = _file_hash(path)
        archived = toc.get("dist/" + rel)
        if (digest != item["sha256"] or file_size != item["bytes"] or
                archived is None or _digest(archive.extract(archived)) != digest):
            raise ParityError("embedded_vite_asset_mismatch")
    final_hash, final_size = _file_hash(artifact)
    if (final_hash, final_size) != (actual_hash, size):
        raise ParityError("qa_executable_changed_during_archive_inspection")
    return {"qaArtifactSha256": actual_hash,
            "qaProvenanceSha256": expected_provenance_sha256,
            "qaSourceSnapshotSha256": expected_snapshot_sha256,
            "embeddedProvenanceChecked": True, "viteAssetCount": len(assets),
            "nonRelease": True}


def audit(source_root: Path, *, observed_installed: str = OBSERVED_INSTALLED_BASELINE,
          expected_source_sha256: str | None = None, bundle: Path | None = None,
          qa_artifact: Path | None = None, expected_qa_sha256: str | None = None,
          expected_snapshot_sha256: str | None = None,
          expected_qa_provenance_sha256: str | None = None,
          archive_reader=None) -> dict:
    """A passing parity check is NEVER an installation or finance GO verdict."""
    checks = {}
    context = {"baselineVersion": observed_installed,
               "baselineProvenance": "operator_reported_2026-11-10"}

    def record(label, operation):
        try:
            value = operation()
            checks[label] = {"state": "PASS", **value}
            return value
        except (ParityError, OSError, ValueError, TypeError, KeyError,
                AttributeError, UnicodeError, SyntaxError) as exc:
            checks[label] = {"state": "BLOCKED", "reason": (
                str(exc) if isinstance(exc, ParityError) else type(exc).__name__)}
            return None

    source = record("source_metadata", lambda: inspect_source(source_root))
    def validate_baseline():
        baseline_tuple = _version(observed_installed)
        if baseline_tuple < _version(OBSERVED_INSTALLED_BASELINE):
            raise ParityError("installed_baseline_below_observed_1.0.26_floor")
        return {"baseline": observed_installed, "tuple": baseline_tuple}

    baseline = record("baseline_semver", validate_baseline)
    if source and baseline:
        context["candidateVersion"] = source["version"]
        def no_downgrade():
            if _version(source["version"]) <= baseline["tuple"]:
                raise ParityError("candidate_must_be_newer_than_installed")
            return {"candidateNewer": True}

        record("no_downgrade", no_downgrade)
    else:
        checks["no_downgrade"] = {"state": "BLOCKED", "reason": "version_unavailable"}
    if source:
        context["sourceFingerprintSha256"] = source["sourceFingerprintSha256"]
    if (source and type(expected_source_sha256) is str and
            SHA256.fullmatch(expected_source_sha256) and
            source["sourceFingerprintSha256"] == expected_source_sha256):
        checks["external_source_pin"] = {"state": "PASS", "sha256": expected_source_sha256}
    else:
        checks["external_source_pin"] = {"state": "BLOCKED",
                                         "reason": "missing_or_mismatched_external_source_pin"}
    if (source and bundle is not None and qa_artifact is not None and
            expected_qa_sha256 is not None and expected_snapshot_sha256 is not None and
            expected_qa_provenance_sha256 is not None):
        record("qa_candidate", lambda: inspect_qa_bundle(
            bundle, qa_artifact, expected_qa_sha256, expected_snapshot_sha256,
            source, expected_qa_provenance_sha256, archive_reader=archive_reader))
    else:
        checks["qa_candidate"] = {"state": "BLOCKED",
                                  "reason": "qa_bundle_artifact_and_pins_required"}
    if source:
        def source_stability():
            reread = inspect_source(source_root)
            if reread["sourceFingerprintSha256"] != source["sourceFingerprintSha256"]:
                raise ParityError("release_input_changed_during_attestation")
            return {"releaseInputsStableDuringAudit": True}

        record("source_stability", source_stability)
    else:
        checks["source_stability"] = {"state": "BLOCKED",
                                      "reason": "source_metadata_unavailable"}
    blockers = [name for name, result in checks.items() if result["state"] != "PASS"]
    return {"schema": 1, "readOnly": True,
            "decision": "VERSION_PARITY_ONLY" if not blockers else "BLOCKED",
            "mayInstall": False, "mayDeploy": False,
            "blockers": blockers, "checks": checks, "context": context,
            "safeNextSteps": (
                "Integrate latest source; choose a new version strictly above the "
                "independently confirmed installed baseline (at least 1.0.27 if 1.0.26); "
                "update package.json, package-lock.json root versions, "
                "madar_update.CURRENT_VERSION, create matching immutable "
                "scripts/build_integrated_v127.py wrapper and set dist:rc to it; "
                "update release readiness pins; build fresh QA-only artifact "
                "with explicit appVersion in qa-build-result and embedded "
                "qa-provenance; independently record source, snapshot, EXE SHA256 "
                "pins; run full release/rollback/signing gates before owner approval."),
            "limitations": ("Selected source-input hash is not a Git commit or whole-tree "
                            "identity; SHA256 pin must come from independent trusted "
                            "record; QA provenance is not an official publisher or "
                            "functional acceptance receipt; reported installed baseline "
                            "has not been independently re-read.")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--installed-version", default=OBSERVED_INSTALLED_BASELINE)
    parser.add_argument("--source-pin", help="Independent SHA256 of printed source fingerprint")
    parser.add_argument("--bundle", type=Path, default=LATEST_QA_BUNDLE)
    parser.add_argument("--qa-exe", type=Path, default=LATEST_QA_EXE)
    parser.add_argument("--qa-pin", default=LATEST_QA_SHA256,
                        help="External QA executable SHA256")
    parser.add_argument("--provenance-pin", default=LATEST_QA_PROVENANCE_SHA256,
                        help="External QA provenance JSON SHA256")
    parser.add_argument("--snapshot-pin", default=LATEST_QA_SNAPSHOT_SHA256,
                        help="External source snapshot tree SHA256")
    args = parser.parse_args(argv)
    try:
        result = audit(args.source, observed_installed=args.installed_version,
                       expected_source_sha256=args.source_pin, bundle=args.bundle,
                       qa_artifact=args.qa_exe, expected_qa_sha256=args.qa_pin,
                       expected_snapshot_sha256=args.snapshot_pin,
                       expected_qa_provenance_sha256=args.provenance_pin)
    except Exception as exc:
        result = {"schema": 1, "readOnly": True, "decision": "BLOCKED",
                  "mayInstall": False, "mayDeploy": False,
                  "blockers": ["internal_verifier_error"],
                  "checks": {"internal_verifier_error": {"state": "BLOCKED",
                             "reason": type(exc).__name__}}}
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["decision"] == "VERSION_PARITY_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
