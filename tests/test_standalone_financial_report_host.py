"""Synthetic RIAL report invariants and standalone host integration."""
import tempfile
import unittest
from pathlib import Path

from accounting_reporting import ledger_reports
from standalone_financial_report_host import attach_verified_reports
from standalone_accounting_desktop import AccountingDesktopAPI


class FinancialReportsHostTests(unittest.TestCase):
    def test_rial_reports_from_committed_invoice_and_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            api = AccountingDesktopAPI(Path(folder) / 'isolated-finance')
            first = api.standaloneAccountingRead()
            self.assertEqual(first['view']['currency'], 'RIAL')
            self.assertTrue(first['view']['financialReports']['reconciled'])
            self.assertEqual(first['view']['financialReports']['trialBalance']['totalDebit'], 0)
            commands = [
                dict(type='party.register', eventId='evt-1', partyId='buyer',
                     name='Customer', kind='customer'),
                dict(type='invoice.create', eventId='evt-2', invoiceId='inv-1',
                     partyId='buyer', documentDate='2026-10-01',
                     lines=[dict(description='Book', quantity=3, unitPrice=1)]),
                dict(type='invoice.approve',eventId='evt-3',invoiceId='inv-1'),
                dict(type='invoice.issue',eventId='evt-4',invoiceId='inv-1',
                     postingDate='2026-10-02'),
                dict(type='receipt.record',eventId='evt-5',receiptId='rec-1',
                     partyId='buyer',accountId='1010',postingDate='2026-10-03',
                     allocations=[dict(invoiceId='inv-1',amount=1)]),
            ]
            revision = first['revision']
            for command in commands:
                result = api.standaloneAccountingCommand(
                    {'command':command,'expectedRevision':revision})
                revision = result['revision']
            reports = api.standaloneAccountingRead()['view']['financialReports']
            self.assertEqual(reports['currency'],'RIAL')
            self.assertEqual(reports['profitLoss']['net'],3)
            self.assertEqual(reports['trialBalance']['totalDebit'],3)
            self.assertEqual(reports['trialBalance']['totalCredit'],3)
            self.assertEqual(reports['counterpartyBalances'][0]['receivable'],2)
            self.assertEqual(reports['cashBankBalances'][1]['balance'],1)
            self.assertEqual(reports['balanceSheet']['assets'],3)

    def test_fail_closed_on_counterparty_gl_disagreement(self):
        valid = {'currency':'RIAL', 'accounts':{
            '1200':{'name':'AR','kind':'asset','liquid':False}},
            'parties':{'buyer':{'name':'Buyer','receivable':0,'payable':0}},
            'journals':[]}
        result = attach_verified_reports({'revision':0,'view':valid})
        self.assertTrue(result['view']['financialReports']['reconciled'])
        invalid = {**valid, 'parties':{'buyer':{'name':'Buyer','receivable':1,'payable':0}}}
        with self.assertRaisesRegex(ValueError,'reconcile'):
            attach_verified_reports({'revision':0,'view':invalid})

    def test_rial_dated_reports_do_not_use_future_settlement(self):
        with tempfile.TemporaryDirectory() as folder:
            api = AccountingDesktopAPI(Path(folder) / 'dated-ledger')
            commands = [
                {'type':'party.register','eventId':'v1','partyId':'buyer',
                 'name':'Buyer','kind':'customer'},
                {'type':'invoice.create','eventId':'v2','invoiceId':'i1',
                 'partyId':'buyer','documentDate':'2026-10-01',
                 'lines':[{'description':'Work','quantity':2,'unitPrice':5}]},
                {'type':'invoice.approve','eventId':'v3','invoiceId':'i1'},
                {'type':'invoice.issue','eventId':'v4','invoiceId':'i1',
                 'postingDate':'2026-10-02'},
                {'type':'receipt.record','eventId':'v5','receiptId':'r1',
                 'partyId':'buyer','accountId':'1010','postingDate':'2026-10-03',
                 'allocations':[{'invoiceId':'i1','amount':4}]},
            ]
            for revision, command in enumerate(commands):
                api.standaloneAccountingCommand({'command':command,
                                                  'expectedRevision':revision})
            view = api.standaloneAccountingRead()['view']
            earlier = ledger_reports(view, through_date='2026-10-02')
            self.assertEqual(earlier['counterpartyBalances'][0]['receivable'],10)
            self.assertEqual(earlier['cashBankBalances'][1]['balance'],0)
            self.assertEqual(earlier['balanceSheet']['assets'],10)
            later = ledger_reports(view, through_date='2026-10-03')
            self.assertEqual(later['counterpartyBalances'][0]['receivable'],6)
            self.assertEqual(later['cashBankBalances'][1]['balance'],4)
            self.assertEqual(later['profitLoss']['net'],10)

    def test_legacy_fake_host_output_untouched(self):
        result={'revision':0,'view':{'standalone':True}}
        self.assertIs(attach_verified_reports(result),result)

if __name__ == '__main__':
    unittest.main()
