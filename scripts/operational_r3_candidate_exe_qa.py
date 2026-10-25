"""Safety-constrained smoke: launch ONLY named new R3 candidate EXEs.

Windows GUI process window / WM_CLOSE / automatic financial backup. All profile
and book paths disposable; the script does not discover any real user APPDATA.
It does not install, publish, edit or stop another user's processes.
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
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FOLDER = tempfile.TemporaryDirectory(prefix="madar-r3-candidate-exe-")
SCRATCH = Path(FOLDER.name)
WM_CLOSE = 0x0010
user32 = ctypes.WinDLL("user32", use_last_error=True)
ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = (ENUM, wintypes.LPARAM)
user32.GetWindowThreadProcessId.argtypes = (
    wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.PostMessageW.argtypes = (
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.PostMessageW.restype = wintypes.BOOL


def windows_for(owned):
    try:
        pids = {owned.pid} | {p.pid for p in owned.children(recursive=True)}
    except psutil.Error:
        pids = {owned.pid}
    result = []

    @ENUM
    def each(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids or not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 240:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if "مدار" in title.value:
            result.append((hwnd, pid.value, title.value))
        return True

    user32.EnumWindows(each, 0)
    return result


def stop_owned_only(proc):
    try:
        children = proc.children(recursive=True)
    except psutil.Error:
        children = []
    for child in reversed(children):
        try:
            child.terminate()
        except psutil.Error:
            pass
    try:
        proc.terminate()
    except psutil.Error:
        pass
    for child in psutil.wait_procs(children + [proc], timeout=4)[1]:
        try:
            child.kill()
        except psutil.Error:
            pass


def exercise(exe: Path, label: str, *, accounting: bool):
    path = SCRATCH / label
    path.mkdir()
    isolated = {
        "APPDATA": path / "roaming",
        "LOCALAPPDATA": path / "local",
        "WEBVIEW2_USER_DATA_FOLDER": path / "webview2",
        "TEMP": path / "tmp",
        "TMP": path / "tmp",
    }
    for folder in isolated.values():
        folder.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **{name: str(folder)
                         for name, folder in isolated.items()}}
    env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    args = [str(exe)]
    if accounting:
        book = path / "financial-only"
        book.mkdir()
        args.extend(("--data-dir", str(book)))
    result = {"exe": str(exe), "checks": {}, "diagnostics": []}
    if not exe.is_file():
        result["checks"]["candidate_exists"] = False
        return result
    process = psutil.Popen(args, cwd=str(ROOT), env=env,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        visible = []
        backups = []
        while time.monotonic() < deadline and process.is_running():
            visible = windows_for(process)
            backups = list(path.rglob("standalone-accounting-auto-*.sqlite3"))
            if visible and backups:
                break
            time.sleep(.35)
        result["checks"]["window_opened"] = bool(visible)
        result["checks"]["startup_backup"] = bool(backups)
        result["checks"]["isolated_sqlite"] = len(list(
            path.rglob("standalone-accounting.sqlite3"))) == 1
        if visible:
            result["diagnostics"].append(visible[0][2])
            result["checks"]["owned_window_close_posted"] = bool(
                user32.PostMessageW(visible[0][0], WM_CLOSE, 0, 0))
            try:
                process.wait(timeout=20)
                result["checks"]["normal_process_exit"] = process.returncode == 0
            except psutil.TimeoutExpired:
                result["checks"]["normal_process_exit"] = False
            later = list(path.rglob("standalone-accounting-auto-*.sqlite3"))
            result["checks"]["mandatory_exit_backup"] = len(later) > len(backups)
            try:
                from standalone_accounting_restore import _check_input
                for saved in later:
                    _check_input(saved)
                result["checks"]["backups_replay_valid"] = bool(later)
            except Exception as error:
                result["checks"]["backups_replay_valid"] = False
                result["diagnostics"].append(str(error))
        else:
            for name in ("owned_window_close_posted", "normal_process_exit",
                         "mandatory_exit_backup", "backups_replay_valid"):
                result["checks"][name] = False
    finally:
        if process.is_running():
            stop_owned_only(process)
    return result


def main():
    results = []
    try:
        cases = (
            ("accounting", "Madar-Accounting-Fixes-R3-20261025.exe", True),
            ("main", "Madar-Desk-Fixes-R3-20261025.exe", False),
        )
        for label, filename, account in cases:
            results.append(exercise(ROOT / "release" / filename, label,
                                    accounting=account))
        # PowerShell 5.1 stdout can use cp1256, which cannot encode all Persian
        # characters in WebView window titles. Keep test results ASCII-safe.
        print(json.dumps(results, ensure_ascii=True, indent=2))
        return 0 if all(v["checks"] and all(v["checks"].values())
                        for v in results) else 1
    finally:
        FOLDER.cleanup()


if __name__ == "__main__":
    sys.exit(main())
