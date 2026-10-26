"""Switch lifecycle with a simulated WebView and real isolated ledger backups."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys
import types
import unittest

from standalone_accounting_company_registry import StandaloneCompanyRegistry
from standalone_accounting_desktop import main, AccountingDesktopAPI
from standalone_accounting_identity import LocalCompanyIdentity


class CloseEvent:
    def __init__(self): self.callback=None
    def __iadd__(self,callback): self.callback=callback; return self


class FakeWindow:
    def __init__(self,api):
        self.api=api
        self.events=types.SimpleNamespace(closing=CloseEvent())
    def destroy(self):
        # The fake start loop invokes the close event synchronously itself.
        pass


class CompanySwitchTests(unittest.TestCase):
    def test_two_company_switches_use_distinct_books_and_verified_exit_backups(self):
        with TemporaryDirectory(prefix='madar-r10-switch-') as temp:
            root=Path(temp)
            (root/'accounting.html').write_text('<html><head></head><body></body></html>',encoding='utf-8')
            hub=root/'hub';hub.mkdir()
            registry=StandaloneCompanyRegistry(hub)
            a=registry.create_company('شرکت الف')
            b=registry.create_company('شرکت ب')
            books=[registry.company_data_directory(a['id']),registry.company_data_directory(b['id'])]
            def authenticate(store):
                if not store.initialized():
                    store.add_user('synthetic_admin','SyntheticAdminSecurePass2026','admin')
                token=store.login('synthetic_admin','SyntheticAdminSecurePass2026')
                return store.require_session(token),token
            selection=[{'name':a['name'],'path':books[0]},
                       {'name':b['name'],'path':books[1]}]
            windows=[]
            webview=types.ModuleType('webview')
            def create_window(title,url,*,js_api,**_kwargs):
                current=FakeWindow(js_api)
                windows.append(current)
                return current
            def run_webview():
                current=windows[-1]
                if len(windows)==1:
                    self.assertEqual(current.api.standaloneAccountingRead()['view']['companyWorkspaceLabel'],'شرکت الف')
                    self.assertTrue(current.api.standaloneAccountingRequestCompanySwitch())
                else:
                    self.assertEqual(current.api.standaloneAccountingRead()['view']['companyWorkspaceLabel'],'شرکت ب')
                    self.assertFalse(current.api._switch_requested)
                self.assertTrue(current.events.closing.callback())
            webview.create_window=create_window
            webview.start=run_webview
            with patch.dict(sys.modules,{'webview':webview}), patch(
                    'standalone_accounting_company_registry.pick_company_dialog',
                    side_effect=selection) as chosen, patch(
                    'standalone_accounting_desktop._native_accounting_login',
                    side_effect=authenticate):
                self.assertEqual(main(['--companies-dir',str(hub),
                    '--site-dir',str(root)]),0)
            self.assertEqual(chosen.call_count,2)
            self.assertEqual(len(windows),2)
            self.assertEqual(windows[0].api.path.parent,books[0])
            self.assertEqual(windows[1].api.path.parent,books[1])
            for book in books:
                self.assertTrue((book/'standalone-accounting.sqlite3').is_file())
                self.assertTrue((book/'local-users.json').is_file())
                self.assertGreaterEqual(len(list((book/'standalone-accounting-backups').glob('*.sqlite3'))),2)
                self.assertEqual(AccountingDesktopAPI(book).standaloneAccountingRead()['revision'],0)

    def test_switch_denied_without_company_mode(self):
        with TemporaryDirectory() as temp:
            api=AccountingDesktopAPI(Path(temp))
            with self.assertRaises(RuntimeError):api.standaloneAccountingRequestCompanySwitch()


if __name__=='__main__':unittest.main()
