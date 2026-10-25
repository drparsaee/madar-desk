"""Host-backed independent quotation: no task store and no operational card."""
import tempfile
import unittest
from pathlib import Path

from standalone_accounting_desktop import AccountingDesktopAPI
from standalone_accounting_backup import backup_standalone_accounting
from standalone_accounting_restore import restore_standalone_accounting


class DesktopProformaAcceptance(unittest.TestCase):
    def test_direct_invoice_without_quote_or_task(self):
        with tempfile.TemporaryDirectory() as root:
            host=AccountingDesktopAPI(Path(root)/'standalone-only')
            commands=[
                {'type':'party.register','eventId':'p1','partyId':'direct.customer',
                 'name':'Direct Customer','kind':'customer'},
                {'type':'invoice.create','eventId':'inv-create','invoiceId':'direct.001',
                 'partyId':'direct.customer','documentDate':'2026-10-24',
                 'lines':[{'description':'Service','quantity':1,'unitPrice':1}]},
                {'type':'invoice.approve','eventId':'inv-approve',
                 'invoiceId':'direct.001'},
                {'type':'invoice.issue','eventId':'inv-issue',
                 'invoiceId':'direct.001','postingDate':'2026-10-24'},
            ]
            current=host.standaloneAccountingRead()
            for cmd in commands:
                current=host.standaloneAccountingCommand(
                    {'command':cmd,'expectedRevision':current['revision']})
            self.assertEqual(current['view']['invoices']['direct.001']['total'],1)
            self.assertEqual(current['view']['parties']['direct.customer']['receivable'],1)
            self.assertEqual(current['view']['proformas'],{})
            self.assertEqual(len(current['view']['journals']),1)

    def test_sales_quote_invoice_and_backup_remain_isolated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            private = root/'financial-data'
            host = AccountingDesktopAPI(private)
            self.assertFalse(private.exists())
            commands = [
                {'type':'party.register','eventId':'one','partyId':'buyer',
                 'name':'Customer','kind':'customer'},
                {'type':'proforma.create','eventId':'two','proformaId':'pf1',
                 'partyId':'buyer','documentDate':'2026-10-24',
                 'lines':[{'description':'Brochure printing','quantity':100,
                           'unitPrice':7}],'tax':0,'discount':0},
                {'type':'proforma.send','eventId':'three','proformaId':'pf1'},
                {'type':'proforma.accept','eventId':'four','proformaId':'pf1'},
                {'type':'proforma.convert','eventId':'five','proformaId':'pf1',
                 'invoiceId':'invoice.1','documentDate':'2026-10-24'},
                {'type':'invoice.approve','eventId':'six','invoiceId':'invoice.1'},
                {'type':'invoice.issue','eventId':'seven','invoiceId':'invoice.1',
                 'postingDate':'2026-10-24'}
            ]
            current = host.standaloneAccountingRead()
            self.assertEqual(current['view']['currency'],'RIAL')
            for idx, command in enumerate(commands):
                current = host.standaloneAccountingCommand(
                    {'command':command,'expectedRevision':current['revision']})
                self.assertEqual(current['revision'],idx+1)
                if idx < 6:
                    self.assertFalse(current['view']['journals'])
                    self.assertEqual(current['view']['parties']['buyer']['receivable'],0)
            self.assertEqual(current['view']['invoices']['invoice.1']['total'],700)
            self.assertEqual(current['view']['proformas']['pf1']['status'],'converted')
            self.assertEqual(current['view']['parties']['buyer']['receivable'],700)
            self.assertTrue(current['view']['financialReports']['reconciled'])
            self.assertEqual(len(current['view']['journals']),1)
            for forbidden in ['tasks.json','finance.json','madar-unified.sqlite3']:
                self.assertFalse((private/forbidden).exists())
            backup_dir=root/'backups'
            backup_dir.mkdir()
            backup_path=backup_dir/'isolated-backup.sqlite3'
            backup_standalone_accounting(private/'standalone-accounting.sqlite3',
                                         backup_path,plaintext_acknowledged=True)
            # Restore tested by the existing restore suite; only inspect
            # this snapshot through isolated API to avoid real system data.
            recovered_host=AccountingDesktopAPI(root/'recovered')
            self.assertEqual(host.standaloneAccountingRead()['revision'],7)
            self.assertTrue(backup_path.is_file())
            self.assertEqual(recovered_host.standaloneAccountingRead()['revision'],0)

if __name__=='__main__':
    unittest.main()
