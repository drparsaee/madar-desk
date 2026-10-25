"""Standalone finance ACL: comprehensive reducer/LAN parity with synthetic data."""

from copy import deepcopy
from pathlib import Path
import tempfile
import threading
import time
import unittest

import accounting_core as core
from lan import LanService, standalone_finance_access, standalone_finance_accounts
from native_app import Bridge


DAY = "2026-10-24"
NOW = DAY + "T12:00:00Z"
AUTHORITY = {
    "root": {"username": "root", "role": "admin"},
    "editor": {"username": "editor", "role": "editor",
               "financeView": True, "financeEdit": True},
    "writer": {"username": "writer", "role": "editor",
               "financeView": False, "financeEdit": True},
    "reader": {"username": "reader", "role": "editor",
               "financeView": True, "financeEdit": False},
    "auditor": {"username": "auditor", "role": "viewer",
                "financeView": True, "financeEdit": False},
    "forged-viewer": {"username": "forged-viewer", "role": "viewer",
                      "financeView": False, "financeEdit": True},
}

# Independent expected contract. In particular no wildcard "inventory.*" or
# "fiscal.*" should silently turn future commands into finance-editor powers.
STANDARD = frozenset({
    "proforma.create", "proforma.update", "proforma.send", "proforma.accept",
    "proforma.reject", "proforma.cancel", "proforma.convert",
    "contractor.job.intake", "contractor.job.price", "contractor.job.approve",
    "contractor.bill.create",
    "party.register", "party.update", "item.create", "item.update",
    "invoice.create", "invoice.update", "invoice.reopen", "invoice.approve",
    "invoice.issue", "invoice.cancel", "invoice.return", "invoice.correct",
    "bill.create", "bill.update", "bill.reopen", "bill.approve",
    "bill.issue", "bill.cancel", "bill.return", "bill.correct",
    "receipt.record", "payment.record", "funds.transfer",
    "journal.manual", "journal.reverse",
    "warehouse.create", "item.stock.enable", "inventory.receive",
    "inventory.issue", "inventory.transfer", "inventory.adjust",
    "inventory.reverse",
    "cheque.register", "cheque.deposit", "cheque.endorse", "cheque.clear",
    "cheque.return", "cheque.redeliver", "cheque.cancel",
    "bank.statement.add", "bank.statement.batch", "bank.statement.match",
    "bank.statement.unmatch", "installments.create", "installments.cancel",
    "payroll.accrue", "payroll.pay", "payroll.remit",
})
ADMIN_ONLY = frozenset({
    "account.create", "company.profile.set", "funds.deposit",
    "inventory.opening", "tax.rule.set", "fiscal.year.close", "period.close",
})


