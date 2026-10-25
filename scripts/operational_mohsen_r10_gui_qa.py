"""Real Windows pywebview check of ribbon and invoice template UX.

All app/profile/book paths are disposable project scratch. This checks only
NEW UX workflows against the same current built R10 frontend, not production ledgers.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import sys
from threading import Thread
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
SCRATCH=ROOT/".qa-mohsen-r10-ribbon-verified-20261025"
if SCRATCH.exists():
    raise SystemExit("Refusing existing R10 ribbon scratch folder")
SCRATCH.mkdir()
for name in ("roaming","local","webview2","temp","companies"):
    (SCRATCH/name).mkdir()
os.environ["APPDATA"]=str(SCRATCH/"roaming")
os.environ["LOCALAPPDATA"]=str(SCRATCH/"local")
os.environ["WEBVIEW2_USER_DATA_FOLDER"]=str(SCRATCH/"webview2")
os.environ["TEMP"]=os.environ["TMP"]=str(SCRATCH/"temp")
sys.path.insert(0,str(ROOT))

from standalone_accounting_company_registry import StandaloneCompanyRegistry
from standalone_accounting_desktop import AccountingDesktopAPI,serve_accounting_page

registry=StandaloneCompanyRegistry(SCRATCH/"companies")
company=registry.create_company("شرکت آزمایشی مستقل")
api=AccountingDesktopAPI(registry.company_data_directory(company["id"]),
                         company_name=company["name"])
start=api.standaloneAccountingRead()
api.standaloneAccountingCommand({
    "expectedRevision":start["revision"],
    "command":{"type":"party.register","eventId":"ux40-party-register",
               "partyId":"ux40.customer","name":"مشتری مصنوعی","kind":"customer"}})
checks={}
errors=[]
windows=[]


def check(name,ok,detail=None):
    checks[name]={"pass":bool(ok),"detail":detail}
    return bool(ok)


def js(code):
    return windows[0].evaluate_js("(function(){"+code+"})()")


def until(code,timeout=8):
    limit=time.monotonic()+timeout
    while time.monotonic()<limit:
        try:
            if js(code) is True:
                return True
        except Exception:
            pass
        time.sleep(.15)
    return False


def fill(selector,value):
    return js("""
      const e=document.querySelector(%s);
      if(!e)return false;
      const proto=HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto,'value').set.call(e,%s);
      e.dispatchEvent(new Event('input',{bubbles:true}));
      return true;
    """%(json.dumps(selector),json.dumps(str(value),ensure_ascii=False)))


def screenshot_if_safe():
    try:
        from PIL import ImageGrab
        hwnd=ctypes.windll.user32.FindWindowW(None,"مدار | بررسی ریبون محسن فاکتور")
        if not hwnd:
            return False
        class RECT(ctypes.Structure):
            _fields_=[("left",ctypes.c_long),("top",ctypes.c_long),
                      ("right",ctypes.c_long),("bottom",ctypes.c_long)]
        rect=RECT()
        if not ctypes.windll.user32.GetWindowRect(hwnd,ctypes.byref(rect)):
            return False
        if rect.right<=rect.left or rect.bottom<=rect.top:
            return False
        ImageGrab.grab(bbox=(rect.left,rect.top,rect.right,rect.bottom)).save(
            SCRATCH/"r7-ribbon-editor.png")
        return True
    except Exception as exc:
        errors.append({"screenshot":repr(exc)})
        return False


def run_gui():
    try:
        check("shell_loaded",until("return !!document.querySelector('.sac-root')"))
        check("top_ribbon",until("""
           return !!document.querySelector('.sac-ribbon-shell') &&
             document.querySelectorAll('.sac-ribbon-tabs button').length===7;
        """))
        check("old_sidebar_visually_hidden",js("""
          return getComputedStyle(document.querySelector('.sac-sidebar')).display==='none';
        """))
        check("company_name_visible_in_topbar",until("""
          return document.querySelector('.sac-ribbon-identity')?.textContent
             .includes('شرکت آزمایشی مستقل')===true;
        """))
        check("categorization_invoice_group",js("""
          const b=[...document.querySelectorAll('.sac-ribbon-tabs button')]
            .find(x=>x.textContent.includes('فاکتورها و سفارش‌ها'));
          if(!b)return false;b.click();return true;
        """))
        check("invoice_group_action_visible",until("""
          return [...document.querySelectorAll('.sac-ribbon-tools button')]
              .some(b=>b.textContent.includes('فاکتورهای فروش'));
        """))
        check("navigate_to_invoice",js("""
          const b=[...document.querySelectorAll('.sac-ribbon-tools button')]
              .find(x=>x.textContent.includes('فاکتورهای فروش'));
          if(!b)return false;b.click();return true;
        """))
        check("invoice_editor_with_grid",until("""
          return !!document.querySelector('.sac-invoice-editor .sac-invoice-columns') &&
           !!document.querySelector('.sac-entry-template-bar') &&
           !!document.querySelector('.sac-invoice-line-total');
        """))
        check("json_template_import_control",js("""
          return !!document.querySelector(
            'input[type=file][aria-label="فراخوانی قالب اقلام"]');
        """))
        # Hide browser download; capture Blob asynchronously inside WebView2.
        check("safe_template_download_capture",js("""
          window.__qaTemplate=null;
          HTMLAnchorElement.prototype.click=function(){
             const response={name:this.download,done:false,content:null,error:null};
             window.__qaTemplate=response;
             fetch(this.href).then(r=>r.text()).then(t=>{
               response.content=t;response.done=true;
             }).catch(err=>{response.error=String(err);response.done=true;});
          };return true;
        """))
        check("fill_item_desc",fill(".sac-invoice-line input[maxlength='300']",
               "خدمات چاپ آزمایشی"))
        check("fill_item_quantity",fill(
            ".sac-invoice-line input[inputmode=numeric]", "2"))
        check("fill_item_price",js("""
           const inputs=[...document.querySelectorAll('.sac-invoice-line input[inputmode=numeric]')];
           if(inputs.length<2)return false;
           const input=inputs[1];
           Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')
             .set.call(input,'500000');
           input.dispatchEvent(new Event('input',{bubbles:true}));return true;
        """))
        check("live_total_one_million",until("""
          return document.querySelector('.sac-invoice-line-total')?.textContent
              .includes('۱٬۰۰۰٬۰۰۰')===true;
        """))
        check("save_template_button_click",js("""
          const btn=[...document.querySelectorAll('.sac-entry-template-bar button')]
               .find(x=>x.textContent.includes('ذخیره قالب'));
          if(!btn)return false;btn.click();return true;
        """))
        check("json_blob_generated",until("""
          return !!window.__qaTemplate?.done&&!window.__qaTemplate.error;
        """))
        captured=js("return window.__qaTemplate")
        parsed=json.loads(captured["content"]) if captured and captured.get("content") else {}
        check("saved_template_data_exact",
              (parsed.get("currency")=="RIAL" and
               parsed.get("lines",[{}])[0].get("description")=="خدمات چاپ آزمایشی" and
               parsed.get("lines",[{}])[0].get("quantity")=="2" and
               parsed.get("lines",[{}])[0].get("unitPrice")=="500000"))
        check("new_entry_library_present",until("""
          return !!document.querySelector('.sac-template-library button') &&
            [...document.querySelectorAll('.sac-template-library button')]
              .some(b=>b.textContent.includes('ذخیره در کتابخانه'));
        """))
        check("store_entry_template_clicked",js("""
          const b=[...document.querySelectorAll('.sac-template-library button')]
            .find(x=>x.textContent.includes('ذخیره در کتابخانه'));
          if(!b)return false;b.click();return true;
        """))
        check("entry_template_stored_on_private_book",until(
            "return document.body.textContent.includes('در کتابخانه خصوصی')"))
        check("keyboard_next_cell_enter_dispatched",js("""
          const first=document.querySelector('[data-invoice-row="0"][data-invoice-col="0"]');
          if(!first)return false;first.focus();
          first.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
          return true;
        """))
        check("keyboard_focus_moves",until("""
          return document.activeElement?.dataset?.invoiceCol==='1';
        """))
        check("keyboard_ctrl_insert_add_row",js("""
          const first=document.querySelector('[data-invoice-row="0"][data-invoice-col="1"]');
          if(!first)return false;
          first.dispatchEvent(new KeyboardEvent('keydown',{
            key:'Insert',ctrlKey:true,bubbles:true,cancelable:true}));
          return true;
        """))
        check("keyboard_second_row_visible",until("""
          return !!document.querySelector('[data-invoice-row="1"][data-invoice-col="0"]');
        """))
        check("designer_open_click",js("""
          const b=[...document.querySelectorAll('button')]
            .find(b=>b.textContent.includes('باز کردن طراح قالب چاپ'));
          if(!b)return false;b.click();return true;
        """))
        check("designer_canvas_renders",until("""
          const canvas=document.querySelector('.sac-print-canvas-shell canvas');
          return !!canvas&&canvas.width>0&&canvas.height>0;
        """,timeout=12))
        check("print_template_save_clicked",js("""
          const b=[...document.querySelectorAll('.sac-template-library button')]
            .find(x=>x.textContent.includes('ذخیره قالب چاپ'));
          if(!b)return false;b.click();return true;
        """))
        check("print_template_saved_in_company_store",until("""
          return [...document.querySelectorAll('select[aria-label="قالب چاپ ذخیره‌شده"] option')]
            .some(o=>o.textContent.includes('قالب اختصاصی مدار'));
        """))
        check("issuer_save_independent",js("""
          const label=[...document.querySelectorAll('.sac-panel label')]
            .find(x=>x.textContent.includes('عنوان قانونی'));
          const input=label?.querySelector('input');
          if(!input)return false;
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(
            input,'شرکت صادرکننده آزمایشی');
          input.dispatchEvent(new Event('input',{bubbles:true}));
          return true;
        """))
        check("issuer_save_click",js("""
          const b=[...document.querySelectorAll('.sac-template-library button')]
            .find(x=>x.textContent.includes('ذخیره صادرکننده'));
          if(!b)return false;b.click();return true;
        """))
        check("issuer_saved_in_company_store",until("""
          return [...document.querySelectorAll('select[aria-label="انتخاب صادرکننده چاپی"] option')]
            .some(o=>o.textContent.includes('شرکت صادرکننده آزمایشی'));
        """))
        # Window capture omitted: compositor may obscure window under browser.
        # Validate that this GUI action made NO financial command.
        after=api.standaloneAccountingRead()
        check("template_not_posted_to_ledger",after["revision"]==1 and
              len(after["view"]["invoices"])==0 and
              len(after["view"]["journals"])==0)
        check("library_three_types_persisted",all(len(api.standaloneAccountingTemplateList(
            name)["templates"])>=1 for name in ("entry","print","issuer")))
    except Exception as exc:
        errors.append({"error":repr(exc),"trace":traceback.format_exc()[-3000:]})
    finally:
        try:
            windows[0].destroy()
        except Exception as exc:
            errors.append({"close":repr(exc)})


def main():
    site=ROOT/"dist"
    server=serve_accounting_page(site)
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        import webview
        window=webview.create_window("مدار | بررسی ریبون محسن فاکتور",
          "http://127.0.0.1:%d/accounting.html"%server.server_port,
          width=1440,height=900,js_api=api)
        windows.append(window)
        window.events.loaded+=run_gui
        webview.start()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    report={"mode":"synthetic company + actual pywebview + current built R10 frontend",
            "companyDir":str(api.path.parent),"checks":checks,"errors":errors}
    (SCRATCH/"report.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"pass":sum(v["pass"] for v in checks.values()),
       "fail":sum(not v["pass"] for v in checks.values())+len(errors),
       "checks":checks,"errors":errors},ensure_ascii=True))
    return 0 if checks and all(v["pass"] for v in checks.values()) and not errors else 1


if __name__=="__main__":
    sys.exit(main())
