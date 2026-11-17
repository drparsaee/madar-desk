"""Non-release, side-by-side Madar -> Taraz QA build (2026-11-10).

Writes ONLY to a unique directory below D:\\CoS-Test\\MTR-MADAR-TARAZ-QA-BUNDLE-20261110.
Never modifies the live worktree except for this pre-authorized script file.
Does not launch an application, install, sign, contact the network, or use profiles.
An EXE plus static/archived method evidence is NOT a functional LAN/finance test.
"""
from __future__ import annotations

import ast
import hashlib
import json
import marshal
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import types
import uuid

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PARENT = Path(r"D:\CoS-Test\MTR-MADAR-TARAZ-QA-BUNDLE-20261110")
METHODS = (
    "tarazIntegrationOpenLocal",
    "tarazIntegrationPrepare",
    "tarazIntegrationQueue",
    "tarazIntegrationHistory",
)
TESTS = (
    "tests/test_mtr_taraz_connection_contract_20261110.py",
    "tests/test_mtr_taraz_installed_peer_20261110.py",
)
STATIC_FILES = (
    "index.html", "package.json", "package-lock.json", "vite.config.js",
)
TREE_FOLDERS = ("src", "public", "assets", "node_modules")
EXE_NAME = "Madar-Taraz-Connection-QA-20261110-NONRELEASE.exe"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json_new(path: Path, data: object) -> None:
    with path.open("x", encoding="utf-8") as destination:
        json.dump(data, destination, indent=2, ensure_ascii=False, sort_keys=True)
        destination.write("\n")


def assert_regular(path: Path, *, directory: bool = False) -> None:
    if path.is_symlink() or not path.exists():
        raise RuntimeError("Missing or linked build input: " + str(path))
    if directory:
        if not path.is_dir():
            raise RuntimeError("Expected directory: " + str(path))
    elif not path.is_file():
        raise RuntimeError("Expected regular file: " + str(path))
    if path.stat().st_file_attributes & 1024 if os.name == "nt" else False:
        raise RuntimeError("Reparse-point build input: " + str(path))


def list_inputs() -> list[Path]:
    selected = [ROOT / name for name in (*STATIC_FILES, *TESTS)]
    selected += sorted(ROOT.glob("*.py"))
    for folder in TREE_FOLDERS:
        start = ROOT / folder
        assert_regular(start, directory=True)
        for current, dirs, files in os.walk(start, followlinks=False):
            base = Path(current)
            for name in dirs:
                assert_regular(base / name, directory=True)
            for name in files:
                selected.append(base / name)
    for path in selected:
        assert_regular(path)
        if path.resolve().is_relative_to(ROOT.resolve()) is False:
            raise RuntimeError("Input outside source root: " + str(path))
    rels = [p.relative_to(ROOT).as_posix() for p in selected]
    if len(rels) != len(set(rels)):
        raise RuntimeError("Duplicate source inputs")
    return sorted(selected, key=lambda p: p.relative_to(ROOT).as_posix())


