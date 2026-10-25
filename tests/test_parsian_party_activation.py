"""Synthetic GL historical customer activation and future invoice smoke."""
from pathlib import Path
import hashlib
import json
from tempfile import TemporaryDirectory
import unittest

from parsian_full_archive_sqlite import create_archive
from parsian_party_activation import register_historic_customers, PartyMigrationError
from standalone_accounting import StandaloneAccountingStore

ACTOR="legacy-party-registration"
USERS={ACTOR:{"username":ACTOR,"role":"admin"}}
NOW="2026-10-24T12:00:00Z"


def setup_fixture(tmp):
    root=Path(tmp)/"migration-experiment-test"
    root.mkdir()
    trial = root/"older"
    trial.mkdir()
    book=trial/"standalone-accounting.sqlite3"
    store=StandaloneAccountingStore(book,default_currency="RIAL")
    cmds=[
        {"type":"account.create","eventId":"ps.account.1","accountId":"ps.12.2.1",
         "name":"Customer GL", "kind":"asset","liquid":False},
        {"type":"journal.manual","eventId":"ps.sanad.42",
         "postingDate":"2026-10-24","note":"Synthetic Parsian GL",
         "lines":[{"accountId":"ps.12.2.1","debit":500,"credit":0},
                  {"accountId":"ps.12.2.1","debit":0,"credit":500}]},
    ]
    for rev, cmd in enumerate(cmds):
        store.command(cmd,actor=ACTOR,accounts=USERS,
                      expected_revision=rev,now=NOW)
    source=root/"captured.json"
    source.write_text(json.dumps({
        "sourceType":"ATTACHED_LIVE_SQL_READ_ONLY_NOT_BAK_SNAPSHOT",
        "tables":{"tbl_Tafsili":[
            {"KolCode":12,"MoeenCode":2,"Code":1,"CName":"Test Customer"},
            {"KolCode":12,"MoeenCode":2,"Code":2,"CName":"Test Customer Two"},
        ]}}),encoding="utf8")
    typed = trial/"typed.jsonl"
    typed.write_text(json.dumps({"table":"tbl_Tafsili","fields":{
        "Code":{"t":"integer","text":"1"},
        "CName":{"t":"text","value":"Test Customer"}}})+"\n",encoding="utf8")
    meta = trial/"parsian-archive-manifest.json"
    meta.write_text(json.dumps({
        "source":"ATTACHED_LIVE_SQL_NOT_RESTORED_BACKUP",
        "snapshotMatchesBackup":False,
        "sourceCurrency":"RIAL_OWNER_CONFIRMED",
        "vendorTableCount":1,"vendorRowCount":1,
        "tableCounts":{"tbl_Tafsili":1},
        "archiveSha256":hashlib.sha256(typed.read_bytes()).hexdigest(),
    }),encoding="utf8")
    create_archive(typed,meta,trial/"parsian-all-base-tables-PRIVATE.sqlite3")
    return root,book,source


class HistoricPartyActivationTests(unittest.TestCase):
    def test_registered_people_without_double_posting_and_new_invoice(self):
        with TemporaryDirectory() as temp:
            root,book,source=setup_fixture(temp)
            dest=root/"parsian-operational-customer-test-disposable"
            report=register_historic_customers(book,source,dest)
            self.assertEqual(report["customerIdentityCount"],2)
            self.assertEqual(report["oldGLDocumentsRetained"],1)
            self.assertFalse(report["historicGLReposted"])
            store=StandaloneAccountingStore(
                dest/"standalone-accounting.sqlite3",default_currency="TOMAN")
            view=store.read(actor=ACTOR,accounts=USERS)
            self.assertEqual(view["view"]["currency"],"RIAL")
            self.assertEqual(view["revision"],4)
            self.assertEqual(len(view["view"]["journals"]),1)
            self.assertEqual(len(view["view"]["parties"]),2)
            self.assertEqual(view["view"]["parties"]["ps.party.12.2.1"]["receivable"],0)
            # New operational invoice is now possible for a migrated customer.
            id0=view["revision"]
            new_invoices=[
                {"type":"invoice.create","eventId":"new.inv.1","invoiceId":"invoice2",
                 "partyId":"ps.party.12.2.1","documentDate":"2026-10-24",
                 "lines":[{"description":"New job", "quantity":1,"unitPrice":100,
                           "accountId":"4000"}]},
                {"type":"invoice.approve","eventId":"new.approve.1","invoiceId":"invoice2"},
                {"type":"invoice.issue","eventId":"new.issue.1","invoiceId":"invoice2",
                 "postingDate":"2026-10-24"},
            ]
            for cmd in new_invoices:
                res=store.command(cmd,actor=ACTOR,accounts=USERS,
                                  expected_revision=id0,now=NOW)
                id0=res["revision"]
            final=store.read(actor=ACTOR,accounts=USERS)
            self.assertEqual(len(final["view"]["journals"]),2)
            self.assertEqual(final["view"]["parties"]["ps.party.12.2.1"]["receivable"],100)
            self.assertEqual(final["view"]["invoices"]["invoice2"]["status"],"issued")
            paid=store.command(
                {"type":"receipt.record","eventId":"new.receipt.1",
                 "receiptId":"receipt2","partyId":"ps.party.12.2.1",
                 "accountId":"1010","postingDate":"2026-10-24",
                 "allocations":[{"invoiceId":"invoice2","amount":100}]},
                actor=ACTOR,accounts=USERS,
                expected_revision=id0,now=NOW)
            self.assertEqual(len(paid["view"]["journals"]),3)
            self.assertEqual(
                paid["view"]["parties"]["ps.party.12.2.1"]["receivable"],0)
            self.assertEqual(
                paid["view"]["invoices"]["invoice2"]["allocated"],100)
            with self.assertRaises(PartyMigrationError):
                register_historic_customers(book,source,dest)

    def test_reject_untrusted_or_foreign_source_before_publish(self):
        with TemporaryDirectory() as temp:
            root,book,source=setup_fixture(temp)
            obj=json.loads(source.read_text("utf8"))
            obj["sourceType"]="UNSAFE"
            source.write_text(json.dumps(obj),encoding="utf8")
            dest=root/"parsian-operational-customer-test-disposable"
            with self.assertRaisesRegex(PartyMigrationError,"Unexpected"):
                register_historic_customers(book,source,dest)
            self.assertFalse(dest.exists())


if __name__=="__main__":
    unittest.main()
