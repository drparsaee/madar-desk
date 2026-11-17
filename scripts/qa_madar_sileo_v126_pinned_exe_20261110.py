"""Build immutable, isolated QA-only Windows EXE from pinned Madar 1.0.26 assets.

Not an installer, signed release, deployed binary, registered finance issuer, or
permission to overwrite the user's installed Madar. The already built and
source-hashed Vite snapshot is the immutable frontend source of truth.
Additional top-level Python imports, absent from the Vite snapshot, are copied
into a second SHA-bound private source layer BEFORE PyInstaller is started.
Never import Python modules from the mutable repository during packaging.

Run: python -B scripts/qa_madar_sileo_v126_pinned_exe_20261110.py
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from uuid import uuid4

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(r"D:\CoS-Test\000- Madar\madar-mtr-v126-integration-20261110")
QA_PARENT = Path(r"D:\CoS-Test\MTR-MADAR-SILEO-QA-20261110")
PINNED_RUN = QA_PARENT / "run-20261110-163354-67a1ede34858"
MANIFEST_SHA256 = "33a9c9aec67d6c2175e1feb7e07d75748bdcfe58a50c6faebeb30c6e811d1553"
SOURCE_SHA256 = "b8d2b61392c467765b395f261b3587ec3161bb3475a444bddb751ccf9a3d1768"
DEPENDENCY_SHA256 = "a30fc49c4517f46179b0859880dc42039e11635758e35a495e90c183417964ee"
VITE_MAIN_SHA256 = "f2c5f5c495482ca6fd6271e04eb4212e6b407ee775b44f90c3ab72bc13281856"
VITE_MAIN = "assets/main-Cd8KyHQW.js"
EXE_NAME = "Madar-Sileo-Help-v1.0.26-QA-ONLY-NONRELEASE.exe"
MAX_PYTHON_FILES = 220
MAX_PYTHON_BYTES = 30 * 1024 * 1024
MAX_EXE_BYTES = 350 * 1024 * 1024


class QaExeBlocked(RuntimeError):
    """The EXE is not independently eligible for the claimed QA result."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha(value: object) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":")).encode("utf-8"))


def reject_unsafe_path(path: Path, *, must_exist: bool = True) -> None:
    if not path.is_absolute():
        raise QaExeBlocked("absolute-only pinned QA path required")
    if must_exist and not path.exists():
        raise QaExeBlocked("missing pinned QA file/directory: " + str(path))
    for node in (path, *path.parents):
        if not node.exists():
            continue
        metadata = node.lstat()
        if (node.is_symlink() or getattr(node, "is_junction", lambda: False)()
                or (getattr(metadata, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))):
            raise QaExeBlocked("unsafe linked/reparse path: " + str(node))
    if must_exist and path.is_file():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise QaExeBlocked("not a regular independently owned pinned file")


