"""No real data: historical Parsian debtor collection must not fake a sale."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from accounting_reporting import ledger_reports
from standalone_accounting import StandaloneAccountingStore

ACTOR = "qa"
PEOPLE = {ACTOR: {"username": ACTOR, "role": "admin"}}
NOW = "2026-10-24T12:00:00Z"


class HistoricCollectionTests(unittest.TestCase):
    def test_manual_gl_collection_reduces_legacy_debtor_and_increases_bank(self):
        with TemporaryDirectory() as tmp:
            book = StandaloneAccountingStore(
                Path(tmp)/"standalone-accounting.sqlite3", default_currency="RIAL")
            events = [
                {"type":"account.create","eventId":"a1",
                 "accountId":"ps.12.2.1","name":"Old customer",
                 "kind":"asset","liquid":False},
                {"type":"account.create","eventId":"a2",
                 "accountId":"ps.11.1.0","name":"Old bank",
                 "kind":"asset","liquid":False},
                {"type":"journal.manual","eventId":"ps.sanad.1",
                 "postingDate":"2026-10-24","note":"Imported old sale",
                 "lines":[
                     {"accountId":"ps.12.2.1","debit":500,"credit":0},
                     {"accountId":"4000","debit":0,"credit":500}]},
                {"type":"journal.manual","eventId":"ps.collect.1",
                 "postingDate":"2026-10-24","note":"Historical GL collection",
                 "lines":[
                     {"accountId":"ps.11.1.0","debit":200,"credit":0},
                     {"accountId":"ps.12.2.1","debit":0,"credit":200}]},
            ]
            for revision, event in enumerate(events):
                book.command(event,actor=ACTOR,accounts=PEOPLE,
                             expected_revision=revision,now=NOW)
            reopened = StandaloneAccountingStore(
                book.path, default_currency="TOMAN").read(
                    actor=ACTOR,accounts=PEOPLE)
            view = reopened["view"]
            self.assertEqual(view["currency"],"RIAL")
            self.assertEqual(view["accounts"]["ps.12.2.1"]["debitMinusCredit"],300)
            self.assertEqual(view["accounts"]["ps.11.1.0"]["debitMinusCredit"],200)
            self.assertEqual(len(view["journals"]),2)
            self.assertEqual(len(view["invoices"]),0)
            self.assertEqual(len(view["parties"]),0)
            reports=ledger_reports(view)
            self.assertEqual(reports["trialBalance"]["totalDebit"],
                             reports["trialBalance"]["totalCredit"])
            self.assertEqual(reports["profitLoss"]["revenue"],500)
            self.assertEqual(reports["journalCountThroughDate"],2)


if __name__=="__main__":
    unittest.main()
