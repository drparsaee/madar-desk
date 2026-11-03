"""Launch Madar's isolated accounting desk without loading the task manager.

Development/explicit local mode. The operator must specify an ABSOLUTE private
data directory; this module never discovers or opens Madar's task/finance DB.
No network or real user files are touched simply by importing the module.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock, Thread
from urllib.parse import urlsplit, unquote


ACCOUNTING_FILE = "standalone-accounting.sqlite3"

JS_BRIDGE = """<script>
window.__madarStandaloneOnly = true;
window.madar = Object.fromEntries(
  ['standaloneAccountingRead', 'standaloneAccountingCommand',
   'standaloneAccountingCsvChooseFile', 'standaloneAccountingCsvPreview',
   'standaloneAccountingParsianArchiveIndex', 'standaloneAccountingParsianArchiveRows',
   'standaloneAccountingTemplateList', 'standaloneAccountingTemplateSave',
   'standaloneAccountingTemplateDelete', 'standaloneAccountingTemplateDefault',
   'standaloneAccountingTemplateDuplicate',
   'standaloneAccountingRequestCompanySwitch',
   'standaloneAccountingTaxPreflight',
   'standaloneAccountingManageUsers',
   'releaseCheck', 'releaseDownload', 'releaseInstall'].map(
    key => [key, (...args) => new Promise((resolve, reject) => {
      // WebView2 can expose an api object before populating the methods.
      // Checking only window.pywebview.api caused a TypeError/blank GUI on
      // slower starts. Retry only for a bounded startup window.
      const started = Date.now();
      const invoke = () => {
        const fn = window.pywebview?.api?.[key];
        if (typeof fn !== 'function') {
          if (Date.now() - started < 12000) {
            setTimeout(invoke, 80);
          } else {
            reject(new Error('ارتباط امن حسابداری ویندوز آماده نشد؛ برنامه را دوباره باز کنید.'));
          }
          return;
        }
        try {
          Promise.resolve(fn(...args)).then(resolve, reject);
        } catch (err) {
          reject(err);
        }
      };
      invoke();
    })]
  )
);
</script>"""


class AccountingDesktopAPI:
    """Single local desktop principal; not a multi-user authentication server."""

    def __init__(self, explicit_data_root, *, company_name="", authenticated_user=None,
                 identity_store=None, identity_token=None):
        path = Path(explicit_data_root)
        if not path.is_absolute():
            raise ValueError("Accounting data directory must be explicit and absolute")
        if path.exists() and not path.is_dir():
            raise ValueError("Accounting data path must be a directory")
        self.path = path / ACCOUNTING_FILE
        self._lock = RLock()
        self._exit_backed_up = False
        self._identity_store = identity_store
        self._identity_token = identity_token
        if identity_store is not None:
            if not isinstance(identity_token,str) or not identity_token:
                raise PermissionError('Authentication is required before accessing company ledger')
            checked=identity_store.require_session(identity_token)
            if not isinstance(authenticated_user,dict) or checked != authenticated_user:
                raise PermissionError('Invalid or mismatched accounting identity')
            self._actor=checked['username']
            self._accounts=identity_store.accounting_accounts()
            if self._actor not in self._accounts:
                raise PermissionError('Inactive accounting identity')
        else:
            self._actor='local'
            self._accounts = {"local": {"username": "local", "role": "admin"}}
        # Only a display hint from an explicitly selected private company
        # directory. This never becomes an accounting event or ledger field.
        self.company_name = company_name if isinstance(company_name,str) else ""
        self._switch_requested = False
        self._native_window = None
        from provider_csv_bridge import ProviderCsvPreviewBridge
        self._csv_preview = ProviderCsvPreviewBridge()

    def releaseCheck(self):
        """Public version metadata only; no accounting data leaves this host."""
        with self._lock:
            self._require_authenticated()
            if self._exit_backed_up:
                raise RuntimeError("Accounting desktop is closing")
        import madar_update
        return madar_update.check()

    def releaseDownload(self):
        """Host selects and verifies the complete installer, never the browser."""
        with self._lock:
            self._require_authenticated()
            if self._exit_backed_up:
                raise RuntimeError("Accounting desktop is closing")
        import madar_update
        return madar_update.download(madar_update.check())

    def releaseInstall(self):
        """Schedule only a verified installer; closing still requires finance backup."""
        with self._lock:
            self._require_authenticated()
            if self._exit_backed_up:
                raise RuntimeError("Accounting desktop is closing")
            if self._native_window is None:
                raise RuntimeError("Native accounting window is unavailable")
        import madar_update
        info = madar_update.check()
        saved = madar_update.download(info)
        with self._lock:
            self._require_authenticated()
            if self._exit_backed_up:
                raise RuntimeError("Accounting desktop is closing")
        # The pending PowerShell process waits for THIS desktop PID. The normal
        # closing handler runs and verifies the mandatory financial backup.
        return madar_update.schedule_verified_install(info, saved)

    def standaloneAccountingCsvChooseFile(self, group, encoding, delimiter):
        """Admin-selected local CSV header only; no ledger or disk writes."""
        with self._lock:
            self._require_authenticated('admin')
            if self._native_window is None:
                raise RuntimeError("Native accounting file chooser is unavailable")
            from provider_csv_bridge import GROUPS
            if group not in GROUPS or type(group) is not str:
                raise ValueError("Unknown CSV group")
            import webview
            chosen = self._native_window.create_file_dialog(
                webview.FileDialog.OPEN, file_types=("CSV files (*.csv)",))
            return self._csv_preview.select(group, encoding, delimiter, chosen)

    def standaloneAccountingCsvPreview(self, request):
        """Preview chosen user-owned CSV files; never call accounting store."""
        with self._lock:
            self._require_authenticated('admin')
            return self._csv_preview.preview(request)

    def _require_authenticated(self,required='viewer'):
        if self._identity_store is not None:
            checked=self._identity_store.require_session(self._identity_token,required)
            if checked['username'] != self._actor:
                raise PermissionError('Active accounting identity changed')
            self._accounts=self._identity_store.accounting_accounts()
            return checked
        return self._accounts[self._actor]

    def standaloneAccountingRequestCompanySwitch(self):
        """Only the native company chooser may switch the active ledger.

        This call does NOT access another book. The actual switch happens
        after the current WebView has closed, backed up and released its lock.
        """
        with self._lock:
            self._require_authenticated()
            if not self.company_name:
                raise RuntimeError("Company switching requires a selected company registry")
            if self._exit_backed_up:
                raise RuntimeError("Accounting desktop is closing")
            if self._native_window is None:
                raise RuntimeError("Accounting window is not available for switching")
            self._switch_requested = True
            # window.close() in JavaScript is ignored by some embedded
            # WebView2 configurations. Close the owned native window through
            # pywebview instead; its closing handler MUST still verify backup.
            window = self._native_window
            def close_owned_window():
                time.sleep(.12)
                try:
                    window.destroy()
                except Exception as exc:
                    print("Company switch could not close native window: " + str(exc),
                          file=sys.stderr)
                    with self._lock:
                        self._switch_requested = False
            Thread(target=close_owned_window, daemon=True).start()
            return True

    def _store(self):
        from standalone_accounting import StandaloneAccountingStore
        # Only an explicit read or command may create this directory/database.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # New independent ledgers default to RIAL; existing TOMAN snapshots
        # retain their persisted currency and are never reinterpreted.
        return StandaloneAccountingStore(self.path, default_currency="RIAL")

    def _with_migration(self, result):
        """Read-only historic Parsian view, if this explicit book has a sidecar.

        The source sidecar must be packaged beside this particular standalone
        book. No directory traversal, discovery under APPDATA, or writes to
        Parsian/other account books. Historical documents remain NON-POSTED.
        """
        from parsian_legacy_views import legacy_views
        historic = legacy_views(
            result["view"],
            archive_path=self.path.parent / "parsian-all-base-tables-PRIVATE.sqlite3",
            manifest_path=self.path.parent / "parsian-archive-manifest.json",
        )
        if historic is not None:
            result["view"]["parsianMigration"] = historic
        if self.company_name:
            result["view"]["companyWorkspaceLabel"] = self.company_name
        return result

    def standaloneAccountingRead(self):
        with self._lock:
            self._require_authenticated()
            from standalone_financial_report_host import attach_verified_reports
            result = self._with_migration(attach_verified_reports(self._store().read(
                actor=self._actor, accounts=self._accounts)))
            role=self._accounts[self._actor]['role']
            result["capabilities"] = {
                "canView": True, "canManage": role in ('admin','editor'),
                "canDraft": role in ('admin','editor'), "canAdmin": role=='admin'}
            identity=(self._identity_store.require_session(self._identity_token)
                      if self._identity_store is not None else
                      {"username":self._actor,"role":role,"jobTitle":""})
            result["currentUser"]={"username":identity['username'],
                                   "jobTitle":identity.get('jobTitle',''),"role":role}
            return result

    def standaloneAccountingParsianArchiveIndex(self):
        """Admin-only catalogue of verified, immutable Parsian year archives."""
        with self._lock:
            self._require_authenticated('admin')
            from parsian_source_year_browser import list_year_archives
            return list_year_archives(self.path.parent)

    def standaloneAccountingParsianArchiveRows(self, year, table, offset=0):
        """Paginated, redacted read-only values; no arbitrary filesystem path."""
        with self._lock:
            self._require_authenticated('admin')
            from parsian_source_year_browser import source_table_page
            return source_table_page(self.path.parent, year, table, offset)

    def standaloneAccountingCommand(self, request):
        if (type(request) is not dict or
                set(request) != {"command", "expectedRevision"} or
                type(request["command"]) is not dict or
                type(request["expectedRevision"]) is not int or
                request["expectedRevision"] < 0):
            raise ValueError("Invalid accounting CAS request")
        with self._lock:
            self._require_authenticated('editor')
            if self._exit_backed_up:
                raise RuntimeError("Accounting desktop is closing; financial changes are locked")
            from standalone_financial_report_host import attach_verified_reports
            return self._with_migration(attach_verified_reports(self._store().command(
                request["command"], actor=self._actor, accounts=self._accounts,
                expected_revision=request["expectedRevision"],
                now=datetime.now(timezone.utc).isoformat(),
            )))

    def _template_store(self):
        from standalone_accounting_template_store import StandaloneAccountingTemplateStore
        return StandaloneAccountingTemplateStore(self.path.parent)

    def _require_template_permission(self,write=False):
        self._require_authenticated('editor' if write else 'viewer')

    def standaloneAccountingTemplateList(self, kind):
        with self._lock:
            self._require_template_permission()
            return self._template_store().list(kind)

    def standaloneAccountingTemplateSave(self, kind, title, data, template_id=""):
        with self._lock:
            self._require_template_permission(True)
            if self._exit_backed_up:
                raise RuntimeError("Accounting desktop is closing")
            return self._template_store().save(kind, title, data, template_id)

    def standaloneAccountingTemplateDelete(self, kind, template_id):
        with self._lock:
            self._require_template_permission(True)
            if self._exit_backed_up:
                raise RuntimeError("Accounting desktop is closing")
            return self._template_store().delete(kind, template_id)

    def standaloneAccountingTemplateDefault(self, kind, template_id):
        with self._lock:
            self._require_template_permission(True)
            if self._exit_backed_up:
                raise RuntimeError("Accounting desktop is closing")
            return self._template_store().set_default(kind, template_id)

    def standaloneAccountingTemplateDuplicate(self, kind, template_id):
        with self._lock:
            self._require_template_permission(True)
            if self._exit_backed_up:
                raise RuntimeError("Accounting desktop is closing")
            return self._template_store().duplicate(kind, template_id)

    def standaloneAccountingTaxPreflight(self, invoice_id):
        """Read-only advisory; never submits, changes or signs tax invoices."""
        if not isinstance(invoice_id,str) or len(invoice_id)>96:
            raise ValueError('Invalid invoice identifier')
        with self._lock:
            self._require_authenticated()
            from standalone_accounting_tax_advisor import preflight_einvoice
            result=self.standaloneAccountingRead()
            view=result['view']
            invoice=view.get('invoices',{}).get(invoice_id)
            if not invoice:raise ValueError('Invoice not found in active company ledger')
            company=view.get('companyProfile') or {}
            return preflight_einvoice({
                'invoiceId':invoice_id,'issueDate':invoice.get('documentDate'),
                'kind':'original','lines':[
                    {'productServiceId':line.get('taxProductServiceId') or '',
                     'quantity':line.get('quantity'), 'unitPrice':line.get('unitPrice')}
                    for line in invoice.get('lines',[])]},company)

    def standaloneAccountingManageUsers(self):
        """Native-only credential prompts; no password enters the React DOM."""
        with self._lock:
            self._require_authenticated('admin')
            if self._identity_store is None or self._identity_token is None:
                raise PermissionError('User management requires authenticated company mode')
            from standalone_accounting_user_dialog import manage_local_users
            store=self._identity_store
            token=self._identity_token
        manage_local_users(store,token)
        return {'status':'closed'}


def serve_accounting_page(site):
    """Host only the built accounting page on an ephemeral loopback port."""
    site = Path(site)
    if not (site / "accounting.html").is_file():
        raise FileNotFoundError("Run npm run build before launching accounting")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(site), **kwargs)

        def do_GET(self):
            pathname = urlsplit(self.path).path
            decoded = unquote(pathname)
            # SimpleHTTPRequestHandler unquotes before resolving the filesystem.
            # Deny aliases too; this host must never serve task-manager HTML.
            if decoded.lower().endswith(('/index.html', '/index.htm')):
                self.send_error(404, "Task manager not part of standalone accounting")
                return
            if pathname in ("/", "/accounting.html"):
                content = (site / "accounting.html").read_text(encoding="utf-8")
                content = content.replace("</head>", JS_BRIDGE + "</head>")
                encoded = content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(encoded)
                return
            if pathname in ("/index.html",):
                self.send_error(404, "Task manager not part of standalone accounting")
                return
            super().do_GET()

        def log_message(self, *_args):
            return

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)


def _native_accounting_login(store):
    """Open native premium credentials gate before serving accounting UI."""
    if not store.initialized() and (store.root/ACCOUNTING_FILE).exists():
        raise PermissionError('Existing ledger has no identity file: restore its backup before login')
    from standalone_accounting_secure_login import prompt_premium_accounting_login
    return prompt_premium_accounting_login(store)


def _run_company_session(data_dir, selected_company_name, args):
    company_guard = None
    identity_store = None
    logged_in_user = None
    identity_token = None
    from standalone_accounting_company_registry import (
        CompanySessionGuard, StandaloneCompanyRegistry)
    directory=Path(data_dir)
    registered=False
    if directory.parent.name=='books' and (directory.parent.parent/'companies.json').exists():
        registry=StandaloneCompanyRegistry(directory.parent.parent)
        registered=directory==registry.company_data_directory(directory.name)
    if args.companies_dir or registered:
        company_guard = CompanySessionGuard(Path(data_dir)).acquire()
    try:
        identity_path=Path(data_dir)/'local-users.json'
        if (args.companies_dir or registered or identity_path.exists() or
            identity_path.is_symlink() or (Path(data_dir)/ACCOUNTING_FILE).exists()):
            from standalone_accounting_identity import LocalCompanyIdentity
            identity_store=LocalCompanyIdentity(Path(data_dir))
            # Never let a missing identity registry convert an existing book
            # into a new local-admin account, regardless of launch switches.
            if not identity_store.initialized() and (Path(data_dir)/ACCOUNTING_FILE).exists():
                raise PermissionError('Existing ledger has no user registry; restore identity backup before login')
            login=_native_accounting_login(identity_store)
            if login is None:
                if company_guard:
                    company_guard.release()
                return False
            logged_in_user,identity_token=login
        api = AccountingDesktopAPI(data_dir, company_name=selected_company_name,
            authenticated_user=logged_in_user,identity_store=identity_store,
            identity_token=identity_token)
        from standalone_accounting_auto_backup import AutomaticStandaloneBackups
        backups = AutomaticStandaloneBackups(
            api.path.parent, plaintext_acknowledged=True)
        # Fail closed at startup if a verified baseline cannot be backed up.
        with api._lock:
            api.standaloneAccountingRead()
            backups.backup_now()
        backups.start()
    except BaseException:
        if company_guard:
            company_guard.release()
        raise
    server = None
    server_thread = None
    exit_backup_saved = False
    try:
        server = serve_accounting_page(args.site_dir)
        server_thread = Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        import webview
        window = webview.create_window(
            "مدار | حسابداری مستقل", f"http://127.0.0.1:{server.server_port}/accounting.html",
            width=1450, height=925, min_size=(880, 620), js_api=api,
        )
        api._native_window = window

        def backup_on_close():
            nonlocal exit_backup_saved
            try:
                with api._lock:
                    backups.backup_now()
                    # Financial commands cannot race in after the final
                    # verified backup has been published.
                    api._exit_backed_up = True
            except Exception as exc:
                # pywebview events.closing cancels the close when a handler
                # returns False. The user may retry after fixing disk access.
                api._switch_requested = False
                print("Mandatory accounting exit backup failed: " + str(exc),
                      file=sys.stderr)
                try:
                    window.evaluate_js("window.alert(" + json.dumps(
                        "بستن حسابداری متوقف شد. پشتیبان‌گیری مالی ناموفق بود: " +
                        str(exc), ensure_ascii=False) + ")")
                except Exception:
                    pass  # Still prevent close even if the dialog fails.
                return False
            exit_backup_saved = True
            return True

        window.events.closing += backup_on_close
        webview.start()
    finally:
        try:
            backups.stop()
            # Recovery path for a webview runtime that terminates without
            # delivering its normal closing event. Never silently exit on a
            # failed final backup, even when the native window already died.
            if not exit_backup_saved:
                with api._lock:
                    backups.backup_now()
                    api._exit_backed_up = True
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if server_thread is not None:
                server_thread.join(timeout=5)
            if company_guard:
                company_guard.release()
            if identity_store is not None and identity_token is not None:
                identity_store.logout(identity_token)

    return bool(api._switch_requested and exit_backup_saved)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Madar isolated accounting desktop")
    parser.add_argument("--data-dir",
                        help="Explicit absolute private directory for accounting data; if omitted, select a folder")
    parser.add_argument("--companies-dir",
                        help="Existing absolute registry root for independent per-company accounting books")
    parser.add_argument("--recovery", action="store_true",
                        help="Open a separate OFFLINE restore wizard; NEVER start the live accounting host")
    bundled_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    parser.add_argument("--site-dir", default=str(bundled_root / "dist"),
                        help="Directory containing built accounting.html")
    parser.add_argument("--restore-ui", action="store_true",
                        help="Run the OFFLINE no-overwrite graphical restore wizard and exit")
    args = parser.parse_args(argv)
    if args.companies_dir and (args.data_dir or args.recovery or args.restore_ui):
        parser.error("--companies-dir requires standalone company mode without other launch modes")
    if args.recovery:
        from standalone_accounting_recovery_wizard import run_offline_recovery_wizard
        return 0 if run_offline_recovery_wizard(
            Path(args.data_dir) if args.data_dir else None) else 1
    if args.restore_ui:
        # Must run BEFORE AccountingDesktopAPI, backup timers and WebView host.
        from standalone_accounting_restore_ui import run_restore_wizard
        return run_restore_wizard()
    while True:
        data_dir = args.data_dir
        selected_company_name = ""
        if args.companies_dir:
            from standalone_accounting_company_registry import (
                StandaloneCompanyRegistry, pick_company_dialog,
            )
            selected = pick_company_dialog(StandaloneCompanyRegistry(
                Path(args.companies_dir)))
            if selected is None:
                return 0
            data_dir = selected["path"]
            selected_company_name = selected["name"]
        if data_dir is None:
            # A packaged EXE must be launchable by double-click without silently
            # selecting an existing task-manager or finance database.
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            try:
                data_dir = filedialog.askdirectory(
                    parent=root, title="پوشه اختصاصی اطلاعات حسابداری مدار را انتخاب کنید",
                    mustexist=True,
                )
            finally:
                root.destroy()
            if not data_dir:
                return 0
        switch_requested = _run_company_session(data_dir, selected_company_name, args)
        if not args.companies_dir or not switch_requested:
            return 0

if __name__ == "__main__":
    main()
