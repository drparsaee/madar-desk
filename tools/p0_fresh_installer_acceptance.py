"""Build and exercise a second *QA-only* Inno 1.0.3 clean-install variant."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
VERSION = "1.0.3"
STAMP = "20261102"
PROGRAM = RELEASE / f"Madar-Desk-v{VERSION}-RC-{STAMP}.exe"
FRESH = RELEASE / f"Madar-Setup-v{VERSION}-RC-{STAMP}-QA-Fresh.exe"
FRESH_ROOT = ROOT / ".qa-inno-v103-20261102-fresh"
ISCC = Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe"


def checksum(path):
    with path.open("rb") as handle:
        return sha256(handle.read()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError("Fresh RC install check failed: " + message)


def main():
    require(PROGRAM.is_file() and ISCC.is_file(), "RC exe or compiler missing")
    require(not FRESH.exists(), "Immutable QA-Fresh setup already exists")
    require(not FRESH_ROOT.exists(), "Previously used synthetic QA root exists")
    FRESH_ROOT.mkdir()
    args = [str(ISCC), "/Qp", "/DQA",
            "/DQA_ROOT=" + str(FRESH_ROOT),
            "/DMadarVersion=" + VERSION,
            "/DExeFile=" + PROGRAM.name,
            "/DRCOutputBase=" + FRESH.stem,
            "/DEXE_SHA256=" + checksum(PROGRAM),
            str(ROOT / "scripts" / "madar-update.iss")]
    subprocess.run(args, cwd=ROOT, check=True)
    require(FRESH.is_file(), "QA-Fresh compiler output missing")
    log = FRESH_ROOT / "fresh-install.log"
    result = subprocess.run(
        [str(FRESH), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
         "/LOG=" + str(log)],
        cwd=ROOT, capture_output=True, text=True, timeout=240)
    if result.returncode:
        text = log.read_text(encoding="utf8", errors="replace")[-3500:] if log.exists() else ""
        raise RuntimeError("QA clean installer failed " + str(result.returncode) + ": " + text)
    root = FRESH_ROOT / "Programs" / "MadarDesk"
    installed = root / "versions" / VERSION / "Madar-Desk.exe"
    require(installed.is_file() and checksum(installed) == checksum(PROGRAM),
            "fresh program binary hash mismatch")
    require((root / "current-version.txt").read_text().strip() == VERSION,
            "fresh install pointer not activated")
    require(not (FRESH_ROOT / "Roaming" / "MadarDesk" / "tasks.json").exists(),
            "new user profile unexpectedly seeded with tasks")
    require(not list((FRESH_ROOT / "Snapshots").glob("*.zip")) if
            (FRESH_ROOT / "Snapshots").exists() else True,
            "clean install should not claim an existing-profile backup")
    print("RC_FRESH_INSTALL_PASS", VERSION, checksum(FRESH), flush=True)
    print("ISOLATED_QA_ROOT", FRESH_ROOT, flush=True)


if __name__ == "__main__":
    main()
