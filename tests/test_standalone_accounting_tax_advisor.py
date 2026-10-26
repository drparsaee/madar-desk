import unittest
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

if __name__=='__main__':unittest.main()
