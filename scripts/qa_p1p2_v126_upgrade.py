"""Synthetic 1.0.23 -> 1.0.26 isolated installer, rollback and EXE QA.

Never runs the production installer or accesses the real APPDATA/install.
The candidate must have been built in the dedicated v126 P1P2 worktree.
"""
from __future__ import annotations

import ctypes
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent / "madar-ux-execution-20261104"
RC = ROOT
RELEASE = RC / "release"
QA = RC / ".qa-inno-v126-p1p2-20261107"
ACCEPTANCE = RELEASE / "Madar-Desk-1.0.26-P1P2-QA.acceptance.json"
OLD = BASE / "release" / "Madar-Desk-v1.0.23-Cumulative-20261107-SettingsTaraz.exe"
MANIFEST = RELEASE / "Madar-Desk-1.0.26-P1P2-Candidate.json"


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(folder: Path) -> dict[str, str]:
    return {path.relative_to(folder).as_posix(): digest(path)
            for path in folder.rglob("*") if path.is_file()}


def no_links(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise PermissionError("QA path may not contain any junction or symlink: " + str(part))


def run_activation(target: Path, version: str, checksum: str, rollback=False):
    command = ["powershell.exe", "-NoProfile", "-NonInteractive",
               "-ExecutionPolicy", "Bypass", "-File",
               str(RC / "scripts" / "Madar-Activate-Version.ps1"),
               "-InstallRoot", str(target), "-Version", version,
               "-ExpectedSHA256", checksum]
    if rollback:
        command.append("-AllowRollback")
    return subprocess.run(command, capture_output=True, timeout=30, text=True)


def pointer(folder: Path, name="current-version.txt") -> str:
    return (folder / name).read_text(encoding="utf-8-sig").strip()


def close_owned_window(pid: int):
    """Send WM_CLOSE only to the child executable owned by this QA harness."""
    user32 = ctypes.windll.user32
    enum = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    allowed = {pid}
    try:
        import psutil
        allowed.update(child.pid for child in psutil.Process(pid).children(recursive=True))
    except (ImportError, OSError):
        pass
    def callback(hwnd, extra):
        observed = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(observed))
        if observed.value in allowed:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
        return True
    user32.EnumWindows(enum(callback), 0)


def validate_release(*, resume: bool = False):
    if ACCEPTANCE.exists():
        raise FileExistsError("Immutable QA acceptance already exists")
    no_links(QA)
    if not QA.is_dir():
        raise FileNotFoundError("P1P2 QA root must be present and owned by the candidate")
    if resume:
        marker = QA / ".p1p2-owned-profile.json"
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf8")) != {
                "owner": "madar-v126-synthetic-qa", "upgradingFrom": "1.0.23"}:
            raise PermissionError("Cannot resume a QA root without its exact ownership marker")
    elif any(QA.iterdir()):
        raise FileExistsError("P1P2 QA root must be the fresh, empty builder-created directory")
    receipt = json.loads(MANIFEST.read_text(encoding="utf8"))
    if receipt.get("version") != "1.0.26" or receipt.get("classification") != (
            "unsigned-local-QA-candidate-not-published"):
        raise RuntimeError("Candidate receipt missing or has wrong identity")
    if subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=RC).strip():
        raise RuntimeError("Candidate release source changed after packaging")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=RC,
                                     encoding="ascii").strip()
    if actual != receipt["sourceGitCommit"]:
        raise RuntimeError("Candidate release is not tied to current committed source")
    for entry in receipt["outputs"].values():
        item = RELEASE / entry["name"]
        if not item.is_file() or item.stat().st_size != entry["bytes"] or (
                digest(item) != entry["sha256"]) or item.open("rb").read(2) != b"MZ":
            raise RuntimeError("Candidate binary failed digest/PE verification: " + str(item))
    if not OLD.is_file() or OLD.open("rb").read(2) != b"MZ":
        raise RuntimeError("Old 1.0.23 program is missing or invalid")
    return receipt


