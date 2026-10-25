"""Isolated, real pywebview GUI acceptance, never pointed at APPDATA or live books.

This tests the same built Vite frontend and the real standalone API as the EXE.
It is a SOURCE-HOSTED GUI test, not instrumentation of the packaged EXE.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from threading import Thread
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / ".qa-jalali-live-gui-20261024"
if SCRATCH.exists():
    raise SystemExit("Refusing to reuse an existing synthetic GUI test directory")
SCRATCH.mkdir()
for name in ("appdata", "localappdata", "webview2", "temp"):
    (SCRATCH / name).mkdir()
os.environ["APPDATA"] = str(SCRATCH / "appdata")
os.environ["LOCALAPPDATA"] = str(SCRATCH / "localappdata")
os.environ["WEBVIEW2_USER_DATA_FOLDER"] = str(SCRATCH / "webview2")
os.environ["TEMP"] = os.environ["TMP"] = str(SCRATCH / "temp")

sys.path.insert(0, str(ROOT))
from standalone_accounting_desktop import AccountingDesktopAPI, serve_accounting_page
from standalone_accounting_auto_backup import AutomaticStandaloneBackups

api = AccountingDesktopAPI(SCRATCH / "financial")
backup = AutomaticStandaloneBackups(api.path.parent, interval_seconds=2,
                                    max_backups=3, plaintext_acknowledged=True)
checks = {}
events = []
window_ref = []


def check(name, evidence, *, detail=None):
    checks[name] = {"status": "PASS" if evidence else "FAIL"}
    if detail is not None:
        checks[name]["evidence"] = detail
    return evidence


def evaluate(code):
    return window_ref[0].evaluate_js("(function(){" + code + "})()")


def until(code, *, seconds=8):
    deadline = time.monotonic() + seconds
    observed = None
    while time.monotonic() < deadline:
        try:
            observed = evaluate(code)
            if observed is True:
                return True
        except Exception as exc:
            observed = type(exc).__name__ + ": " + str(exc)[:120]
        time.sleep(.20)
    events.append({"timeout": code[:90], "last": observed})
    return False


def navigate(label):
    return evaluate("""
      const b=[...document.querySelectorAll('.sac-sidebar nav button')]
        .find(x=>x.textContent.includes(%s));
      if(!b)return false;
      b.click(); return true;
    """ % json.dumps(label, ensure_ascii=False))


def fill(panel_title, field_label, value):
    return evaluate("""
      const sec=[...document.querySelectorAll('section.sac-panel')]
        .find(s=>s.querySelector('.sac-panel-title h2')?.textContent.includes(%s));
      if(!sec)return false;
      const label=[...sec.querySelectorAll('label.sac-field')]
        .find(el=>el.querySelector('span')?.textContent.includes(%s));
      const input=label?.querySelector('input,select,textarea');
      if(!input)return false;
      const value=%s;
      const ctor=input.tagName==='SELECT'?HTMLSelectElement:
        input.tagName==='TEXTAREA'?HTMLTextAreaElement:HTMLInputElement;
      Object.getOwnPropertyDescriptor(ctor.prototype,'value').set.call(input,value);
      input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input',
                                     {bubbles:true}));
      return true;
    """ % (json.dumps(panel_title,ensure_ascii=False),
           json.dumps(field_label,ensure_ascii=False),
           json.dumps(str(value),ensure_ascii=False)))


def click_button(partial, *, panel=None):
    panel_js = ("""
      const scope=[...document.querySelectorAll('section.sac-panel')].find(
        s=>s.querySelector('.sac-panel-title h2')?.textContent.includes(%s));
    """ % json.dumps(panel,ensure_ascii=False)) if panel else "const scope=document;"
    return evaluate(panel_js + """
      if(!scope)return false;
      const b=[...scope.querySelectorAll('button')].find(x=>
        x.textContent.includes(%s)&&!x.disabled);
      if(!b)return false;b.click();return true;
    """ % json.dumps(partial,ensure_ascii=False))


def submit_form(panel):
    return evaluate("""
      const sec=[...document.querySelectorAll('section.sac-panel')]
        .find(s=>s.querySelector('.sac-panel-title h2')?.textContent.includes(%s));
      const form=sec?.querySelector('form');
      if(!form)return false;
      if(!form.reportValidity())return false;
      form.requestSubmit();return true;
    """ % json.dumps(panel,ensure_ascii=False))


def GUI_run():
    try:
        check("gui_dom_mounted", until("return !!document.querySelector('.sac-root')"))
        check("font_and_rtl", evaluate("""
          return !!document.querySelector('.sac-root[dir=rtl]') &&
            !!document.querySelector('nav[aria-label="ناوبری میز حسابداری"]');
        """))
        check("initial_rial", until("""
          return !![...document.querySelectorAll('.sac-sidebar-footer')]
             .find(e=>e.textContent.includes('ریال'));
        """))
        check("no_task_manager", evaluate("""
          return !document.querySelector('.kanban,.task-card') &&
            !document.querySelector('button[aria-label*="تسک"]');
        """))
        check("go_parties", navigate("اشخاص"))
        check("party_form_present", until("""
          return !![...document.querySelectorAll('.sac-panel-title h2')]
            .find(x=>x.textContent.includes('ثبت شخص جدید'));
        """))
        for field,val in (("شناسه","qa.customer"),("نام","مشتری آزمایشی ویندوز")):
            check("party_fill_"+field, fill("ثبت شخص جدید", field, val))
        check("party_submit", submit_form("ثبت شخص جدید"))
        check("party_db_saved", until("""
          return [...document.querySelectorAll('.sac-table-wrap tr')]
            .some(t=>t.textContent.includes('qa.customer'));
        """))
        check("go_proforma", navigate("پیش‌فاکتور مستقل"))
        check("proforma_form_present", until("""
          return [...document.querySelectorAll('.sac-panel-title h2')]
            .some(x=>x.textContent.includes('ایجاد پیش‌فاکتور مستقل'));
        """))
        check("jalali_input_not_gregorian",evaluate("""
          const fields=[...document.querySelectorAll('input[aria-label="تاریخ شمسی"]')];
          return fields.length>0 && fields.every(f=>f.type==='text') &&
            fields.some(f=>/^۱۴۰۵\//.test(f.value)) &&
            ![...document.querySelectorAll('input[type="date"]')].length;
        """))
        details = [
            ("شناسه پیش‌فاکتور","qa.proforma"),
            ("مشتری","qa.customer"),
            ("تخفیف","1"),
            ("مالیات صریح","0"),
            ("اعتبار تا (اختیاری)","۱۴۰۵/۰۸/۰۶"),
            ("شرایط و توضیحات","پیشنهاد آزمایشی بدون تسک"),
            ("شرح","چاپ جلد آزمایشی"),
            ("تعداد","3"),
            ("قیمت واحد","251"),
        ]
        for field, value in details:
            panel = "ایجاد پیش‌فاکتور مستقل"
            check("proforma_fill_"+field,fill(panel,field,value))
        check("proforma_submit",submit_form("ایجاد پیش‌فاکتور مستقل"))
        check("proforma_visible",until("""
          return [...document.querySelectorAll('.sac-table-wrap tr')]
             .some(t=>t.textContent.includes('qa.proforma'));
        """))
        snap = api.standaloneAccountingRead()
        record = snap["view"]["proformas"].get("qa.proforma",{})
        check("jalali_to_iso_persisted",record.get("validUntil")=="2026-10-28",
              detail=record.get("validUntil"))
        check("proforma_amount_exact",record.get("total")==752,
              detail=record.get("total"))
        check("no_gl_before_issue",len(snap["view"]["journals"])==0)

        # Browser canvas and PDF/PNG generation must be verified without
        # actually saving into the user's Downloads folder.
        evaluate("""
          window.__qaDownloads=[];
          const original=HTMLAnchorElement.prototype.click;
          HTMLAnchorElement.prototype.click=function(){
            window.__qaDownloads.push({filename:this.download,url:this.href});
          };
          window.__qaOriginalAnchorClick=original;
          return true;
        """)
        check("pdf_button_click", click_button("PDF پیش‌فاکتور",
                                                panel="پیش‌فاکتورهای فروش مستقل"))
        check("pdf_generated_in_webview", until("""
          return Array.isArray(window.__qaDownloads) &&
            window.__qaDownloads.some(x=>x.filename.endsWith('.pdf') &&
              x.filename.includes('proforma'));
        """))
        try:
            details=evaluate("""
              const item=window.__qaDownloads.find(x=>x.filename.endsWith('.pdf'));
              if(!item)return null;
              window.__qaPdfResult=null;
              fetch(item.url).then(x=>x.arrayBuffer()).then(raw=>{
                const bytes=new Uint8Array(raw);
                window.__qaPdfResult={length:bytes.length,
                  magic:String.fromCharCode(...bytes.slice(0,8))};
              }).catch(err=>window.__qaPdfResult={error:String(err)});
              return true;
            """)
            check("pdf_bytes_present",until("""
              return !!window.__qaPdfResult && window.__qaPdfResult.length>1000
                && window.__qaPdfResult.magic.startsWith('%PDF-');
            """))
        except Exception as exc:
            check("pdf_bytes_present",False,detail=str(exc))
        if not click_button("ثبت ارسال",panel="پیش‌فاکتورهای فروش مستقل"):
            check("send_click",False)
        else:
            check("send_click",True)
            check("sent_state",until("""
              return [...document.querySelectorAll('.sac-table-wrap tr')]
                .some(t=>t.textContent.includes('qa.proforma') &&
                  t.textContent.includes('ارسال‌شده'));
            """))
        check("accept_click",click_button("ثبت پذیرش",
                                           panel="پیش‌فاکتورهای فروش مستقل"))
        check("accepted_state",until("""
          return [...document.querySelectorAll('.sac-table-wrap tr')]
            .some(t=>t.textContent.includes('qa.proforma') &&
              t.textContent.includes('پذیرفته‌شده'));
        """))
        # Conversion id is a controlled input in the proforma table row.
        check("invoice_target_fill", evaluate("""
          const i=[...document.querySelectorAll('input')]
            .find(x=>x.getAttribute('aria-label')?.includes('شماره فاکتور مقصد qa.proforma'));
          if(!i)return false;
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')
            .set.call(i,'qa.invoice');
          i.dispatchEvent(new Event('input',{bubbles:true}));return true;
        """))
        check("convert_click", click_button("تبدیل به فاکتور",
                                             panel="پیش‌فاکتورهای فروش مستقل"))
        check("invoice_tab",until("""
          return document.querySelector('.sac-header h1')?.textContent
            .includes('فاکتورهای فروش')===true;
        """))
        check("invoice_created",until("""
          return [...document.querySelectorAll('.sac-table-wrap tr')]
            .some(t=>t.textContent.includes('qa.invoice'));
        """))
        check("approve_click",click_button("تأیید",panel="فاکتورهای فروش"))
        check("approved_state",until("""
          return [...document.querySelectorAll('.sac-table-wrap tr')]
            .some(t=>t.textContent.includes('qa.invoice') &&
              t.textContent.includes('تأییدشده'));
        """))
        check("issue_click",click_button("صدور سند",panel="فاکتورهای فروش"))
        check("issued_state",until("""
          return [...document.querySelectorAll('.sac-table-wrap tr')]
            .some(t=>t.textContent.includes('qa.invoice') &&
              t.textContent.includes('صادرشده'));
        """))
        check("settle_nav_click",click_button("تسویه",panel="فاکتورهای فروش"))
        check("settlement_form",until("""
          return [...document.querySelectorAll('.sac-panel-title h2')]
            .some(x=>x.textContent.includes('تسویه سند صادرشده'));
        """))
        for field,val in (("مبلغ تسویه","252"),("حساب صندوق / بانک","1010")):
            check("settlement_fill_"+field,fill("تسویه سند صادرشده",field,val))
        check("settlement_submit",submit_form("تسویه سند صادرشده"))
        check("receipt_visible",until("""
          return [...document.querySelectorAll('.sac-panel-title h2')]
            .some(x=>x.textContent.includes('دریافت‌ها و پرداخت‌ها')) &&
            [...document.querySelectorAll('.sac-table-wrap tr')]
              .some(t=>t.textContent.includes('252') || t.textContent.includes('۲۵۲'));
        """))

        final=api.standaloneAccountingRead()
        view=final["view"]
        check("accounting_ar_exact",view["parties"]["qa.customer"]["receivable"]==500,
              detail=view["parties"]["qa.customer"]["receivable"])
        check("ledger_journals_two",len(view["journals"])==2,
              detail=len(view["journals"]))
        check("host_financial_reports",view.get("financialReports",{}).get("reconciled") is True)
        check("independent_no_tasks",
              not any((SCRATCH/"financial"/f).exists()
                      for f in ("tasks.json","madar-unified.sqlite3","finance.json")))
    except BaseException as exc:
        checks["gui_unhandled"]={"status":"FAIL","error":repr(exc),
                                  "traceback":traceback.format_exc()[-3000:]}
    finally:
        try:
            window_ref[0].destroy()
        except BaseException as exc:
            checks["gui_close"]={"status":"FAIL","error":repr(exc)}


def main():
    api.standaloneAccountingRead()
    initial=backup.backup_now()
    check("startup_backup",initial.is_file())
    backup.start()
    server=serve_accounting_page(ROOT/"dist")
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        import webview
        window=webview.create_window("مدار | تست عملیاتی پیش‌فاکتور",
               f"http://127.0.0.1:{server.server_port}/accounting.html",
               width=1450,height=925,js_api=api)
        window_ref.append(window)
        window.events.loaded += GUI_run
        webview.start()
    finally:
        backup.stop()
        try:
            backup.backup_now()
            check("final_backup",True)
        except Exception as exc:
            check("final_backup",False,detail=str(exc))
        files=list((SCRATCH/"financial"/"standalone-accounting-backups").glob("*.sqlite3"))
        check("backup_rotation_3",len(files)<=3 and len(files)>=2,
              detail=len(files))
        server.shutdown();server.server_close();thread.join(timeout=5)
        report={"mode":"real pywebview + built Vite + real SQLite API",
                "synthetic_root":str(SCRATCH),"checks":checks,"events":events}
        (SCRATCH/"operational-report.json").write_text(
            json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"pass":sum(v["status"]=="PASS" for v in checks.values()),
                          "fail":sum(v["status"]!="PASS" for v in checks.values()),
                          "report":str(SCRATCH/"operational-report.json")},
                         ensure_ascii=False))
    return 0 if all(v["status"]=="PASS" for v in checks.values()) else 1


if __name__=="__main__":
    sys.exit(main())
