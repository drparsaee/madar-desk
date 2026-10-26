"""Real pywebview invoice navigation smoke on synthetic temporary company only."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import json
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from standalone_accounting_desktop import AccountingDesktopAPI,serve_accounting_page

checks={}
errors=[]
windows=[]
observed={}
def js(code):
    return windows[0].evaluate_js('(function(){'+code+'})()')
def until(code,seconds=8):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            if js(code) is True:return True
        except Exception:pass
        time.sleep(.15)
    return False
def ck(key,value):
    checks[key]=bool(value)
def click_contains(selector,label):
    return js('const b=[...document.querySelectorAll('+json.dumps(selector)+')].find('
              'e=>e.textContent.includes('+json.dumps(label,ensure_ascii=False)+'));'
              'if(!b)return false;b.click();return true;')
def run():
    project=Path(__file__).resolve().parents[1]
    with TemporaryDirectory(prefix='madar-r15-gui-more-') as temporary:
        api=AccountingDesktopAPI(Path(temporary),company_name='آزمون رابط فاکتور')
        api.standaloneAccountingRead()
        api.standaloneAccountingCommand({'expectedRevision':0,'command':{
            'type':'party.register','eventId':'qa-r15-customer-event',
            'partyId':'qa-r15-customer','name':'مشتری تست رابط','kind':'customer'}})
        server=serve_accounting_page(project/'dist')
        thread=Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            import webview
            def verify():
                try:
                    ck('loaded',until('return !!document.querySelector(".sac-root")'))
                    ck('ribbon_invoice',click_contains('.sac-ribbon-tabs button','فاکتورها و سفارش‌ها'))
                    ck('invoice_tab',click_contains('.sac-ribbon-tools button','فاکتورهای فروش'))
                    ck('list_without_form',until('return !!document.querySelector(".sac-invoice-list-help")&&!document.querySelector(".sac-invoice-editor")'))
                    ck('compact_invoice_mode',js('return document.querySelector(".sac-root")?.classList.contains("sac-invoice-work-mode")'))
                    ck('invoice_search_visible',js('return !!document.querySelector(".sac-invoice-list-search input[type=search]")'))
                    ck('four_status_choices',js('return document.querySelectorAll(".sac-invoice-status-filters button").length===4'))
                    ck('start_new',click_contains('.sac-workflow-actions button','ثبت فاکتور جدید'))
                    ck('form_shows_back',until('return !!document.querySelector(".sac-invoice-editor")&&!!document.querySelector(".sac-ribbon-back")'))
                    ck('customer_search_focus',until('return document.activeElement?.getAttribute("aria-label")==="جست‌وجوی مشتری یا تأمین‌کننده"'))
                    ck('auto_number',until('return /^INV-[0-9]{4}-[0-9]{4}$/.test(document.querySelector(".sac-id-input input")?.value||"")'))
                    observed['number']=js('return document.querySelector(".sac-id-input input")?.value || "MISSING"')
                    observed['form_start']=js('return document.querySelector(".sac-invoice-editor")?.innerHTML.slice(0,1300)||"NO_FORM"')
                    ck('tools_collapsed',js('return [...document.querySelectorAll(".sac-invoice-editor details")].length>=3&&[...document.querySelectorAll(".sac-invoice-editor details")].every(d=>!d.open)'))
                    ck('form_command_bar',js('return !!document.querySelector(".sac-invoice-commandbar button[type=submit]") && !!document.querySelector(".sac-invoice-commandbar button[type=button]")'))
                    ck('five_primary_columns',js('return document.querySelectorAll(".sac-invoice-columns>span").length===5'))
                    ck('summary_visible',js('return !!document.querySelector(".sac-invoice-summary .sac-live-total")'))
                    ck('row_advanced_closed',js('return document.querySelector(".sac-row-advanced")?.open===false'))
                    ck('row_advanced_toggle',js('const d=document.querySelector(".sac-row-advanced");if(!d)return false;d.open=true;return d.querySelectorAll("select").length===2'))
                    ck('row_account_available',js('return !!document.querySelector(".sac-row-advanced select[data-invoice-col]")'))
                    ck('row_advanced_close',js('const d=document.querySelector(".sac-row-advanced");if(!d)return false;d.open=false;return !d.open'))
                    ck('dirty_fill',js('const e=document.querySelector(".sac-invoice-line input[data-invoice-col=\\"0\\"]");if(!e)return false;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(e,"آزمایش چاپ");e.dispatchEvent(new Event("input",{bubbles:true}));return true;'))
                    ck('cancel_rejected',js('window.confirm=()=>false;document.querySelector(".sac-ribbon-back")?.click();return true'))
                    ck('draft_kept',until('return !!document.querySelector(".sac-invoice-editor")'))
                    ck('cancel_accepted',js('window.confirm=()=>true;document.querySelector(".sac-ribbon-back")?.click();return true'))
                    ck('returned_list',until('return !document.querySelector(".sac-invoice-editor")&&!!document.querySelector(".sac-invoice-list-help")'))
                    ck('no_financial_write',api.standaloneAccountingRead()['revision']==1)
                    ck('reopen_after_cancel',click_contains('.sac-workflow-actions button','ثبت فاکتور جدید'))
                    ck('reopened_editor',until('return !!document.querySelector(".sac-invoice-editor")'))
                    ck('enter_from_price_adds_row',js('const input=document.querySelectorAll(".sac-invoice-line input[data-invoice-col]")[2];if(!input)return false;input.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true,cancelable:true}));return true;'))
                    ck('new_row_focused',until('return document.querySelectorAll(".sac-invoice-line").length===2 && document.activeElement?.dataset.invoiceRow==="1"'))
                    ck('remove_extra_empty_row',js('const last=[...document.querySelectorAll(".sac-invoice-line")].at(-1);const b=last?.querySelector("button.sac-remove");if(!b)return false;b.click();return true'))
                    ck('back_to_single_row',until('return document.querySelectorAll(".sac-invoice-line").length===1'))
                    ck('choose_customer',js('const e=document.querySelector(".sac-invoice-editor select[required]");if(!e)return false;Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,"value").set.call(e,"qa-r15-customer");e.dispatchEvent(new Event("change",{bubbles:true}));return true;'))
                    ck('description_new',js('const e=document.querySelector(".sac-invoice-line input[data-invoice-col=\\"0\\"]");if(!e)return false;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(e,"چاپ تستی");e.dispatchEvent(new Event("input",{bubbles:true}));return true;'))
                    ck('quantity_new',js('const e=document.querySelector(".sac-invoice-line input[data-invoice-col=\\"1\\"]");if(!e)return false;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(e,"2");e.dispatchEvent(new Event("input",{bubbles:true}));return true;'))
                    ck('price_new',js('const e=document.querySelector(".sac-invoice-line input[data-invoice-col=\\"2\\"]");if(!e)return false;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(e,"500000");e.dispatchEvent(new Event("input",{bubbles:true}));return true;'))
                    ck('total_updated',until('return document.querySelector(".sac-invoice-line-total")?.textContent.includes("۱٬۰۰۰٬۰۰۰")===true'))
                    ck('submit_draft',js('const b=document.querySelector(".sac-invoice-editor button[type=submit]");if(!b)return false;b.click();return true'))
                    ck('saved_and_returned',until('return !document.querySelector(".sac-invoice-editor")&&!!document.querySelector(".sac-invoice-list-help")',12))
                    result=api.standaloneAccountingRead()
                    ck('database_draft_saved',len(result['view']['invoices'])==1 and
                       next(iter(result['view']['invoices'].values()))['status']=='draft')
                    ck('save_did_not_post_journal',len(result['view']['journals'])==0)
                    ck('draft_counter_updated',until('return [...document.querySelectorAll(".sac-invoice-status-filters button")].some(b=>b.textContent.includes("پیش‌نویس")&&b.textContent.includes("۱"))'))
                    ck('filter_draft_only',click_contains('.sac-invoice-status-filters button','پیش‌نویس'))
                    ck('draft_filtered_visible',until('return document.querySelectorAll(".sac-panel tbody tr").length>=1'))
                    ck('filter_issued_only',click_contains('.sac-invoice-status-filters button','صادرشده'))
                    ck('issued_filter_empty',until('return document.body.textContent.includes("فاکتوری مطابق فیلتر پیدا نشد")'))
                    ck('restore_all_status',click_contains('.sac-invoice-status-filters button','همه'))
                except Exception as exc:errors.append(repr(exc))
                finally:windows[0].destroy()
            window=webview.create_window('مدار | تست بازگشت فاکتور',
                f'http://127.0.0.1:{server.server_port}/accounting.html',
                width=1380,height=900,js_api=api)
            windows.append(window)
            window.events.loaded+=verify
            webview.start()
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)
    report={'pass':sum(checks.values()),'fail':sum(not value for value in checks.values())+len(errors),
            'checks':checks,'observed':observed,'errors':errors}
    target=project/'.qa-r15-final-user-gui-report.json'
    if target.exists():raise RuntimeError('Refusing to overwrite existing GUI report')
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
    return 0 if report['fail']==0 and checks else 1
if __name__=='__main__':raise SystemExit(run())
