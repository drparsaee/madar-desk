"""Build one complete, immutable Madar Desk 1.0.10 cumulative installer.

The output is a full Vite/PyInstaller program in a versioned Inno Setup,
not a delta patch. 1.0.5, 1.0.6 and 1.0.9 can update directly to this build.
This script prepares release files; it never installs or publishes them.
Do not run before source integration and real release QA approval.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import build_p0_release_candidate as builder


builder.VERSION = "1.0.10"
builder.LABEL = "20261103-Cumulative"
builder.PROGRAM = builder.RELEASE / "Madar-Desk-v1.0.10-Cumulative-20261103.exe"
builder.QA = builder.RELEASE / "Madar-Desk-1.0.10-Setup-QA.exe"
builder.PROD = builder.RELEASE / "Madar-Desk-1.0.10-Setup.exe"
builder.QA_ROOT = builder.ROOT / ".qa-inno-v110-cumulative"
MANIFEST = builder.RELEASE / "Madar-Desk-1.0.10-Setup.release.json"


def validate_source_metadata(package_path: Path, updater_path: Path,
                             lock_path: Path) -> None:
    package = json.loads(package_path.read_text(encoding="utf-8"))
    if package.get("version") != builder.VERSION:
        raise ValueError("package.json must identify complete release 1.0.10")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("version") != builder.VERSION or (
            lock.get("packages", {}).get("", {}).get("version") != builder.VERSION):
        raise ValueError("package-lock.json root versions must be 1.0.10")
    tree = ast.parse(updater_path.read_text(encoding="utf-8"))
    versions = [node.value.value for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "CURRENT_VERSION"
                        for target in node.targets)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)]
    if versions != [builder.VERSION]:
        raise ValueError("madar_update.CURRENT_VERSION must be 1.0.10")
    if "scripts/build_integrated_v110.py" not in package.get("scripts", {}).get("dist:rc", ""):
        raise ValueError("Default installer build must use v1.0.10 wrapper")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as data:
        for chunk in iter(lambda: data.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    validate_source_metadata(builder.ROOT / "package.json",
                             builder.ROOT / "madar_update.py",
                             builder.ROOT / "package-lock.json")
    if builder.PROD.name != "Madar-Desk-1.0.10-Setup.exe":
        raise RuntimeError("Auto-updater expects exact 1.0.10 setup filename")
    if any(p.exists() for p in (builder.PROGRAM, builder.QA, builder.PROD, MANIFEST)):
        raise FileExistsError("Immutable 1.0.10 release artifact exists; refusing overwrite")
    builder.main()  # Requires --webview2 and a Microsoft Authenticode signature.
    if not all(p.is_file() for p in (builder.PROGRAM, builder.QA, builder.PROD)):
        raise RuntimeError("Complete 1.0.10 program and QA/production setup are required")
    descriptor = {
        "schema": 1,
        "version": builder.VERSION,
        "asset": builder.PROD.name,
        "installerSha256": digest(builder.PROD),
        "installerBytes": builder.PROD.stat().st_size,
        "application": builder.PROGRAM.name,
        "applicationSha256": digest(builder.PROGRAM),
        "cumulativeFrom": ["1.0.5", "1.0.6", "1.0.7", "1.0.8", "1.0.9"],
        "profileMigration": "none; preserve all existing task and standalone accounting data",
    }
    with MANIFEST.open("x", encoding="utf-8") as output:
        json.dump(descriptor, output, indent=2, ensure_ascii=False)
        output.write("\n")
    print("CUMULATIVE_110_PREPARED_NOT_INSTALLED", MANIFEST, flush=True)


if __name__ == "__main__":
    main()
