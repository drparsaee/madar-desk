"""Immutable 1.0.4 Inno hotfix. Reuse the previously verified application EXE.

Only the embedded PowerShell preflight script changed. The application EXE is
unchanged and was built/tested by the preceding 1.0.4 Logo1 release. This
script refuses to overwrite any prior production, QA, or packaged release.
"""
from pathlib import Path
from hashlib import sha256
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
PROGRAM = RELEASE / "Madar-Desk-v1.0.4-RC-20261102-Logo1.exe"
PROGRAM_SHA = "6963ad4440e56f0a662c670aa84cb626c7c22be9b135b0a05c34916c65635c60"
NAME = "Madar-Desk-1.0.4-Setup-Fix2"
INSTALLER = RELEASE / (NAME + ".exe")
QA = RELEASE / (NAME + "-QA.exe")
QA_FRESH = RELEASE / (NAME + "-QA-Fresh.exe")
QA_ROOT = ROOT / ".qa-inno-v104-selfdetect-fix2"
QA_FRESH_ROOT = ROOT / ".qa-inno-v104-selfdetect-fix2-fresh"
ISCC = Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe"
PREREQ = RELEASE / ".madar-inno-prereq" / "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"


def sha(path):
    h = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def compile_setup(path, qa=False, root=None):
    defines = [
        "/DMadarVersion=1.0.4",
        "/DExeFile=" + PROGRAM.name,
        "/DRCOutputBase=" + path.stem,
        "/DEXE_SHA256=" + PROGRAM_SHA,
    ]
    if qa:
        defines += ["/DQA", "/DQA_ROOT=" + str(root)]
    subprocess.run([str(ISCC), "/Qp", *defines,
                    str(ROOT / "scripts" / "madar-update.iss")], cwd=ROOT, check=True)
    if not path.is_file() or path.open("rb").read(2) != b"MZ":
        raise RuntimeError("Inno output missing/not PE: " + str(path))
    print("BUILT", path.name, path.stat().st_size, sha(path), flush=True)


def main():
    expected = (INSTALLER, QA, QA_FRESH, QA_ROOT, QA_FRESH_ROOT)
    if any(path.exists() for path in expected):
        raise FileExistsError("Hotfix is immutable; at least one output already exists")
    if not (PROGRAM.is_file() and PREREQ.is_file() and ISCC.is_file()):
        raise FileNotFoundError("Previously verified EXE, WebView2, or Inno not present")
    if sha(PROGRAM) != PROGRAM_SHA:
        raise RuntimeError("Refusing to use an unverified application EXE")
    # Reverify the upstream signed WebView2 prerequisite.
    from build_p0_release_candidate import verify_microsoft_signature
    verify_microsoft_signature(PREREQ)
    QA_ROOT.mkdir()
    QA_FRESH_ROOT.mkdir()
    compile_setup(QA, qa=True, root=QA_ROOT)
    compile_setup(QA_FRESH, qa=True, root=QA_FRESH_ROOT)
    compile_setup(INSTALLER)
    print("FIX2_PREPARED_PRODUCTION_NOT_INSTALLED", flush=True)


if __name__ == "__main__":
    main()