def main():
    if sys.argv[1:] not in ([], ["--resume"]):
        raise ValueError("Only the exact --resume flag is supported")
    resume = sys.argv[1:] == ["--resume"]
    receipt = validate_release(resume=resume)
    no_links(QA)
    marker = QA / ".p1p2-owned-profile.json"
    if not resume:
        marker.write_text(json.dumps({"owner": "madar-v126-synthetic-qa",
                                      "upgradingFrom": "1.0.23"}), encoding="utf8")
    install = QA / "Programs" / "MadarDesk"
    previous_exe = install / "versions" / "1.0.23" / "Madar-Desk.exe"
    if not resume:
        previous_exe.parent.mkdir(parents=True)
    # Copy only the previously released app into the fresh QA root.
    import shutil
    if not resume:
        shutil.copyfile(OLD, previous_exe)
    old_hash = digest(previous_exe)
    if old_hash != digest(OLD):
        raise RuntimeError("Synthetic old EXE copy changed")
    if not resume:
        (install / "current-version.txt").write_text("1.0.23\n", encoding="ascii")
        (install / "previous-version.txt").write_text("1.0.22\n", encoding="ascii")

    profile = QA / "Roaming" / "MadarDesk"
    if not resume:
        profile.mkdir(parents=True)
    # Explicitly synthetic, valid task structure. Never import a personal backup.
    if not resume:
        sys.path.insert(0, str(RC))
        import native_app
        state = native_app.normalize_state(native_app.initial_state())
        (profile / "tasks.json").write_text(json.dumps(state, ensure_ascii=False),
                                             encoding="utf8")
        (profile / "QA-preserve-attachment.bin").write_bytes(
            b"P1P2-v126-synthetic-user-attachment\x00keep-byte-for-byte")
        (profile / "synthetic.csv").write_text("id,amount\nqa,123\n", encoding="ascii")
    before = snapshot(profile)
    if not before:
        raise RuntimeError("Synthetic profile is missing or empty")

    qa_setup = RELEASE / receipt["outputs"]["qaInstaller"]["name"]
    log = QA / "qa-install.log"
    command = [str(qa_setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
               "/SP-", "/DIR=" + str(install), "/LOG=" + str(log)]
    if not resume:
        installed = subprocess.run(command, capture_output=True, text=True, timeout=240)
        if installed.returncode:
            raise RuntimeError("QA Inno failed with code " + str(installed.returncode)
                               + ": " + (installed.stderr + installed.stdout)[-1400:])
    elif not log.is_file():
        raise RuntimeError("Cannot resume an installation without its original Inno log")
    active = install / "versions" / "1.0.26" / "Madar-Desk.exe"
    new_hash = receipt["outputs"]["app"]["sha256"]
    if not active.is_file() or digest(active) != new_hash:
        raise RuntimeError("QA installer did not install the expected 1.0.26 EXE")
    if pointer(install) != "1.0.26" or pointer(install, "previous-version.txt") != "1.0.23":
        raise RuntimeError("QA activation pointers are incorrect")
    if digest(previous_exe) != old_hash or snapshot(profile) != before:
        raise RuntimeError("QA upgrade changed old EXE or synthetic profile")
    archives = list((QA / "Snapshots").glob("Madar-Before-1.0.26-*.zip"))
    if len(archives) != 1:
        raise RuntimeError("Expected exactly one synthetic pre-upgrade backup")
    with ZipFile(archives[0]) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Synthetic backup integrity check failed")
        archived = {name: sha256(archive.read(name)).hexdigest()
                    for name in archive.namelist() if not name.endswith("/")}
    if archived != before:
        raise RuntimeError("Backup contents differ from the original synthetic profile")

    blocked = run_activation(install, "1.0.23", old_hash)
    if blocked.returncode == 0 or pointer(install) != "1.0.26":
        raise RuntimeError("Downgrade without explicit rollback was not blocked")
    if "requires explicit rollback" not in (blocked.stderr + blocked.stdout):
        raise RuntimeError("Downgrade failure was not the intended rollback security gate")
    wrong_digest = run_activation(install, "1.0.23", "0"*64, rollback=True)
    if wrong_digest.returncode == 0 or pointer(install) != "1.0.26":
        raise RuntimeError("Rollback accepted an invalid previous EXE digest")
    if "integrity verification failed" not in (wrong_digest.stderr + wrong_digest.stdout):
        raise RuntimeError("Rollback hash rejection was not verified")
    rolled = run_activation(install, "1.0.23", old_hash, rollback=True)
    if rolled.returncode or pointer(install) != "1.0.23":
        raise RuntimeError("Explicit rollback to retained 1.0.23 failed")
    forward = run_activation(install, "1.0.26", new_hash)
    if forward.returncode or pointer(install) != "1.0.26":
        raise RuntimeError("Reactivation of the candidate after rollback failed")

    # Launch the ACTUAL compiled EXE in this same synthetic profile.
    env = os.environ.copy()
    env["APPDATA"] = str(QA / "Roaming")
    env["LOCALAPPDATA"] = str(QA / "Local")
    env["WEBVIEW2_USER_DATA_FOLDER"] = str(QA / "WebView2")
    env["MADAR_QA_VIEW"] = "read-only-runtime-health"
    env["MADAR_QA_REPORT"] = str(QA / "packaged-ui.json")
    report_path = Path(env["MADAR_QA_REPORT"])
    for dirname in ("Local", "WebView2"):
        (QA / dirname).mkdir(exist_ok=True)
    process = subprocess.Popen([str(active)], cwd=install, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(210):
            if report_path.exists():
                break
            if process.poll() is not None:
                raise RuntimeError("Packaged EXE exited before creating GUI report")
            time.sleep(0.2)
        if not report_path.exists():
            raise RuntimeError("Packaged WebView2 UI report was not created")
        runtime = json.loads(report_path.read_text(encoding="utf8"))
        if not runtime.get("main") or runtime.get("bridge") != "object" or (
                runtime.get("rootLength", 0) < 1000):
            raise RuntimeError("Packaged EXE did not mount the real task UI")
    finally:
        if process.poll() is None:
            close_owned_window(process.pid)
            try:
                process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                # PyInstaller onefile may launch its own child that owns the
                # WebView2 window. Terminate only this QA subtree.
                try:
                    import psutil
                    for child in psutil.Process(process.pid).children(recursive=True):
                        child.terminate()
                except (ImportError, OSError):
                    pass
                process.terminate()
                process.wait(timeout=8)

    evidence = {
        "schema": 1, "version": "1.0.26", "sourceGitCommit": receipt["sourceGitCommit"],
        "result": "synthetic-qa-upgrade-rollback-and-packaged-ui-passed",
        "from": "1.0.23", "to": "1.0.26", "sourceExeSha256": old_hash,
        "qaExeSha256": new_hash, "qaInstallerSha256":
            receipt["outputs"]["qaInstaller"]["sha256"],
        "profileFilesPreserved": len(before), "zipFilesVerified": len(archived),
        "oldExePreserved": True, "automaticDowngradeBlocked": True,
        "wrongDigestRejected": True, "explicitRollbackAndForwardPassed": True,
        "packagedWebView2TaskUI": True, "installerLogSha256": digest(log),
        "qaRoot": str(QA), "syntheticOnly": True,
    }
    with ACCEPTANCE.open("x", encoding="utf8") as output:
        json.dump(evidence, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print("P1P2_V126_SYNTHETIC_UPGRADE_ROLLBACK_GUI_PASSED " + str(ACCEPTANCE))


if __name__ == "__main__":
    main()
