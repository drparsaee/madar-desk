"""Strict manual journal and internal bank/cash transfers, only synthetic data."""
from copy import deepcopy
import unittest

from accounting_core import accounting_view, apply_accounting_command, empty_accounting_state
from accounting_service import apply_madar_accounting
from finance import empty_finance_state, validate_finance_state

USERS = {"admin": {"username": "admin", "role": "admin"}}
NOW = "2026-10-21T18:00:00+03:30"
DAY = "2026-10-21"


class ManualJournalBankTests(unittest.TestCase):
    def setUp(self):
        self.finance = empty_finance_state()
        self.counter = 0

    def apply(self, command):
        out = apply_madar_accounting(self.finance, command, actor="admin",
                                     accounts=USERS, cards=[], projects=[], now=NOW)
        self.finance = out["state"]
        return out

    def command(self, typ, **fields):
        self.counter += 1
        return self.apply({"type": typ, "eventId": "e" + str(self.counter), **fields})

    def ledger(self):
        return accounting_view(self.finance.get("accounting", empty_accounting_state()),
                               actor="admin", accounts=USERS)

    def test_internal_funds_transfer_and_reversal(self):
        self.command("funds.deposit", accountId="1010", amount=1000,
                     postingDate=DAY, note="Owner funds")
        movement = self.command("funds.transfer", fromAccountId="1010",
                                toAccountId="1000", amount=300,
                                postingDate=DAY, note="Bank to cash")
        self.assertEqual(self.ledger()["accounts"]["1010"]["normalBalance"], 700)
        self.assertEqual(self.ledger()["accounts"]["1000"]["normalBalance"], 300)
        self.assertEqual(self.ledger()["accounts"]["3000"]["normalBalance"], 1000)
        self.command("journal.reverse", journalId=movement["result"]["journalId"],
                     postingDate=DAY, reason="Transfer reversed")
        self.assertEqual(self.ledger()["accounts"]["1010"]["normalBalance"], 1000)
        self.assertEqual(self.ledger()["accounts"]["1000"]["normalBalance"], 0)
        self.assertTrue(validate_finance_state(self.finance))

    def test_transfer_refuses_overdraft_self_and_zero(self):
        self.command("funds.deposit", accountId="1010", amount=100,
                     postingDate=DAY, note="Own funds")
        for account, amount in (("1000", 101), ("1010", 1), ("1000", 0)):
            before = deepcopy(self.finance)
            with self.subTest(account=account, amount=amount), self.assertRaises(ValueError):
                self.command("funds.transfer", fromAccountId="1010",
                             toAccountId=account, amount=amount,
                             postingDate=DAY, note="Invalid")
            self.assertEqual(before, self.finance)

    def test_manual_entry_balanced_and_reversible(self):
        entry = self.command("journal.manual", postingDate=DAY, note="Recognized service accrual",
                             lines=[{"accountId": "5000", "debit": 100, "credit": 0},
                                    {"accountId": "2200", "debit": 0, "credit": 100}])
        self.assertEqual(self.ledger()["accounts"]["5000"]["normalBalance"], 100)
        self.assertEqual(self.ledger()["accounts"]["2200"]["normalBalance"], 100)
        self.command("journal.reverse", journalId=entry["result"]["journalId"],
                     postingDate=DAY, reason="Correction")
        self.assertEqual(self.ledger()["accounts"]["5000"]["normalBalance"], 0)
        self.assertTrue(validate_finance_state(self.finance))

    def test_manual_entry_cannot_bypass_named_party_or_unbalance(self):
        for lines in (
            [{"accountId": "1200", "debit": 10, "credit": 0},
             {"accountId": "4000", "debit": 0, "credit": 10}],
            [{"accountId": "5000", "debit": 10, "credit": 0},
             {"accountId": "2000", "debit": 0, "credit": 10}],
            [{"accountId": "5000", "debit": 10, "credit": 0},
             {"accountId": "2200", "debit": 0, "credit": 9}],
            [{"accountId": "5000", "debit": 10, "credit": 0},
             {"accountId": "2200", "debit": 10, "credit": 0}],
        ):
            before = deepcopy(self.finance)
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                self.command("journal.manual", postingDate=DAY, note="Invalid", lines=lines)
            self.assertEqual(before, self.finance)


if __name__ == "__main__":
    unittest.main()
