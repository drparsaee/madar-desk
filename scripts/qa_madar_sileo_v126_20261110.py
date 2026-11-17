"""Create-only, source-pinned v1.0.26 Sileo + context-help Vite QA bundle.

No installed application or user profile is used as a build input. The detached
dirty worktree is read as a source snapshot (including npm dependencies);
live source/dependency hashes must remain unchanged before and after building.
This is a QA asset bundle, not a release, an installer, or a financial proof.

Usage:
    python -B scripts/qa_madar_sileo_v126_20261110.py
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4


SOURCE = Path(r"D:\CoS-Test\000- Madar\madar-mtr-v126-integration-20261110")
QA_ROOT = Path(r"D:\CoS-Test\MTR-MADAR-SILEO-QA-20261110")
VERSION = "1.0.26"
SILEO_VERSION = "0.1.6"
SOURCE_DIRS = ("src", "public", "assets")
SOURCE_FILES = (
    "package.json", "package-lock.json", "index.html", "vite.config.js",
    "native_app.py", "madar_update.py", "scripts/sync_font.py",
)
MAX_SINGLE_FILE = 40 * 1024 * 1024
MAX_SOURCE_BYTES = 300 * 1024 * 1024
MAX_DEPS_BYTES = 400 * 1024 * 1024
MAX_INSTALLED_EXE = 350 * 1024 * 1024


class QaBlocked(RuntimeError):
    """The evidence is insufficient; no QA success may be claimed."""


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _encoded_sha(data: object) -> str:
    return hashlib.sha256(json.dumps(
        data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _reject_link(path: Path) -> None:
    info = path.lstat()
    if (path.is_symlink() or getattr(path, "is_junction", lambda: False)()
            or (getattr(info, "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))):
        raise QaBlocked("linked/reparse source or output path: " + str(path))


def _regular_file(path: Path):
    _reject_link(path)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_size > MAX_SINGLE_FILE):
        raise QaBlocked("oversized, hardlinked or nonregular QA source: " + str(path))
    return info


def inventory(source: Path, *, dependencies: bool = False) -> dict[str, str]:
    """Strict SHA256 map; add/delete/change/link in a source tree is observable."""
    if not source.is_absolute() or not source.is_dir():
        raise QaBlocked("explicit absolute existing source root required")
    _reject_link(source)
    relative_files: list[Path] = []
    if dependencies:
        roots = ("node_modules",)
    else:
        for name in SOURCE_FILES:
            path = source / name
            if not path.is_file():
                raise QaBlocked("required source file missing: " + name)
            relative_files.append(Path(name))
        roots = SOURCE_DIRS

    for name in roots:
        folder = source / name
        if not folder.is_dir():
            raise QaBlocked("required source directory missing: " + name)
        _reject_link(folder)
        for directory, subfolders, files in os.walk(folder, followlinks=False):
            parent = Path(directory)
            _reject_link(parent)
            subfolders.sort()
            files.sort()
            for subfolder in subfolders:
                target = parent / subfolder
                if not target.is_dir():
                    raise QaBlocked("non-directory source tree member")
                _reject_link(target)
            for file in files:
                relative_files.append((parent / file).relative_to(source))
    hashes: dict[str, str] = {}
    total = 0
    limit = MAX_DEPS_BYTES if dependencies else MAX_SOURCE_BYTES
    for relative in sorted(relative_files, key=lambda value: value.as_posix()):
        path = source / relative
        if not path.is_file():
            raise QaBlocked("source item vanished during hash: " + str(relative))
        info = _regular_file(path)
        total += info.st_size
        if total > limit:
            raise QaBlocked("source snapshot exceeds bounded QA size")
        hashes[relative.as_posix()] = _digest(path)
    return hashes


def require_ready(source: Path) -> dict:
    """Check actual App wiring, package/lock and independently installed deps."""
    package = json.loads((source / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((source / "package-lock.json").read_text(encoding="utf-8"))
    if (package.get("version") != VERSION or lock.get("version") != VERSION
            or lock.get("packages", {}).get("", {}).get("version") != VERSION):
        raise QaBlocked("source/package/lock version does not match 1.0.26")
    if (package.get("dependencies", {}).get("sileo") != SILEO_VERSION
            or lock.get("packages", {}).get("", {}).get(
                "dependencies", {}).get("sileo") != SILEO_VERSION
            or lock.get("packages", {}).get("node_modules/sileo", {}).get(
                "version") != SILEO_VERSION):
        raise QaBlocked("Sileo package and lock identity disagree")
    installed_sileo = json.loads((source / "node_modules" / "sileo" /
                                  "package.json").read_text(encoding="utf-8"))
    if installed_sileo.get("version") != SILEO_VERSION:
        raise QaBlocked("local Sileo dependency differs from locked package")
    app = (source / "src" / "App.jsx").read_text(encoding="utf-8")
    feedback = (source / "src" / "mtr_sileo_feedback.jsx").read_text(encoding="utf-8")
    help_ui = (source / "src" / "mtr_context_help.jsx").read_text(encoding="utf-8")
    help_data = (source / "src" / "mtr_context_help_data.js").read_text(encoding="utf-8")
    if (len(re.findall(r"<MadarSileoFeedback\b", app)) != 1
            or len(re.findall(r"<MadarContextHelp\b", app)) != 1
            or not re.search(
                r"import\s*\{MadarSileoFeedback\}\s*from\s*['\"]\./mtr_sileo_feedback\.jsx", app)
            or not re.search(
                r"import\s*\{MadarContextHelp\}\s*from\s*['\"]\./mtr_context_help\.jsx", app)
            or "currentSection={helpCurrentSection}" not in app
            or "availableSections={helpAvailableSections}" not in app):
        raise QaBlocked("Sileo root or contextual help has not been wired in App.jsx")
    if (len(re.findall(r"<Toaster\b", feedback)) != 1
            or "from 'sileo'" not in feedback
            or 'mtr-context-help__trigger' not in help_ui
            or "MADAR_HELP_SECTIONS" not in help_data
            or "officialFinanceReceiptVerified" in feedback):
        raise QaBlocked("source Sileo/help behavior or finance boundary changed")
    if not (source / "node_modules" / "vite" / "bin" / "vite.js").is_file():
        raise QaBlocked("offline installed Vite dependency unavailable")
    return {
        "version": VERSION,
        "sileo": SILEO_VERSION,
        "sileoRootMounts": 1,
        "helpRootMounts": 1,
        "helpHasVisibilityFilter": True,
    }


def _copy_inventory(source: Path, target: Path, hashes: dict[str, str]) -> None:
    """Create-only copy, hash readback. Output folder must be newly created."""
    for name, expected in hashes.items():
        relative = Path(name)
        original = source / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        # x+b refuses to overwrite even if another writer raced this build.
        with original.open("rb") as inp, destination.open("xb") as out:
            while True:
                chunk = inp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        if _digest(destination) != expected:
            raise QaBlocked("snapshot changed while being copied: " + name)


def _create_run_root(qa_root: Path) -> Path:
    if not qa_root.is_absolute():
        raise QaBlocked("absolute QA output root required")
    if qa_root.exists():
        _reject_link(qa_root)
        if not qa_root.is_dir():
            raise QaBlocked("QA output root is not a directory")
    else:
        # No unreviewed parent mkdir: only the exact approved QA root is new.
        if not qa_root.parent.is_dir():
            raise QaBlocked("QA root parent directory missing")
        _reject_link(qa_root.parent)
        qa_root.mkdir(exist_ok=False)
    label = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_root = qa_root / ("run-" + label + "-" + uuid4().hex[:12])
    run_root.mkdir(exist_ok=False)
    return run_root


def _bounded_build_env(run_root: Path) -> dict[str, str]:
    allow = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
             "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS"}
    result = {key: value for key, value in os.environ.items()
              if key.upper() in allow}
    for key in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "HOME",
                "USERPROFILE"):
        folder = run_root / "isolated-env" / key.lower()
        folder.mkdir(parents=True, exist_ok=True)
        result[key] = str(folder)
    result["CI"] = "1"
    result["NODE_ENV"] = "production"
    result["VITE_CJS_IGNORE_WARNING"] = "true"
    return result


def compile_snapshot(snapshot: Path, output: Path, run_root: Path) -> str:
    """Run snapshot's locally copied Vite. No npm install/network/profiles."""
    node = shutil.which("node")
    if not node:
        raise QaBlocked("local Node.js unavailable")
    argv = [node, str(snapshot / "node_modules" / "vite" / "bin" / "vite.js"),
            "build", "--mode", "production", "--outDir", str(output)]
    result = subprocess.run(
        argv, cwd=snapshot, env=_bounded_build_env(run_root),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=150, check=False)
    if result.returncode:
        raise QaBlocked("snapshot Vite compilation failed (exit {}): {}".format(
            result.returncode, (result.stderr or result.stdout)[-1200:]))
    return result.stdout[-1200:]


