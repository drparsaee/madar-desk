"""R16 native WebView smoke against one disposable, synthetic company only.

No registry lookup, Parsian access, production company, or packaged installer.
"""
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import ctypes
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from standalone_accounting_desktop import AccountingDesktopAPI, serve_accounting_page


def run():
    project = Path(__file__).resolve().parents[1]
    today = date.today()
    due = (today + timedelta(days=3)).isoformat()
    checks, errors, warnings, windows = {}, [], [], []

    def check(name, condition):
        checks[name] = bool(condition)

    def js(code):
        return windows[0].evaluate_js('(function(){' + code + '})()')

    def until(code, timeout=9):
        stop = time.monotonic() + timeout
        while time.monotonic() < stop:
            try:
                if js(code) is True:
                    return True
            except Exception:
                pass
            time.sleep(.2)
        return False

    with TemporaryDirectory(prefix='madar-r16-dashboard-test-') as temporary:
        api = AccountingDesktopAPI(Path(temporary), company_name='شرکت مصنوعی R16')

        def command(command_type, **fields):
            revision = api.standaloneAccountingRead()['revision']
            return api.standaloneAccountingCommand({'expectedRevision': revision,
                'command': {'type': command_type, 'eventId': 'r16-test-' + str(revision + 1), **fields}})

        api.standaloneAccountingRead()
        command('party.register', partyId='R16-CUSTOMER', name='مشتری ساختگی', kind='customer')
        command('invoice.create', invoiceId='R16-INVOICE', partyId='R16-CUSTOMER',
                documentDate=today.isoformat(), lines=[{'description': 'آزمون نمودار',
                'quantity': 2, 'unitPrice': 250000}])
        command('invoice.approve', invoiceId='R16-INVOICE')
        command('invoice.issue', invoiceId='R16-INVOICE', postingDate=today.isoformat())
        command('cheque.register', chequeId='R16-CHEQUE', direction='receipt',
                documentId='R16-INVOICE', bankAccountId='1010', dueDate=due,
                amount=200000, reference='R16-FAKE-REFERENCE')
        baseline = api.standaloneAccountingRead()
        check('one_company_only', baseline['view']['companyWorkspaceLabel'] == 'شرکت مصنوعی R16')
        check('one_issued_invoice', len(baseline['view']['invoices']) == 1 and
              baseline['view']['invoices']['R16-INVOICE']['status'] == 'issued')
        check('one_open_cheque', baseline['view']['cheques']['R16-CHEQUE']['status'] == 'received')
        check('no_cheque_cash_posting', len(baseline['view']['journals']) == 1)

        server = serve_accounting_page(project / 'dist')
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            import webview

            def inspect():
                try:
                    check('workspace_loaded', until('return !!document.querySelector(".sac-root")'))
                    check('overview_default', until('return document.querySelector(".sac-header h1")?.textContent === "داشبورد"'))
                    check('dashboard_loaded', until('return !!document.querySelector(".madar-management-dashboard")'))
                    check('charts_available', until('return document.querySelectorAll(".madar-dashboard-chart").length >= 2'))
                    check('synthetic_cheque_reminder', until('return [...document.querySelectorAll(".madar-dashboard-reminder")].some(e=>e.textContent.includes("R16-FAKE-REFERENCE"))'))
                    check('no_fake_product_profit', until('return document.querySelector(".madar-management-dashboard")?.textContent.includes("اطلاعات کافی") === true'))
                    screenshot = project / '.qa-r16-management-dashboard-v3.png'
                    if not screenshot.exists():
                        try:
                            from PIL import ImageGrab
                            hwnd = ctypes.windll.user32.FindWindowW(None, 'مدار | آزمون داشبورد R16')
                            if hwnd:
                                ctypes.windll.user32.ShowWindow(hwnd, 9)
                                ctypes.windll.user32.SetForegroundWindow(hwnd)
                                time.sleep(.6)
                                # Never screenshot unrelated foreground windows.
                                if ctypes.windll.user32.GetForegroundWindow() != hwnd:
                                    raise RuntimeError('Owned window did not gain focus; screenshot skipped')
                                class Rect(ctypes.Structure):
                                    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                                                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]
                                rect = Rect()
                                if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                                    ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom),
                                                   all_screens=True).save(screenshot)
                        except Exception as exc:
                            warnings.append('Screenshot optional: ' + repr(exc))
                    check('open_chart', js('const c=document.querySelector(".madar-dashboard-chart");if(!c)return false;c.click();return true'))
                    check('drilldown_open', until('return !!document.querySelector(".madar-dashboard-drilldown")'))
                    check('custom_range_controls', until('return document.querySelectorAll(".madar-dashboard-drilldown input").length >= 2'))
                    check('custom_range_recalculates_sales', js('''
                        const input=document.querySelector('input[aria-label="تاریخ پایان جزئیات"]');
                        if(!input)return false;
                        const yesterday=new Date();yesterday.setDate(yesterday.getDate()-1);
                        const parts=new Intl.DateTimeFormat('en-US-u-ca-persian-nu-latn',
                          {year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(yesterday);
                        const fields=Object.fromEntries(parts.map(p=>[p.type,p.value]));
                        const next=fields.year+'/'+fields.month+'/'+fields.day;
                        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,next);
                        input.dispatchEvent(new Event('input',{bubbles:true}));return true;
                    ''') and until('return document.querySelector(".madar-management-dashboard .mdash-kpi-value")?.textContent.includes("۵۰۰٬۰۰۰") === false'))
                    check('currency_shown', js('return document.querySelector(".madar-management-dashboard")?.textContent.includes("ریال") === true'))
                    check('dashboard_has_no_write_buttons', not bool(js('return !!document.querySelector(".madar-management-dashboard button[data-financial-write]")')))
                except Exception as exc:
                    errors.append(repr(exc))
                finally:
                    windows[0].destroy()

            window = webview.create_window('مدار | آزمون داشبورد R16',
                f'http://127.0.0.1:{server.server_port}/accounting.html',
                width=1440, height=900, js_api=api)
            windows.append(window)
            window.events.loaded += inspect
            webview.start()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        check('no_financial_change_in_gui', api.standaloneAccountingRead()['revision'] == baseline['revision'])

    report = {'pass': sum(checks.values()), 'fail': sum(not v for v in checks.values()) + len(errors),
              'checks': checks, 'errors': errors, 'warnings': warnings}
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['fail'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(run())
