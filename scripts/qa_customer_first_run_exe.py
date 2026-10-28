"""Verify a fresh installed-style Windows executable starts with no user cards.

The EXE runs in an exclusively owned Windows Job with disposable APPDATA,
LOCALAPPDATA, TEMP and WebView2 folders. Does not touch any real installation.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from v1_gui_smoke import WindowsOwnedJob, _disposable_root, isolated_environment


PROJECT = Path(__file__).resolve().parent.parent
EXPECTED = {
    "projectCount": 0,
    "boardCount": 0,
    "cardCount": 0,
    "workspaceCount": 1,
    "workspaceNameIsDefault": True,
    "mounted": True,
    "emptyOnboardingVisible": True,
    "createButton": True,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    args = parser.parse_args()
    executable = args.exe.resolve()
    release_root = (PROJECT / "release").resolve()
    if not executable.is_file() or executable.suffix.lower() != ".exe" or not executable.is_relative_to(release_root):
        raise ValueError("Only an existing release EXE under the project release folder is allowed")
    with _disposable_root() as scratch:
        env = isolated_environment(os.environ, scratch, screenshot=False)
        env["MADAR_QA_VIEW"] = "fresh-profile"
        result_file = scratch / "diagnostics.json"
        job = WindowsOwnedJob(executable, PROJECT, env)
        try:
            for _ in range(160):
                if result_file.is_file():
                    break
                if job.poll() is not None:
                    raise RuntimeError("Customer EXE exited without an initial-state report")
                time.sleep(.25)
            if not result_file.is_file():
                raise TimeoutError("Customer EXE did not provide fresh-profile evidence")
            observed = json.loads(result_file.read_text(encoding="utf8"))
            data_path = scratch / "AppData" / "Roaming" / "MadarDesk" / "tasks.json"
            stored = json.loads(data_path.read_text(encoding="utf8"))
            persisted = {
                "projectCount": len(stored["projects"]),
                "boardCount": len(stored.get("boards", [])),
                "cardCount": len(stored["tasks"]),
                "workspaceCount": len(stored.get("workspaces", [])),
            }
            errors = {
                key: {"expected": expected, "actual": observed.get(key)}
                for key, expected in EXPECTED.items()
                if observed.get(key) != expected
            }
            for key, expected in persisted.items():
                if expected != EXPECTED[key]:
                    errors["on_disk_" + key] = {"expected": EXPECTED[key], "actual": expected}
            if errors:
                print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False))
                return 1
            print(json.dumps({"status": "PASS", "fresh_profile": observed,
                              "persisted": persisted}, ensure_ascii=False))
            return 0
        finally:
            job.stop()


if __name__ == "__main__":
    raise SystemExit(main())
