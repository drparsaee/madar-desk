"""Produce one complete, immutable Madar Desktop 1.0.9 setup after integration.

Invoking this script builds the full Vite/PyInstaller application and the
single self-contained offline Inno setup. No 1.0.4..1.0.8 delta packages are
needed. Run only from the integrated 1.0.9 release worktree. Neither the
current installed application nor user databases are changed by this script.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import build_p0_release_candidate as builder


builder.VERSION = "1.0.9"
builder.LABEL = "20261103-Cumulative"
builder.PROGRAM = builder.RELEASE / "Madar-Desk-v1.0.9-Cumulative-20261103.exe"
builder.QA = builder.RELEASE / "Madar-Desk-1.0.9-Setup-QA.exe"
# Must exactly agree with madar_update.inspect_release's trusted asset name.
builder.PROD = builder.RELEASE / "Madar-Desk-1.0.9-Setup.exe"
builder.QA_ROOT = builder.ROOT / ".qa-inno-v109-cumulative"
MANIFEST = builder.RELEASE / "Madar-Desk-1.0.9-Setup.release.json"


def validate_source_metadata(package_path: Path, updater_path: Path) -> None:
    package = json.loads(package_path.read_text(encoding="utf-8"))
    if package.get("version") != builder.VERSION:
        raise ValueError("Integrated package.json must be exactly 1.0.9 before build")
    tree = ast.parse(updater_path.read_text(encoding="utf-8"))
    versions = [node.value.value for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "CURRENT_VERSION"
                        for target in node.targets)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)]
    if versions != [builder.VERSION]:
        raise ValueError("madar_update.CURRENT_VERSION must be exactly 1.0.9")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    validate_source_metadata(builder.ROOT / "package.json", builder.ROOT / "madar_update.py")
    if builder.PROD.name != "Madar-Desk-1.0.9-Setup.exe":
        raise RuntimeError("Updater filename contract mismatch")
    if MANIFEST.exists():
        raise FileExistsError("Immutable 1.0.9 release descriptor already exists")
    builder.main()  # Requires --webview2 and source version checks; creates full EXE.
    if not (builder.PROGRAM.is_file() and builder.PROD.is_file()
            and builder.QA.is_file()):
        raise RuntimeError("Complete 1.0.9 executable/QA/production setup missing")
    payload = {
        "schema": 1,
        "version": builder.VERSION,
        "asset": builder.PROD.name,
        "installerSha256": digest(builder.PROD),
        "installerBytes": builder.PROD.stat().st_size,
        "application": builder.PROGRAM.name,
        "applicationSha256": digest(builder.PROGRAM),
        "cumulativeFrom": ["1.0.4", "1.0.5", "1.0.6", "1.0.7", "1.0.8"],
        "profileMigration": "none; existing profiles and standalone finance remain in place",
    }
    with MANIFEST.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print("CUMULATIVE_SETUP_PREPARED_NOT_INSTALLED", MANIFEST, flush=True)


if __name__ == "__main__":
    main()
