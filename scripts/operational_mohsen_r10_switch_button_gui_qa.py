"""Click the actual R10 ribbon company-switch control in isolated pywebview."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from threading import Thread, Event
import json
import os
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from standalone_accounting_company_registry import StandaloneCompanyRegistry
from standalone_accounting_desktop import main


def run():
    with TemporaryDirectory(prefix='madar-r10-ribbon-switch-') as scratch:
        root=Path(scratch)
        for key in ('APPDATA','LOCALAPPDATA','WEBVIEW2_USER_DATA_FOLDER','TEMP','TMP'):
            folder=root/key.lower();folder.mkdir(exist_ok=True)
            os.environ[key]=str(folder)
        hub=root/'companies';hub.mkdir()
        registry=StandaloneCompanyRegistry(hub)
        selection=[]
        for name in ('آزمون یک','آزمون دو'):
            company=registry.create_company(name)
            selection.append({'name':name,'path':registry.company_data_directory(company['id'])})
        import webview
        original_create=webview.create_window
        windows=[];checks=[];errors=[]
        def intercept_create(*args,**kwargs):
            window=original_create(*args,**kwargs)
            index=len(windows)
            windows.append(window)
            closed=Event()
            window.events.closed+=closed.set
            def loaded():
                def act():
                    try:
                        if index==0:
                            ready=False
                            for _ in range(50):
                                ready=window.evaluate_js("(function(){const b=document.querySelector('.sac-ribbon-quick button[title*=\\\"انتخاب‌گر\\\"]');return !!b&&!b.disabled})()")
                                if ready:break
                                time.sleep(.12)
                            checks.append({'switch_button_visible':bool(ready)})
                            if ready:
                                clicked=window.evaluate_js("""
                                  (function(){
                                    window.confirm=()=>true;
                                    window.alert=(msg)=>{window.__qaSwitchAlert=String(msg);};
                                    const button=document.querySelector('.sac-ribbon-quick button[title*="انتخاب‌گر"]');
                                    if(!button)return false;
                                    button.click();
                                    return true;
                                  })()
                                """)
                                checks.append({'clicked':bool(clicked)})
                            if not closed.wait(7):
                                checks.append({'backend_requested_switch':bool(kwargs['js_api']._switch_requested),
                                               'backend_window_bound':kwargs['js_api']._native_window is window})
                                try:
                                    checks.append({'frontend_alert':window.evaluate_js('window.__qaSwitchAlert||""')})
                                except Exception as exc:
                                    checks.append({'frontend_alert_read_error':repr(exc)})
                                errors.append('Ribbon company switch did not close its window')
                                window.destroy()
                        else:
                            window.destroy()
                    except Exception as exc:
                        errors.append(repr(exc))
                        try:window.destroy()
                        except Exception:pass
                Thread(target=act,daemon=True).start()
            window.events.loaded+=loaded
            return window
        try:
            with patch('standalone_accounting_company_registry.pick_company_dialog',side_effect=selection),\
                 patch.object(webview,'create_window',side_effect=intercept_create):
                code=main(['--companies-dir',str(hub),'--site-dir',str(ROOT/'dist')])
        except Exception as exc:
            code=-1;errors.append(repr(exc))
        result={'result':code,'windows':len(windows),'checks':checks,'errors':errors,
                'backups':[len(list(x['path'].rglob('standalone-accounting-auto-*.sqlite3')))
                           for x in selection]}
        print(json.dumps(result,ensure_ascii=True))
        return 0 if code==0 and len(windows)==2 and all(checks[0].values()) and len(checks)>1 and checks[1]['clicked'] and not errors and all(x>=2 for x in result['backups']) else 1


if __name__=='__main__':raise SystemExit(run())
