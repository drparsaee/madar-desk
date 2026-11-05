"""Execute ONLY the separately compiled QA installer in synthetic Madar data.

The QA Inno binary is compiled with a fixed .qa-inno-v114-integrated root and
cannot write the production APPDATA or the installed production program. The
test refuses a nonempty preexisting QA root and never kills unrelated apps.
"""
from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
from zipfile import ZipFile

from build_integrated_v114 import (builder, digest, read_verified_release_descriptor,
                                   QA_ACCEPTANCE as ACCEPTANCE)


def snapshot(root: Path):
    return {file.relative_to(root).as_posix(): sha256(file.read_bytes()).hexdigest()
            for file in root.rglob("*") if file.is_file()}


def assert_disposable_qa_root(qa: Path) -> None:
    """No caller-selected profile, linked/junction directory or live APPDATA."""
    expected = builder.ROOT / ".qa-inno-v114-integrated"
    if qa != expected or qa.parent.resolve() != builder.ROOT.resolve():
        raise RuntimeError("QA installer destination is not the fixed isolated root")
    for directory in (qa, *qa.parents):
        if directory.is_symlink() or (hasattr(directory, "is_junction") and
                                      directory.is_junction()):
            raise RuntimeError("QA root or ancestor is a link/junction: " + str(directory))


def main():
    # Verify the QA installer itself before executing it. A renamed production
    # installer must never run here just because production/application match.
    descriptor = read_verified_release_descriptor()
    if ACCEPTANCE.exists():
        raise FileExistsError("Immutable 1.0.14 QA acceptance already exists")

    qa = builder.QA_ROOT
    assert_disposable_qa_root(qa)
    if qa.exists() and any(qa.iterdir()):
        raise FileExistsError("Refusing to overwrite an existing QA profile: " + str(qa))
    qa.mkdir(parents=True, exist_ok=True)
    marker = qa / ".madar-v114-synthetic-only.json"
    marker.write_text('{"version":"1.0.14","purpose":"synthetic-installer-acceptance"}',
                      encoding="utf8")
    profile = qa / "Roaming" / "MadarDesk"
    profile.mkdir(parents=True)
    (profile / "tasks.json").write_text(json.dumps({"tasks": [{"id": "SYNTHETIC-TASK"}]}),
                                         encoding="utf8")
    (profile / "attachment.dat").write_bytes(b"synthetic-private-attachment-not-a-user-file")
    db_file = profile / "standalone-accounting.sqlite3"
    with closing(sqlite3.connect(db_file)) as connection, connection:
        connection.execute("CREATE TABLE QA_ledger (id INTEGER PRIMARY KEY, rial INTEGER NOT NULL)")
        connection.execute("INSERT INTO QA_ledger(rial) VALUES (987654321)")
    (profile / "standalone-accounting.sqlite3-wal").write_bytes(b"synthetic-wal-only")
    (profile / "standalone-accounting.sqlite3-shm").write_bytes(b"synthetic-shm-only")
    (profile / "test-parsian.bak").write_bytes(b"synthetic-test-only-not-a-real-parsian-backup")
    before = snapshot(profile)

    installation = qa / "Programs" / "MadarDesk"
    old = installation / "versions" / "1.0.13" / "Madar-Desk.exe"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"MZsynthetic-v1.0.13-old-program")
    (installation / "current-version.txt").write_text("1.0.13\n", encoding="ascii")
    old_digest = digest(old)
    log = qa / "qa-installer.log"
    command = [str(builder.QA), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
               "/SP-", "/DIR=" + str(installation), "/LOG=" + str(log)]
    if digest(builder.QA) != descriptor["qaInstallerSha256"]:
        raise RuntimeError("QA executable changed after preflight verification")
    result = subprocess.run(command, capture_output=True, timeout=240,
                            check=False, text=True)
    if result.returncode:
        raise RuntimeError("Synthetic Inno QA installer failed with " + str(result.returncode)
                           + ": " + (result.stderr or result.stdout)[-1500:])
    target = installation / "versions" / "1.0.14" / "Madar-Desk.exe"
    if (not target.is_file() or digest(target) != descriptor["applicationSha256"] or
            (installation / "current-version.txt").read_text().strip() != "1.0.14" or
            (installation / "previous-version.txt").read_text().strip() != "1.0.13"):
        raise RuntimeError("QA installer did not safely activate the complete application")
    if digest(old) != old_digest or snapshot(profile) != before:
        raise RuntimeError("QA installer changed synthetic data or the old application")
    backups = list((qa / "Snapshots").glob("Madar-Before-1.0.14-*.zip"))
    if len(backups) != 1:
        raise RuntimeError("QA installer did not preserve exactly one verified backup")
    with ZipFile(backups[0]) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Corrupt synthetic backup")
        zip_hashes = {name: sha256(archive.read(name)).hexdigest()
                      for name in archive.namelist() if not name.endswith("/")}
    if zip_hashes != before:
        raise RuntimeError("Synthetic backup content differs from original data")
    if not log.is_file():
        raise RuntimeError("QA Inno installer did not produce a diagnostic log")
    log_digest = digest(log)
    # Remove only the positively identified self-owned disposable QA directory.
    assert_disposable_qa_root(qa)
    if (not marker.is_file() or
            json.loads(marker.read_text(encoding="utf8")) != {
                "version": "1.0.14", "purpose": "synthetic-installer-acceptance"}):
        raise RuntimeError("Synthetic QA ownership marker missing, refusing cleanup")
    shutil.rmtree(qa)
    if qa.exists():
        raise RuntimeError("Disposable QA root still exists after cleanup")
    receipt = {
        "schema": 1, "version": "1.0.14", "result": "synthetic-installer-passed",
        "sourceGitCommit": descriptor["sourceGitCommit"],
        "qaInstallerSha256": descriptor["qaInstallerSha256"],
        "productionInstallerSha256": descriptor["installerSha256"],
        "applicationSha256": descriptor["applicationSha256"],
        "qaInstallerLogSha256": log_digest,
        "upgradeFrom": "1.0.13", "upgradeTo": "1.0.14",
        "syntheticProfileFileCount": len(before),
        "verifiedBackupFileCount": len(zip_hashes),
        "previousProgramUnchanged": True,
        "profileByteHashesUnchanged": True,
        "qaDirectoryRemoved": True,
    }
    with ACCEPTANCE.open("x", encoding="utf-8") as output:
        json.dump(receipt, output, indent=2, ensure_ascii=False)
        output.write("\n")
    print("INNO_114_SYNTHETIC_UPGRADE_PASSED: old=1.0.13 new=1.0.14;"
          f" preserved={len(before)} files, verified_backup={len(zip_hashes)} files;"
          " isolated QA directory removed; real profile not inspected", flush=True)


if __name__ == "__main__":
    main()