def inspect_compiled(output: Path) -> dict:
    """Check the actual Vite output contains Sileo root and contextual help."""
    html = output / "index.html"
    if not html.is_file():
        raise QaBlocked("Vite output has no index.html")
    html_text = html.read_text(encoding="utf-8")
    if ('<div id="root"></div>' not in html_text
            or not re.search(r"assets/[^\"']+\.js", html_text)):
        raise QaBlocked("compiled HTML does not load Vite entry")
    assets = output / "assets"
    if not assets.is_dir():
        raise QaBlocked("compiled assets directory missing")
    js = sorted(assets.glob("*.js"))
    css = sorted(assets.glob("*.css"))
    if not js or not css:
        raise QaBlocked("compiled JavaScript/CSS missing")
    js_content = "\n".join(file.read_text(encoding="utf-8") for file in js)
    css_content = "\n".join(file.read_text(encoding="utf-8") for file in css)
    checks = {
        "compiledSileoViewport": "data-sileo-viewport" in js_content,
        "compiledSileoToast": "data-sileo-toast" in js_content,
        "compiledHelpTrigger": "mtr-context-help__trigger" in js_content,
        "compiledHelpTitle": "راهنمای مدار" in js_content,
        "compiledHelpCss": ".mtr-context-help" in css_content,
        "compiledSileoCss": "data-sileo-viewport" in css_content,
        "compiledAppTarazManualBoundary": "tarazIntegrationQueue" in js_content,
    }
    if not all(checks.values()):
        raise QaBlocked("compiled bundle missing actual Sileo/help evidence: " +
                        ",".join(key for key, value in checks.items() if not value))
    files = [file for file in output.rglob("*") if file.is_file()]
    if not files:
        raise QaBlocked("no compiled output files")
    return {
        "checks": checks,
        "assetCount": len(files),
        "assets": {file.relative_to(output).as_posix(): {
            "bytes": file.stat().st_size, "sha256": _digest(file),
        } for file in sorted(files)},
    }


