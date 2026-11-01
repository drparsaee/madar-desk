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
SCRATCH = ROOT / ".qa-mohsen-ux40-gui-20261025"
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


def fill_operational(form_title, field_label, value):
    return evaluate("""
      const sec=[...document.querySelectorAll('section.sac-operational-form')]
        .find(s=>s.querySelector('h3')?.textContent.includes(%s));
      if(!sec)return false;
      const label=[...sec.querySelectorAll('label.sac-field')]
        .find(x=>x.querySelector('span')?.textContent.includes(%s));
      const control=label?.querySelector('input,select,textarea');
      if(!control)return false;
      const ctor=control.tagName==='SELECT'?HTMLSelectElement:
        control.tagName==='TEXTAREA'?HTMLTextAreaElement:HTMLInputElement;
      Object.getOwnPropertyDescriptor(ctor.prototype,'value')
        .set.call(control,%s);
      control.dispatchEvent(new Event(control.tagName==='SELECT'?'change':'input',
        {bubbles:true}));
      return true;
    """ % (json.dumps(form_title,ensure_ascii=False),
           json.dumps(field_label,ensure_ascii=False),
           json.dumps(str(value),ensure_ascii=False)))


def submit_operational(form_title):
    return evaluate("""
      const sec=[...document.querySelectorAll('section.sac-operational-form')]
        .find(s=>s.querySelector('h3')?.textContent.includes(%s));
      const form=sec?.querySelector('form');
      if(!form||!form.reportValidity())return false;
      form.requestSubmit();return true;
    """ % json.dumps(form_title,ensure_ascii=False))


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
        check("party_edit_open",evaluate("""
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(x=>x.textContent.includes('qa.customer'));
          const b=[...tr.querySelectorAll('button')]
            .find(x=>x.textContent.includes('ویرایش مشخصات'));
          if(!b)return false;b.click();return true;
        """))
        check("party_edit_name",fill("ویرایش شخص","نام","مشتری اصلاح‌شده"))
        check("party_edit_credit",fill("ویرایش شخص","سقف اعتبار مشتری","2000"))
        check("party_edit_reason",fill("ویرایش شخص","علت ویرایش","تأیید شناسه و نام مشتری"))
        check("party_update_submit",submit_form("ویرایش شخص"))
        check("party_update_persisted",until("""
          return [...document.querySelectorAll('.sac-table-wrap tr')]
            .some(t=>t.textContent.includes('qa.customer')&&
              t.textContent.includes('مشتری اصلاح‌شده'));
        """))
        check("go_proforma", navigate("پیش‌فاکتور مستقل"))
        check("proforma_form_present", until("""
          return [...document.querySelectorAll('.sac-panel-title h2')]
            .some(x=>x.textContent.includes('ایجاد پیش‌فاکتور مستقل'));
        """))
        check("jalali_input_not_gregorian",evaluate("""
          const fields=[...document.querySelectorAll('input[aria-label="تاریخ شمسی"]')];
          return fields.length>0 && fields.every(f=>f.type==='text') &&
            fields.some(f=>/^۱۴۰۵\\//.test(f.value)) &&
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
        check("continuous_list_no_numbered_pages",evaluate("""
          const box=document.querySelector('.sac-table-tools');
          return box && box.textContent.includes('ردیف') &&
            !document.body.textContent.includes('صفحه ۱ از');
        """))
        check("invoice_detail_open",click_button("مشاهده جزئیات",panel="فاکتورهای فروش"))
        check("invoice_detail_exact",until("""
          const detail=document.querySelector('section.sac-document-detail');
          return !!detail && detail.textContent.includes('qa.invoice') &&
            detail.textContent.includes('چاپ جلد آزمایشی') &&
            detail.textContent.includes('۷۵۲') &&
            detail.textContent.includes('پیش‌نویس');
        """))
        check("proforma_sourced_draft_editable_with_provenance",evaluate("""
          return [...document.querySelectorAll('.sac-document-detail button')]
            .some(b=>b.textContent.includes('ویرایش فاکتور'));
        """))
        check("edit_from_document_detail",evaluate("""
          const button=[...document.querySelectorAll('.sac-document-detail button')]
            .find(b=>b.textContent.includes('ویرایش فاکتور'));
          if(!button)return false;button.click();return true;
        """))
        check("edited_unit_price",fill("اصلاح پیش‌نویس","قیمت واحد","260"))
        check("edit_converted_invoice_saved",submit_form("اصلاح پیش‌نویس"))
        check("edited_invoice_total_779",until("""
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(t=>t.textContent.includes('qa.invoice'));
          return !!tr && tr.textContent.includes('۷۷۹');
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
        check("red_debtor_amount",evaluate("""
          return !!document.querySelector('span.sac-money-debit[aria-label^="بدهکار"]');
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
        check("accounting_ar_exact",view["parties"]["qa.customer"]["receivable"]==527,
              detail=view["parties"]["qa.customer"]["receivable"])
        check("ledger_journals_two",len(view["journals"])==2,
              detail=len(view["journals"]))
        check("host_financial_reports",view.get("financialReports",{}).get("reconciled") is True)
        # An ordinary draft, unlike proforma-sourced invoices, must support
        # detail -> edit, and approved -> auditable reopening -> editing.
        check("navigate_invoice_for_edit",navigate("فاکتورهای فروش"))
        for field,value in (
            ("شناسه یکتا","qa.manual"),
            ("شرح","خدمت اولیه"),
            ("تعداد","2"),
            ("قیمت واحد","100"),
        ):
            check("ordinary_draft_fill_"+field,
                  fill("ساخت پیش‌نویس مستقل",field,value))
        check("ordinary_draft_party_select",evaluate("""
          const panel=[...document.querySelectorAll('section.sac-panel')]
            .find(x=>x.querySelector('.sac-panel-title h2')?.textContent.includes('ساخت پیش‌نویس مستقل'));
          const field=[...panel.querySelectorAll('label.sac-field')]
            .find(x=>x.querySelector('span')?.textContent.includes('مشتری'));
          const select=field?.querySelector('select');
          if(!select)return false;
          Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value')
            .set.call(select,'qa.customer');
          select.dispatchEvent(new Event('change',{bubbles:true}));
          return true;
        """))
        check("ordinary_draft_create",submit_form("ساخت پیش‌نویس مستقل"))
        check("ordinary_draft_persisted",until("""
          return [...document.querySelectorAll('.sac-table-wrap tr')]
            .some(t=>t.textContent.includes('qa.manual'));
        """))
        check("ordinary_draft_edit_button",evaluate("""
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(t=>t.textContent.includes('qa.manual'));
          const b=[...tr.querySelectorAll('button')]
            .find(x=>x.textContent.includes('ویرایش پیش‌نویس'));
          if(!b)return false;b.click();return true;
        """))
        check("ordinary_edit_qty",fill("اصلاح پیش‌نویس","تعداد","3"))
        check("ordinary_draft_update",submit_form("اصلاح پیش‌نویس"))
        check("ordinary_edited_total",until("""
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(t=>t.textContent.includes('qa.manual'));
          return !!tr && tr.textContent.includes('۳۰۰');
        """))
        check("ordinary_approve",evaluate("""
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(t=>t.textContent.includes('qa.manual'));
          const b=[...tr.querySelectorAll('button')]
            .find(x=>x.textContent.includes('تأیید'));
          if(!b||b.disabled)return false;b.click();return true;
        """))
        check("ordinary_approved",until("""
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(t=>t.textContent.includes('qa.manual'));
          return !!tr&&tr.textContent.includes('تأییدشده');
        """))
        check("ordinary_detail_open",evaluate("""
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(t=>t.textContent.includes('qa.manual'));
          const b=[...tr.querySelectorAll('button')]
            .find(x=>x.textContent.includes('مشاهده جزئیات'));
          if(!b)return false;b.click();return true;
        """))
        check("reopen_reason_fill",evaluate("""
          const input=document.querySelector('input[aria-label="دلیل بازگرداندن فاکتور برای اصلاح"]');
          if(!input)return false;
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')
            .set.call(input,'اصلاح ردیف قبل از صدور');
          input.dispatchEvent(new Event('input',{bubbles:true}));
          return true;
        """))
        check("reopen_approved",evaluate("""
          const button=[...document.querySelectorAll('.sac-document-detail button')]
            .find(x=>x.textContent.includes('بازگرداندن به پیش‌نویس')&&!x.disabled);
          if(!button)return false;button.click();return true;
        """))
        check("reopened_draft_persisted",until("""
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(t=>t.textContent.includes('qa.manual'));
          return !!tr && tr.textContent.includes('پیش‌نویس');
        """))
        edit=api.standaloneAccountingRead()["view"]["invoices"]["qa.manual"]
        check("reopen_event_auditable",edit.get("reopenCount")==1 and
              edit.get("lastReopenReason")=="اصلاح ردیف قبل از صدور")
        check("no_extra_gl_for_reopened_draft",
              len(api.standaloneAccountingRead()["view"]["journals"])==2)
        check("ordinary_approve_again",evaluate("""
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(t=>t.textContent.includes('qa.manual'));
          const b=[...tr.querySelectorAll('button')]
            .find(x=>x.textContent.includes('تأیید')&&!x.disabled);
          if(!b)return false;b.click();return true;
        """))
        check("ordinary_approved_again",until("""
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(t=>t.textContent.includes('qa.manual'));
          return !!tr && tr.textContent.includes('تأییدشده');
        """))
        check("ordinary_issue_again",evaluate("""
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(t=>t.textContent.includes('qa.manual'));
          const b=[...tr.querySelectorAll('button')]
            .find(x=>x.textContent.includes('صدور سند')&&!x.disabled);
          if(!b)return false;b.click();return true;
        """))
        check("ordinary_issued_for_correction",until("""
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(t=>t.textContent.includes('qa.manual'));
          return !!tr && tr.textContent.includes('صادرشده');
        """))
        check("correct_button_visible",evaluate("""
          const d=document.querySelector('.sac-document-detail');
          return !!d && [...d.querySelectorAll('button')]
            .some(b=>b.textContent.includes('اصلاح فاکتور صادرشده'));
        """))
        check("correction_open",evaluate("""
          const d=document.querySelector('.sac-document-detail');
          const b=[...d.querySelectorAll('button')]
            .find(b=>b.textContent.includes('اصلاح فاکتور صادرشده'));
          if(!b)return false;b.click();return true;
        """))
        check("correction_unit_price",fill("سند اصلاحی برای qa.manual","قیمت واحد","125"))
        check("correction_reason",fill("سند اصلاحی برای qa.manual",
                                        "علت اصلاح","اشتباه قیمت واحد فاکتور قطعی"))
        check("correction_submit",submit_form("سند اصلاحی برای qa.manual"))
        check("correction_reversal_recorded",until("""
          return [...document.querySelectorAll('.sac-table-wrap tr')]
            .some(x=>x.textContent.includes('qa.manual')&&
              x.textContent.includes('برگشت‌شده'));
        """))
        fixed=api.standaloneAccountingRead()
        linked=[x for x in fixed["view"]["invoices"].values()
                if x.get("correctionOf")=="qa.manual"]
        check("replacement_draft_linked",len(linked)==1 and
              linked[0]["total"]==375 and linked[0]["status"]=="draft",
              detail=[{"id":x["id"],"total":x["total"]} for x in linked])
        check("original_reference_linked",
              fixed["view"]["invoices"]["qa.manual"].get("correctedBy") ==
              (linked[0]["id"] if linked else None))
        check("corrected_ledger_gl_balanced",fixed["view"]["financialReports"]["reconciled"] is True)
        # Full commercial return: issue the linked replacement, then drive
        # the real GUI's auditable full-return operation on the unpaid document.
        replacement_id=linked[0]["id"] if linked else ""
        check("return_approve_replacement",evaluate("""
          const id=%s;
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(x=>x.textContent.includes(id));
          const b=[...tr?.querySelectorAll('button')||[]]
            .find(x=>x.textContent.includes('تأیید')&&!x.disabled);
          if(!b)return false;b.click();return true;
        """ % json.dumps(replacement_id,ensure_ascii=False)))
        check("return_replacement_approved",until("""
          const id=%s;
          return [...document.querySelectorAll('.sac-table-wrap tr')]
            .some(x=>x.textContent.includes(id)&&x.textContent.includes('تأییدشده'));
        """ % json.dumps(replacement_id,ensure_ascii=False)))
        check("return_issue_replacement",evaluate("""
          const id=%s;
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(x=>x.textContent.includes(id));
          const b=[...tr?.querySelectorAll('button')||[]]
            .find(x=>x.textContent.includes('صدور سند')&&!x.disabled);
          if(!b)return false;b.click();return true;
        """ % json.dumps(replacement_id,ensure_ascii=False)))
        check("return_replacement_issued",until("""
          const id=%s;
          return [...document.querySelectorAll('.sac-table-wrap tr')]
            .some(x=>x.textContent.includes(id)&&x.textContent.includes('صادرشده'));
        """ % json.dumps(replacement_id,ensure_ascii=False)))
        check("return_open_replacement_detail",evaluate("""
          const id=%s;
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(x=>x.textContent.includes(id));
          const b=[...tr?.querySelectorAll('button')||[]]
            .find(x=>x.textContent.includes('مشاهده جزئیات'));
          if(!b)return false;b.click();return true;
        """ % json.dumps(replacement_id,ensure_ascii=False)))
        check("return_full_action_visible",until("""
          const d=document.querySelector('section.sac-document-detail');
          return !!d&&d.textContent.includes(%s)&&
            [...d.querySelectorAll('button')]
            .some(x=>x.textContent.includes('ثبت مرجوعی کامل سند'));
        """ % json.dumps(replacement_id,ensure_ascii=False)))
        check("return_click_full_action",evaluate("""
          const b=[...document.querySelectorAll('.sac-document-detail button')]
            .find(x=>x.textContent.includes('ثبت مرجوعی کامل سند'));
          if(!b)return false;b.click();return true;
        """))
        check("return_fill_reason",evaluate("""
          const form=document.querySelector('section.sac-document-detail form.sac-cancel-form');
          const inp=form?.querySelector('input');
          if(!inp)return false;
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')
            .set.call(inp,'بازگشت کل سفارش مشتری بدون وصول');
          inp.dispatchEvent(new Event('input',{bubbles:true}));
          return true;
        """))
        check("return_submit_full",evaluate("""
          const form=document.querySelector('section.sac-document-detail form.sac-cancel-form');
          if(!form||!form.reportValidity())return false;
          form.requestSubmit();return true;
        """))
        check("return_posting_visible",until("""
          const id=%s;
          const tr=[...document.querySelectorAll('.sac-table-wrap tr')]
            .find(x=>x.textContent.includes(id));
          return !!tr && tr.textContent.includes('برگشت‌شده');
        """ % json.dumps(replacement_id,ensure_ascii=False)))
        after_return=api.standaloneAccountingRead()["view"]
        check("return_record_traceable",
              any(x.get("documentId")==replacement_id and x.get("amount")==375
                  for x in after_return.get("returns",{}).values()))
        check("return_no_orphan_receivable",
              after_return["parties"]["qa.customer"]["receivable"]==527)
        check("return_all_financial_reports_reconcile",
              api.standaloneAccountingRead()["view"]["financialReports"]["reconciled"] is True)
        check("report_navigation",navigate("گزارش‌های مالی"))
        check("period_report_open_close_columns",until("""
          return [...document.querySelectorAll('.sac-table-wrap th')]
            .some(t=>t.textContent.includes('اول دوره بدهکار')) &&
            [...document.querySelectorAll('.sac-table-wrap th')]
            .some(t=>t.textContent.includes('پایان دوره بستانکار'));
        """))
        check("report_rows_present",until("""
          return [...document.querySelectorAll('.sac-table-wrap tr')]
            .some(r=>r.textContent.includes('1200'));
        """))
        check("chart_navigation",navigate("حساب‌ها و دفترکل"))
        check("chart_form_available",until("""
          return [...document.querySelectorAll('.sac-panel-title h2')]
            .some(h=>h.textContent.includes('ایجاد حساب کل، معین یا تفصیلی'));
        """))
        for field,value in (("شناسه حساب","REV.M"),("عنوان","درآمد معین تست"),
                            ("ماهیت","revenue"),("سطح حساب","moein")):
            check("chart_moein_fill_"+field,
                  fill("ایجاد حساب کل، معین یا تفصیلی",field,value))
        check("chart_moein_parent_available",until("""
          const panel=[...document.querySelectorAll('section.sac-panel')]
            .find(x=>x.querySelector('h2')?.textContent.includes('ایجاد حساب کل، معین یا تفصیلی'));
          return [...panel.querySelectorAll('label.sac-field')]
            .some(l=>l.querySelector('span')?.textContent.includes('حساب والد'));
        """))
        check("chart_moein_parent_select",fill("ایجاد حساب کل، معین یا تفصیلی","حساب والد","4000"))
        check("chart_moein_create",submit_form("ایجاد حساب کل، معین یا تفصیلی"))
        check("chart_moein_store",until("""
          return [...document.querySelectorAll('.sac-table-wrap tr')]
            .some(r=>r.textContent.includes('REV.M')&&r.textContent.includes('معین'));
        """))
        for field,value in (("شناسه حساب","REV.T"),("عنوان","درآمد تفصیلی تست"),
                            ("ماهیت","revenue"),("سطح حساب","tafsili")):
            check("chart_tafsili_fill_"+field,
                  fill("ایجاد حساب کل، معین یا تفصیلی",field,value))
        check("chart_tafsili_parent_select",fill("ایجاد حساب کل، معین یا تفصیلی","حساب والد","REV.M"))
        check("chart_tafsili_create",submit_form("ایجاد حساب کل، معین یا تفصیلی"))
        check("chart_tree_hierarchy_persisted",until("""
          const t=[...document.querySelectorAll('details.sac-chart-sub')]
            .find(x=>x.textContent.includes('REV.M')&&x.textContent.includes('REV.T'));
          return !!t;
        """))
        snap_chart=api.standaloneAccountingRead()["view"]["accounts"]
        check("chart_lineage_exact",snap_chart.get("REV.M",{}).get("parentId")=="4000"
              and snap_chart.get("REV.T",{}).get("parentId")=="REV.M"
              and snap_chart.get("REV.T",{}).get("level")=="tafsili")
        check("company_page_navigation",navigate("مشخصات شرکت"))
        check("company_form_visible",until("""
          return [...document.querySelectorAll('section.sac-operational-form h3')]
            .some(x=>x.textContent.includes('ثبت مشخصات شرکت'));
        """))
        for field,value in (("عنوان رسمی","شرکت چاپ آزمایشی"),
                            ("شناسه ملی","QA-TEST"),("شماره تماس","000"),
                            ("دلیل ثبت","ثبت شرکت در محیط تست ایزوله")):
            check("company_fill_"+field,
                  fill_operational("ثبت مشخصات شرکت",field,value))
        check("company_profile_submit",submit_operational("ثبت مشخصات شرکت"))
        check("company_profile_persist",until("""
          return document.body.textContent.includes('شرکت چاپ آزمایشی');
        """))
        check("company_history_one",
              len(api.standaloneAccountingRead()["view"].get("companyProfile",{}).get("history",[]))==1)
        check("cheque_page_navigation",navigate("خزانه و چک"))
        check("cheque_live_page",until("""
          return document.body.textContent.includes('خزانه و چک عملیاتی') &&
            document.body.textContent.includes('ثبت چک دریافتی یا پرداختی');
        """))
        check("warehouse_page_navigation",navigate("کالا، انبار و کاردکس"))
        check("warehouse_live_page",until("""
          return document.body.textContent.includes('انبار، کاردکس و بهای تمام‌شده FIFO') &&
            document.body.textContent.includes('تعریف انبار');
        """))
        check("cash_bank_page_navigation",navigate("صندوق، بانک و مغایرت"))
        check("bank_live_page",until("""
          return document.body.textContent.includes('مغایرت‌گیری بانک') &&
            document.body.textContent.includes('ثبت ردیف صورتحساب بانکی');
        """))
        check("settlements_instalment_navigation",navigate("دریافت، پرداخت و اقساط"))
        check("instalment_live_page",until("""
          return document.body.textContent.includes('دفتر اقساط و سررسید') &&
            document.body.textContent.includes('ایجاد برنامه اقساط');
        """))
        check("payroll_page_navigation",navigate("حقوق و مالیات"))
        check("payroll_live_page",until("""
          return document.body.textContent.includes('حقوق و دستمزد') &&
            document.body.textContent.includes('ثبت سند حقوق و کسورات') &&
            document.body.textContent.includes('ثبت / بازنگری سیاست مالیات');
        """))
        check("fiscal_page_navigation",navigate("سال مالی و بستن دوره"))
        check("fiscal_live_page",until("""
          return document.body.textContent.includes('اختتامیه سال مالی') &&
            document.body.textContent.includes('ثبت اختتامیه و قفل سال');
        """))
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
    server=serve_accounting_page(ROOT/".qa-mohsen-ux40-20261025")
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