def pinned_manifest(run: Path = PINNED_RUN) -> tuple[dict, dict]:
    """Check the exact immutable QA input snapshot and Vite provenance.

    This deliberately does not trust the currently dirty worktree's JS, CSS,
    package or dependency installation after the pinned Vite compilation.
    """
    reject_unsafe_path(run)
    manifest_file = run / "source-manifest.json"
    report_file = run / "qa-report.json"
    reject_unsafe_path(manifest_file)
    reject_unsafe_path(report_file)
    if sha256_file(manifest_file) != MANIFEST_SHA256:
        raise QaExeBlocked("pinned source-manifest bytes changed")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    report = json.loads(report_file.read_text(encoding="utf-8"))
    if (report.get("status") != "QA_VITE_SOURCE_SNAPSHOT_VERIFIED"
            or report.get("classification")
            != "SOURCE_SNAPSHOT_QA_ONLY_NONRELEASE_NOT_INSTALLED"
            or report.get("version") != "1.0.26"
            or report.get("sourceSha256") != SOURCE_SHA256
            or report.get("dependencySha256") != DEPENDENCY_SHA256
            or manifest.get("sourceSha256") != SOURCE_SHA256
            or manifest.get("dependencySha256") != DEPENDENCY_SHA256
            or canonical_sha(manifest.get("sourceFiles", {})) != SOURCE_SHA256
            or canonical_sha(manifest.get("dependencyFiles", {})) != DEPENDENCY_SHA256
            or report.get("windowsExecutable") != "NOT_BUILT"
            or report.get("installer") != "NOT_BUILT"):
        raise QaExeBlocked("pinned Vite/source provenance not trusted")
    snapshot = run / "source-snapshot"
    for relative, expected in (manifest["sourceFiles"] |
                               manifest["dependencyFiles"]).items():
        path = snapshot / relative
        reject_unsafe_path(path)
        if not path.is_file() or sha256_file(path) != expected:
            raise QaExeBlocked("pinned snapshot source changed: " + relative)
    package = json.loads((snapshot / "package.json").read_text(encoding="utf-8"))
    if (package.get("version") != "1.0.26"
            or package.get("dependencies", {}).get("sileo") != "0.1.6"):
        raise QaExeBlocked("pinned package identity differs")
    compiled = run / "vite-compiled"
    record = report.get("compiled", {})
    flags = record.get("checks", {})
    if (not flags or not all(value is True for value in flags.values())
            or record.get("assetCount") != len(record.get("assets", {}))
            or record.get("assets", {}).get(VITE_MAIN, {}).get("sha256") != VITE_MAIN_SHA256):
        raise QaExeBlocked("pinned Vite feature checks incomplete")
    for relative, attributes in record["assets"].items():
        path = compiled / relative
        reject_unsafe_path(path)
        if (not path.is_file() or path.stat().st_size != attributes["bytes"]
                or sha256_file(path) != attributes["sha256"]):
            raise QaExeBlocked("Vite compiled asset changed: " + relative)
    text = (compiled / VITE_MAIN).read_text(encoding="utf-8")
    for marker in ("data-sileo-viewport", "data-sileo-toast",
                   "mtr-context-help__trigger", "راهنمای مدار"):
        if marker not in text:
            raise QaExeBlocked("pinned compiled Vite lacks feature " + marker)
    return manifest, report


def supplementary_python_files(root: Path = ROOT) -> dict[str, str]:
    """Extra Python imports are bounded and separately pinned before freezing.

    Frontend, native entrypoint and updater are never read from this mutable
    root. They *must* use the immutable existing Vite QA source snapshot.
    """
    reject_unsafe_path(root)
    files = sorted(root.glob("*.py"))
    files = [file for file in files
             if file.name not in {"native_app.py", "madar_update.py"}]
    if not files or len(files) > MAX_PYTHON_FILES:
        raise QaExeBlocked("unbounded/missing supplementary Python dependency set")
    result: dict[str, str] = {}
    total = 0
    for file in files:
        reject_unsafe_path(file)
        info = file.stat()
        total += info.st_size
        if (not file.is_file() or info.st_size > 3 * 1024 * 1024
                or total > MAX_PYTHON_BYTES):
            raise QaExeBlocked("unbounded supplementary Python file")
        result[file.name] = sha256_file(file)
    required = {"lan.py", "offline_exchange.py", "cloud_continuity.py",
                "data_model.py", "collab.py", "automation_buttons.py",
                "finance.py", "attachments.py", "app_storage.py",
                "automation_v1.py", "gui_user_flow.py"}
    if not required <= result.keys():
        raise QaExeBlocked("required Windows host Python dependency missing")
    return result


def create_only_run(qa_parent: Path = QA_PARENT) -> Path:
    if qa_parent != QA_PARENT:
        raise QaExeBlocked("QA EXE outputs must stay inside approved QA parent")
    reject_unsafe_path(qa_parent)
    label = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = qa_parent / ("exe-only-" + label + "-" + uuid4().hex[:12])
    target.mkdir(mode=0o700, exist_ok=False)
    return target


def copy_python_layer(run: Path, extras: dict[str, str],
                      snapshot: Path) -> Path:
    """New isolated module tree cannot import mutable worktree on build."""
    package = run / "python-input"
    package.mkdir(exist_ok=False)
    for original in sorted(extras):
        source = ROOT / original
        destination = package / original
        with source.open("rb") as stream, destination.open("xb") as dest:
            shutil.copyfileobj(stream, dest, length=1024 * 1024)
        if sha256_file(destination) != extras[original]:
            raise QaExeBlocked("Python dependency mutated while being copied")
    for core in ("native_app.py", "madar_update.py"):
        source = snapshot / core
        destination = package / core
        with source.open("rb") as stream, destination.open("xb") as dest:
            shutil.copyfileobj(stream, dest, length=1024 * 1024)
        if sha256_file(destination) != sha256_file(source):
            raise QaExeBlocked("pinned core Python entrypoint changed during copy")
    return package


