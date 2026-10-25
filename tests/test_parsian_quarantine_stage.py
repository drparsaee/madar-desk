"""Synthetic-only quarantine tests. No live Parsian/Madar data are opened."""
from copy import deepcopy
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from parsian_quarantine_stage import (
    QuarantineError, create_quarantine, profile_export,
)


def fixture(digest):
    return {
        "schemaVersion": 1,
        "sourceType": "ATTACHED_LIVE_SQL_READ_ONLY_NOT_BAK_SNAPSHOT",
        "backupCopySha256": digest,
        "extractedAtUtc": "2026-10-24T12:00:00Z",
        "tables": {
            "tbl_ACCGroup": [{"Code": 1, "CName": "Group"}],
            "tbl_Kol": [{"Code": 11, "CName": "Asset", "GroupCode": 1,
                         "iType": 0}],
            "tbl_Moeen": [{"KolCode": 11, "Code": 4, "CName": "Sub",
                           "HaveChild": True}],
            "tbl_Tafsili": [{"KolCode": 11, "MoeenCode": 4, "Code": 7,
                             "CName": "Detail"}],
            "tbl_Document": [
                {"ID": 1, "Sanad_Num": 9, "SanadDate": "1405/08/02",
                 "KolCode": 11, "MoeenCode": 4, "TafsiliCode": 7,
                 "Bed": 500.0, "Bes": 0.0, "IsNote": False},
                {"ID": 2, "Sanad_Num": 9, "SanadDate": "1405/08/02",
                 "KolCode": 11, "MoeenCode": 4, "TafsiliCode": 7,
                 "Bed": 0.0, "Bes": 500.0, "IsNote": False},
            ],
            "tbl_Factor": [],
            "tbl_Goods": [],
        },
    }


class QuarantineTests(unittest.TestCase):
    def test_realistic_synthetic_record_count_and_balance_without_posting(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            backup = root/"source.bak"
            backup.write_bytes(b"QA_BACKUP_IS_NOT_REAL")
            export = fixture(hashlib.sha256(backup.read_bytes()).hexdigest())
            staged = root/"input.json"
            staged.write_text(json.dumps(export), encoding="utf-8")
            output = root/"source-stage.sqlite3"
            report = create_quarantine(staged, output, backup_copy=backup)
            self.assertEqual(report["documentGroups"], 1)
            self.assertEqual(report["unbalancedDocumentGroups"], 0)
            self.assertFalse(report["financialPostingAllowed"])
            with closing(sqlite3.connect(output)) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM raw_source_rows").fetchone()[0], 6)
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],
                                 "ok")
                self.assertEqual(conn.execute(
                    "SELECT value FROM metadata WHERE key='financial_posting_allowed'"
                ).fetchone()[0], "false")
            self.assertEqual(backup.read_bytes(), b"QA_BACKUP_IS_NOT_REAL")
            with self.assertRaises(QuarantineError):
                create_quarantine(staged, output, backup_copy=backup)

    def test_missing_table_and_duplicate_id_fail(self):
        base = fixture("a"*64)
        item = deepcopy(base)
        del item["tables"]["tbl_Factor"]
        with self.assertRaisesRegex(QuarantineError, "Incomplete"):
            profile_export(item)
        item = deepcopy(base)
        item["tables"]["tbl_Document"][1]["ID"] = 1
        with self.assertRaisesRegex(QuarantineError, "Duplicate"):
            profile_export(item)

    def test_unbalanced_journal_is_detected_and_never_authorized(self):
        item = fixture("a"*64)
        item["tables"]["tbl_Document"][1]["Bes"] = 400.0
        out = profile_export(item)
        self.assertEqual(out["unbalancedDocumentGroups"], 1)
        self.assertFalse(out["financialPostingAllowed"])

    def test_ambiguous_or_fractional_money_rejected(self):
        for bad in (0.15, "NaN", -1, 1e18, True, None):
            item = fixture("a"*64)
            item["tables"]["tbl_Document"][0]["Bed"] = bad
            with self.assertRaises((QuarantineError, ValueError, TypeError),
                                   msg=str(bad)):
                profile_export(item)

    def test_invalid_jalali_date_and_missing_flag_rejected(self):
        for date in ("2026-10-24", "1405/13/01", "1405/07/32", "", None):
            item = fixture("a"*64)
            item["tables"]["tbl_Document"][0]["SanadDate"] = date
            with self.assertRaises(QuarantineError):
                profile_export(item)
        item = fixture("a"*64)
        item["tables"]["tbl_Document"][0]["IsNote"] = 0
        with self.assertRaises(QuarantineError):
            profile_export(item)

    def test_mismatch_backup_hash_refuses_and_does_not_create_ledger(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            backup = root/"source.bak"
            backup.write_bytes(b"QA_BACKUP_IS_NOT_REAL")
            staged = root/"input.json"
            staged.write_text(json.dumps(fixture("b"*64)), encoding="utf-8")
            dest = root/"quarantine.sqlite3"
            with self.assertRaisesRegex(QuarantineError, "Backup copy"):
                create_quarantine(staged, dest, backup_copy=backup)
            self.assertFalse(dest.exists())
            self.assertFalse((root/"standalone-accounting.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
