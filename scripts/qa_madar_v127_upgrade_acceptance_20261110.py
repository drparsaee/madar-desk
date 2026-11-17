"""Run the real v1.0.27 QA-only Inno setup on a sterile isolated Windows tree.

No access to live Madar user data, databases, LAN, services or installed
program for writing. Never invokes any production installer. Does not run the
packaged application, nor assert application/financial acceptance.

Only the already-built /DQA /DCOMPACT /DIR-guarded candidate is allowed.
Tests a wrong /DIR first, then synthetic v1.0.26->1.0.27 side-by-side update,
verifies Inno's full SHA-backed profile backup, rolls the pointer back to the
previous SHA-pinned QA executable, and checks every synthetic byte unchanged.

Usage: python -B scripts/qa_madar_v127_upgrade_acceptance_20261110.py
Exit 0 = sterile QA upgrade and rollback pass (production install still NO_GO).
Exit 2 = blocked / failed; no production installation attempted.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
from uuid import uuid4
from zipfile import ZipFile


ROOT = Path(r"D:\CoS-Test\MTR-NEXT-UPDATE-CANDIDATES-20261110\madar-v1.0.27")
QA_RUN = ROOT / "hardened-qa-v127-5ddf1f3e715f"
QA_DATA = QA_RUN / ".qa-inno-v127-20261110"
QA_PROGRAM = QA_DATA / "Programs" / "MadarDesk"
QA_ROAMING = QA_DATA / "Roaming" / "MadarDesk"
QA_SNAPSHOTS = QA_DATA / "Snapshots"
QA_SETUP = (QA_RUN / "builder" / "release" /
            "Madar-Desk-1.0.27-Setup-QA-DIR-GUARDED-NONRELEASE.exe")
QA_ISS = QA_RUN / "builder" / "scripts" / "madar-update-QA-DIR-HARDENED.iss"
QA_ACTIVATE = QA_RUN / "builder" / "scripts" / "Madar-Activate-Version.ps1"
QA_MANIFEST = QA_RUN / "qa-update-package-manifest.json"
OLD_PE = (Path(r"D:\CoS-Test\MTR-MADAR-SILEO-QA-20261110") /
          "exe-only-20261110-164543-5e6ab975712e" / "exe-dist" /
          "Madar-Sileo-Help-v1.0.26-QA-ONLY-NONRELEASE.exe")
TARGET_VERSION = "1.0.27"
BASE_VERSION = "1.0.26"
QA_SETUP_SHA = "97c0b2ba33e8b13ab8b2533a6ebfd940f970ffb9750354f38845186829e5d9fd"
QA_APP_SHA = "28db6ea51eccbb17d99cccf9111cd934c5e0353fde615e34367825ded228e919"
QA_ISS_SHA = "d7fbd3ac90b2ba4b15f9d240d639c8a84d55effd9efe6f40f354123d2c121872"
OLD_PE_SHA = "f2d161bfc41576beb0dbd28cd8bb6154a32ffeb8cd69e15e0eca75bb24973468"
REAL_V126_SHA = "9bb1471944fc4b31aece7470e9d433fb68e207653d865ca3881c8d5654c943a4"
QA_ACTIVATE_SHA = "e0af9dc5d61801d61890446b8d70e365bbe2ab721ad7dfdc3597e681777dbcca"
MAX_EVIDENCE = 400 * 1024 * 1024
MAX_PROFILE_FILES = 25


class AcceptanceBlocked(RuntimeError):
    """No success claim permitted; installed app never modified by this script."""


def sha_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def safe_path(path: Path, *, file: bool = True, must_exist: bool = True) -> Path:
    path = Path(path)
    if not path.is_absolute():
        raise AcceptanceBlocked("only absolute QA evidence paths allowed")
    if must_exist and not path.exists():
        raise AcceptanceBlocked("required QA evidence path missing: " + str(path))
    for ancestor in (path, *path.parents):
        if not ancestor.exists():
            continue
        info = ancestor.lstat()
        if (ancestor.is_symlink() or getattr(ancestor, "is_junction", lambda: False)()
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise AcceptanceBlocked("linked/reparse path forbidden: " + str(ancestor))
    if must_exist and file:
        if not path.is_file() or path.stat().st_nlink != 1:
            raise AcceptanceBlocked("regular private file required")
        if path.stat().st_size > MAX_EVIDENCE:
            raise AcceptanceBlocked("evidence exceeds bounded file size")
    elif must_exist and not file and not path.is_dir():
        raise AcceptanceBlocked("QA evidence directory missing")
    return path


def read_json(path: Path) -> dict:
    safe_path(path)
    if path.stat().st_size > 5_000_000:
        raise AcceptanceBlocked("JSON manifest too large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcceptanceBlocked("JSON manifest not object")
    return value


def read_version(path: Path) -> str:
    safe_path(path)
    if path.stat().st_size > 64:
        raise AcceptanceBlocked("version pointer oversized")
    value = path.read_text(encoding="utf-8-sig").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise AcceptanceBlocked("malformed version pointer")
    return value


def installed_readonly_snapshot(localappdata: Path | None = None) -> dict:
    """Read ONLY program version pointer and binary SHA; never read user profile."""
    local = Path(localappdata or os.environ["LOCALAPPDATA"])
    root = safe_path(local / "Programs" / "MadarDesk", file=False)
    version = read_version(root / "current-version.txt")
    prior = root / "previous-version.txt"
    previous = read_version(prior) if prior.exists() else None
    exe = safe_path(root / "versions" / BASE_VERSION / "Madar-Desk.exe")
    with exe.open("rb") as input_file:
        header = input_file.read(2)
    if exe.stat().st_size < 1_000_000 or header != b"MZ":
        raise AcceptanceBlocked("real installed Madar baseline is not a PE")
    return {
        "current": version, "previous": previous,
        "exeSha256": sha_file(exe), "exeBytes": exe.stat().st_size,
        "root": str(root),
        "onlyProgramFilesRead": True,
    }


def get_process_names() -> list[str]:
    """Read running process list, never stop or modify any process."""
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "Get-Process | Where-Object {$_.ProcessName -match '^(Madar-Desk|MadarHost|Taraz)(-|$)'} | ForEach-Object {$_.ProcessName + ':' + $_.Id}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False, timeout=12)
    if proc.returncode:
        raise AcceptanceBlocked("cannot inspect current Madar processes")
    return [x.strip() for x in proc.stdout.splitlines() if x.strip()]


def verify_inputs() -> dict:
    """Pinned binary and QA-only /DIR guard accepted, unsigned noted, never run here."""
    safe_path(ROOT, file=False)
    safe_path(QA_RUN, file=False)
    for path, expected in (
            (QA_SETUP, QA_SETUP_SHA), (QA_ISS, QA_ISS_SHA),
            (OLD_PE, OLD_PE_SHA), (QA_ACTIVATE, QA_ACTIVATE_SHA)):
        if sha_file(safe_path(path)) != expected:
            raise AcceptanceBlocked("pinned input SHA differs: " + path.name)
    with QA_SETUP.open("rb") as exe:
        if exe.read(2) != b"MZ":
            raise AcceptanceBlocked("QA setup is not Windows PE")
    manifest = read_json(QA_MANIFEST)
    if (manifest.get("status") !=
            "QA_V127_INNO_DIR_HARDENED_SETUP_BUILT_NOT_INSTALLED"
            or manifest.get("version") != TARGET_VERSION
            or manifest.get("signed") is not False
            or manifest.get("installerExecuted") is not False
            or manifest.get("setup", {}).get("sha256") != QA_SETUP_SHA
            or manifest.get("payloadSha256") != QA_APP_SHA
            or manifest.get("hardenedInnoSha256") != QA_ISS_SHA
            or Path(manifest.get("setupPath", "")) != QA_SETUP
            or Path(manifest.get("qaOnlyDefaultInstallRoot", "")) != QA_PROGRAM):
        raise AcceptanceBlocked("candidate manifest not exact pinned QA build")
    iss = QA_ISS.read_text(encoding="utf-8")
    expected = (
        "#ifdef QA", "DefaultDirName={#QA_ROOT}",
        "QaExactInstallDestination", "GetFileAttributesW@kernel32.dll",
        "ExpandFileName(ExpandConstant('{app}'))",
        "CompareText(Expected, Actual) = 0",
        "if not QaExactInstallDestination() then begin",
        "Snapshot checksum mismatch",
    )
    # Last string is in separately staged backup helper, not the Inno script.
    if not all(item in iss for item in expected[:-1]):
        raise AcceptanceBlocked("QA installer missing exact /DIR/reparse gate")
    preflight = QA_RUN / "builder" / "scripts" / "Madar-Upgrade-Preflight.ps1"
    if "Snapshot checksum mismatch" not in safe_path(preflight).read_text(encoding="utf-8"):
        raise AcceptanceBlocked("QA backup verification missing")
    if (iss.index("if not QaExactInstallDestination() then begin") >
            iss.index("RunHiddenPowerShell('Madar-Upgrade-Preflight.ps1'")):
        raise AcceptanceBlocked("QA /DIR guard occurs too late")
    if QA_DATA.exists():
        raise AcceptanceBlocked("QA install root not sterile; never overwrite/reuse")
    current = installed_readonly_snapshot()
    if current["current"] != BASE_VERSION or current["exeSha256"] != REAL_V126_SHA:
        raise AcceptanceBlocked("real installed baseline not pinned v1.0.26")
    return {"manifestStatus": manifest["status"],
            "setupSha256": QA_SETUP_SHA, "qaStageSourceSha256": QA_ISS_SHA,
            "qaDestination": str(QA_PROGRAM),
            "installedBefore": current, "runningProcesses": get_process_names()}


def create_synthetic_profile() -> dict[str, str]:
    """Create test-only independent 3-db fixture; never touch real APPDATA."""
    if QA_DATA.exists():
        raise AcceptanceBlocked("QA fixture destination already exists")
    safe_path(QA_DATA.parent, file=False)
    QA_DATA.mkdir(mode=0o700, exist_ok=False)
    QA_ROAMING.mkdir(parents=True, exist_ok=False)
    qa_old = QA_PROGRAM / "versions" / BASE_VERSION / "Madar-Desk.exe"
    qa_old.parent.mkdir(parents=True, exist_ok=False)
    with OLD_PE.open("rb") as reader, qa_old.open("xb") as writer:
        shutil.copyfileobj(reader, writer, length=1024 * 1024)
    if sha_file(qa_old) != OLD_PE_SHA:
        raise AcceptanceBlocked("synthetic prior v1.0.26 PE copy mismatch")
    with (QA_PROGRAM / "current-version.txt").open("x", encoding="ascii") as f:
        f.write(BASE_VERSION + "\n")
    contents = {
        "tasks.json": b'{"qaOnly":true,"project":"synthetic","cards":[1,2]}\n',
        "projects/board.json": b'{"id":"synthetic-project","tasks":3}\n',
        "finance/NON_LEDGER_README.txt": b"SYNTHETIC FINANCE TEST ONLY. No real accounting data.\n",
    }
    for name, data in contents.items():
        file = QA_ROAMING / name
        file.parent.mkdir(parents=True, exist_ok=True)
        with file.open("xb") as writer:
            writer.write(data)
    for name in ("tasks", "collab", "finance"):
        file = QA_ROAMING / "db" / (name + ".sqlite")
        file.parent.mkdir(parents=True, exist_ok=True)
        if file.exists():
            raise AcceptanceBlocked("synthetic DB file unexpectedly exists")
        # sqlite3.Connection as context manager COMMITs but does NOT CLOSE.
        # On Windows, an open SQLite handle blocks Inno's profile backup zip.
        # Explicit close before invoking any installer is mandatory.
        conn = sqlite3.connect(str(file))
        try:
            conn.execute("CREATE TABLE synthetic_probe (id INTEGER PRIMARY KEY, marker TEXT)")
            conn.execute("INSERT INTO synthetic_probe(marker) VALUES (?)",
                         ("qa-only-" + name,))
            conn.commit()
        finally:
            conn.close()
    hashes = synthetic_digest_map()
    if len(hashes) != 6:
        raise AcceptanceBlocked("synthetic file count unexpected")
    return hashes


def synthetic_digest_map() -> dict[str, str]:
    safe_path(QA_ROAMING, file=False)
    files = sorted(path for path in QA_ROAMING.rglob("*") if path.is_file())
    if not files or len(files) > MAX_PROFILE_FILES:
        raise AcceptanceBlocked("synthetic fixture missing or too large")
    result = {}
    for file in files:
        safe_path(file)
        if file.stat().st_size > 1_000_000:
            raise AcceptanceBlocked("synthetic profile file oversized")
        result[file.relative_to(QA_ROAMING).as_posix()] = sha_file(file)
    return result


def verify_snapshot(snapshot: dict[str, str]) -> dict:
    """Independently hash-check all bounded synthetic backup archives.

    More than one archive is valid after a fail-closed Inno preflight is
    manually rechecked and a fresh create-only install attempt follows.
    Every archive must independently match the same never-changing fixture.
    """
    current = synthetic_digest_map()
    if snapshot != current:
        raise AcceptanceBlocked("synthetic profile mutated by installer")
    archives = sorted(QA_SNAPSHOTS.glob("Madar-Before-1.0.27-*.zip"))
    if not 1 <= len(archives) <= 4:
        raise AcceptanceBlocked("expected one to four verified QA snapshots")
    reports = []
    for item in archives:
        archive = safe_path(item)
        if archive.stat().st_size > 10_000_000:
            raise AcceptanceBlocked("synthetic snapshot exceeds byte bound")
        found = {}
        with ZipFile(archive, "r") as z:
            files = [entry for entry in z.infolist() if not entry.is_dir()]
            if len(files) != len(snapshot):
                raise AcceptanceBlocked("snapshot file count differs")
            for entry in files:
                name = entry.filename.replace("\\", "/")
                if (name not in snapshot or name in found or
                        entry.file_size > 1_000_000):
                    raise AcceptanceBlocked("snapshot unknown/duplicate oversized entry")
                found[name] = sha256(z.read(entry)).hexdigest()
        if found != snapshot:
            raise AcceptanceBlocked("independent snapshot hash mismatch")
        reports.append({"path": str(archive), "sha256": sha_file(archive),
                        "files": len(found)})
    return {"archives": reports, "count": len(reports),
            "independentHashReadback": True}


def installer_command(log_path: Path, *, install_dir: Path | None = None) -> list[str]:
    """No shell, no installed path: command operates on isolated QA only."""
    if install_dir is None:
        install_dir = QA_PROGRAM
    if not install_dir.is_absolute() or not install_dir.is_relative_to(QA_RUN):
        raise AcceptanceBlocked("QA /DIR cannot target outside approved run")
    if not log_path.is_absolute() or not log_path.is_relative_to(QA_RUN):
        raise AcceptanceBlocked("QA /LOG cannot target outside approved run")
    return [str(QA_SETUP), "/VERYSILENT", "/SUPPRESSMSGBOXES",
            "/NORESTART", "/SP-", "/DIR=" + str(install_dir),
            "/LOG=" + str(log_path)]


def rollback_command() -> list[str]:
    if not QA_PROGRAM.is_relative_to(QA_DATA):
        raise AcceptanceBlocked("QA rollback target not in isolated root")
    return ["powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(QA_ACTIVATE),
            "-InstallRoot", str(QA_PROGRAM),
            "-Version", BASE_VERSION,
            "-ExpectedSHA256", OLD_PE_SHA, "-AllowRollback"]


def run_checked(args: list[str], *, timeout: int = 110) -> dict:
    # Keep installer and PowerShell scratch paths out of real APPDATA/TEMP.
    private = QA_RUN / "isolated-process-env"
    env = os.environ.copy()
    for key in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "USERPROFILE",
                "HOME"):
        path = private / key.lower()
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(args, cwd=str(QA_RUN),
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace",
                            timeout=timeout, check=False, env=env)
    return {"exitCode": result.returncode,
            "stdoutTail": result.stdout[-1200:],
            "stderrTail": result.stderr[-1200:]}


def qa_upgrade_rollback() -> dict:
    """The *actual* QA Inno setup executes only after all preflight gates."""
    facts = verify_inputs()
    run = QA_RUN / ("acceptance-" + uuid4().hex[:12])
    run.mkdir(exist_ok=False)
    output = {"schema": 1, "classification": "STERILE_QA_UPGRADE_ROLLBACK_NOT_RELEASE",
              "status": "BLOCKED", "setupSha256": QA_SETUP_SHA,
              "targetVersion": TARGET_VERSION, "installedBefore": facts["installedBefore"],
              "qaRunRoot": str(run), "qaProgramRoot": str(QA_PROGRAM),
              "productionInstallAttempted": False, "installedProgramModified": False,
              "realUserProfileTouched": False, "realLedgerTouched": False,
              "networkServiceModified": False, "realAppLaunched": False,
              "setupSignature": "NotSigned", "productionAllowed": False,
              "processesBefore": facts["runningProcesses"]}
    try:
        fingerprints = create_synthetic_profile()
        output["syntheticBefore"] = fingerprints
        output["syntheticOldExeSha256"] = OLD_PE_SHA
        # A misdirected /DIR must not escape: wrong path remains inside same
        # disposable QA run. Inno must return failure before any file copy.
        wrong = QA_DATA / "wrong-dir" / "Programs" / "MadarDesk"
        wrong_cmd = installer_command(run / "negative-dir.log", install_dir=wrong)
        negative = run_checked(wrong_cmd, timeout=75)
        output["negativeDir"] = negative
        if (negative["exitCode"] == 0 or wrong.exists() or
                (QA_PROGRAM / "versions" / TARGET_VERSION).exists()
                or list(QA_SNAPSHOTS.glob("Madar-Before-1.0.27-*.zip"))):
            raise AcceptanceBlocked("/DIR override not rejected before QA file changes")
        if synthetic_digest_map() != fingerprints:
            raise AcceptanceBlocked("synthetic profile changed after rejected /DIR")
        if read_version(QA_PROGRAM / "current-version.txt") != BASE_VERSION:
            raise AcceptanceBlocked("wrong-dir attempt mutated version pointer")
        positive = run_checked(
            installer_command(run / "positive-qa-install.log"), timeout=150)
        output["positiveQaInstall"] = positive
        if positive["exitCode"] != 0:
            raise AcceptanceBlocked("actual isolated QA Inno setup returned nonzero")
        staged = safe_path(QA_PROGRAM / "versions" / TARGET_VERSION / "Madar-Desk.exe")
        if sha_file(staged) != QA_APP_SHA:
            raise AcceptanceBlocked("Inno installed QA PE hash mismatch")
        if read_version(QA_PROGRAM / "current-version.txt") != TARGET_VERSION:
            raise AcceptanceBlocked("QA installer did not activate v1.0.27")
        if read_version(QA_PROGRAM / "previous-version.txt") != BASE_VERSION:
            raise AcceptanceBlocked("QA installer previous pointer not v1.0.26")
        output["qaInstalledExeSha256"] = sha_file(staged)
        output["verifiedPreupgradeBackup"] = verify_snapshot(fingerprints)
        # Explicit rollback is authorized **solely** for the disposable QA
        # pointer; the previous immutable EXE remains intact.
        rollback = run_checked(rollback_command(), timeout=40)
        output["qaRollback"] = rollback
        if rollback["exitCode"] != 0:
            raise AcceptanceBlocked("QA rollback command failed")
        if read_version(QA_PROGRAM / "current-version.txt") != BASE_VERSION:
            raise AcceptanceBlocked("QA rollback did not restore 1.0.26 pointer")
        if (sha_file(QA_PROGRAM / "versions" / BASE_VERSION / "Madar-Desk.exe")
                != OLD_PE_SHA or
                sha_file(QA_PROGRAM / "versions" / TARGET_VERSION / "Madar-Desk.exe")
                != QA_APP_SHA):
            raise AcceptanceBlocked("QA rollback corrupted previous/new binary")
        if synthetic_digest_map() != fingerprints:
            raise AcceptanceBlocked("synthetic data changed during rollback")
        output["verifiedPostRollbackBackup"] = verify_snapshot(fingerprints)
        output["qaRollbackToVersion"] = BASE_VERSION
        output["status"] = "QA_ISOLATED_INNO_INSTALL_BACKUP_ROLLBACK_VERIFIED"
    except (AcceptanceBlocked, OSError, ValueError, sqlite3.DatabaseError,
            subprocess.TimeoutExpired) as error:
        output["blocker"] = str(error)[:1000]
        # Never silently call a production update or destructively revert
        # unknown QA state; leave evidence intact for operator inspection.
    finally:
        try:
            output["installedAfter"] = installed_readonly_snapshot()
            if output["installedAfter"] != facts["installedBefore"]:
                output["status"] = "BLOCKED_INSTALLED_BASELINE_CHANGED"
                output["blocker"] = "real installed app version/binary changed externally"
        except (AcceptanceBlocked, OSError) as error:
            output["status"] = "BLOCKED_INSTALLED_READBACK_FAILED"
            output["blocker"] = str(error)[:700]
        with (run / "qa-upgrade-acceptance.json").open(
                "x", encoding="utf-8") as report:
            json.dump(output, report, indent=2, ensure_ascii=True, sort_keys=True)
            report.write("\n")
    return output


def resume_qa_from_verified_retry() -> dict:
    """Complete only the already-created synthetic QA acceptance after retry.

    The first Inno call failed its preflight, with no writes outside QA. The
    standalone QA preflight subsequently succeeded and a *separate* actual
    Inno retry succeeded. Record both, do not hide transient backup failure.
    Run only the SHA-pinned synthetic rollback if every byte and log matches.
    """
    safe_path(QA_RUN, file=False)
    if not QA_DATA.exists():
        raise AcceptanceBlocked("no previous synthetic QA run to resume")
    if (sha_file(safe_path(QA_SETUP)) != QA_SETUP_SHA
            or sha_file(safe_path(QA_ACTIVATE)) != QA_ACTIVATE_SHA):
        raise AcceptanceBlocked("QA setup or rollback script changed before recovery")
    run_previous = QA_RUN / "acceptance-e204b0b93d12"
    prior = read_json(run_previous / "qa-upgrade-acceptance.json")
    if (prior.get("status") != "BLOCKED"
            or prior.get("positiveQaInstall", {}).get("exitCode") != 7
            or prior.get("negativeDir", {}).get("exitCode") != 7
            or prior.get("setupSha256") != QA_SETUP_SHA
            or prior.get("installedBefore", {}).get("exeSha256") != REAL_V126_SHA):
        raise AcceptanceBlocked("previous bounded QA failure evidence not intact")
    log = safe_path(run_previous / "retry-qa-install.log")
    if log.stat().st_size > 300_000:
        raise AcceptanceBlocked("QA Inno retry log exceeds bound")
    log_text = log.read_text(encoding="utf-8-sig")
    if (log_text.count("Installation process succeeded.") != 1
            or QA_SETUP.name not in log_text
            or str(QA_PROGRAM) not in log_text
            or "QA ONLY: invalid installation destination" in log_text):
        raise AcceptanceBlocked("actual successful QA retry log not independently verified")
    first_log = safe_path(run_previous / "positive-qa-install.log")
    first_text = first_log.read_text(encoding="utf-8-sig")
    if ("PrepareToInstall failed:" not in first_text
            or "profile is unsafe" not in first_text
            or "Installation process succeeded." in first_text):
        raise AcceptanceBlocked("first failed Inno preflight evidence missing")
    wrong_log = safe_path(run_previous / "negative-dir.log")
    wrong_text = wrong_log.read_text(encoding="utf-8-sig")
    if ("QA ONLY: invalid installation destination or junction" not in wrong_text
            or "Installation process succeeded." in wrong_text):
        raise AcceptanceBlocked("wrong /DIR refusal evidence missing")
    baseline = installed_readonly_snapshot()
    if baseline != prior["installedBefore"]:
        raise AcceptanceBlocked("installed user program changed since QA attempt")
    hashes = prior["syntheticBefore"]
    if (len(hashes) != 6 or synthetic_digest_map() != hashes
            or read_version(QA_PROGRAM / "current-version.txt") != TARGET_VERSION
            or read_version(QA_PROGRAM / "previous-version.txt") != BASE_VERSION
            or sha_file(QA_PROGRAM / "versions" / TARGET_VERSION /
                        "Madar-Desk.exe") != QA_APP_SHA
            or sha_file(QA_PROGRAM / "versions" / BASE_VERSION /
                        "Madar-Desk.exe") != OLD_PE_SHA):
        raise AcceptanceBlocked("synthetic QA upgrade state inconsistent")
    backup_before = verify_snapshot(hashes)
    recovery = QA_RUN / ("acceptance-rollback-" + uuid4().hex[:12])
    recovery.mkdir(exist_ok=False)
    record = {
        "schema": 2, "status": "BLOCKED",
        "classification": "SYNTHETIC_QA_RETRY_AND_ROLLBACK_NOT_RELEASE",
        "firstAttempt": "QA_PREFLIGHT_FAILED_EXIT_7",
        "independentPreflightThenRetry": "SUCCEEDED",
        "negativeDirOverride": "BLOCKED_EXIT_7_BEFORE_COPY",
        "setupSha256": QA_SETUP_SHA, "qaAppSha256": QA_APP_SHA,
        "oldQaAppSha256": OLD_PE_SHA,
        "syntheticBefore": hashes, "backupBeforeRollback": backup_before,
        "successfulActualInnoLogSha256": sha_file(log),
        "failedActualInnoLogSha256": sha_file(first_log),
        "qaOnlyRoot": str(QA_DATA),
        "installedBefore": baseline,
        "productionInstallAttempted": False,
        "realUserProfileTouched": False,
        "realLedgerTouched": False,
        "servicesChanged": False,
        "releaseApproved": False,
        "firstPreflightIntermittenceUnresolved": True,
        "runRoot": str(recovery),
    }
    try:
        rollback = run_checked(rollback_command(), timeout=40)
        record["rollback"] = rollback
        if rollback["exitCode"] != 0:
            raise AcceptanceBlocked("synthetic rollback script returned nonzero")
        if (read_version(QA_PROGRAM / "current-version.txt") != BASE_VERSION
                or read_version(QA_PROGRAM / "previous-version.txt")
                != TARGET_VERSION):
            raise AcceptanceBlocked("QA rollback pointer state incorrect")
        if (sha_file(QA_PROGRAM / "versions" / BASE_VERSION /
                     "Madar-Desk.exe") != OLD_PE_SHA
                or sha_file(QA_PROGRAM / "versions" / TARGET_VERSION /
                            "Madar-Desk.exe") != QA_APP_SHA):
            raise AcceptanceBlocked("QA rollback changed binary content")
        if synthetic_digest_map() != hashes:
            raise AcceptanceBlocked("QA rollback modified 3-db synthetic profile")
        record["backupAfterRollback"] = verify_snapshot(hashes)
        record["rolledBackTo"] = BASE_VERSION
        record["status"] = "QA_RETRY_INSTALL_AND_SYNTHETIC_ROLLBACK_VERIFIED_WITH_PREFLIGHT_BLOCKER"
    except (AcceptanceBlocked, OSError, subprocess.TimeoutExpired) as error:
        record["blocker"] = str(error)[:700]
    finally:
        try:
            record["installedAfter"] = installed_readonly_snapshot()
            if record["installedAfter"] != baseline:
                record["status"] = "BLOCKED_REAL_INSTALLED_BASELINE_CHANGED"
        except (AcceptanceBlocked, OSError) as error:
            record["status"] = "BLOCKED_INSTALLED_READBACK"
            record["blocker"] = str(error)[:700]
        with (recovery / "qa-upgrade-recovery.json").open(
                "x", encoding="utf-8") as report:
            json.dump(record, report, indent=2, sort_keys=True, ensure_ascii=True)
            report.write("\n")
    return record


def fresh_sterile_qa_upgrade() -> dict:
    """Build a NEW hashed QA setup with a NEW static QA_ROOT; exercise first run.

    The earlier first-run backup failed because sqlite3 Connection context
    managers do not close handles. This new run explicitly closes all three
    synthetic DB handles before launching Inno and checks full backup/rollback.
    Never build a production installer or reuse any earlier QA data root.
    """
    from unittest.mock import patch

    safe_path(ROOT, file=False)
    safe_path(QA_RUN, file=False)
    manifest = read_json(QA_MANIFEST)
    if (sha_file(safe_path(QA_SETUP)) != QA_SETUP_SHA
            or sha_file(safe_path(QA_ISS)) != QA_ISS_SHA
            or manifest["payloadSha256"] != QA_APP_SHA):
        raise AcceptanceBlocked("original audited QA source identity changed")
    before = installed_readonly_snapshot()
    if before["current"] != BASE_VERSION or before["exeSha256"] != REAL_V126_SHA:
        raise AcceptanceBlocked("real installed v1.0.26 baseline changed")
    fresh = ROOT / ("fresh-acceptance-" + uuid4().hex[:12])
    fresh.mkdir(exist_ok=False)
    builder = fresh / "builder"
    scripts = builder / "scripts"
    release = builder / "release"
    assets = builder / "assets"
    scripts.mkdir(parents=True, exist_ok=False)
    release.mkdir(exist_ok=False)
    assets.mkdir(exist_ok=False)
    copying = [
        (QA_ISS, scripts / QA_ISS.name, QA_ISS_SHA),
        (QA_ACTIVATE, scripts / QA_ACTIVATE.name, QA_ACTIVATE_SHA),
        (QA_RUN / "builder" / "scripts" / "Madar-Upgrade-Preflight.ps1",
         scripts / "Madar-Upgrade-Preflight.ps1",
         "16cb3b4ebaac6d71a3e9331f0aa955021567f6f2a80aa624f6754415c896d1f4"),
        (QA_RUN / "builder" / "scripts" / "Run-Madar.cmd",
         scripts / "Run-Madar.cmd",
         "5f75414da3b888b3f45853341806d3faef570445d942a9fd9925f285e4c04984"),
        (QA_RUN / "builder" / "release" / "Madar-Desk-v1.0.27-QA-ONLY-NONRELEASE.exe",
         release / "Madar-Desk-v1.0.27-QA-ONLY-NONRELEASE.exe", QA_APP_SHA),
    ]
    icon = QA_RUN / "builder" / "assets" / "madar.ico"
    if icon.stat().st_size > 1_000_000:
        raise AcceptanceBlocked("oversized QA icon")
    copying.append((icon, assets / "madar.ico", sha_file(safe_path(icon))))
    for original, staged, expected in copying:
        if sha_file(safe_path(original)) != expected:
            raise AcceptanceBlocked("pinned QA input changed: " + original.name)
        with original.open("rb") as src, staged.open("xb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
        if sha_file(staged) != expected:
            raise AcceptanceBlocked("fresh staged QA input hash mismatch")
    qa_data = fresh / ".qa-inno-v127-20261110"
    qa_program = qa_data / "Programs" / "MadarDesk"
    qa_roaming = qa_data / "Roaming" / "MadarDesk"
    qa_snapshots = qa_data / "Snapshots"
    setup_name = "Madar-Desk-1.0.27-Setup-QA-FRESH-CLOSED-DB-NONRELEASE.exe"
    iscc = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Inno Setup 6" / "ISCC.exe"
    safe_path(iscc)
    defines = [
        str(iscc), "/Qp", "/DQA", "/DCOMPACT",
        "/DQA_ROOT=" + str(qa_data),
        "/DMadarVersion=" + TARGET_VERSION,
        "/DExeFile=" + copying[4][1].name,
        "/DRCOutputBase=" + Path(setup_name).stem,
        "/DEXE_SHA256=" + QA_APP_SHA,
        str(scripts / QA_ISS.name),
    ]
    environment = os.environ.copy()
    for key in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "USERPROFILE", "HOME"):
        item = fresh / "compiler-env" / key.lower()
        item.mkdir(parents=True, exist_ok=True)
        environment[key] = str(item)
    compiler = subprocess.run(defines, cwd=str(scripts),
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=80, env=environment, check=False)
    if compiler.returncode:
        raise AcceptanceBlocked("fresh isolated Inno compiler failed: " +
                                (compiler.stderr or compiler.stdout)[-800:])
    setup = safe_path(release / setup_name)
    with setup.open("rb") as f:
        if f.read(2) != b"MZ":
            raise AcceptanceBlocked("fresh QA compiler did not produce a PE")
    setup_hash = sha_file(setup)
    qa_manifest = {
        "schema": 4,
        "version": TARGET_VERSION, "status":
        "QA_V127_INNO_DIR_HARDENED_SETUP_BUILT_NOT_INSTALLED",
        "signed": False, "installerExecuted": False,
        "setupPath": str(setup), "qaOnlyDefaultInstallRoot": str(qa_program),
        "setup": {"sha256": setup_hash},
        "payloadSha256": QA_APP_SHA,
        "hardenedInnoSha256": QA_ISS_SHA,
        "sourceQaManifestSha256": sha_file(QA_MANIFEST),
        "sourceQaSetupSha256": QA_SETUP_SHA,
    }
    with (fresh / "qa-update-package-manifest.json").open(
            "x", encoding="utf-8") as handle:
        json.dump(qa_manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    module = sys.modules[__name__]
    with patch.multiple(
            module, QA_RUN=fresh, QA_DATA=qa_data,
            QA_PROGRAM=qa_program, QA_ROAMING=qa_roaming,
            QA_SNAPSHOTS=qa_snapshots, QA_SETUP=setup,
            QA_ISS=scripts / QA_ISS.name, QA_ACTIVATE=scripts / QA_ACTIVATE.name,
            QA_MANIFEST=fresh / "qa-update-package-manifest.json",
            QA_SETUP_SHA=setup_hash):
        evidence = qa_upgrade_rollback()
    evidence["freshCandidateSetupSha256"] = setup_hash
    evidence["freshCandidateSetupPath"] = str(setup)
    evidence["freshAcceptanceRoot"] = str(fresh)
    evidence["syntheticSQLiteHandlesClosedBeforeInno"] = True
    # qa_upgrade_rollback writes its own immutable original report; this is a
    # distinct additive attestation, never rewriting previous evidence.
    with (fresh / "fresh-acceptance-result.json").open(
            "x", encoding="utf-8") as report:
        json.dump(evidence, report, indent=2, sort_keys=True, ensure_ascii=True)
        report.write("\n")
    return evidence


def main() -> int:
    try:
        if sys.argv[1:] == ["--fresh-sterile"]:
            result = fresh_sterile_qa_upgrade()
        elif sys.argv[1:] == ["--resume-verified-qa-retry"]:
            result = resume_qa_from_verified_retry()
        elif not sys.argv[1:]:
            result = qa_upgrade_rollback()
        else:
            raise AcceptanceBlocked("only --resume-verified-qa-retry or no flag permitted")
    except (AcceptanceBlocked, OSError, ValueError, KeyError) as error:
        print("MADAR_V127_QA_INSTALL_PREFLIGHT_NO_GO " + str(error), flush=True)
        return 2
    print("MADAR_V127_UPGRADE_ACCEPTANCE " + result["status"] + " " +
          str(result.get("qaRunRoot", result.get("runRoot"))), flush=True)
    if result["status"] not in (
            "QA_ISOLATED_INNO_INSTALL_BACKUP_ROLLBACK_VERIFIED",
            "QA_RETRY_INSTALL_AND_SYNTHETIC_ROLLBACK_VERIFIED_WITH_PREFLIGHT_BLOCKER"):
        print("BLOCKER " + result.get("blocker", "unknown"), flush=True)
        return 2
    print("PRODUCTION_INSTALL_NO_GO_UNTIL_SEPARATE_RELEASE_GATES", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
