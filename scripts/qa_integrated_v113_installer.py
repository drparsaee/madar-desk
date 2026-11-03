"""Execute ONLY the separately compiled QA installer in synthetic Madar data.

The QA Inno binary is compiled with a fixed .qa-inno-v113-integrated root and
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

from build_integrated_v113 import builder, MANIFEST, digest


def snapshot(root: Path):
    return {file.relative_to(root).as_posix(): sha256(file.read_bytes()).hexdigest()
            for file in root.rglob("*") if file.is_file()}


def main():
    if not builder.QA.is_file() or not builder.PROD.is_file() or not builder.PROGRAM.is_file():
        raise FileNotFoundError("Compile immutable 1.0.13 QA/production installers first")
    if not MANIFEST.is_file():
        raise FileNotFoundError("Integrated release descriptor missing")
    descriptor = json.loads(MANIFEST.read_text(encoding="utf8"))
    if (descriptor.get("version") != "1.0.13" or
            descriptor.get("installerSha256") != digest(builder.PROD) or
            descriptor.get("applicationSha256") != digest(builder.PROGRAM)):
        raise RuntimeError("Release descriptor or program hash mismatch")

    qa = builder.QA_ROOT
    if qa.exists() and any(qa.iterdir()):
        raise FileExistsError("Refusing to overwrite an existing QA profile: " + str(qa))
    qa.mkdir(parents=True, exist_ok=True)
    marker = qa / ".madar-v113-synthetic-only.json"
    marker.write_text('{"version":"1.0.13","purpose":"synthetic-installer-acceptance"}',
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
    old = installation / "versions" / "1.0.12" / "Madar-Desk.exe"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"MZsynthetic-v1.0.11-old-program")
    (installation / "current-version.txt").write_text("1.0.11\n", encoding="ascii")
    old_digest = digest(old)
    log = qa / "qa-installer.log"
    command = [str(builder.QA), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
               "/SP-", "/LOG=" + str(log)]
    result = subprocess.run(command, capture_output=True, timeout=240,
                            check=False, text=True)
    if result.returncode:
        raise RuntimeError("Synthetic Inno QA installer failed with " + str(result.returncode)
                           + ": " + (result.stderr or result.stdout)[-1500:])
    target = installation / "versions" / "1.0.13" / "Madar-Desk.exe"
    if (not target.is_file() or digest(target) != descriptor["applicationSha256"] or
            (installation / "current-version.txt").read_text().strip() != "1.0.13" or
            (installation / "previous-version.txt").read_text().strip() != "1.0.12"):
        raise RuntimeError("QA installer did not safely activate the complete application")
    if digest(old) != old_digest or snapshot(profile) != before:
        raise RuntimeError("QA installer changed synthetic data or the old application")
    backups = list((qa / "Snapshots").glob("Madar-Before-1.0.13-*.zip"))
    if len(backups) != 1:
        raise RuntimeError("QA installer did not preserve exactly one verified backup")
    with ZipFile(backups[0]) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Corrupt synthetic backup")
        zip_hashes = {name: sha256(archive.read(name)).hexdigest()
                      for name in archive.namelist() if not name.endswith("/")}
    if zip_hashes != before:
        raise RuntimeError("Synthetic backup content differs from original data")
    # Remove only the positively identified self-owned disposable QA directory.
    if not marker.is_file() or json.loads(marker.read_text(encoding="utf8"))["version"] != "1.0.13":
        raise RuntimeError("Synthetic QA ownership marker missing, refusing cleanup")
    shutil.rmtree(qa)
    print("INNO_113_SYNTHETIC_UPGRADE_PASSED: old=1.0.12 new=1.0.13;"
          f" preserved={len(before)} files, verified_backup={len(zip_hashes)} files;"
          " isolated QA directory removed; real profile untouched", flush=True)


if __name__ == "__main__":
    main()
