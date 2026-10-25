"""Smoke packaged --recovery entry WITHOUT choosing or restoring any real files.

Only owned child windows are closed. Runtime profile and finance roots are
temporary and never derived from actual APPDATA or a real accounting database.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import psutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "release" / "Madar-Accounting-Fixes-R5-20261025.exe"
WIN = ctypes.WinDLL("user32", use_last_error=True)
ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
WIN.EnumWindows.argtypes = (ENUM, wintypes.LPARAM)
WIN.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
WIN.IsWindowVisible.argtypes = (wintypes.HWND,)
WIN.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
WIN.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
WIN.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


def windows_for_process(process):
    try:
        pids = {process.pid} | {child.pid for child in process.children(recursive=True)}
    except psutil.Error:
        pids = {process.pid}
    windows = []

    @ENUM
    def each(hwnd, _):
        pid = wintypes.DWORD()
        WIN.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and WIN.IsWindowVisible(hwnd):
            n = WIN.GetWindowTextLengthW(hwnd)
            if n < 1024:
                title = ctypes.create_unicode_buffer(n + 1)
                WIN.GetWindowTextW(hwnd, title, n + 1)
                windows.append((hwnd, title.value))
        return True

    WIN.EnumWindows(each, 0)
    return windows


def main():
    if not EXE.is_file():
        raise FileNotFoundError(EXE)
    with TemporaryDirectory(prefix="madar-r5-recovery-exe-qa-") as temp:
        root = Path(temp)
        finance = root / "private-financial-root"
        finance.mkdir()
        isolated = {"APPDATA": root / "roaming", "LOCALAPPDATA": root / "local",
                    "TEMP": root / "temp", "TMP": root / "temp",
                    "WEBVIEW2_USER_DATA_FOLDER": root / "webview2"}
        for path in isolated.values():
            path.mkdir(exist_ok=True)
        env = {**os.environ, **{name: str(path) for name, path in isolated.items()}}
        env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
        owned = psutil.Popen([str(EXE), "--recovery", "--data-dir", str(finance)],
                            env=env, cwd=str(ROOT),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        detected = []
        try:
            until = time.monotonic() + 35
            while owned.is_running() and time.monotonic() < until:
                detected = windows_for_process(owned)
                if detected:
                    break
                time.sleep(.25)
            opened = bool(detected)
            if detected:
                for hwnd, _ in detected:
                    WIN.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE to our dialog only
                try:
                    owned.wait(timeout=8)
                except psutil.TimeoutExpired:
                    pass
            checks = {
                "recovery_dialog_opened": opened,
                "no_accounting_book_initialized": not list(finance.rglob("*.sqlite3")),
                "no_tasks_initialized": not list(root.rglob("tasks.json")),
                "no_finance_json_initialized": not list(root.rglob("finance.json")),
            }
            print(json.dumps({"checks": checks, "passed": sum(checks.values()),
                              "total": len(checks),
                              "dialog_titles": [title for _, title in detected]},
                             ensure_ascii=True, indent=2))
            return 0 if all(checks.values()) else 1
        finally:
            if owned.is_running():
                from operational_r3_candidate_exe_qa import stop_owned_only
                stop_owned_only(owned)


if __name__ == "__main__":
    sys.exit(main())
