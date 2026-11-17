"""Read-only, fail-closed Madar next-version release qualification.

Runs no installer/EXE/GUI, service, browser, build, test suite, network, or Git
write. Reads exact pinned QA inputs and default installed v1.0.26 only.
Optional --next-version-path is a previously created *candidate directory*.
It cannot authorize itself: a manifest and matching bytes are necessary, not
sufficient for live finance, migration, user approval or release.

Usage:
  python -B scripts/qa_madar_next_version_release_gate_20261110.py
  python -B scripts/qa_madar_next_version_release_gate_20261110.py --next-version-path D:\\CoS-Test\\candidate
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


SOURCE = Path(r"D:\CoS-Test\000- Madar\madar-mtr-v126-integration-20261110")
VITE_QA = Path(r"D:\CoS-Test\MTR-MADAR-SILEO-QA-20261110\run-20261110-163354-67a1ede34858")
EXE_QA = Path(r"D:\CoS-Test\MTR-MADAR-SILEO-QA-20261110\exe-only-20261110-164543-5e6ab975712e")
TARGET_VERSION = "1.0.27"  # plan only: NEVER change app/version here
BASELINE_VERSION = "1.0.26"
PINNED_MANIFEST_SHA = "33a9c9aec67d6c2175e1feb7e07d75748bdcfe58a50c6faebeb30c6e811d1553"
PINNED_VITE_SOURCE = "b8d2b61392c467765b395f261b3587ec3161bb3475a444bddb751ccf9a3d1768"
PINNED_VITE_JS = "f2c5f5c495482ca6fd6271e04eb4212e6b407ee775b44f90c3ab72bc13281856"
PINNED_QA_EXE = "f2d161bfc41576beb0dbd28cd8bb6154a32ffeb8cd69e15e0eca75bb24973468"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
MAX_JSON = 4 * 1024 * 1024
MAX_EXE = 400 * 1024 * 1024


class EvidenceError(ValueError):
    """No affirmative release claim can be derived from this input."""


def version_number(text: str) -> tuple[int, int, int]:
    match = VERSION.fullmatch(text) if isinstance(text, str) else None
    if not match:
        raise EvidenceError("invalid three-component version")
    return tuple(int(x) for x in match.groups())


def safe_path(path: Path, *, directory: bool | None = None) -> Path:
    """Read-only, reject symlinks, junctions and reparse ancestors."""
    path = Path(path)
    if not path.is_absolute():
        raise EvidenceError("only absolute evidence paths accepted")
    for item in (path, *path.parents):
        if not item.exists():
            continue
        details = item.lstat()
        if (item.is_symlink() or getattr(item, "is_junction", lambda: False)()
                or getattr(details, "st_file_attributes", 0) & 0x400):
            raise EvidenceError("linked or reparse evidence path")
    if not path.exists():
        raise EvidenceError("evidence path missing")
    if directory is True and not path.is_dir():
        raise EvidenceError("evidence directory missing")
    if directory is False:
        if not path.is_file():
            raise EvidenceError("evidence file missing")
        details = path.stat()
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise EvidenceError("evidence file not regular")
    return path


def digest(path: Path, *, max_bytes: int = MAX_EXE) -> str:
    path = safe_path(path, directory=False)
    if path.stat().st_size > max_bytes:
        raise EvidenceError("evidence file exceeds size bound")
    result = hashlib.sha256()
    with path.open("rb") as reader:
        while True:
            content = reader.read(1024 * 1024)
            if not content:
                break
            result.update(content)
    return result.hexdigest()


def read_json(path: Path) -> dict:
    path = safe_path(path, directory=False)
    if path.stat().st_size > MAX_JSON:
        raise EvidenceError("JSON evidence oversized")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvidenceError("evidence must be a JSON object")
    return value


def read_text(path: Path, *, limit: int = 2_000_000) -> str:
    path = safe_path(path, directory=False)
    if path.stat().st_size > limit:
        raise EvidenceError("source file exceeds limit")
    return path.read_text(encoding="utf-8")


def gate(code: str, passed: bool, detail: str, *, blocking: bool = True) -> dict:
    return {"code": code, "status": "PASS" if passed else
            ("NO_GO" if blocking else "UNKNOWN"),
            "detail": detail[:380]}


def installed_baseline(localappdata: Path | None = None) -> dict:
    """Read default Inno install pointer and v1.0.26 PE only, no profile data."""
    try:
        root = Path(localappdata or os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MadarDesk"
        safe_path(root, directory=True)
        pointer = root / "current-version.txt"
        version = read_text(pointer, limit=64).strip()
        version_number(version)
        exe = root / "versions" / BASELINE_VERSION / "Madar-Desk.exe"
        safe_path(exe, directory=False)
        if exe.stat().st_size < 1024:
            raise EvidenceError("installed EXE implausibly small")
        with exe.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise EvidenceError("installed EXE lacks MZ header")
        return {"status": "VERIFIED_PE_READ_ONLY", "version": version,
                "installedRoot": str(root), "v126Exe": str(exe),
                "v126ExeSha256": digest(exe), "readOnly": True}
    except (EvidenceError, OSError, UnicodeError) as error:
        return {"status": "BLOCKED", "reason": str(error)[:180]}


def git_state(source: Path) -> dict:
    """Never fetch, clean, stage, commit, refresh index or run source tests."""
    def run(*args):
        return subprocess.run(["git", *args], cwd=source,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=12, check=False)
    try:
        head = run("rev-parse", "--verify", "HEAD")
        status = run("status", "--porcelain=v1", "--untracked-files=all")
        branch = run("symbolic-ref", "-q", "--short", "HEAD")
        if (head.returncode or status.returncode or
                not re.fullmatch(r"[a-f0-9]{40}", head.stdout.strip())):
            raise EvidenceError("Git state not verifiable")
        entries = [item for item in status.stdout.splitlines() if item.strip()]
        return {"head": head.stdout.strip(), "detached": branch.returncode != 0,
                "clean": not entries, "dirtyCount": len(entries),
                "statusSample": entries[:9]}
    except (EvidenceError, OSError, subprocess.TimeoutExpired) as error:
        return {"error": str(error)[:180], "clean": False, "detached": True}


def source_version_contract(source: Path, installed: str) -> dict:
    """Check package/lock/updater/active release builder are exactly aligned."""
    try:
        pkg = read_json(source / "package.json")
        lock = read_json(source / "package-lock.json")
        updater = read_text(source / "madar_update.py")
        builder = read_text(source / "scripts" / "build_p1p2_v126_qa.py")
        setup = read_text(source / "scripts" / "madar-update.iss")
        activate = read_text(source / "scripts" / "Madar-Activate-Version.ps1")
        preflight = read_text(source / "scripts" / "Madar-Upgrade-Preflight.ps1")
        launcher = read_text(source / "scripts" / "Run-Madar.cmd")
        values = {
            "package": pkg.get("version"),
            "lock": lock.get("version"),
            "lockRoot": lock.get("packages", {}).get("", {}).get("version"),
        }
        match = re.search(r'(?m)^CURRENT_VERSION\s*=\s*"([0-9.]+)"', updater)
        values["updater"] = match.group(1) if match else None
        match = re.search(r'(?m)^VERSION\s*=\s*"([0-9.]+)"', builder)
        values["builder"] = match.group(1) if match else None
        assert all(isinstance(x, str) for x in values.values())
        monotonic = all(version_number(x) > version_number(installed)
                        for x in values.values())
        aligned = len(set(values.values())) == 1
        # The updater's explicit no-downgrade logic and full snapshot preflight
        # are necessary controls; their presence does not prove runtime success.
        safeguards = {
            "hashPinnedActivation": "Target program integrity verification failed" in activate,
            "explicitRollbackGate": "-AllowRollback" in activate,
            "backupContentHash": "Snapshot checksum mismatch" in preflight,
            "sameVersionNoOverwrite": "onlyifdoesntexist" in setup,
            "launcherPointer": "current-version.txt" in launcher,
            "installerDeclaredSha256": "EXE_SHA256" in setup,
            "defaultReleaseOutput": "OutputDir=..\\release" in setup,
        }
        if not all(safeguards.values()):
            raise EvidenceError("updater or installer controls absent: " +
                                ",".join(k for k, v in safeguards.items() if not v))
        return {"values": values, "aligned": aligned,
                "strictlyNewer": monotonic, "safeguards": safeguards,
                "targetVersion": TARGET_VERSION}
    except (EvidenceError, OSError, ValueError, AssertionError, UnicodeError) as error:
        return {"error": str(error)[:260], "aligned": False,
                "strictlyNewer": False}


def verify_qa_provenance(vite_dir: Path, exe_dir: Path) -> dict:
    """Use exact hashes and embedded PyInstaller archive, not display labels."""
    try:
        safe_path(vite_dir, directory=True)
        safe_path(exe_dir, directory=True)
        manifest_file = vite_dir / "source-manifest.json"
        if digest(manifest_file, max_bytes=MAX_JSON) != PINNED_MANIFEST_SHA:
            raise EvidenceError("pinned Vite source manifest SHA mismatch")
        manifest = read_json(manifest_file)
        vite = read_json(vite_dir / "qa-report.json")
        exe = read_json(exe_dir / "qa-exe-report.json")
        if (vite.get("status") != "QA_VITE_SOURCE_SNAPSHOT_VERIFIED"
                or exe.get("status") != "QA_WINDOWS_EXE_EMBEDDED_VITE_VERIFIED_NO_INSTALL"
                or vite.get("sourceSha256") != PINNED_VITE_SOURCE
                or exe.get("viteSourceManifestSha256") != PINNED_MANIFEST_SHA
                or manifest.get("sourceSha256") != PINNED_VITE_SOURCE
                or exe.get("version") != BASELINE_VERSION):
            raise EvidenceError("pinned QA reports disagree")
        js_rel = next((rel for rel, data in vite.get("compiled", {}).get(
            "assets", {}).items() if rel.endswith(".js")
            and data.get("sha256") == PINNED_VITE_JS), None)
        if js_rel is None:
            raise EvidenceError("pinned Sileo/help JS not declared")
        js = vite_dir / "vite-compiled" / js_rel
        if digest(js) != PINNED_VITE_JS:
            raise EvidenceError("Vite JS bytes differ from recorded hash")
        js_text = read_text(js)
        for marker in ("data-sileo-viewport", "mtr-context-help__trigger",
                       "راهنمای مدار"):
            if marker not in js_text:
                raise EvidenceError("missing compiled Sileo/help: " + marker)
        binary = Path(exe.get("qaExecutable", ""))
        if binary.parent != exe_dir / "exe-dist":
            raise EvidenceError("QA binary not inside its declared output run")
        if digest(binary) != PINNED_QA_EXE:
            raise EvidenceError("QA EXE SHA differs from recorded binary")
        from PyInstaller.archive.readers import CArchiveReader
        archive = CArchiveReader(str(binary))
        archive_names = {name.replace("\\", "/"): name for name in archive.toc}
        archive_name = archive_names.get("dist/" + js_rel)
        if not archive_name:
            raise EvidenceError("embedded Vite JS missing from Windows CArchive")
        embedded = archive.extract(archive_name)
        if hashlib.sha256(embedded).hexdigest() != PINNED_VITE_JS:
            raise EvidenceError("EXE embedded Sileo/help differs from Vite input")
        pyz = archive.open_embedded_archive("PYZ.pyz")
        pyz_names = set(pyz.toc)
        needed = {"mtr_e2_send_journal", "mtr_taraz_installed_peer",
                  "taraz_review_status"}
        runtime_ready = needed <= pyz_names
        missing = sorted(needed - pyz_names)
        return {"status": "PINNED_QA_EMBEDDED_FEATURES_VERIFIED",
                "qaVersion": BASELINE_VERSION,
                "qaExeSha256": PINNED_QA_EXE,
                "viteJsSha256": PINNED_VITE_JS,
                "runtimeMetadataImports": runtime_ready,
                "missingRuntimeModules": missing,
                "pyzModuleCount": len(pyz_names),
                "installerVerified": exe.get("installerBuilt") is True,
                "releaseSigned": exe.get("signed") is True,
                "officialFinanceReceiptVerified":
                    exe.get("officialFinanceReceiptVerified") is True}
    except (EvidenceError, OSError, ValueError, UnicodeError,
            KeyError, RuntimeError, ImportError) as error:
        return {"status": "BLOCKED", "reason": str(error)[:280]}


def runtime_parity(source: Path, exe_dir: Path, vite_dir: Path) -> dict:
    """Compare Python boundary and staged imports, do not treat module=live."""
    try:
        snapshot = vite_dir / "source-snapshot"
        stage = exe_dir / "python-input"
        native = read_text(source / "native_app.py")
        pinned = read_text(snapshot / "native_app.py")
        staged = read_text(stage / "native_app.py")
        if pinned != staged:
            raise EvidenceError("packaged native entrypoint differs from pinned QA source")
        required = ("mtr_e2_send_journal", "mtr_taraz_installed_peer",
                    "taraz_review_status")
        native_ast = ast.parse(native)
        imports = set()
        for node in ast.walk(native_ast):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        absent_source = [name for name in required
                         if name not in imports or not (source / (name+".py")).is_file()]
        absent_stage = [name for name in required
                        if not (stage / (name+".py")).is_file()]
        # Registered host-side finance/peer issuer is not a general E2 helper.
        # A source marker without an independently verified runtime would NOT
        # constitute a finance authority either.
        finance_issuer_live = bool(
            re.search(r"from\s+mtr_finance_authenticated_origin\s+import", native)
            or re.search(r"from\s+mtr_lan_finance_adapter\s+import", native))
        return {"sourceMatchesPackagedNative": native == staged,
                "metadataImportsPresentInLiveSource": not absent_source,
                "metadataImportsPresentInStage": not absent_stage,
                "absentSource": absent_source, "absentStage": absent_stage,
                "authenticatedFinanceRuntimeWired": finance_issuer_live,
                "sourceSha256": hashlib.sha256(native.encode()).hexdigest(),
                "stageSha256": hashlib.sha256(staged.encode()).hexdigest()}
    except (EvidenceError, OSError, SyntaxError, UnicodeError) as error:
        return {"error": str(error)[:250],
                "sourceMatchesPackagedNative": False,
                "metadataImportsPresentInStage": False,
                "authenticatedFinanceRuntimeWired": False}


def optional_candidate(path: Path | None, installed: dict) -> dict:
    """Read-only structural candidate audit; cannot accept self-attested QA."""
    if path is None:
        return {"status": "NOT_PROVIDED"}
    try:
        path = safe_path(path, directory=True)
        if any(part.lower() in {"appdata", "program files", "program files (x86)"}
               for part in path.parts):
            raise EvidenceError("candidate may not be under user profile or installed app")
        record = read_json(path / "release-evidence.json")
        version = record.get("version")
        if version != TARGET_VERSION or version_number(version) <= version_number(
                installed.get("version", BASELINE_VERSION)):
            raise EvidenceError("candidate version must be 1.0.27 and newer than installed")
        names = {"app": "Madar-Desk.exe",
                 "setup": "Madar-Desk-1.0.27-Setup.exe"}
        hashes = {}
        for key, name in names.items():
            desc = record.get("artifacts", {}).get(key, {})
            if (desc.get("filename") != name or
                    not isinstance(desc.get("sha256"), str)
                    or not HEX64.fullmatch(desc["sha256"])):
                raise EvidenceError("candidate artifact missing sha256 identity: " + key)
            target = path / name
            safe_path(target, directory=False)
            if not 1024 <= target.stat().st_size <= MAX_EXE:
                raise EvidenceError("candidate artifact invalid size: " + key)
            if digest(target) != desc["sha256"]:
                raise EvidenceError("candidate artifact SHA mismatch: " + key)
            with target.open("rb") as reader:
                if reader.read(2) != b"MZ":
                    raise EvidenceError("candidate not Windows PE: " + key)
            hashes[key] = desc["sha256"]
        return {"status": "ARTIFACT_BYTES_MATCH_SELF_DECLARED_MANIFEST_ONLY",
                "version": version, "artifactSha256": hashes,
                "authenticatedInstallerQA": False,
                "financeAndMigrationAcceptance": False}
    except (EvidenceError, OSError, UnicodeError, ValueError, KeyError) as error:
        return {"status": "BLOCKED", "reason": str(error)[:240]}


def evaluate(*, source: Path = SOURCE, vite_dir: Path = VITE_QA,
             exe_dir: Path = EXE_QA, localappdata: Path | None = None,
             next_version_path: Path | None = None,
             override: dict | None = None) -> dict:
    """All-positive, independently supported gates required before GO.

    Current evidence has no trusted end-to-end signed installer/rollback,
    genuine two-machine/permission QA, or official finance issuer. Even a
    self-declared candidate cannot eliminate those release blockers.
    """
    override = override or {}
    installed = override.get("installed") or installed_baseline(localappdata)
    git = override.get("git") or git_state(source)
    contract = override.get("version") or source_version_contract(
        source, installed.get("version", BASELINE_VERSION))
    qa = override.get("qa") or verify_qa_provenance(vite_dir, exe_dir)
    parity = override.get("parity") or runtime_parity(source, exe_dir, vite_dir)
    candidate = override.get("candidate") or optional_candidate(
        next_version_path, installed)
    checks = [
        gate("INSTALLED_BASELINE", installed.get("status") == "VERIFIED_PE_READ_ONLY",
             "installed current pointer and v1.0.26 PE independently read"),
        gate("NEXT_VERSION_MONOTONIC",
             bool(contract.get("aligned") and contract.get("strictlyNewer")),
             "package, lock, updater and active builder must agree on a version > installed"),
        gate("CLEAN_COMMITTED_SOURCE", bool(git.get("clean") and not git.get("detached")),
             "dirty/detached worktree is not a release-source commit"),
        gate("VITE_EXE_PROVENANCE", qa.get("status") ==
             "PINNED_QA_EMBEDDED_FEATURES_VERIFIED",
             "Sileo/help JS must match immutable Vite and EXE embedded SHA"),
        gate("NATIVE_SOURCE_PARITY", parity.get("sourceMatchesPackagedNative") is True,
             "packaged native_app.py must equal current reviewed source"),
        gate("METADATA_PEER_RUNTIME",
             parity.get("metadataImportsPresentInLiveSource") is True
             and parity.get("metadataImportsPresentInStage") is True
             and qa.get("runtimeMetadataImports") is True,
             "all manually queued Taraz metadata helper imports must be in EXE"),
        gate("AUTHENTICATED_PEER_FINANCE",
             parity.get("authenticatedFinanceRuntimeWired") is True
             and qa.get("officialFinanceReceiptVerified") is True,
             "no trusted authenticated peer/finance journal issuer readback demonstrated"),
        gate("NEW_RELEASE_INSTALLER",
             candidate.get("status") ==
             "ARTIFACT_BYTES_MATCH_SELF_DECLARED_MANIFEST_ONLY"
             and qa.get("installerVerified") is True
             and qa.get("releaseSigned") is True,
             "no independently signed 1.0.27 setup and verified versioned upgrade"),
        gate("INSTALL_ROLLBACK_RECOVERY_E2E", False,
             "no verified disposable 1.0.26→1.0.27 installer, rollback, crash and multi-DB recovery"),
        gate("GUI_LAN_SECURITY_E2E", False,
             "no full packaged Windows GUI, two-PC pinned TLS, ACL and offline conflict acceptance"),
        gate("OWNER_RELEASE_APPROVAL", False,
             "no explicit approval of a concrete fully reviewed, signed v1.0.27 release"),
    ]
    blocked = [item["code"] for item in checks if item["status"] != "PASS"]
    return {"schema": 1, "classification": "READ_ONLY_RELEASE_GATE_NOT_RELEASE",
            "status": "NO_GO" if blocked else "GO",
            "recommendedNextVersion": TARGET_VERSION, "checks": checks,
            "blockers": blocked,
            "evidence": {"installed": installed, "git": git,
                         "versionContract": contract, "pinnedQA": qa,
                         "runtimeParity": parity, "candidate": candidate},
            "sourceModified": False, "profileModified": False,
            "installedModified": False, "published": False,
            "officialFinanceReceiptVerified": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--next-version-path", type=Path, default=None,
                        help="optional existing local candidate folder, read-only")
    args = parser.parse_args(argv)
    result = evaluate(next_version_path=args.next_version_path)
    # ASCII JSON is intentional: Windows PowerShell 5.1 Python stdout can use
    # legacy cp1256, which cannot encode an arrow or every Unicode filename.
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if result["status"] == "GO" else 2


if __name__ == "__main__":
    sys.exit(main())