def audit_installed(*, localappdata: Path | None = None) -> dict:
    """Read-only audit of exact Inno default install root and v1.0.26 PE."""
    if localappdata is None:
        home = os.environ.get("LOCALAPPDATA")
        if not home:
            return {"status": "NO_LOCALAPPDATA", "targetVersion": VERSION}
        localappdata = Path(home)
    if not localappdata.is_absolute():
        return {"status": "INVALID_LOCALAPPDATA", "targetVersion": VERSION}
    root = localappdata / "Programs" / "MadarDesk"
    result = {"targetVersion": VERSION, "installRoot": str(root),
              "status": "NOT_FOUND_AT_DEFAULT_LOCATION"}
    if not root.is_dir():
        return result
    try:
        _reject_link(root)
        pointer = root / "current-version.txt"
        if not pointer.is_file():
            return {**result, "status": "POINTER_MISSING"}
        _regular_file(pointer)
        if pointer.stat().st_size > 64:
            raise QaBlocked("oversized installed version pointer")
        version = pointer.read_text(encoding="utf-8-sig").strip()
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise QaBlocked("malformed installed version pointer")
        result["installedVersion"] = version
        result["versionComparison"] = (
            "SAME_VERSION_NO_OVERWRITE" if version == VERSION
            else "INSTALLED_NEWER_NO_DOWNGRADE"
            if tuple(map(int, version.split("."))) > (1, 0, 26)
            else "INSTALLED_OLDER_NO_INSTALL")
        exe = root / "versions" / VERSION / "Madar-Desk.exe"
        result["v126Executable"] = str(exe)
        if not exe.is_file():
            return {**result, "status": "V126_EXE_NOT_FOUND"}
        _reject_link(exe)
        info = exe.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_size > MAX_INSTALLED_EXE):
            raise QaBlocked("unsafe or non-PE installed v1.0.26 executable")
        with exe.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise QaBlocked("installed v1.0.26 binary has no PE header")
        return {**result, "status": "EXACT_V126_PE_FOUND",
                "exeBytes": info.st_size, "exeSha256": _digest(exe),
                "readOnly": True}
    except (QaBlocked, OSError, UnicodeError) as error:
        return {**result, "status": "INSTALLED_AUDIT_BLOCKED",
                "reason": type(error).__name__}


