"""Real Inno Setup QA installer, entirely inside an isolated synthetic profile.

This must never point to the user's APPDATA, real installed Madar, or Parsian
database. It does not launch the installed GUI or publish a release.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / ".qa-inno-v112-cumulative"
PROFILE = QA / "Roaming" / "MadarDesk"
SNAPSHOTS = QA / "Snapshots"
INSTALL = QA / "Programs" / "MadarDesk"
LOG = QA / "qa-install.log"
EVIDENCE = QA / "qa-acceptance-v112.json"
MANIFEST = ROOT / "release" / "Madar-Desk-1.0.12-Setup.release.json"
QA_SETUP = ROOT / "release" / "Madar-Desk-1.0.12-Setup-QA.exe"


def sha(path: Path):
    h = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(root: Path):
    return {file.relative_to(root).as_posix(): sha(file)
            for file in root.rglob("*") if file.is_file()}


def main():
    if ROOT != QA.parent or QA.name != ".qa-inno-v112-cumulative":
        raise RuntimeError("QA scope guard failed")
    if not QA_SETUP.is_file() or not MANIFEST.is_file():
        raise FileNotFoundError("Compiled 1.0.12 QA installer or manifest missing")
    if EVIDENCE.exists() or PROFILE.exists() or LOG.exists():
        raise FileExistsError("QA profile already exists; never reuse/overwrite")
    meta = json.loads(MANIFEST.read_text(encoding="utf8"))
    assert meta["version"] == "1.0.12"
    QA.mkdir(exist_ok=True)
    PROFILE.mkdir(parents=True)
    SNAPSHOTS.mkdir(exist_ok=True)
    (PROFILE / "tasks.json").write_text(json.dumps({
        "schema": 1, "boards": [{"id": "SYN-BOARD", "name": "Synthetic"}],
        "tasks": [{"id": "SYN-TASK", "title": "Protect data"}]
    }), encoding="utf8")
    (PROFILE / "planner-synthetic.json").write_text(
        json.dumps({"account": '["solo","local"]',
                    "items": [{"id": "PL-1", "title": "Synthetic"}]}), encoding="utf8")
    (PROFILE / "company-settings.json").write_text(json.dumps({
        "legalName": "Synthetic fixture only", "currency": "RIAL",
        "postingUtcOffsetMinutes": 210
    }), encoding="utf8")
    (PROFILE / "synthetic-attachment.dat").write_bytes(b"not-user-data\x00fixture")
    ledger = PROFILE / "standalone-accounting.sqlite3"
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE synthetic_rial_ledger(id TEXT PRIMARY KEY, rial INTEGER NOT NULL)")
        db.execute("INSERT INTO synthetic_rial_ledger VALUES(?,?)", ("SYN-FIN-1", 515_200_000))
        db.commit()
    before = snapshot(PROFILE)
    if len(before) != 5:
        raise AssertionError(f"Unexpected QA fixture file count: {len(before)}")
    old = INSTALL / "versions" / "1.0.11" / "Madar-Desk.exe"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"MZsynthetic-old-1.0.11-executable")
    (INSTALL / "current-version.txt").write_text("1.0.11\n", encoding="ascii")
    old_hash = sha(old)
    setup = subprocess.run(
        [str(QA_SETUP), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
         "/LOG=" + str(LOG)],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    if setup.returncode != 0:
        raise RuntimeError("QA installer failed: return " + str(setup.returncode)
                           + "; log tail: " + LOG.read_text(errors="replace")[-2200:])
    current = (INSTALL / "current-version.txt").read_text(encoding="ascii").strip()
    previous = (INSTALL / "previous-version.txt").read_text(encoding="ascii").strip()
    target = INSTALL / "versions" / "1.0.12" / "Madar-Desk.exe"
    if current != "1.0.12" or previous != "1.0.11":
        raise AssertionError(f"Version pointers incorrect: {current}/{previous}")
    if not target.is_file() or sha(target) != meta["applicationSha256"]:
        raise AssertionError("Installed binary fails full release manifest digest")
    if sha(old) != old_hash:
        raise AssertionError("Old 1.0.11 executable was changed")
    after = snapshot(PROFILE)
    if before != after:
        raise AssertionError(f"Profile was modified: before={before} after={after}")
    archive_files = list(SNAPSHOTS.glob("Madar-Before-1.0.12-*.zip"))
    if len(archive_files) != 1:
        raise AssertionError(f"Expected one QA backup archive, got {len(archive_files)}")
    with ZipFile(archive_files[0]) as archive:
        if archive.testzip() is not None:
            raise AssertionError("QA snapshot ZIP integrity failed")
        entries = {key.replace("\\", "/"): sha256(archive.read(key)).hexdigest()
                   for key in archive.namelist() if not key.endswith("/")}
        if entries != before:
            raise AssertionError("QA snapshot content fails file SHA comparison")
    with sqlite3.connect(ledger) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        amount = db.execute("SELECT rial FROM synthetic_rial_ledger WHERE id='SYN-FIN-1'").fetchone()[0]
    if integrity != "ok" or amount != 515_200_000:
        raise AssertionError("Synthetic RIAL fixture changed or failed SQLite validation")
    report = {
        "status": "PASS", "scenario": "actual QA Inno installer on synthetic 1.0.11",
        "setupExitCode": setup.returncode, "installedVersion": current,
        "previousVersion": previous, "profileFiles": len(before), "changedProfileFiles": 0,
        "archive": str(archive_files[0]), "archiveFilesVerified": len(entries),
        "archiveSha256": sha(archive_files[0]), "sqliteIntegrity": integrity,
        "sqliteRial": amount, "oldExecutablePreserved": True,
        "installedExecutableSha256": sha(target), "manifestSha256": meta["applicationSha256"],
        "scope": str(QA), "realUserProfileAccess": False,
        "packagedGuiSmokeTested": False,
    }
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf8")
    print("QA_INSTALLER_PASS " + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
