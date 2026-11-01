"""Require a trusted Windows Authenticode signature for public distribution.

Build QA may be unsigned. Passing this gate is mandatory before describing an
installer as a signed, public, SmartScreen-ready release. It never signs files
or bypasses Defender / SmartScreen.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--require-signed", action="store_true")
    args = parser.parse_args()
    path = args.file.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    check = (
        "$s=Get-AuthenticodeSignature -LiteralPath '" +
        str(path).replace("'", "''") + "'; "
        "Write-Output ('SIGNATURE_STATUS='+$s.Status); "
        "if($s.SignerCertificate){Write-Output ('SIGNER='+$s.SignerCertificate.Subject)}; "
        "if($s.Status -ne 'Valid'){exit 3}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", check],
        capture_output=True, text=True, timeout=30)
    print(result.stdout.strip() or result.stderr.strip())
    if args.require_signed and result.returncode != 0:
        raise SystemExit("BLOCKED: Unsigned/invalid release is not approved for public distribution.")


if __name__ == "__main__":
    main()
