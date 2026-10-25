"""Synthetic, offline, isolated multi-company issue, backup and restore QA."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from standalone_accounting_company_registry import StandaloneCompanyRegistry, CompanySessionGuard, CompanyRegistryError
from standalone_accounting_desktop import AccountingDesktopAPI
from standalone_accounting_auto_backup import AutomaticStandaloneBackups
from standalone_accounting_restore import restore_standalone_accounting, _check_input


class R9CompanyWorkflow(unittest.TestCase):
    def test_two_company_issued_invoice_and_backup_restore_are_disjoint(self):
        with TemporaryDirectory(prefix='r9-multi-company-') as root:
            hub=Path(root)/'companies';hub.mkdir()
            registry=StandaloneCompanyRegistry(hub)
            a=registry.create_company('شرکت آزمایشی الف')
            b=registry.create_company('شرکت آزمایشی ب')
            a_root=registry.company_data_directory(a['id'])
            b_root=registry.company_data_directory(b['id'])
            a_api=AccountingDesktopAPI(a_root,company_name=a['name'])
            b_api=AccountingDesktopAPI(b_root,company_name=b['name'])
            def command(api,current,body):
                return api.standaloneAccountingCommand({
                    'expectedRevision':current['revision'],'command':body})
            with CompanySessionGuard(a_root):
                with self.assertRaises(CompanyRegistryError):
                    CompanySessionGuard(a_root).acquire()
                read=a_api.standaloneAccountingRead()
                read=command(a_api,read,{'type':'party.register','eventId':'a-party-register',
                    'partyId':'a.customer','name':'طرف‌حساب شرکت الف','kind':'customer'})
                read=command(a_api,read,{'type':'invoice.create','eventId':'a-invoice-create',
                    'invoiceId':'a.invoice','partyId':'a.customer','documentDate':'2026-10-18',
                    'lines':[{'description':'چاپ آزمایشی','quantity':2,'unitPrice':500000}]})
                read=command(a_api,read,{'type':'invoice.approve','eventId':'a-invoice-approve',
                    'invoiceId':'a.invoice'})
                read=command(a_api,read,{'type':'invoice.issue','eventId':'a-invoice-issue',
                    'invoiceId':'a.invoice','postingDate':'2026-10-19'})
                self.assertEqual(read['view']['invoices']['a.invoice']['total'],1000000)
                self.assertEqual(read['view']['invoices']['a.invoice']['status'],'issued')
                self.assertEqual(len(read['view']['journals']),1)
                self.assertEqual(read['revision'],4)
                book_b=b_api.standaloneAccountingRead()
                self.assertEqual(book_b['revision'],0)
                self.assertNotIn('a.invoice',book_b['view']['invoices'])
                self.assertNotIn('a.customer',book_b['view']['parties'])
                self.assertEqual(book_b['view']['companyWorkspaceLabel'],b['name'])
                # Per-company appearance must never import customers, currency or journals.
                a_api.standaloneAccountingTemplateSave('entry','چاپ الف',{
                    'format':'madar-invoice-lines-v1','version':1,'title':'چاپ الف',
                    'currency':'RIAL','lines':[{'description':'تست','quantity':'2',
                    'unitPrice':'500000','accountId':'4000','itemId':''}]})
                a_api.standaloneAccountingTemplateSave('issuer','صادرکننده الف',{
                    'format':'madar-issuer-profile-v1','profile':{'legalName':'صادرکننده الف'}})
                self.assertFalse(b_api.standaloneAccountingTemplateList('entry')['templates'])
                self.assertFalse(b_api.standaloneAccountingTemplateList('issuer')['templates'])
                backup_a=AutomaticStandaloneBackups(a_root,plaintext_acknowledged=True).backup_now()
                backup_b=AutomaticStandaloneBackups(b_root,plaintext_acknowledged=True).backup_now()
                self.assertEqual(_check_input(backup_a)[0],4)
                self.assertEqual(_check_input(backup_b)[0],0)
                self.assertTrue(backup_a.with_suffix('.templates.json').exists())
                self.assertFalse(backup_b.with_suffix('.templates.json').exists())
                restore_root=Path(root)/'restored_a';restore_root.mkdir()
                restored=restore_standalone_accounting(backup_a,
                    restore_root/'standalone-accounting.sqlite3',
                    plaintext_acknowledged=True,offline_acknowledged=True)
                self.assertTrue(restored.is_file())
                restored_view=AccountingDesktopAPI(restore_root).standaloneAccountingRead()
                self.assertEqual(restored_view['revision'],4)
                self.assertIn('a.invoice',restored_view['view']['invoices'])
                with self.assertRaises(FileExistsError):
                    restore_standalone_accounting(backup_a,restored,
                        plaintext_acknowledged=True,offline_acknowledged=True)
                self.assertEqual(b_api.standaloneAccountingRead()['revision'],0)


if __name__=='__main__':unittest.main()
