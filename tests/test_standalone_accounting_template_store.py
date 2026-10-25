"""Disposable directories only, never installed accounting or APPDATA."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from standalone_accounting_template_store import (
    StandaloneAccountingTemplateStore, TemplateStoreError,
)
from standalone_accounting_desktop import AccountingDesktopAPI
from standalone_accounting_auto_backup import AutomaticStandaloneBackups


def entry(name='خدمات', currency='RIAL'):
    return {"format":"madar-invoice-lines-v1", "version":1, "title":name,
            "currency":currency, "lines":[{"description":"کار", "quantity":"2", "unitPrice":"300",
            "accountId":"4000", "itemId":""}]}


def printable():
    return {"format":"madar-print-layout-v1","version":1,"title":"نمونه"}


class TemplateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.a=Path(self.temp.name)/"a"
        self.b=Path(self.temp.name)/"b"
        self.a.mkdir(); self.b.mkdir()
        self.store=StandaloneAccountingTemplateStore(self.a)

    def test_separate_company_libs_and_defaults(self):
        first=self.store.save('entry','الگوی A',entry())
        other=StandaloneAccountingTemplateStore(self.b)
        self.assertEqual(other.list('entry'), {'templates':[], 'defaultId':''})
        second=other.save('entry','الگوی B',entry(currency='TOMAN'))
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(self.store.list('entry')['defaultId'],first['id'])
        self.assertEqual(other.list('entry')['defaultId'],second['id'])
        self.assertNotIn('الگوی A', (self.b/'invoice-templates.json').read_text('utf-8'))

    def test_write_update_copy_delete_and_previous_backup(self):
        one=self.store.save('entry','اول',entry())
        self.store.save('entry','ویرایش',entry('جدید'),one['id'])
        self.assertEqual(self.store.list('entry')['templates'][0]['title'],'ویرایش')
        self.assertTrue(self.store.previous.exists())
        copy=self.store.duplicate('entry',one['id'])
        self.assertEqual(len(self.store.list('entry')['templates']),2)
        self.store.set_default('entry',copy['id'])
        self.assertEqual(self.store.list('entry')['defaultId'],copy['id'])
        self.store.delete('entry',copy['id'])
        self.assertEqual(self.store.list('entry')['defaultId'],one['id'])

    def test_reject_invalid_kinds_and_payload_and_missing_id(self):
        for kind in ('../entry','',None,'unknown'):
            with self.assertRaises(TemplateStoreError): self.store.list(kind)
        with self.assertRaises(TemplateStoreError): self.store.save('entry','',entry())
        with self.assertRaises(TemplateStoreError): self.store.save('entry','bad',{"lines":[]})
        with self.assertRaises(TemplateStoreError): self.store.save('print','bad',entry())
        with self.assertRaises(TemplateStoreError): self.store.save('entry','bad',entry(),'../escape')
        with self.assertRaises(TemplateStoreError): self.store.delete('entry','0'*32)
        with self.assertRaises(TemplateStoreError): self.store.set_default('print','0'*32)

    def test_malformed_file_fails_closed(self):
        (self.a/'invoice-templates.json').write_text('{',encoding='utf-8')
        with self.assertRaises(TemplateStoreError): self.store.list('entry')
        with self.assertRaises(TemplateStoreError): self.store.save('entry','new',entry())

    def test_symlink_rejected_when_supported(self):
        link=self.a/'invoice-templates.json'
        try:link.symlink_to(self.b/'invoice-templates.json')
        except (OSError,NotImplementedError): self.skipTest('No symlink privilege')
        with self.assertRaises(TemplateStoreError): self.store.list('entry')

    def test_bridge_template_edit_never_changes_financial_revision(self):
        api=AccountingDesktopAPI(self.a)
        initial=api.standaloneAccountingRead()['revision']
        record=api.standaloneAccountingTemplateSave('entry','تست',entry())
        self.assertEqual(api.standaloneAccountingRead()['revision'],initial)
        self.assertEqual(api.standaloneAccountingTemplateList('entry')['templates'][0]['id'],record['id'])
        api.standaloneAccountingTemplateDefault('entry',record['id'])
        api.standaloneAccountingTemplateDuplicate('entry',record['id'])
        api.standaloneAccountingTemplateDelete('entry',record['id'])
        self.assertEqual(api.standaloneAccountingRead()['revision'],initial)
        api._exit_backed_up=True
        with self.assertRaises(RuntimeError): api.standaloneAccountingTemplateSave('entry','no',entry())

    def test_periodic_financial_backup_has_matching_template_companion(self):
        api=AccountingDesktopAPI(self.a)
        api.standaloneAccountingRead()
        api.standaloneAccountingTemplateSave('entry','نمونه',entry())
        backups=AutomaticStandaloneBackups(self.a,plaintext_acknowledged=True,max_backups=2)
        first=backups.backup_now()
        companion=first.with_suffix('.templates.json')
        self.assertTrue(companion.is_file())
        self.assertEqual(json.loads(companion.read_text('utf-8'))['templates'][0]['title'],'نمونه')
        api.standaloneAccountingTemplateSave('entry','بعدی',entry('بعدی'))
        second=backups.backup_now()
        self.assertEqual(len(json.loads(second.with_suffix('.templates.json').read_text('utf-8'))['templates']),2)
        third=backups.backup_now()
        self.assertFalse(first.exists())
        self.assertFalse(companion.exists())
        self.assertTrue(third.with_suffix('.templates.json').exists())


if __name__=='__main__': unittest.main()
