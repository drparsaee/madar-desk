"""Synthetic acceptance of safe edit-after-approval without rewriting posted invoices."""
from pathlib import Path
import tempfile
import unittest

from standalone_accounting import StandaloneAccountingStore

NOW = "2026-10-24T11:00:00Z"
ACTORS = {"root": {"username": "root", "role": "admin"},
          "auditor": {"username": "auditor", "role": "viewer", "financeView": True}}


class ApprovedInvoiceCorrectionTests(unittest.TestCase):
    def setUp(self):
        disposable = tempfile.TemporaryDirectory(prefix="madar-invoice-correction-qa-")
        self.addCleanup(disposable.cleanup)
        self.store = StandaloneAccountingStore(
            Path(disposable.name) / "standalone-only.sqlite3")

    def execute(self, typ, **data):
        read = self.store.read(actor="root", accounts=ACTORS)
        return self.store.command({"type": typ, "eventId": f"qa-{read['revision']+1}",
                                   **data}, actor="root", accounts=ACTORS,
                                  now=NOW, expected_revision=read["revision"])

    def view(self):
        return self.store.read(actor="root", accounts=ACTORS)["view"]

    def create(self, *, kind="invoice"):
        person = "buyer" if kind == "invoice" else "supplier"
        self.execute("party.register", partyId=person, name="Disposable user",
                     kind="customer" if kind == "invoice" else "vendor")
        self.execute(kind + ".create", **{kind+"Id": "DOC-1"},
                     partyId=person, documentDate="2026-10-22",
                     lines=[{"description": "One line", "quantity": 2,
                             "unitPrice": 500}])
        self.execute(kind + ".approve", **{kind+"Id": "DOC-1"})

    def test_approved_sales_reopens_edit_and_issues_new_values_without_duplicate_posting(self):
        self.create()
        self.assertEqual(len(self.view()["journals"]), 0)
        result = self.execute("invoice.reopen", invoiceId="DOC-1",
                              reason="Correct customer amount before issuance")
        self.assertEqual(result["view"]["invoices"]["DOC-1"]["status"], "draft")
        self.assertEqual(self.view()["invoices"]["DOC-1"]["reopenCount"], 1)
        self.execute("invoice.update", invoiceId="DOC-1", partyId="buyer",
                     documentDate="2026-10-22",
                     lines=[{"description": "Corrected line", "quantity": 3,
                             "unitPrice": 700}])
        self.assertEqual(self.view()["invoices"]["DOC-1"]["total"], 2100)
        self.assertEqual(len(self.view()["journals"]), 0)
        self.execute("invoice.approve", invoiceId="DOC-1")
        self.execute("invoice.issue", invoiceId="DOC-1",
                     postingDate="2026-10-24")
        self.assertEqual(self.view()["invoices"]["DOC-1"]["total"], 2100)
        self.assertEqual(len(self.view()["journals"]), 1)
        lines = self.view()["journals"][0]["lines"]
        self.assertEqual(sum(line["debit"] for line in lines),
                         sum(line["credit"] for line in lines))
        previous_revision = self.store.read(actor="root", accounts=ACTORS)["revision"]
        with self.assertRaisesRegex(ValueError, "approved, unposted"):
            self.execute("invoice.reopen", invoiceId="DOC-1", reason="Backdate fraud")
        self.assertEqual(self.store.read(actor="root", accounts=ACTORS)["revision"],
                         previous_revision)
        self.assertEqual(len(self.view()["journals"]), 1)

    def test_purchase_reopen_requires_reason_and_admin_and_remains_auditable(self):
        self.create(kind="bill")
        for reason in ("", "   "):
            with self.assertRaises(ValueError):
                self.execute("bill.reopen", billId="DOC-1", reason=reason)
        result = self.execute("bill.reopen", billId="DOC-1",
                              reason="Price was quoted incorrectly")
        doc = result["view"]["bills"]["DOC-1"]
        self.assertEqual(doc["status"], "draft")
        self.assertEqual(doc["lastReopenReason"], "Price was quoted incorrectly")
        self.assertEqual(len(result["view"]["journals"]), 0)
        with self.assertRaises(PermissionError):
            self.store.command({"type": "bill.reopen", "eventId": "auditor-event",
                                "billId": "DOC-1", "reason": "No permission"},
                               actor="auditor", accounts=ACTORS, now=NOW,
                               expected_revision=result["revision"])

    def test_converted_proforma_draft_remains_editable_without_breaking_link(self):
        self.execute("party.register", partyId="buyer", name="Synthetic buyer", kind="customer")
        self.execute("proforma.create", proformaId="PF-1", partyId="buyer",
                     documentDate="2026-10-22",
                     lines=[{"description": "Quoted print", "quantity": 2, "unitPrice": 100}])
        self.execute("proforma.send", proformaId="PF-1")
        self.execute("proforma.accept", proformaId="PF-1")
        self.execute("proforma.convert", proformaId="PF-1", invoiceId="INV-PF-1",
                     documentDate="2026-10-24")
        old = self.view()
        self.assertEqual(old["proformas"]["PF-1"]["total"], 200)
        self.execute("invoice.update", invoiceId="INV-PF-1", partyId="buyer",
                     documentDate="2026-10-24",
                     lines=[{"description": "Agreed revised print", "quantity": 2,
                             "unitPrice": 125}])
        updated = self.view()
        self.assertEqual(updated["invoices"]["INV-PF-1"]["total"], 250)
        self.assertEqual(updated["invoices"]["INV-PF-1"]["sourceType"], "proforma")
        self.assertEqual(updated["invoices"]["INV-PF-1"]["sourceId"], "PF-1")
        self.assertEqual(updated["proformas"]["PF-1"]["total"], 200)
        self.assertEqual(len(updated["journals"]), 0)
        self.execute("invoice.approve", invoiceId="INV-PF-1")
        self.execute("invoice.reopen", invoiceId="INV-PF-1",
                     reason="Customer accepted revised quantity")
        self.assertEqual(self.view()["invoices"]["INV-PF-1"]["status"], "draft")


if __name__ == "__main__":
    unittest.main()
