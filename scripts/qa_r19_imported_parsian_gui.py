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
    trial=root/'.private-parsian-staging-20261026'/'r19-1405'/'migration-experiment-20261026'/'parsian-rial-gl-import-disposable'
    credential=trial.parent/'R19-TRIAL-LOGIN-PRIVATE.txt'
    secret=next(x.partition(': ')[2] for x in credential.read_text('utf-8').splitlines()
                if x.startswith('رمز عبور آزمایشی: '))
    store=LocalCompanyIdentity(trial)
    token=store.login('trialadmin',secret)
    user=store.require_session(token)
    api=AccountingDesktopAPI(trial,company_name='آزمایش هر دو سال پارسیان R19',
        identity_store=store,identity_token=token,authenticated_user=user)
    snap=api.standaloneAccountingRead()
    checks={}
    checks['no_financial_initial_change']=snap['revision']==251
    checks['imported_journals']=len(snap['view']['journals'])==125
    checks['restored_historical_invoices']=snap['view']['parsianMigration']['historicalInvoiceGroups']==67
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
    diagnostics={}
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
                diagnostics['canAdminHost']=snap['capabilities']['canAdmin']
                diagnostics['rawExplorer']=js('return document.querySelector(".pra-root")?.textContent?.slice(0,140)||"ABSENT"')
                diagnostics['hasSelect']=bool(js('return !!document.querySelector(".pra-head select")'))
                checks['two_source_years_loaded']=until('return document.querySelector(".pra-head select")?.options.length===2')
                checks['all_1405_tables_listed']=until('return document.querySelectorAll(".pra-table-list button").length===98')
                checks['year1404_factor_rows']=api.standaloneAccountingParsianArchiveRows('1404','tbl_Factor',0)['total']==327
                checks['open_raw_source_table']=bool(js('''
                    const b=[...document.querySelectorAll('.pra-table-list button')].find(
                      e=>e.textContent.includes('tbl_Factor'));
                    if(!b)return false;b.click();return true;
                '''))
                checks['source_page_has_40_rows']=until('return document.querySelectorAll(".pra-record").length===40')
                checks['select_1404_in_app']=bool(js('''
                    const e=document.querySelector('.pra-head select');
                    if(!e)return false;
                    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(e,'1404');
                    e.dispatchEvent(new Event('change',{bubbles:true}));return true;
                '''))
                checks['all_1404_tables_listed']=until('return document.querySelectorAll(".pra-table-list button").length===126')
                checks['open_1404_factor_table']=bool(js('''
                    const b=[...document.querySelectorAll('.pra-table-list button')].find(
                      e=>e.textContent.includes('tbl_Factor'));
                    if(!b)return false;b.click();return true;
                '''))
                checks['1404_rows_rendered']=until('return document.querySelectorAll(".pra-record").length===40')
            except Exception as exc:errors.append(repr(exc))
            finally:windows[0].destroy()
        window=webview.create_window('مدار | آزمون واقعی آرشیو پارسیان R19',
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
                      'checks':checks,'errors':errors,'diagnostics':diagnostics},ensure_ascii=True))
    return 0 if checks and all(checks.values()) and not errors else 1


if __name__=='__main__':raise SystemExit(run())
