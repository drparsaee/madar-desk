"""Prove readonly migration comparison source from actual checked backup."""
import copy
import json
import subprocess
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from madar_offline_reconciliation_export import build_madar_comparison_snapshot
from parsian_reconciliation_gate import compare_snapshots
from standalone_accounting import StandaloneAccountingStore
from standalone_accounting_auto_backup import AutomaticStandaloneBackups

PEOPLE = {"admin": {"username": "admin", "role": "admin"}}
NOW = "2026-10-24T12:00:00Z"


class ReadonlyMigrationExportTests(unittest.TestCase):
    def test_full_real_verified_snapshot_matches_same_fake_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            root = folder / "isolated-finance"
            store = StandaloneAccountingStore(root/"standalone-accounting.sqlite3",
                                              default_currency="RIAL")
            commands = [
                {"type":"party.register","eventId":"ev1",
                 "partyId":"buyer","name":"Synthetic","kind":"customer"},
                {"type":"invoice.create","eventId":"ev2","invoiceId":"invoice1",
                 "partyId":"buyer","documentDate":"2026-10-24",
                 "lines":[{"description":"Print","quantity":3,"unitPrice":251}],
                 "discount":1},
                {"type":"invoice.approve","eventId":"ev3","invoiceId":"invoice1"},
                {"type":"invoice.issue","eventId":"ev4","invoiceId":"invoice1",
                 "postingDate":"2026-10-24"},
                {"type":"receipt.record","eventId":"ev5","receiptId":"receipt1",
                 "partyId":"buyer","accountId":"1010",
                 "postingDate":"2026-10-24",
                 "allocations":[{"invoiceId":"invoice1","amount":252}]},
            ]
            for rev, event in enumerate(commands):
                store.command(event,actor="admin",accounts=PEOPLE,
                              expected_revision=rev,now=NOW)
            backup = AutomaticStandaloneBackups(
                root,plaintext_acknowledged=True).backup_now()
            before = sha256(backup.read_bytes()).hexdigest()
            snapshot = build_madar_comparison_snapshot(
                backup, company_ref="qa-company", as_of="2026-10-24")
            self.assertEqual(snapshot["currency"], "RIAL")
            self.assertEqual(snapshot["controlTotals"]["receivable"], 500)
            self.assertEqual(snapshot["controlTotals"]["cashBank"], 252)
            self.assertEqual(snapshot["documentCounts"]["journals"], 2)
            self.assertEqual(snapshot["documentCounts"]["salesInvoices"], 1)
            self.assertEqual(snapshot["documentCounts"]["receipts"], 1)
            source = copy.deepcopy(snapshot)
            source["sourceSystem"] = "PARSIAN"
            result = compare_snapshots(source, snapshot)
            self.assertTrue(result["balancesMatchInSuppliedSnapshots"])
            self.assertFalse(result["safeToImport"])
            source_file = folder / "synthetic-parsian-summary.json"
            source_file.write_text(json.dumps(source),encoding="utf-8")
            command = [sys.executable,"-B","-m","parsian_reconciliation_gate",
                       "--parsian-summary",str(source_file),
                       "--madar-backup",str(backup),
                       "--company-ref","qa-company","--as-of","2026-10-24"]
            process = subprocess.run(command,
                     cwd=Path(__file__).resolve().parents[1],
                     capture_output=True,text=True,timeout=15)
            self.assertEqual(process.returncode,0,process.stdout+process.stderr)
            self.assertEqual(json.loads(process.stdout)["gateStatus"],
                             "SAMPLE_BALANCES_EQUAL_UNVERIFIED")
            self.assertEqual(sha256(backup.read_bytes()).hexdigest(), before)
            # No journal sidecars created by the read-only snapshot exporter.
            for sidecar in ("-wal","-shm","-journal"):
                self.assertFalse(Path(str(backup) + sidecar).exists())

    def test_reject_active_database_and_legacy_toman(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/"isolated"
            legacy = StandaloneAccountingStore(
                root/"standalone-accounting.sqlite3",default_currency="TOMAN")
            legacy.command(
                {"type":"party.register","eventId":"legacy1","partyId":"p1",
                 "name":"Legacy synthetic","kind":"customer"},
                actor="admin",accounts=PEOPLE,expected_revision=0,now=NOW)
            backup = AutomaticStandaloneBackups(
                root,plaintext_acknowledged=True).backup_now()
            with self.assertRaisesRegex(ValueError, "RIAL"):
                build_madar_comparison_snapshot(
                    backup,company_ref="company",as_of="2026-10-24")
            with self.assertRaisesRegex(ValueError, "automatically validated"):
                build_madar_comparison_snapshot(
                    legacy.path,company_ref="company",as_of="2026-10-24")

    def test_empty_backup_has_no_authoritative_currency_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/"empty-rial"
            StandaloneAccountingStore(root/"standalone-accounting.sqlite3",
                                      default_currency="RIAL")
            backup = AutomaticStandaloneBackups(
                root,plaintext_acknowledged=True).backup_now()
            with self.assertRaisesRegex(ValueError, "Cannot infer RIAL/TOMAN"):
                build_madar_comparison_snapshot(
                    backup,company_ref="company",as_of="2026-10-24")


if __name__ == "__main__":
    unittest.main()
