"""Synthetic bookkeeping parity only. No real Parsian/Madar data ever opened."""
import copy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from parsian_reconciliation_gate import (
    ReconciliationError, compare_snapshots, validate_snapshot, main,
)


def example(system, *, unit="RIAL"):
    mult = 1 if unit == "RIAL" else 10
    def amount(value):
        assert value % mult == 0
        return value // mult
    return {
        "schemaVersion": 1, "sourceSystem": system, "companyRef": "qa-company",
        "asOf": "2026-10-24", "currency": unit,
        "trialBalance": [
            {"id": "1200", "debit": amount(500), "credit": 0},
            {"id": "1010", "debit": amount(250), "credit": 0},
            {"id": "4000", "debit": 0, "credit": amount(750)},
        ],
        "parties": [
            {"id": "customer-1", "receivable": amount(500), "payable": 0},
        ],
        "cashBanks": [
            {"id": "bank-1", "balance": amount(250)},
        ],
        "controlTotals": {"receivable": amount(500),
                          "payable": 0, "cashBank": amount(250)},
        "documentCounts": {
            "journals": 2, "salesInvoices": 1, "purchaseBills": 0,
            "receipts": 1, "payments": 0, "inventoryMovements": 0,
            "cheques": 0,
        },
    }


class ParsianReconciliationGateTests(unittest.TestCase):
    def source(self, unit="RIAL"):
        return example("PARSIAN", unit=unit)

    def target(self):
        return example("MADAR")

    def test_exact_rial_parity_is_staging_only(self):
        report = compare_snapshots(self.source(), self.target())
        self.assertTrue(report["balancesMatchInSuppliedSnapshots"])
        self.assertEqual(report["gateStatus"], "SAMPLE_BALANCES_EQUAL_UNVERIFIED")
        self.assertFalse(report["sourceAuthenticated"])
        self.assertFalse(report["safeToImport"])
        self.assertEqual(len(report["blockingReasons"]), 4)
        serialized = json.dumps(report)
        self.assertNotIn("customer-1", serialized)
        self.assertNotIn("qa-company", serialized)
        self.assertNotIn("bank-1", serialized)

    def test_toman_multiplies_exactly_by_ten(self):
        report = compare_snapshots(self.source("TOMAN"), self.target())
        self.assertTrue(report["balancesMatchInSuppliedSnapshots"])
        self.assertEqual(report["currencyNormalization"], "multiply_by_10")

    def test_unequal_rows_even_when_balance_totals_same_is_rejected(self):
        target = self.target()
        target["trialBalance"][0]["debit"] -= 100
        target["trialBalance"][1]["debit"] += 100
        result = compare_snapshots(self.source(), target)
        self.assertFalse(result["balancesMatchInSuppliedSnapshots"])
        self.assertEqual(result["mismatches"]["trialBalance"]["unequal"], 2)

    def test_missing_records_are_detected_not_ignored(self):
        target = self.target()
        target["trialBalance"].pop()
        # First confirm a source unbalanced trial balance is itself rejected.
        with self.assertRaisesRegex(ReconciliationError, "not debit/credit balanced"):
            compare_snapshots(self.source(), target)
        target = self.target()
        target["parties"] = []
        target["controlTotals"]["receivable"] = 0
        result = compare_snapshots(self.source(), target)
        self.assertEqual(result["mismatches"]["parties"]["missing"], 1)
        self.assertFalse(result["balancesMatchInSuppliedSnapshots"])

    def test_explicit_crosswalk_supported_but_never_attests_identity(self):
        target = self.target()
        target["trialBalance"][0]["id"] = "asset-receivable"
        target["parties"][0]["id"] = "client-109"
        target["cashBanks"][0]["id"] = "bank-real"
        mismatch = compare_snapshots(self.source(), target)
        self.assertFalse(mismatch["balancesMatchInSuppliedSnapshots"])
        report = compare_snapshots(self.source(), target, crosswalk={
            "accounts": {"1200": "asset-receivable"},
            "parties": {"customer-1": "client-109"},
            "cashBanks": {"bank-1": "bank-real"},
        })
        self.assertTrue(report["balancesMatchInSuppliedSnapshots"])
        self.assertFalse(report["mappingIndependentlyVerified"])

    def test_crosswalk_double_mapping_and_invented_codes_refused(self):
        source = self.source()
        target = self.target()
        for mapping in [
            {"accounts": {"1200": "1010", "1010": "1010"}, "parties": {},
             "cashBanks": {}},
            {"accounts": {"UNKNOWN": "1200"}, "parties": {}, "cashBanks": {}},
            {"accounts": {"1200": "UNKNOWN"}, "parties": {}, "cashBanks": {}},
            {"accounts": {}, "parties": {}, "cashBanks": {},
             "execute": "DROP TABLE"},
        ]:
            with self.assertRaises(ReconciliationError):
                compare_snapshots(source, target, crosswalk=mapping)

    def test_controls_and_document_counts_cannot_silently_pass(self):
        source = self.source()
        target = self.target()
        target["documentCounts"]["receipts"] = 0
        report = compare_snapshots(source, target)
        self.assertEqual(report["unequalDocumentCounts"], 1)
        target = self.target()
        target["parties"][0]["receivable"] += 1
        with self.assertRaisesRegex(ReconciliationError, "AR control"):
            compare_snapshots(source, target)

    def test_invalid_shapes_dates_oversize_money_duplicate_and_bool(self):
        source = self.source()
        for key, value in [
            ("currency", "IRR"), ("asOf", "2026-02-30"),
            ("companyRef", "bad id"), ("schemaVersion", True),
            ("sourceSystem", "MADAR"), ("parties", {}),
        ]:
            candidate = {**source, key: value}
            with self.assertRaises(ReconciliationError, msg=key):
                validate_snapshot(candidate, kind="source")
        candidate = self.source()
        candidate["trialBalance"].append(copy.deepcopy(candidate["trialBalance"][0]))
        with self.assertRaisesRegex(ReconciliationError, "Duplicate"):
            validate_snapshot(candidate, kind="source")
        candidate = self.source()
        candidate["parties"][0]["receivable"] = True
        with self.assertRaises(ReconciliationError):
            validate_snapshot(candidate, kind="source")
        candidate = self.source()
        candidate["parties"][0]["receivable"] = 10**18
        with self.assertRaises(ReconciliationError):
            validate_snapshot(candidate, kind="source")
        candidate = self.target()
        candidate["currency"] = "TOMAN"
        with self.assertRaisesRegex(ReconciliationError, "Target must"):
            compare_snapshots(self.source(), candidate)

    def test_cli_readonly_matches_and_fails_without_write_to_data(self):
        with TemporaryDirectory(prefix="parsian-qa-reconcile-") as root:
            directory = Path(root)
            source = directory / "source.json"
            target = directory / "target.json"
            source.write_text(json.dumps(self.source()), encoding="utf-8")
            target.write_text(json.dumps(self.target()), encoding="utf-8")
            orig = [path.read_bytes() for path in (source, target)]
            # Run the CLI with a real process and ensure no implicit output file
            cmd = [sys.executable, "-B", "-m", "parsian_reconciliation_gate",
                   "--parsian-summary", str(source),
                   "--madar-summary", str(target)]
            process = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1],
                                     capture_output=True, text=True, timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertFalse(json.loads(process.stdout)["safeToImport"])
            self.assertEqual([path.read_bytes() for path in (source, target)], orig)
            self.assertEqual(sorted(path.name for path in directory.iterdir()),
                             ["source.json", "target.json"])
            target.write_text(target.read_text()[:-1] + ', "currency":"RIAL"}',
                              encoding="utf-8")
            reject = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(reject.returncode, 2)
            self.assertEqual(json.loads(reject.stdout)["gateStatus"],
                             "INVALID_OR_UNVERIFIED_INPUT")


if __name__ == "__main__":
    unittest.main()
