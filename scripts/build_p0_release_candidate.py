"""Create distinct versioned Madar 1.0.3 RC binaries; never install them.

Inputs must already be local. The WebView prerequisite must have a valid
Microsoft Authenticode signature. Production and QA setup outputs are
immutable: existing files fail instead of being overwritten.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
VERSION = "1.0.3"
LABEL = "20261102"
PROGRAM = RELEASE / f"Madar-Desk-v{VERSION}-RC-{LABEL}.exe"
QA = RELEASE / f"Madar-Setup-v{VERSION}-RC-{LABEL}-QA.exe"
PROD = RELEASE / f"Madar-Setup-v{VERSION}-RC-{LABEL}.exe"
QA_ROOT = ROOT / f".qa-inno-v{VERSION.replace('.', '')}-{LABEL}"
ISCC = Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe"
PREREQ = RELEASE / ".madar-inno-prereq" / "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return sha256(handle.read()).hexdigest()


def verify_microsoft_signature(path: Path):
    code = ("$s=Get-AuthenticodeSignature -LiteralPath '" +
            str(path).replace("'", "''") + "'; " +
            "if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject " +
            "-notmatch '(^|, )O=Microsoft Corporation(,|$)') " +
            "{throw 'Invalid Microsoft-signed WebView2 prerequisite'}")
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                    "-Command", code], check=True, cwd=ROOT)


def compile_setup(*, qa: bool, program_hash: str):
    name = QA if qa else PROD
    if name.exists():
        raise FileExistsError("Refusing to overwrite versioned setup: " + str(name))
    defines = ["/DMadarVersion=" + VERSION, "/DExeFile=" + PROGRAM.name,
               "/DRCOutputBase=" + name.stem,
               "/DEXE_SHA256=" + program_hash]
    if qa:
        defines.extend(["/DQA", "/DQA_ROOT=" + str(QA_ROOT)])
    subprocess.run([str(ISCC), "/Qp", *defines,
                    str(ROOT / "scripts" / "madar-update.iss")],
                   cwd=ROOT, check=True)
    if not name.is_file() or name.open("rb").read(2) != b"MZ":
        raise RuntimeError("Invalid or missing compiled Windows installer")
    (RELEASE / (name.name + ".sha256.txt")).write_text(
        digest(name) + "  " + name.name + "\n", encoding="ascii")
    print("SETUP_VERIFIED", name, name.stat().st_size, digest(name), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--webview2", type=Path, required=True,
                        help="Existing locally available Microsoft-signed offline installer")
    args = parser.parse_args()
    if json.loads((ROOT / "package.json").read_text(encoding="utf8"))["version"] != VERSION:
        raise RuntimeError("The source package version and RC version disagree")
    if not ISCC.is_file() or not args.webview2.is_file():
        raise FileNotFoundError("Inno Setup compiler or offline WebView2 prerequisite missing")
    if PROGRAM.exists() or QA.exists() or PROD.exists():
        raise FileExistsError("RC outputs are immutable; refusing overwrite")
    verify_microsoft_signature(args.webview2)
    RELEASE.mkdir(parents=True, exist_ok=True)
    PREREQ.parent.mkdir(parents=True, exist_ok=True)
    if not PREREQ.exists():
        shutil.copy2(args.webview2, PREREQ)
    if digest(PREREQ) != digest(args.webview2):
        raise RuntimeError("Prerequisite did not copy byte-for-byte")
    verify_microsoft_signature(PREREQ)
    subprocess.run(["npm.cmd", "run", "build"], check=True, cwd=ROOT)
    subprocess.run(["python", "-m", "PyInstaller", "--noconfirm",
                    "--onefile", "--windowed", "--name", PROGRAM.stem,
                    "--icon", str(ROOT / "assets" / "madar.ico"),
                    "--distpath", str(RELEASE),
                    "--workpath", str(ROOT / ".qa-p0-pyinstaller" / "work"),
                    "--specpath", str(ROOT / ".qa-p0-pyinstaller"),
                    "--add-data", str(ROOT / "dist") + ";dist", "native_app.py"],
                   check=True, cwd=ROOT)
    if not PROGRAM.is_file() or PROGRAM.open("rb").read(2) != b"MZ":
        raise RuntimeError("PyInstaller binary missing or not a Windows PE")
    program_hash = digest(PROGRAM)
    (RELEASE / (PROGRAM.name + ".sha256.txt")).write_text(
        program_hash + "  " + PROGRAM.name + "\n", encoding="ascii")
    print("PROGRAM_VERIFIED", PROGRAM, PROGRAM.stat().st_size,
          program_hash, flush=True)
    QA_ROOT.mkdir(parents=True, exist_ok=True)
    compile_setup(qa=True, program_hash=program_hash)
    compile_setup(qa=False, program_hash=program_hash)
    print("RC_PREPARED_NOT_INSTALLED", flush=True)


if __name__ == "__main__":
    main()
