"""End-to-end synthetic current-source Madar↔Taraz finance security checks.

All principals, keys, registered company and ledger are created in temporary
directories. Synthetic transport confidence is *injected*, not live trust.
No installed program, personal accounting profile, LAN, or user ledger touched.
"""
from __future__ import annotations

from contextlib import closing, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts import qa_mtr_finance_crosssource_synthetic_20261110 as qa


class CurrentCrossSourceSyntheticTests(unittest.TestCase):
    def _common(self, result):
        self.assertTrue(result["currentPrivateLanAccountForTokenVerified"])
        self.assertTrue(result["syntheticPeerTransportTrustInjected"])
        self.assertTrue(result["syntheticTestKeysOnly"])
        self.assertEqual(result["sameOriginalIntakeCount"], 1)
        self.assertEqual(result["sameQueryCount"], 1)
        self.assertTrue(result["lostAckIntakeIdempotent"])
        self.assertTrue(result["lostAckQueryIdentical"])
        self.assertTrue(result["secondHostQueryDenied"])
        self.assertEqual(result["sourceRawSha256"], result["reviewedRawSha256"])
        self.assertTrue(result["nonfinancialManualReviewSourceBound"])
        self.assertTrue(result["persistedSyntheticInvoiceIssueJournal"])
        self.assertEqual(result["ledgerRevision"], 4)
        self.assertTrue(result["externalActorLinkGrantedByCurrentTarazAdmin"])
        self.assertTrue(result["externalActorLinkConsumed"])
        for key in ("officialFinanceReceiptVerified",
                    "independentlyAuthenticatedMadarActorVerified",
                    "trustedMadarInvoiceBindingVerified",
                    "financialPostingReal", "installed", "mayRelease", "mayDeploy"):
            self.assertIs(result[key], False, key)
        for key in ("sourceRawSha256", "reviewMarkerSha256",
                    "signedOriginalWireSha256", "signedQueryWireSha256",
                    "signedPeerLookupSha256", "ledgerStateSha256",
                    "invoiceIssueEventSha256"):
            self.assertRegex(result[key], r"^[0-9a-f]{64}$", key)
        for rel, digest in result["sourceModulesSha256"].items():
            parent, filename = rel.split("/", 1)
            root = qa.MADAR_ROOT if parent == "madar" else qa.TARAZ_ROOT
            self.assertEqual(hashlib.sha256((root / filename).read_bytes()).hexdigest(),
                             digest, "current source bytes changed during QA")

    def test_actual_madar_proposal_private_lan_taraz_editor_admin_journal_binding(self):
        with tempfile.TemporaryDirectory(prefix="mtr-finance-full-qa-") as folder:
            root = Path(folder)
            result = qa.run_crosssource_synthetic(root=root)
            self._common(result)
            self.assertEqual(result["decision"], "SYNTHETIC_JOURNAL_OBSERVED_NOT_OFFICIAL")
            self.assertTrue(result["manualFinanceBindingRun"])
            self.assertTrue(result["manualFinanceBindingReplayDenied"])
            self.assertFalse(result.get("syntheticFinanceWitnessCryptographyVerified", False))

            source_files = list((root / "LOCALAPPDATA" / "Madar-Taraz-Bridge"
                                 / "reviewed").glob("[0-9a-f]" * 32 + ".json"))
            self.assertEqual(len(source_files), 1)
            self.assertEqual(hashlib.sha256(source_files[0].read_bytes()).hexdigest(),
                             result["sourceRawSha256"])
            databases = list(root.rglob("standalone-accounting.sqlite3"))
            self.assertEqual(len(databases), 1)
            with closing(sqlite3.connect(databases[0])) as conn:
                revision, state, digest = conn.execute(
                    "SELECT revision,state,digest FROM standalone_accounting WHERE id=1"
                ).fetchone()
            self.assertEqual(revision, 4)
            self.assertEqual(hashlib.sha256(state).hexdigest(), digest)
            self.assertEqual(digest, result["ledgerStateSha256"])
            self.assertEqual(sum(
                1 for event in json.loads(state)["events"]
                if event["command"]["type"] == "invoice.issue"), 1)

    def test_actual_independently_keyed_witness_issuer_and_verifier_remain_nonofficial(self):
        with tempfile.TemporaryDirectory(prefix="mtr-finance-witness-qa-") as folder:
            result = qa.run_crosssource_synthetic(
                root=Path(folder), include_finance_witness=True)
            self._common(result)
            self.assertEqual(
                result["decision"], "SYNTHETIC_FINANCE_WITNESS_STRUCTURAL_ONLY_NOT_OFFICIAL")
            self.assertFalse(result["manualFinanceBindingRun"])
            self.assertTrue(result["syntheticFinanceWitnessCryptographyVerified"])
            self.assertTrue(result["syntheticFinanceWitnessBoundToExactJournal"])
            self.assertTrue(result["oneTimeDurableWitnessChallengeConsumed"])
            self.assertTrue(result["witnessIssuerReplayDenied"])
            self.assertTrue(result["witnessVerifierReplayDenied"])
            self.assertEqual(result["financeWitnessEventRawSha256"],
                             result["invoiceIssueEventSha256"])
            self.assertEqual(result["financeWitnessAssessment"],
                             "SIGNED_WITNESS_STRUCTURALLY_VERIFIED_OFFICIAL_ISSUER_UNAVAILABLE")
            self.assertEqual(result["financeWitnessIssuer"], "SOURCE_PRESENT_UNINTEGRATED")
            self.assertTrue(result["financeWitnessMadarVerifierSourcePresent"])
            for name in ("mtr-taraz-finance-witness-queries.sqlite3",
                         "mtr-taraz-finance-witness-issued.sqlite3"):
                self.assertEqual(len(list(Path(folder).rglob(name))), 1)

    def test_existing_nonempty_root_denied_without_modification(self):
        with tempfile.TemporaryDirectory(prefix="mtr-finance-negative-qa-") as folder:
            marker = Path(folder) / "someones-synthetic-data.txt"
            marker.write_text("preserve", encoding="utf-8")
            with self.assertRaises(ValueError):
                qa.run_crosssource_synthetic(root=Path(folder))
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")
            self.assertEqual(list(Path(folder).iterdir()), [marker])

    def test_missing_current_source_denied_before_any_profile_creation(self):
        with tempfile.TemporaryDirectory(prefix="mtr-finance-missing-qa-") as folder:
            with patch.object(qa, "_check_sources",
                              side_effect=RuntimeError("current source unavailable")):
                with self.assertRaisesRegex(RuntimeError, "current source unavailable"):
                    qa.run_crosssource_synthetic(root=Path(folder))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_cli_fails_closed_on_any_execution_error(self):
        buffer = io.StringIO()
        with patch.object(qa, "run_crosssource_synthetic",
                          side_effect=PermissionError("synthetic trust denied")):
            with redirect_stdout(buffer):
                code = qa.main()
        self.assertEqual(code, 2)
        report = json.loads(buffer.getvalue())
        self.assertEqual(report["decision"], "BLOCKED_SYNTHETIC_EXECUTION")
        for field in ("officialFinanceReceiptVerified", "installed",
                      "financialPostingReal", "mayRelease"):
            self.assertIs(report[field], False)

    def test_invalid_witness_mode_denied(self):
        with self.assertRaises(TypeError):
            qa.run_crosssource_synthetic(include_finance_witness="true")


if __name__ == "__main__":
    unittest.main()
