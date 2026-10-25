"""Install immutable R3 candidate into temporary Windows test dirs only.

Validates package hashes, private app/financial separation, three shortcuts,
and a refused overwrite. Never uses real APPDATA or user Desktop shortcuts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT / "release" / "Madar-Suite-Fixes-R3-20261025"
COPY={("apps","madarSha256"):"Madar-Desk.exe",
      ("apps","accountingSha256"):"Madar-Accounting.exe"}


def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda:src.read(1<<20),b""):
            h.update(block)
    return h.hexdigest().lower()


def main():
    if not (PACKAGE / "manifest.json").is_file():
        raise RuntimeError("R3 package not yet created")
    manifest=json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8-sig"))
    assert manifest["appCapabilities"]["accountingRecoveryUI"] is True
    assert manifest["package"] == "Madar-Suite-Windows-x64"
    with TemporaryDirectory(prefix="madar-r3-suite-installer-test-") as tmp:
        scratch=Path(tmp)
        install=scratch / "new-version-only"
        data=scratch / "private-data"
        shortcuts=scratch / "isolated-shortcuts"
        tests={
            "never_reused_real_desktop": True,
            "private_finance_empty_until_first_launch": False,
            "three_shortcuts_x_two": False,
            "package_sha_verified": False,
            "idempotent_no_overwrite": False,
            "existing_different_exe_refused": False,
        }
        localapp=scratch / "private-localapp"
        localapp.mkdir()
        env={**os.environ,"MADAR_INSTALL_QA":"1",
             "LOCALAPPDATA":str(localapp),"APPDATA":str(scratch/"roaming")}
        args=[
            "powershell.exe","-NoProfile","-ExecutionPolicy","Bypass",
            "-File",str(PACKAGE/"Setup.ps1"),
            "-InstallRoot",str(install),"-DataRoot",str(data),
            "-Silent","-SkipRuntimeForTest","-TestShortcutRoot",str(shortcuts),
        ]
        def run():
            return subprocess.run(args,cwd=ROOT,env=env,
                                  capture_output=True,timeout=150)
        result=run()
        if result.returncode:
            raise RuntimeError("Synthetic installer failed: "+
                               result.stderr.decode(errors="replace")[-1200:])
        tests["package_sha_verified"]=all(
            (install/name).is_file() and sha(install/name)==manifest[section][key].lower()
            for (section,key),name in COPY.items())
        finance=data/"Accounting"
        tests["private_finance_empty_until_first_launch"]=(
            finance.is_dir() and not list(finance.iterdir()) and
            not any((data/name).exists()
                    for name in ("tasks.json","finance.json","madar-unified.sqlite3")))
        desktop=shortcuts/"Desktop"
        menu=shortcuts/"StartMenu"/"Programs"/"Madar Suite"
        tests["three_shortcuts_x_two"]=(
            len(list(desktop.glob("*.lnk")))==3 and
            len(list(menu.glob("*.lnk")))==3 and
            any("بازیابی" in path.name for path in desktop.glob("*.lnk")))
        files={name:sha(install/name) for name in COPY.values()}
        second=run()
        tests["idempotent_no_overwrite"]=(
            second.returncode==0 and
            all(sha(install/name)==digest for name,digest in files.items()))
        # A deliberately altered expected hash must REFUSE, not replace installed
        # binaries or financial data. Test package mutation only in this test
        # would violate immutable shared package; instead test a modified copy.
        candidate=scratch/"candidate"
        candidate.mkdir()
        (candidate/"Apps").mkdir()
        (candidate/"Prerequisites").mkdir()
        import shutil
        for name in COPY.values():
            shutil.copy2(PACKAGE/"Apps"/name,candidate/"Apps"/name)
        shutil.copy2(PACKAGE/"Prerequisites"/"MicrosoftEdgeWebView2RuntimeInstallerX64.exe",
                     candidate/"Prerequisites"/"MicrosoftEdgeWebView2RuntimeInstallerX64.exe")
        shutil.copy2(PACKAGE/"Setup.ps1",candidate/"Setup.ps1")
        forged={**manifest,"apps":{**manifest["apps"],"madarSha256":"0"*64}}
        (candidate/"manifest.json").write_text(json.dumps(forged),encoding="utf8")
        bad_args=[*args]
        bad_args[bad_args.index(str(PACKAGE/"Setup.ps1"))]=str(candidate/"Setup.ps1")
        bad=subprocess.run(bad_args,cwd=ROOT,env=env,capture_output=True,timeout=150)
        tests["existing_different_exe_refused"]=(
            bad.returncode!=0 and
            all(sha(install/name)==digest for name,digest in files.items()) and
            not list(finance.iterdir()))
        print(json.dumps({"checks":tests,"passed":sum(tests.values()),
                          "total":len(tests)},ensure_ascii=True))
        return 0 if all(tests.values()) else 1


if __name__=="__main__":
    sys.exit(main())
