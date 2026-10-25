"""Synthetic standalone contractor intake, batch purchase and accounting boundary."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from standalone_accounting import StandaloneAccountingStore, AccountingRevisionConflict

NOW = "2026-10-22T11:00:00Z"
USERS = {
    "root": {"username": "root", "role": "admin"},
    "staff": {"username": "staff", "role": "viewer"},
    "finance": {"username": "finance", "role": "editor", "financeEdit": True},
}


class ContractorFlow(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix="madar-contractor-fake-")
        self.addCleanup(temp.cleanup)
        self.db = StandaloneAccountingStore(Path(temp.name) / "accounting.sqlite3")
        self.n = 0
        for pid, name, kind in (("customer", "آقای فلان", "customer"),
                                ("behrouz", "بهروز", "vendor"),
                                ("laminate", "سلفون‌کشی نمونه", "vendor"),
                                ("pooya", "صحافی پویا", "vendor")):
            self.command("party.register", partyId=pid, name=name, kind=kind)

    def read(self):
        return self.db.read(actor="root", accounts=USERS)

    def command(self, typ, *, actor="root", expected=None, eventId=None, **data):
        self.n += 1
        if expected is None:
            expected = self.read()["revision"]
        return self.db.command({"type": typ, "eventId": eventId or f"evt.{self.n}", **data},
                               actor=actor, accounts=USERS, expected_revision=expected, now=NOW)

    def intake(self, jid, vendor, quantity, price=None):
        return self.command("contractor.job.intake", jobId=jid, sourceType="task.expense",
                            sourceId=f"source.{jid}", partyId=vendor,
                            description="صحافی چسب گرم کتاب بهمان" if vendor == "pooya" else jid,
                            quantity=quantity, currency="TOMAN", unitPrice=price)

    def test_book_workflow_no_gl_before_issue_and_multi_party_step(self):
        self.command("invoice.create", invoiceId="book.sale", partyId="customer",
                     documentDate="2026-10-22", sourceType="task.sale",
                     sourceId="book100", lines=[{"description": "کتاب بهمان",
                                              "quantity": 100, "unitPrice": 20000}])
        self.intake("courier", "behrouz", 1, 150000)
        self.intake("laminate.job", "laminate", 100)
        self.intake("binding.job", "pooya", 100)
        v = self.read()["view"]
        self.assertEqual(len(v["contractorJobs"]), 3)
        self.assertIsNone(v["contractorJobs"]["binding.job"]["unitPrice"])
        self.assertEqual(v["journals"], [])
        self.assertEqual(v["parties"]["pooya"]["payable"], 0)
        self.assertEqual(v["invoices"]["book.sale"]["total"], 2000000)
        self.assertNotIn("۴۰۰ صفحه", str(v))
        with self.assertRaisesRegex(ValueError, "price"):
            self.command("contractor.job.approve", jobId="binding.job", confirmedQuantity=100)
        self.command("contractor.job.price", jobId="binding.job",
                     unitPrice=2500, currency="TOMAN")
        with self.assertRaisesRegex(ValueError, "quantity"):
            self.command("contractor.job.approve", jobId="binding.job", confirmedQuantity=99)
        self.command("contractor.job.approve", jobId="binding.job", confirmedQuantity=100)
        self.intake("binding.second", "pooya", 50, 3000)
        self.command("contractor.job.approve", jobId="binding.second", confirmedQuantity=50)
        self.command("contractor.bill.create", billId="pooya.month", partyId="pooya",
                     documentDate="2026-10-22", jobIds=["binding.job", "binding.second"])
        self.assertEqual(self.read()["view"]["bills"]["pooya.month"]["total"], 400000)
        self.assertEqual(self.read()["view"]["journals"], [])
        with self.assertRaisesRegex(ValueError, "already billed"):
            self.command("contractor.bill.create", billId="duplicate", partyId="pooya",
                         documentDate="2026-10-22", jobIds=["binding.job"])
        self.command("bill.approve", billId="pooya.month")
        self.command("bill.issue", billId="pooya.month", postingDate="2026-10-22")
        v = self.read()["view"]
        self.assertEqual(v["parties"]["pooya"]["payable"], 400000)
        self.assertEqual(len(v["journals"]), 1)

    def test_same_commercial_source_cannot_duplicate_or_change_content(self):
        self.intake("courier", "behrouz", 1, 150000)
        self.intake("courier", "behrouz", 1, 150000)
        self.assertEqual(len(self.read()["view"]["contractorJobs"]), 1)
        with self.assertRaisesRegex(ValueError, "commercial source"):
            self.intake("courier", "behrouz", 2, 150000)
        with self.assertRaises(ValueError):
            self.command("contractor.job.intake", jobId="another",
                         sourceType="task.expense", sourceId="source.courier",
                         partyId="behrouz", description="another",
                         quantity=1, currency="TOMAN")

    def test_cancel_draft_releases_jobs_and_draft_updates_leave_audit_trail(self):
        self.intake("job", "pooya", 100, 2000)
        self.command("contractor.job.approve", jobId="job", confirmedQuantity=100)
        self.command("contractor.bill.create", billId="monthly", partyId="pooya",
                     documentDate="2026-10-22", jobIds=["job"])
        with self.assertRaisesRegex(ValueError, "ordinary draft"):
            self.command("bill.update", billId="monthly", partyId="pooya",
                         documentDate="2026-10-22",
                         lines=[{"description": "wrong", "quantity": 1, "unitPrice": 1}])
        self.command("bill.cancel", billId="monthly", reason="correct batch")
        self.assertEqual(self.read()["view"]["contractorJobs"]["job"]["status"], "approved")
        self.command("contractor.bill.create", billId="replacement", partyId="pooya",
                     documentDate="2026-10-22", jobIds=["job"])
        self.command("invoice.create", invoiceId="sale", partyId="customer",
                     documentDate="2026-10-22", lines=[
                         {"description": "کتاب", "quantity": 100, "unitPrice": 100}])
        self.command("invoice.update", invoiceId="sale", partyId="customer",
                     documentDate="2026-10-22", lines=[
                         {"description": "کتاب", "quantity": 100, "unitPrice": 200}])
        self.assertEqual(self.read()["view"]["invoices"]["sale"]["total"], 20000)

    def test_acl_exact_currency_and_cas(self):
        with self.assertRaises(PermissionError):
            self.command("contractor.job.intake", actor="staff", jobId="denied",
                         sourceType="task.expense", sourceId="x", partyId="pooya",
                         description="Denied", quantity=1, currency="TOMAN")
        with self.assertRaises(PermissionError):
            self.db.read(actor="staff", accounts=USERS)
        with self.assertRaises(ValueError):
            self.command("contractor.job.intake", jobId="rial", sourceType="task.expense",
                         sourceId="rial", partyId="pooya", description="Rial",
                         quantity=1, currency="RIAL", unitPrice=120)
        base = self.read()["revision"]
        def race(index):
            try:
                self.command("contractor.job.intake", expected=base, eventId=f"r.{index}",
                             jobId=f"r.{index}", sourceType="task.expense",
                             sourceId=f"r.{index}", partyId="pooya",
                             description="Job", quantity=1, currency="TOMAN")
                return "ok"
            except AccountingRevisionConflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as executor:
            result = list(executor.map(race, range(2)))
        self.assertCountEqual(result, ["ok", "conflict"])
        self.assertEqual(len(self.read()["view"]["contractorJobs"]), 1)


if __name__ == "__main__":
    unittest.main()
