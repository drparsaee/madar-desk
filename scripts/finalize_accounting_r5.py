"""No-clobber ZIP publication and independent hash readback for tested R5.

The package is intended as a synthetic-only candidate, NOT a production
accounting/legal migration authorization. Never replaces another ZIP or EXE.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "release" / "Madar-Suite-Accounting-R5-20261025"
ZIP = ROOT / "release" / (PACKAGE.name + ".zip")


def digest_bytes(source):
    h = hashlib.sha256()
    while chunk := source.read(1024*1024):
        h.update(chunk)
    return h.hexdigest().upper()


def main():
    if ZIP.exists():
        raise FileExistsError("R5 archive exists, refusing replacement: " + str(ZIP))
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    targets = {"Apps/Madar-Desk-R5.exe": manifest["apps"]["madarSha256"],
               "Apps/Madar-Accounting-R5.exe": manifest["apps"]["accountingSha256"],
               "Prerequisites/MicrosoftEdgeWebView2RuntimeInstallerX64.exe":
                   manifest["prerequisites"]["webview2Sha256"]}
    files = sorted(p for p in PACKAGE.rglob("*") if p.is_file())
    if len(files) != 7:
        raise RuntimeError("Unexpected package member count: " + str(len(files)))
    for relative, expected in targets.items():
        with (PACKAGE / relative).open("rb") as source:
            if digest_bytes(source) != expected.upper():
                raise RuntimeError("Untrusted file before zipping: " + relative)
    temporary = None
    published = False
    try:
        with NamedTemporaryFile(prefix=".r5-zip-stage-", suffix=".zip",
                               dir=str(ZIP.parent), delete=False) as tmp:
            temporary = Path(tmp.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED,
                             allowZip64=True) as archive:
            for f in files:
                archive.write(f, arcname=PACKAGE.name + "/" + f.relative_to(PACKAGE).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            errors = archive.testzip()
            if errors:
                raise RuntimeError("Zip CRC mismatch: " + errors)
            names = archive.namelist()
            for relative, expected in targets.items():
                with archive.open(PACKAGE.name + "/" + relative) as stream:
                    if digest_bytes(stream) != expected.upper():
                        raise RuntimeError("ZIP readback mismatch: " + relative)
            if len(names) != len(files):
                raise RuntimeError("ZIP has unexpected members")
        with temporary.open("rb") as stream:
            zip_hash = digest_bytes(stream)
        # Atomic publishing without overwriting any existing R5 archive.
        os.link(temporary, ZIP)
        published = True
        print(json.dumps({"zip": str(ZIP), "size": ZIP.stat().st_size,
                          "sha256": zip_hash, "members": len(files),
                          "zip_crc_and_payload_hash_verified": True}, indent=2))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if not published and ZIP.exists():
            # The script must not erase a race-created destination.
            pass


if __name__ == "__main__":
    sys.exit(main())
