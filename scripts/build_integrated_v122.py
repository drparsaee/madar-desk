"""Build one complete, immutable cumulative Madar Desk 1.0.22 installer.

Builds a full Vite/PyInstaller application and two Inno installers. No delta
patch, live data access, installation or publication is performed here.
Only run after integrated financial, UX and synthetic-upgrade gates pass.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "build_p0_release_candidate_v122",
    Path(__file__).with_name("build_p0_release_candidate.py"))
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)

builder.VERSION = "1.0.22"
builder.LABEL = "20261105-LabelsDock"
builder.PROGRAM = builder.RELEASE / "Madar-Desk-v1.0.22-Cumulative-20261105-UX.exe"
builder.QA = builder.RELEASE / "Madar-Desk-1.0.22-Setup-QA.exe"
builder.PROD = builder.RELEASE / "Madar-Desk-1.0.22-Setup.exe"
builder.QA_ROOT = builder.ROOT / ".qa-inno-v122-integrated"
MANIFEST = builder.RELEASE / "Madar-Desk-1.0.22-Setup.release.json"
QA_ACCEPTANCE = builder.RELEASE / "Madar-Desk-1.0.22-Setup-QA.acceptance.json"


def artifact_sidecars() -> tuple[Path, ...]:
    """An old hash receipt is also a partial release and must not be replaced."""
    return tuple(builder.RELEASE / (path.name + ".sha256.txt")
                 for path in (builder.PROGRAM, builder.QA, builder.PROD))


def validate_source_metadata(package_path: Path, updater_path: Path,
                             lock_path: Path) -> None:
    package = json.loads(package_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if (package.get("version") != builder.VERSION or
            lock.get("version") != builder.VERSION or
            lock.get("packages", {}).get("", {}).get("version") != builder.VERSION):
        raise ValueError("Package and lock root versions must all be 1.0.22")
    tree = ast.parse(updater_path.read_text(encoding="utf-8"))
    versions = [node.value.value for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "CURRENT_VERSION"
                        for target in node.targets)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)]
    if versions != [builder.VERSION]:
        raise ValueError("madar_update.CURRENT_VERSION must be 1.0.22")
    if "scripts/build_integrated_v122.py" not in package.get("scripts", {}).get("dist:rc", ""):
        raise ValueError("Default installer builder must use v1.0.22 wrapper")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def has_pe_header(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(2) == b"MZ"


def source_git_commit(root: Path) -> str:
    """Pin the exact committed release input, not a dirty working snapshot.

    This is a source identity gate; it does NOT attest deterministic compilers.
    """
    try:
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1",
             "--untracked-files=normal"],
            check=True, capture_output=True, text=True, encoding="utf-8")
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            check=True, capture_output=True, text=True, encoding="utf-8")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Cannot establish a clean committed release source") from exc
    if status.stdout.strip():
        raise RuntimeError("Release source has uncommitted or untracked files")
    sha = head.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("Release source commit is not a full Git SHA-1")
    return sha


def release_descriptor(source_commit: str) -> dict:
    """Record digests for *all three* byte artifacts, including the QA binary."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("A committed source revision is required")
    return {
        "schema": 2,
        "version": builder.VERSION,
        "sourceGitCommit": source_commit,
        "asset": builder.PROD.name,
        "installerSha256": digest(builder.PROD),
        "installerBytes": builder.PROD.stat().st_size,
        "qaInstaller": builder.QA.name,
        "qaInstallerSha256": digest(builder.QA),
        "qaInstallerBytes": builder.QA.stat().st_size,
        "application": builder.PROGRAM.name,
        "applicationSha256": digest(builder.PROGRAM),
        "applicationBytes": builder.PROGRAM.stat().st_size,
        "webview2PrerequisiteSha256": digest(builder.PREREQ),
        "cumulativeFrom": ["1.0.5", "1.0.6", "1.0.7", "1.0.8", "1.0.9",
                           "1.0.10", "1.0.11", "1.0.12", "1.0.13", "1.0.14", "1.0.15", "1.0.16", "1.0.17", "1.0.18", "1.0.19", "1.0.20", "1.0.21"],
        "profileMigration": "none; preserve all task, company accounting and Parsian test data",
    }


