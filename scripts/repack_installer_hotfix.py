"""Reissue the unchanged Madar 1.0.1 executable with a repaired installer.

Does not overwrite the previously issued distribution.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
BASE = "Madar-Desk-v1.0.1-Customer-20261028"
HOTFIX = BASE + "-InstallerFix1"
SOURCE = RELEASE / BASE
TARGET = RELEASE / HOTFIX
ZIP = RELEASE / (HOTFIX + ".zip")

def sha(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()

def main():
    if TARGET.exists() or ZIP.exists():
        raise FileExistsError("Immutable hotfix release already exists")
    original = SOURCE / "Madar-Release-Manifest.json"
    manifest = json.loads(original.read_text(encoding="utf-8"))
    exe = SOURCE / manifest["executable"]
    if sha(exe).lower() != manifest["sha256"].lower():
        raise RuntimeError("Existing executable hash failed verification")
    TARGET.mkdir()
    for item in SOURCE.iterdir():
        if item.is_file():
            shutil.copy2(item, TARGET / item.name)
    shutil.copy2(ROOT / "scripts" / "Install-Madar-Customer.ps1",
                 TARGET / "Install-Madar-Customer.ps1")
    manifest["otherFilesSha256"]["Install-Madar-Customer.ps1"] = sha(TARGET / "Install-Madar-Customer.ps1")
    (TARGET / "Madar-Release-Manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with ZipFile(ZIP, "x", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for f in sorted(TARGET.iterdir()):
            archive.write(f, f.name)
    with ZipFile(ZIP) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Bad ZIP file")
        if set(archive.namelist()) != {f.name for f in TARGET.iterdir()}:
            raise RuntimeError("Incomplete ZIP file")
    (RELEASE / (HOTFIX + ".sha256.txt")).write_text(
        sha(ZIP) + "  " + ZIP.name + "\n", encoding="ascii")
    print("OUTPUT", ZIP)
    print("ZIP_SHA256", sha(ZIP))
    print("EXE_SHA256", sha(TARGET / manifest["executable"]))

if __name__ == "__main__":
    main()
