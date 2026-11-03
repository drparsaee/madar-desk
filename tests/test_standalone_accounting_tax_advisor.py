import unittest
from math import inf, nan
from standalone_accounting_tax_advisor import preflight_einvoice

class TaxPreflightTests(unittest.TestCase):
    def test_incomplete_document_flags_blockers(self):
        out=preflight_einvoice({}, {})
        self.assertFalse(out['submissionPermitted'])
        self.assertGreaterEqual(len(out['issues']),5)

    def test_complete_looking_document_still_cannot_auto_submit(self):
        out=preflight_einvoice({'invoiceId':'demo-1','issueDate':'2026-10-26',
            'kind':'original','lines':[{'productServiceId':'demo',
                       'quantity':2,'unitPrice':500000}]},
            {'economicCode':'example','taxMemoryId':'example'})
        self.assertFalse(out['readyForSubmission'])
        self.assertFalse(out['submissionPermitted'])
        self.assertTrue(any(x['field']=='regulatoryRules' for x in out['issues']))

    def test_amendment_requires_reference(self):
        out=preflight_einvoice({'invoiceId':'draft','issueDate':'2026-10-26',
            'kind':'amendment','lines':[{'productServiceId':'x','quantity':1,'unitPrice':1}]},
            {'economicCode':'x','taxMemoryId':'x'})
        self.assertTrue(any(x['field']=='invoice.referenceTaxInvoiceId' for x in out['issues']))

    def test_nonfinite_floats_and_out_of_range_values_block_with_exact_fields(self):
        for field in ('quantity','unitPrice'):
            for invalid in (nan, inf, -inf, True, 0, -1, 1.5, '1', 10**18):
                with self.subTest(field=field,invalid=str(invalid)):
                    row={'productServiceId':'test','quantity':1,'unitPrice':100}
                    row[field]=invalid
                    out=preflight_einvoice({'invoiceId':'x','issueDate':'2026-10-26',
                                           'lines':[row]},
                                          {'economicCode':'demo','taxMemoryId':'demo'})
                    self.assertIn(f'lines.0.{field}', [x['field'] for x in out['issues']
                                   if x['severity']=='blocker'])
                    self.assertFalse(out['submissionPermitted'])

    def test_exact_line_total_overflow_is_blocked(self):
        out=preflight_einvoice({'invoiceId':'x','issueDate':'2026-10-26',
            'lines':[{'productServiceId':'test','quantity':1_000_000,
                      'unitPrice':10**15}]},
            {'economicCode':'demo','taxMemoryId':'demo'})
        self.assertIn('lines.0.lineTotal',[issue['field'] for issue in out['issues']])

if __name__=='__main__':unittest.main()
