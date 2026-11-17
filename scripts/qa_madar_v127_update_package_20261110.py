"""Create-only isolated *QA* v1.0.27 Madar offline update candidate.

This does NOT install/launch the app or installer, sign/release, alter the
installed v1.0.26, write live profiles, or fetch data from the network.

Source: previously SHA-attested Sileo/help Vite QA and independent Windows EXE
staging.  The frozen v1.0.26 updater is NOT relabeled: ONLY a private staged
copy of madar_update.py is set to v1.0.27 and PyInstaller is rerun. The
existing Inno script is copied read-only into an isolated build tree and
compiled with /DQA /DCOMPACT to a hardcoded synthetic QA install root. This
setup cannot update the real user's installed location.

If the runtime/setup cannot be safely generated, emit only a hash-pinned QA
proposal ZIP with the original correctly labeled v1.0.26 executable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

from PyInstaller.archive.readers import CArchiveReader

SOURCE = Path(r"D:\CoS-Test\000- Madar\madar-mtr-v126-integration-20261110")
VITE = Path(r"D:\CoS-Test\MTR-MADAR-SILEO-QA-20261110\run-20261110-163354-67a1ede34858")
PRIOR = Path(r"D:\CoS-Test\MTR-MADAR-SILEO-QA-20261110\exe-only-20261110-164543-5e6ab975712e")
OUT = Path(r"D:\CoS-Test\MTR-NEXT-UPDATE-CANDIDATES-20261110\madar-v1.0.27")
ISCC = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"
TARGET = "1.0.27"
INSTALLED = "1.0.26"
PRIOR_EXE_SHA = "f2d161bfc41576beb0dbd28cd8bb6154a32ffeb8cd69e15e0eca75bb24973468"
VITE_JS_SHA = "f2c5f5c495482ca6fd6271e04eb4212e6b407ee775b44f90c3ab72bc13281856"
VITE_MANIFEST_SHA = "33a9c9aec67d6c2175e1feb7e07d75748bdcfe58a50c6faebeb30c6e811d1553"
PYTHON_LAYER_SHA = "bccdc21dd8c0b2641b2f43f19219c0b7cbd09b38d0c52b5585faf35b2d19e1a3"
CURRENT_INSTALLED_EXE_SHA = "9bb1471944fc4b31aece7470e9d433fb68e207653d865ca3881c8d5654c943a4"
PAYLOAD_NAME = "Madar-Desk-v1.0.27-QA-ONLY-NONRELEASE.exe"
SETUP_NAME = "Madar-Desk-1.0.27-Setup-QA-ONLY-NONRELEASE.exe"
FALLBACK_NAME = "Madar-Desk-v1.0.27-PACKAGING-PROPOSAL-QA-ONLY-NO-SETUP.zip"
PRIOR_NAME = "Madar-Desk-v1.0.26-Sileo-Help-BASELINE-QA-ONLY.exe"
REQUIRED = (
    "scripts/madar-update.iss",
    "scripts/Madar-Upgrade-Preflight.ps1",
    "scripts/Madar-Activate-Version.ps1",
    "scripts/Run-Madar.cmd",
)
MAX_PE = 400 * 1024 * 1024


class QaBlock(RuntimeError):
    """Fail closed without asserting a valid update candidate."""


def file_sha(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def data_sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def canonical_sha(mapping: object) -> str:
    return data_sha(json.dumps(mapping, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8"))


def safe(path: Path, *, file: bool = True, max_size: int = MAX_PE) -> Path:
    path = Path(path)
    if not path.is_absolute() or not path.exists():
        raise QaBlock("absolute existing QA input required")
    for node in (path, *path.parents):
        if not node.exists():
            continue
        info = node.lstat()
        if (node.is_symlink() or getattr(node, "is_junction", lambda: False)()
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise QaBlock("linked/junction/reparse input forbidden")
    if file:
        if not path.is_file():
            raise QaBlock("required regular input file missing")
        st = path.stat()
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_size > max_size):
            raise QaBlock("nonregular, hardlinked or oversized input")
    elif not path.is_dir():
        raise QaBlock("QA directory input missing")
    return path


def json_read(path: Path) -> dict:
    safe(path, max_size=5_000_000)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QaBlock("JSON input must be an object")
    return value


def write_json_x(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def copy_verified(source: Path, destination: Path, sha: str) -> None:
    safe(source)
    if file_sha(source) != sha:
        raise QaBlock("input source hash changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as original, destination.open("xb") as target:
        shutil.copyfileobj(original, target, 1024 * 1024)
    if file_sha(destination) != sha:
        raise QaBlock("create-only copied QA input differs")


def overlay_version(raw: bytes) -> bytes:
    """Only one pinned updater assignment changed in a disposable build copy."""
    old = b'CURRENT_VERSION = "1.0.26"'
    if raw.count(old) != 1 or b'CURRENT_VERSION = "1.0.27"' in raw:
        raise QaBlock("exact pinned v1.0.26 updater assignment missing/ambiguous")
    modified = raw.replace(old, b'CURRENT_VERSION = "1.0.27"', 1)
    if modified == raw or modified.count(b'CURRENT_VERSION = "1.0.27"') != 1:
        raise QaBlock("private runtime version overlay failed")
    return modified


def set_pkg_version(raw: bytes) -> bytes:
    data = json.loads(raw.decode("utf-8"))
    if data.get("version") != INSTALLED:
        raise QaBlock("source package/lock is not pinned baseline v1.0.26")
    data["version"] = TARGET
    if "packages" in data:
        if data["packages"].get("", {}).get("version") != INSTALLED:
            raise QaBlock("package-lock root version does not match baseline")
        data["packages"][""]["version"] = TARGET
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def pinned_inputs() -> dict:
    """Reject missing/stale frozen binary, source manifest or asset provenance."""
    safe(SOURCE, file=False)
    safe(PRIOR, file=False)
    safe(VITE, file=False)
    if file_sha(VITE / "source-manifest.json") != VITE_MANIFEST_SHA:
        raise QaBlock("pinned Vite source manifest hash mismatch")
    manifest = json_read(VITE / "source-manifest.json")
    vite = json_read(VITE / "qa-report.json")
    old = json_read(PRIOR / "qa-exe-report.json")
    layer = json_read(PRIOR / "python-input-manifest.json")
    if (old.get("status") != "QA_WINDOWS_EXE_EMBEDDED_VITE_VERIFIED_NO_INSTALL"
            or old.get("version") != INSTALLED
            or old.get("embeddedEvidence", {}).get("exeSha256") != PRIOR_EXE_SHA
            or vite.get("status") != "QA_VITE_SOURCE_SNAPSHOT_VERIFIED"
            or old.get("viteSourceManifestSha256") != VITE_MANIFEST_SHA
            or canonical_sha(layer.get("supplementalFiles", {})) != PYTHON_LAYER_SHA
            or layer.get("supplementalSha256") != PYTHON_LAYER_SHA):
        raise QaBlock("old QA executable or source provenance unverified")
    old_exe = Path(old["qaExecutable"])
    if old_exe.parent != PRIOR / "exe-dist" or file_sha(safe(old_exe)) != PRIOR_EXE_SHA:
        raise QaBlock("pinned v1.0.26 EXE missing or modified")
    # Check the original artifact really carries the audited frontend.
    archive = CArchiveReader(str(old_exe))
    names = {name.replace("\\", "/"): name for name in archive.toc}
    js = next((name for name, details in vite.get("compiled", {}).get("assets", {}).items()
               if name.endswith(".js") and details.get("sha256") == VITE_JS_SHA), None)
    if not js or "dist/" + js not in names:
        raise QaBlock("old QA EXE has no pinned Sileo/help JS")
    if data_sha(archive.extract(names["dist/" + js])) != VITE_JS_SHA:
        raise QaBlock("old QA EXE embedded Vite hash mismatch")
    pyz = archive.open_embedded_archive("PYZ.pyz")
    old_update = pyz.extract("madar_update")
    if old_update is None or INSTALLED not in old_update.co_consts or TARGET in old_update.co_consts:
        raise QaBlock("old embedded updater version not confirmed as 1.0.26")
    if (manifest.get("sourceFiles", {}).get("madar_update.py")
            != layer.get("pinnedCorePython", {}).get("madar_update.py")):
        raise QaBlock("v1.0.26 updater source identity disagrees")
    # Unmodified source tree's installed version must be read, never inferred.
    local = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "MadarDesk"
    safe(local, file=False)
    pointer = safe(local / "current-version.txt", max_size=64)
    current = pointer.read_text(encoding="utf-8-sig").strip()
    if current != INSTALLED:
        raise QaBlock("installed version is not exact expected v1.0.26")
    current_exe = safe(local / "versions" / INSTALLED / "Madar-Desk.exe")
    if file_sha(current_exe) != CURRENT_INSTALLED_EXE_SHA:
        raise QaBlock("installed v1.0.26 baseline hash changed")
    return {
        "sourceManifestSha256": VITE_MANIFEST_SHA,
        "viteSourceInventorySha256": manifest["sourceSha256"],
        "viteDependencyInventorySha256": manifest["dependencySha256"],
        "viteJsSha256": VITE_JS_SHA,
        "priorExeSha256": PRIOR_EXE_SHA,
        "priorPyModulesSha256": PYTHON_LAYER_SHA,
        "installedBefore": {"version": current, "sha256": CURRENT_INSTALLED_EXE_SHA},
        "pythonManifest": layer, "viteManifest": manifest, "viteReport": vite,
        "priorExe": old_exe,
    }


def previous_python_layer(inputs: dict, target: Path) -> dict[str, str]:
    """Build from immutable prior QA Python layer, never current dirty .py files."""
    sources = inputs["pythonManifest"]["supplementalFiles"]
    core = inputs["pythonManifest"]["pinnedCorePython"]
    expected = {**sources, **core}
    root = PRIOR / "python-input"
    safe(root, file=False)
    target.mkdir(exist_ok=False)
    for name, digest in sorted(expected.items()):
        if Path(name).name != name or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise QaBlock("invalid Python source manifest entry")
        prior = safe(root / name)
        if file_sha(prior) != digest:
            raise QaBlock("prior independent Python layer mutated: " + name)
        if name == "madar_update.py":
            replacement = overlay_version(prior.read_bytes())
            with (target / name).open("xb") as writer:
                writer.write(replacement)
            if (file_sha(target / name) != data_sha(replacement)):
                raise QaBlock("staged v1.0.27 updater version not retained")
        else:
            copy_verified(prior, target / name, digest)
    stage_hashes = {x.name: file_sha(x) for x in target.glob("*.py")}
    if len(stage_hashes) != len(expected) or stage_hashes["native_app.py"] != core["native_app.py"]:
        raise QaBlock("private Python source graph incomplete")
    if stage_hashes["madar_update.py"] == core["madar_update.py"]:
        raise QaBlock("staged application still contains old updater")
    return stage_hashes


def staged_package(source: Path, target: Path, manifest: dict) -> dict:
    hashes = {}
    for name in ("package.json", "package-lock.json"):
        expected = manifest["sourceFiles"][name]
        path = safe(source / name)
        if file_sha(path) != expected:
            raise QaBlock("pinned v1.0.26 package source changed")
        result = set_pkg_version(path.read_bytes())
        destination = target / name
        with destination.open("xb") as stream:
            stream.write(result)
        hashes[name] = file_sha(destination)
    pkg = json_read(target / "package.json")
    lock = json_read(target / "package-lock.json")
    if (pkg["version"] != TARGET or lock["version"] != TARGET
            or lock["packages"][""]["version"] != TARGET):
        raise QaBlock("private v1.0.27 package/lock version mismatch")
    return hashes


def original_builder_scripts(build_root: Path) -> dict[str, str]:
    hashes = {}
    for name in REQUIRED:
        path = safe(SOURCE / name, max_size=1_000_000)
        expected = file_sha(path)
        if name.endswith("madar-update.iss"):
            content = path.read_text(encoding="utf-8")
            if not all(value in content for value in (
                    "#ifdef QA", "DefaultDirName={#QA_ROOT}",
                    "-IsolatedQA", "onlyifdoesntexist",
                    "EXE_SHA256", "RaiseException")):
                raise QaBlock("Inno script missing isolated QA/safe activation controls")
        if name.endswith("Madar-Upgrade-Preflight.ps1"):
            content = path.read_text(encoding="utf-8")
            if not all(v in content for v in (
                    "Snapshot checksum mismatch", "BackupRoot", "IsolatedQA")):
                raise QaBlock("preflight backup/QA isolation checks missing")
        if name.endswith("Madar-Activate-Version.ps1"):
            content = path.read_text(encoding="utf-8")
            if not all(v in content for v in (
                    "ExpectedSHA256", "VERSION_ALREADY_ACTIVE",
                    "Downgrade", "AssertNoReparsePoints")):
                raise QaBlock("activation monotonic/hash/rollback gate missing")
        copy_verified(path, build_root / name, expected)
        hashes[name] = expected
    return hashes


def build_environment(root: Path) -> dict[str, str]:
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
               "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS"}
    env = {key: value for key, value in os.environ.items()
           if key.upper() in allowed}
    for key in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME", "TEMP", "TMP",
                "PYTHONPYCACHEPREFIX", "PYINSTALLER_CONFIG_DIR"):
        folder = root / "isolated-env" / key.lower()
        folder.mkdir(exist_ok=False, parents=True)
        env[key] = str(folder)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["CI"] = "1"
    return env


def qa_inno_command(build_root: Path, payload_hash: str, qa_root: Path) -> list[str]:
    if (not re.fullmatch(r"[0-9a-f]{64}", payload_hash)
            or not re.fullmatch(r"\.qa-inno-v127-[a-zA-Z0-9-]+", qa_root.name)
            or not qa_root.is_relative_to(OUT)):
        raise QaBlock("unsafe QA root or payload hash")
    return [
        str(ISCC), "/Qp", "/DQA", "/DCOMPACT",
        "/DQA_ROOT=" + str(qa_root),
        "/DMadarVersion=" + TARGET,
        "/DExeFile=" + PAYLOAD_NAME,
        "/DRCOutputBase=" + Path(SETUP_NAME).stem,
        "/DEXE_SHA256=" + payload_hash,
        str(build_root / "scripts" / "madar-update.iss"),
    ]


def inspect_exe(exe: Path, inputs: dict, updater_hash: str,
                assets_override: dict | None = None) -> dict:
    safe(exe)
    with exe.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise QaBlock("staged EXE not Windows PE")
    archive = CArchiveReader(str(exe))
    names = {name.replace("\\", "/"): name for name in archive.toc}
    assets = assets_override or inputs["viteReport"]["compiled"]["assets"]
    for name, details in assets.items():
        key = "dist/" + name
        if key not in names or data_sha(archive.extract(names[key])) != details["sha256"]:
            raise QaBlock("rebuilt v1.0.27 missing exact pinned Vite asset: " + name)
    pyz = archive.open_embedded_archive("PYZ.pyz")
    if "madar_update" not in pyz.toc:
        raise QaBlock("staged updater absent from EXE")
    compiled = pyz.extract("madar_update")
    if (compiled is None or TARGET not in compiled.co_consts
            or INSTALLED in compiled.co_consts):
        raise QaBlock("embedded updater is not v1.0.27")
    # Internal full Python source cannot be inferred from co_consts alone;
    # retain hash of staged source and PyInstaller command as provenance.
    app_js = [data["sha256"] for name, data in assets.items()
              if name.startswith("assets/") and name.endswith(".js")
              and data["bytes"] > 100_000]
    if len(app_js) != 1:
        raise QaBlock("compiled main app JS is missing/ambiguous")
    return {
        "sha256": file_sha(exe), "bytes": exe.stat().st_size,
        "embeddedUpdaterVersion": TARGET,
        "stagedUpdaterSha256": updater_hash,
        "viteAssetsByteIdentical": len(assets),
        "sileoHelpCompiledJsSha256": app_js[0],
        "pyzModules": len(pyz.toc),
    }


def verify_inno_setup(path: Path) -> dict:
    safe(path)
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise QaBlock("generated setup is not Windows PE")
    # Read PE file metadata without executing installer.
    ps = ("$f=Get-Item -LiteralPath '" + str(path).replace("'", "''") +
          "'; $s=Get-AuthenticodeSignature -LiteralPath $f.FullName; "
          "Write-Output ('VERSION='+$f.VersionInfo.FileVersion); "
          "Write-Output ('SIGNATURE='+$s.Status)")
    cmd = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True, timeout=20)
    if cmd.returncode:
        raise QaBlock("Inno compiled setup metadata readback failed")
    version = re.search(r"(?m)^VERSION=(.+)$", cmd.stdout)
    if version is None or version.group(1).strip() not in ("1.0.27.0", "1.0.27"):
        raise QaBlock("Inno setup FileVersion is not exactly 1.0.27")
    signature = re.search(r"(?m)^SIGNATURE=(.+)$", cmd.stdout)
    return {
        "sha256": file_sha(path), "bytes": path.stat().st_size,
        "peVersion": version.group(1).strip(),
        "signatureStatus": signature.group(1).strip() if signature else "UNKNOWN",
        "signedAndApproved": False,
    }


def fallback_zip(root: Path, inputs: dict, reason: str) -> dict:
    """Offline, non-executable plan if staged v1.0.27 QA setup is not proven."""
    path = root / FALLBACK_NAME
    prior = inputs["priorExe"]
    proposal = {
        "schema": 1,
        "status": "NO_EXECUTABLE_SETUP_ZIP_PROPOSAL_QA_ONLY",
        "targetProposedVersion": TARGET,
        "actualPayloadRuntimeVersion": INSTALLED,
        "classification": "HASH_PINNED_NONINSTALLABLE_QA_PLAN",
        "requiredBeforeRealUpgrade": [
            "new internally consistent 1.0.27 executable",
            "QA installer build and isolated backup/rollback",
            "GUI and live LAN/finance acceptance, signing and owner review",
        ],
        "sha256": PRIOR_EXE_SHA,
        "blockedReason": reason[:900],
    }
    content = (json.dumps(proposal, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with ZipFile(path, "x", ZIP_DEFLATED, compresslevel=7) as archive:
        archive.writestr("QA-ONLY-NO-SETUP.json", content)
        archive.write(prior, PRIOR_NAME)
    with ZipFile(path, "r") as archive:
        if (set(archive.namelist()) != {"QA-ONLY-NO-SETUP.json", PRIOR_NAME}
                or data_sha(archive.read(PRIOR_NAME)) != PRIOR_EXE_SHA):
            raise QaBlock("fallback QA ZIP does not match pinned baseline")
    return {"name": path.name, "sha256": file_sha(path),
            "bytes": path.stat().st_size, "actualPayloadVersion": INSTALLED}


def package(*, run=subprocess.run) -> dict:
    inputs = pinned_inputs()
    if OUT.exists():
        raise QaBlock("create-only candidate destination already exists; refusing overwrite")
    if not OUT.parent.parent.is_dir():
        raise QaBlock("approved D: QA parent is missing")
    if not OUT.parent.exists():
        OUT.parent.mkdir(exist_ok=False)
    safe(OUT.parent, file=False)
    OUT.mkdir(exist_ok=False)
    receipt = {
        "schema": 1, "status": "BLOCKED",
        "classification": "QA_ONLY_NONRELEASE_UNAPPROVED_NO_INSTALL",
        "targetCandidateVersion": TARGET,
        "installedVersionBefore": inputs["installedBefore"],
        "pinnedOriginalQaExe": {
            "version": INSTALLED, "sha256": PRIOR_EXE_SHA},
        "provenance": {k: value for k, value in inputs.items()
                       if k in ("sourceManifestSha256", "viteSourceInventorySha256",
                                "viteDependencyInventorySha256", "viteJsSha256",
                                "priorExeSha256", "priorPyModulesSha256")},
        "installerExecuted": False,
        "installedApplicationModified": False, "userProfileTouched": False,
        "signed": False, "released": False, "published": False,
        "officialFinanceAcceptance": False,
    }
    try:
        stage = OUT / "stage"
        stage.mkdir(exist_ok=False)
        python = stage / "python-input"
        hashes = previous_python_layer(inputs, python)
        receipt["pythonInputsSha256"] = canonical_sha(hashes)
        receipt["runtimeUpdaterSha256"] = hashes["madar_update.py"]
        pkg = staged_package(
            VITE / "source-snapshot", stage, inputs["viteManifest"])
        receipt["stagedPackageSha256"] = pkg
        build = stage / "builder"
        build.mkdir(exist_ok=False)
        original_scripts = original_builder_scripts(build)
        receipt["originalInstallerScriptsSha256"] = original_scripts
        copy_verified(VITE / "source-snapshot" / "assets" / "madar.ico",
                      build / "assets" / "madar.ico",
                      inputs["viteManifest"]["sourceFiles"]["assets/madar.ico"])
        target_exe = build / "release" / PAYLOAD_NAME
        target_exe.parent.mkdir(exist_ok=False)
        isolated = build_environment(OUT)
        cmd = [sys.executable, "-B", "-m", "PyInstaller",
               "--onefile", "--windowed", "--noupx", "--log-level", "WARN",
               "--name", Path(PAYLOAD_NAME).stem,
               "--distpath", str(build / "release"),
               "--workpath", str(OUT / "pyi-work"),
               "--specpath", str(OUT / "pyi-spec"),
               "--paths", str(python),
               "--icon", str(build / "assets" / "madar.ico"),
               "--add-data", str(VITE / "vite-compiled") + ";dist",
               str(python / "native_app.py")]
        proc = run(cmd, cwd=python, env=isolated, capture_output=True,
                   text=True, encoding="utf-8", errors="replace",
                   timeout=240, check=False)
        receipt["pyInstallerExitCode"] = proc.returncode
        receipt["pyInstallerLogTail"] = (proc.stderr or proc.stdout)[-1800:]
        if proc.returncode:
            raise QaBlock("private v1.0.27 PyInstaller build failed")
        receipt["payload"] = inspect_exe(
            target_exe, inputs, hashes["madar_update.py"])
        if original_builder_scripts_check() != original_scripts:
            raise QaBlock("existing Inno or safety scripts changed during packaging")
        # Compile ONLY QA AppId/QA_ROOT and COMPACT: no global prerequisite.
        qa_root = OUT / ".qa-inno-v127-20261110"
        inno_cmd = qa_inno_command(build, receipt["payload"]["sha256"], qa_root)
        proc = run(inno_cmd, cwd=build / "scripts",
                   env=isolated, capture_output=True, text=True,
                   encoding="utf-8", errors="replace",
                   timeout=150, check=False)
        receipt["isccExitCode"] = proc.returncode
        receipt["isccLogTail"] = (proc.stderr or proc.stdout)[-2200:]
        if proc.returncode:
            raise QaBlock("QA-only Inno Setup compilation failed")
        # Inno script itself writes to builder/release. No production file.
        setup = build / "release" / SETUP_NAME
        if not setup.is_file():
            raise QaBlock("Inno produced no QA setup")
        receipt["setup"] = verify_inno_setup(setup)
        # Strictly no runnable artifact named like a production setup at root.
        receipt["qaInstallRootIfExplicitlyRun"] = str(qa_root / "Programs" / "MadarDesk")
        receipt["setupPath"] = str(setup)
        if (inputs["installedBefore"] !=
                _installed_readback()):
            raise QaBlock("installed v1.0.26 baseline changed during QA packaging")
        receipt["status"] = "QA_V127_INNO_OFFLINE_SETUP_CREATED_NOT_INSTALLED"
    except (QaBlock, OSError, ValueError, subprocess.TimeoutExpired,
            UnicodeError) as error:
        receipt["reason"] = str(error)[:900]
        receipt["fallbackZip"] = fallback_zip(OUT, inputs, str(error))
        receipt["status"] = "QA_HASH_PINNED_ZIP_PROPOSAL_NO_SETUP"
    write_json_x(OUT / "qa-update-package-manifest.json", receipt)
    return receipt


def _installed_readback() -> dict:
    root = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "MadarDesk"
    version = safe(root / "current-version.txt", max_size=64).read_text(
        encoding="utf-8-sig").strip()
    return {"version": version, "sha256": file_sha(safe(
        root / "versions" / INSTALLED / "Madar-Desk.exe"))}


def original_builder_scripts_check() -> dict[str, str]:
    """Read current scripts only for a safe nonmutating pre/post comparison."""
    return {name: file_sha(safe(SOURCE / name, max_size=1_000_000))
            for name in REQUIRED}


def harden_qa_inno_stage(original: Path) -> Path:
    """Create NEW QA-only Inno script that refuses /DIR escape BEFORE copying.

    Validate the exact normalized target and every existing parent junction
    at PrepareToInstall. The post-install activation independently rechecks.
    Never modify original builder script and never compile a production AppId.
    """
    original = safe(original, max_size=1_000_000)
    src = original.read_text(encoding="utf-8")
    signature = "function PrepareToInstall(var NeedsRestart: Boolean): String;"
    start = "  Result := '';\n  Params := "
    activation = "  if CurStep <> ssPostInstall then exit;"
    if (src.count(signature) != 1 or src.count(start) != 1
            or src.count(activation) != 1):
        raise QaBlock("Inno source insertion points changed; no QA setup")
    helper = r"""
