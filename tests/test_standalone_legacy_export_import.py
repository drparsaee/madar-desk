import json
import tempfile
import unittest
from pathlib import Path

from standalone_accounting import StandaloneAccountingStore
from standalone_legacy_export_import import import_reviewed_export


class PreviousSoftwareImportTests(unittest.TestCase):
    def fixture(self):
        return {
            'schemaVersion': 1, 'currency': 'TOMAN',
            'parties':[{'id':'client1','name':'Book buyer','kind':'customer'},
                       {'id':'bindery1','name':'Pooya bindery','kind':'vendor'}],
            'openingDeposits':[{'id':'opening1','accountId':'1010',
                                'postingDate':'2026-01-01','amount':3000000,
                                'note':'Audited synthetic opening deposit'}],
            'documents':[
                {'kind':'invoice','id':'inv1','partyId':'client1',
                 'documentDate':'2026-01-02','postingDate':'2026-01-03',
                 'status':'issued','lines':[{'description':'100 books',
                  'quantity':100,'unitPrice':50000}], 'discount':0,'tax':0},
                {'kind':'bill','id':'bill1','partyId':'bindery1',
                 'documentDate':'2026-01-02','postingDate':'2026-01-03',
                 'status':'issued','lines':[{'description':'Binding 100 books',
                  'quantity':100,'unitPrice':2000}], 'discount':0,'tax':0},
            ],
            'settlements':[{'kind':'receipt','id':'receipt1','partyId':'client1',
                            'accountId':'1010','postingDate':'2026-01-04',
                            'allocations':[{'documentId':'inv1','amount':100000}]},
                           {'kind':'payment','id':'payment1','partyId':'bindery1',
                            'accountId':'1010','postingDate':'2026-01-04',
                            'allocations':[{'documentId':'bill1','amount':50000}]}],
        }

    def test_preview_no_mutation_and_full_rial_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/'previous-system.json'
            source.write_text(json.dumps(self.fixture()),encoding='utf-8')
            dest = root/'standalone-accounting.sqlite3'
            kwargs={'offline_ack':True,'plaintext_ack':True}
            preview = import_reviewed_export(source,dest,**kwargs)
            self.assertTrue(preview['preview'])
            self.assertEqual(preview['invoices'],1)
            self.assertFalse(dest.exists())
            result = import_reviewed_export(source,dest,apply=True,**kwargs)
            self.assertFalse(result['preview'])
            store = StandaloneAccountingStore(dest,default_currency='RIAL')
            view = store.read(actor='admin',accounts={'admin':{'username':'admin','role':'admin'}})['view']
            self.assertEqual(view['currency'],'RIAL')
            self.assertEqual(view['invoices']['inv1']['total'],50000000)
            self.assertEqual(view['parties']['client1']['receivable'],49000000)
            self.assertEqual(view['parties']['bindery1']['payable'],1500000)
            with self.assertRaises(ValueError):
                import_reviewed_export(source,dest,apply=True,**kwargs)

    def test_malformed_source_fails_without_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source=root/'source.json'
            data=self.fixture()
            data['documents'][0]['lines'][0]['unitPrice']='50000'
            source.write_text(json.dumps(data),encoding='utf-8')
            destination=root/'standalone-accounting.sqlite3'
            with self.assertRaises(ValueError):
                import_reviewed_export(source,destination,apply=True,
                                       offline_ack=True,plaintext_ack=True)
            self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
