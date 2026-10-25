"""Synthetic, disposable integration tests for the independent TOMAN store."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import standalone_accounting as module
from standalone_accounting import (
    AccountingIntegrityError, AccountingRevisionConflict,
    StandaloneAccountingError, StandaloneAccountingStore,
)


NOW = "2026-10-22T11:00:00Z"
DAY = "2026-10-22"
USERS = {
    "root": {"username": "root", "role": "admin"},
    "editor": {"username": "editor", "role": "editor", "financeEdit": True},
    "viewer": {"username": "viewer", "role": "viewer"},
    "auditor": {"username": "auditor", "role": "viewer", "financeView": True},
}


class StandaloneAccountingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-standalone-synthetic-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "isolated-accounting.sqlite3"
        self.store = StandaloneAccountingStore(self.path)

    def read(self, *, actor="root", accounts=None):
        return self.store.read(actor=actor, accounts=accounts or USERS)

    def cmd(self, typ, *, event_id=None, expected_revision=None,
            actor="root", accounts=None, now=NOW, **fields):
        head = self.read()
        if event_id is None:
            event_id = "evt-" + str(head["revision"] + 1)
        return self.store.command(
            {"type": typ, "eventId": event_id, **fields},
            actor=actor, accounts=accounts or USERS, now=now,
            expected_revision=(head["revision"] if expected_revision is None
                               else expected_revision),
        )

    def _customer(self):
        return self.cmd("party.register", partyId="client-1", name="Customer",
                        kind="customer")

    def _supplier(self):
        return self.cmd("party.register", partyId="supplier-1", name="Vendor",
                        kind="vendor")

    def _invoice(self):
        self._customer()
        self.cmd("invoice.create", invoiceId="inv-1", partyId="client-1",
                 documentDate="2026-10-21", lines=[
                     {"description": "Design work", "quantity": 2, "unitPrice": 500}])
        self.cmd("invoice.approve", invoiceId="inv-1")
        return self.cmd("invoice.issue", invoiceId="inv-1", postingDate=DAY)

    def _bill(self):
        self._supplier()
        self.cmd("bill.create", billId="bill-1", partyId="supplier-1",
                 documentDate="2026-10-21", lines=[
                     {"description": "Paper", "quantity": 2, "unitPrice": 200}])
        self.cmd("bill.approve", billId="bill-1")
        return self.cmd("bill.issue", billId="bill-1", postingDate=DAY)

    def _tamper(self, mutate, *, recompute_digest=False):
        connection = sqlite3.connect(str(self.path))
        try:
            row = connection.execute(
                "SELECT revision,state,digest FROM standalone_accounting").fetchone()
            assert row is not None
            state = json.loads(row[1])
            state = mutate(state)
            payload = json.dumps(state, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":"), allow_nan=False).encode("utf8")
            digest = sha256(payload).hexdigest() if recompute_digest else row[2]
            connection.execute(
                "UPDATE standalone_accounting SET state=?, digest=? WHERE id=1",
                (payload, digest))
            connection.commit()
        finally:
            connection.close()

    def test_empty_is_revision_zero_separate_database_and_detached_view(self):
        empty = self.read()
        self.assertEqual(empty["revision"], 0)
        self.assertEqual(empty["view"]["currency"], "TOMAN")
        self.assertEqual(empty["view"]["journals"], [])
        empty["view"]["accounts"]["1000"]["name"] = "forged"
        self.assertEqual(self.read()["view"]["accounts"]["1000"]["name"], "Cash")
        with closing(sqlite3.connect(str(self.path))) as connection:
            self.assertEqual(
                {x[0] for x in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")},
                {"standalone_accounting"})
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM standalone_accounting").fetchone()[0], 0)
        self.assertFalse((self.root / "unified.sqlite3").exists())

    def test_invoice_issue_receipt_and_trial_balance_restarts(self):
        issued = self._invoice()
        self.assertEqual(issued["result"]["total"], 1000)
        self.assertEqual(issued["view"]["accounts"]["1200"]["normalBalance"], 1000)
        self.assertEqual(issued["view"]["parties"]["client-1"]["receivable"], 1000)
        self.assertEqual(issued["view"]["invoices"]["inv-1"]["status"], "issued")
        deposited = self.cmd(
            "receipt.record", receiptId="receipt-1", partyId="client-1",
            accountId="1010", postingDate=DAY, allocations=[
                {"invoiceId": "inv-1", "amount": 300}])
        self.assertEqual(deposited["view"]["parties"]["client-1"]["receivable"], 700)
        self.assertEqual(deposited["view"]["accounts"]["1010"]["normalBalance"], 300)
        reopened = StandaloneAccountingStore(self.path)
        self.assertEqual(reopened.read(actor="root", accounts=USERS), self.read())
        self.assertEqual(len(reopened.read(actor="root", accounts=USERS)[
            "view"]["journals"]), 2)

    def test_supplier_bill_payment_deposit_and_partial_allocation(self):
        issued = self._bill()
        self.assertEqual(issued["view"]["parties"]["supplier-1"]["payable"], 400)
        self.assertEqual(issued["view"]["accounts"]["2000"]["normalBalance"], 400)
        self.cmd("funds.deposit", accountId="1010", amount=500,
                 postingDate=DAY, note="Synthetic capital")
        paid = self.cmd(
            "payment.record", paymentId="payment-1", partyId="supplier-1",
            accountId="1010", postingDate=DAY,
            allocations=[{"billId": "bill-1", "amount": 250}])
        self.assertEqual(paid["view"]["parties"]["supplier-1"]["payable"], 150)
        self.assertEqual(paid["view"]["accounts"]["1010"]["normalBalance"], 250)
        self.assertEqual(paid["view"]["bills"]["bill-1"]["allocated"], 250)

    def test_other_core_operations_stockless_item_transfer_manual_and_close(self):
        opened = self.cmd("account.create", accountId="1011", name="Second bank",
                          kind="asset", liquid=True)
        self.assertEqual(opened["view"]["accounts"]["1011"]["kind"], "asset")
        self.cmd("item.create", itemId="sku-1", sku="PACK-1", name="Packaging",
                 kind="goods", unit="piece")
        self.cmd("item.update", itemId="sku-1", name="Printed packaging",
                 active=False)
        self.assertFalse(self.read()["view"]["items"]["sku-1"]["active"])
        self.cmd("funds.deposit", accountId="1010", amount=500,
                 postingDate=DAY, note="Opening capital")
        self.cmd("funds.transfer", fromAccountId="1010", toAccountId="1011",
                 amount=200, postingDate=DAY, note="Move bank balance")
        self.assertEqual(self.read()["view"]["accounts"]["1011"]["normalBalance"], 200)
        manual = self.cmd("journal.manual", postingDate=DAY, note="Office supply paid",
                          lines=[
                              {"accountId": "5000", "debit": 50, "credit": 0},
                              {"accountId": "1011", "debit": 0, "credit": 50}])
        self.assertEqual(manual["view"]["accounts"]["1011"]["normalBalance"], 150)
        reversed_result = self.cmd(
            "journal.reverse", journalId=manual["result"]["journalId"],
            postingDate=DAY, reason="Document reversed")
        self.assertEqual(reversed_result["view"]["accounts"]["1011"]["normalBalance"], 200)
        self.cmd("period.close", throughDate="2026-10-21")
        before = self.read()
        with self.assertRaisesRegex(ValueError, "closed"):
            self.cmd("funds.deposit", accountId="1010", amount=10,
                     postingDate="2026-10-21", note="Rejected old transaction")
        self.assertEqual(self.read(), before)

    def test_idempotent_retry_no_revision_and_changed_payload_conflict(self):
        original = {"type": "party.register", "eventId": "same-1",
                    "partyId": "company", "name": "One", "kind": "customer"}
        first = self.store.command(original, actor="root", accounts=USERS,
                                   expected_revision=0, now=NOW)
        self.assertEqual(first["revision"], 1)
        repeat = self.store.command(original, actor="root", accounts=USERS,
                                    expected_revision=1,
                                    now="2026-10-22T11:01:00Z")
        self.assertEqual(first, repeat)
        with self.assertRaisesRegex(ValueError, "reused"):
            self.store.command({**original, "name": "Changed"},
                               actor="root", accounts=USERS,
                               expected_revision=1, now=NOW)
        with self.assertRaisesRegex(ValueError, "reused"):
            self.store.command(original, actor="editor", accounts=USERS,
                               expected_revision=1, now=NOW)
        with self.assertRaises(AccountingRevisionConflict):
            self.store.command(original, actor="root", accounts=USERS,
                               expected_revision=0, now=NOW)
        self.assertEqual(self.read()["revision"], 1)

    def test_read_roles_and_command_roles_and_client_supplied_proof(self):
        with self.assertRaises(PermissionError):
            self.read(actor="viewer")
        with self.assertRaises(PermissionError):
            self.read(actor="unknown")
        self.assertEqual(self.read(actor="auditor")["revision"], 0)
        with self.assertRaises(PermissionError):
            self.cmd("party.register", actor="viewer",
                     event_id="forbidden", partyId="p", name="Name",
                     kind="customer")
        with self.assertRaises(PermissionError):
            self.cmd("party.register", actor="not-authenticated",
                     event_id="forbidden2", partyId="p", name="Name",
                     kind="customer")
        self.cmd("party.register", actor="editor", partyId="p",
                 name="Name", kind="customer")
        with self.assertRaises(PermissionError):
            self.cmd("period.close", actor="editor", throughDate=DAY,
                     event_id="editor-close")
        for field, value in (("actor", "root"), ("proof", "trusted"),
                             ("role", "admin"), ("companyId", "xyz")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.store.command(
                    {"type": "party.register", "eventId": "spoof-" + field,
                     "partyId": "p-" + field, "name": "Bad", "kind": "customer",
                     field: value}, actor="root", accounts=USERS,
                    expected_revision=self.read()["revision"], now=NOW)
        self.assertEqual(self.read()["revision"], 1)

    def test_negative_money_and_invalid_dates_preserve_snapshot(self):
        self._invoice()
        before = self.read()
        with self.assertRaises((ValueError, PermissionError)):
            self.cmd("receipt.record", event_id="too-big", receiptId="r1",
                     partyId="client-1", accountId="1010", postingDate=DAY,
                     allocations=[{"invoiceId": "inv-1", "amount": 1001}])
        with self.assertRaises(ValueError):
            self.cmd("funds.deposit", event_id="float", accountId="1010",
                     amount=1.5, postingDate=DAY, note="Bad")
        with self.assertRaises(ValueError):
            self.cmd("funds.deposit", event_id="future", accountId="1010",
                     amount=100, postingDate="2026-10-25", note="Bad date")
        self.assertEqual(self.read(), before)

    def test_two_database_instances_same_revision_one_wins(self):
        other = StandaloneAccountingStore(self.path)
        def attempt(i):
            command = {"type": "party.register", "eventId": f"parallel-{i}",
                       "partyId": f"party-{i}", "name": f"Party {i}",
                       "kind": "customer"}
            try:
                return ("ok", other.command(command, actor="root",
                                             accounts=USERS,
                                             expected_revision=0, now=NOW))
            except AccountingRevisionConflict:
                return ("conflict", None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (1, 2)))
        self.assertEqual(sorted(value[0] for value in results), ["conflict", "ok"])
        self.assertEqual(self.read()["revision"], 1)
        self.assertEqual(len(self.read()["view"]["parties"]), 1)

    def test_injected_failure_after_write_rolls_back_sql_and_head(self):
        before = self.read()
        original = StandaloneAccountingStore._write
        def simulated_failure(connection, expected, revision, raw):
            original(connection, expected, revision, raw)
            raise OSError("simulated failure after writing SQL row before COMMIT")
        with patch.object(StandaloneAccountingStore, "_write",
                          staticmethod(simulated_failure)):
            with self.assertRaisesRegex(OSError, "simulated failure"):
                self._customer()
        self.assertEqual(self.read(), before)
        with closing(sqlite3.connect(str(self.path))) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM standalone_accounting").fetchone()[0], 0)
        self._customer()
        self.assertEqual(self.read()["revision"], 1)

    def test_existing_history_survives_second_revision_write_failure(self):
        self._customer()
        before = self.read()
        original = StandaloneAccountingStore._write

        def simulated_failure(connection, expected, revision, raw):
            original(connection, expected, revision, raw)
            raise OSError("failure updating nonempty history")

        with patch.object(StandaloneAccountingStore, "_write",
                          staticmethod(simulated_failure)):
            with self.assertRaisesRegex(OSError, "nonempty history"):
                self.cmd("party.register", partyId="supplier", name="Vendor",
                         kind="vendor")
        self.assertEqual(self.read(), before)
        self.assertEqual(StandaloneAccountingStore(self.path).read(
            actor="root", accounts=USERS), before)

    def test_corrupt_checksum_detected_on_read_and_command_without_overwrite(self):
        self._customer()
        self._tamper(lambda state: {
            **state, "events": [*state["events"][:-1], {
                **state["events"][-1], "actor": "ghost"}]})
        for action in (
            lambda: self.read(),
            lambda: self.cmd("party.register", event_id="next",
                             partyId="other", name="Other", kind="customer"),
        ):
            with self.assertRaises(AccountingIntegrityError):
                action()
        with closing(sqlite3.connect(str(self.path))) as connection:
            self.assertEqual(connection.execute(
                "SELECT revision FROM standalone_accounting").fetchone()[0], 1)

    def test_corrupt_event_replay_detected_even_with_recomputed_sha256(self):
        self._customer()
        self._tamper(lambda state: {
            **state, "events": [*state["events"][:-1], {
                **state["events"][-1],
                "result": {"changed": "fraud"}}]},
            recompute_digest=True)
        with self.assertRaises(AccountingIntegrityError):
            self.read()
        with self.assertRaises(AccountingIntegrityError):
            self.cmd("party.register", event_id="new", partyId="x",
                     name="X", kind="customer")

    def test_state_size_and_event_count_limits_fail_closed(self):
        with patch.object(module, "MAX_STATE_BYTES", 200):
            with self.assertRaisesRegex(ValueError, "size"):
                self._customer()
            self.assertEqual(self.read()["revision"], 0)
        with patch.object(module, "MAX_EVENT_COUNT", 0):
            with self.assertRaisesRegex(ValueError, "bounded"):
                self._customer()
            self.assertEqual(self.read()["revision"], 0)

    def test_requires_valid_revision_and_timestamps(self):
        for value in (-1, True, 1.0, "0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.command(
                    {"type": "party.register", "eventId": "first",
                     "partyId": "p", "name": "Name", "kind": "customer"},
                    actor="root", accounts=USERS,
                    expected_revision=value, now=NOW)
        with self.assertRaises(ValueError):
            self.cmd("party.register", event_id="bad-time", now="2026-10-22",
                     partyId="p", name="Name", kind="customer")
        self.assertEqual(self.read()["revision"], 0)

    def test_no_implicit_migration_into_occupied_database(self):
        foreign = self.root / "existing.sqlite3"
        with closing(sqlite3.connect(str(foreign))) as connection:
            connection.execute("CREATE TABLE task_manager(id INTEGER)")
        with self.assertRaises(StandaloneAccountingError):
            StandaloneAccountingStore(foreign)
        with closing(sqlite3.connect(str(foreign))) as connection:
            self.assertEqual({x[0] for x in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")},
                {"task_manager"})


if __name__ == "__main__":
    unittest.main()
