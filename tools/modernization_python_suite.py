"""Bounded, disposable-profile unittest audit for Madar Desk (no pytest dependency).

Each test module runs in an independent child process, with disposable Windows
profile/temp roots.  Failure in one module does not mask remaining modules.
This is source-level characterization, never an installed-app acceptance test.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT / "docs" / "modernization" / "full_python_phase3_results.json"
RAN = re.compile(r"Ran (\d+) tests? in [\d.]+s")
SKIPPED = re.compile(r"skipped=(\d+)")
EXPECTED = re.compile(r"expected failures=(\d+)")
FAILS = re.compile(r"(?<!expected )failures=(\d+)")
ERRORS = re.compile(r"errors=(\d+)")
OUTPUT_CAP = 10000


def sanitize_diagnostic(output: str) -> str:
    """Keep local machine usernames and repo locations out of shared reports."""
    for value, replacement in (
        (str(PROJECT), "<PROJECT_ROOT>"),
        (os.environ.get("USERPROFILE", ""), "<USER_HOME>"),
        (str(Path.home()), "<USER_HOME>"),
    ):
        if value:
            output = re.sub(re.escape(value), lambda _: replacement, output,
                            flags=re.IGNORECASE)
    return output


def execute_module(path: Path, scratch: Path, timeout: int, legacy_seed: bool) -> dict:
    isolated = scratch / path.stem
    roaming = isolated / "Roaming"
    local = isolated / "Local"
    temporary = isolated / "Temp"
    home = isolated / "Home"
    for folder in (roaming, local, temporary, home):
        folder.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        APPDATA=str(roaming), LOCALAPPDATA=str(local), TEMP=str(temporary),
        TMP=str(temporary), TMPDIR=str(temporary), USERPROFILE=str(home),
        HOME=str(home), XDG_DATA_HOME=str(local),
        PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
        PYTHONPATH=os.pathsep.join((str(PROJECT), str(PROJECT / "tests"))),
    )
    if legacy_seed:
        # Characterization only: old bridge tests assumed every fresh profile
        # contained example-1..4, before the empty-profile production fix.
        # Patch the imported factory in this child process, not runtime files.
        code = (
            "import native_app, unittest, sys; "
            "native_app.empty_initial_state = native_app.initial_state; "
            "suite = unittest.defaultTestLoader.discover('tests', pattern=sys.argv[1]); "
            "result = unittest.TextTestRunner(verbosity=0).run(suite); "
            "sys.exit(0 if result.wasSuccessful() else 1)"
        )
        cmd = [sys.executable, "-c", code, path.name]
    else:
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests",
               "-p", path.name, "-q"]
    started = time.monotonic()
    try:
        process = subprocess.run(cmd, cwd=PROJECT, env=env,
                                 capture_output=True, timeout=timeout,
                                 text=True, encoding="utf-8", errors="replace")
        result = "pass" if process.returncode == 0 else "fail"
        output = process.stdout + "\n" + process.stderr
        code = process.returncode
    except subprocess.TimeoutExpired as exc:
        result = "timeout"
        code = None
        value = exc.stdout or b""
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        extra = exc.stderr or b""
        if isinstance(extra, bytes):
            extra = extra.decode("utf-8", errors="replace")
        output = value + "\n" + extra + "\nTIMEOUT"
    match = RAN.search(output)
    skipped = SKIPPED.search(output)
    expected = EXPECTED.search(output)
    fail_count = FAILS.search(output)
    error_count = ERRORS.search(output)
    return {
        "module": path.name, "status": result, "returncode": code,
        "duration_seconds": round(time.monotonic() - started, 2),
        "tests": int(match.group(1)) if match else None,
        "skipped": int(skipped.group(1)) if skipped else 0,
        "expected_failures": int(expected.group(1)) if expected else 0,
        "failures": int(fail_count.group(1)) if fail_count else 0,
        "errors": int(error_count.group(1)) if error_count else 0,
        "diagnostic": sanitize_diagnostic(output[-OUTPUT_CAP:]) if result != "pass" else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=75,
                        help="Maximum wall time per test module")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("--failed-only", type=Path,
                        help="Re-run only modules failed/timed-out in a previous JSON report")
    parser.add_argument("--legacy-seed", action="store_true",
                        help="Diagnostic simulation of old sample-seeded fresh profile")
    parser.add_argument("--recount-existing", type=Path,
                        help="Correct counters in existing report without re-running tests")
    args = parser.parse_args()
    if args.recount_existing:
        saved = json.loads(args.recount_existing.read_text(encoding="utf-8"))
        for row in saved["modules"]:
            match = FAILS.search(row["diagnostic"])
            row["failures"] = int(match.group(1)) if match else 0
            row["diagnostic"] = sanitize_diagnostic(row["diagnostic"])
        saved["summary"]["test_failures"] = sum(
            row["failures"] for row in saved["modules"])
        args.recount_existing.write_text(
            json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Recounted historical stderr: ", saved["summary"]["test_failures"],
              "unexpected test failures; no tests re-executed")
        return 0
    if not 1 <= args.workers <= 8 or not 1 <= args.timeout <= 179:
        parser.error("workers must be 1..8, timeout 1..179 seconds")
    modules = sorted((PROJECT / "tests").glob(args.pattern))
    if args.failed_only:
        previous = json.loads(args.failed_only.read_text(encoding="utf-8"))
        names = {row["module"] for row in previous["modules"]
                 if row["status"] != "pass"}
        modules = [row for row in modules if row.name in names]
    if not modules:
        parser.error("No modules matched pattern")

    # Avoid running a built/existing executable as part of this source audit.
    # The packaged EXE test gets its own opt-in release-acceptance run.
    excluded = {"test_packaged_madar_host_exe.py"}
    selected = [path for path in modules if path.name not in excluded]
    results = []
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="madar-python-phase3-") as root:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            jobs = {pool.submit(execute_module, module, Path(root), args.timeout,
                                args.legacy_seed): module
                    for module in selected}
            for job in as_completed(jobs):
                result = job.result()
                results.append(result)
                print(f"{len(results):3}/{len(selected)} {result['status']:7} "
                      f"{result['tests']!s:>4} {result['duration_seconds']:>7}s "
                      f"{result['module']}", flush=True)

    results.sort(key=lambda result: result["module"])
    summary = {
        "modules_discovered": len(modules), "modules_excluded": sorted(excluded & {p.name for p in modules}),
        "modules_executed": len(results),
        "modules_passed": sum(r["status"] == "pass" for r in results),
        "modules_failed": sum(r["status"] == "fail" for r in results),
        "modules_timed_out": sum(r["status"] == "timeout" for r in results),
        "tests_reported": sum(r["tests"] or 0 for r in results),
        "tests_skipped": sum(r["skipped"] for r in results),
        "expected_failures": sum(r["expected_failures"] for r in results),
        "test_failures": sum(r["failures"] for r in results),
        "test_errors": sum(r["errors"] for r in results),
        "elapsed_seconds": round(time.monotonic() - start, 2),
    }
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0], "runner": "unittest module-process isolation",
        "max_workers": args.workers, "timeout_per_module_seconds": args.timeout,
        "legacy_seed_diagnostic": args.legacy_seed,
        "environment": "Synthetic per-module APPDATA/LOCALAPPDATA/TEMP/USERPROFILE/HOME",
        "summary": summary, "modules": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("SUMMARY " + json.dumps(summary), flush=True)
    print("REPORT " + str(args.report), flush=True)
    return 0 if not summary["modules_failed"] and not summary["modules_timed_out"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