def verify_release_descriptor(descriptor: dict, *, source_commit: str | None = None) -> None:
    """Fail closed before launching *either* QA binary.

    SHA256 comparison demonstrates identity against the recorded manifest,
    not independent publisher authenticity or deterministic rebuilds.
    """
    if not isinstance(descriptor, dict) or descriptor.get("schema") != 2 or \
            descriptor.get("version") != "1.0.22":
        raise RuntimeError("Unsupported or stale integrated release descriptor")
    if descriptor.get("sourceGitCommit") is None or not re.fullmatch(
            r"[0-9a-f]{40}", str(descriptor["sourceGitCommit"])):
        raise RuntimeError("Missing committed build-source identity")
    if source_commit is not None and descriptor["sourceGitCommit"] != source_commit:
        raise RuntimeError("QA source revision differs from release build source")
    if descriptor.get("cumulativeFrom", [])[-1:] != ["1.0.21"]:
        raise RuntimeError("1.0.21 upgrade is absent from cumulative release scope")

    for target, name_key, digest_key, size_key in (
            (builder.PROGRAM, "application", "applicationSha256", "applicationBytes"),
            (builder.QA, "qaInstaller", "qaInstallerSha256", "qaInstallerBytes"),
            (builder.PROD, "asset", "installerSha256", "installerBytes")):
        expected_hash = descriptor.get(digest_key)
        if (descriptor.get(name_key) != target.name or
                type(descriptor.get(size_key)) is not int or
                descriptor[size_key] < 2 or
                not isinstance(expected_hash, str) or
                not re.fullmatch(r"[0-9a-f]{64}", expected_hash)):
            raise RuntimeError("Invalid release artifact identity: " + target.name)
        if not target.is_file() or target.stat().st_size != descriptor[size_key] or \
                digest(target) != expected_hash or not has_pe_header(target):
            raise RuntimeError("Release artifact failed SHA256/size/PE check: " + target.name)

    if descriptor["installerSha256"] == descriptor["qaInstallerSha256"]:
        raise RuntimeError("QA and production installers must be distinct")
    prerequisite_hash = descriptor.get("webview2PrerequisiteSha256")
    if (not isinstance(prerequisite_hash, str) or
            not re.fullmatch(r"[0-9a-f]{64}", prerequisite_hash) or
            not builder.PREREQ.is_file() or digest(builder.PREREQ) != prerequisite_hash):
        raise RuntimeError("Signed WebView2 prerequisite differs from build input")


def read_verified_release_descriptor(*, check_source: bool = True) -> dict:
    if not MANIFEST.is_file():
        raise FileNotFoundError("Integrated 1.0.22 release descriptor missing")
    descriptor = json.loads(MANIFEST.read_text(encoding="utf-8"))
    verify_release_descriptor(descriptor, source_commit=(
        source_git_commit(builder.ROOT) if check_source else None))
    return descriptor


def main() -> None:
    validate_source_metadata(builder.ROOT / "package.json",
                             builder.ROOT / "madar_update.py",
                             builder.ROOT / "package-lock.json")
    if builder.PROD.name != "Madar-Desk-1.0.22-Setup.exe":
        raise RuntimeError("Updater expects exact 1.0.22 setup filename")
    if any(path.exists() for path in (
            builder.PROGRAM, builder.QA, builder.PROD, MANIFEST, QA_ACCEPTANCE,
            *artifact_sidecars())):
        raise FileExistsError("Immutable 1.0.22 release artifact already exists")
    source_commit = source_git_commit(builder.ROOT)
    builder.main()  # Signed WebView2 prerequisite and fixed installer preflight.
    # npm's font-license synchronization may change only the working-tree
    # timestamps even when its bytes are identical to the committed content.
    # Verify exact Git content equality before refreshing metadata. Never
    # stage, replace, or silently ignore an actual font-license change.
    fonts = ["public/fonts/Estedad-OFL.txt", "public/fonts/OFL.txt"]
    subprocess.run(["git", "-C", str(builder.ROOT), "diff", "--exit-code",
                    "--", *fonts], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(builder.ROOT), "update-index",
                    "--refresh", "--", *fonts], check=False,
                   capture_output=True)
    if not all(path.is_file() for path in (builder.PROGRAM, builder.QA, builder.PROD)):
        raise RuntimeError("Complete cumulative Windows application and installers required")
    if source_git_commit(builder.ROOT) != source_commit:
        raise RuntimeError("Release source changed during packaging")
    descriptor = release_descriptor(source_commit)
    verify_release_descriptor(descriptor, source_commit=source_commit)
    with MANIFEST.open("x", encoding="utf-8") as output:
        json.dump(descriptor, output, indent=2, ensure_ascii=False)
        output.write("\n")
    print("CUMULATIVE_121_PREPARED_NOT_INSTALLED", MANIFEST, flush=True)


if __name__ == "__main__":
    main()
