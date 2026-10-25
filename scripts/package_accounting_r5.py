"""Assemble a NEW, hash-checked R5 Windows package; never overwrite R2/R3/R4.

Uses the previously audited no-overwrite PowerShell 5.1 installer logic, with
strictly versioned names/locations and a dedicated offline-recovery shortcut.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release" / "Madar-Suite-Accounting-R5-20261025"
OLD = ROOT / "release" / "Madar-Suite-Operations-R2-20261025"
BINARIES = {
    "madarSha256": (ROOT / "release" / "Madar-Desk-Fixes-R5-20261025.exe", "Madar-Desk-R5.exe"),
    "accountingSha256": (ROOT / "release" / "Madar-Accounting-Fixes-R5-20261025.exe", "Madar-Accounting-R5.exe"),
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for data in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest().upper()


def substitute(script, old, new, count=None):
    found = script.count(old)
    if not found or count is not None and found != count:
        raise RuntimeError(f"Installer template mismatch: {old!r} appears {found} times")
    return script.replace(old, new)


def main():
    if OUT.exists():
        raise FileExistsError("R5 package folder already exists; refusing overwrite")
    for original, _ in BINARIES.values():
        if not original.is_file():
            raise FileNotFoundError(original)
    prerequisite = OLD / "Prerequisites" / "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
    if not prerequisite.is_file():
        raise FileNotFoundError("Bundled signed WebView2 prerequisite missing")
    template = (OLD / "Setup.ps1").read_text(encoding="utf-8-sig")
    script = substitute(template, "Madar-Desk.exe", "Madar-Desk-R5.exe")
    script = substitute(script, "Madar-Accounting.exe", "Madar-Accounting-R5.exe")
    script = substitute(script, "Programs\\Madar Suite'", "Programs\\Madar Suite R5'")
    script = substitute(script, "'Madar Suite'", "'Madar Suite R5'")
    script = substitute(script, "'Madar Suite Data'", "'Madar Suite Data R5'")
    shortcut = (
        "        @{filename='مدار - حسابداری مستقل.lnk';target=$installed2;\n"
        "          args=('--data-dir \"'+$accountingData+'\"');icon=$installed2}"
    )
    new_shortcut = (
        "        @{filename='مدار R5 - حسابداری مستقل.lnk';target=$installed2;\n"
        "          args=('--data-dir \"'+$accountingData+'\"');icon=$installed2},\n"
        "        @{filename='مدار R5 - بازیابی آفلاین حسابداری.lnk';target=$installed2;\n"
        "          args=('--recovery --data-dir \"'+$accountingData+'\"');icon=$installed2}"
    )
    script = substitute(script, shortcut, new_shortcut, count=1)
    script = substitute(script, "filename='مدار - مدیریت کارها.lnk'",
                        "filename='مدار R5 - مدیریت کارها.lnk'", count=1)
    out_apps, out_pre = OUT / "Apps", OUT / "Prerequisites"
    try:
        out_apps.mkdir(parents=True)
        out_pre.mkdir()
        hashes = {}
        for key, (original, target) in BINARIES.items():
            destination = out_apps / target
            shutil.copy2(original, destination)
            hashes[key] = digest(destination)
            if hashes[key] != digest(original):
                raise RuntimeError("Source/destination hash differs: " + target)
        copied_pre = out_pre / prerequisite.name
        shutil.copy2(prerequisite, copied_pre)
        pre_hash = digest(copied_pre)
        old_manifest = json.loads((OLD / "manifest.json").read_text(encoding="utf-8-sig"))
        if pre_hash != old_manifest["prerequisites"]["webview2Sha256"].upper():
            raise RuntimeError("WebView2 installer differs from prior signed package")
        manifest = {
            "package": "Madar-Suite-Windows-x64", "schema": 1,
            "version": "R5-20261025", "createdUtc": datetime.now(timezone.utc).isoformat(),
            "apps": hashes,
            "prerequisites": {**old_manifest["prerequisites"],
                              "webview2Sha256": pre_hash},
            "appCapabilities": {"standaloneAccounting": True,
                                "accountingRecoveryUI": True,
                                "recoveryArgument": "--recovery",
                                "financeEditorExplicitACL": True,
                                "partialCreditNote": True},
            "noProductionAcceptance": ["Parsian SQL restore", "legal tax submission",
                                       "second physical Windows host", "real accountant sign-off"],
        }
        (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False,
                                                      indent=2) + "\n", encoding="utf-8")
        (OUT / "Setup.ps1").write_text(script, encoding="utf-8-sig")
        shutil.copy2(OLD / "INSTALL.cmd", OUT / "INSTALL.cmd")
        (OUT / "README-FA.txt").write_text(
            "نسخه آزمایشی R5 مدار و حسابداری مستقل. نصب فقط در پوشه مستقل جدید انجام شود.\n"
            "با فایل INSTALL.cmd شروع کنید. نسخه‌های قدیمی بازنویسی نمی‌شوند.\n"
            "سه میانبر: مدیریت کارها، حسابداری مستقل، بازیابی آفلاین حسابداری.\n"
            "هنگام بازیابی همه برنامه‌ها را ببندید؛ مقصد باید تازه و خالی باشد.\n"
            "داده و نسخه پشتیبان مالی بدون رمزنگاری هستند. اطلاعات واقعی و مهاجرت پارسیان\n"
            "بدون بررسی و تأیید حسابدار به این نسخه وارد نشود.\n",
            encoding="utf-8")
    except BaseException:
        # Never clean up any preexisting directory, only a newly created R5 output.
        if OUT.exists():
            shutil.rmtree(OUT)
        raise
    print(json.dumps({"package": str(OUT), "hashes": hashes,
                      "prerequisiteSha256": pre_hash}, indent=2))


if __name__ == "__main__":
    sys.exit(main())