def _write_json_exclusive(path: Path, value: dict):
    with path.open("x", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False, sort_keys=True, indent=2)
        out.write("\n")


def build_qa(
    source: Path = SOURCE, qa_root: Path = QA_ROOT,
    *, build=compile_snapshot, installed_audit=audit_installed,
) -> dict:
    """Use only source snapshots; return evidence, or a BLOCKED report on disk."""
    source = Path(source)
    ready = require_ready(source)
    live_files = inventory(source)
    dependencies = inventory(source, dependencies=True)
    initial_source = _encoded_sha(live_files)
    initial_deps = _encoded_sha(dependencies)
    run_root = _create_run_root(Path(qa_root))
    result = {
        "schema": 1, "status": "BLOCKED", "classification":
        "SOURCE_SNAPSHOT_QA_ONLY_NONRELEASE_NOT_INSTALLED",
        "sourceRoot": str(source),
        "outputRoot": str(run_root),
        "version": VERSION,
        "appWiring": ready,
        "sourceSha256": initial_source, "dependencySha256": initial_deps,
        "sourceFileCount": len(live_files),
        "dependencyFileCount": len(dependencies),
        "windowsExecutable": "NOT_BUILT",
        "installer": "NOT_BUILT",
        "officialFinanceReceiptVerified": False,
        "installedApplicationModified": False,
    }
    try:
        snapshot = run_root / "source-snapshot"
        snapshot.mkdir(exist_ok=False)
        _copy_inventory(source, snapshot, live_files)
        _copy_inventory(source, snapshot, dependencies)
        _write_json_exclusive(run_root / "source-manifest.json", {
            "schema": 1, "sourceSha256": initial_source,
            "dependencySha256": initial_deps,
            "sourceFiles": live_files, "dependencyFiles": dependencies,
        })
        if (inventory(source) != live_files
                or inventory(source, dependencies=True) != dependencies):
            raise QaBlocked("SOURCE_CHANGED_DURING_SNAPSHOT")
        output = run_root / "vite-compiled"
        result["viteLogTail"] = build(snapshot, output, run_root)
        # Check both the *snapshotted* inputs and the original input tree,
        # even if an independent worker edited or added a file during Vite.
        if (inventory(source) != live_files
                or inventory(source, dependencies=True) != dependencies):
            raise QaBlocked("SOURCE_CHANGED_DURING_BUILD")
        if (inventory(snapshot) != live_files
                or inventory(snapshot, dependencies=True) != dependencies):
            raise QaBlocked("SNAPSHOT_CHANGED_DURING_BUILD")
        result["compiled"] = inspect_compiled(output)
        if (inventory(source) != live_files
                or inventory(source, dependencies=True) != dependencies):
            raise QaBlocked("SOURCE_CHANGED_DURING_ASSET_AUDIT")
        result["installedAudit"] = installed_audit()
        result["status"] = "QA_VITE_SOURCE_SNAPSHOT_VERIFIED"
    except (QaBlocked, subprocess.TimeoutExpired, OSError, ValueError,
            UnicodeError) as error:
        result["reason"] = str(error)[:1100]
    _write_json_exclusive(run_root / "qa-report.json", result)
    return result


def main() -> int:
    try:
        result = build_qa()
    except (QaBlocked, OSError, ValueError, UnicodeError) as error:
        print("MTR_SILEO_V126_QA_BLOCKED_PREFLIGHT " + str(error), flush=True)
        return 2
    print("MTR_SILEO_V126_QA " + result["status"] + " " +
          str(Path(result["outputRoot"]) / "qa-report.json"), flush=True)
    if result["status"] != "QA_VITE_SOURCE_SNAPSHOT_VERIFIED":
        print("BLOCKER " + result.get("reason", "unknown"), flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
