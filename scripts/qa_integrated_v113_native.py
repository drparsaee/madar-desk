"""Opt-in real packaged WebView2 smoke with a disposable accounting profile.

This spawns only the new immutable candidate executable, never the already
installed application. Every APPDATA/LOCALAPPDATA and finance file is synthetic.
The owned process tree is stopped after its read-only bridge QA completes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import psutil

from build_integrated_v113 import builder, digest, read_verified_release_descriptor


def stop_owned_process(process):
    try:
        owner = psutil.Process(process.pid)
    except psutil.NoSuchProcess:
        return
    descendants = owner.children(recursive=True)
    for child in reversed(descendants):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    gone, alive = psutil.wait_procs(descendants, timeout=4)
    for child in alive:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    try:
        owner.terminate()
        owner.wait(timeout=4)
    except (psutil.NoSuchProcess, psutil.TimeoutExpired):
        try:
            owner.kill()
        except psutil.NoSuchProcess:
            pass


def synthetic_environment(root: Path, source: dict[str, str]) -> dict[str, str]:
    """Scope both environment-based profile roots and the Python home.

    This cannot override OS known-folder APIs; this native check is therefore
    deliberately a narrow readiness smoke, NOT proof of whole-app isolation.
    """
    env = {key: value for key, value in source.items()
           if not key.upper().startswith(("MADAR_", "PARSIAN_", "ACCOUNTING_",
                                          "SQLSERVER_")) and
           key.upper() not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")}
    for key, name in (("APPDATA", "Roaming"), ("LOCALAPPDATA", "Local"),
                      ("TEMP", "Temp"), ("TMP", "Temp"),
                      ("USERPROFILE", "UserProfile"), ("HOME", "UserProfile")):
        folder = root / name
        folder.mkdir(exist_ok=True)
        env[key] = str(folder)
    user = root / "UserProfile"
    env["HOMEDRIVE"] = user.drive
    env["HOMEPATH"] = str(user)[len(user.drive):]
    return env


def main():
    # Require exact pinned binary identity before starting a native process,
    # not merely the first two "MZ" bytes of any executable.
    descriptor = read_verified_release_descriptor()
    with tempfile.TemporaryDirectory(prefix="madar-qa-bridge-v113-") as directory:
        root = Path(directory)
        env = synthetic_environment(root, os.environ)
        report = root / "native-bridge-report.json"
        env.update(MADAR_QA_REPORT=str(report), MADAR_QA_VIEW="bridge-readiness",
                   PYTHONIOENCODING="utf-8")
        if digest(builder.PROGRAM) != descriptor["applicationSha256"]:
            raise RuntimeError("Packaged program changed after native smoke preflight")
        process = subprocess.Popen([str(builder.PROGRAM)], env=env,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            deadline = time.monotonic() + 90
            while not report.is_file() and time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Packaged Windows program exited before bridge QA")
                time.sleep(0.35)
            if not report.is_file():
                raise RuntimeError("Packaged WebView2 did not produce a bridge QA result")
            info = json.loads(report.read_text(encoding="utf8"))
            before, accounting, after = (
                info.get("nativeBridgeBefore") or {},
                info.get("nativeBridgeAccounting") or {},
                info.get("nativeBridgeAfterReturn") or {},
            )
            read = info.get("nativeAccountingReadHealth") or {}
            if (info.get("nativeBridgeError") or
                    before.get("root", 0) < 500 or
                    accounting.get("path") != "/accounting.html" or
                    accounting.get("root", 0) < 500 or
                    accounting.get("bridge") != "object" or
                    accounting.get("read") != "function" or
                    read.get("done") is not True or read.get("ok") is not True or
                    after.get("path") != "/index.html" or after.get("root", 0) < 500):
                raise RuntimeError("Packaged native accounting bridge QA failed: " +
                                   json.dumps({"before": before, "accounting": accounting,
                                               "read": read, "after": after,
                                               "error": info.get("nativeBridgeError")},
                                              ensure_ascii=False))
            print("PACKAGED_113_NATIVE_WEBVIEW2_PASSED: main-to-accounting-to-main,"
                  " authenticated API projection read, synthetic APPDATA only", flush=True)
        finally:
            stop_owned_process(process)


if __name__ == "__main__":
    main()
