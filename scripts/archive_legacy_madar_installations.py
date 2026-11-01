"""Backup old accounting executables before removing historical installations.

This is a recovery archive, not a deployable current release and never enters Git.
"""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(os.environ["LOCALAPPDATA"]) / "Programs"
DEST = Path(os.environ["LOCALAPPDATA"]) / "MadarDesk-ReleaseBackups" / "Madar-Legacy-Installed-Binaries-20261101.zip"

def hash_bytes(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for blob in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(blob)
    return h.hexdigest()

def main():
    if DEST.exists():
        raise FileExistsError("Historical binaries backup already exists")
    roots = sorted(p for p in ROOT.iterdir()
                   if p.is_dir() and
                   (p.name.startswith("Madar Accounting ") or p.name == "Madar Suite R5"))
    if len(roots) != 15:
        raise RuntimeError("Expected exactly 15 known historical installation folders")
    files = []
    for root in roots:
        if root.is_symlink():
            raise RuntimeError("Linked root blocked")
        for file in root.rglob("*"):
            if file.is_symlink() or (hasattr(file, "is_junction") and file.is_junction()):
                raise RuntimeError("Linked installation content blocked")
            if file.is_file():
                if file.suffix.lower() not in {".exe", ".ps1", ".cmd"}:
                    raise RuntimeError("Unknown installation file type, will not delete")
                files.append((root.name + "/" + file.relative_to(root).as_posix(),
                              file, hash_bytes(file)))
    if len(files) != 17:
        raise RuntimeError("Expected 17 executable/helper files; refusing blanket cleanup")
    DEST.parent.mkdir(exist_ok=True, parents=True)
    with ZipFile(DEST, "x", ZIP_DEFLATED, compresslevel=6) as z:
        for name, file, _ in files:
            z.write(file, name)
        z.writestr("MANIFEST.json", json.dumps({
            "format": "madar-historical-program-recovery",
            "files": {name: digest for name, _, digest in files}
        }, sort_keys=True))
    with ZipFile(DEST) as z:
        if z.testzip() is not None:
            raise RuntimeError("Archive checksum failed")
        for name, file, digest in files:
            if hash_bytes(file) != digest or sha256(z.read(name)).hexdigest() != digest:
                raise RuntimeError("Original/archive file hash mismatch")
    print("LEGACY_EXECUTABLE_BACKUP_PASS", len(roots), "folders", len(files), "files")
    print("ARCHIVED_BYTES", DEST.stat().st_size)
    print("ARCHIVE_SHA256", hash_bytes(DEST))

if __name__ == "__main__":
    main()
