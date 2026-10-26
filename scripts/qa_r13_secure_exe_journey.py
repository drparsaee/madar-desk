"""Real installed-style R13 EXE: company selector -> credential form -> SQLite.

Only disposable companies and credentials, no installed profiles or user data.
Input is sent ONLY while an owned application window has keyboard focus.
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
from standalone_accounting_identity import LocalCompanyIdentity
from standalone_accounting_restore import restore_standalone_accounting,_check_input
from operational_r3_candidate_exe_qa import windows_for,user32,WM_CLOSE,stop_owned_only

VK_RETURN=0x0D
VK_TAB=0x09
KEYEVENTF_KEYUP=0x0002
KEYEVENTF_UNICODE=0x0004

class KEYBDINPUT(ctypes.Structure):
    _fields_=[('wVk',ctypes.c_ushort),('wScan',ctypes.c_ushort),
              ('dwFlags',ctypes.c_ulong),('time',ctypes.c_ulong),
              ('dwExtraInfo',ctypes.c_void_p)]
class MOUSEINPUT(ctypes.Structure):
    _fields_=[('dx',ctypes.c_long),('dy',ctypes.c_long),
              ('mouseData',ctypes.c_ulong),('dwFlags',ctypes.c_ulong),
              ('time',ctypes.c_ulong),('dwExtraInfo',ctypes.c_void_p)]
class HARDWAREINPUT(ctypes.Structure):
    _fields_=[('uMsg',ctypes.c_ulong),('wParamL',ctypes.c_ushort),
              ('wParamH',ctypes.c_ushort)]
class _INPUTUNION(ctypes.Union):
    _fields_=[('ki',KEYBDINPUT),('mi',MOUSEINPUT),('hi',HARDWAREINPUT)]
class INPUT(ctypes.Structure):
    _fields_=[('type',ctypes.c_ulong),('u',_INPUTUNION)]

user32.SetForegroundWindow.argtypes=[ctypes.c_void_p]
user32.SetForegroundWindow.restype=ctypes.c_bool
user32.GetForegroundWindow.restype=ctypes.c_void_p
user32.SendInput.argtypes=(ctypes.c_uint,ctypes.POINTER(INPUT),ctypes.c_int)
user32.SendInput.restype=ctypes.c_uint
user32.keybd_event.argtypes=(ctypes.c_ubyte,ctypes.c_ubyte,ctypes.c_ulong,ctypes.c_ulong)

def press(vk):
    user32.keybd_event(vk,0,0,0)
    user32.keybd_event(vk,0,KEYEVENTF_KEYUP,0)

def type_unicode(value):
    for character in value:
        for released in (False,True):
            inp=INPUT()
            inp.type=1
            inp.u.ki=KEYBDINPUT(0,ord(character),KEYEVENTF_UNICODE |
                                 (KEYEVENTF_KEYUP if released else 0),0,None)
            if user32.SendInput(1,ctypes.byref(inp),ctypes.sizeof(inp))!=1:
                raise OSError('Synthetic Unicode keyboard injection failed')

def owned_window(process,title,seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline and process.is_running():
        matching=[entry for entry in windows_for(process) if title in entry[2]]
        if matching:return matching[0]
        time.sleep(.2)
    return None

def focus_owned(window):
    if not window:return False
    user32.SetForegroundWindow(window[0])
    time.sleep(.4)
    return user32.GetForegroundWindow()==window[0]

def main():
    exe=ROOT/'release'/'Madar-Accounting-Secure-Tax-R13-20261026.exe'
    results={}
    with tempfile.TemporaryDirectory(prefix='madar-r13-secure-user-') as tmp:
        scratch=Path(tmp)
        hub=scratch/'companies';hub.mkdir()
        registry=StandaloneCompanyRegistry(hub)
        company=registry.create_company('دفتر تست امنیت مدار')
        book=registry.company_data_directory(company['id'])
        auth=LocalCompanyIdentity(book)
        name='syntheticadmin'
        password='SecureSyntheticPassword2026'
        auth.add_user(name,password,'admin')
        env=os.environ.copy()
        for key,folder in (('APPDATA','appdata'),('LOCALAPPDATA','local'),('TEMP','tmp'),
                           ('TMP','tmp'),('WEBVIEW2_USER_DATA_FOLDER','webview')):
            root=scratch/folder;root.mkdir(exist_ok=True)
            env[key]=str(root)
        process=psutil.Popen([str(exe),'--companies-dir',str(hub)],
                              cwd=str(ROOT),env=env,
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            chooser=owned_window(process,'انتخاب شرکت',35)
            results['chooser']=bool(chooser)
            results['chooser_focus']=focus_owned(chooser)
            if results['chooser_focus']:press(VK_RETURN)
            login=owned_window(process,'ورود امن حسابداری',35)
            results['premium_login_window']=bool(login)
            results['login_focus']=focus_owned(login)
            if results['login_focus']:
                time.sleep(.35)
                type_unicode(name)
                press(VK_TAB)
                type_unicode(password)
                press(VK_RETURN)
            main_window=owned_window(process,'مدار | حسابداری مستقل',45)
            results['financial_window']=bool(main_window)
            result_book=book/'standalone-accounting.sqlite3'
            results['financial_database']=result_book.is_file()
            initial=list((book/'standalone-accounting-backups').glob('*.sqlite3')) if (
                book/'standalone-accounting-backups').is_dir() else []
            results['startup_backup']=bool(initial)
            if main_window:
                results['close_owned_window']=bool(
                    user32.PostMessageW(main_window[0],WM_CLOSE,0,0))
                try:process.wait(timeout=20)
                except psutil.TimeoutExpired:pass
            else:results['close_owned_window']=False
            results['normal_exit']=process.poll()==0
            all_backups=list((book/'standalone-accounting-backups').glob('*.sqlite3')) if (
                book/'standalone-accounting-backups').is_dir() else []
            results['exit_backup']=len(all_backups)>len(initial)
            results['backup_replay']=bool(all_backups) and all(
                _check_input(p)[0]==0 for p in all_backups)
            results['credential_companion']=bool(all_backups) and all(
                p.with_suffix('.users.json').is_file() for p in all_backups)
            if results['credential_companion']:
                recovered=scratch/'restored';recovered.mkdir()
                restore_standalone_accounting(all_backups[-1],
                    recovered/'standalone-accounting.sqlite3',
                    plaintext_acknowledged=True,offline_acknowledged=True)
                auth2=LocalCompanyIdentity(recovered)
                token=auth2.login(name,password)
                results['restored_credentials_valid']=(
                    auth2.require_session(token)['role']=='admin')
            else:results['restored_credentials_valid']=False
        finally:
            if process.is_running():stop_owned_only(process)
    print(json.dumps({'checks':results,'pass':sum(results.values()),
        'fail':sum(not v for v in results.values())},ensure_ascii=True))
    return 0 if results and all(results.values()) else 1

if __name__=='__main__':raise SystemExit(main())
