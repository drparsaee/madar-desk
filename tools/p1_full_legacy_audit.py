"""Repeatable, non-destructive full Python source audit for the integrated Madar.

This is intentionally NOT the task-only release gate. It preserves failures
from retired financial contracts in its report instead of hiding them.
Run from the repository root using:
  py -3.12 -B tools/p1_full_legacy_audit.py --report PATH_TO_FRESH_REPORT_JSON
No packaged EXE, installed app or real profile is used.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from safe_test_runner import isolated_environment

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True,
                        help='Fresh, persistent JSON path outside the disposable profile')
    args = parser.parse_args()
    report = args.report.resolve(strict=False)
    if report.is_file():
        raise FileExistsError('Refusing to overwrite an existing full QA report: ' + str(report))
    if not report.parent.is_dir():
        raise FileNotFoundError('Create an intentional QA report directory first: ' + str(report.parent))
    if report.is_relative_to(ROOT):
        raise ValueError('Store the full report outside the source worktree')
    if report.is_symlink() or any(p.is_symlink() for p in report.parents):
        raise PermissionError('QA report path may not traverse a symlink')

    with tempfile.TemporaryDirectory(prefix='madar-p1-full-audit-') as temp:
        environment = isolated_environment(Path(temp) / 'parent')
        command = [sys.executable, '-B', str(ROOT/'tools'/'modernization_python_suite.py'),
                   '--workers', '5', '--timeout', '120', '--report', str(report)]
        completed = subprocess.run(
            command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding='utf-8',
            errors='replace', timeout=900, check=False)

    if not report.is_file():
        raise RuntimeError('No durable per-module report; child exit=' +
                           str(completed.returncode) + '\n' + completed.stdout[-2500:])
    payload = json.loads(report.read_text(encoding='utf-8'))
    summary = payload['summary']
    if len(payload['modules']) != summary['modules_executed']:
        raise RuntimeError('Incomplete per-module result inventory')
    print('P1_FULL_PYTHON_EXIT=' + str(completed.returncode), flush=True)
    print('P1_FULL_PYTHON_SUMMARY=' + json.dumps(summary, ensure_ascii=True), flush=True)
    print('P1_FULL_PYTHON_REPORT=' + str(report), flush=True)
    return completed.returncode


if __name__ == '__main__':
    raise SystemExit(main())
