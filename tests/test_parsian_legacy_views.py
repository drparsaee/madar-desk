"""Typed historic Parsian views never duplicate GL and are desktop-safe."""
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
from contextlib import closing
import json
import sqlite3
import unittest

from parsian_full_archive_sqlite import create_archive
from parsian_legacy_views import legacy_views, HistoricalDataError
from standalone_accounting_desktop import AccountingDesktopAPI


class LegacyViewsTests(unittest.TestCase):
    @staticmethod
    def _data(root):
        data_dir = root/"trial"
        data_dir.mkdir()
        typed = []
        def row(table,fields):
            typed.append({"table":table,"fields":fields})
        def integer(n):
            return {"t":"integer","text":str(n)}
        def string(s):
            return {"t":"text","value":s}
        row("tbl_FactorKind",{
            "Code":integer(1),"CName":string("فاکتور فروش")})
        row("tbl_Factor",{
            "ID":integer(100),"TitleCode":integer(1),
            "I/O":integer(0),"FactorKind":integer(1),
            "Factor_Num":integer(5),"Factor_Date":string("1405/06/01"),
            "Sanad_Num":integer(42)})
        row("tbl_Factor",{
            "ID":integer(101),"TitleCode":integer(1),
            "I/O":integer(0),"FactorKind":integer(1),
            "Factor_Num":integer(5),"Factor_Date":string("1405/06/01"),
            "Sanad_Num":integer(42)})
        row("tbl_Check",{"ID":integer(9)})
        raw_path = root/"original.jsonl"
        raw_path.write_text("".join(json.dumps(x, ensure_ascii=False)+"\n"
                                    for x in typed), encoding="utf-8")
        counts = {"tbl_Factor":2,"tbl_FactorKind":1,"tbl_Check":1,
                  "tbl_Goods":0,"tbl_TopCheck":0,"tbl_Tafsili":0,
                  "tbl_Moeen":0}
        manifest = {
            "source": "ATTACHED_LIVE_SQL_NOT_RESTORED_BACKUP",
            "snapshotMatchesBackup": False,
            "sourceCurrency": "RIAL_OWNER_CONFIRMED",
            "vendorTableCount": len(counts),
            "vendorRowCount": len(typed),
            "tableCounts": counts,
            "archiveSha256":sha256(raw_path.read_bytes()).hexdigest(),
        }
        m = data_dir/"parsian-archive-manifest.json"
        m.write_text(json.dumps(manifest,ensure_ascii=False),encoding="utf8")
        db = data_dir/"parsian-all-base-tables-PRIVATE.sqlite3"
        create_archive(raw_path,m,db)
        return data_dir, db, m

    def test_historic_invoices_are_archived_not_posted_and_debtors_real(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            book,archive,manifest = self._data(root)
            view = {
                "currency":"RIAL",
                "accounts":{
                    "ps.12.2.1":{"name":"مشتری الف",
                                 "debitMinusCredit":10000},
                    "ps.12.2.2":{"name":"مشتری ب",
                                 "debitMinusCredit":0},
                },
            }
            old = legacy_views(view, archive_path=archive,
                               manifest_path=manifest)
            self.assertEqual(old["positiveDebtorCount"],1)
            self.assertEqual(old["positiveDebtorTotal"],10000)
            self.assertEqual(old["historicalInvoiceGroups"],1)
            self.assertEqual(old["historicalFactorLines"],2)
            self.assertEqual(old["historicalDocuments"][0]["number"],"5")
            self.assertEqual(old["historicalDocuments"][0]["lineCount"],2)
            self.assertFalse(old["historicalDocuments"][0]["priceAndStockConverted"])
            self.assertEqual(old["historicalCheques"],1)
            self.assertTrue(old["notOperationalInvoicesOrPayments"])
            self.assertEqual(old["archiveRows"],4)

    def test_empty_book_without_sidecar_behaves_as_normal(self):
        with TemporaryDirectory() as temp:
            data = Path(temp)
            api=AccountingDesktopAPI(data)
            view=api.standaloneAccountingRead()["view"]
            self.assertNotIn("parsianMigration",view)
            self.assertEqual(view["currency"],"RIAL")

    def test_host_exposes_readonly_history_when_sidecar_present(self):
        with TemporaryDirectory() as temp:
            data_dir,_,_=self._data(Path(temp))
            api=AccountingDesktopAPI(data_dir)
            result=api.standaloneAccountingRead()
            historical=result["view"]["parsianMigration"]
            self.assertTrue(historical["readOnlyHistory"])
            self.assertEqual(historical["historicalInvoiceGroups"],1)
            self.assertEqual(result["revision"],0)
            self.assertEqual(len(result["view"]["journals"]),0)

    def test_tamper_in_archived_invoice_is_rejected(self):
        with TemporaryDirectory() as temp:
            data_dir,archive,manifest=self._data(Path(temp))
            with closing(sqlite3.connect(archive)) as db:
                db.execute("UPDATE archived_rows SET typed_raw_json=? "
                           "WHERE source_table='tbl_Factor' AND ordinal=0",
                           (b'{}',))
                db.commit()
            with self.assertRaisesRegex(HistoricalDataError,"checksum"):
                legacy_views({"currency":"RIAL","accounts":{}},
                             archive_path=archive,manifest_path=manifest)

    def test_wrong_currency_or_incomplete_manifest_rejected(self):
        with TemporaryDirectory() as temp:
            data_dir,archive,manifest=self._data(Path(temp))
            with self.assertRaisesRegex(HistoricalDataError,"currency"):
                legacy_views({"currency":"TOMAN","accounts":{}},
                             archive_path=archive,manifest_path=manifest)
            manifest.unlink()
            with self.assertRaisesRegex(HistoricalDataError,"Incomplete"):
                legacy_views({"currency":"RIAL","accounts":{}},
                             archive_path=archive,manifest_path=manifest)


if __name__=="__main__":
    unittest.main()
