"""Build Inno Setup 1.0.2 offline EXE and an isolated QA variant.

Read-only with respect to operational APPDATA; creates artifacts only in
release/. Does NOT sign, install, delete user data or publish the result.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
APP = RELEASE / "Madar-Desk-v1.0.2-Update-20261101.exe"
SCRIPT = ROOT / "scripts" / "madar-update.iss"
ISCC = Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe"
OLD_BUNDLE = RELEASE / "Madar-Suite-Setup-20261024.zip"
PREREQ = RELEASE / ".madar-inno-prereq" / "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
SOURCE_MEMBER = "Madar-Suite-Setup-20261024/Prerequisites/MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
PROD = RELEASE / "Madar-Setup-v1.0.2-Update-20261101-Fix1.exe"
QA = RELEASE / "Madar-Setup-v1.0.2-QA-Fix1.exe"
QA_ROOT = ROOT / ".qa-inno-v102-update-20261101"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blob in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blob)
    return h.hexdigest()


def ensure_prerequisite():
    if not PREREQ.exists():
        PREREQ.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(OLD_BUNDLE) as archive, archive.open(SOURCE_MEMBER) as source, PREREQ.open("xb") as out:
            import shutil
            shutil.copyfileobj(source, out, 1024 * 1024)
    # Trust store and publisher checks, not just matching a checksum from
    # an arbitrary preexisting archive.
    verify = (
        "$s=Get-AuthenticodeSignature -LiteralPath '" + str(PREREQ) + "';"
        "if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Microsoft Corporation')"
        "{throw 'WebView2 runtime publisher signature is not valid.'}"
    )
    # Re-check the signer even when the prerequisite was cached on disk.
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", verify], check=True, cwd=ROOT)


def compile_one(args: list[str], expected: Path):
    if expected.exists():
        raise FileExistsError("Immutable output already exists: " + str(expected))
    subprocess.run([str(ISCC), "/Qp", *args, str(SCRIPT)], check=True, cwd=ROOT)
    if not expected.is_file():
        raise RuntimeError("Compiler reported success, but installer not found: " + str(expected))
    with expected.open("rb") as f:
        if f.read(2) != b"MZ":
            raise RuntimeError("Unexpected Windows executable header")
    (RELEASE / (expected.name + ".sha256.txt")).write_text(
        digest(expected) + "  " + expected.name + "\n", encoding="ascii"
    )
    print("BUILT", expected, expected.stat().st_size, digest(expected), flush=True)


def main():
    if not ISCC.exists() or not APP.is_file():
        raise RuntimeError("Inno compiler or actual 1.0.2 program build missing")
    if json.loads((ROOT / "package.json").read_text(encoding="utf8"))["version"] != "1.0.2":
        raise RuntimeError("Package version is not 1.0.2")
    ensure_prerequisite()
    expected_sha = digest(APP)
    if not QA_ROOT.exists():
        QA_ROOT.mkdir()
    if QA.exists() or PROD.exists():
        raise FileExistsError("Existing version-specific installer; refusing overwrite")
    compile_one(["/DQA", "/DQA_ROOT=" + str(QA_ROOT), "/DEXE_SHA256=" + expected_sha], QA)
    compile_one(["/DEXE_SHA256=" + expected_sha], PROD)


if __name__ == "__main__":
    main()
