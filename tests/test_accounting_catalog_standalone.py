"""Synthetic accounting item catalog + standalone invoices and supplier bills.

No actual user/Parsian database or application data is opened.
"""
from copy import deepcopy
import unittest

from accounting_core import (accounting_view, apply_accounting_command,
                             empty_accounting_state, validate_accounting_state)
from accounting_service import apply_madar_accounting, read_madar_accounting
from finance import empty_finance_state, validate_finance_state


NOW = "2026-10-21T18:00:00+03:30"
TODAY = "2026-10-21"
USERS = {"admin": {"username": "admin", "role": "admin", "projects": None}}
PROJECTS = [{"id": "p1", "name": "One"}, {"id": "p2", "name": "Two"}]


class CatalogAndStandaloneTests(unittest.TestCase):
    def setUp(self):
        self.state = empty_accounting_state()
        self.finance = empty_finance_state()
        self.serial = 0

    def core(self, command_type, **payload):
        self.serial += 1
        out = apply_accounting_command(self.state,
                                       {"type": command_type, "eventId": f"core-{self.serial}", **payload},
                                       actor="admin", accounts=USERS, now=NOW)
        self.state = out["state"]
        return out["result"]

    def service(self, cmd):
        result = apply_madar_accounting(self.finance, cmd, actor="admin", accounts=USERS,
                                        cards=[], projects=PROJECTS, now=NOW)
        self.finance = result["state"]
        return result

    def test_catalog_creates_versioned_replayable_non_stock_items(self):
        self.core("item.create", itemId="item-1", sku="PRN-1", name="Printing",
                  kind="service", unit="sheet")
        self.core("item.create", itemId="item-2", sku="BOX-1", name="Carton",
                  kind="goods", unit="number")
        projection = accounting_view(self.state, actor="admin", accounts=USERS)
        self.assertEqual(projection["items"]["item-2"]["kind"], "goods")
        self.assertFalse(projection["items"]["item-2"]["stockTracked"])
        self.assertTrue(validate_accounting_state(self.state))
        projection["items"]["item-1"]["name"] = "forged"
        self.assertEqual(accounting_view(self.state, actor="admin", accounts=USERS)[
            "items"]["item-1"]["name"], "Printing")

    def test_item_sku_must_be_unique_even_case_insensitive(self):
        self.core("item.create", itemId="i1", sku="BOX-A", name="A",
                  kind="goods", unit="unit")
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "duplicate SKU"):
            self.core("item.create", itemId="i2", sku="box-a", name="B",
                      kind="goods", unit="unit")
        self.assertEqual(self.state, before)

    def test_inactive_item_cannot_be_added_to_new_document_but_old_is_immutable(self):
        self.core("item.create", itemId="i1", sku="ITEM-1", name="Layout",
                  kind="service", unit="job")
        self.core("party.register", partyId="ali", name="Ali", kind="customer")
        line = {"itemId": "i1", "description": "Layout original", "quantity": 1,
                "unitPrice": 300}
        self.core("invoice.create", invoiceId="invoice-1", partyId="ali",
                  documentDate=TODAY, lines=[line])
        self.core("item.update", itemId="i1", name="Layout renamed", active=False)
        old = self.state
        with self.assertRaisesRegex(ValueError, "inactive"):
            self.core("invoice.create", invoiceId="invoice-2", partyId="ali",
                      documentDate=TODAY, lines=[line])
        self.assertEqual(self.state, old)
        view = accounting_view(self.state, actor="admin", accounts=USERS)
        self.assertEqual(view["invoices"]["invoice-1"]["lines"][0]["description"],
                         "Layout original")
        self.assertTrue(validate_accounting_state(self.state))

    def test_item_update_rejects_extra_fields(self):
        self.core("item.create", itemId="i1", sku="ONE", name="Layout",
                  kind="service", unit="job")
        for payload in ({"sku": "NEW"}, {"stockTracked": True}, {"active": 1}, {}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.core("item.update", itemId="i1", **payload)

    def _setup_company(self):
        self.service({"type": "party.register", "eventId": "p-ali", "partyId": "ali",
                      "name": "Ali", "kind": "customer"})
        self.service({"type": "party.register", "eventId": "p-paper", "partyId": "paper",
                      "name": "Paper Vendor", "kind": "vendor"})
        self.service({"type": "item.create", "eventId": "cat-box", "itemId": "box",
                      "sku": "BOX", "name": "Packaging", "kind": "goods", "unit": "number"})

    def _document(self, kind="sales", doc_id="sale-1", party="ali", event="doc-1",
                  project="p1", item_id="box"):
        return {"type": "document.create", "eventId": event, "projectId": project,
                "kind": kind, "documentId": doc_id, "partyId": party,
                "documentDate": TODAY,
                "lines": [{"itemId": item_id, "description": "Custom packaging",
                           "quantity": 2, "unitPrice": 250}]}

    def test_standalone_sale_issue_receipt_and_project_filter(self):
        self._setup_company()
        cmd = self._document()
        created = self.service(cmd)
        self.assertEqual(created["result"]["total"], 500)
        self.assertEqual(self.service(cmd)["changed"], False)
        self.assertEqual(len(self.finance["accounting"]["events"]), 4)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            self.service({**cmd, "projectId": "p2"})
        self.assertEqual(len(read_madar_accounting(self.finance, actor="admin",
                                                    accounts=USERS, project_id="p2")["documents"]), 0)
        self.assertEqual(len(read_madar_accounting(self.finance, actor="admin",
                                                    accounts=USERS, project_id="p1")["documents"]), 1)
        self.assertIn("box", read_madar_accounting(self.finance, actor="admin",
                                                   accounts=USERS)["items"])
        self.service({"type": "document.review", "eventId": "rev-1",
                      "projectId": "p1", "documentId": "sale-1"})
        self.service({"type": "document.issue", "eventId": "iss-1",
                      "projectId": "p1", "documentId": "sale-1", "postingDate": TODAY})
        self.service({"type": "receipt.record", "eventId": "rec-1",
                      "receiptId": "r1", "partyId": "ali", "accountId": "1010",
                      "postingDate": TODAY, "allocations": [{"invoiceId": "sale-1", "amount": 200}]})
        view = read_madar_accounting(self.finance, actor="admin", accounts=USERS)
        self.assertEqual(view["trialBalance"]["1010"]["normalBalance"], 200)
        self.assertEqual(view["trialBalance"]["1200"]["normalBalance"], 300)
        self.assertEqual(view["parties"]["ali"]["receivable"], 300)
        self.assertTrue(validate_finance_state(self.finance))

    def test_standalone_supplier_bill_requires_actual_party_and_posts_after_issue(self):
        self._setup_company()
        cmd = self._document(kind="purchase", doc_id="bill-1", party="paper", event="bill-1")
        self.service(cmd)
        view = read_madar_accounting(self.finance, actor="admin", accounts=USERS)
        self.assertEqual(view["parties"]["paper"]["payable"], 0)
        self.service({"type": "document.review", "eventId": "review-b",
                      "projectId": "p1", "documentId": "bill-1"})
        self.service({"type": "document.issue", "eventId": "issue-b",
                      "projectId": "p1", "documentId": "bill-1", "postingDate": TODAY})
        view = read_madar_accounting(self.finance, actor="admin", accounts=USERS)
        self.assertEqual(view["trialBalance"]["2000"]["normalBalance"], 500)
        self.assertEqual(view["parties"]["paper"]["payable"], 500)
        self.assertTrue(validate_finance_state(self.finance))

    def test_malformed_source_forgery_fails_closed(self):
        self._setup_company()
        original = deepcopy(self.finance)
        for broken in (self._document(party="wrong"), self._document(item_id="missing"),
                       self._document(project="missing"),
                       self._document(kind="refund"),
                       {**self._document(), "stockTracked": True}):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                self.service(broken)
            self.assertEqual(self.finance, original)


if __name__ == "__main__":
    unittest.main()
