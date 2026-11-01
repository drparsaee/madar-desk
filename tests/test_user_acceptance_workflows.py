"""Beta user acceptance against real Bridge + disposable SQLite.

No desktop/UI, network listener, production credentials, real APPDATA, or
release mutations. All invoices, costs, receipts and parties are synthetic.
"""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app
from tests.legacy_sample_fixture import seed_legacy_example_state
from app_storage import UnifiedAppStorage
from lan import LanService


PROJECT = "p-sample"
CARD = "example-2"
CUSTOMER = {"id": "customer-demo", "name": "Demo Person",
            "kind": "customer", "reference": ""}
SUPPLIER = {"id": "supplier-demo", "name": "Demo Print Vendor",
            "kind": "supplier", "reference": ""}


class UserAcceptanceWorkflows(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-user-acceptance-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.datadir_patch = patch.object(native_app, "datadir",
                                         return_value=self.root)
        self.datadir_patch.start()
        self.addCleanup(self.datadir_patch.stop)
        self.bridge = seed_legacy_example_state(native_app.Bridge())
        self.assertEqual(self.bridge.enableUnifiedStorage()["mode"], "sqlite")
        self.store = UnifiedAppStorage(self.bridge.unified_path)
        self.today = datetime.now(timezone.utc).date().isoformat()

    def snapshot(self):
        saved = self.store.load()
        self.assertIsNotNone(saved)
        return saved

    def assert_unchanged(self, before):
        after = self.snapshot()
        self.assertEqual(after.revision, before.revision)
        self.assertEqual(after.sha256, before.sha256)
        self.assertEqual(after.bundle, before.bundle)
        self.assertTrue(self.store.integrity_check())

    def run_accounting(self, typ, event_id, **fields):
        return self.bridge.accountingCommand(
            {"type": typ, "eventId": event_id, **fields})

    def get_document(self, doc_id):
        docs = self.bridge.accountingRead(PROJECT)["documents"]
        found = [doc for doc in docs if doc["id"] == doc_id]
        self.assertEqual(len(found), 1)
        return found[0]

    def sale_draft(self, suffix="a"):
        return self.run_accounting(
            "draft.sales.fromTask", "sale-" + suffix,
            projectId=PROJECT, cardId=CARD, party=CUSTOMER,
            lines=[{"id": "service-line", "description": "Print job",
                    "quantity": 2, "unitPrice": 1500}],
            discount=200, tax=50, advance=300)["documentId"]

    def review_issue(self, doc_id, suffix):
        self.run_accounting("document.review", "review-" + suffix,
                            projectId=PROJECT, documentId=doc_id)
        return self.run_accounting("document.issue", "issue-" + suffix,
                                   projectId=PROJECT, documentId=doc_id,
                                   postingDate=self.today)

    def record_cost(self):
        return self.bridge.financeCommand({
            "type": "cost.set", "eventId": "cost-demo-v1", "cardId": CARD,
            "value": {"cardId": CARD, "costEnabled": True,
                      "estimatedDirect": 500, "actualDirect": 450,
                      "items": []}})

    def purchase_draft(self, suffix="a"):
        return self.run_accounting(
            "draft.purchase.fromCosts", "bill-" + suffix,
            projectId=PROJECT, party=SUPPLIER,
            selections=[{"cardId": CARD, "sourceId": "direct"}],
            basis="actual", approveEstimate=False)["documentId"]

    def test_task_to_named_sales_invoice_review_issue_and_partial_receipt(self):
        before = self.snapshot()
        invoice_id = self.sale_draft()
        draft = self.get_document(invoice_id)
        self.assertEqual(draft["status"], "Draft")
        self.assertEqual(draft["party"]["name"], CUSTOMER["name"])
        self.assertEqual(draft["total"], 2850)
        self.assertEqual(draft["sourceCardIds"], [CARD])
        self.assertEqual(self.bridge.accountingRead(PROJECT)["trialBalance"]
                         ["1200"]["normalBalance"], 0)

        self.review_issue(invoice_id, "sale")
        posted = self.get_document(invoice_id)
        self.assertEqual(posted["status"], "Issued")
        self.assertEqual(self.bridge.accountingRead(PROJECT)["trialBalance"]
                         ["1200"]["normalBalance"], 2850)
        # Declared advance is not actual cash until a receipt is recorded.
        self.assertEqual(self.bridge.accountingRead(PROJECT)["trialBalance"]
                         ["1010"]["normalBalance"], 0)

        result = self.run_accounting(
            "receipt.record", "receipt-a", receiptId="receipt-demo",
            partyId=CUSTOMER["id"], accountId="1010",
            postingDate=self.today,
            allocations=[{"invoiceId": invoice_id, "amount": 1000}])
        self.assertEqual(result["amount"], 1000)
        updated = self.bridge.accountingRead(PROJECT)
        self.assertEqual(next(row["receivable"] for row in updated["balances"]
                              if row["partyId"] == CUSTOMER["id"]), 1850)
        self.assertEqual(updated["trialBalance"]["1010"]["normalBalance"], 1000)
        self.assertEqual(updated["trialBalance"]["1200"]["normalBalance"], 1850)
        self.assertGreater(self.snapshot().revision, before.revision)
        self.assertTrue(self.store.integrity_check())

    def test_cost_to_supplier_purchase_bill_issue_funds_and_partial_payment(self):
        self.record_cost()
        before = self.snapshot()
        bill_id = self.purchase_draft()
        draft = self.get_document(bill_id)
        self.assertEqual(draft["kind"], "purchase")
        self.assertEqual(draft["party"]["name"], SUPPLIER["name"])
        self.assertEqual(draft["total"], 450)
        self.assertEqual(draft["status"], "Draft")
        self.review_issue(bill_id, "bill")
        posted = self.bridge.accountingRead(PROJECT)
        self.assertEqual(next(row["payable"] for row in posted["balances"]
                              if row["partyId"] == SUPPLIER["id"]), 450)
        self.assertEqual(posted["trialBalance"]["2000"]["normalBalance"], 450)

        previous = self.snapshot()
        with self.assertRaises(ValueError):
            self.run_accounting(
                "payment.record", "no-funds", paymentId="no-funds",
                partyId=SUPPLIER["id"], accountId="1010",
                postingDate=self.today,
                allocations=[{"billId": bill_id, "amount": 200}])
        self.assert_unchanged(previous)

        self.run_accounting(
            "funds.deposit", "fund-demo", accountId="1010",
            amount=1000, postingDate=self.today, note="Synthetic opening funds")
        self.run_accounting(
            "payment.record", "paid-demo", paymentId="payment-demo",
            partyId=SUPPLIER["id"], accountId="1010",
            postingDate=self.today,
            allocations=[{"billId": bill_id, "amount": 200}])
        view = self.bridge.accountingRead(PROJECT)
        self.assertEqual(next(row["payable"] for row in view["balances"]
                              if row["partyId"] == SUPPLIER["id"]), 250)
        self.assertEqual(view["trialBalance"]["1010"]["normalBalance"], 800)
        self.assertEqual(view["trialBalance"]["2000"]["normalBalance"], 250)
        self.assertGreater(self.snapshot().revision, before.revision)

    def test_restart_reopens_same_double_entry_receipt_and_purchase_source(self):
        self.record_cost()
        sale_id = self.sale_draft()
        bill_id = self.purchase_draft()
        self.review_issue(sale_id, "reopen-sale")
        self.review_issue(bill_id, "reopen-bill")
        self.run_accounting(
            "receipt.record", "reopen-receipt", receiptId="reopen-receipt",
            partyId=CUSTOMER["id"], accountId="1010", postingDate=self.today,
            allocations=[{"invoiceId": sale_id, "amount": 1000}])
        baseline = self.snapshot()
        reopened = native_app.Bridge()
        self.assertEqual(reopened.storageStatus()["mode"], "sqlite")
        self.assertEqual(UnifiedAppStorage(self.bridge.unified_path).load().sha256,
                         baseline.sha256)
        data = reopened.accountingRead(PROJECT)
        documents = {doc["id"]: doc for doc in data["documents"]}
        self.assertEqual(set(documents), {sale_id, bill_id})
        self.assertEqual(documents[sale_id]["status"], "Issued")
        self.assertEqual(documents[bill_id]["status"], "Issued")
        self.assertEqual(documents[bill_id]["total"], 450)
        self.assertEqual(data["trialBalance"]["1200"]["normalBalance"], 1850)
        self.assertEqual(data["trialBalance"]["2000"]["normalBalance"], 450)
        self.assertEqual(data["trialBalance"]["1010"]["normalBalance"], 1000)
        self.assertEqual(reopened._load_finance()["accountingSources"],
                         baseline.bundle["finance"]["accountingSources"])

    def test_sqlite_backup_restore_recovers_finance_and_tasks_after_later_edits(self):
        self.record_cost()
        sale_id = self.sale_draft()
        bill_id = self.purchase_draft()
        self.review_issue(sale_id, "backup-sale")
        self.review_issue(bill_id, "backup-bill")
        original = self.snapshot()
        backup = self.bridge.createLocalBackup()
        self.assertFalse(backup["complete"])
        self.assertEqual(backup["scope"], "sqlite-domains-only")
        self.assertIn("lan-accounts", backup["omitted"])
        self.assertIn("attachment-binaries", backup["omitted"])
        self.assertTrue(Path(backup["path"]).is_file())

        self.run_accounting(
            "receipt.record", "after-backup-receipt",
            receiptId="receipt-after-backup", partyId=CUSTOMER["id"],
            accountId="1010", postingDate=self.today,
            allocations=[{"invoiceId": sale_id, "amount": 100}])
        changed = self.bridge.getState()
        next(card for card in changed["tasks"] if card["id"] == CARD)[
            "title"] = "Changed after backup"
        self.bridge.saveState(changed)
        self.assertNotEqual(self.snapshot().bundle["tasks"], original.bundle["tasks"])

        self.bridge.restoreLocalBackup(backup["name"])
        restored = self.snapshot()
        self.assertGreater(restored.revision, original.revision)
        self.assertEqual(restored.bundle["finance"], original.bundle["finance"])
        self.assertEqual(restored.bundle["tasks"], original.bundle["tasks"])
        self.assertEqual(restored.bundle["collab"], original.bundle["collab"])
        self.assertEqual(restored.bundle["completion_outbox"],
                         original.bundle["completion_outbox"])
        fresh = native_app.Bridge()
        self.assertEqual(fresh.accountingRead(PROJECT)["trialBalance"]
                         ["1200"]["normalBalance"], 2850)
        self.assertEqual(fresh.accountingRead(PROJECT)["trialBalance"]
                         ["2000"]["normalBalance"], 450)
        self.assertTrue(list((self.root / "backups").glob("before-restore-*.sqlite3")))
        self.assertTrue(self.store.integrity_check())

    def test_active_automation_backup_restore_keeps_finance_and_fifth_domain(self):
        self.assertEqual(self.bridge.enableAutomationEngine()["mode"], "active")
        invoice_id = self.sale_draft("five-domain")
        self.review_issue(invoice_id, "five-domain")
        expected = self.snapshot()
        self.assertIn("automation", expected.bundle)
        backup = self.bridge.createLocalBackup()
        self.run_accounting(
            "receipt.record", "five-receipt", receiptId="five-receipt",
            partyId=CUSTOMER["id"], accountId="1010", postingDate=self.today,
            allocations=[{"invoiceId": invoice_id, "amount": 250}])
        self.assertEqual(self.bridge.accountingRead(PROJECT)["trialBalance"]
                         ["1200"]["normalBalance"], 2600)
        self.bridge.restoreLocalBackup(backup["name"])
        restored = self.snapshot()
        self.assertEqual(restored.bundle["finance"], expected.bundle["finance"])
        self.assertEqual(restored.bundle["automation"], expected.bundle["automation"])
        self.assertEqual(restored.bundle["collab"], expected.bundle["collab"])
        self.assertEqual(self.bridge.accountingRead(PROJECT)["trialBalance"]
                         ["1200"]["normalBalance"], 2850)
        self.assertTrue(self.store.integrity_check())

    def test_duplicate_sales_and_purchase_cost_source_refused_without_partial_write(self):
        self.record_cost()
        invoice_id = self.sale_draft()
        bill_id = self.purchase_draft()
        baseline = self.snapshot()
        with self.assertRaises(ValueError):
            self.purchase_draft("different-event-same-cost")
        self.assert_unchanged(baseline)
        with self.assertRaises(ValueError):
            self.run_accounting(
                "draft.sales.fromTask", "sale-a", projectId=PROJECT,
                cardId=CARD, party=CUSTOMER,
                lines=[{"id": "service-line", "description": "Tampered",
                        "quantity": 2, "unitPrice": 1500}],
                discount=200, tax=50, advance=300)
        self.assert_unchanged(baseline)
        self.assertEqual(self.get_document(invoice_id)["status"], "Draft")
        self.assertEqual(self.get_document(bill_id)["status"], "Draft")

    def test_cancelled_sales_draft_can_be_corrected_without_erasing_audit(self):
        first_id = self.sale_draft("original")
        self.assertEqual(self.get_document(first_id)["status"], "Draft")
        cancelled = self.run_accounting(
            "document.cancel", "cancel-original", projectId=PROJECT,
            documentId=first_id, reason="Customer requested corrected quantities")
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.get_document(first_id)["status"], "Cancelled")
        second_id = self.sale_draft("corrected")
        self.assertNotEqual(second_id, first_id)
        self.assertEqual(self.get_document(second_id)["status"], "Draft")
        self.review_issue(second_id, "corrected-sale")
        view = self.bridge.accountingRead(PROJECT)
        self.assertEqual(len(view["documents"]), 2)
        self.assertEqual({doc["status"] for doc in view["documents"]},
                         {"Cancelled", "Issued"})
        self.assertEqual(view["trialBalance"]["1200"]["normalBalance"], 2850)
        self.assertTrue(self.store.integrity_check())

    def test_issued_sales_invoice_cannot_be_duplicated_from_same_task(self):
        original_id = self.sale_draft("issued-once")
        self.review_issue(original_id, "issued-once")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.sale_draft("issued-twice")
        self.assert_unchanged(before)
        self.assertEqual(self.get_document(original_id)["status"], "Issued")
        self.assertEqual(len(self.bridge.accountingRead(PROJECT)["documents"]), 1)

    def test_LAN_role_scope_and_session_authorization_without_network_listener(self):
        service = LanService(self.bridge, self.root / "synthetic-users.json",
                             bind="127.0.0.1", port=0)
        service.setup_owner("admin", "test-admin-password")
        admin = service.authenticate("admin", "test-admin-password")["token"]
        for username, role, projects in (
            ("reader", "viewer", [PROJECT]),
            ("editor", "editor", [PROJECT]),
            ("other", "editor", ["p-personal"]),
        ):
            service.upsert_user(admin, {
                "username": username, "password": "test-user-password",
                "role": role, "projects": projects})
        tokens = {username: service.authenticate(
            username, "test-user-password")["token"]
            for username in ("reader", "editor", "other")}
        baseline = self.snapshot()
        sales = {"type": "draft.sales.fromTask", "eventId": "lan-sale",
                 "projectId": PROJECT, "cardId": CARD,
                 "party": CUSTOMER,
                 "lines": [{"id": "service", "description": "Services",
                            "quantity": 1, "unitPrice": 120}],
                 "discount": 0, "tax": 0, "advance": 0}
        for username in ("reader", "editor", "other"):
            with self.subTest(user=username):
                with self.assertRaises(PermissionError):
                    service.accounting_command(tokens[username], sales)
                with self.assertRaises(PermissionError):
                    service.accounting_read(tokens[username], PROJECT)
        with self.assertRaises(PermissionError):
            service.accounting_command("invalid-session", sales)
        self.assert_unchanged(baseline)
        issued = service.accounting_command(admin, sales)
        doc_id = issued["documentId"]
        self.assertEqual(len(service.accounting_read(admin, PROJECT)["documents"]), 1)
        # Session actor, not an asserted actor inside the command, determines ACL.
        self.assertEqual(service.accounting_read(admin, PROJECT)["documents"]
                         [0]["id"], doc_id)
        self.assertIsNone(service.server)

    def test_read_filtered_project_does_not_mislabel_global_trial_balance(self):
        sale_id = self.sale_draft()
        self.review_issue(sale_id, "project-label")
        data = self.bridge.accountingRead(PROJECT)
        self.assertEqual(data["trialBalanceScope"], "all-projects")
        self.assertEqual(data["partyBalancesScope"], "all-projects")
        self.assertEqual(len(data["documents"]), 1)
        self.assertEqual(self.bridge.accountingRead("p-personal")["documents"], [])
        self.assertEqual(self.bridge.accountingRead("p-personal")
                         ["trialBalanceScope"], "all-projects")


if __name__ == "__main__":
    unittest.main()
