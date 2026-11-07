"""P1 task-only Python regression gate; deliberately not a release-wide pass.

Run each explicitly selected task-management module with an independent synthetic
profile. Legacy accounting suites remain in the full audit, never deleted or
silently counted as passing here. No installed Madar, Taraz or user data is read.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from modernization_python_suite import PROJECT, execute_module
from safe_test_runner import isolated_environment


TASK_ONLY_MODULES = (
    "test_collab.py",
    "test_collab_bridge.py",
    "test_card_dependency_validation.py",
    "test_project_integrity.py",
    "test_p1_project_grants.py",
    "test_lan_user_persistence.py",
    "test_safe_test_runner.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Optional JSON result path")
    args = parser.parse_args()

    paths = [PROJECT / "tests" / name for name in TASK_ONLY_MODULES]
    missing = [p.name for p in paths if not p.is_file()]
    if missing:
        print("P1_TASK_ONLY_BLOCKED missing=" + ",".join(missing), flush=True)
        return 2

    with tempfile.TemporaryDirectory(prefix="madar-p1-task-only-") as folder:
        scratch = Path(folder)
        clean_env = isolated_environment(scratch / "parent")
        results = []
        # execute_module spawns isolated children; scrub inherited private
        # environment overrides before it takes its os.environ snapshot.
        with patch.dict(os.environ, clean_env, clear=True):
            for path in paths:
                result = execute_module(path, scratch / "modules", 120, False)
                results.append(result)
                print(f"{result['status'].upper()} {path.name} "
                      f"tests={result['tests']} timeout={result['status']=='timeout'}",
                      flush=True)
                if result["status"] != "pass":
                    # Windows legacy consoles may not encode Persian Unicode.
                    diagnostic = result["diagnostic"].encode(
                        "ascii", errors="backslashreplace").decode("ascii")
                    print(diagnostic[-4000:], flush=True)

    summary = {"executed": len(results),
               "passed": sum(item["status"] == "pass" for item in results),
               "failed": sum(item["status"] == "fail" for item in results),
               "timedOut": sum(item["status"] == "timeout" for item in results),
               "testsReported": sum(item["tests"] or 0 for item in results)}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(
            {"scope": "P1 explicitly allowlisted task-only, not full source QA",
             "summary": summary, "modules": results}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    print("P1_TASK_ONLY " + json.dumps(summary), flush=True)
    return 0 if summary["passed"] == len(paths) else 1


if __name__ == "__main__":
    raise SystemExit(main())
