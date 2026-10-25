"""Pure synthetic policy invariants; never opens real finance or APPDATA."""
import dataclasses
import json
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from money_policy import (
    MAX_RIAL, RIAL_PER_TOMAN, CompanyMoneyPolicy, MoneyPolicyError,
    LegacySourceEvidence, assert_posted_document_unchanged,
    format_money, freeze_posted_document, multiply_rial, parse_money_input,
    quote_legacy_toman_migration, require_rial_amount, snapshot_sha256,
    sum_rial_amounts, verify_legacy_migration_quote,
)


class MoneyPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = CompanyMoneyPolicy("co-1")

    def assert_reject(self, callback):
        with self.assertRaises(MoneyPolicyError):
            callback()

    def test_company_rial_canonical_and_display_opt_in(self):
        self.assertEqual(self.policy.accounting_currency, "RIAL")
        self.assertEqual(self.policy.display_unit, "RIAL")
        toman = self.policy.with_display_unit("TOMAN")
        self.assertEqual(toman.display_unit, "TOMAN")
        self.assertEqual(toman.accounting_currency, "RIAL")
        self.assertEqual(self.policy.display_unit, "RIAL")
        self.assert_reject(lambda: CompanyMoneyPolicy("co-1", accounting_currency="TOMAN"))
        self.assert_reject(lambda: CompanyMoneyPolicy("co-1", display_unit="تومان"))
        self.assert_reject(lambda: self.policy.with_display_unit("rial"))
        self.assert_reject(lambda: CompanyMoneyPolicy("bad id"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.policy.display_unit = "TOMAN"

    def test_exact_persian_arabic_ascii_and_grouping(self):
        sample = [
            ("۱۲٬۳۴۵", "TOMAN", 123450),
            ("١٢٬٣٤٥", "TOMAN", 123450),
            ("12,345", "TOMAN", 123450),
            ("12,345", "RIAL", 12345),
            ("۹۹٫۹", "TOMAN", 999),
            ("۹۹.۱", "TOMAN", 991),
            ("٠٫١", "TOMAN", 1),
            ("0.0", "TOMAN", 0),
            (" ۱۰٫۱ ", "TOMAN", 101),
            ("۰", "RIAL", 0),
            ("١٢٣٤", "RIAL", 1234),
            ("0.9", "TOMAN", 9),
        ]
        for text, unit, expected in sample:
            with self.subTest(text=text, unit=unit):
                self.assertEqual(parse_money_input(text, unit), expected)

    def test_reject_ambiguous_or_lossy_money_strings(self):
        bad = [
            ("", "RIAL"), ("12.1", "RIAL"), ("10.01", "TOMAN"),
            ("10.", "TOMAN"), ("10.10", "TOMAN"), (".5", "TOMAN"),
            ("-1", "RIAL"), ("+1", "RIAL"), ("01", "RIAL"),
            ("1,23", "RIAL"), ("1,2345", "RIAL"), ("1,23,456", "RIAL"),
            ("1,,000", "RIAL"), ("1 000", "RIAL"), ("1e3", "TOMAN"),
            ("1_000", "RIAL"), ("NaN", "RIAL"), ("Infinity", "RIAL"),
            ("10٬2", "TOMAN"), ("۱۰٫۲٫۳", "TOMAN"),
            ("10-", "RIAL"), ("--1", "RIAL"), ("0x10", "RIAL"),
            ("10٪", "RIAL"), ("10\n20", "RIAL"),
        ]
        for text, unit in bad:
            with self.subTest(text=text, unit=unit):
                self.assert_reject(lambda: parse_money_input(text, unit))
        for raw in [10, 1.2, None, False, [], {}]:
            self.assert_reject(lambda: parse_money_input(raw, "RIAL"))
        self.assert_reject(lambda: parse_money_input("12", "UNKNOWN"))

    def test_remainder_rial_preserved_as_one_decimal_toman(self):
        values = [1, 2, 9, 10, 11, 101, 109, 111, 1001, 1_000_001]
        for rial in values:
            rendered = format_money(rial, "TOMAN")
            self.assertEqual(parse_money_input(rendered, "TOMAN"), rial)
        self.assertEqual(format_money(101, "TOMAN"), "10.1")
        self.assertEqual(format_money(100, "TOMAN"), "10")
        self.assertEqual(format_money(1, "TOMAN", persian_digits=True), "۰.۱")
        self.assertEqual(format_money(100_005, "TOMAN", persian_digits=True), "۱۰,۰۰۰.۵")

    def test_format_rial_toman_round_trip_on_boundaries(self):
        for rial in [0, 1, 9, 10, 19, 1234, 9_000_000,
                     MAX_RIAL - 1, MAX_RIAL]:
            for unit in ["RIAL", "TOMAN"]:
                for persian in [False, True]:
                    text = format_money(rial, unit, persian_digits=persian)
                    self.assertEqual(parse_money_input(text, unit), rial)
        self.assertEqual(format_money(123, "RIAL", include_unit=True), "123 RIAL")

    def test_negatives_only_when_opted_in_and_sign_not_rounded(self):
        self.assert_reject(lambda: parse_money_input("-۰٫۱", "TOMAN"))
        self.assertEqual(parse_money_input("-۰٫۱", "TOMAN", allow_negative=True), -1)
        self.assertEqual(format_money(-101, "TOMAN"), "-10.1")
        self.assertEqual(format_money(-123456, "RIAL"), "-123,456")
        self.assertEqual(parse_money_input(format_money(-101, "TOMAN"),
                                           "TOMAN", allow_negative=True), -101)
        self.assert_reject(lambda: parse_money_input("-0", "TOMAN", allow_negative=False))
        self.assert_reject(lambda: parse_money_input("-۰٫۰", "TOMAN", allow_negative=True))

    def test_zero_bound_and_bool_are_never_implicitly_accepted(self):
        self.assert_reject(lambda: parse_money_input("0", "RIAL", allow_zero=False))
        self.assert_reject(lambda: parse_money_input("0.0", "TOMAN", allow_zero=False))
        self.assert_reject(lambda: require_rial_amount(True))
        self.assert_reject(lambda: require_rial_amount(False))
        self.assert_reject(lambda: require_rial_amount(1.0))
        self.assert_reject(lambda: require_rial_amount("100"))
        self.assertEqual(require_rial_amount(MAX_RIAL), MAX_RIAL)
        self.assert_reject(lambda: require_rial_amount(MAX_RIAL + 1))

    def test_cap_at_js_safe_integer_and_no_legacy_overflow(self):
        self.assertEqual(MAX_RIAL, 2**53 - 1)
        self.assertEqual(RIAL_PER_TOMAN, 10)
        self.assert_reject(lambda: parse_money_input(str(MAX_RIAL + 1), "RIAL"))
        self.assert_reject(lambda: parse_money_input(
            str(MAX_RIAL // 10 + 1), "TOMAN"))
        self.assertEqual(parse_money_input(
            format_money(MAX_RIAL, "TOMAN"), "TOMAN"), MAX_RIAL)
        self.assert_reject(lambda: CompanyMoneyPolicy("co-1", max_abs_rial=MAX_RIAL + 1))
        self.assert_reject(lambda: CompanyMoneyPolicy("co-1", max_abs_rial=True))
        self.assert_reject(lambda: CompanyMoneyPolicy("co-1", max_abs_rial=0))

    def test_arithmetic_bounds_operands_and_intermediate_totals(self):
        self.assertEqual(sum_rial_amounts([100, -20, 1]), 81)
        self.assertEqual(multiply_rial(101, 3), 303)
        self.assertEqual(multiply_rial(-2, 2), -4)
        self.assert_reject(lambda: sum_rial_amounts([MAX_RIAL, 1]))
        self.assert_reject(lambda: sum_rial_amounts([MAX_RIAL, 1, -1]))
        self.assert_reject(lambda: sum_rial_amounts([1.5]))
        self.assert_reject(lambda: multiply_rial(MAX_RIAL, 2))
        self.assert_reject(lambda: multiply_rial(1, 1.0))
        self.assert_reject(lambda: multiply_rial(1, True))
        self.assert_reject(lambda: multiply_rial(1, 1_000_001))

    def test_posted_document_is_frozen_snapshot_not_live_reference(self):
        original = {"companyId": "co-1", "eventId": "entry-10", "currency": "RIAL",
                    "status": "posted", "amountRial": 101,
                    "lines": [{"accountId": "1000", "debitRial": 101, "creditRial": 0}],
                    "party": {"id": "p1", "name": "Customer"}}
        frozen = freeze_posted_document(original, self.policy)
        assert_posted_document_unchanged(frozen, original, self.policy)
        original["lines"][0]["debitRial"] = 999
        original["party"]["name"] = "Changed"
        self.assertEqual(frozen.document_copy()["lines"][0]["debitRial"], 101)
        self.assertEqual(frozen.document_copy()["party"]["name"], "Customer")
        self.assert_reject(lambda: assert_posted_document_unchanged(
            frozen, original, self.policy))
        clone = frozen.document_copy()
        clone["amountRial"] = 900
        self.assertEqual(frozen.amount_rial, 101)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            frozen.amount_rial = 99

    def test_posted_freeze_blocks_draft_wrong_unit_cross_company_float(self):
        posted = {"companyId": "co-1", "eventId": "e1", "currency": "RIAL",
                  "status": "posted", "amountRial": 100, "memo": "OK"}
        for changed in [
            {"status": "draft"}, {"currency": "TOMAN"},
            {"companyId": "co-2"}, {"amountRial": 100.0},
            {"lineTotalRial": MAX_RIAL + 1},
            {"taxRial": True},
            {"memo": {"ratio": 1.5}}, {"eventId": "bad id"},
        ]:
            self.assert_reject(lambda: freeze_posted_document(
                {**posted, **changed}, self.policy))
        snap = freeze_posted_document(posted, self.policy)
        self.assert_reject(lambda: assert_posted_document_unchanged(
            snap, {**posted, "memo": "Modified"}, self.policy))

    def _legacy(self):
        snapshot = {"invoices": [{"id": "legacy-1", "sale": {"due": 250}}],
                    "cardCosts": {"t1": {"actualDirect": 37}}}
        evidence = LegacySourceEvidence(
            source_id="legacy-finance-v1", declared_unit="TOMAN",
            verified_unit="TOMAN", source_snapshot_sha256=snapshot_sha256(snapshot),
            verifier_id="trusted-admin", verification_reference="approval-1")
        return snapshot, evidence

    def test_legacy_toman_conversion_requires_specific_verified_full_snapshot(self):
        snapshot, evidence = self._legacy()
        quote = quote_legacy_toman_migration(
            snapshot, ("invoices", 0, "sale", "due"), evidence, self.policy)
        self.assertEqual(quote.legacy_toman, 250)
        self.assertEqual(quote.converted_rial, 2500)
        self.assertEqual(quote.company_id, "co-1")
        self.assertEqual(len(quote.quote_sha256), 64)
        verify_legacy_migration_quote(quote, snapshot, evidence, self.policy)
        self.assertEqual(snapshot["invoices"][0]["sale"]["due"], 250)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            quote.converted_rial = 2

    def test_legacy_unit_must_not_be_guessed_or_unverified(self):
        snapshot, evidence = self._legacy()
        for declared, verified in [("RIAL", "RIAL"), ("TOMAN", "RIAL"),
                                   ("RIAL", "TOMAN"), ("UNKNOWN", "TOMAN")]:
            self.assert_reject(lambda: LegacySourceEvidence(
                evidence.source_id, declared, verified,
                evidence.source_snapshot_sha256,
                evidence.verifier_id, evidence.verification_reference))
        self.assert_reject(lambda: quote_legacy_toman_migration(
            snapshot, ("invoices", 0, "sale", "due"),
            None, self.policy))

    def test_legacy_snapshot_changes_are_detected_before_conversion(self):
        snapshot, evidence = self._legacy()
        quote = quote_legacy_toman_migration(
            snapshot, ("cardCosts", "t1", "actualDirect"), evidence, self.policy)
        self.assertEqual(quote.converted_rial, 370)
        snapshot["cardCosts"]["t1"]["actualDirect"] = 38
        self.assert_reject(lambda: quote_legacy_toman_migration(
            snapshot, ("cardCosts", "t1", "actualDirect"), evidence, self.policy))
        self.assert_reject(lambda: verify_legacy_migration_quote(
            quote, snapshot, evidence, self.policy))

    def test_legacy_wrong_field_type_missing_path_and_overflow_fail_closed(self):
        for value in [True, 1.0, "100"]:
            snapshot = {"amount": value}
            if type(value) is float:
                self.assert_reject(lambda: snapshot_sha256(snapshot))
                continue
            evidence = LegacySourceEvidence(
                "legacy-1", "TOMAN", "TOMAN", snapshot_sha256(snapshot),
                "verifier-1", "ref-1")
            self.assert_reject(lambda: quote_legacy_toman_migration(
                snapshot, ("amount",), evidence, self.policy))
        snapshot, evidence = self._legacy()
        self.assert_reject(lambda: quote_legacy_toman_migration(
            snapshot, ("missing",), evidence, self.policy))
        amount_snapshot = {"amount": MAX_RIAL // 10 + 1}
        ev = LegacySourceEvidence("legacy-big", "TOMAN", "TOMAN",
                                  snapshot_sha256(amount_snapshot),
                                  "verifier-1", "ref-1")
        self.assert_reject(lambda: quote_legacy_toman_migration(
            amount_snapshot, ("amount",), ev, self.policy))

    def test_legacy_negative_adjustment_requires_explicit_opt_in(self):
        snapshot = {"adjustment": -17}
        evidence = LegacySourceEvidence("legacy-credit", "TOMAN", "TOMAN",
                                        snapshot_sha256(snapshot), "admin", "ref-1")
        self.assert_reject(lambda: quote_legacy_toman_migration(
            snapshot, ("adjustment",), evidence, self.policy))
        quote = quote_legacy_toman_migration(
            snapshot, ("adjustment",), evidence, self.policy, allow_negative=True)
        self.assertEqual(quote.converted_rial, -170)
        verify_legacy_migration_quote(quote, snapshot, evidence, self.policy)

    def test_verified_quote_detects_tampering_without_committing(self):
        snapshot, evidence = self._legacy()
        quote = quote_legacy_toman_migration(
            snapshot, ("invoices", 0, "sale", "due"), evidence, self.policy)
        tampered = dataclasses.replace(quote, converted_rial=999)
        self.assert_reject(lambda: verify_legacy_migration_quote(
            tampered, snapshot, evidence, self.policy))
        switched = dataclasses.replace(evidence, verification_reference="approval-2")
        self.assert_reject(lambda: verify_legacy_migration_quote(
            quote, snapshot, switched, self.policy))

    def test_snapshot_canonicalization_stable_and_float_disallowed_everywhere(self):
        self.assertEqual(snapshot_sha256({"b": [1, 2], "a": {"z": True}}),
                         snapshot_sha256({"a": {"z": True}, "b": [1, 2]}))
        for bad in [{"x": 1.0}, {"x": [float("nan")]}, {"x": {"y": float("inf")}},
                    {1: "bad key"}]:
            self.assert_reject(lambda: snapshot_sha256(bad))
        self.assertEqual(len(snapshot_sha256({"status": "posted"})), 64)


if __name__ == "__main__":
    unittest.main()
