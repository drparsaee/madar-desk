import tempfile
import unittest
from pathlib import Path

from standalone_accounting import StandaloneAccountingStore
from standalone_accounting_backup import backup_standalone_accounting
from standalone_rial_migration import convert_state, migrate_offline


NOW = '2026-10-22T12:00:00+00:00'
USERS = {'admin': {'username': 'admin', 'role': 'admin'}}


class RialMigrationTests(unittest.TestCase):
    def fixture(self, root):
        store = StandaloneAccountingStore(root / 'standalone-accounting.sqlite3')
        commands = [
            {'type':'party.register','eventId':'e1','partyId':'client1',
             'name':'Sample Customer','kind':'customer'},
            {'type':'invoice.create','eventId':'e2','invoiceId':'inv1',
             'partyId':'client1','documentDate':'2026-10-22',
             'lines':[{'description':'Printed book','quantity':100,'unitPrice':150000}]},
            {'type':'invoice.approve','eventId':'e3','invoiceId':'inv1'},
            {'type':'invoice.issue','eventId':'e4','invoiceId':'inv1',
             'postingDate':'2026-10-22'},
            {'type':'receipt.record','eventId':'e5','receiptId':'receipt1',
             'partyId':'client1','accountId':'1010','postingDate':'2026-10-22',
             'allocations':[{'invoiceId':'inv1','amount':5000}]},
        ]
        for i, command in enumerate(commands):
            store.command(command,actor='admin',accounts=USERS,
                          expected_revision=i,now=NOW)
        return store

    def test_exact_historical_conversion_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = self.fixture(root)
            backup_dir = root / 'backup'
            backup_dir.mkdir()
            backup = backup_standalone_accounting(original.path,
                backup_dir / 'standalone-accounting-old.sqlite3',
                plaintext_acknowledged=True)
            destination = root / 'converted' / 'standalone-accounting.sqlite3'
            destination.parent.mkdir()
            preview = migrate_offline(backup,destination,
                offline_acknowledged=True,plaintext_acknowledged=True)
            self.assertEqual(preview['events'],5)
            self.assertFalse(destination.exists())
            result = migrate_offline(backup,destination,offline_acknowledged=True,
                                    plaintext_acknowledged=True,apply=True)
            self.assertEqual(result['currency'],'RIAL')
            rial = StandaloneAccountingStore(destination,default_currency='RIAL').read(
                actor='admin',accounts=USERS)
            self.assertEqual(rial['view']['invoices']['inv1']['total'],150000000)
            self.assertEqual(rial['view']['parties']['client1']['receivable'],149950000)
            self.assertEqual(original.read(actor='admin',accounts=USERS)['view']['currency'],'TOMAN')
            with self.assertRaises(FileExistsError):
                migrate_offline(backup,destination,offline_acknowledged=True,
                                plaintext_acknowledged=True,apply=True)

    def test_acknowledgement_required(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(PermissionError):
                migrate_offline(Path(temp)/'any',Path(temp)/'destination')

    def test_legacy_toman_proforma_and_converted_draft_scale_exactly(self):
        with tempfile.TemporaryDirectory() as temp:
            old = StandaloneAccountingStore(Path(temp)/'old.sqlite3')
            events = [
                {'type':'party.register','eventId':'party','partyId':'client1',
                 'name':'Customer','kind':'customer'},
                {'type':'proforma.create','eventId':'quote','proformaId':'q1',
                 'partyId':'client1','documentDate':'2026-10-22',
                 'lines':[{'description':'Service','quantity':1,'unitPrice':13}],
                 'discount':2,'tax':0},
                {'type':'proforma.send','eventId':'sent','proformaId':'q1'},
                {'type':'proforma.accept','eventId':'accepted','proformaId':'q1'},
                {'type':'proforma.convert','eventId':'converted','proformaId':'q1',
                 'invoiceId':'i1','documentDate':'2026-10-22'},
            ]
            for revision, command in enumerate(events):
                old.command(command,actor='admin',accounts=USERS,
                            expected_revision=revision,now=NOW)
            with old._connect() as conn:
                _, state=old._current(conn)
            transformed=convert_state(state)
            from accounting_core import accounting_view
            view=accounting_view(transformed,actor='admin',accounts=USERS)
            self.assertEqual(view['currency'],'RIAL')
            self.assertEqual(view['proformas']['q1']['total'],110)
            self.assertEqual(view['proformas']['q1']['convertedInvoiceId'],'i1')
            self.assertEqual(view['invoices']['i1']['total'],110)
            self.assertFalse(view['journals'])


if __name__ == '__main__':
    unittest.main()
