"""Native Windows pywebview sequential-company lifecycle smoke, synthetic only.

This runs two sequential GUI sessions inside this Python process, switching
after first mandatory backup. It never interacts with installed Madar windows.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from threading import Thread
import json
import os
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from standalone_accounting_company_registry import StandaloneCompanyRegistry
from standalone_accounting_desktop import main


def run():
    with TemporaryDirectory(prefix='madar-r10-native-company-') as tmp:
        root=Path(tmp)
        for key in ('APPDATA','LOCALAPPDATA','WEBVIEW2_USER_DATA_FOLDER','TEMP','TMP'):
            d=root/key.lower();d.mkdir(exist_ok=True)
            os.environ[key]=str(d)
        hub=root/'hub';hub.mkdir()
        registry=StandaloneCompanyRegistry(hub)
        companies=[registry.create_company('شرکت مصنوعی '+str(i)) for i in (1,2)]
        selections=[{'name':c['name'],'path':registry.company_data_directory(c['id'])} for c in companies]
        import webview
        native_create=webview.create_window
        windows=[]
        errors=[]
        def create_window(*args,**kwargs):
            window=native_create(*args,**kwargs)
            index=len(windows)
            windows.append(window)
            def close_after_load():
                def owned_action():
                    time.sleep(1)
                    try:
                        if index==0:
                            kwargs['js_api'].standaloneAccountingRequestCompanySwitch()
                        window.destroy()
                    except Exception as exc:
                        errors.append(str(exc))
                Thread(target=owned_action,daemon=True).start()
            window.events.loaded += close_after_load
            return window
        try:
            with patch('standalone_accounting_company_registry.pick_company_dialog',side_effect=selections),\
                 patch.object(webview,'create_window',side_effect=create_window):
                result=main(['--companies-dir',str(hub),'--site-dir',str(ROOT/'dist')])
        except Exception as exc:
            errors.append(repr(exc));result=-1
        report={'returnCode':result,'guiWindows':len(windows),'errors':errors,
                'bookPaths':[str(selection['path']) for selection in selections],
                'backups':[len(list(selection['path'].rglob('standalone-accounting-auto-*.sqlite3')))
                           for selection in selections]}
        print(json.dumps(report,ensure_ascii=True))
        return 0 if result==0 and len(windows)==2 and not errors and all(n>=2 for n in report['backups']) else 1


if __name__=='__main__':raise SystemExit(run())
