"""Packaged R19 imported-trial login-gate smoke; no simulated passwords.

Owned process and isolated QA company only, checks the password gate appears
without opening the ledger, then closes it. Not a secure-login completion test.
"""
from pathlib import Path
import json
import os
import psutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from operational_r3_candidate_exe_qa import windows_for,user32,WM_CLOSE,stop_owned_only
from standalone_accounting import StandaloneAccountingStore


def main():
    executable=Path(os.environ['LOCALAPPDATA'])/'Programs'/'Madar Accounting Mohsen R19'/(
        'Madar-Accounting-Estedad-Parsian-Archive-R19-20261026.exe')
    book=ROOT/'.private-parsian-staging-20261026'/'r19-1405'/'migration-experiment-20261026'/(
        'parsian-rial-gl-import-disposable')
    identity=book/'local-users.json'
    result={}
    result['installed_r19_exists']=executable.is_file()
    result['isolated_parsian_trial_exists']=(book/'standalone-accounting.sqlite3').is_file()
    result['trial_identity_exists']=identity.is_file()
    if not all(result.values()):
        print(json.dumps(result));return 1
    with tempfile.TemporaryDirectory(prefix='madar-r19-trial-exe-') as temp:
        env=os.environ.copy()
        for key,relative in (('APPDATA','appdata'),('LOCALAPPDATA','local'),
                             ('TEMP','temp'),('TMP','temp'),
                             ('WEBVIEW2_USER_DATA_FOLDER','webview')):
            path=Path(temp)/relative
            path.mkdir(exist_ok=True)
            env[key]=str(path)
        process=psutil.Popen([str(executable),'--data-dir',str(book)],
            cwd=str(ROOT),env=env,stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        try:
            login=None
            deadline=time.monotonic()+35
            while process.is_running() and time.monotonic()<deadline:
                owned=[w for w in windows_for(process) if 'ورود امن حسابداری' in w[2]]
                if owned:
                    login=owned[0]
                    break
                time.sleep(.2)
            result['native_password_gate_opened']=bool(login)
            result['no_unauthenticated_ledger_window']=not any(
                'حسابداری مستقل' in w[2] for w in windows_for(process))
            if login:
                result['owned_login_closed']=bool(user32.PostMessageW(login[0],WM_CLOSE,0,0))
                try:process.wait(timeout=20)
                except psutil.TimeoutExpired:pass
            else:result['owned_login_closed']=False
            result['normal_exit']=process.poll()==0
        finally:
            if process.is_running():stop_owned_only(process)
    db=StandaloneAccountingStore(book/'standalone-accounting.sqlite3',default_currency='RIAL')
    snap=db.read(actor='test',accounts={'test':{'username':'test','role':'admin'}})
    result['trial_revision_unchanged']=snap['revision']==251
    result['journal_count_unchanged']=len(snap['view']['journals'])==125
    print(json.dumps({'pass':sum(result.values()),'fail':sum(not v for v in result.values()),
                      'checks':result},ensure_ascii=False))
    return 0 if all(result.values()) else 1


if __name__=='__main__':raise SystemExit(main())