def isolated_environment(run: Path) -> dict[str, str]:
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
               "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS"}
    env = {key: value for key, value in os.environ.items()
           if key.upper() in allowed}
    for key in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "HOME",
                "USERPROFILE", "PYINSTALLER_CONFIG_DIR", "PYTHONPYCACHEPREFIX"):
        location = run / "isolated-env" / key.lower()
        location.mkdir(parents=True, exist_ok=True)
        env[key] = str(location)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CI"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    return env


def pyinstaller_command(run: Path, module_root: Path,
                        frontend: Path) -> list[str]:
    """No installer, --noconfirm, --clean, version bump or release path."""
    return [
        sys.executable, "-B", "-m", "PyInstaller", "--onefile",
        "--windowed", "--noupx", "--log-level", "WARN",
        "--name", Path(EXE_NAME).stem,
        "--distpath", str(run / "exe-dist"),
        "--workpath", str(run / "pyi-work"),
        "--specpath", str(run / "pyi-spec"),
        "--paths", str(module_root),
        "--icon", str(PINNED_RUN / "source-snapshot" / "assets" / "madar.ico"),
        "--add-data", str(frontend) + ";dist",
        str(module_root / "native_app.py"),
    ]


def verify_embedded_frontend(exe: Path, report: dict,
                             frontend: Path) -> dict:
    """Extract actual PE CArchive payloads; require byte-identical Vite files."""
    reject_unsafe_path(exe)
    info = exe.stat()
    if (not exe.is_file() or not 1_000_000 <= info.st_size <= MAX_EXE_BYTES):
        raise QaExeBlocked("invalid/missing bounded PyInstaller QA EXE")
    with exe.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise QaExeBlocked("Windows QA EXE lacks MZ/PE header")
    archive = CArchiveReader(str(exe))
    mapped = {name.replace("\\", "/"): name for name in archive.toc}
    extracted: dict[str, dict] = {}
    for relative, attributes in report["compiled"]["assets"].items():
        name = "dist/" + relative
        actual = mapped.get(name)
        if actual is None:
            raise QaExeBlocked("embedded Vite asset absent from PE: " + name)
        blob = archive.extract(actual)
        if (len(blob) != attributes["bytes"] or
                sha256_bytes(blob) != attributes["sha256"] or
                sha256_file(frontend / relative) != attributes["sha256"]):
            raise QaExeBlocked("embedded Vite asset differs from pinned source: " + name)
        if relative == VITE_MAIN:
            text = blob.decode("utf-8")
            for marker in ("data-sileo-viewport", "data-sileo-toast",
                           "mtr-context-help__trigger", "راهنمای مدار"):
                if marker not in text:
                    raise QaExeBlocked("embedded PE missing Sileo/help marker")
        extracted[name] = {
            "size": len(blob),
            "sha256": attributes["sha256"],
        }
    # No *general* host or installed application runtime was ever executed.
    return {"embeddedAssetsVerified": extracted,
            "embeddedSileoViewport": True,
            "embeddedHelpTrigger": True,
            "exeBytes": info.st_size,
            "exeSha256": sha256_file(exe)}


