import tempfile
import unittest
from pathlib import Path

from standalone_accounting import StandaloneAccountingStore
from standalone_task_prepare import prepare_from_saved_task


class RialCoreTests(unittest.TestCase):
    def test_rial_book_order_and_unpriced_supplier_stay_out_of_general_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StandaloneAccountingStore(Path(directory) / 'rial.sqlite3', default_currency='RIAL')
            accounts = {'admin': {'username': 'admin', 'role': 'admin'}}
            at = '2026-10-22T12:00:00+00:00'
            revision = 0
            for event, party_id, kind in [('buyer', 'client', 'customer'), ('vendor', 'bindery', 'vendor')]:
                result = store.command({'type':'party.register','eventId':event,
                    'partyId':party_id,'name':party_id,'kind':kind},
                    actor='admin',accounts=accounts,expected_revision=revision,now=at)
                revision = result['revision']
            tasks = [{'id':'book-1','title':'کتاب بهمان','description':'۴۰۰ صفحه وزیری سیاه و سفید',
                'salePartyId':'client','saleCurrency':'RIAL','saleQuantity':100,
                'saleUnitPrice':125,'checklist':[{'id':'step-1','text':'صحافی',
                'expenseItems':[{'id':'binding-expense','description':'صحافی چسب گرم',
                'partyId':'bindery','quantity':100,'unitPrice':None,'currency':'RIAL'}]}]}]
            sale = prepare_from_saved_task(store,{'taskId':'book-1','expenseId':None},
                    tasks=tasks,actor='admin',accounts=accounts,now=at)
            self.assertFalse(sale['existing'])
            work = prepare_from_saved_task(store,{'taskId':'book-1','expenseId':'binding-expense'},
                    tasks=tasks,actor='admin',accounts=accounts,now=at)
            self.assertFalse(work['existing'])
            view = store.read(actor='admin',accounts=accounts)['view']
            self.assertEqual(next(iter(view['invoices'].values()))['total'],12500)
            self.assertIsNone(view['contractorJobs']['binding-expense']['unitPrice'])
            self.assertFalse(view['journals'])
            self.assertNotIn('۴۰۰ صفحه',str(view))
            self.assertTrue(prepare_from_saved_task(store,{'taskId':'book-1','expenseId':None},
                    tasks=tasks,actor='admin',accounts=accounts,now=at)['existing'])

    def test_new_rial_ledger_and_exact_single_rial_invoice(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StandaloneAccountingStore(Path(directory) / 'rial.sqlite3', default_currency='RIAL')
            accounts = {'admin': {'username': 'admin', 'role': 'admin'}}
            result = store.read(actor='admin', accounts=accounts)
            self.assertEqual(result['view']['currency'], 'RIAL')
            now = '2026-10-22T12:00:00+00:00'
            register = store.command({'type':'party.register','eventId':'e.party',
                                      'partyId':'c1','name':'Customer','kind':'customer'},
                                     actor='admin',accounts=accounts,expected_revision=0,now=now)
            invoice = store.command({'type':'invoice.create','eventId':'e.invoice',
                                     'invoiceId':'inv1','partyId':'c1','documentDate':'2026-10-22',
                                     'lines':[{'description':'Book','quantity':3,'unitPrice':1}]},
                                    actor='admin',accounts=accounts,expected_revision=1,now=now)
            self.assertEqual(invoice['result']['total'], 3)
            self.assertEqual(invoice['view']['currency'], 'RIAL')
            self.assertEqual(StandaloneAccountingStore(Path(directory)/'rial.sqlite3').read(
                actor='admin',accounts=accounts)['view']['currency'], 'RIAL')

    def test_old_toman_ledger_remains_toman(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'old.sqlite3'
            accounts = {'admin':{'username':'admin','role':'admin'}}
            old = StandaloneAccountingStore(path)
            old.command({'type':'party.register','eventId':'e1','partyId':'c1',
                         'name':'Customer','kind':'customer'},actor='admin',accounts=accounts,
                        expected_revision=0,now='2026-10-22T12:00:00+00:00')
            self.assertEqual(StandaloneAccountingStore(path,default_currency='RIAL').read(
                actor='admin',accounts=accounts)['view']['currency'], 'TOMAN')
