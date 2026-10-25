"""Offline Parsian staging checks using exclusively synthetic metadata / BAKs."""

from copy import deepcopy
import builtins
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parsian_backup_probe import identify_backup
from parsian_migration_staging import (
    MAX_BACKUP_BYTES, build_staging_manifest, classify_backup_header,
    validate_currency_evidence, validate_field_mapping,
    validate_schema_inventory,
)


HEADER = b"TAPE" + b"\0" * 12
NON_TAPE = b"FAKE" + b"\0" * 12
SCHEMA = {
    "schemaVersion": 1,
    "tables": [
        {"name": "dbo.Invoice", "columns": [
            "InvoiceId", "CustomerId", "InvoiceDate", "TotalRial"
        ], "primaryKey": ["InvoiceId"]},
        {"name": "dbo.Person", "columns": [
            "PersonId", "Name", "Kind"
        ], "primaryKey": ["PersonId"]},
        {"name": "dbo.Bill", "columns": [
            "BillId", "VendorId", "BillDate", "TotalRial"
        ], "primaryKey": ["BillId"]},
    ],
}
SALES = [
    {"sourceTable": "dbo.Invoice", "sourceColumn": src,
     "targetField": target, "sourceUnit": unit}
    for src, target, unit in (
        ("InvoiceId", "sales_invoice.id", None),
        ("CustomerId", "sales_invoice.party_id", None),
        ("InvoiceDate", "sales_invoice.date", None),
        ("TotalRial", "sales_invoice.total", "RIAL"),
    )
]
PURCHASE = [
    {"sourceTable": "dbo.Bill", "sourceColumn": src,
     "targetField": target, "sourceUnit": unit}
    for src, target, unit in (
        ("BillId", "purchase_bill.id", None),
        ("VendorId", "purchase_bill.party_id", None),
        ("BillDate", "purchase_bill.date", None),
        ("TotalRial", "purchase_bill.total", "RIAL"),
    )
]
RIAL_REVIEW = {
    "sourceUnit": "RIAL",
    "method": "restored_schema_and_trial_balance",
    "evidenceSha256": "a" * 64,
    "reviewId": "review-2026-01",
}


def stage(**kwargs):
    return build_staging_manifest(HEADER, size_bytes=1024, **kwargs)


class ParsianMigrationStagingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="parsian-stage-synthetic-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_synthetic_tape_magic_is_candidate_not_a_verified_backup(self):
        result = classify_backup_header(HEADER, size_bytes=1024)
        self.assertEqual(result["format"], "sqlserver_media_header_candidate")
        self.assertEqual(result["signature"], "TAPE")
        self.assertEqual(result["confidence"], "signature_only")
        self.assertFalse(result["schemaParsed"])
        self.assertFalse(result["backupValidityVerified"])
        self.assertFalse(result["canRestore"])
        self.assertFalse(result["canImport"])

    def test_non_tape_also_cannot_import(self):
        result = classify_backup_header(NON_TAPE, size_bytes=1024)
        self.assertEqual(result["format"], "unrecognized_media_header")
        self.assertFalse(result["canImport"])

    def test_only_exact_bytes_and_safe_size_bounds_accepted(self):
        for header in (b"TAPE", bytearray(HEADER), memoryview(HEADER),
                       None, b"TAPE" + b"\0" * 13, "TAPE"):
            with self.subTest(header=type(header)), self.assertRaises(ValueError):
                classify_backup_header(header, size_bytes=1024)
        for size in (-1, 0, 511, MAX_BACKUP_BYTES + 1, True, 1024.0, "1024"):
            with self.subTest(size=size), self.assertRaises(ValueError):
                classify_backup_header(HEADER, size_bytes=size)
        self.assertEqual(classify_backup_header(HEADER, size_bytes=512)["sizeBytes"], 512)
        self.assertEqual(classify_backup_header(HEADER, size_bytes=MAX_BACKUP_BYTES)
                         ["sizeBytes"], MAX_BACKUP_BYTES)

    def test_synthetic_temp_bak_probe_is_compatible_but_not_schema_parser(self):
        # This is a NEW fabricated 512-byte buffer; no user's original BAK is opened.
        sample = self.root / "fabricated.bak"
        sample.write_bytes(HEADER + b"\0" * 496)
        probed = identify_backup(sample)
        self.assertEqual(probed["signature"], "TAPE")
        self.assertFalse(probed["canImportIntoMadar"])
        manifest = build_staging_manifest(sample.read_bytes()[:16], size_bytes=512)
        self.assertEqual(manifest["schemaStatus"], "not_parsed_from_backup")
        self.assertFalse(manifest["canApplyToMadar"])
        self.assertIsNone(manifest["inventoryCounts"])

    def test_preview_functions_do_not_use_file_open_path_or_data_connection(self):
        with patch.object(builtins, "open", side_effect=AssertionError("open forbidden")):
            manifest = stage()
        self.assertFalse(manifest["moneyImportAllowed"])
        self.assertFalse(manifest["allImportAllowed"])

    def test_inventory_accepts_names_keys_and_counts_but_never_data_rows(self):
        summary = validate_schema_inventory(SCHEMA)
        self.assertEqual(summary["tableCount"], 3)
        self.assertEqual(summary["columnCount"], 11)
        self.assertNotIn("records", json.dumps(summary))

    def test_inventory_rejects_sql_injection_and_record_payloads(self):
        for name in ("dbo.Invoice;DROP", "[dbo].[Invoice]", "Invoice",
                     "dbo.Invoice..Trash", "dbo.Invoice--", ""):
            candidate = deepcopy(SCHEMA)
            candidate["tables"][0]["name"] = name
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_schema_inventory(candidate)
        for key in ("data", "rows", "money"):
            candidate = deepcopy(SCHEMA)
            candidate["tables"][0][key] = [{"customer": "PRIVATE", "amount": 500}]
            with self.subTest(extra=key), self.assertRaises(ValueError):
                validate_schema_inventory(candidate)

    def test_inventory_rejects_collision_unknown_key_and_capacity(self):
        base = deepcopy(SCHEMA)
        base["tables"][0]["columns"].append("invoiceid")
        with self.assertRaises(ValueError):
            validate_schema_inventory(base)
        base = deepcopy(SCHEMA)
        base["tables"][0]["primaryKey"] = ["NoSuchKey"]
        with self.assertRaises(ValueError):
            validate_schema_inventory(base)
        base = deepcopy(SCHEMA)
        base["tables"].append(deepcopy(base["tables"][0]))
        with self.assertRaises(ValueError):
            validate_schema_inventory(base)
        base = deepcopy(SCHEMA)
        base["tables"][0]["columns"] = [f"Column{n}" for n in range(257)]
        with self.assertRaises(ValueError):
            validate_schema_inventory(base)
        base = deepcopy(SCHEMA)
        base["tables"] = base["tables"] * 43
        with self.assertRaises(ValueError):
            validate_schema_inventory(base)

    def test_inventory_malformed_type_version_and_empty_structures_rejected(self):
        for bad in (None, {}, [], {"schemaVersion": True, "tables": SCHEMA["tables"]},
                    {"schemaVersion": 2, "tables": SCHEMA["tables"]},
                    {"schemaVersion": 1, "tables": []}):
            with self.subTest(case=type(bad)), self.assertRaises(ValueError):
                validate_schema_inventory(bad)

    def test_mapping_complete_sales_and_purchase_proposals_only(self):
        out = validate_field_mapping(SCHEMA, SALES + PURCHASE,
                                     required_groups=["sales_invoice", "purchase_bill"])
        self.assertTrue(out["mappingComplete"])
        self.assertEqual(out["claimedSourceUnit"], "RIAL")
        self.assertEqual(out["moneyFields"], 2)
        self.assertEqual(out["mappedFields"], 8)
        self.assertEqual(out["missingTargets"], [])
        self.assertEqual(len(out["proposalDigest"]), 64)
        self.assertNotIn("TotalRial", json.dumps(out))

    def test_partial_mapping_is_not_complete_even_when_valid(self):
        result = validate_field_mapping(SCHEMA, SALES[:-1],
                                        required_groups=["sales_invoice"])
        self.assertFalse(result["mappingComplete"])
        self.assertEqual(result["missingTargets"], ["sales_invoice.total"])
        self.assertIsNone(result["claimedSourceUnit"])
        self.assertFalse(validate_field_mapping(SCHEMA, SALES)["mappingComplete"])

    def test_money_mapping_requires_explicit_unit_claim_and_no_mixed_units(self):
        for unit in (None, "", "IRR", "rial", "RIAL/TOMAN", True):
            proposal = deepcopy(SALES)
            proposal[-1]["sourceUnit"] = unit
            with self.subTest(unit=unit), self.assertRaises(ValueError):
                validate_field_mapping(SCHEMA, proposal)
        inconsistent = deepcopy(SALES + PURCHASE)
        inconsistent[-1]["sourceUnit"] = "TOMAN"
        with self.assertRaisesRegex(ValueError, "Mixed"):
            validate_field_mapping(SCHEMA, inconsistent)

    def test_mapping_rejects_extra_code_formula_and_unsupported_destinations(self):
        for field, replacement in (
            ("targetField", "sales_invoice.execute_sql"),
            ("sourceColumn", "TotalRial;DROP"),
            ("sourceTable", "dbo.Unknown"),
        ):
            example = deepcopy(SALES)
            example[3][field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_field_mapping(SCHEMA, example)
        malicious = deepcopy(SALES)
        malicious[3]["transform"] = "eval(1)"
        with self.assertRaises(ValueError):
            validate_field_mapping(SCHEMA, malicious)

    def test_mapping_detects_duplicate_fields_and_duplicate_source_columns(self):
        duplicated = deepcopy(SALES) + [deepcopy(SALES[-1])]
        with self.assertRaises(ValueError):
            validate_field_mapping(SCHEMA, duplicated)
        duplicate_source = deepcopy(SALES)
        duplicate_source[-1]["sourceColumn"] = "InvoiceId"
        with self.assertRaises(ValueError):
            validate_field_mapping(SCHEMA, duplicate_source)

    def test_non_money_mapping_rejects_undue_currency_claim(self):
        proposal = deepcopy(SALES)
        proposal[0]["sourceUnit"] = "RIAL"
        with self.assertRaises(ValueError):
            validate_field_mapping(SCHEMA, proposal)

    def test_invalid_mapping_collection_and_required_groups_refuse(self):
        for invalid in (None, {}, [], [1], [True] * 129):
            with self.subTest(invalid=type(invalid)), self.assertRaises(ValueError):
                validate_field_mapping(SCHEMA, invalid)
        for groups in (["unknown"], ["sales_invoice", "sales_invoice"], "sales_invoice"):
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                validate_field_mapping(SCHEMA, SALES, required_groups=groups)

    def test_unit_missing_or_claim_never_qualifies_as_verified(self):
        self.assertEqual(validate_currency_evidence(None)["status"], "missing")
        claimed = validate_currency_evidence(RIAL_REVIEW)
        self.assertEqual(claimed["unitClaim"], "RIAL")
        self.assertEqual(claimed["status"], "review_claim_only")
        self.assertTrue(claimed["claimFormatValid"])
        self.assertFalse(claimed["independentlyVerified"])
        same = validate_currency_evidence({**RIAL_REVIEW, "sourceUnit": "TOMAN"})
        self.assertFalse(same["independentlyVerified"])

    def test_forged_verified_flag_or_bad_evidence_rejected(self):
        for bad in (
            {**RIAL_REVIEW, "verified": True},
            {**RIAL_REVIEW, "sourceUnit": "UNKNOWN"},
            {**RIAL_REVIEW, "evidenceSha256": "not-really-sha"},
            {**RIAL_REVIEW, "method": "operator_guess"},
            {**RIAL_REVIEW, "reviewId": "x"},
            {"sourceUnit": "RIAL", "verified": True},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_currency_evidence(bad)

    def test_manifest_is_redacted_and_never_contains_fake_customer_or_records(self):
        evidence = deepcopy(RIAL_REVIEW)
        manifest = stage(inventory=SCHEMA, mappings=SALES,
                         required_groups=("sales_invoice",),
                         currency_evidence=evidence)
        serialized = json.dumps(manifest, ensure_ascii=True)
        self.assertFalse(manifest["canApplyToMadar"])
        self.assertFalse(manifest["moneyImportAllowed"])
        self.assertFalse(manifest["allImportAllowed"])
        self.assertEqual(manifest["currencyReview"]["status"], "review_claim_only")
        self.assertIn("RIAL_identity", manifest["conversionPlan"])
        self.assertEqual(manifest["targetUnit"], "RIAL")
        self.assertEqual(manifest["mapping"]["mappedFields"], 4)
        for sensitive in ("dbo.Invoice", "TotalRial", "InvoiceId",
                          "review-2026", evidence["evidenceSha256"]):
            self.assertNotIn(sensitive, serialized)
        self.assertEqual(manifest, json.loads(json.dumps(manifest)))

    def test_toman_manifest_still_disallows_money_import_and_has_no_conversion(self):
        mapping = deepcopy(SALES)
        mapping[-1]["sourceUnit"] = "TOMAN"
        evidence = {**RIAL_REVIEW, "sourceUnit": "TOMAN"}
        manifest = stage(inventory=SCHEMA, mappings=mapping,
                         required_groups=["sales_invoice"],
                         currency_evidence=evidence)
        self.assertEqual(manifest["conversionPlan"],
                         "TOMAN_to_RIAL_requires_exact_multiply_by_10_per_amount")
        self.assertFalse(manifest["moneyImportAllowed"])

    def test_mismatched_currency_claim_halts_instead_of_guessing_exchange(self):
        with self.assertRaisesRegex(ValueError, "contradicts"):
            stage(inventory=SCHEMA, mappings=SALES,
                  currency_evidence={**RIAL_REVIEW, "sourceUnit": "TOMAN"})
        with self.assertRaises(ValueError):
            stage(inventory=SCHEMA, mappings=None)
        with self.assertRaises(ValueError):
            stage(required_groups=("sales_invoice",))

    def test_unrecognized_bak_never_becomes_ready_even_with_complete_mapping(self):
        result = build_staging_manifest(
            NON_TAPE, size_bytes=512, inventory=SCHEMA, mappings=SALES,
            required_groups=("sales_invoice",), currency_evidence=RIAL_REVIEW)
        self.assertTrue(result["mapping"]["mappingComplete"])
        self.assertEqual(result["classification"]["format"],
                         "unrecognized_media_header")
        self.assertFalse(result["moneyImportAllowed"])
        self.assertFalse(result["canApplyToMadar"])

    def test_schema_inventory_input_is_not_mutated(self):
        before_schema, before_map, before_review = (
            deepcopy(SCHEMA), deepcopy(SALES), deepcopy(RIAL_REVIEW))
        stage(inventory=SCHEMA, mappings=SALES,
              required_groups=("sales_invoice",), currency_evidence=RIAL_REVIEW)
        self.assertEqual(SCHEMA, before_schema)
        self.assertEqual(SALES, before_map)
        self.assertEqual(RIAL_REVIEW, before_review)


if __name__ == "__main__":
    unittest.main()