#ifdef QA
function QaWindowsAttributes(FileName: String): Cardinal;
  external 'GetFileAttributesW@kernel32.dll stdcall';

function QaPathHasJunctionOrLink(Path: String): Boolean;
var
  A: Cardinal;
  Parent: String;
begin
  Result := True;
  while Path <> '' do begin
    A := QaWindowsAttributes(Path);
    if (A <> $FFFFFFFF) and ((A and $400) <> 0) then exit;
    Parent := ExtractFileDir(Path);
    if Parent = Path then break;
    Path := Parent;
  end;
  Result := False;
end;

function QaExactInstallDestination(): Boolean;
var
  Expected: String;
  Actual: String;
begin
  Expected := ExpandFileName('{#QA_ROOT}\Programs\MadarDesk');
  Actual := ExpandFileName(ExpandConstant('{app}'));
  Result := (CompareText(Expected, Actual) = 0) and
            (not QaPathHasJunctionOrLink(Actual));
end;
#endif
"""
    src = src.replace(signature, helper + "\n" + signature, 1)
    src = src.replace(start, (
        "  Result := '';\n"
        "#ifdef QA\n"
        "  if not QaExactInstallDestination() then begin\n"
        "    Result := 'QA ONLY: invalid installation destination or junction. No files copied.';\n"
        "    exit;\n"
        "  end;\n"
        "#endif\n"
        "  Params := "), 1)
    src = src.replace(activation, (
        activation + "\n"
        "#ifdef QA\n"
        "  if not QaExactInstallDestination() then\n"
        "    RaiseException('QA ONLY: destination was changed. Activation blocked.');\n"
        "#endif"), 1)
    if (src.count("QaExactInstallDestination()") != 3
            or "QA ONLY: invalid installation destination" not in src
            or "GetFileAttributesW@kernel32.dll" not in src):
        raise QaBlock("hardened Inno QA path guard absent")
    target = original.with_name("madar-update-QA-DIR-HARDENED.iss")
    with target.open("x", encoding="utf-8") as file:
        file.write(src)
    return target


def compile_v127_ui(run_root: Path, inputs: dict, env: dict,
                    *, runner=subprocess.run) -> dict:
    """Recompile actual React bundle from copied pinned source + v1.0.27 package.

    Do NOT binary-patch minified JS: App.jsx imports package.json to display
    its own version. The prior v1.0.26 JS cannot be relabeled safely.
    """
    base = VITE / "source-snapshot"
    target = run_root / "vite-source-v127"
    target.mkdir(exist_ok=False)
    records = {**inputs["viteManifest"]["sourceFiles"],
               **inputs["viteManifest"]["dependencyFiles"]}
    updated = {}
    for relative, expected in sorted(records.items()):
        original = safe(base / relative, max_size=50_000_000)
        if file_sha(original) != expected:
            raise QaBlock("pinned source/dependency changed before 1.0.27 UI build")
        dest = target / relative
        if relative in ("package.json", "package-lock.json"):
            dest.parent.mkdir(parents=True, exist_ok=True)
            value = set_pkg_version(original.read_bytes())
            with dest.open("xb") as f:
                f.write(value)
            updated[relative] = data_sha(value)
        else:
            copy_verified(original, dest, expected)
    expected_app = read_version = json_read(target / "package.json").get("version")
    expected_lock = json_read(target / "package-lock.json")
    if (expected_app != TARGET or expected_lock["version"] != TARGET
            or expected_lock["packages"][""]["version"] != TARGET):
        raise QaBlock("Vite source package/lock not uniformly 1.0.27")
    output = run_root / "vite-compiled-v127"
    node = shutil.which("node")
    if not node:
        raise QaBlock("offline Node.js unavailable")
    argv = [node, str(target / "node_modules" / "vite" / "bin" / "vite.js"),
            "build", "--mode", "production", "--outDir", str(output)]
    result = runner(argv, cwd=target, env=env, capture_output=True,
                    text=True, encoding="utf-8", errors="replace",
                    timeout=160, check=False)
    if result.returncode:
        raise QaBlock("staged v1.0.27 React/Vite compile failed: " +
                      (result.stderr or result.stdout)[-420:])
    # Pin full staged source after build. Only two controlled package files
    # may differ, no missing/extra sources, scripts or npm dependency drift.
    for relative, expected in records.items():
        current = file_sha(safe(target / relative, max_size=50_000_000))
        if current != updated.get(relative, expected):
            raise QaBlock("Vite changed staged source/dependency: " + relative)
    if (set(x.relative_to(target).as_posix() for x in target.rglob("*") if x.is_file())
            != set(records)):
        raise QaBlock("Vite source tree has unexpected added/deleted file")
    assets = {}
    for file in output.rglob("*"):
        if file.is_file():
            name = file.relative_to(output).as_posix()
            assets[name] = {"sha256": file_sha(file), "bytes": file.stat().st_size}
    js = [(name, data) for name, data in assets.items()
          if name.startswith("assets/") and name.endswith(".js")
          and data["bytes"] > 100_000]
    if len(js) != 1 or not (output / "index.html").is_file():
        raise QaBlock("new Vite entry not a complete app")
    name, js_meta = js[0]
    text = (output / name).read_text(encoding="utf-8")
    if (text.count("1.0.27") != 1 or "1.0.26" in text or
            not all(key in text for key in (
                "data-sileo-viewport", "data-sileo-toast",
                "mtr-context-help__trigger", "راهنمای مدار"))):
        raise QaBlock("compiled app version or Sileo/help markers mismatch")
    if (len(assets) < 10 or
            not any(name.endswith(".css") for name in assets)):
        raise QaBlock("incomplete staged Vite assets")
    return {
        "sourceManifestSha256": VITE_MANIFEST_SHA,
        "originalSourceFiles": len(records),
        "controlledVersionFiles": updated,
        "compiledAssetCount": len(assets),
        "compiledJs": name,
        "compiledJsSha256": js_meta["sha256"],
        "compiledVersion": TARGET,
        "assets": assets,
        "output": str(output),
    }


def package_version_consistent(*, runner=subprocess.run) -> dict:
    """Distinct immutable v2 candidate; never overwrite first QA candidate."""
    inputs = pinned_inputs()
    safe(OUT, file=False)
    revised = OUT / ("revised-source-v127-" + uuid4().hex[:12])
    revised.mkdir(exist_ok=False)
    receipt = {
        "schema": 2, "status": "BLOCKED",
        "classification": "QA_ONLY_VERSION_CONSISTENT_UPDATE_NOT_RELEASE_NOT_INSTALLED",
        "candidateVersion": TARGET,
        "installedBefore": inputs["installedBefore"],
        "pinnedOldExeSha256": PRIOR_EXE_SHA,
        "pinnedSourceManifestSha256": VITE_MANIFEST_SHA,
        "noInstall": True, "installerExecuted": False,
        "installedModifiedByThisOperation": False,
        "signed": False, "published": False, "released": False,
        "officialFinanceAcceptance": False,
        "replacesEarlierQaClaim": str(OUT / "qa-update-package-manifest.json"),
        "runRoot": str(revised),
    }
    try:
        stage = revised / "stage"
        stage.mkdir(exist_ok=False)
        python = stage / "python-input"
        python_hashes = previous_python_layer(inputs, python)
        receipt["pythonLayerSha256"] = canonical_sha(python_hashes)
        receipt["stagedUpdaterSha256"] = python_hashes["madar_update.py"]
        receipt["stagePackageSha256"] = staged_package(
            VITE / "source-snapshot", stage, inputs["viteManifest"])
        builder = stage / "builder"
        builder.mkdir(exist_ok=False)
        scripts = original_builder_scripts(builder)
        receipt["installerSourceSha256"] = scripts
        hardened = harden_qa_inno_stage(builder / "scripts" / "madar-update.iss")
        receipt["hardenedQaInnoSha256"] = file_sha(hardened)
        copy_verified(VITE / "source-snapshot" / "assets" / "madar.ico",
                      builder / "assets" / "madar.ico",
                      inputs["viteManifest"]["sourceFiles"]["assets/madar.ico"])
        env = build_environment(revised)
        vite = compile_v127_ui(revised, inputs, env, runner=runner)
        receipt["viteV127"] = {key: value for key, value in vite.items()
                               if key != "assets"}
        target_exe = builder / "release" / PAYLOAD_NAME
        target_exe.parent.mkdir(exist_ok=False)
        pyi = [
            sys.executable, "-B", "-m", "PyInstaller",
            "--onefile", "--windowed", "--noupx", "--log-level", "WARN",
            "--name", Path(PAYLOAD_NAME).stem,
            "--distpath", str(builder / "release"),
            "--workpath", str(revised / "pyi-work"),
            "--specpath", str(revised / "pyi-spec"),
            "--paths", str(python),
            "--icon", str(builder / "assets" / "madar.ico"),
            "--add-data", vite["output"] + ";dist",
            str(python / "native_app.py"),
        ]
        proc = runner(pyi, cwd=python, env=env, capture_output=True,
                      text=True, encoding="utf-8", errors="replace",
                      timeout=240, check=False)
        receipt["pyInstallerExitCode"] = proc.returncode
        receipt["pyInstallerLogTail"] = (proc.stderr or proc.stdout)[-1100:]
        if proc.returncode:
            raise QaBlock("version-consistent PyInstaller build failed")
        receipt["payload"] = inspect_exe(
            target_exe, inputs, python_hashes["madar_update.py"],
            assets_override=vite["assets"])
        if receipt["payload"]["sileoHelpCompiledJsSha256"] != vite["compiledJsSha256"]:
            raise QaBlock("embedded v1.0.27 React app does not match Vite")
        if (original_builder_scripts_check() != scripts
                or inputs["installedBefore"] != _installed_readback()):
            raise QaBlock("original scripts or installed baseline changed")
        qa_root = revised / ".qa-inno-v127-20261110"
        inno = qa_inno_command(builder, receipt["payload"]["sha256"], qa_root)
        inno[-1] = str(hardened)
        proc = runner(inno, cwd=builder / "scripts", env=env,
                      capture_output=True, text=True, encoding="utf-8",
                      errors="replace", timeout=150, check=False)
        receipt["isccExitCode"] = proc.returncode
        receipt["isccLogTail"] = (proc.stderr or proc.stdout)[-1200:]
        if proc.returncode:
            raise QaBlock("version-consistent Inno QA build failed")
        setup = builder / "release" / SETUP_NAME
        receipt["setup"] = verify_inno_setup(setup)
        receipt["setupPath"] = str(setup)
        receipt["qaOnlyInstallRoot"] = str(qa_root / "Programs" / "MadarDesk")
        if inputs["installedBefore"] != _installed_readback():
            raise QaBlock("installed version/exe hash changed during packaging")
        receipt["status"] = "QA_V127_VERSION_CONSISTENT_SETUP_CREATED_NO_INSTALL"
        # Add a new marker; never overwrite the earlier candidate/manifest.
        with (OUT / "EARLIER_QA_CANDIDATE_SUPERSEDED.txt").open(
                "x", encoding="utf-8") as note:
            note.write("EARLIER ROOT-LEVEL QA HAS V1.0.26 UI EMBEDDED. "
                       "DO NOT INSTALL. New verified run: " + str(revised) + "\n")
    except (QaBlock, OSError, ValueError, UnicodeError,
            subprocess.TimeoutExpired) as error:
        receipt["reason"] = str(error)[:900]
        receipt["fallbackZip"] = fallback_zip(revised, inputs, str(error))
        receipt["status"] = "QA_HASH_PINNED_ZIP_PROPOSAL_NO_SETUP"
    write_json_x(revised / "qa-update-package-manifest.json", receipt)
    return receipt


VERIFIED_V127_RUN = OUT / "revised-source-v127-e56b2f18d2d4"
VERIFIED_V127_MANIFEST_SHA = "65d0ce637b8eef1ad245a74b77fb350447ee913d8dbddc3cd6b3a5b05f397c78"
VERIFIED_V127_EXE_SHA = "28db6ea51eccbb17d99cccf9111cd934c5e0353fde615e34367825ded228e919"
VERIFIED_V127_JS_SHA = "6cbc7d73c7a09fc7992a89372100d92bcf80e61fe336ca72c2d5bde06ba0eb08"
HARDENED_SETUP_NAME = "Madar-Desk-1.0.27-Setup-QA-DIR-GUARDED-NONRELEASE.exe"


def package_hardened_qa_inno(*, runner=subprocess.run) -> dict:
    """Freeze already recompiled v1.0.27 GUI/updater into safer isolated setup.

    Creates a *third* unique candidate rather than replacing old artifacts.
    Runtime executable is copied only from SHA-pinned earlier v1.0.27 build.
    The new Inno script blocks /DIR override and junctions before file writes.
    """
    inputs = pinned_inputs()
    safe(OUT, file=False)
    if file_sha(safe(VERIFIED_V127_RUN / "qa-update-package-manifest.json")) != VERIFIED_V127_MANIFEST_SHA:
        raise QaBlock("previous rebuilt 1.0.27 QA manifest bytes changed")
    old = json_read(VERIFIED_V127_RUN / "qa-update-package-manifest.json")
    if (old.get("status") != "QA_V127_VERSION_CONSISTENT_SETUP_CREATED_NO_INSTALL"
            or old.get("viteV127", {}).get("compiledVersion") != TARGET
            or old.get("viteV127", {}).get("compiledJsSha256") != VERIFIED_V127_JS_SHA
            or old.get("payload", {}).get("sha256") != VERIFIED_V127_EXE_SHA
            or old.get("payload", {}).get("embeddedUpdaterVersion") != TARGET
            or old.get("payload", {}).get("sileoHelpCompiledJsSha256") != VERIFIED_V127_JS_SHA):
        raise QaBlock("previous v1.0.27 Vite/PyInstaller source attestation fails")
    compiled = VERIFIED_V127_RUN / "vite-compiled-v127"
    assets = {}
    for path in compiled.rglob("*"):
        if path.is_file():
            relative = path.relative_to(compiled).as_posix()
            assets[relative] = {"sha256": file_sha(safe(path)),
                                "bytes": path.stat().st_size}
    if (len(assets) != old["viteV127"]["compiledAssetCount"]
            or assets[old["viteV127"]["compiledJs"]]["sha256"] != VERIFIED_V127_JS_SHA):
        raise QaBlock("rebuilt 1.0.27 frontend assets changed")
    js = (compiled / old["viteV127"]["compiledJs"]).read_text(encoding="utf-8")
    if (js.count("1.0.27") != 1 or "1.0.26" in js or
            "data-sileo-viewport" not in js or
            "mtr-context-help__trigger" not in js):
        raise QaBlock("recompiled 1.0.27 React app is not version-consistent")
    payload = VERIFIED_V127_RUN / "stage" / "builder" / "release" / PAYLOAD_NAME
    if file_sha(safe(payload)) != VERIFIED_V127_EXE_SHA:
        raise QaBlock("prior v1.0.27 program changed")
    previous = inspect_exe(payload, inputs, old["payload"]["stagedUpdaterSha256"],
                           assets_override=assets)
    if previous["sileoHelpCompiledJsSha256"] != VERIFIED_V127_JS_SHA:
        raise QaBlock("prior EXE embeds wrong React asset version")
    new = OUT / ("hardened-qa-v127-" + uuid4().hex[:12])
    new.mkdir(exist_ok=False)
    result = {
        "schema": 3,
        "status": "BLOCKED",
        "classification": "QA_ONLY_DIR_GUARDED_INNO_UNAPPROVED_NO_INSTALL",
        "version": TARGET,
        "installedVersionBefore": inputs["installedBefore"],
        "sourceViteManifestSha256": VITE_MANIFEST_SHA,
        "recompiledViteJsSha256": VERIFIED_V127_JS_SHA,
        "previousRebuiltManifestSha256": VERIFIED_V127_MANIFEST_SHA,
        "payloadSha256": VERIFIED_V127_EXE_SHA,
        "qaOnly": True, "installerExecuted": False, "installedModified": False,
        "userProfileTouched": False, "signed": False, "released": False,
        "officialFinanceAcceptance": False,
        "supersedes": [
            str(OUT / "stage" / "builder" / "release" / SETUP_NAME),
            str(VERIFIED_V127_RUN / "stage" / "builder" / "release" / SETUP_NAME),
        ],
        "runRoot": str(new),
    }
    try:
        builder = new / "builder"
        builder.mkdir(exist_ok=False)
        scripts = original_builder_scripts(builder)
        if scripts != old["installerSourceSha256"]:
            raise QaBlock("original installer source differs from verified QA source")
        guarded = harden_qa_inno_stage(builder / "scripts" / "madar-update.iss")
        result["hardenedInnoSha256"] = file_sha(guarded)
        result["hardenedPathCheck"] = (
            "EXACT_ABSOLUTE_QA_DIR_PLUS_PARENT_REPARSE_CHECK_PRE_COPY")
        copy_verified(VITE / "source-snapshot" / "assets" / "madar.ico",
                      builder / "assets" / "madar.ico",
                      inputs["viteManifest"]["sourceFiles"]["assets/madar.ico"])
        copy_verified(payload, builder / "release" / PAYLOAD_NAME,
                      VERIFIED_V127_EXE_SHA)
        env = build_environment(new)
        qa_root = new / ".qa-inno-v127-20261110"
        command = qa_inno_command(builder, VERIFIED_V127_EXE_SHA, qa_root)
        command[-1] = str(guarded)
        command = [("/DRCOutputBase=" + Path(HARDENED_SETUP_NAME).stem)
                   if value.startswith("/DRCOutputBase=") else value
                   for value in command]
        proc = runner(command, cwd=builder / "scripts", env=env,
                      capture_output=True, text=True, encoding="utf-8",
                      errors="replace", timeout=150, check=False)
        result["isccExitCode"] = proc.returncode
        result["isccLogTail"] = (proc.stderr or proc.stdout)[-2400:]
        if proc.returncode:
            raise QaBlock("hardened QA Inno setup failed to compile")
        setup = builder / "release" / HARDENED_SETUP_NAME
        result["setup"] = verify_inno_setup(setup)
        result["setupPath"] = str(setup)
        result["qaOnlyDefaultInstallRoot"] = str(qa_root / "Programs" / "MadarDesk")
        if inputs["installedBefore"] != _installed_readback():
            raise QaBlock("installed baseline changed during hardened packaging")
        result["status"] = "QA_V127_INNO_DIR_HARDENED_SETUP_BUILT_NOT_INSTALLED"
        with (OUT / "UNSAFE_EARLIER_QA_SETUPS_DO_NOT_RUN.txt").open(
                "x", encoding="utf-8") as stream:
            stream.write(
                "Earlier Inno QA builds do not reject /DIR override before copying.\n"
                "DO NOT RUN those first two setup.exe files.\n"
                "The new QA-only hardened build is " + str(new) + "\n"
                "Still unsigned and NOT an authorized release or live update.\n"
            )
    except (QaBlock, OSError, ValueError, UnicodeError,
            subprocess.TimeoutExpired) as error:
        result["reason"] = str(error)[:900]
        result["fallbackZip"] = fallback_zip(new, inputs, str(error))
        result["status"] = "QA_HASH_PINNED_ZIP_PROPOSAL_NO_SETUP"
    write_json_x(new / "qa-update-package-manifest.json", result)
    return result


def main() -> int:
    if "--harden-existing-v127" in sys.argv[1:]:
        if sys.argv[1:] != ["--harden-existing-v127"]:
            print("HARDENED_QA_ACCEPTS_EXACT_FLAG_ONLY", flush=True)
            return 2
        try:
            result = package_hardened_qa_inno()
        except (QaBlock, OSError, ValueError, UnicodeError) as error:
            print("HARDENED_QA_PREFLIGHT_BLOCKED " + str(error), flush=True)
            return 2
        print("HARDENED_V127_QA " + result["status"] + " " + result["runRoot"],
              flush=True)
        if result["status"] != "QA_V127_INNO_DIR_HARDENED_SETUP_BUILT_NOT_INSTALLED":
            print("BLOCKER " + result.get("reason", "unknown"), flush=True)
            return 2
        print("HARDENED_QA_SETUP_SHA256 " + result["setup"]["sha256"],
              flush=True)
        return 0
    if "--rebuild-with-vite" in sys.argv[1:]:
        if sys.argv[1:] != ["--rebuild-with-vite"]:
            print("REBUILD_ONLY_ACCEPTS_EXACT_FLAG", flush=True)
            return 2
        try:
            result = package_version_consistent()
        except (QaBlock, OSError, ValueError, KeyError) as error:
            print("REVISED_V127_PREFLIGHT_BLOCKED " + str(error), flush=True)
            return 2
        print("REVISED_V127_QA " + result["status"] + " " + result["runRoot"],
              flush=True)
        if result["status"] != "QA_V127_VERSION_CONSISTENT_SETUP_CREATED_NO_INSTALL":
            print("REASON " + result.get("reason", "unknown"), flush=True)
            return 2
        print("REVISED_QA_SETUP_SHA256 " + result["setup"]["sha256"], flush=True)
        return 0
    try:
        result = package()
    except (QaBlock, OSError, ValueError, KeyError, UnicodeError) as error:
        print("MADAR_V127_QA_PACKAGE_PREFLIGHT_BLOCKED " + str(error),
              flush=True)
        return 2
    print("MADAR_V127_QA_PACKAGE " + result["status"] + " " +
          str(OUT / "qa-update-package-manifest.json"), flush=True)
    if "setup" in result:
        print("QA_SETUP_SHA256 " + result["setup"]["sha256"], flush=True)
        return 0
    print("FALLBACK_ZIP_SHA256 " + result["fallbackZip"]["sha256"], flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
