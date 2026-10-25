"""No commercial data; synthetic gates for guarded non-posting financial plan."""
from copy import deepcopy
import unittest

from parsian_financial_preflight import build_financial_plan
from parsian_quarantine_stage import QuarantineError
from tests.test_parsian_quarantine_stage import fixture


def date_map():
    return {
        "schemaVersion": 1,
        "sourceClass": "ATTACHED_LIVE_SQL_READ_ONLY_NOT_BAK_SNAPSHOT",
        "calendar": "System.Globalization.PersianCalendar",
        "dates": {"1405/08/02": "2026-10-24"},
    }


class FinancialMigrationPreflightTests(unittest.TestCase):
    def source(self):
        return fixture("a" * 64)

    def test_balanced_financial_preview_never_allows_posting(self):
        detail, summary = build_financial_plan(self.source(), date_map())
        self.assertEqual(summary["sourceDocumentGroups"], 1)
        self.assertEqual(summary["sourceJournalRows"], 2)
        self.assertEqual(summary["distinctReferencedAccountPaths"], 1)
        self.assertEqual(summary["sourceJalaliDatesMapped"], 1)
        self.assertEqual(summary["unbalancedDocuments"], 0)
        self.assertFalse(summary["readyToPostToMadarTrial"])
        self.assertFalse(detail["financialPostingAuthorized"])
        self.assertEqual(detail["sourceCurrencyUnit"],
                         "UNVERIFIED_NO_RIAL_OR_TOMAN_ASSUMPTION")
        self.assertEqual(detail["journalGroups"][0]["postingDateISO"],
                         "2026-10-24")
        self.assertEqual(detail["journalGroups"][0]["sourceDebitTotal"], 500)
        self.assertEqual(detail["journalGroups"][0]["sourceCreditTotal"], 500)
        self.assertEqual(detail["journalGroups"][0]["rows"][0][
            "sourceAccountPath"], [11, 4, 7])

    def test_unbalanced_source_fails_not_merely_warns(self):
        source = self.source()
        source["tables"]["tbl_Document"][1]["Bes"] = 499
        with self.assertRaisesRegex(QuarantineError, "strict financial"):
            build_financial_plan(source, date_map())

    def test_missing_or_wrong_calendar_mapping_fails(self):
        for dates in (
            {},
            {"1405/08/01": "2026-10-23"},
            {"1405/08/02": "2026-99-99"},
        ):
            proof = date_map()
            proof["dates"] = dates
            with self.assertRaises(QuarantineError):
                build_financial_plan(self.source(), proof)
        proof = date_map()
        proof["calendar"] = "untrusted-converter"
        with self.assertRaises(QuarantineError):
            build_financial_plan(self.source(), proof)

    def test_unknown_account_code_refused(self):
        source = self.source()
        source["tables"]["tbl_Document"][0]["MoeenCode"] = 99
        with self.assertRaisesRegex(QuarantineError, "unresolved account"):
            build_financial_plan(source, date_map())

    def test_missing_account_group_detected_and_blocks_even_balanced(self):
        source = self.source()
        source["tables"]["tbl_Kol"][0]["GroupCode"] = 999
        detail, summary = build_financial_plan(source, date_map())
        self.assertEqual(summary["kolGroupEntriesMissingReference"], 1)
        self.assertIn("some_kol_groups_have_no_matching_group_reference",
                      summary["blockingReasons"])
        self.assertFalse(detail["financialPostingAuthorized"])

    def test_ambiguous_money_never_coerced(self):
        for amount in (True, -1, 5.55, "100", 10**16):
            source = self.source()
            source["tables"]["tbl_Document"][0]["Bed"] = amount
            with self.assertRaises((QuarantineError, ValueError), msg=str(amount)):
                build_financial_plan(source, date_map())

    def test_factor_without_journal_stays_explicitly_blocked(self):
        source = self.source()
        source["tables"]["tbl_Factor"] = [{
            "ID": 5, "Factor_Num": 10, "Factor_Date": "1405/08/02",
            "TitleCode": 2, "I/O": 0, "FactorKind": 1,
            "Sanad_Num": 999, "GoodsCode": 12.0, "Tedad": 1,
            "Price": 500, "Discont": 0,
        }]
        _, summary = build_financial_plan(source, date_map())
        self.assertEqual(summary["factorRowsWithoutMatchedJournal"], 1)
        self.assertIn("some_factor_rows_have_no_matching_journal_number",
                      summary["blockingReasons"])


if __name__ == "__main__":
    unittest.main()
