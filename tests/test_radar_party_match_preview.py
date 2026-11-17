"""Synthetic E4 matching-preview contracts; no Taraz, profiles, or network."""

from __future__ import annotations

from copy import deepcopy
import socket
import unittest
from unittest.mock import patch

from radar_party_match_preview import preview_party_matches


ORG = "test-org-alpha"
SCOPE = {
    "organization_id": ORG,
    "server_scoped": True,
    "party_read_authorized": True,
    "finance_review_authorized": True,
    "visible_fields": ["official_id", "name", "phone", "address"],
}
CUSTOMER = {
    "customer_id": "temporary-7",
    "organization_id": ORG,
    "official_id": "۰۰۱۲۳",
    "official_id_source_verified": True,  # a synthetic source CLAIM, not actual ID verification
    "name": "شرکت آفتاب‌گستر",
    "phone": "۰۹۱۲ ۳۴۵-۶۷۸۹",
    "address": "تهران، خيابان بهار",
}


def candidate(identifier, **fields):
    return {
        "party_id": identifier,
        "organization_id": ORG,
        "read_authorized": True,
        **fields,
    }


class PartyMatchPreviewTests(unittest.TestCase):
    def preview(self, candidates, *, customer=None, scope=None):
        return preview_party_matches(
            CUSTOMER if customer is None else customer,
            candidates, scope=SCOPE if scope is None else scope,
        )

    def test_all_supplied_visible_candidates_and_original_order_even_without_overlap(self):
        rows = [
            candidate("party-exact", official_id="00123", official_id_source_verified=True,
                      name="شركت آفتاب گستر", phone="0912 (345) 6789",
                      address="تهران، خیابان بهار"),
            candidate("party-different-id", official_id="۰۰۹۹۹",
                      official_id_source_verified=True,
                      name="شرکت آفتاب گستر", phone="0912-3456789"),
            candidate("party-name-overlap", name="آفتاب گستر تجارت",
                      phone="02111111111", address="اصفهان"),
            candidate("party-unrelated", name="کالای آزمایشی دیگر", phone="3333",
                      address="شیراز"),
        ]
        result = self.preview(rows)
        self.assertEqual(result["candidate_count"], 4)
        self.assertEqual([r["party_id"] for r in result["candidates"]],
                         [r["party_id"] for r in rows])
        self.assertTrue(all(r["requires_human_financial_decision"]
                            for r in result["candidates"]))
        self.assertEqual(
            result["candidates"][0]["fields"]["name"]["comparison"],
            "equal_after_heuristic_normalization",
        )
        self.assertEqual(
            result["candidates"][0]["fields"]["phone"]["comparison"],
            "equal_after_heuristic_normalization",
        )
        self.assertEqual(
            result["candidates"][0]["fields"]["official_id"]["comparison"],
            "equal_after_heuristic_normalization",
        )
        self.assertEqual(result["candidates"][0]["conflicts"], [])
        self.assertEqual(
            result["candidates"][1]["conflicts"],
            ["conflicting_upstream_claimed_verified_official_ids"],
        )
        self.assertIn(
            "گستر",
            result["candidates"][2]["fields"]["name"]["heuristic_shared_words"],
        )
        self.assertEqual(
            result["candidates"][3]["fields"]["name"]["comparison"], "different",
        )
        self.assertEqual(result["candidates"][3]["fields"]["name"]["heuristic_shared_words"], [])

    def test_conflicting_source_claimed_verified_ids_are_not_hidden_by_matching_name(self):
        result = self.preview([candidate(
            "party-conflict", official_id="888888",
            official_id_source_verified=True, name="شرکت آفتاب گستر",
        )])
        row = result["candidates"][0]
        self.assertEqual(row["fields"]["name"]["comparison"],
                         "equal_after_heuristic_normalization")
        self.assertEqual(row["fields"]["official_id"]["comparison"], "different")
        self.assertEqual(row["fields"]["official_id"]["upstream_claimed_verified"],
                         {"temporary": True, "candidate": True})
        self.assertEqual(row["conflicts"],
                         ["conflicting_upstream_claimed_verified_official_ids"])
        self.assertFalse(result["official_id_verified_by_engine"])
        self.assertFalse(result["automatic_link_or_creation_performed"])

    def test_different_ids_without_both_source_claims_stay_different_not_verified_conflict(self):
        temp = {**CUSTOMER, "official_id_source_verified": False}
        result = self.preview(
            [candidate("party-1", official_id="99", official_id_source_verified=True)],
            customer=temp,
        )
        row = result["candidates"][0]
        self.assertEqual(row["fields"]["official_id"]["comparison"], "different")
        self.assertEqual(row["conflicts"], [])
        self.assertEqual(row["fields"]["official_id"]["upstream_claimed_verified"],
                         {"temporary": False, "candidate": True})

    def test_missing_fields_are_explained_without_filling_guessed_values(self):
        temp = {"customer_id": "temporary-empty", "organization_id": ORG}
        rows = [
            candidate("empty"),
            candidate("populated", name="نام دیگر", phone="0999", official_id="0001"),
        ]
        result = self.preview(rows, customer=temp)
        self.assertEqual(result["candidate_count"], 2)
        for field in ("official_id", "name", "phone", "address"):
            self.assertEqual(result["candidates"][0]["fields"][field]["comparison"],
                             "missing_both")
        for field in ("official_id", "name", "phone"):
            self.assertEqual(result["candidates"][1]["fields"][field]["comparison"],
                             "missing_temporary")
            self.assertIsNone(result["candidates"][1]["fields"][field]["temporary_value"])
        self.assertEqual(result["candidates"][1]["fields"]["address"]["comparison"],
                         "missing_both")
        self.assertEqual(
            self.preview([candidate("no-phone", name="X")])["candidates"][0]
            ["fields"]["phone"]["comparison"], "missing_candidate",
        )

    def test_unauthorized_fields_never_used_or_reflected_even_if_present_in_input(self):
        scope = {**SCOPE, "visible_fields": ["name"]}
        private = candidate("party-private", name="آفتاب گستر",
                            phone="SECRET-PHONE-PRIVATE", address="SECRET-ADDRESS-PRIVATE",
                            official_id="SECRET-ID-PRIVATE",
                            official_id_source_verified=True)
        result = self.preview([private], scope=scope)
        row = result["candidates"][0]
        # The company-name prefix is meaningful, not a token to silently drop.
        self.assertEqual(row["fields"]["name"]["comparison"], "different")
        self.assertEqual(row["fields"]["name"]["heuristic_shared_words"],
                         ["آفتاب", "گستر"])
        for field in ("official_id", "phone", "address"):
            self.assertEqual(row["fields"][field], {"comparison": "not_authorized"})
        text = repr(result)
        for secret in ("SECRET-PHONE-PRIVATE", "SECRET-ADDRESS-PRIVATE", "SECRET-ID-PRIVATE"):
            self.assertNotIn(secret, text)
        self.assertEqual(row["conflicts"], [])

    def test_rejects_cross_organization_candidates_as_whole_batch_without_partial_response(self):
        first = candidate("allowed", name="آفتاب گستر")
        outside = {**candidate("outside", name="EXTERNAL-CONFIDENTIAL"),
                   "organization_id": "private-other-organization"}
        with self.assertRaises(PermissionError) as context:
            self.preview([first, outside])
        self.assertNotIn("EXTERNAL-CONFIDENTIAL", str(context.exception))
        with self.assertRaises(PermissionError):
            self.preview([outside, first])
        with self.assertRaises(PermissionError):
            self.preview([first], customer={**CUSTOMER, "organization_id": "another-org"})

    def test_missing_or_false_acl_and_server_scope_fail_closed(self):
        rows = [candidate("one")]
        for field in ("organization_id", "server_scoped", "party_read_authorized",
                      "finance_review_authorized", "visible_fields"):
            with self.subTest(field=field):
                missing = {key: value for key, value in SCOPE.items() if key != field}
                with self.assertRaises(PermissionError):
                    self.preview(rows, scope=missing)
        for bad in (
            {"server_scoped": False}, {"server_scoped": 1},
            {"party_read_authorized": False},
            {"finance_review_authorized": False},
            {"organization_id": ""},
            {"organization_id": " test-org-alpha "},
            {"visible_fields": ["name", "private_notes"]},
            {"visible_fields": ["name", "name"]},
            {"visible_fields": None},
        ):
            with self.subTest(bad=bad), self.assertRaises(PermissionError):
                self.preview(rows, scope={**SCOPE, **bad})
        for invalid in (
            {**candidate("one"), "read_authorized": False},
            {**candidate("one"), "read_authorized": 1},
            {key: value for key, value in candidate("one").items()
             if key != "read_authorized"},
            {**candidate("one"), "organization_id": None},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(PermissionError):
                self.preview([invalid])

    def test_rejects_duplicate_party_ids_and_invalid_claims_without_silent_merging(self):
        with self.assertRaisesRegex(ValueError, "Duplicate candidate"):
            self.preview([candidate("duplicate"), candidate("duplicate")])
        with self.assertRaisesRegex(ValueError, "boolean"):
            self.preview([candidate("party", official_id="123",
                                    official_id_source_verified="yes")])
        with self.assertRaisesRegex(ValueError, "cannot be missing"):
            self.preview([candidate("party", official_id=None,
                                    official_id_source_verified=True)])
        with self.assertRaises(ValueError):
            self.preview([candidate("party", name={"secret": "not-a-string"})])
        with self.assertRaises(PermissionError):
            self.preview([object()])

    def test_persian_unicode_and_phone_normalization_are_conservative_heuristics(self):
        result = self.preview([
            candidate("same", name="شركت آفتاب گستر", phone="0912(345)6789",
                      address="تهران، خیابان بهار", official_id="00123"),
            candidate("different-phone-format", name="شرکت آفتاب گستر",
                      phone="+989123456789", official_id="123"),
        ])
        first, second = result["candidates"]
        for field in ("name", "phone", "address", "official_id"):
            self.assertEqual(first["fields"][field]["comparison"],
                             "equal_after_heuristic_normalization")
        self.assertEqual(second["fields"]["phone"]["comparison"], "different")
        self.assertEqual(second["fields"]["official_id"]["comparison"], "different")
        self.assertEqual(result["comparison_normalization"],
                         "heuristic_not_official_verification")

    def test_empty_candidates_do_not_invent_official_records(self):
        result = self.preview([])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["candidate_count"], 0)
        self.assertTrue(result["manual_financial_review_required"])
        self.assertFalse(result["automatic_link_or_creation_performed"])

    def test_preview_preserves_inputs_and_never_makes_a_financial_decision_or_network_call(self):
        rows = [candidate("party", name="آفتاب گستر", official_id="00123")]
        original_customer = deepcopy(CUSTOMER)
        original_rows = deepcopy(rows)
        original_scope = deepcopy(SCOPE)
        with (
            patch("socket.create_connection", side_effect=AssertionError("network forbidden")),
            patch("builtins.open", side_effect=AssertionError("file I/O forbidden")),
        ):
            result = self.preview(rows)
        self.assertEqual(CUSTOMER, original_customer)
        self.assertEqual(rows, original_rows)
        self.assertEqual(SCOPE, original_scope)
        self.assertNotIn("selected_party_id", result)
        self.assertNotIn("decision", result)
        self.assertNotIn("score", repr(result))
        self.assertNotIn("threshold", repr(result))
        self.assertTrue(result["manual_financial_review_required"])
        self.assertTrue(result["candidates"][0]["requires_human_financial_decision"])
        self.assertFalse(result["automatic_link_or_creation_performed"])


if __name__ == "__main__":
    unittest.main()
