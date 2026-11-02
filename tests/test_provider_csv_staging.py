"""Synthetic provider-neutral staging checks; no financial database touched."""

import csv
import tempfile
import unittest
from pathlib import Path

from provider_csv_staging import CsvStagingError, stage_provider_csv


class ProviderCsvStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.columns = {
            "parties": {"id": "Code", "name": "Name", "kind": "Role"},
            "invoices": {"id": "Doc", "partyId": "Party", "kind": "Type",
                         "date": "Day", "status": "State", "total": "Sum"},
            "transactions": {"id": "Txn", "partyId": "Party", "documentId": "Doc",
                             "kind": "Type", "date": "Day", "amount": "Sum"},
        }
        self.records = {
            "parties": [
                ["C1", "مشتری نمونه", "مشتری"], ["V1", "فروشنده نمونه", "فروشنده"]],
            "invoices": [
                ["INV1", "C1", "invoice", "2026-10-01", "issued", "120"],
                ["B1", "V1", "bill", "2026-10-01", "issued", "40"]],
            "transactions": [
                ["T1", "C1", "INV1", "receipt", "2026-10-03", "20"],
                ["T2", "V1", "B1", "payment", "2026-10-03", "10"]],
        }
        self.spec = {
            "schemaVersion": 1, "provider": "SyntheticOtherSoftware", "currency": "RIAL",
            "datasets": {},
            "expectations": {"counts": {"parties": 2, "invoices": 2,
                                        "transactions": 2},
                             "totals": {"invoice": 120, "bill": 40,
                                        "receipt": 20, "payment": 10}},
        }
        for name, mapping in self.columns.items():
            self.spec["datasets"][name] = {
                "path": str(self.root / f"{name}.csv"), "format": "csv",
                "encoding": "utf-8-sig", "delimiter": ",", "mapping": mapping,
                "valueMaps": {"kind": {"مشتری": "customer", "فروشنده": "vendor"}}
                if name == "parties" else {},
            }
        self.write_files()

    def write_files(self):
        for name, records in self.records.items():
            cfg = self.spec["datasets"][name]
            from io import StringIO
            stream = StringIO(newline="")
            writer = csv.writer(stream, delimiter=cfg["delimiter"])
            writer.writerow(list(self.columns[name].values()))
            writer.writerows(records)
            Path(cfg["path"]).write_bytes(stream.getvalue().encode(cfg["encoding"]))

    def test_complete_preview_and_no_writes(self):
        before = {path: path.read_bytes() for path in self.root.iterdir()}
        result = stage_provider_csv(self.spec)
        self.assertEqual(result["counts"], {"parties": 2, "invoices": 2,
                                           "transactions": 2})
        self.assertEqual(result["totalsRial"]["receipt"], 20)
        self.assertEqual(result["previewRows"]["parties"][0]["kind"], "customer")
        self.assertTrue(result["structuralChecksPassed"])
        self.assertFalse(result["canApplyToMadar"])
        self.assertTrue(result["previewOnly"])
        self.assertEqual({path: path.read_bytes() for path in self.root.iterdir()}, before)

    def test_fingerprints_stable_under_csv_row_reorder(self):
        first = stage_provider_csv(self.spec)
        self.records["parties"].reverse()
        self.records["transactions"].reverse()
        self.write_files()
        second = stage_provider_csv(self.spec)
        for group in first["fingerprints"]:
            self.assertEqual({pair["identity"] for pair in first["fingerprints"][group]},
                             {pair["identity"] for pair in second["fingerprints"][group]})
            self.assertEqual({pair["content"] for pair in first["fingerprints"][group]},
                             {pair["content"] for pair in second["fingerprints"][group]})

    def test_prior_identity_detected_as_discrepancy(self):
        fingerprint = stage_provider_csv(self.spec)["fingerprints"]["invoices"][0]["identity"]
        output = stage_provider_csv(self.spec, previous_identity_fingerprints=[fingerprint])
        self.assertEqual(output["discrepancies"][0]["type"], "previous_identity_duplicate")
        self.assertFalse(output["structuralChecksPassed"])

    def test_overallocation_reported_without_posting(self):
        self.records["transactions"][0][-1] = "121"
        self.write_files()
        result = stage_provider_csv(self.spec)
        kinds = {issue["type"] for issue in result["discrepancies"]}
        self.assertIn("overallocated_document", kinds)
        self.assertIn("totals_mismatch", kinds)
        self.assertFalse(result["structuralChecksPassed"])

    def test_wrong_expected_count_detected(self):
        self.spec["expectations"]["counts"]["parties"] = 5
        output = stage_provider_csv(self.spec)
        self.assertIn({"type": "counts_mismatch", "group": "parties",
                       "expected": 5, "actual": 2}, output["discrepancies"])

    def test_explicit_cp1256_and_semicolon_supported(self):
        for cfg in self.spec["datasets"].values():
            cfg["encoding"] = "cp1256"
            cfg["delimiter"] = ";"
        # cp1256 exports conventionally use Arabic yeh, not Persian yeh.
        for row in self.records["parties"]:
            row[1] = row[1].replace("ی", "ي")
            row[2] = row[2].replace("ی", "ي")
        self.spec["datasets"]["parties"]["valueMaps"]["kind"]["مشتري"] = "customer"
        self.write_files()
        self.assertTrue(stage_provider_csv(self.spec)["structuralChecksPassed"])

    def test_extra_column_rejected_until_ignored_explicitly(self):
        self.columns["parties"]["unused"] = "Office"
        self.records["parties"][0].append("Tehran")
        self.records["parties"][1].append("Shiraz")
        self.write_files()
        with self.assertRaisesRegex(CsvStagingError, "Incomplete or unknown"):
            stage_provider_csv(self.spec)
        self.spec["datasets"]["parties"]["mapping"].pop("unused")
        with self.assertRaisesRegex(CsvStagingError, "Unmapped"):
            stage_provider_csv(self.spec)
        self.spec["datasets"]["parties"]["ignoreColumns"] = ["Office"]
        self.assertTrue(stage_provider_csv(self.spec)["structuralChecksPassed"])

    def test_missing_mapping_rejected(self):
        self.spec["datasets"]["invoices"]["mapping"].pop("total")
        with self.assertRaises(CsvStagingError):
            stage_provider_csv(self.spec)

    def test_unmapped_enum_rejected(self):
        self.records["parties"][0][2] = "UnknownRole"
        self.write_files()
        with self.assertRaisesRegex(CsvStagingError, "Unmapped"):
            stage_provider_csv(self.spec)

    def test_duplicate_id_and_reference_rejected(self):
        self.records["parties"][1][0] = "c1"
        self.write_files()
        with self.assertRaisesRegex(CsvStagingError, "Duplicate"):
            stage_provider_csv(self.spec)
        self.records["parties"][1][0] = "V1"
        self.records["transactions"][0][2] = "MISSING"
        self.write_files()
        with self.assertRaisesRegex(CsvStagingError, "missing or mismatched"):
            stage_provider_csv(self.spec)

    def test_mismatched_currency_rejected_without_conversion(self):
        self.spec["currency"] = "TOMAN"
        with self.assertRaisesRegex(CsvStagingError, "currency"):
            stage_provider_csv(self.spec)
        self.spec["currency"] = None
        with self.assertRaisesRegex(CsvStagingError, "currency"):
            stage_provider_csv(self.spec)

    def test_untrusted_amount_and_date_rejected(self):
        self.records["invoices"][0][-1] = "1,200"
        self.write_files()
        with self.assertRaisesRegex(CsvStagingError, "ASCII digits"):
            stage_provider_csv(self.spec)
        self.records["invoices"][0][-1] = "120"
        self.records["invoices"][0][3] = "1405-08-12"
        self.write_files()
        with self.assertRaisesRegex(CsvStagingError, "Gregorian"):
            stage_provider_csv(self.spec)

    def test_malformed_rows_do_not_stage(self):
        self.records["invoices"][0].pop()
        self.write_files()
        with self.assertRaisesRegex(CsvStagingError, "Malformed"):
            stage_provider_csv(self.spec)

    def test_symlink_source_rejected(self):
        real = self.root / "parties.csv"
        link = self.root / "link.csv"
        try:
            link.symlink_to(real)
        except OSError:
            self.skipTest("Symlink privileges unavailable on Windows")
        self.spec["datasets"]["parties"]["path"] = str(link)
        with self.assertRaisesRegex(CsvStagingError, "non-symlink"):
            stage_provider_csv(self.spec)


if __name__ == "__main__":
    unittest.main()
