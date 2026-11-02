"""Opt-in real Inno installer QA on isolated synthetic Windows profile only.

This runs the QA *installer* executable, not a mock CLI. It never installs
production app IDs, touches actual APPDATA or executes a user's installed app.
The QA root is compiled into the installer at release-build time.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
VER = "1.0.3"
LABEL = "20261102"
RELEASE = ROOT / "release"
QA = RELEASE / f"Madar-Setup-v{VER}-RC-{LABEL}-QA.exe"
PROGRAM = RELEASE / f"Madar-Desk-v{VER}-RC-{LABEL}.exe"
QA_ROOT = ROOT / ".qa-inno-v103-20261102"


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return sha256(handle.read()).hexdigest()


def require(condition, description):
    if not condition:
        raise RuntimeError("RC QA FAILED: " + description)


def main():
    require(QA.is_file() and PROGRAM.is_file(), "QA installer or RC program missing")
    require(not (QA_ROOT / "Roaming" / "MadarDesk").exists(),
            "Previously used QA data root; refusing to overwrite any files")
    require(not (QA_ROOT / "Programs" / "MadarDesk").exists(),
            "Previously used QA install root; refusing to overwrite any files")
    data = QA_ROOT / "Roaming" / "MadarDesk"
    install = QA_ROOT / "Programs" / "MadarDesk"
    snapshots = QA_ROOT / "Snapshots"
    (data / "attachments").mkdir(parents=True)
    (data / "tasks.json").write_text('{"tasks":[{"id":"keep-me","title":"کار آزمایشی"}]}',
                                    encoding="utf8")
    (data / "users.json").write_text('{"testUser":"synthetic-no-secrets"}', encoding="utf8")
    (data / "attachments" / "invoice.pdf").write_bytes(b"synthetic-PDF-bytes-for-QA-only\x00")
    before = {p.relative_to(data).as_posix(): p.read_bytes()
              for p in data.rglob("*") if p.is_file()}
    old_exe = install / "versions" / "1.0.2" / "Madar-Desk.exe"
    old_exe.parent.mkdir(parents=True)
    old_exe.write_bytes(b"MZ synthetic-old-binary-1.0.2")
    (install / "current-version.txt").write_text("1.0.2\n", encoding="ascii")
    log = QA_ROOT / "synthetic-installer.log"
    command = [str(QA), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
               "/LOG=" + str(log)]
    print("RUN_ISOLATED_QA_INSTALLER", flush=True)
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=240)
    if result.returncode:
        tail = log.read_text(encoding="utf8", errors="replace")[-5000:] if log.exists() else ""
        raise RuntimeError(f"QA installer exited {result.returncode}\n{result.stderr}\n{tail}")
    new_exe = install / "versions" / VER / "Madar-Desk.exe"
    require(new_exe.is_file() and sha(new_exe) == sha(PROGRAM), "installed RC binary hash mismatch")
    require(old_exe.read_bytes() == b"MZ synthetic-old-binary-1.0.2", "old executable overwritten")
    require((install / "current-version.txt").read_text().strip() == VER, "new version pointer missing")
    require((install / "previous-version.txt").read_text().strip() == "1.0.2", "rollback pointer missing")
    after = {p.relative_to(data).as_posix(): p.read_bytes()
             for p in data.rglob("*") if p.is_file()}
    require(before == after, "existing user data altered during upgrade")
    archives = list(snapshots.glob(f"Madar-Before-{VER}-*.zip"))
    require(len(archives) == 1, "expected exactly one complete pre-upgrade ZIP")
    with ZipFile(archives[0]) as zipped:
        require(zipped.testzip() is None, "corrupted pre-upgrade snapshot")
        require({name: zipped.read(name) for name in before} == before,
                "snapshot contents differ from original profile bytes")
    activate = ROOT / "scripts" / "Madar-Activate-Version.ps1"
    def switch(target, expected_hash, *, allow_rollback=False):
        args = ["powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", str(activate),
                "-InstallRoot", str(install), "-Version", target,
                "-ExpectedSHA256", expected_hash]
        if allow_rollback:
            args.append("-AllowRollback")
        return subprocess.run(args, cwd=ROOT, capture_output=True,
                              text=True, timeout=30)

    # A normal updater must refuse implicit downgrade. The test's intentional
    # rollback is an explicitly authorized, hash-verified recovery operation.
    denied = switch("1.0.2", sha(old_exe))
    require(denied.returncode != 0 and "requires explicit rollback" in denied.stderr,
            "silent downgrade was not rejected")
    require((install / "current-version.txt").read_text().strip() == VER,
            "denied downgrade modified the active version pointer")
    for target, expected_hash, rollback in (("1.0.2", sha(old_exe), True),
                                            (VER, sha(new_exe), False)):
        run = switch(target, expected_hash, allow_rollback=rollback)
        require(run.returncode == 0, "pointer rollback/forward failed: " + run.stderr)
        require((install / "current-version.txt").read_text().strip() == target,
                "pointer does not match selected safe version")
    require({p.relative_to(data).as_posix(): p.read_bytes()
             for p in data.rglob("*") if p.is_file()} == before,
            "rollback changed existing user data")
    summary = {"installer": QA.name, "version": VER,
               "program_sha256": sha(PROGRAM), "installer_sha256": sha(QA),
               "original_files_preserved": len(before),
               "pre_upgrade_snapshot_verified": True,
               "old_binary_retained": True, "rollback_and_reactivate": True,
               "qa_root": str(QA_ROOT), "installed_into_real_profile": False}
    (QA_ROOT / "p0-qa-evidence.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print("RC_ISOLATED_INSTALL_UPGRADE_ROLLBACK_PASS", flush=True)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
