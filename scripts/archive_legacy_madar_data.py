"""Archive scattered historical Madar accounting profiles before cleanup.

Archive lives under the current user's LocalAppData release-backup directory.
It is intentionally not placed in Git. Requires no third-party dependency.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(os.environ["LOCALAPPDATA"])
DEST = ROOT / "MadarDesk-ReleaseBackups" / "Madar-Legacy-Accounting-Profiles-20261101.zip"
DIRS = sorted(p for p in ROOT.iterdir() if p.is_dir() and
              (p.name.startswith("Madar Accounting Companies R") or
               p.name == "Madar Suite Data R5"))

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()

def main():
    if not DIRS:
        raise RuntimeError("Legacy data locations were not found")
    if DEST.exists():
        raise FileExistsError("Historical accounting archive already exists, never overwrite")
    metadata = {}
    files = []
    for folder in DIRS:
        if folder.is_symlink():
            raise RuntimeError("Cannot archive link/junction root")
        metadata[folder.name] = 0
        for item in folder.rglob("*"):
            if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                raise RuntimeError("Unexpected symlink or junction inside legacy profile")
            if not item.is_file():
                continue
            name = folder.name + "/" + item.relative_to(folder).as_posix()
            if name in (entry[0] for entry in files):
                raise RuntimeError("Duplicate file path")
            files.append((name, item, sha(item)))
            metadata[folder.name] += 1
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(DEST, "x", ZIP_DEFLATED, compresslevel=6) as archive:
        for name, source, _ in files:
            archive.write(source, name)
        archive.writestr("MANIFEST.json", json.dumps({
            "format": "madar-historical-profile-snapshot",
            "date": "2026-11-01",
            "files": {name: digest for name, _, digest in files},
            "roots": metadata,
        }, sort_keys=True, ensure_ascii=False))
    with ZipFile(DEST) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP CRC check failed")
        expected = json.loads(archive.read("MANIFEST.json"))["files"]
        if len(expected) != len(files):
            raise RuntimeError("ZIP file count mismatch")
        for name, source, digest in files:
            if source.is_file() and sha(source) != digest:
                raise RuntimeError("Source file changed during backup")
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise RuntimeError("Archive content mismatch")
    print("LEGACY_ARCHIVE_VERIFIED", len(metadata), "roots", len(files), "files")
    print("LEGACY_ARCHIVE_BYTES", DEST.stat().st_size)
    print("LEGACY_ARCHIVE_SHA256", sha(DEST))

if __name__ == "__main__":
    main()
