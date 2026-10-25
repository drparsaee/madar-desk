r"""Reproducible, Windows-oriented Madar release regression runner.

    py -3 scripts\release_qa.py
    py -3 scripts\release_qa.py --full

All child processes receive a fresh APPDATA and LOCALAPPDATA. The runner never
copies, migrates, launches or restores a user's real MadarDesk data or EXE.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


PROJECT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated Madar Desk 1.0 RC regression QA")
    parser.add_argument("--full", action="store_true",
                        help="also execute the project's complete npm test suite")
    arguments = parser.parse_args(argv)

    if not (PROJECT / "native_app.py").is_file() or not (PROJECT / "tests").is_dir():
        parser.error("Cannot locate Madar Desk source and tests")

    commands: list[tuple[str, list[str]]] = [
        ("Release regression tests", [sys.executable, "-m", "unittest", "discover",
                                      "-s", "tests", "-p", "test_release_*.py", "-v"]),
    ]
    if arguments.full:
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            print("ERROR: npm is required for --full QA", file=sys.stderr)
            return 2
        commands.append(("Full Python + JavaScript suite", [npm, "test"]))

    with tempfile.TemporaryDirectory(prefix="madar-release-qa-root-") as isolated:
        isolated_dir = Path(isolated)
        appdata = isolated_dir / "AppData"
        appdata.mkdir()
        env = os.environ.copy()
        env["APPDATA"] = str(appdata)
        env["LOCALAPPDATA"] = str(appdata)
        env["MADAR_RELEASE_QA"] = "1"
        print(f"Madar release QA, Python {sys.version.split()[0]}", flush=True)
        print(f"Project: {PROJECT}", flush=True)
        print("APPDATA and LOCALAPPDATA are isolated in a disposable temporary directory.",
              flush=True)
        for name, command in commands:
            print(f"\nRUN: {name}", flush=True)
            # Never shell=True. No command is built from user-controlled script text.
            result = subprocess.run(command, cwd=PROJECT, env=env, check=False)
            if result.returncode != 0:
                print(f"FAIL: {name} (exit {result.returncode})", flush=True)
                return result.returncode
            print(f"PASS: {name}", flush=True)

    print("\nPASS: automated release QA. Desktop, EXE, LAN and Drive manual gates remain.",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
