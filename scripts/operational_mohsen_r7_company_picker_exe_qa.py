"""GUI test of the actual packaged multi-company launcher, synthetic data only."""
from __future__ import annotations

import json
import os
import argparse
from pathlib import Path
import psutil
import subprocess
import sys
import tempfile
import time

from operational_r3_candidate_exe_qa import ROOT, windows_for, user32, WM_CLOSE, stop_owned_only


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",action="store_true",
                        help="Smoke the current source before rebuilding EXE")
    parser.add_argument("--exe",type=str,default="",
                        help="Override candidate EXE path after a new build")
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="madar-r7-company-picker-") as tmp:
        root=Path(tmp)
        hub=root/"company-hub"
        hub.mkdir()
        isolated={key:root/name for key,name in (
            ("APPDATA","roaming"),("LOCALAPPDATA","local"),
            ("WEBVIEW2_USER_DATA_FOLDER","webview2"),
            ("TEMP","temp"),("TMP","temp"))}
        for path in isolated.values():
            path.mkdir(exist_ok=True)
        env={**os.environ,**{key:str(path) for key,path in isolated.items()}}
        exe=Path(args.exe) if args.exe else (
            ROOT/"release"/"Madar-Accounting-Mohsen-UX-R7-20261025.exe")
        command=([sys.executable,str(ROOT/"standalone_accounting_desktop.py")]
                 if args.source else [str(exe)])
        proc=psutil.Popen([*command,"--companies-dir",str(hub)],
                          cwd=str(ROOT),env=env,
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        checks={}
        observations=[]
        try:
            windows=[]
            deadline=time.monotonic()+30
            while time.monotonic()<deadline and proc.is_running():
                windows=windows_for(proc)
                if windows:
                    break
                time.sleep(.25)
            checks["chooser_window_visible"]=bool(windows)
            if windows:
                observations.append({"windowTitle":windows[0][2]})
                checks["close_message_sent"]=bool(
                    user32.PostMessageW(windows[0][0],WM_CLOSE,0,0))
                try:
                    proc.wait(timeout=15)
                    checks["chooser_closed"]=True
                    observations.append({"exitCode":proc.returncode})
                    checks["clean_cancel_exit"]=proc.returncode==0
                except psutil.TimeoutExpired:
                    checks["chooser_closed"]=False
                    checks["clean_cancel_exit"]=False
                    observations.append({"processAlive":proc.is_running(),
                        "windowsStillOpen":windows_for(proc)})
            checks["no_ledger_created"]=not list(root.rglob(
                "standalone-accounting.sqlite3"))
            checks["no_company_allocated"]=not (hub/"books").exists()
            print(json.dumps({"checks":checks,"observations":observations},
                             ensure_ascii=True))
            return 0 if checks and all(checks.values()) else 1
        finally:
            if proc.is_running():
                stop_owned_only(proc)


if __name__=="__main__":
    sys.exit(main())
