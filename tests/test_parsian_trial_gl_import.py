"""Synthetic RIAL general-ledger migration acceptance, isolation, rollback."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from parsian_quarantine_stage import create_quarantine
from parsian_trial_gl_import import (
    stage_trial_gl, TrialMigrationError,
)
from standalone_accounting import StandaloneAccountingStore
from tests.test_parsian_quarantine_stage import fixture
from tests.test_parsian_financial_preflight import date_map


ACTOR = {"trial-importer": {"username": "trial-importer", "role": "admin"}}


def staged_source(root):
    root.mkdir()
    export = fixture("a"*64)
    # Source group 11 is explicitly asset, matching the real chart classification.
    export["tables"]["tbl_ACCGroup"][0]["Code"] = 11
    export["tables"]["tbl_Kol"][0]["GroupCode"] = 11
    srcbak = root/"bak.copy"
    srcbak.write_bytes(b"SYNTHETIC-ONLY-NOT-A-BAK")
    export["backupCopySha256"] = hashlib.sha256(srcbak.read_bytes()).hexdigest()
    src = root/"source.json"
    src.write_text(json.dumps(export), encoding="utf8")
    dates = root/"dates.json"
    dates.write_text(json.dumps(date_map()), encoding="utf8")
    archive = root/"source-quarantine.sqlite3"
    create_quarantine(src, archive, backup_copy=srcbak)
    return src, dates, archive


class TrialGLTests(unittest.TestCase):
    def test_synthetic_general_ledger_replayed_and_reconciled(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)/"migration-experiment-fixture"
            src, dates, archive = staged_source(root)
            dest = root/"parsian-rial-gl-import-disposable"
            summary = stage_trial_gl(
                source_path=src, date_path=dates, quarantine_path=archive,
                destination_dir=dest, confirmed_unit="RIAL")
            self.assertEqual(summary["journalGroupsImported"], 1)
            self.assertEqual(summary["journalLinesImported"], 2)
            self.assertEqual(summary["originalDebitRial"], 500)
            self.assertEqual(summary["importedCreditRial"], 500)
            self.assertTrue(summary["sourceAccountBalancesIdentical"])
            self.assertFalse(summary["safeToReplaceParsian"])
            store = StandaloneAccountingStore(
                dest/"standalone-accounting.sqlite3", default_currency="TOMAN")
            state = store.read(actor="trial-importer", accounts=ACTOR)
            self.assertEqual(state["view"]["currency"], "RIAL")
            self.assertEqual(state["revision"], 2)
            self.assertEqual(len(state["view"]["journals"]), 1)
            self.assertIn("ps.11.4.7", state["view"]["accounts"])
            self.assertEqual(state["view"]["journals"][0]["lines"][0]["debit"], 500)
            with self.assertRaises(TrialMigrationError):
                stage_trial_gl(
                    source_path=src, date_path=dates,
                    quarantine_path=archive,
                    destination_dir=dest, confirmed_unit="RIAL")

    def test_unconfirmed_unit_blocks_entire_new_book(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)/"migration-experiment-fixture"
            src, dates, archive = staged_source(root)
            dest = root/"parsian-rial-gl-import-disposable"
            with self.assertRaisesRegex(TrialMigrationError, "explicit RIAL"):
                stage_trial_gl(
                    source_path=src, date_path=dates, quarantine_path=archive,
                    destination_dir=dest, confirmed_unit="TOMAN")
            self.assertFalse(dest.exists())

    def test_source_tampering_refused_before_any_book_created(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)/"migration-experiment-fixture"
            src, dates, archive = staged_source(root)
            dest = root/"parsian-rial-gl-import-disposable"
            content = json.loads(src.read_text("utf8"))
            content["tables"]["tbl_Document"][0]["Bed"] = 501
            src.write_text(json.dumps(content), encoding="utf8")
            with self.assertRaises(TrialMigrationError):
                stage_trial_gl(
                    source_path=src, date_path=dates,
                    quarantine_path=archive, destination_dir=dest,
                    confirmed_unit="RIAL")
            self.assertFalse(dest.exists())

    def test_uncategorized_source_general_account_fails_closed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)/"migration-experiment-fixture"
            src, dates, archive = staged_source(root)
            with self.assertRaises(TrialMigrationError):
                # Does not permit writing to the working source directory.
                stage_trial_gl(
                    source_path=src, date_path=dates, quarantine_path=archive,
                    destination_dir=root, confirmed_unit="RIAL")


if __name__ == "__main__":
    unittest.main()