def verify_methods() -> dict:
    native = ROOT / "native_app.py"
    ui = ROOT / "src" / "App.jsx"
    assert_regular(native)
    assert_regular(ui)
    tree = ast.parse(native.read_text(encoding="utf-8"), filename=str(native))
    bridges = [node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "Bridge"]
    if len(bridges) != 1:
        raise RuntimeError("Cannot find the current native Bridge class")
    declared = {node.name for node in bridges[0].body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    missing = set(METHODS) - declared
    exported = native.read_text(encoding="utf-8")
    app = ui.read_text(encoding="utf-8")
    if missing or any(repr(name) not in exported for name in METHODS):
        raise RuntimeError("Missing callable/exported native integration method: "
                           + ",".join(sorted(missing)))
    calls = {
        "tarazIntegrationOpenLocal": "api.tarazIntegrationOpenLocal(true)",
        "tarazIntegrationPrepare": "api.tarazIntegrationPrepare(taskId)",
        "tarazIntegrationQueue": "api.tarazIntegrationQueue(taskId,null,targetId)",
        "tarazIntegrationHistory": "api.tarazIntegrationHistory(task.id,true)",
    }
    if any(call not in app for call in calls.values()):
        raise RuntimeError("UI lacks a current explicit integration action")
    if "tarazIntegrationStatus" not in app or "tarazIntegrationStatus" not in declared:
        raise RuntimeError("Integration status method is absent")
    return {
        "nativeBridgeMethods": list(METHODS),
        "nativeAndUiSource": {
            "native_app.py": sha256(native),
            "src/App.jsx": sha256(ui),
        },
        "uiCalls": calls,
    }


def copy_snapshot(inputs: list[Path], snapshot: Path) -> tuple[dict, str]:
    manifest = {}
    tree_digest = hashlib.sha256()
    for source in inputs:
        rel = source.relative_to(ROOT)
        target = snapshot / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        before = sha256(source)
        with source.open("rb") as original, target.open("xb") as output:
            shutil.copyfileobj(original, output, length=1024 * 1024)
        copied = sha256(target)
        if before != copied or sha256(source) != copied:
            raise RuntimeError("Source changed during snapshot copy: " + str(rel))
        manifest[rel.as_posix()] = {"sha256": copied, "bytes": target.stat().st_size}
        tree_digest.update(f"{rel.as_posix()}\0{copied}\n".encode("utf-8"))
    return manifest, tree_digest.hexdigest()


def run_offline(command: list[str], *, cwd: Path, env: dict,
                log: Path, seconds: int) -> None:
    with log.open("x", encoding="utf-8", errors="replace") as stream:
        stream.write("COMMAND: " + " ".join(command) + "\n")
        stream.flush()
        try:
            result = subprocess.run(command, cwd=str(cwd), env=env,
                                    stdin=subprocess.DEVNULL, stdout=stream,
                                    stderr=subprocess.STDOUT,
                                    timeout=seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Timed out after {seconds}s: {log}") from exc
    if result.returncode:
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-18:]
        raise RuntimeError(f"Build command exit {result.returncode}: {log}\n"
                           + "\n".join(tail))


def bundle_files(dist: Path) -> tuple[dict, list[str]]:
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError("Vite did not generate index.html")
    files = sorted(p for p in dist.rglob("*") if p.is_file())
    js = [p for p in files if p.suffix == ".js"]
    if not js:
        raise RuntimeError("Vite emitted no JS bundle")
    scripts = "\n".join(p.read_text(encoding="utf-8") for p in js)
    missing = [name for name in (*METHODS, "tarazIntegrationStatus")
               if name not in scripts]
    if missing:
        raise RuntimeError("Compiled Vite UI missing method names: " + str(missing))
    return ({p.relative_to(dist).as_posix(): {
        "sha256": sha256(p), "bytes": p.stat().st_size
    } for p in files}, [name for name in (*METHODS, "tarazIntegrationStatus")
                       if name in scripts])


def bytecode_methods(code: types.CodeType) -> tuple[bool, set[str]]:
    """Find compiled Bridge class body, never execute archived code."""
    for nested in code.co_consts:
        if isinstance(nested, types.CodeType) and nested.co_name == "Bridge":
            return True, set(nested.co_names)
        if isinstance(nested, types.CodeType):
            found, names = bytecode_methods(nested)
            if found:
                return found, names
    return False, set()


def verify_exe(exe: Path, proof: Path, web_files: dict) -> dict:
    if not exe.is_file() or exe.stat().st_size < 4096:
        raise RuntimeError("PyInstaller EXE missing or too small")
    with exe.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise RuntimeError("QA artifact is not a Windows PE file")
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(exe))
    names = set(archive.toc)
    # PyInstaller TOC paths are Windows backslashes on this build host.
    portable_names = {name.replace("\\", "/"): name for name in names}
    script_key = next((name for name in ("native_app", "native_app.py")
                       if name in names), None)
    if script_key is None:
        raise RuntimeError("Executable has no native_app entrypoint")
    data = archive.extract(script_key)
    compiled = None
    for offset in (0, 16, 12, 8):
        try:
            candidate = marshal.loads(data[offset:])
        except (EOFError, ValueError, TypeError):
            continue
        if isinstance(candidate, types.CodeType):
            compiled = candidate
            break
    if compiled is None:
        raise RuntimeError("Could not inspect compiled entrypoint bytecode")
    found, compiled_names = bytecode_methods(compiled)
    if not found or not set(METHODS).issubset(compiled_names):
        raise RuntimeError("Compiled Bridge is missing integration method(s)")
    embedded_proof = "qa_proof/" + proof.name
    if (embedded_proof not in portable_names or
            archive.extract(portable_names[embedded_proof]) != proof.read_bytes()):
        raise RuntimeError("Executable provenance receipt does not match")
    missing_assets = ["dist/" + rel for rel in web_files
                      if "dist/" + rel not in portable_names]
    if missing_assets:
        raise RuntimeError("Compiled EXE missing Vite data: " + str(missing_assets[:5]))
    for rel, expected in web_files.items():
        actual = archive.extract(portable_names["dist/" + rel])
        if hashlib.sha256(actual).hexdigest() != expected["sha256"]:
            raise RuntimeError("Embedded Vite data mismatch: " + rel)
    return {
        "filename": exe.name, "bytes": exe.stat().st_size, "sha256": sha256(exe),
        "windowsPE": True, "compiledBridgeMethods": sorted(set(METHODS) & compiled_names),
        "embeddedProvenanceMatches": True, "embeddedViteAssetsVerified": len(web_files),
        "executed": False, "releaseReady": False,
    }


