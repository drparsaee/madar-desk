"""Restore one book plus its print/entry/issuer library, never live APPDATA."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from standalone_accounting_desktop import AccountingDesktopAPI
from standalone_accounting_auto_backup import AutomaticStandaloneBackups
from standalone_accounting_restore import (
    restore_standalone_accounting, preview_template_companion,
    StandaloneRestoreError,
)
from standalone_accounting_restore_ui import preview_restore_candidate
from standalone_accounting_template_store import StandaloneAccountingTemplateStore


class TemplateCompanionRestore(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix='madar-r10-template-restore-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.src=self.root/'original';self.src.mkdir()
        self.destination=self.root/'restored';self.destination.mkdir()
        api=AccountingDesktopAPI(self.src)
        api.standaloneAccountingRead()
        api.standaloneAccountingTemplateSave('entry','فرم چاپ',{
            'format':'madar-invoice-lines-v1','version':1,'title':'فرم چاپ','currency':'RIAL',
            'lines':[{'description':'نمونه','quantity':'2','unitPrice':'300',
                      'accountId':'4000','itemId':''}]})
        api.standaloneAccountingTemplateSave('issuer','سربرگ',{
            'format':'madar-issuer-profile-v1','profile':{'legalName':'ناشر آزمایشی'}})
        self.backup=AutomaticStandaloneBackups(self.src,plaintext_acknowledged=True).backup_now()

    def test_companion_preflight_and_restore_both_files_without_mutating_source(self):
        source_bytes=self.backup.read_bytes()
        companion=self.backup.with_suffix('.templates.json')
        original=companion.read_bytes()
        preview=preview_restore_candidate(self.backup,self.destination)
        self.assertTrue(preview['has_template_companion'])
        self.assertEqual(preview['template_count'],2)
        self.assertFalse((self.destination/'invoice-templates.json').exists())
        restored=restore_standalone_accounting(self.backup,preview['destination'],
              plaintext_acknowledged=True,offline_acknowledged=True)
        self.assertEqual(restored.parent,self.destination)
        store=StandaloneAccountingTemplateStore(self.destination)
        self.assertEqual(len(store.list('entry')['templates']),1)
        self.assertEqual(len(store.list('issuer')['templates']),1)
        self.assertEqual(self.backup.read_bytes(),source_bytes)
        self.assertEqual(companion.read_bytes(),original)
        self.assertEqual(AccountingDesktopAPI(self.destination).standaloneAccountingRead()['revision'],0)

    def test_existing_template_never_overwritten_or_financial_db_created(self):
        dst=self.destination/'invoice-templates.json'
        dst.write_text('User existing data',encoding='utf-8')
        with self.assertRaises(FileExistsError):
            preview_restore_candidate(self.backup,self.destination)
        with self.assertRaises(FileExistsError):
            restore_standalone_accounting(self.backup,self.destination/'standalone-accounting.sqlite3',
                plaintext_acknowledged=True,offline_acknowledged=True)
        self.assertEqual(dst.read_text('utf-8'),'User existing data')
        self.assertFalse((self.destination/'standalone-accounting.sqlite3').exists())

    def test_invalid_or_corrupt_companion_blocks_whole_restore(self):
        companion=self.backup.with_suffix('.templates.json')
        companion.write_text('{',encoding='utf-8')
        with self.assertRaises(StandaloneRestoreError):
            preview_template_companion(self.backup,self.destination/'standalone-accounting.sqlite3')
        with self.assertRaises(StandaloneRestoreError):
            restore_standalone_accounting(self.backup,self.destination/'standalone-accounting.sqlite3',
                plaintext_acknowledged=True,offline_acknowledged=True)
        self.assertEqual(list(self.destination.iterdir()),[])

    def test_forged_default_reference_rejected_atomically(self):
        companion=self.backup.with_suffix('.templates.json')
        obj=json.loads(companion.read_text('utf-8'))
        obj['defaults']['entry']='f'*32
        companion.write_text(json.dumps(obj),encoding='utf-8')
        with self.assertRaises(StandaloneRestoreError):
            restore_standalone_accounting(self.backup,self.destination/'standalone-accounting.sqlite3',
                plaintext_acknowledged=True,offline_acknowledged=True)
        self.assertFalse(any(self.destination.iterdir()))


if __name__=='__main__':unittest.main()
