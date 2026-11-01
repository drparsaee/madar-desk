"""Read-only independent restore verification of one offline Madar profile ZIP.

Restores into a temporary PRIVATE Windows user folder, never into a live
APPDATA profile or the Git repository. Never prints actual file contents.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    if not archive.is_file():
        raise RuntimeError("Expected an actual snapshot ZIP file")
    with tempfile.TemporaryDirectory(
        prefix="MadarRestoreVerification-", dir=os.environ["LOCALAPPDATA"]
    ) as directory:
        root = Path(directory)
        with zipfile.ZipFile(archive) as backup:
            if backup.testzip() is not None:
                raise RuntimeError("Archive CRC validation failed")
            sources = {}
            for info in backup.infolist():
                if info.is_dir():
                    continue
                item = PurePosixPath(info.filename)
                if (item.is_absolute() or len(item.parts) > 15 or
                    ".." in item.parts or chr(92) in info.filename or
                    not item.parts or any(part in {"", "."} for part in item.parts)):
                    raise RuntimeError("Unexpected archive member path")
                if info.file_size > 256 * 1024 * 1024:
                    raise RuntimeError("Archive member exceeds restore policy")
                if info.filename in sources:
                    raise RuntimeError("Duplicate archive member")
                sources[info.filename] = info.file_size
            if len(sources) > 10000 or sum(sources.values()) > 1_073_741_824:
                raise RuntimeError("Snapshot exceeds bounded restore policy")
            for name in sources:
                target = root.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with backup.open(name) as inp, target.open("xb") as out:
                    import shutil
                    shutil.copyfileobj(inp, out)
                if target.stat().st_size != sources[name]:
                    raise RuntimeError("Unexpected reconstructed file size")
                with backup.open(name) as inp:
                    source_sha = sha256(inp.read()).digest()
                with target.open("rb") as inp:
                    restored_sha = sha256(inp.read()).digest()
                if source_sha != restored_sha:
                    raise RuntimeError("Restored content SHA mismatch")
        tasks = root / "tasks.json"
        if tasks.exists():
            import json
            state = json.loads(tasks.read_text(encoding="utf-8-sig"))
            if not isinstance(state.get("projects"), list) or not isinstance(state.get("tasks"), list):
                raise RuntimeError("Restored task data has invalid basic schema")
            print("RESTORE_TASKS_OK", len(state["projects"]), len(state["tasks"]))
        dbpath = root / "standalone-accounting.sqlite3"
        if dbpath.exists():
            database = sqlite3.connect(f"file:{dbpath.as_posix()}?mode=ro", uri=True)
            try:
                check = database.execute("pragma quick_check").fetchone()[0]
                if check != "ok":
                    raise RuntimeError("Restored SQLite quick check failed")
            finally:
                database.close()
            print("RESTORE_SQLITE_OK")
        print("RESTORE_VERIFICATION_PASS", len(sources), "files")


if __name__ == "__main__":
    main()
