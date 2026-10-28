"""Build an immutable, per-user Windows Madar distribution from an existing EXE.

This assembles files only under the ignored release/ directory. It never
installs, starts, stops or modifies a real user's running application/data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
VERSION = "1.0.0"
STAMP = "20261028"
NAME = "Madar-Desk-v1.0.0-Customer-20261028"
SOURCE_EXE = RELEASE / (NAME + ".exe")
PACKAGE = RELEASE / NAME
ARCHIVE = RELEASE / (NAME + ".zip")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    if not SOURCE_EXE.is_file():
        raise RuntimeError("Windows build missing: " + str(SOURCE_EXE))
    if PACKAGE.exists() or ARCHIVE.exists():
        raise FileExistsError("Existing customer package is immutable. Refusing overwrite.")
    if json.loads((ROOT / "package.json").read_text(encoding="utf8"))["version"] != VERSION:
        raise RuntimeError("Package version and customer executable version differ")

    sources = {
        SOURCE_EXE.name: SOURCE_EXE,
        "Install-Madar-Customer.ps1": ROOT / "scripts" / "Install-Madar-Customer.ps1",
        "Create-Madar-Issue-Report.ps1": ROOT / "scripts" / "Create-Madar-Issue-Report.ps1",
        "Madar-Customer-Guide.md": ROOT / "docs" / "MADAR_CUSTOMER_RELEASE.md",
    }
    for name, source in sources.items():
        if not source.is_file():
            raise FileNotFoundError("Cannot package missing component: " + str(source))

    exe_hash = sha256(SOURCE_EXE)
    PACKAGE.mkdir(parents=True)
    try:
        for name, source in sources.items():
            shutil.copy2(source, PACKAGE / name)
        # This package has a single entrypoint for a user who does not know PS.
        (PACKAGE / "Install-Madar.cmd").write_bytes(
            ("@echo off\r\n"
             "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%~dp0Install-Madar-Customer.ps1\"\r\n"
             "if errorlevel 1 (\r\n"
             "  echo Installation was stopped. Madar data was not replaced.\r\n"
             "  pause\r\n"
             "  exit /b 1\r\n"
             ")\r\n"
             "echo Madar is installed. Use the Madar shortcut from Start Menu.\r\n"
             "pause\r\n").encode("ascii")
        )
        (PACKAGE / "START-HERE.txt").write_text(
            "مدار | نسخه 1.0.0 برای استفادهٔ کاربر\n"
            "\n"
            "۱) فایل ZIP را کاملاً از حالت فشرده خارج کنید.\n"
            "۲) همه پنجره‌های مدار و سرویس MadarHost را ببندید.\n"
            "۳) فایل Install-Madar.cmd را اجرا کنید. اگر خطایی نمایش داده شد، نصب متوقف شده است.\n"
            "۴) برنامه را از منوی Start ویندوز با نام «مدار» اجرا کنید.\n"
            "۵) داده‌های اصلی به طور پیش‌فرض در %APPDATA%\\MadarDesk باقی می‌مانند.\n"
            "۶) هنگام نصب روی دادهٔ موجود، قبل از سوییچ نسخه بکاپ جداگانه ساخته می‌شود.\n"
            "۷) داده‌های پوشه آزمایشی قدیمی Madar-UserTest-Data خودکار منتقل نمی‌شوند.\n"
            "۸) برای گزارش مشکل، راهنمای Madar-Customer-Guide.md را بخوانید.\n"
            "\n"
            "پیش‌نیاز اجرا: Microsoft Edge WebView2 Runtime. فایل اجرایی امضای دیجیتال ندارد.\n"
            "ارتقای خودکار و ارسال خودکار گزارش خطا در این بسته فعال نیست.\n",
            encoding="utf8",
        )
        info = {
            "product": "Madar Desk", "version": VERSION,
            "executable": SOURCE_EXE.name, "sha256": exe_hash,
            "releaseDate": "2026-10-28",
            "delivery": "per-user opt-in install, immutable binary version",
            "signature": "unsigned",
            "otherFilesSha256": {
                name: sha256(PACKAGE / name) for name in sources if name != SOURCE_EXE.name
            },
        }
        (PACKAGE / "Madar-Release-Manifest.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        with ZipFile(ARCHIVE, "x", compression=ZIP_DEFLATED, compresslevel=9) as zipped:
            for file in sorted(PACKAGE.iterdir()):
                zipped.write(file, file.name)
        with ZipFile(ARCHIVE) as zipped:
            if zipped.testzip() is not None:
                raise RuntimeError("Release archive integrity test failed")
            if len(zipped.namelist()) != len(list(PACKAGE.iterdir())):
                raise RuntimeError("Release archive has missing files")
        (RELEASE / (NAME + ".sha256.txt")).write_text(
            f"{sha256(ARCHIVE)}  {ARCHIVE.name}\n", encoding="ascii")
        print("PACKAGE:", ARCHIVE)
        print("EXE_SHA256:", exe_hash)
        print("ZIP_SHA256:", sha256(ARCHIVE))
        print("PACKAGE_FILES:", len(list(PACKAGE.iterdir())))
    except Exception:
        # Do not delete any partial package; it is evidence for a failed build.
        raise


if __name__ == "__main__":
    main()