class FinanceAclComprehensiveTests(unittest.TestCase):
    def setUp(self):
        self.state = core.empty_rial_accounting_state()
        self.serial = 0

    def cmd(self, typ, *, actor="editor", **fields):
        self.serial += 1
        result = core.apply_accounting_command(
            self.state, {"type": typ, "eventId": f"acl.{self.serial}", **fields},
            actor=actor, accounts=AUTHORITY, now=NOW)
        self.state = result["state"]
        self.assertTrue(result["changed"])
        self.assertTrue(core.validate_accounting_state(self.state))
        return result["result"]

    def view(self):
        return core.accounting_view(self.state, actor="root", accounts=AUTHORITY)

    def document(self, direction, identifier, party, price, quantity=2, *, actor="editor",
                 item_id=None):
        key = "invoiceId" if direction == "invoice" else "billId"
        line = {"description": "Synthetic", "unitPrice": price, "quantity": quantity}
        if item_id:
            line["itemId"] = item_id
        self.cmd(direction + ".create", actor=actor, **{key: identifier},
                 partyId=party, documentDate="2026-10-15", lines=[line])
        self.cmd(direction + ".approve", actor=actor, **{key: identifier})
        return self.cmd(direction + ".issue", actor=actor, **{key: identifier},
                        postingDate="2026-10-16")

    def test_policy_is_explicit_complete_disjoint_and_admin_only_is_protected(self):
        self.assertEqual(core._EDITOR_FINANCE_COMMANDS, STANDARD)
        self.assertEqual(core._ADMIN_ONLY_COMMANDS, ADMIN_ONLY)
        self.assertFalse(STANDARD & ADMIN_ONLY)
        for command in sorted(STANDARD):
            with self.subTest(allowed=command):
                core._require("editor", command, finance_edit=True)
                core._require("admin", command)
                for role, grant in (("editor", False), ("viewer", True),
                                    ("viewer", False)):
                    with self.assertRaises(PermissionError):
                        core._require(role, command, finance_edit=grant)
        for command in sorted(ADMIN_ONLY | {
            "fiscal.year.reopen", "payroll.privilege.grant", "invoice.force-issue",
            "inventory.opening.unsafe",
        }):
            with self.subTest(protected=command):
                core._require("admin", command)
                with self.assertRaises(PermissionError):
                    core._require("editor", command, finance_edit=True)
        with self.assertRaises(PermissionError):
            core._require("viewer", "invoice.approve", finance_edit=True)

    def test_lan_write_gate_and_reducer_agree_for_operational_mutations(self):
        for name in ("root", "editor", "writer"):
            standalone_finance_access(name, AUTHORITY, mutation=True)
        for name in ("reader", "auditor", "forged-viewer"):
            with self.subTest(name=name), self.assertRaises(PermissionError):
                standalone_finance_access(name, AUTHORITY, mutation=True)
        trusted = standalone_finance_accounts(AUTHORITY)
        self.assertTrue(trusted["editor"]["financeEdit"])
        self.assertFalse(trusted["auditor"]["financeEdit"])
        self.cmd("party.register", actor="editor", partyId="C", name="Customer",
                 kind="customer")
        self.cmd("party.register", actor="writer", partyId="V", name="Supplier",
                 kind="vendor")
        self.document("invoice", "S", "C", 100, actor="editor")
        self.document("bill", "B", "V", 70, actor="writer")
        self.assertEqual(self.view()["invoices"]["S"]["status"], "issued")
        self.assertEqual(self.view()["bills"]["B"]["status"], "issued")
        self.assertEqual(self.view()["parties"]["C"]["receivable"], 200)
        self.assertEqual(self.view()["parties"]["V"]["payable"], 140)
        self.assertTrue(all(
            event["role"] == "editor" and event["financeEdit"] is True
            for event in self.state["events"]))

    def test_editor_can_settle_sale_purchase_and_issue_credit_note(self):
        self.cmd("party.register", partyId="C", name="Customer", kind="customer")
        self.cmd("party.register", partyId="V", name="Vendor", kind="vendor")
        self.document("invoice", "S", "C", 150)
        self.document("bill", "B", "V", 100)
        self.cmd("funds.deposit", actor="root", accountId="1010", amount=500,
                 postingDate="2026-10-16", note="Synthetic capital only")
        self.cmd("receipt.record", receiptId="R", partyId="C", accountId="1010",
                 postingDate=DAY, allocations=[{"invoiceId": "S", "amount": 100}])
        self.cmd("payment.record", paymentId="P", partyId="V", accountId="1010",
                 postingDate=DAY, allocations=[{"billId": "B", "amount": 80}])
        self.cmd("invoice.return", invoiceId="S", returnId="CREDIT1",
                 postingDate=DAY, reason="Part of purchase returned",
                 lines=[{"lineIndex": 0, "quantity": 1}])
        self.assertEqual(self.view()["invoices"]["S"]["status"], "issued")
        self.assertEqual(self.view()["returns"]["CREDIT1"]["amount"], 150)
        self.assertEqual(self.view()["parties"]["C"]["receivable"], 50)
        self.assertEqual(self.view()["parties"]["V"]["payable"], 120)
        self.assertEqual(self.view()["accounts"]["1010"]["debitMinusCredit"], 520)

    def test_editor_can_manage_stock_without_receiving_owner_opening_power(self):
        self.cmd("item.create", itemId="I", sku="SKU", name="Tracked",
                 kind="goods", unit="pcs")
        self.cmd("item.stock.enable", itemId="I")
        self.cmd("warehouse.create", warehouseId="W", name="Synthetic warehouse")
        self.cmd("party.register", partyId="V", name="Vendor", kind="vendor")
        self.cmd("party.register", partyId="C", name="Customer", kind="customer")
        self.document("bill", "B", "V", 40, quantity=3, item_id="I")
        receipt = self.cmd("inventory.receive", warehouseId="W", itemId="I",
                           quantity=3, billId="B", postingDate=DAY)
        self.assertEqual(receipt["value"], 120)
        self.document("invoice", "S", "C", 100, quantity=2, item_id="I")
        issue = self.cmd("inventory.issue", warehouseId="W", itemId="I",
                         quantity=2, invoiceId="S", postingDate=DAY)
        self.assertEqual(issue["value"], 80)
        self.assertEqual(self.view()["stock"]["W"]["I"]["quantity"], 1)
        self.cmd("inventory.reverse", movementId=issue["movementId"],
                 postingDate=DAY, reason="Synthetic goods returned")
        self.assertEqual(self.view()["stock"]["W"]["I"]["quantity"], 3)
        with self.assertRaises(PermissionError):
            self.cmd("inventory.opening", warehouseId="W", itemId="I",
                     quantity=1, unitCost=10, postingDate=DAY,
                     reason="Unauthorized capital entry")
        self.assertEqual(self.view()["stock"]["W"]["I"]["quantity"], 3)

    def test_editor_can_reconcile_bank_and_handle_cheque_but_not_fiscal_closure(self):
        self.cmd("party.register", partyId="C", name="Customer", kind="customer")
        self.document("invoice", "S", "C", 100)
        self.cmd("cheque.register", chequeId="CH", direction="receipt",
                 documentId="S", bankAccountId="1010", dueDate="2026-10-17",
                 amount=100, reference="Synthetic cheque")
        self.cmd("cheque.deposit", chequeId="CH")
        cheque = self.cmd("cheque.clear", chequeId="CH", postingDate=DAY)
        self.assertEqual(cheque["status"], "cleared")
        self.cmd("bank.statement.add", statementId="ST", accountId="1010",
                 date=DAY, amount=100, reference="Synthetic bank row")
        journal_id = self.view()["cheques"]["CH"]["journalId"]
        self.cmd("bank.statement.match", statementId="ST",
                 journalId=journal_id, reason="Verified synthetic bank movement")
        self.assertEqual(self.view()["bankStatements"]["ST"]["journalId"],
                         journal_id)
        self.cmd("bank.statement.unmatch", statementId="ST",
                 reason="Reconciliation correction")
        self.assertIsNone(self.view()["bankStatements"]["ST"]["journalId"])
        for command in sorted(ADMIN_ONLY):
            with self.subTest(admin_only=command), self.assertRaises(PermissionError):
                # Permission always precedes payload validation or state mutation.
                self.cmd(command)
        self.assertEqual(self.view()["parties"]["C"]["receivable"], 100)

    def test_missing_or_revoked_grant_and_forged_viewer_cannot_mutate(self):
        before = deepcopy(self.state)
        payload = {"type": "party.register", "eventId": "acl.denied",
                   "partyId": "C", "name": "No", "kind": "customer"}
        for actor in ("reader", "auditor", "forged-viewer"):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                core.apply_accounting_command(
                    self.state, payload, actor=actor, accounts=AUTHORITY, now=NOW)
            self.assertEqual(self.state, before)
        with self.assertRaises(PermissionError):
            core.accounting_view(self.state, actor="forged-viewer", accounts=AUTHORITY)
        core.accounting_view(self.state, actor="auditor", accounts=AUTHORITY)
        self.cmd("party.register", partyId="C", name="Synthetic", kind="customer")
        recorded = deepcopy(self.state)
        self.assertTrue(core.validate_accounting_state(recorded))
        revoked = deepcopy(AUTHORITY)
        revoked["editor"]["financeEdit"] = False
        with self.assertRaises(PermissionError):
            core.apply_accounting_command(
                recorded, recorded["events"][0]["command"],
                actor="editor", accounts=revoked, now=NOW)
        self.assertEqual(self.state, recorded)
        self.assertTrue(core.validate_accounting_state(recorded))

    def test_direct_editor_write_permission_even_without_finance_view(self):
        # A finance writer MUST also read the same ledger, even when the
        # optional financeView grant is absent. Viewer remains unprivileged.
        standalone_finance_access("writer", AUTHORITY, mutation=False)
        with self.assertRaises(PermissionError):
            standalone_finance_access("forged-viewer", AUTHORITY, mutation=False)
        standalone_finance_access("writer", AUTHORITY, mutation=True)
        self.cmd("party.register", actor="writer", partyId="V",
                 name="Supplier", kind="vendor")
        self.assertEqual(self.view()["parties"]["V"]["kind"], "vendor")

    def test_historical_toman_admin_events_remain_replayable(self):
        self.state = core.empty_accounting_state()
        self.cmd("funds.deposit", actor="root", accountId="1010", amount=500,
                 postingDate="2026-10-16", note="Legacy owner capitalization")
        self.cmd("funds.transfer", actor="editor", fromAccountId="1010",
                 toAccountId="1000", amount=100, postingDate=DAY,
                 note="Ordinary cash movement")
        self.assertEqual(self.view()["accounts"]["1000"]["normalBalance"], 100)
        self.assertTrue(core.validate_accounting_state(self.state))

    def test_editor_cannot_bypass_owner_capital_controls_through_other_commands(self):
        funding = self.cmd(
            "funds.deposit", actor="root", accountId="1010", amount=500,
            postingDate="2026-10-16", note="Owner-approved cash opening")
        before = deepcopy(self.state)
        with self.assertRaisesRegex(PermissionError, "owner equity"):
            self.cmd("journal.reverse", journalId=funding["journalId"],
                     postingDate=DAY, reason="Undo capital without admin")
        with self.assertRaisesRegex(PermissionError, "equity"):
            self.cmd("journal.manual", postingDate=DAY,
                     note="Disguised owner injection", lines=[
                         {"accountId": "1010", "debit": 100, "credit": 0},
                         {"accountId": "3000", "debit": 0, "credit": 100}])
        self.assertEqual(self.state, before)
        manual = self.cmd("journal.manual", actor="root", postingDate=DAY,
                          note="Owner-approved capital adjustment", lines=[
                              {"accountId": "1010", "debit": 100, "credit": 0},
                              {"accountId": "3000", "debit": 0, "credit": 100}])
        after_manual = deepcopy(self.state)
        with self.assertRaisesRegex(PermissionError, "owner equity"):
            self.cmd("journal.reverse", journalId=manual["journalId"],
                     postingDate=DAY, reason="Undo approved equity without admin")
        self.assertEqual(self.state, after_manual)
        self.cmd("item.create", itemId="I", sku="ITEM", name="Goods",
                 kind="goods", unit="pcs")
        self.cmd("item.stock.enable", itemId="I")
        self.cmd("warehouse.create", warehouseId="W", name="Warehouse")
        opening = self.cmd(
            "inventory.opening", actor="root", warehouseId="W", itemId="I",
            quantity=2, unitCost=10, postingDate=DAY,
            reason="Admin owner capital opening")
        stock_before = deepcopy(self.state)
        with self.assertRaisesRegex(PermissionError, "opening inventory"):
            self.cmd("inventory.reverse", movementId=opening["movementId"],
                     postingDate=DAY, reason="Unauthorized opening reversal")
        self.assertEqual(self.state, stock_before)
        self.cmd("inventory.reverse", actor="root",
                 movementId=opening["movementId"], postingDate=DAY,
                 reason="Admin-approved opening reversal")
        self.assertEqual(self.view()["stock"]["W"]["I"]["quantity"], 0)

    def test_real_lan_service_and_real_store_allow_editor_issue_but_block_closure(self):
        # No real APPDATA, task database, browser, network listener or SQL.
        with tempfile.TemporaryDirectory(prefix="madar-acl-real-host-synthetic-") as root:
            path = Path(root)
            bridge = Bridge.__new__(Bridge)
            bridge.path = path / "tasks.json"
            bridge._lock = threading.RLock()
            bridge.connection = {"mode": "server"}
            bridge.lan = None
            service = LanService(bridge, path / "lan-users.json",
                                 bind="127.0.0.1", port=0)
            service.users = deepcopy(AUTHORITY)
            bridge.lan = service
            for actor in ("root", "editor", "reader", "auditor"):
                service.sessions["token." + actor] = (actor, time.time() + 3600)

            revision = 0

            def invoke(command_type, *, actor="editor", **fields):
                nonlocal revision
                request = {"command": {
                    "type": command_type, "eventId": "LAN." + str(revision + 1),
                    **fields}, "expectedRevision": revision}
                outcome = service.standalone_accounting_command(
                    "token." + actor, request)
                revision = outcome["revision"]
                return outcome

            invoke("party.register", partyId="C", name="Synthetic LAN customer",
                   kind="customer")
            invoke("invoice.create", invoiceId="S", partyId="C",
                   documentDate="2026-10-15", lines=[
                       {"description": "Sale", "quantity": 1, "unitPrice": 50}])
            invoke("invoice.approve", invoiceId="S")
            issued = invoke("invoice.issue", invoiceId="S", postingDate="2026-10-16")
            self.assertEqual(issued["view"]["invoices"]["S"]["status"], "issued")
            self.assertEqual(revision, 4)
            with self.assertRaises(PermissionError):
                invoke("period.close", throughDate=DAY)
            with self.assertRaises(PermissionError):
                invoke("receipt.record", actor="auditor", receiptId="R",
                       partyId="C", accountId="1010", postingDate=DAY,
                       allocations=[{"invoiceId": "S", "amount": 50}])
            self.assertEqual(service.standalone_accounting_read(
                "token.reader")["revision"], 4)
            self.assertTrue((path / "standalone-accounting.sqlite3").is_file())
            self.assertFalse(bridge.path.exists())
            self.assertFalse((path / "finance.json").exists())


if __name__ == "__main__":
    unittest.main()
