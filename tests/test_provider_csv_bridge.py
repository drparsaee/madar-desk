"""Synthetic local file chooser -> preview; no production accounting data."""
import csv
from io import StringIO
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from provider_csv_bridge import ProviderCsvPreviewBridge
from provider_csv_staging import CsvStagingError
from standalone_accounting_desktop import AccountingDesktopAPI, JS_BRIDGE


class ProviderCsvBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.columns={
            'parties':{'id':'Code','name':'Name','kind':'Role'},
            'invoices':{'id':'Doc','partyId':'Party','kind':'Type','date':'Day',
                        'status':'State','total':'Sum'},
            'transactions':{'id':'Txn','partyId':'Party','documentId':'Doc',
                            'kind':'Type','date':'Day','amount':'Sum'},
        }
        self.values={
            'parties':[['party1','Synthetic person','customer']],
            'invoices':[['invoice1','party1','invoice','2026-01-01','issued','100']],
            'transactions':[['receipt1','party1','invoice1','receipt','2026-01-02','10']],
        }
        self.paths={}
        for group,mapping in self.columns.items():
            path=self.root/(group+'.csv')
            out=StringIO(newline='')
            writer=csv.writer(out)
            writer.writerow(list(mapping.values()))
            writer.writerows(self.values[group])
            path.write_bytes(out.getvalue().encode('utf-8-sig'))
            self.paths[group]=str(path)
        self.request={
            'schemaVersion':1,'provider':'SyntheticProvider','currency':'RIAL',
            'datasets':{group:{'path':path,'format':'csv','encoding':'utf-8-sig',
               'delimiter':',','mapping':self.columns[group],
               'ignoreColumns':[],'valueMaps':{}} for group,path in self.paths.items()},
        }

    def select_all(self,bridge):
        for group,path in self.paths.items():
            output=bridge.select(group,'utf-8-sig',',',path)
            self.assertEqual(output['columns'],list(self.columns[group].values()))
            self.assertFalse(output['canceled'])

    def test_explicit_file_selection_required_and_preview_keeps_bytes(self):
        bridge=ProviderCsvPreviewBridge()
        with self.assertRaises(CsvStagingError):
            bridge.preview(self.request)
        before={p:Path(p).read_bytes() for p in self.paths.values()}
        self.select_all(bridge)
        output=bridge.preview(self.request)
        self.assertEqual(output['counts'],{'parties':1,'invoices':1,'transactions':1})
        self.assertTrue(output['structuralChecksPassed'])
        self.assertFalse(output['canApplyToMadar'])
        self.assertEqual(before,{p:Path(p).read_bytes() for p in self.paths.values()})

    def test_path_or_encoding_tamper_rejected(self):
        bridge=ProviderCsvPreviewBridge()
        self.select_all(bridge)
        altered=dict(self.request)
        altered['datasets']={k:dict(v) for k,v in self.request['datasets'].items()}
        altered['datasets']['invoices']['path']=self.paths['parties']
        with self.assertRaisesRegex(CsvStagingError,'selected local file'):
            bridge.preview(altered)
        altered['datasets']['invoices']['path']=self.paths['invoices']
        altered['datasets']['invoices']['encoding']='cp1256'
        with self.assertRaisesRegex(CsvStagingError,'selected local file'):
            bridge.preview(altered)

    def test_cancel_clears_selection(self):
        bridge=ProviderCsvPreviewBridge()
        self.select_all(bridge)
        self.assertTrue(bridge.select('invoices','utf-8-sig',',',None)['canceled'])
        with self.assertRaises(CsvStagingError):
            bridge.preview(self.request)

    def test_fake_native_desktop_window_only_selected_csv(self):
        root=self.root/'never-created-ledger'
        api=AccountingDesktopAPI(root)
        class FakeWindow:
            def __init__(self, selections):
                self.selections=iter(selections)
            def create_file_dialog(self,*_args,**_kwargs):
                return next(self.selections)
        api._native_window=FakeWindow(list(self.paths.values()))
        fake_webview=types.SimpleNamespace(FileDialog=types.SimpleNamespace(OPEN='open'))
        with patch.dict(sys.modules,{'webview':fake_webview}):
            for group in self.paths:
                selected=api.standaloneAccountingCsvChooseFile(group,'utf-8-sig',',')
                self.assertEqual(selected['path'],self.paths[group])
        preview=api.standaloneAccountingCsvPreview(self.request)
        self.assertEqual(preview['counts']['invoices'],1)
        self.assertFalse(root.exists(),'Selecting/previewing CSV must not create a ledger')
        self.assertIn('standaloneAccountingCsvChooseFile',JS_BRIDGE)
        self.assertIn('standaloneAccountingCsvPreview',JS_BRIDGE)

    def test_native_desktop_viewer_denied_before_file_dialog(self):
        root=self.root/'no-ledger'
        api=AccountingDesktopAPI(root)
        with patch.object(api,'_require_authenticated',side_effect=PermissionError('viewer')):
            with self.assertRaises(PermissionError):
                api.standaloneAccountingCsvChooseFile('parties','utf-8-sig',',')
            with self.assertRaises(PermissionError):
                api.standaloneAccountingCsvPreview(self.request)
        self.assertFalse(root.exists())

    def test_main_bridge_accounting_wrapper_exports_only_expected_methods(self):
        from native_app import ACCOUNTING_JS_BRIDGE
        self.assertIn('standaloneAccountingCsvChooseFile',ACCOUNTING_JS_BRIDGE)
        self.assertIn('standaloneAccountingCsvPreview',ACCOUNTING_JS_BRIDGE)
        self.assertNotIn("'saveState'",ACCOUNTING_JS_BRIDGE)


if __name__=='__main__':
    unittest.main()
