"""Synthetic exact purchase stock valuation and fail-closed input tax controls."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from accounting_core import (
    accounting_view, apply_accounting_command, empty_rial_accounting_state,
    validate_accounting_state,
)
from accounting_reporting import ledger_reports
from standalone_accounting import StandaloneAccountingStore


NOW = "2026-11-03T16:00:00+03:30"
ACTORS = {
    "admin": {"username": "admin", "role": "admin"},
    "bookkeeper": {"username": "bookkeeper", "role": "editor",
                   "financeEdit": True, "financeView": True},
    "reader": {"username": "reader", "role": "viewer", "financeView": True},
}
POLICY = {
    "discountAllocation": "per-line-exact",
    "lineDiscounts": [{"lineIndex": 0, "amount": 1},
                      {"lineIndex": 1, "amount": 3},
                      {"lineIndex": 2, "amount": 6}],
    "allocationReference": "supplier-evidence-1",
    "allocationReason": "Approved supplier split across goods and service",
}


class ExactPurchaseAllocationTests(unittest.TestCase):
    def setUp(self):
        self.state = empty_rial_accounting_state()
        self.sequence = 0

    def command(self, command_type, *, actor="admin", event_id=None, **fields):
        self.sequence += 1
        command = {"type": command_type, "eventId": event_id or f"exact-{self.sequence}", **fields}
        output = apply_accounting_command(self.state, command,
                                          actor=actor, accounts=ACTORS, now=NOW)
        self.state = output["state"]
        return output

    def view(self):
        return accounting_view(self.state, actor="admin", accounts=ACTORS)

    def bootstrap(self, *, tax=18, discount=10):
        for item_id in ("A", "B"):
            self.command("item.create", itemId=item_id, sku=f"SKU{item_id}",
                         name=f"Goods {item_id}", kind="goods", unit="piece")
            self.command("item.stock.enable", itemId=item_id)
        for warehouse in ("WH1", "WH2"):
            self.command("warehouse.create", warehouseId=warehouse, name=warehouse)
        self.command("party.register", partyId="vendor", name="Vendor", kind="vendor")
        self.command("bill.create", billId="purchase", partyId="vendor",
                     documentDate="2026-10-01", tax=tax, discount=discount, lines=[
                         {"description": "Goods A", "quantity": 3, "unitPrice": 100,
                          "itemId": "A"},
                         {"description": "Goods B", "quantity": 2, "unitPrice": 70,
                          "itemId": "B"},
                         {"description": "Service", "quantity": 1, "unitPrice": 50},
                     ])
        self.command("bill.approve", billId="purchase")
        self.command("bill.issue", billId="purchase", postingDate="2026-10-01")

    def receive(self, item, quantity, warehouse="WH1", **policy):
        return self.command("inventory.receive", warehouseId=warehouse,
                            itemId=item, quantity=quantity, billId="purchase",
                            postingDate="2026-10-03", taxTreatment="expense",
                            **(policy if policy else POLICY))

    def assert_financial_balances(self):
        view = self.view()
        self.assertTrue(validate_accounting_state(self.state))
        report = ledger_reports(view)
        self.assertTrue(report["reconciled"])
        self.assertEqual(report["trialBalance"]["totalDebit"],
                         report["trialBalance"]["totalCredit"])
        self.assertEqual(view["accounts"]["1300"]["debitMinusCredit"], sum(
            bucket["value"] for warehouse in view["stock"].values()
            for bucket in warehouse.values()))
        return view, report

    def test_mixed_lines_fractional_cost_and_tax_expense_reconcile_exactly(self):
        self.bootstrap()
        first = self.receive("A", 2)
        second = self.receive("A", 1, "WH2")
        third = self.receive("B", 1)
        fourth = self.receive("B", 1, "WH2")
        self.assertEqual([x["result"]["value"] for x in (first, second, third, fourth)],
                         [200, 99, 69, 68])
        view, reports = self.assert_financial_balances()
        self.assertEqual(view["accounts"]["1300"]["debitMinusCredit"], 436)
        self.assertEqual(view["accounts"]["5000"]["debitMinusCredit"], 50)
        self.assertEqual(view["accounts"]["5100"]["debitMinusCredit"], -6)
        self.assertEqual(view["accounts"]["5200"]["debitMinusCredit"], 18)
        self.assertEqual(view["accounts"]["2000"]["debitMinusCredit"], -498)
        self.assertEqual(reports["profitLoss"],
                         {"revenue": 6, "expense": 68, "net": -62})
        self.assertEqual(view["bills"]["purchase"]["receiptDiscountAllocation"]
                         ["lineDiscounts"], [1, 3, 6])
        self.assertEqual(view["stock"]["WH1"]["A"]["layers"], [
            {"source": "@receipt:" + first["state"]["events"][-1]["eventId"],
             "quantity": 2, "unitCost": 100}])
        self.assertEqual(view["stock"]["WH2"]["A"]["layers"][0]["unitCost"], 99)

    def test_fifo_issue_uses_exact_integer_layers_and_reverses_cogs(self):
        self.bootstrap()
        self.receive("A", 3)
        self.command("party.register", partyId="buyer", name="Buyer", kind="customer")
        self.command("invoice.create", invoiceId="sale", partyId="buyer",
                     documentDate="2026-10-02", lines=[
                         {"description": "Sale", "quantity": 3,
                          "unitPrice": 150, "itemId": "A"}])
        self.command("invoice.approve", invoiceId="sale")
        self.command("invoice.issue", invoiceId="sale", postingDate="2026-10-03")
        issue = self.command("inventory.issue", warehouseId="WH1", itemId="A",
                             quantity=3, invoiceId="sale", postingDate="2026-10-03")
        self.assertEqual(issue["result"]["value"], 299)
        self.assertEqual(self.view()["accounts"]["5300"]["debitMinusCredit"], 299)
        self.command("inventory.reverse", movementId=issue["result"]["movementId"],
                     postingDate="2026-10-04", reason="Synthetic sales reversal")
        view, _ = self.assert_financial_balances()
        self.assertEqual(view["stock"]["WH1"]["A"]["value"], 299)
        self.assertEqual(view["accounts"]["5300"]["debitMinusCredit"], 0)

    def test_reversing_last_fractional_receipt_restores_same_gl_and_reposts(self):
        self.bootstrap()
        a = self.receive("A", 2)
        b = self.receive("A", 1)
        with self.assertRaisesRegex(ValueError, "subsequent item movements"):
            self.command("inventory.reverse", movementId=a["result"]["movementId"],
                         postingDate="2026-10-04", reason="Out of order")
        self.command("inventory.reverse", movementId=b["result"]["movementId"],
                     postingDate="2026-10-04", reason="Correct receipt quantity")
        view, _ = self.assert_financial_balances()
        self.assertEqual(view["stock"]["WH1"]["A"]["value"], 200)
        self.assertEqual(view["accounts"]["5100"]["debitMinusCredit"], -10)
        self.assertEqual(self.receive("A", 1)["result"]["value"], 99)
        self.assert_financial_balances()

    def test_mixed_purchase_return_is_line_specific_and_remaining_goods_can_be_received(self):
        self.bootstrap(tax=0)
        a = self.receive("A", 3)
        b = self.receive("B", 2)
        self.command("inventory.reverse", movementId=a["result"]["movementId"],
                     postingDate="2026-10-04", reason="Return before stock recost")
        self.command("inventory.reverse", movementId=b["result"]["movementId"],
                     postingDate="2026-10-04", reason="Return before stock recost")
        self.command("bill.return", billId="purchase", returnId="return-A-and-service",
                     postingDate="2026-10-04", reason="Partial vendor credit note",
                     lines=[{"lineIndex": 0, "quantity": 1},
                            {"lineIndex": 2, "quantity": 1}])
        note = self.view()["returns"]["return-A-and-service"]
        self.assertEqual(note["discount"], 6)
        self.assertEqual(note["subtotal"], 150)
        self.assertEqual(self.receive("A", 1)["result"]["value"], 100)
        self.assertEqual(self.receive("A", 1)["result"]["value"], 99)
        self.assertEqual(self.receive("B", 2)["result"]["value"], 137)
        view, _ = self.assert_financial_balances()
        self.assertEqual(view["stock"]["WH1"]["A"]["value"], 199)
        self.assertEqual(view["stock"]["WH1"]["B"]["value"], 137)
        self.assertEqual(view["accounts"]["1300"]["debitMinusCredit"], 336)

    def test_two_partial_returns_use_cumulative_integer_discount_without_double_rounding(self):
        self.bootstrap(tax=0)
        receipt = self.receive("A", 3)
        self.command("inventory.reverse", movementId=receipt["result"]["movementId"],
                     postingDate="2026-10-04", reason="Correct supplier partial returns")
        for index in (1, 2):
            self.command("bill.return", billId="purchase", returnId=f"ret{index}",
                         postingDate="2026-10-04", reason="Vendor credit tranche",
                         lines=[{"lineIndex": 0, "quantity": 1}])
        view = self.view()
        self.assertEqual([view["returns"][f"ret{i}"]["discount"] for i in (1, 2)],
                         [0, 1])
        self.assertEqual(self.receive("A", 1)["result"]["value"], 100)
        self.assert_financial_balances()

    def test_taxed_mixed_purchase_partial_return_requires_source_tax_allocation(self):
        self.bootstrap(tax=18)
        receipt = self.receive("A", 3)
        self.command("inventory.reverse", movementId=receipt["result"]["movementId"],
                     postingDate="2026-10-04", reason="Restore stock before supplier credit")
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "source-approved tax allocation"):
            self.command("bill.return", billId="purchase", returnId="unsupported-tax-credit",
                         postingDate="2026-10-04", reason="Tax source not itemized",
                         lines=[{"lineIndex": 0, "quantity": 1}])
        self.assertEqual(self.state, before)
        self.assert_financial_balances()

    def test_fifo_transfer_round_trip_before_exact_receipt_reversal(self):
        self.bootstrap()
        receipt = self.receive("A", 3)
        moved = self.command("inventory.transfer", warehouseId="WH1", toWarehouseId="WH2",
                             itemId="A", quantity=2, postingDate="2026-10-04",
                             reason="Transfer source-verified stock")
        view, _ = self.assert_financial_balances()
        self.assertEqual(view["stock"]["WH2"]["A"]["value"], 200)
        with self.assertRaisesRegex(ValueError, "subsequent item movements"):
            self.command("inventory.reverse", movementId=receipt["result"]["movementId"],
                         postingDate="2026-10-04", reason="Cannot undo transferred stock")
        self.command("inventory.reverse", movementId=moved["result"]["movementId"],
                     postingDate="2026-10-04", reason="Reverse transfer first")
        self.command("inventory.reverse", movementId=receipt["result"]["movementId"],
                     postingDate="2026-10-04", reason="Undo complete receipt")
        view, _ = self.assert_financial_balances()
        self.assertEqual(view["stock"]["WH1"]["A"]["value"], 0)
        self.assertEqual(view["accounts"]["1300"]["debitMinusCredit"], 0)

    def test_full_return_after_receipt_reversals_clears_gl_and_payable(self):
        self.bootstrap()
        a = self.receive("A", 3)
        b = self.receive("B", 2)
        self.command("inventory.reverse", movementId=b["result"]["movementId"],
                     postingDate="2026-10-04", reason="Supplier cancelled purchase")
        self.command("inventory.reverse", movementId=a["result"]["movementId"],
                     postingDate="2026-10-04", reason="Supplier cancelled purchase")
        self.command("bill.return", billId="purchase", returnId="full-credit",
                     postingDate="2026-10-04", reason="Fully refunded purchase",
                     lines=[{"lineIndex": 0, "quantity": 3},
                            {"lineIndex": 1, "quantity": 2},
                            {"lineIndex": 2, "quantity": 1}])
        view, report = self.assert_financial_balances()
        self.assertEqual(view["returns"]["full-credit"]["discount"], 10)
        self.assertEqual(view["returns"]["full-credit"]["tax"], 18)
        self.assertEqual(view["parties"]["vendor"]["payable"], 0)
        self.assertEqual(report["balanceSheet"]["assets"], 0)
        self.assertEqual(report["profitLoss"]["net"], 0)

    def test_fail_closed_recoverable_vat_and_allocation_contract(self):
        self.bootstrap()
        attempts = [
            ({**POLICY, "taxTreatment": "recoverable"}, "taxTreatment"),
            ({**POLICY, "lineDiscounts": POLICY["lineDiscounts"][:-1]}, "every purchase line"),
            ({**POLICY, "lineDiscounts": [{"lineIndex": 0, "amount": 0},
                                         {"lineIndex": 1, "amount": 3},
                                         {"lineIndex": 2, "amount": 6}]}, "equal"),
            ({**POLICY, "lineDiscounts": [{"lineIndex": 0, "amount": 1},
                                         {"lineIndex": 0, "amount": 3},
                                         {"lineIndex": 2, "amount": 6}]}, "lineIndex"),
            ({**POLICY, "lineDiscounts": [{"lineIndex": 0, "amount": True},
                                         *POLICY["lineDiscounts"][1:]]}, "exact integer"),
            ({**POLICY, "allocationReason": ""}, "allocationReason"),
            ({**POLICY, "allocationReference": "invalid spaces"}, "allocationReference"),
        ]
        for args, message in attempts:
            with self.subTest(message=message):
                before = deepcopy(self.state)
                with self.assertRaisesRegex(ValueError, message):
                    self.command("inventory.receive", warehouseId="WH1", itemId="A",
                                 quantity=1, billId="purchase", postingDate="2026-10-03",
                                 **{**args, "taxTreatment": args.get("taxTreatment", "expense")})
                self.assertEqual(self.state, before)
        self.assert_financial_balances()

    def test_admin_allocation_policy_cannot_be_modified_mid_receipt(self):
        self.bootstrap()
        self.receive("A", 1)
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "differs"):
            changed = deepcopy(POLICY)
            changed["lineDiscounts"] = [{"lineIndex": 0, "amount": 2},
                                        {"lineIndex": 1, "amount": 2},
                                        {"lineIndex": 2, "amount": 6}]
            self.receive("A", 1, **changed)
        self.assertEqual(self.state, before)
        self.assert_financial_balances()

    def test_receipt_rejects_discount_allocation_after_historical_return(self):
        self.bootstrap()
        self.command("bill.return", billId="purchase", returnId="early-service",
                     postingDate="2026-10-04", reason="Prior unallocated return",
                     lines=[{"lineIndex": 2, "quantity": 1}])
        snapshot = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "before partial purchase returns"):
            self.receive("A", 1)
        self.assertEqual(self.state, snapshot)

    def test_invalid_allocation_and_duplicate_stock_lines_fail_closed(self):
        self.bootstrap()
        high_discount = deepcopy(POLICY)
        high_discount["lineDiscounts"] = [
            {"lineIndex": 0, "amount": 300},
            {"lineIndex": 1, "amount": 0},
            {"lineIndex": 2, "amount": 0},
        ]
        # The purchase itself has only 10 of total discount, so this cannot be
        # rerouted to goods even though every single line amount is in range.
        snapshot = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "must equal"):
            self.receive("A", 1, **high_discount)
        self.assertEqual(self.state, snapshot)

    def test_zero_unit_cost_fails_closed_without_stock_or_gl_side_effects(self):
        self.bootstrap()
        self.command("bill.create", billId="low-price", partyId="vendor",
                     documentDate="2026-10-02", discount=2,
                     lines=[{"description": "Low priced stock", "quantity": 3,
                             "unitPrice": 1, "itemId": "A"}])
        self.command("bill.approve", billId="low-price")
        self.command("bill.issue", billId="low-price", postingDate="2026-10-03")
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "Zero-cost units"):
            self.command("inventory.receive", warehouseId="WH1", itemId="A",
                         quantity=2, billId="low-price", postingDate="2026-10-03",
                         taxTreatment="none", discountAllocation="per-line-exact",
                         lineDiscounts=[{"lineIndex": 0, "amount": 2}],
                         allocationReference="supplier-zero-test",
                         allocationReason="Would create zero-valued item")
        self.assertEqual(self.state, before)
        self.assert_financial_balances()
        self.command("bill.create", billId="duplicate", partyId="vendor",
                     documentDate="2026-10-02", discount=1,
                     lines=[{"description": "A first", "quantity": 2,
                             "unitPrice": 100, "itemId": "A"},
                            {"description": "A second", "quantity": 2,
                             "unitPrice": 100, "itemId": "A"}])
        self.command("bill.approve", billId="duplicate")
        self.command("bill.issue", billId="duplicate", postingDate="2026-10-03")
        snapshot = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "one matching stock line"):
            self.command("inventory.receive", warehouseId="WH1", itemId="A",
                         quantity=1, billId="duplicate", postingDate="2026-10-03",
                         discountAllocation="per-line-exact", taxTreatment="none",
                         lineDiscounts=[{"lineIndex": 0, "amount": 1},
                                        {"lineIndex": 1, "amount": 0}],
                         allocationReference="supplier-dup",
                         allocationReason="Cannot choose duplicate goods row")
        self.assertEqual(self.state, snapshot)

    def test_editor_cannot_set_exact_allocation_or_use_admin_identity(self):
        self.bootstrap()
        before = deepcopy(self.state)
        with self.assertRaisesRegex(PermissionError, "administrator"):
            self.command("inventory.receive", actor="bookkeeper", itemId="A",
                         warehouseId="WH1", quantity=1, postingDate="2026-10-03",
                         billId="purchase", taxTreatment="expense", **POLICY)
        self.assertEqual(self.state, before)
        with self.assertRaises(PermissionError):
            self.command("inventory.receive", actor="reader", itemId="A",
                         warehouseId="WH1", quantity=1, postingDate="2026-10-03",
                         billId="purchase", taxTreatment="expense", **POLICY)
        self.assert_financial_balances()

    def test_repeat_event_is_idempotent_and_tamper_is_rejected(self):
        self.bootstrap()
        command = {"type": "inventory.receive", "eventId": "fixed-receipt",
                   "warehouseId": "WH1", "itemId": "A", "quantity": 1,
                   "billId": "purchase", "postingDate": "2026-10-03",
                   "taxTreatment": "expense", **POLICY}
        original = apply_accounting_command(self.state, command,
                                            actor="admin", accounts=ACTORS, now=NOW)
        self.state = original["state"]
        again = apply_accounting_command(self.state, command,
                                         actor="admin", accounts=ACTORS, now=NOW)
        self.assertFalse(again["changed"])
        self.assertEqual(again["state"], self.state)
        changed = deepcopy(command)
        changed["allocationReference"] = "different-evidence"
        with self.assertRaisesRegex(ValueError, "Event ID reused"):
            apply_accounting_command(self.state, changed,
                                     actor="admin", accounts=ACTORS, now=NOW)
        self.assert_financial_balances()

    def test_sqlite_cas_and_replay_on_disposable_rial_store(self):
        self.bootstrap()
        with TemporaryDirectory(prefix="madar-fin02-synthetic-") as directory:
            store = StandaloneAccountingStore(
                Path(directory) / "synthetic-accounting.sqlite3", default_currency="RIAL")
            # Replay the validated seed via the real event/CAS storage boundary.
            for record in self.state["events"]:
                snapshot = store.read(actor="admin", accounts=ACTORS)
                store.command(record["command"], actor="admin", accounts=ACTORS,
                              now=record["at"], expected_revision=snapshot["revision"])
            before = store.read(actor="admin", accounts=ACTORS)
            command = {"type": "inventory.receive", "eventId": "sqlite-validated-receipt",
                       "warehouseId": "WH1", "itemId": "A", "quantity": 3,
                       "billId": "purchase", "postingDate": "2026-10-03",
                       "taxTreatment": "expense", **POLICY}
            result = store.command(command, actor="admin", accounts=ACTORS,
                                   now=NOW, expected_revision=before["revision"])
            self.assertEqual(result["revision"], before["revision"] + 1)
            reopened = StandaloneAccountingStore(
                Path(directory) / "synthetic-accounting.sqlite3", default_currency="RIAL")
            projection = reopened.read(actor="admin", accounts=ACTORS)
            self.assertEqual(projection["view"]["stock"]["WH1"]["A"]["value"], 299)
            self.assertEqual(projection["view"]["accounts"]["1300"]["debitMinusCredit"], 299)
            self.assertEqual(projection["revision"], result["revision"])
            self.assertTrue(ledger_reports(projection["view"])["reconciled"])


if __name__ == "__main__":
    unittest.main()
