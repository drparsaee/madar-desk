"""Real Windows WebView2 UI smoke for two consecutive partial credit notes.

Runs ONLY with disposable temp APPDATA, isolated SQLite and a built Vite page.
Never reads the user's actual Madar or Parsian data. No release publication.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Thread
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / ".qa-accounting-final-recovery-20261025"
if not (SITE / "accounting.html").is_file():
    raise SystemExit("Build the isolated Vite accounting UI first")

scratch = tempfile.TemporaryDirectory(prefix="madar-partial-return-gui-")
S = Path(scratch.name)
for directory in ("appdata", "localappdata", "webview2", "temp"):
    (S / directory).mkdir()
for var, path in {
    "APPDATA": S / "appdata",
    "LOCALAPPDATA": S / "localappdata",
    "WEBVIEW2_USER_DATA_FOLDER": S / "webview2",
    "TEMP": S / "temp",
    "TMP": S / "temp",
}.items():
    os.environ[var] = str(path)
sys.path.insert(0, str(ROOT))
from standalone_accounting_desktop import AccountingDesktopAPI, serve_accounting_page

api = AccountingDesktopAPI(S / "accounting-only")
today = datetime.now().strftime("%Y-%m-%d")
checks = {}
errors = []
window = []
server = None


def verify(name, value, context=None):
    checks[name] = {"passed": bool(value), "detail": context}
    return bool(value)


def js(source):
    return window[0].evaluate_js("(function(){" + source + "})()")


def until(source, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if js(source) is True:
                return True
        except Exception as error:
            errors.append(str(error)[:160])
        time.sleep(.15)
    return False


def seed():
    actions = [
        {"type": "party.register", "eventId": "seed.person",
         "partyId": "customer-qa", "name": "Synthetic buyer", "kind": "customer"},
        {"type": "invoice.create", "eventId": "seed.draft",
         "invoiceId": "sale-qa", "partyId": "customer-qa",
         "documentDate": today, "lines": [
             {"description": "First design", "quantity": 3, "unitPrice": 1000},
             {"description": "Second design", "quantity": 2, "unitPrice": 2000}]},
        {"type": "invoice.approve", "eventId": "seed.approve",
         "invoiceId": "sale-qa"},
        {"type": "invoice.issue", "eventId": "seed.issue",
         "invoiceId": "sale-qa", "postingDate": today},
    ]
    response = api.standaloneAccountingRead()
    for cmd in actions:
        response = api.standaloneAccountingCommand({
            "command": cmd, "expectedRevision": response["revision"]})
    return response


def fill(selector, value):
    return js("""
      const e=document.querySelector(%s);
      if(!e)return false;
      const original=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');
      original.set.call(e,%s);
      e.dispatchEvent(new Event('input',{bubbles:true}));
      return true;
    """ % (json.dumps(selector), json.dumps(value)))


def open_doc():
    return (
        js("""
          const nav=[...document.querySelectorAll('.sac-sidebar nav button')]
            .find(b=>b.textContent.includes('فاکتورهای فروش'));
          if(!nav)return false;nav.click();return true;
        """) and
        until("return [...document.querySelectorAll('tr')].some(x=>x.textContent.includes('sale-qa'));") and
        js("""
          const row=[...document.querySelectorAll('tr')]
            .find(x=>x.textContent.includes('sale-qa'));
          const button=[...row?.querySelectorAll('button')||[]]
            .find(b=>b.textContent.includes('مشاهده جزئیات'));
          if(!button)return false;button.click();return true;
        """) and
        until("return !!document.querySelector('.sac-document-detail');")
    )


def gui_run():
    try:
        verify("page_ready", until("return !!document.querySelector('.sac-sidebar nav');"))
        verify("authorized_admin_buttons", until("""
          return !!document.querySelector('header.sac-header') &&
            !document.body.textContent.includes('دسترسی مشاهده:') &&
            !document.body.textContent.includes('دسترسی ثبت اولیه:');
        """))
        verify("open_issued_document", open_doc())
        verify("partial_button", js("""
          const btn=[...document.querySelectorAll('.sac-document-detail button')]
            .find(b=>b.textContent.includes('ثبت مرجوعی جزئی اقلام'));
          if(!btn)return false;btn.click();return true;
        """))
        verify("partial_form", until("return !!document.querySelector('form.sac-cancel-form');"))
        verify("first_qty_input", fill(
            'form.sac-cancel-form input[inputmode="numeric"]', '1'))
        verify("return_reason", fill(
            'form.sac-cancel-form input[required][maxlength="1000"]',
            "Synthetic partial design return"))
        verify("submit_partial", js("""
          const form=document.querySelector('form.sac-cancel-form');
          if(!form||!form.reportValidity())return false;
          form.requestSubmit();return true;
        """))
        verify("credit_note_posted", until("""
          return document.body.textContent.includes('مرجوعی‌های جزئی ثبت‌شده');
        """), api.standaloneAccountingRead()["view"]["invoices"]["sale-qa"])
        verify("credit_note_audit_trail_visible", until("""
          const details=[...document.querySelectorAll('details.sac-audit-notice')]
            .find(el=>el.textContent.includes('سوابق مرجوعی و اسناد'));
          return !!details && details.textContent.includes('Synthetic partial design return');
        """))
        snapshot = api.standaloneAccountingRead()
        document = snapshot["view"]["invoices"]["sale-qa"]
        verify("book_balances_return_1000", document["returnedAmount"] == 1000 and
               document["status"] == "issued" and document["total"] == 7000 and
               document["returnedQuantities"] == [1, 0])
        verify("receivable_exact_6000",
               snapshot["view"]["parties"]["customer-qa"]["receivable"] == 6000)
        verify("ui_amount_6000", until("""
          const info=document.querySelector('.sac-document-detail');
          return !!info && info.textContent.includes('۶٬۰۰۰');
        """))
        verify("no_task_db", not any((S / "accounting-only" / f).exists()
              for f in ("tasks.json", "finance.json", "madar-unified.sqlite3")))
    except BaseException as error:
        errors.append(repr(error) + "\n" + traceback.format_exc()[-1500:])
        verify("unexpected_exception", False, repr(error))
    finally:
        window[0].destroy()


def main():
    global server
    seed()
    server = serve_accounting_page(SITE)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import webview
        gui = webview.create_window(
            "Synthetic Partial Return GUI QA",
            f"http://127.0.0.1:{server.server_port}/accounting.html",
            width=1200, height=850, js_api=api)
        window.append(gui)
        gui.events.loaded += gui_run
        webview.start()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        result = {"pass": sum(v["passed"] for v in checks.values()),
                  "fail": sum(not v["passed"] for v in checks.values()),
                  "checks": checks, "errors": errors}
        print(json.dumps(result, ensure_ascii=False, default=str))
        scratch.cleanup()
    return 0 if checks and all(v["passed"] for v in checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
