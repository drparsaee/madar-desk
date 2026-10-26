"""Read-only pywebview GUI smoke on the isolated restored-BAK trial ledger.

The original SQL db_1405, historical backups, prior app company roots and all
production identity files are never opened. No GUI financial commands sent.
"""
from pathlib import Path
import json
import sys
import time
from threading import Thread

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from standalone_accounting_identity import LocalCompanyIdentity
from standalone_accounting_desktop import AccountingDesktopAPI,serve_accounting_page


def run():
    root=Path(__file__).resolve().parents[1]
    trial=root/'.private-parsian-staging-20261026'/'migration-experiment-20261026'/'parsian-rial-gl-import-disposable'
    credential=trial.parent/'R17-TRIAL-LOGIN-PRIVATE.txt'
    secret=next(x.partition(': ')[2] for x in credential.read_text('utf-8').splitlines()
                if x.startswith('رمز عبور آزمایشی: '))
    store=LocalCompanyIdentity(trial)
    token=store.login('trialadmin',secret)
    user=store.require_session(token)
    api=AccountingDesktopAPI(trial,company_name='آزمایش بکاپ ۱۵:۱۵',
        identity_store=store,identity_token=token,authenticated_user=user)
    snap=api.standaloneAccountingRead()
    checks={}
    checks['no_financial_initial_change']=snap['revision']==249
    checks['imported_journals']=len(snap['view']['journals'])==124
    checks['restored_historical_invoices']=snap['view']['parsianMigration']['historicalInvoiceGroups']==66
    checks['current_user_title']=snap['currentUser']['jobTitle']=='مدیر ارشد'
    windows=[]
    def js(src):return windows[0].evaluate_js('(function(){'+src+'})()')
    def until(src,timeout=10):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:
                if js(src) is True:return True
            except Exception:pass
            time.sleep(.2)
        return False
    server=serve_accounting_page(root/'dist')
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    errors=[]
    try:
        import webview
        def verify():
            try:
                checks['overview_loaded']=until('return document.querySelector(".sac-header h1")?.textContent==="داشبورد"')
                checks['title_next_to_username']=until('return document.querySelector(".sac-ribbon-user")?.textContent.includes("trialadmin") && document.querySelector(".sac-ribbon-user")?.textContent.includes("مدیر ارشد")')
                checks['parsian_archive_summary']=until('return document.body.textContent.includes("مانده بدهکاران تاریخی")')
                checks['management_charts_loaded']=until('return document.querySelectorAll(".madar-dashboard-chart").length>=2')
                checks['navigate_to_archive']=bool(js('''
                    const tabs=[...document.querySelectorAll('.sac-ribbon-tabs button')];
                    const b=tabs.find(x=>x.textContent.includes('گزارش‌ها و سوابق'));
                    if(!b)return false;b.click();return true;
                '''))
                checks['archive_toolbar_visible']=until('return [...document.querySelectorAll(".sac-ribbon-tools button")].some(e=>e.textContent.includes("سوابق انتقالی پارسیان"))')
                checks['open_archive']=bool(js('''
                    const b=[...document.querySelectorAll('.sac-ribbon-tools button')].find(
                      e=>e.textContent.includes('سوابق انتقالی پارسیان'));
                    if(!b)return false;b.click();return true;
                '''))
                checks['archive_tab_loaded']=until('return document.querySelector(".sac-header h1")?.textContent.includes("پارسیان")')
            except Exception as exc:errors.append(repr(exc))
            finally:windows[0].destroy()
        window=webview.create_window('مدار | آزمون واقعی آرشیو پارسیان R17',
            f'http://127.0.0.1:{server.server_port}/accounting.html',
            width=1440,height=900,js_api=api)
        windows.append(window)
        window.events.loaded+=verify
        webview.start()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
        store.logout(token)
    # Revocations occur before the final check; a separate standalone store
    # bypasses no real company security, and can verify SQLite revision only.
    from standalone_accounting import StandaloneAccountingStore
    ledger=StandaloneAccountingStore(trial/'standalone-accounting.sqlite3',default_currency='RIAL')
    refreshed=ledger.read(actor='qa',accounts={'qa':{'username':'qa','role':'admin'}})
    checks['read_only_no_revision_change']=refreshed['revision']==snap['revision']
    print(json.dumps({'pass':sum(checks.values()),'fail':sum(not v for v in checks.values())+len(errors),
                      'checks':checks,'errors':errors},ensure_ascii=False))
    return 0 if checks and all(checks.values()) and not errors else 1


if __name__=='__main__':raise SystemExit(run())
