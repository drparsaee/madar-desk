"""Isolated invoice/proforma lifecycle with no task/project dependency."""
import tempfile
import unittest
from pathlib import Path

from standalone_accounting import StandaloneAccountingStore

USERS = {"owner": {"username": "owner", "role": "admin"},
         "sales": {"username": "sales", "role": "editor", "financeEdit": True},
         "sales_readonly": {"username": "sales_readonly", "role": "editor",
                            "financeView": True, "financeEdit": False},
         "guest": {"username": "guest", "role": "viewer"}}
NOW = "2026-10-24T13:00:00+03:30"


class ProformaStandaloneFlow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "standalone-accounting.sqlite3"
        self.store = StandaloneAccountingStore(self.path, default_currency="RIAL")
        self.revision = 0
        self.command({"type":"party.register","eventId":"p1","partyId":"buyer",
                      "name":"Test Buyer","kind":"customer"})

    def command(self, cmd, actor="owner"):
        result = self.store.command(cmd, actor=actor, accounts=USERS,
                                    expected_revision=self.revision, now=NOW)
        self.revision = result["revision"]
        return result

    def view(self):
        return self.store.read(actor="owner",accounts=USERS)["view"]

    def quote(self):
        return {"type":"proforma.create","eventId":"q1","proformaId":"quote1",
                "partyId":"buyer","documentDate":"2026-10-24",
                "validUntil":"2026-11-24","lines":[
                   {"description":"Print order","quantity":3,"unitPrice":1},
                   {"description":"Design","quantity":1,"unitPrice":15000}],
                "discount":1,"tax":0}

    def prepare_invoice(self):
        self.command(self.quote(),actor="sales")
        self.command({"type":"proforma.send","eventId":"s1","proformaId":"quote1"})
        self.command({"type":"proforma.accept","eventId":"a1","proformaId":"quote1"})
        return {"type":"proforma.convert","eventId":"convert1",
                "proformaId":"quote1","invoiceId":"inv1","documentDate":"2026-10-24"}

    def test_full_workflow_no_task_and_no_early_post(self):
        convert = self.prepare_invoice()
        self.assertEqual(self.view()["journals"],[])
        self.assertEqual(self.view()["invoices"],{})
        result = self.command(convert)
        self.assertEqual(result["result"]["total"],15002)
        self.assertEqual(self.view()["proformas"]["quote1"]["status"],"converted")
        self.assertEqual(self.view()["invoices"]["inv1"]["sourceType"],"proforma")
        self.assertEqual(self.view()["invoices"]["inv1"]["status"],"draft")
        self.assertEqual(self.view()["parties"]["buyer"]["receivable"],0)
        self.command({"type":"invoice.approve","eventId":"approve1","invoiceId":"inv1"})
        self.assertEqual(self.view()["journals"],[])
        self.command({"type":"invoice.issue","eventId":"issue1","invoiceId":"inv1",
                      "postingDate":"2026-10-24"})
        self.assertEqual(self.view()["parties"]["buyer"]["receivable"],15002)
        self.command({"type":"receipt.record","eventId":"receive1","receiptId":"r1",
                      "partyId":"buyer","accountId":"1010","postingDate":"2026-10-24",
                      "allocations":[{"invoiceId":"inv1","amount":2}]})
        view = self.view()
        self.assertEqual(view["parties"]["buyer"]["receivable"],15000)
        self.assertEqual(len(view["journals"]),2)
        self.assertNotIn("taskId",str(view))
        self.assertEqual(StandaloneAccountingStore(self.path).read(
            actor="owner",accounts=USERS)["revision"],self.revision)

    def test_duplicate_conversion_and_link_forgery_are_rejected(self):
        convert = self.prepare_invoice()
        first = self.command(convert)
        replay = self.command(convert)
        self.assertEqual(replay["revision"],first["revision"])
        self.assertEqual(len(self.view()["invoices"]),1)
        with self.assertRaises(ValueError):
            self.command({**convert,"eventId":"convert-again"})
        with self.assertRaises(ValueError):
            self.command({**convert,"invoiceId":"inv2"})
        with self.assertRaises(ValueError):
            self.command({"type":"invoice.create","eventId":"forge","invoiceId":"inv2",
                          "partyId":"buyer","documentDate":"2026-10-24",
                          "lines":[{"description":"Forge","quantity":1,"unitPrice":1}],
                          "sourceType":"proforma","sourceId":"quote1"})
        # Accepted change from UX30: an unissued converted invoice is editable
        # while its verified proforma provenance cannot be forged or erased.
        self.command({"type":"invoice.update","eventId":"edit","invoiceId":"inv1",
                      "partyId":"buyer","documentDate":"2026-10-24",
                      "lines":[{"description":"Changed","quantity":1,"unitPrice":1}]})
        edited = self.view()["invoices"]["inv1"]
        self.assertEqual(edited["sourceType"], "proforma")
        self.assertEqual(edited["sourceId"], "quote1")
        self.assertEqual(edited["total"], 1)
        self.assertEqual(len(self.view()["journals"]), 0)

    def test_draft_revision_send_reject_never_creates_debt(self):
        self.command(self.quote())
        self.command({**self.quote(),"type":"proforma.update","eventId":"update",
                      "lines":[{"description":"Updated","quantity":4,"unitPrice":5}]},
                     actor="sales")
        self.assertEqual(self.view()["proformas"]["quote1"]["total"],19)
        self.command({"type":"proforma.send","eventId":"send","proformaId":"quote1"})
        with self.assertRaises(ValueError):
            self.command({**self.quote(),"type":"proforma.update","eventId":"late"})
        self.command({"type":"proforma.reject","eventId":"reject",
                      "proformaId":"quote1","reason":"Not accepted"})
        with self.assertRaises(ValueError):
            self.command({"type":"proforma.convert","eventId":"reject-convert",
                          "proformaId":"quote1","invoiceId":"inv1",
                          "documentDate":"2026-10-24"})
        self.assertEqual(self.view()["journals"],[])
        self.assertEqual(self.view()["invoices"],{})

    def test_invalid_proforma_and_acl(self):
        with self.assertRaises(ValueError):
            self.command({**self.quote(),"validUntil":"2026-10-23"})
        self.command(self.quote())
        with self.assertRaises(ValueError):
            self.command({"type":"proforma.accept","eventId":"unsent","proformaId":"quote1"})
        # financeEdit now explicitly permits editors to send, accept and
        # convert proformas. The former expectation that sales was denied was
        # stale after the standalone LAN/core ACL alignment.
        self.command({"type":"proforma.send","eventId":"sales-send",
                      "proformaId":"quote1"}, actor="sales")
        self.assertEqual(self.view()["proformas"]["quote1"]["status"], "sent")
        revision = self.revision
        for actor in ("sales_readonly", "guest"):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.command({"type":"proforma.accept",
                              "eventId":"denied-"+actor,
                              "proformaId":"quote1"}, actor=actor)
            self.assertEqual(self.revision, revision)
            self.assertEqual(self.view()["proformas"]["quote1"]["status"], "sent")
        self.command({"type":"proforma.accept", "eventId":"sales-accept",
                      "proformaId":"quote1"}, actor="sales")
        self.command({"type":"proforma.convert", "eventId":"sales-convert",
                      "proformaId":"quote1", "invoiceId":"invoice-from-quote",
                      "documentDate":"2026-10-24"}, actor="sales")
        self.assertEqual(self.view()["invoices"]["invoice-from-quote"]["status"],
                         "draft")
        with self.assertRaises(PermissionError):
            self.command({"type":"period.close", "eventId":"no-close",
                          "throughDate":"2026-10-24"}, actor="sales")

if __name__=="__main__":
    unittest.main()
