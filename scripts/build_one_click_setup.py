"""Build one-click offline setup EXE using Windows in-box .NET C# compiler.

One executable with an appended ZIP; no external Python/Node/installer needed
on the customer PC. Never installs anything on the build computer.
"""
from pathlib import Path
import hashlib
import shutil
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
BASE = "Madar-Desk-v1.0.1-Customer-20261028-InstallerFix1"
SOURCE = RELEASE / BASE
SETUP = RELEASE / "Madar-Setup-v1.0.1-Offline-20261028.exe"
PRE_REQ = RELEASE / "Madar-Suite-Setup-20261024.zip"
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
RUNTIME_NAME = "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
RUNTIME_IN_ARCHIVE = "Madar-Suite-Setup-20261024/Prerequisites/" + RUNTIME_NAME

def main():
    if SETUP.exists():
        raise FileExistsError("Single-file offline setup is immutable; do not overwrite it")
    if not CSC.is_file() or not PRE_REQ.is_file():
        raise RuntimeError("Windows compiler or archived offline prerequisite missing")
    command = [
        str(CSC), "/nologo", "/target:winexe", "/optimize+",
        "/out:" + str(SETUP),
        "/reference:System.Windows.Forms.dll",
        "/reference:System.Drawing.dll",
        "/reference:System.IO.Compression.dll",
        "/reference:System.IO.Compression.FileSystem.dll",
        str(ROOT / "scripts" / "MadarOneClickSetup.cs"),
    ]
    subprocess.run(command, check=True, cwd=ROOT)
    parts = [
        "Madar-Desk-v1.0.1-Customer-20261028.exe",
        "Install-Madar-Customer.ps1",
        "Madar-Release-Manifest.json",
    ]
    try:
        with ZipFile(SETUP, "a", compression=ZIP_STORED, allowZip64=True) as bundled:
            for part in parts:
                bundled.write(SOURCE / part, arcname=part)
            with ZipFile(PRE_REQ, "r") as external, external.open(RUNTIME_IN_ARCHIVE) as data:
                with bundled.open(RUNTIME_NAME, "w", force_zip64=True) as out:
                    shutil.copyfileobj(data, out, length=1024 * 1024)
        with ZipFile(SETUP) as zipfile:
            names = set(zipfile.namelist())
            assert names == set(parts) | {RUNTIME_NAME}, names
            assert zipfile.testzip() is None
        digest = hashlib.file_digest(SETUP.open("rb"), "sha256").hexdigest()
        (RELEASE / (SETUP.name + ".sha256.txt")).write_text(
            digest + "  " + SETUP.name + "\n", encoding="ascii")
        print("SETUP_READY", SETUP)
        print("BYTES", SETUP.stat().st_size)
        print("SHA256", digest)
    except Exception:
        raise

if __name__ == "__main__":
    main()
