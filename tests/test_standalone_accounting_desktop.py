"""The independent accounting launcher must never bootstrap the task manager."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from standalone_accounting_desktop import (
    ACCOUNTING_FILE, AccountingDesktopAPI, serve_accounting_page,
)


class AccountingDesktopTests(unittest.TestCase):
    def test_requires_explicit_absolute_data_root_and_does_not_initialize(self):
        with self.assertRaises(ValueError):
            AccountingDesktopAPI("relative-folder")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "new-accounting-data"
            api = AccountingDesktopAPI(root)
            self.assertEqual(api.path.name, ACCOUNTING_FILE)
            self.assertFalse(root.exists())

    def test_strict_cas_request_has_no_client_authority_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            api = AccountingDesktopAPI(Path(temp))
            bad = [None, {}, {"command": {}, "expectedRevision": True},
                   {"command": {}, "expectedRevision": -1},
                   {"command": {}, "expectedRevision": 0, "actor": "admin"},
                   {"command": [], "expectedRevision": 0}]
            for value in bad:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    api.standaloneAccountingCommand(value)

    def test_real_independent_desktop_api_issues_invoice_without_task_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "accounting-only"
            api = AccountingDesktopAPI(root)
            first = api.standaloneAccountingRead()
            self.assertEqual(first["revision"], 0)
            self.assertEqual(first["capabilities"], {
                "canView": True, "canManage": True, "canDraft": True,
                "canAdmin": True})
            self.assertEqual(first["view"]["currency"], "RIAL")
            actions = [
                {"type": "party.register", "eventId": "person-1",
                 "partyId": "customer-a", "name": "Test customer", "kind": "customer"},
                {"type": "invoice.create", "eventId": "draft-1",
                 "invoiceId": "invoice-a", "partyId": "customer-a",
                 "documentDate": "2026-01-01", "lines": [
                     {"description": "Design service", "quantity": 2,
                      "unitPrice": 1200}]},
                {"type": "invoice.approve", "eventId": "approve-1",
                 "invoiceId": "invoice-a"},
                {"type": "invoice.issue", "eventId": "issue-1",
                 "invoiceId": "invoice-a", "postingDate": "2026-01-02"},
            ]
            response = first
            for action in actions:
                response = api.standaloneAccountingCommand(
                    {"command": action, "expectedRevision": response["revision"]})
            self.assertEqual(response["revision"], 4)
            self.assertEqual(response["view"]["invoices"]["invoice-a"]["total"], 2400)
            self.assertEqual(response["view"]["parties"]["customer-a"]["receivable"], 2400)
            self.assertEqual(len(response["view"]["journals"]), 1)
            self.assertEqual(api.standaloneAccountingRead()["revision"], 4)
            self.assertTrue((root / ACCOUNTING_FILE).is_file())
            self.assertFalse((root / "tasks.json").exists())
            self.assertFalse((root / "finance.json").exists())
            self.assertFalse((root / "madar-unified.sqlite3").exists())

    def test_accounting_only_page_injection_and_no_task_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp)
            (site / "accounting.html").write_text(
                "<html><head></head><body>standalone accounting</body></html>",
                encoding="utf-8")
            (site / "index.html").write_text("SECRET TASK MANAGER", encoding="utf-8")
            server = serve_accounting_page(site)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(base + "/accounting.html", timeout=5) as res:
                    page = res.read().decode("utf8")
                    self.assertEqual(res.headers.get("Cache-Control"), "no-store")
                self.assertIn("standaloneAccountingCommand", page)
                self.assertIn("standalone accounting", page)
                self.assertNotIn("SECRET TASK MANAGER", page)
                with self.assertRaises(HTTPError) as exc:
                    urlopen(base + "/index.html", timeout=5)
                self.assertEqual(exc.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
