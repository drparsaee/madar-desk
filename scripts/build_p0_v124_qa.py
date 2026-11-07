"""Build an immutable, isolated Madar 1.0.24 P0 candidate, never install it.

Run only in feat/madar-v124-p0-rc-20261107 after committing every source
change. Outputs are full Windows PE/QA Inno/production Inno *candidates*,
not a signed public release. Existing 1.0.23 files remain untouched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import build_p0_release_candidate as builder

VERSION = "1.0.24"
LABEL = "20261107-P0"
builder.VERSION = VERSION
builder.LABEL = LABEL
builder.PROGRAM = builder.RELEASE / f"Madar-Desk-v{VERSION}-P0-{LABEL}.exe"
builder.QA = builder.RELEASE / f"Madar-Desk-{VERSION}-P0-Setup-QA.exe"
builder.PROD = builder.RELEASE / f"Madar-Desk-{VERSION}-P0-Setup.exe"
builder.QA_ROOT = builder.ROOT / ".qa-inno-v124-p0-20261107"
MANIFEST = builder.RELEASE / "Madar-Desk-1.0.24-P0-Candidate.json"


def _clean_commit():
    status = subprocess.run(["git", "status", "--porcelain=v1"], cwd=builder.ROOT,
                            capture_output=True, text=True, encoding="utf8", check=True)
    if status.stdout.strip():
        raise RuntimeError("Candidate source is not committed or clean")
    sha = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=builder.ROOT,
                         capture_output=True, text=True, encoding="ascii", check=True).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("Invalid candidate source identity")
    return sha


def _digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _preflight():
    pkg = json.loads((builder.ROOT / "package.json").read_text(encoding="utf8"))
    lock = json.loads((builder.ROOT / "package-lock.json").read_text(encoding="utf8"))
    if any(value != VERSION for value in (
            pkg["version"], lock["version"], lock["packages"][""]["version"])):
        raise RuntimeError("Package/lock versions do not all match 1.0.24")
    update = (builder.ROOT / "madar_update.py").read_text(encoding="utf8")
    if 'CURRENT_VERSION = "1.0.24"' not in update:
        raise RuntimeError("Updater version differs from candidate")
    if not pkg.get("scripts", {}).get("dist:rc", "").startswith(
            "python -B scripts/build_p0_v124_qa.py"):
        raise RuntimeError("Default candidate build command is not explicit")
    if MANIFEST.exists() or any(item.exists() for item in
                                (builder.PROGRAM,builder.QA,builder.PROD)):
        raise FileExistsError("Candidate outputs are immutable; refusing rebuild/overwrite")


def main():
    _preflight()
    source_commit = _clean_commit()
    builder.main()
    # Built fonts may regenerate same bytes with modified timestamps.
    for name in ("public/fonts/Estedad-OFL.txt", "public/fonts/OFL.txt"):
        checked = subprocess.run(["git", "diff", "--exit-code", "--", name],
                                 cwd=builder.ROOT, capture_output=True)
        if checked.returncode:
            raise RuntimeError("Build changed the committed font license: " + name)
        subprocess.run(["git", "update-index", "--refresh", "--", name],
                       cwd=builder.ROOT, capture_output=True)
    if _clean_commit() != source_commit:
        raise RuntimeError("Candidate source changed during build")
    outputs = {}
    for label, path in (("app", builder.PROGRAM), ("qaInstaller", builder.QA),
                        ("candidateInstaller", builder.PROD)):
        if not path.is_file() or path.open("rb").read(2) != b"MZ":
            raise RuntimeError(label + " output is not a Windows PE")
        outputs[label] = {"name": path.name, "bytes": path.stat().st_size,
                          "sha256": _digest(path)}
    receipt = {"schema": 1, "version": VERSION, "label": LABEL,
               "sourceGitCommit": source_commit,
               "classification": "unsigned-local-QA-candidate-not-published",
               "outputs": outputs}
    with MANIFEST.open("x", encoding="utf8") as dest:
        json.dump(receipt, dest, ensure_ascii=False, indent=2)
        dest.write("\n")
    print("P0_V124_CANDIDATE_BUILT_NOT_INSTALLED " + str(MANIFEST), flush=True)


if __name__ == "__main__":
    main()
