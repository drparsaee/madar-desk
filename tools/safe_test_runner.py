"""Run synthetic Madar source tests with private Windows QA profiles.

The installed application, operational Madar data and Parsian data are never
test inputs; the separate packaged EXE acceptance is deliberately excluded.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PREFIXES = ("MADAR_", "PARSIAN_", "ACCOUNTING_", "SQLSERVER_", "SQL_SERVER_", "VITE_")


def isolated_environment(scratch: Path, source=None, *, browser_compatible=False) -> dict:
    """Isolate app data; retain Windows USERPROFILE only for Chrome when needed.

    Chrome on this Windows host refuses Playwright's temporary --user-data-dir
    if USERPROFILE is rewritten. The browser still gets isolated APPDATA,
    LOCALAPPDATA, TEMP, HOME and a separate Playwright browser profile.
    Python/accounting tests never use this exception.
    """
    env = dict(os.environ if source is None else source)
    for key in list(env):
        if key.upper().startswith(PRIVATE_PREFIXES) or key.upper() in (
            "PYTHONPATH", "NODE_OPTIONS", "CHROME_USER_DATA_DIR",
        ):
            del env[key]
    locations = {
        "APPDATA": scratch / "Roaming",
        "LOCALAPPDATA": scratch / "Local",
        "TEMP": scratch / "Temp",
        "TMP": scratch / "Temp",
        "TMPDIR": scratch / "Temp",
        "HOME": scratch / "Home",
        "USERPROFILE": scratch / "Home",
        "XDG_DATA_HOME": scratch / "Local",
    }
    for folder in set(locations.values()):
        folder.mkdir(parents=True, exist_ok=True)
    env.update({key: str(value) for key, value in locations.items()})
    if browser_compatible and os.name == "nt":
        original = (os.environ if source is None else source)
        if not original.get("USERPROFILE"):
            raise RuntimeError("Chrome requires an original Windows USERPROFILE")
        env["USERPROFILE"] = original["USERPROFILE"]
        for key in ("HOMEDRIVE", "HOMEPATH"):
            if key in original:
                env[key] = original[key]
    else:
        home_drive, home_path = os.path.splitdrive(str(locations["HOME"]))
        if home_drive:
            env["HOMEDRIVE"] = home_drive
            env["HOMEPATH"] = home_path
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_logged_phase(label: str, command: list[str], env: dict, root: Path, timeout: int) -> str:
    """Retain logs only in the disposable QA root; show a bounded failure tail."""
    logfile = root / (label + ".log")
    print("RUN " + label, flush=True)
    try:
        with logfile.open("w", encoding="utf-8") as handle:
            outcome = subprocess.run(command, cwd=ROOT, env=env,
                                     stdout=handle, stderr=subprocess.STDOUT,
                                     timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(label + ": time limit exceeded") from error
    output = logfile.read_text(encoding="utf-8", errors="replace")
    if outcome.returncode != 0:
        print("\n".join(output.splitlines()[-75:]), file=sys.stderr, flush=True)
        raise RuntimeError(label + ": exit code " + str(outcome.returncode))
    print("PASS " + label, flush=True)
    return output


def node_totals(output: str) -> dict:
    values = {}
    for key in ("tests", "pass", "fail", "skipped"):
        found = re.search(r"(?m)^(?:#|ℹ)\s+" + key + r"\s+(\d+)\s*$", output)
        if not found:
            raise RuntimeError("Node test runner did not provide " + key + " count")
        values[key] = int(found.group(1))
    if values["fail"] or values["skipped"] or values["tests"] != values["pass"]:
        raise RuntimeError("Node suite incomplete: " + json.dumps(values))
    return values


def main() -> int:
    # Only newly created temporary paths are removed when this run exits.
    try:
        with tempfile.TemporaryDirectory(prefix="madar-safe-suite-") as dirname:
            scratch = Path(dirname)
            env = isolated_environment(scratch / "profile")
            python_report = scratch / "python-summary.json"
            run_logged_phase("python", [sys.executable, "-B",
                str(ROOT / "tools" / "modernization_python_suite.py"),
                "--workers", "5", "--timeout", "120",
                "--report", str(python_report)], env, scratch, timeout=900)
            summary = json.loads(python_report.read_text(encoding="utf-8"))["summary"]
            if not summary["modules_executed"] or summary["modules_failed"] or (
                summary["modules_timed_out"] or summary["test_failures"] or summary["test_errors"]
            ):
                raise RuntimeError("Python suite incomplete: " + json.dumps(summary))
            print("PYTHON " + json.dumps(summary, ensure_ascii=False), flush=True)
            npm = shutil.which("npm.cmd") or shutil.which("npm")
            if not npm:
                raise RuntimeError("npm is unavailable for offline Vite build")
            run_logged_phase("build", [npm, "run", "build"], env, scratch, timeout=180)
            node = shutil.which("node")
            if not node:
                raise RuntimeError("node is unavailable for UI tests")
            tests = sorted((ROOT / "tests").glob("*.test.cjs"))
            if not tests:
                raise RuntimeError("No Node tests found")
            browser_env = isolated_environment(scratch / "browser-profile",
                                                browser_compatible=True)
            stdout = run_logged_phase("node", [node, "--test",
                "--test-concurrency=1", *(str(test) for test in tests)],
                browser_env, scratch, timeout=900)
            print("NODE " + json.dumps(node_totals(stdout)), flush=True)
            print("SOURCE QA COMPLETE: excludes packaged EXE and real-user migration",
                  flush=True)
            return 0
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print("SOURCE QA BLOCKED: " + str(error), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