def main() -> int:
    report = {"schemaVersion": 1, "status": "BLOCKED", "purpose": "QA_ONLY_NON_RELEASE",
              "noInstallNoSignNoDeployNoNetwork": True, "run": None}
    destination = None
    try:
        if (ROOT.name != "madar-p2-gantt-notifications-20261107"
                or ROOT.parent.name != "000- Madar"):
            raise RuntimeError("Refusing to run outside the owner-selected Madar worktree")
        if OUTPUT_PARENT.exists() and (OUTPUT_PARENT.is_symlink()
                                       or not OUTPUT_PARENT.is_dir()):
            raise RuntimeError("Unsafe output parent")
        if ROOT.resolve().is_relative_to(OUTPUT_PARENT.resolve()) or \
                OUTPUT_PARENT.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError("Build output must be outside the source worktree")
        verified = verify_methods()  # REQUIRED before *any* build command.
        inputs = list_inputs()
        for tool in ("npm.cmd",):
            if shutil.which(tool) is None:
                raise RuntimeError("Missing offline local tool: " + tool)
        if not (ROOT / "node_modules" / "vite" / "bin" / "vite.js").is_file():
            raise RuntimeError("Existing local Vite package is missing; no network install allowed")
        try:
            import PyInstaller  # noqa: F401, prerequisite only
            import webview  # noqa: F401, prerequisite only
        except ImportError as error:
            raise RuntimeError("Missing installed Python packaging prerequisite") from error
        OUTPUT_PARENT.mkdir(parents=True, exist_ok=True)
        destination = OUTPUT_PARENT / (
            time.strftime("run-%Y%m%d-%H%M%S") + "-" + str(os.getpid())
            + "-" + uuid.uuid4().hex[:8])
        destination.mkdir(exist_ok=False)
        report["run"] = str(destination)
        snapshot = destination / "source"
        snapshot.mkdir(exist_ok=False)
        files, tree_sha = copy_snapshot(inputs, snapshot)
        save_json_new(destination / "source-input-sha256.json", {
            "sourceRoot": str(ROOT), "sourceSnapshotTreeSha256": tree_sha,
            "fileCount": len(files), "files": files,
            "note": "Snapshot includes present dirty worktree files; not a Git commit attestation.",
        })
        # Compilers work ONLY on the private source snapshot, never the live repo.
        qa_env = os.environ.copy()
        runtime = destination / "sandbox-runtime"
        for directory in ("tmp", "npm-cache", "pyinstaller-cache", "python-cache",
                          "user-profile", "appdata", "localappdata"):
            (runtime / directory).mkdir(parents=True, exist_ok=False)
        qa_env.update({
            "TEMP": str(runtime / "tmp"), "TMP": str(runtime / "tmp"),
            "TMPDIR": str(runtime / "tmp"),
            "APPDATA": str(runtime / "appdata"),
            "LOCALAPPDATA": str(runtime / "localappdata"),
            "USERPROFILE": str(runtime / "user-profile"),
            "HOME": str(runtime / "user-profile"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYINSTALLER_CONFIG_DIR": str(runtime / "pyinstaller-cache"),
            "npm_config_cache": str(runtime / "npm-cache"),
            "npm_config_offline": "true", "npm_config_audit": "false",
            "npm_config_fund": "false", "npm_config_update_notifier": "false",
            "CI": "true",
        })
        ui_dir = destination / "vite-dist"
        run_offline([
            "npm.cmd", "exec", "--offline", "--no", "--", "vite", "build",
            "--outDir", str(ui_dir), "--configLoader", "runner",
        ], cwd=snapshot, env=qa_env, log=destination / "vite-build.log", seconds=600)
        ui_files, methods = bundle_files(ui_dir)
        save_json_new(destination / "vite-assets-sha256.json", ui_files)
        proof = destination / "qa-provenance.json"
        save_json_new(proof, {
            "schemaVersion": 1, "purpose": "NON_RELEASE_QA",
            "sourceSnapshotTreeSha256": tree_sha,
            "sourceFileCount": len(files),
            "nativeSourceSha256": files["native_app.py"]["sha256"],
            "uiSourceSha256": files["src/App.jsx"]["sha256"],
            "testSourceSha256": {name: files[name]["sha256"] for name in TESTS},
            "viteAssetsSha256": sha256(destination / "vite-assets-sha256.json"),
            "preflight": verified, "uiMethodsInCompiledJs": methods,
            "notFunctionalTestOrReleaseApproval": True,
        })
        dist = destination / "exe-dist"
        work = destination / "pyinstaller-work"
        spec = destination / "pyinstaller-spec"
        run_offline([
            sys.executable, "-B", "-m", "PyInstaller",
            "--onefile", "--windowed", "--name", Path(EXE_NAME).stem,
            "--distpath", str(dist), "--workpath", str(work), "--specpath", str(spec),
            "--add-data", str(ui_dir) + os.pathsep + "dist",
            "--add-data", str(proof) + os.pathsep + "qa_proof",
            "--icon", str(snapshot / "assets" / "madar.ico"),
            str(snapshot / "native_app.py"),
        ], cwd=snapshot, env=qa_env,
            log=destination / "pyinstaller-build.log", seconds=1200)
        exe = dist / EXE_NAME
        report.update({
            "status": "QA_BUILT_NON_RELEASE",
            "sourceSnapshotTreeSha256": tree_sha, "sourceFileCount": len(files),
            "frontend": {"files": len(ui_files), "methods": methods,
                         "sha256Manifest": sha256(destination / "vite-assets-sha256.json")},
            "provenance": {"filename": proof.name, "sha256": sha256(proof),
                           "testSourceSha256": {name: files[name]["sha256"] for name in TESTS}},
            "application": verify_exe(exe, proof, ui_files),
        })
        # Only observe concurrent source drift. The built snapshot itself is immutable.
        selected = (*TESTS, "native_app.py", "src/App.jsx",
                    "taraz_exchange.py", "package.json", "vite.config.js")
        report["liveSourceDriftOnSelectedFiles"] = [
            name for name in selected if name in files and
            (not (ROOT / name).is_file() or sha256(ROOT / name) != files[name]["sha256"])
        ]
        print("QA_BUILT_NON_RELEASE", str(exe), report["application"]["sha256"],
              "source_files", len(files), flush=True)
        return 0
    except Exception as error:
        report["blocker"] = type(error).__name__ + ": " + str(error)
        print("QA_BUILD_BLOCKED", report["blocker"], file=sys.stderr, flush=True)
        return 1
    finally:
        if destination is not None and destination.is_dir():
            # Each invocation creates a NEW run directory. Never erase older QA evidence.
            save_json_new(destination / "qa-build-result.json", report)


if __name__ == "__main__":
    raise SystemExit(main())
