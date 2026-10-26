"""Isolated R18 packaged GUI smoke without keyboard focus or real user books.

This specifically does NOT claim secure-login or role UI acceptance; those
need an isolated focus-controlled session. All file writes stay in TemporaryDirectory.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from operational_r3_candidate_exe_qa import windows_for, user32, WM_CLOSE, stop_owned_only
from standalone_accounting_restore import _check_input


def run():
    exe = ROOT / 'release' / 'Madar-Accounting-User-Roles-Parsian-Trial-R18-20261026.exe'
    checks, warnings = {}, []
    checks['release_exists'] = exe.is_file()
    if not checks['release_exists']:
        print(json.dumps({'checks': checks, 'fail': 1}))
        return 1

    with tempfile.TemporaryDirectory(prefix='madar-r18-exe-direct-') as tmp:
        scratch = Path(tmp)
        book = scratch / 'synthetic-book'
        book.mkdir()
        env = os.environ.copy()
        for key, folder in [('APPDATA','appdata'),('LOCALAPPDATA','local'),
                            ('TEMP','temp'),('TMP','temp'),
                            ('WEBVIEW2_USER_DATA_FOLDER','webview')]:
            target = scratch / folder
            target.mkdir(exist_ok=True)
            env[key] = str(target)
        process = psutil.Popen([str(exe), '--data-dir', str(book)],
                                cwd=str(ROOT), env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            window = None
            deadline = time.monotonic() + 45
            while process.is_running() and time.monotonic() < deadline:
                matches = [w for w in windows_for(process)
                           if 'مدار | حسابداری مستقل' in w[2]]
                if matches:
                    window = matches[0]
                    break
                time.sleep(.2)
            checks['financial_window_opened'] = bool(window)
            database = book / 'standalone-accounting.sqlite3'
            checks['isolated_database_created'] = database.is_file()
            before = list((book / 'standalone-accounting-backups').glob('*.sqlite3')) \
                if (book / 'standalone-accounting-backups').is_dir() else []
            checks['startup_backup'] = bool(before)
            if window:
                checks['close_owned_window'] = bool(
                    user32.PostMessageW(window[0], WM_CLOSE, 0, 0))
                try:
                    process.wait(timeout=25)
                except psutil.TimeoutExpired:
                    warnings.append('Owned EXE did not terminate within 25 seconds')
            else:
                checks['close_owned_window'] = False
            checks['normal_exit'] = process.poll() == 0
            after = list((book / 'standalone-accounting-backups').glob('*.sqlite3')) \
                if (book / 'standalone-accounting-backups').is_dir() else []
            checks['exit_backup'] = len(after) > len(before)
            checks['backup_integrity'] = bool(after) and all(
                _check_input(item)[0] == 0 for item in after)
        finally:
            if process.is_running():
                stop_owned_only(process)

    result = {'checks': checks, 'pass': sum(checks.values()),
              'fail': sum(not v for v in checks.values()), 'warnings': warnings}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['fail'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(run())
