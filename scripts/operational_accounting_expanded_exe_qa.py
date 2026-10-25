"""True packaged EXE startup + WM_CLOSE + mandatory backup acceptance.

Runs ONLY the two verified named release EXEs in fresh synthetic profile dirs.
Never sends messages to windows not owned by launched child processes.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
BASE = PROJECT / ".qa-expanded-accounting-exe-close-20261024"
if BASE.exists():
    raise SystemExit("Refusing to reuse an existing synthetic test root")
BASE.mkdir()
user32 = ctypes.WinDLL("user32", use_last_error=True)
WM_CLOSE = 0x0010
ENUMFUNC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = (ENUMFUNC, wintypes.LPARAM)
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.PostMessageW.restype = wintypes.BOOL


def find_owned_windows(root):
    try:
        ids = {root.pid} | {p.pid for p in root.children(recursive=True)}
    except psutil.Error:
        ids = {root.pid}
    found = []

    @ENUMFUNC
    def callback(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in ids or not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 250:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if title.value and "مدار" in title.value:
            found.append((hwnd, pid.value, title.value))
        return True

    user32.EnumWindows(callback, 0)
    return found


def cleanup_owned(root):
    try:
        children = root.children(recursive=True)
    except psutil.Error:
        children = []
    for proc in reversed(children):
        try:
            proc.terminate()
        except psutil.Error:
            pass
    try:
        root.terminate()
    except psutil.Error:
        pass
    remaining = psutil.wait_procs(children + [root], timeout=4)[1]
    for proc in remaining:
        try:
            proc.kill()
        except psutil.Error:
            pass


def run_one(label, exe, *, standalone):
    root = BASE / label
    root.mkdir()
    dirs = {
        "APPDATA": root/"AppData"/"Roaming",
        "LOCALAPPDATA": root/"AppData"/"Local",
        "WEBVIEW2_USER_DATA_FOLDER": root/"WebView2",
        "TEMP": root/"Temp",
        "TMP": root/"Temp",
    }
    for p in dirs.values():
        p.mkdir(parents=True,exist_ok=True)
    env = {**os.environ, **{key:str(path) for key,path in dirs.items()}}
    # Do not inherit experimental remote-debugging setup from an operator.
    env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    synthetic_finance = root / "finance"
    args = [str(exe)]
    if standalone:
        synthetic_finance.mkdir()
        args += ["--data-dir", str(synthetic_finance)]
    result = {"exe":str(exe),"checks":{},"window":None}
    proc = psutil.Popen(args, cwd=str(PROJECT), env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 23
        windows = []
        backup_files = []
        while time.monotonic() < deadline and proc.is_running():
            windows = find_owned_windows(proc)
            backup_files = list(root.rglob("standalone-accounting-auto-*.sqlite3"))
            if windows and backup_files:
                break
            time.sleep(.35)
        result["checks"]["window_opened"] = bool(windows)
        result["checks"]["startup_backup"] = len(backup_files)>=1
        result["checks"]["accounting_db"] = len(list(root.rglob("standalone-accounting.sqlite3")))==1
        result["window"] = windows[0][2] if windows else None
        first_count = len(backup_files)
        if windows:
            hwnd = windows[0][0]
            sent = bool(user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))
            result["checks"]["wm_close_sent"]=sent
            try:
                proc.wait(timeout=19)
                result["checks"]["normal_process_exit"]=proc.returncode==0
                result["exit_code"]=proc.returncode
            except psutil.TimeoutExpired:
                result["checks"]["normal_process_exit"]=False
            after=list(root.rglob("standalone-accounting-auto-*.sqlite3"))
            result["checks"]["mandatory_backup_on_close"]=len(after)>first_count
            result["backup_count_after_close"]=len(after)
        else:
            result["checks"]["wm_close_sent"]=False
            result["checks"]["normal_process_exit"]=False
            result["checks"]["mandatory_backup_on_close"]=False
        # Validate snapshots with the same full-replay source validation.
        try:
            from standalone_accounting_restore import _check_input
            for item in root.rglob("standalone-accounting-auto-*.sqlite3"):
                _check_input(item)
            result["checks"]["backups_restore_valid"]=bool(list(
                root.rglob("standalone-accounting-auto-*.sqlite3")))
        except Exception as exc:
            result["checks"]["backups_restore_valid"]=False
            result["backup_error"]=str(exc)
    finally:
        if proc.is_running():
            cleanup_owned(proc)
    return result


def main():
    cases = (
        ("standalone",PROJECT/".qa-accounting-expanded-install-20261024"/"Apps"/"Madar-Accounting.exe",True),
        ("main",PROJECT/".qa-accounting-expanded-install-20261024"/"Apps"/"Madar-Desk.exe",False),
    )
    results = []
    try:
        for label,path,standalone in cases:
            if not path.is_file():
                results.append({"exe":str(path),"checks":{"file_exists":False}})
                continue
            results.append(run_one(label,path,standalone=standalone))
    finally:
        (BASE/"report.json").write_text(json.dumps(results,indent=2,
            ensure_ascii=False),encoding="utf-8")
    for item in results:
        print(item["exe"],item["checks"],"exit",item.get("exit_code"))
    return 0 if all(all(case["checks"].values()) for case in results) else 1


if __name__ == "__main__":
    sys.exit(main())
