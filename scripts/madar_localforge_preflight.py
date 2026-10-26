"""Read-only comparison of a Madar source tree with a local Git staging snapshot.

This tool deliberately does not initialize repositories, inspect file contents,
modify any files, contact a network service or invoke Git operations that write.
Its output is an inventory for a human to review before deciding on migration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "release", "__pycache__",
    ".pytest_cache", ".venv", "venv", ".idea", ".vscode",
}
PRIVATE_SUFFIXES = {
    ".bak", ".db", ".sqlite", ".sqlite3", ".mdf", ".ldf",
    ".key", ".pem", ".pfx", ".p12", ".exe", ".zip",
    ".log", ".env", ".sqlite-wal", ".sqlite-shm",
}
PRIVATE_NAMES = {"id_rsa", "id_ed25519", "credentials.json", "secrets.json"}
GENERATED_FILE_PREFIXES = (".qa", ".build", ".private", ".chrome", ".scratch", ".dist")
PROJECT_PATH_RE = re.compile(r"^[\w.\-][\w./\-]*$")


def excluded_directory(name: str) -> bool:
    lower = name.lower()
    return (lower in SKIP_DIRS or lower.startswith((
                ".qa", ".build", ".private", ".chrome", ".scratch", ".dist",
                ".rial-", ".standalone-gui-", ".rea-"))
            or lower.startswith("v1-gui-smoke-"))


def possible_private(path: str) -> bool:
    """Conservative filename-only warning, without opening file data."""
    name = Path(path).name.lower()
    parts = path.replace("\\", "/").lower().split("/")
    return (
        name in PRIVATE_NAMES
        or name.startswith(".env")
        or Path(name).suffix.lower() in PRIVATE_SUFFIXES
        or any(part in {"appdata", "private", "secrets", "credentials"} for part in parts)
    )


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_safe_files(root: Path) -> tuple[dict[str, str], list[str], list[str]]:
    found: dict[str, str] = {}
    skipped: list[str] = []
    risky: list[str] = []
    for directory, folders, files in os.walk(root, followlinks=False):
        relative_folder = Path(directory).relative_to(root)
        safe_folders = []
        for name in sorted(folders):
            child = relative_folder / name
            child_path = Path(directory) / name
            if excluded_directory(name) or child_path.is_symlink():
                skipped.append(child.as_posix() + "/")
            else:
                safe_folders.append(name)
        folders[:] = safe_folders
        for name in sorted(files):
            path = Path(directory) / name
            relative = (relative_folder / name).as_posix()
            if name.lower().startswith(GENERATED_FILE_PREFIXES):
                skipped.append(relative)
            elif path.is_symlink():
                skipped.append(relative)
            elif possible_private(relative):
                risky.append(relative)
            elif not PROJECT_PATH_RE.fullmatch(relative):
                skipped.append(relative)
            else:
                found[relative] = digest_file(path)
    return found, skipped, risky


def git_inventory(staging: Path) -> tuple[set[str], str | None, list[str]]:
    commands = [
        ["git", "-C", str(staging), "ls-files", "-z"],
        ["git", "-C", str(staging), "rev-parse", "HEAD"],
        ["git", "-C", str(staging), "remote", "-v"],
    ]
    results = []
    for command in commands:
        result = subprocess.run(command, capture_output=True, check=False, timeout=20)
        if result.returncode:
            raise RuntimeError(f"Git inspection failed: {command[-1]} (exit {result.returncode})")
        results.append(result.stdout)
    tracked = {p.decode("utf-8", "surrogateescape") for p in results[0].split(b"\0") if p}
    revision = results[1].decode("utf-8", "replace").strip() or None
    remotes = [line for line in results[2].decode("utf-8", "replace").splitlines() if line.strip()]
    return tracked, revision, remotes


def audit(source: Path, staging: Path) -> dict[str, object]:
    if not source.is_dir() or not staging.is_dir():
        raise ValueError("Both source and staging must be existing directories")
    if source.resolve() == staging.resolve():
        raise ValueError("Source and staging must be different directories")
    tracked, revision, remotes = git_inventory(staging)
    source_files, skipped, risky = scan_safe_files(source)
    stage_files, _, _ = scan_safe_files(staging)
    # Read only regular safe files in the staging working tree. Restrict the
    # comparison to Git-tracked paths; untracked staging files are not evidence.
    source_paths = set(source_files)
    safe_tracked = {p for p in tracked if not possible_private(p)}
    common = source_paths & safe_tracked
    modified = sorted(p for p in common if source_files[p] != stage_files.get(p))
    missing_from_stage = sorted(source_paths - safe_tracked)
    missing_from_source = sorted(safe_tracked - source_paths)
    inaccessible = sorted(p for p in common if p not in stage_files)
    report = {
        "source": str(source.resolve()),
        "staging": str(staging.resolve()),
        "staging_revision": revision,
        "staging_remote_configured": bool(remotes),
        "remote_count": len({line.split()[0] for line in remotes if line.split()}),
        "safe_source_file_count": len(source_files),
        "tracked_file_count": len(tracked),
        "modified_count": len(modified),
        "missing_from_staging_count": len(missing_from_stage),
        "missing_from_source_count": len(missing_from_source),
        "inaccessible_staging_count": len(inaccessible),
        "risky_filename_count": len(risky),
        "excluded_path_count": len(skipped),
        "modified": modified,
        "missing_from_staging": missing_from_stage,
        "missing_from_source": missing_from_source,
        "inaccessible_staging": inaccessible,
        "risky_filenames_not_read": risky,
        "excluded_paths_not_read": skipped,
    }
    report["ready_for_manual_review"] = not inaccessible
    report["automatic_push_allowed"] = False
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--max-paths", type=int, default=30)
    args = parser.parse_args()
    try:
        result = audit(args.source, args.staging)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"Preflight failed: {exc}", file=sys.stderr)
        return 2
    for key in ("modified", "missing_from_staging", "missing_from_source",
                "inaccessible_staging", "risky_filenames_not_read", "excluded_paths_not_read"):
        paths = result[key]
        assert isinstance(paths, list)
        result[key] = paths[:max(0, args.max_paths)]
        result[key + "_truncated"] = len(paths) > max(0, args.max_paths)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
