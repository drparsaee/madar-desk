"""Synthetic only: shipped Taraz code objects and actual React/Chromium clicks.

These tests NEVER execute installed Taraz.exe, read a user ledger or open
external network. They use create-only disposable QA bridges under TEMP.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


MADAR = Path(__file__).resolve().parents[1]
SCRIPT = MADAR / "scripts" / "qa_taraz_shipped_api_cli_20261110.py"
TARAZ = Path(r"D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109")
BROWSER = TARAZ / "scripts" / "qa_taraz_review_native_browser_20261110.cjs"
spec = importlib.util.spec_from_file_location("taraz_shipped_api_cli", SCRIPT)
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


class BrowserNativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="madar-qa-taraz-bridge-ui-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bridge = self.root / "AppData" / "Local" / "Madar-Taraz-Bridge"
        self.pending = self.bridge / "pending"
        self.pending.mkdir(parents=True)
        (self.root / "AppData" / "Roaming").mkdir()
        (self.root / "Temp").mkdir()
        self.id = "a1" * 16
        self.proposal = {
            "schema": 1, "source": "madar", "id": self.id,
            "taskId": "synthetic-qa-card", "projectId": "synthetic-qa-project",
            "title": "QA disposable metadata request",
            "createdUtc": "2026-11-10T00:00:00+00:00",
        }
        self.save()
        local = os.environ.get("LOCALAPPDATA")
        self.programs = Path(local or "") / "Programs"

    def save(self, payload=None):
        file = self.pending / (self.id + ".json")
        file.write_text(json.dumps(self.proposal if payload is None else payload,
                                   ensure_ascii=False), encoding="utf-8")
        return file

    def cli(self, action, *, decision=None, role="editor", unauth=False):
        args = [sys.executable, "-B", str(SCRIPT), "--action", action,
                "--bridge", str(self.bridge), "--programs", str(self.programs),
                "--id", self.id, "--role", role]
        if decision:
            args += ["--decision", decision]
        if unauth:
            args += ["--unauthenticated"]
        process = subprocess.run(args, capture_output=True, text=True,
                                 check=False, timeout=35)
        return process, json.loads(process.stdout.strip())

    def test_synthetic_qa_path_rejected_outside_exact_temp_root(self):
        wrong = self.root / "other" / "AppData" / "Local" / "Madar-Taraz-Bridge"
        wrong.mkdir(parents=True)
        (wrong / "pending").mkdir()
        with self.assertRaises(qa.BoundaryError):
            qa.validate_bridge(str(wrong))
        with self.assertRaises(qa.BoundaryError):
            qa.validate_bridge("relative/dir")

    def test_hard_stop_on_extra_financial_field(self):
        self.save({**self.proposal, "amountRial": "1"})
        with self.assertRaisesRegex(qa.BoundaryError, "schema"):
            qa._prereview(self.bridge, self.id)

    def test_duplicated_field_rejected_before_packaged_loader(self):
        file = self.save()
        raw = file.read_text(encoding="utf-8").replace(
            '"schema": 1', '"schema": 1, "schema": 1')
        file.write_text(raw, encoding="utf-8")
        with self.assertRaisesRegex(qa.BoundaryError, "Duplicate"):
            qa._prereview(self.bridge, self.id)

    def test_preflight_loads_shipped_code_but_never_lists(self):
        if not self.programs.is_dir():
            self.skipTest("Installed Programs folder unavailable")
        proc, out = self.cli("preflight")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out["installedTarazExeSha256"], qa.EXPECTED_HASH)
        self.assertTrue(out["packagedMethodCodeLoaded"])
        self.assertFalse(out["inboxMethodInvoked"])
        self.assertFalse(out["reviewMethodInvoked"])
        self.assertFalse(out["installedExeLaunched"])

    def test_unauthenticated_list_denied_by_actual_packaged_method(self):
        if not self.programs.is_dir():
            self.skipTest("Installed Programs folder unavailable")
        proc, out = self.cli("list", unauth=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(out["status"], "DENIED")
        self.assertEqual(out["errorCode"], "AUTH_DENIED")
        self.assertTrue(self.save().is_file())

    def test_viewer_review_denied_by_actual_packaged_role_gate(self):
        if not self.programs.is_dir():
            self.skipTest("Installed Programs folder unavailable")
        proc, out = self.cli("review", role="viewer", decision="reviewed")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(out["status"], "DENIED")
        self.assertEqual(out["errorCode"], "AUTH_DENIED")
        self.assertTrue(self.save().is_file())

    def test_editor_review_direct_shipped_api_durable_readback(self):
        if not self.programs.is_dir():
            self.skipTest("Installed Programs folder unavailable")
        result = qa.execute("review", str(self.bridge), str(self.programs),
                            self.id, "reviewed")
        self.assertTrue(result["actualPackagedTarazApiInvoked"])
        self.assertEqual(result["data"]["state"], "reviewed")
        self.assertTrue(qa._review_marker(
            self.bridge, self.id, "reviewed")["storedReviewReceiptVerified"])
        self.assertFalse(result["durableSourceDigestIntentPresent"])
        readback = qa.execute("list", str(self.bridge), str(self.programs),
                              self.id, None)
        self.assertEqual(readback["data"]["requests"], [])

    def test_browser_after_packaged_read_preflight_with_fully_sandboxed_env(self):
        """Exact Persian sample, prior preflight and prime env; no Madar GUI."""
        if not self.programs.is_dir():
            self.skipTest("Installed Programs folder unavailable")
        self.proposal["title"] = "طراحی برد و چیدمان کارها"
        self.save()
        original_roaming = os.environ.get("APPDATA")
        if not original_roaming:
            self.skipTest("Read-only playwright module location unavailable")
        qa_modules = Path(original_roaming) / "npm" / "node_modules"
        if not (qa_modules / "playwright").is_dir():
            self.skipTest("Read-only playwright module unavailable")
        # Earlier prime preflight invoked real packed TarazList, not mocked UI.
        first = qa.execute("list", str(self.bridge), str(self.programs),
                           self.id, None)
        self.assertEqual(len(first["data"]["requests"]), 1)
        env = os.environ.copy()
        env.update({
            "APPDATA": str(self.root / "AppData" / "Roaming"),
            "LOCALAPPDATA": str(self.root / "AppData" / "Local"),
            "TEMP": str(self.root / "Temp"), "TMP": str(self.root / "Temp"),
            "USERPROFILE": str(self.root), "HOME": str(self.root),
            "MTR_QA_PLAYWRIGHT_MODULES": str(qa_modules),
            "PYTHONIOENCODING": "cp1252:strict",
        })
        proc = subprocess.run(
            ["node", str(BROWSER), "--bridge", str(self.bridge),
             "--programs", str(self.programs), "--id", self.id],
            cwd=TARAZ, env=env, capture_output=True, text=True,
            timeout=60, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1700:])
        result = json.loads(proc.stdout.strip())
        self.assertEqual(result["nativeReviewCalls"], 1)
        self.assertEqual(result["nativeInboxReads"], 2)
        self.assertEqual(result["inboxAutomaticReads"], 0)

    def test_cli_reports_only_bounded_safe_denial_codes(self):
        self.save({**self.proposal, "amountRial": "1"})
        proc, result = self.cli("list")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(result["errorCode"], "QA_BLOCKED")
        self.assertEqual(result["phase"], "run_packaged_api")
        self.assertEqual(result["reasonCode"], "PROPOSAL_SCHEMA_KEYS")
        self.assertNotIn(str(self.bridge), proc.stdout + proc.stderr)

    def test_native_browser_with_madar_persian_sample_title(self):
        """Regression for prime's exact legacy sample title, not English QA copy."""
        self.proposal["title"] = "طراحی برد و چیدمان کارها"
        self.save()
        self._assert_browser("reviewed")

    def test_persian_proposal_cli_stdout_encoding(self):
        self.proposal["title"] = "طراحی برد و چیدمان کارها"
        self.save()
        # Force the exact Windows redirected-stdout encoding that made the
        # integration silently return QA_BLOCKED before the fix.
        with patch.dict(os.environ, {"PYTHONIOENCODING": "cp1252:strict"}):
            result, output = self.cli("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output["data"]["requests"][0]["title"],
                         self.proposal["title"])

    def _browser(self, decision):
        if not self.programs.is_dir():
            self.skipTest("Installed Programs folder unavailable")
        if not BROWSER.is_file():
            self.fail("Detached Taraz current-source QA script is missing")
        args = ["node", str(BROWSER), "--bridge", str(self.bridge),
                "--programs", str(self.programs), "--id", self.id]
        if decision == "rejected":
            args.append("--reject")
        proc = subprocess.run(args, cwd=TARAZ, capture_output=True,
                              text=True, check=False, timeout=90)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1500:])
        return json.loads(proc.stdout.strip())

    def _assert_browser(self, decision):
        result = self._browser(decision)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["installedTarazExeSha256"], qa.EXPECTED_HASH)
        self.assertEqual(result["proposalId"], self.id)
        self.assertEqual(result["decision"], decision)
        self.assertTrue(result["actualCurrentReactChromiumClicked"])
        self.assertTrue(result["explicitManualOptIn"])
        self.assertTrue(result["secondConfirmation"])
        self.assertTrue(result["shippedReviewCalledByBrowser"])
        self.assertTrue(result["readbackAfterReview"])
        self.assertEqual(result["inboxAutomaticReads"], 0)
        self.assertEqual(result["nativeInboxReads"], 2)
        self.assertEqual(result["nativeReviewCalls"], 1)
        self.assertFalse(result["financialEventCreated"])
        self.assertFalse(result["installedTarazExeLaunched"])
        self.assertFalse(result["officialTarazReceiptVerified"])
        self.assertTrue(result["qaSourceDigestMatchedBeforeAndAfterMove"])
        self.assertFalse(result["durableIntentMarkerPresent"])
        self.assertFalse(result["crashRecoveryParityWithCurrentSource"])
        self.assertFalse(self.pending.joinpath(self.id + ".json").exists())
        self.assertTrue(qa._review_marker(
            self.bridge, self.id, decision)["storedReviewReceiptVerified"])

    def test_current_real_chromium_review_calls_shipped_native_api(self):
        self._assert_browser("reviewed")

    def test_current_real_chromium_reject_calls_shipped_native_api(self):
        self._assert_browser("rejected")


if __name__ == "__main__":
    unittest.main()