def installed_readonly_audit() -> dict:
    spec = importlib.util.spec_from_file_location(
        "sileo_v126_qa_readonly",
        ROOT / "scripts" / "qa_madar_sileo_v126_20261110.py")
    if spec is None or spec.loader is None:
        raise QaExeBlocked("existing installed audit could not load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.audit_installed()


def json_exclusive(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def build_qa_exe(*, runner=subprocess.run) -> dict:
    """Create-only script; preflight has no output side effects.

    A failed build writes an explicit BLOCKED report; it may leave incomplete
    files in its unique run, which must never be called verified or released.
    """
    manifest, report = pinned_manifest()
    supplemental = supplementary_python_files()
    pinned_core = {name: manifest["sourceFiles"][name]
                   for name in ("native_app.py", "madar_update.py")}
    installed_before = installed_readonly_audit()
    if installed_before.get("versionComparison") != "SAME_VERSION_NO_OVERWRITE":
        raise QaExeBlocked("installed version is not confirmed 1.0.26; no upgrade/downgrade")
    # Never make any output under the installed default app directory.
    installed_root = Path(installed_before["installRoot"]).resolve(strict=True)
    if QA_PARENT.resolve().is_relative_to(installed_root):
        raise QaExeBlocked("QA output overlaps installed program")
    run = create_only_run()
    result = {
        "schema": 1, "status": "BLOCKED", "classification":
        "QA_ONLY_WINDOWS_EXE_NOT_RELEASE_NOT_INSTALLED",
        "version": "1.0.26", "viteQaRun": str(PINNED_RUN),
        "viteSourceSha256": SOURCE_SHA256,
        "viteDependencySha256": DEPENDENCY_SHA256,
        "viteSourceManifestSha256": MANIFEST_SHA256,
        "viteMainJsSha256": VITE_MAIN_SHA256,
        "viteAssetCount": report["compiled"]["assetCount"],
        "pinnedCorePython": pinned_core,
        "supplementalPythonSha256": canonical_sha(supplemental),
        "supplementalPythonFiles": len(supplemental),
        "installedBefore": installed_before,
        "installedModifiedByThisOperation": False,
        "sourceWorktreeModifiedByThisOperation": False,
        "installerBuilt": False, "signed": False, "deployed": False,
        "realProfileUsed": False, "officialFinanceReceiptVerified": False,
        "runRoot": str(run),
        "qaExecutable": "NOT_VERIFIED",
    }
    try:
        snapshot = PINNED_RUN / "source-snapshot"
        frontend = PINNED_RUN / "vite-compiled"
        python = copy_python_layer(run, supplemental, snapshot)
        json_exclusive(run / "python-input-manifest.json", {
            "schema": 1, "supplementalFiles": supplemental,
            "supplementalSha256": canonical_sha(supplemental),
            "pinnedCorePython": pinned_core,
        })
        if supplementary_python_files() != supplemental:
            raise QaExeBlocked("supplemental Python source changed after staging")
        command = pyinstaller_command(run, python, frontend)
        if (run / "exe-dist").exists() or (run / "pyi-work").exists():
            raise QaExeBlocked("create-only build output unexpectedly exists")
        env = isolated_environment(run)
        proc = runner(command, cwd=python, env=env,
                      capture_output=True, text=True, encoding="utf-8",
                      errors="replace", timeout=240, check=False)
        result["pyInstallerExitCode"] = proc.returncode
        result["pyInstallerLogTail"] = (proc.stderr or proc.stdout)[-4000:]
        if proc.returncode:
            raise QaExeBlocked("PyInstaller failed; QA EXE not verified")
        if supplementary_python_files() != supplemental:
            raise QaExeBlocked("supplemental Python source changed during build")
        pinned_manifest()  # Full source/dependency/compiled post-hash invariant.
        for name, expected in {**supplemental, **pinned_core}.items():
            if sha256_file(python / name) != expected:
                raise QaExeBlocked("isolated Python entry/source changed during build")
        exe = run / "exe-dist" / EXE_NAME
        if not exe.is_file():
            raise QaExeBlocked("PyInstaller EXE missing at exclusive QA output path")
        result["embeddedEvidence"] = verify_embedded_frontend(exe, report, frontend)
        after = installed_readonly_audit()
        result["installedAfter"] = after
        if (after.get("exeSha256") != installed_before.get("exeSha256")
                or after.get("installedVersion") != installed_before.get("installedVersion")
                or after.get("status") != "EXACT_V126_PE_FOUND"):
            raise QaExeBlocked("installed same-version executable changed externally")
        result["qaExecutable"] = str(exe)
        result["status"] = "QA_WINDOWS_EXE_EMBEDDED_VITE_VERIFIED_NO_INSTALL"
    except (QaExeBlocked, OSError, subprocess.TimeoutExpired, ValueError,
            UnicodeError) as error:
        result["reason"] = str(error)[:1400]
    json_exclusive(run / "qa-exe-report.json", result)
    return result


def main() -> int:
    try:
        result = build_qa_exe()
    except (QaExeBlocked, OSError, ValueError, UnicodeError) as error:
        print("MTR_V126_PINNED_EXE_PREFLIGHT_BLOCKED " + str(error),
              flush=True)
        return 2
    print("MTR_V126_PINNED_EXE " + result["status"] + " " +
          result["runRoot"] + "\\qa-exe-report.json", flush=True)
    if result["status"] != "QA_WINDOWS_EXE_EMBEDDED_VITE_VERIFIED_NO_INSTALL":
        print("BLOCKER " + result.get("reason", "unknown"), flush=True)
        return 2
    print("WINDOWS_QA_EXE_HASH " + result["embeddedEvidence"]["exeSha256"],
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
