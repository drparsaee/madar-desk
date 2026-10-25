"""Installed EXE: native premium chooser -> real accounting GUI -> safe exit.

Creates one synthetic company in a temporary hub and drives ONLY windows owned
by this new child process. Does not inspect or change installed real data.
"""
from __future__ import annotations
import ctypes
import json
import os
from pathlib import Path
import psutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from standalone_accounting_company_registry import StandaloneCompanyRegistry
from operational_r3_candidate_exe_qa import windows_for, user32, WM_CLOSE, stop_owned_only
from standalone_accounting_restore import _check_input

VK_RETURN=0x0D
KEYEVENTF_KEYUP=0x0002
user32.SetForegroundWindow.argtypes=(ctypes.c_void_p,)
user32.SetForegroundWindow.restype=ctypes.c_bool
user32.keybd_event.argtypes=(ctypes.c_ubyte,ctypes.c_ubyte,ctypes.c_ulong,ctypes.c_ulong)


def run():
    exe=ROOT/'release'/'Madar-Accounting-Mohsen-Premium-R12-20261025.exe'
    result={'checks':{},'errors':[]}
    with tempfile.TemporaryDirectory(prefix='madar-premium-r12-real-gui-') as tmp:
        root=Path(tmp)
        hub=root/'companies';hub.mkdir()
        registry=StandaloneCompanyRegistry(hub)
        company=registry.create_company('آزمون ورود ویندوز')
        book=registry.company_data_directory(company['id'])
        env=os.environ.copy()
        for key,name in [('APPDATA','roaming'),('LOCALAPPDATA','local'),
                         ('WEBVIEW2_USER_DATA_FOLDER','webview'),('TEMP','tmp'),('TMP','tmp')]:
            target=root/name;target.mkdir(exist_ok=True)
            env[key]=str(target)
        proc=psutil.Popen([str(exe),'--companies-dir',str(hub)],cwd=str(ROOT),env=env,
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            chooser=None
            end=time.monotonic()+24
            while time.monotonic()<end and proc.is_running():
                chooser=next((entry for entry in windows_for(proc)
                              if 'انتخاب شرکت' in entry[2]),None)
                if chooser:break
                time.sleep(.25)
            result['checks']['premium_chooser_visible']=bool(chooser)
            if chooser:
                result['checks']['own_window_focused']=bool(user32.SetForegroundWindow(chooser[0]))
                time.sleep(.5)
                user32.keybd_event(VK_RETURN,0,0,0)
                user32.keybd_event(VK_RETURN,0,KEYEVENTF_KEYUP,0)
                result['checks']['keyboard_login_sent']=True
            else:
                result['checks']['keyboard_login_sent']=False
            main_window=None
            end=time.monotonic()+32
            while time.monotonic()<end and proc.is_running():
                main_window=next((entry for entry in windows_for(proc)
                                  if 'حسابداری مستقل' in entry[2]),None)
                if main_window and (book/'standalone-accounting.sqlite3').is_file():break
                time.sleep(.3)
            result['checks']['book_entered_by_user_keyboard']=bool(main_window)
            result['checks']['only_synthetic_book_initialized']=(
                (book/'standalone-accounting.sqlite3').is_file() and
                len(list(hub.rglob('standalone-accounting.sqlite3')))==1)
            initial=list(book.rglob('standalone-accounting-auto-*.sqlite3'))
            result['checks']['startup_backup']=bool(initial)
            if main_window:
                result['checks']['close_own_accounting_window']=bool(
                    user32.PostMessageW(main_window[0],WM_CLOSE,0,0))
                try:
                    proc.wait(timeout=18)
                    result['checks']['normal_exit']=proc.returncode==0
                except psutil.TimeoutExpired:
                    result['checks']['normal_exit']=False
                backups=list(book.rglob('standalone-accounting-auto-*.sqlite3'))
                result['checks']['mandatory_exit_backup']=len(backups)>len(initial)
                result['checks']['verified_backups']=len(backups)>0 and all(
                    _check_input(path)[0]==0 for path in backups)
            else:
                for key in ('close_own_accounting_window','normal_exit',
                            'mandatory_exit_backup','verified_backups'):
                    result['checks'][key]=False
        finally:
            if proc.is_running():stop_owned_only(proc)
    print(json.dumps(result,ensure_ascii=True,indent=2))
    return 0 if result['checks'] and all(result['checks'].values()) else 1


if __name__=='__main__':raise SystemExit(run())
