"""Harness-only tests: no actual windows, user profiles or EXEs launched."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import zlib


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "v1_gui_smoke.py"
SPEC = importlib.util.spec_from_file_location("v1_gui_smoke", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
gui = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gui)


def passing_diagnostic():
    return {
        "port": 49371,
        "url": "http://127.0.0.1:49371/",
        "readyState": "complete",
        "rootLength": 45230,
        "bodyTextStart": "مدار\nپروژه نمونه\nکارت نمونه",
        "bridgeType": "object",
        "pywebviewType": "object",
        "fontLoaded": True,
        "stageCount": 5,
        "cardCount": 4,
    }


def complete_png(width=320, height=240):
    """Small valid RGB PNG built in stdlib; no GUI/Pillow dependency."""
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload +
                struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    # Filter type 0 plus opaque RGB black for each scanline.
    pixels = (b"\x00" + b"\x00\x00\x00" * width) * height
    return (gui.PNG_MAGIC + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(pixels, 9)) +
            chunk(b"IEND", b""))


class FakeJob:
    created = []
    diagnostic = None
    screenshot_bytes = None
    write_report = True
    exit_code = None
    native_done = True

    def __init__(self, executable, cwd, env):
        self.executable = executable
        self.cwd = cwd
        self.env = env
        self.pid = 4242
        self.closed = False
        type(self).created.append(self)
        if type(self).write_report:
            report = type(self).diagnostic
            if report is None:
                report = passing_diagnostic()
            if type(self).screenshot_bytes is not None:
                report = {**report, "screenshot": {"done": type(self).native_done}}
                Path(env["MADAR_QA_SCREENSHOT"]).write_bytes(type(self).screenshot_bytes)
            Path(env["MADAR_QA_REPORT"]).write_text(json.dumps(report), encoding="utf-8")

    def poll(self):
        return type(self).exit_code

    def stop(self):
        self.closed = True


class GuiSmokeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gui-smoke-test-only-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = self.root / "release"
        self.release.mkdir()
        self.exe = self.release / "Madar-Desk-v1.0-rc1.exe"
        self.exe.write_bytes(b"placeholder fixture; never executed")
        FakeJob.created = []
        FakeJob.diagnostic = None
        FakeJob.screenshot_bytes = None
        FakeJob.write_report = True
        FakeJob.exit_code = None
        FakeJob.native_done = True

    def run_fake(self, **kwargs):
        return gui.run_smoke(self.exe, launcher=FakeJob, release_root=self.release,
                             base_env={"APPDATA": "C:\\Users\\real\\AppData\\Roaming",
                                       "LOCALAPPDATA": "C:\\Users\\real\\AppData\\Local",
                                       "MADAR_QA_REPORT": "C:\\NeverTouch.json",
                                       "MADAR_QA_SCREENSHOT": "C:\\NeverTouch.png"},
                             **kwargs)

    def test_fake_report_pass_and_owned_job_closed(self):
        output = self.run_fake()
        self.assertEqual(output["status"], "PASS")
        self.assertEqual(len(FakeJob.created), 1)
        job = FakeJob.created[0]
        self.assertTrue(job.closed)
        self.assertEqual(job.pid, output["pid"])
        self.assertEqual(job.env["MADAR_QA_VIEW"], "sample-project")
        self.assertNotIn("MADAR_QA_SCREENSHOT", job.env)
        self.assertNotEqual(job.env["APPDATA"], "C:\\Users\\real\\AppData\\Roaming")
        self.assertNotEqual(job.env["LOCALAPPDATA"], "C:\\Users\\real\\AppData\\Local")
        self.assertTrue(Path(job.env["APPDATA"]).is_relative_to(Path(job.env["MADAR_QA_REPORT"]).parent))
        self.assertTrue(Path(job.env["TEMP"]).is_relative_to(Path(job.env["MADAR_QA_REPORT"]).parent))
        self.assertFalse(Path(job.env["APPDATA"]).exists())
        self.assertFalse(Path(job.env["MADAR_QA_REPORT"]).exists())
        self.assertEqual(gui.validate_report(passing_diagnostic())["visible_cards"]["status"], "PASS")

    def test_no_report_from_early_exit_is_fail_and_lifecycle_stops(self):
        FakeJob.write_report = False
        FakeJob.exit_code = 42
        result = self.run_fake(timeout=8)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("code 42", result["reason"])
        self.assertTrue(FakeJob.created[-1].closed)
        self.assertEqual(result["checks"], {})

    def test_missing_card_count_is_unverified_and_fails_not_false_pass(self):
        FakeJob.diagnostic = {k: v for k, v in passing_diagnostic().items() if k != "cardCount"}
        result = self.run_fake()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["checks"]["visible_cards"]["status"], "UNVERIFIED")
        self.assertEqual(result["checks"]["board_columns"]["status"], "PASS")

    def test_false_bridge_or_font_fails(self):
        broken = passing_diagnostic()
        broken.update(bridgeType="undefined", fontLoaded=False, cardCount=0)
        FakeJob.diagnostic = broken
        result = self.run_fake()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["checks"]["native_bridge"]["status"], "FAIL")
        self.assertEqual(result["checks"]["font_loaded"]["status"], "FAIL")
        self.assertEqual(result["checks"]["visible_cards"]["status"], "FAIL")

    def test_invalid_json_report_does_not_claim_success(self):
        diagnostics = self.root / "test-bad.json"
        diagnostics.write_text("{broken", encoding="utf-8")
        self.assertIsNone(gui._parse_report(diagnostics))
        diagnostics.write_text(json.dumps([]), encoding="utf-8")
        with self.assertRaises(gui.SmokeError):
            gui._parse_report(diagnostics)

    def test_screenshot_requested_requires_native_success_and_valid_png_header(self):
        # Full PNG CRC, zlib stream and IEND are required. Pixel quality and
        # screen semantics remain separate visual-review tasks.
        FakeJob.screenshot_bytes = complete_png()
        parent = self.root / "artifacts"
        parent.mkdir()
        # Normal Windows TEMP often lives *inside* real LOCALAPPDATA.
        # For this artificial fixture, model a different user's protected
        # profile, so artifact saving itself remains outside protected paths.
        with mock.patch.dict(os.environ, {
            "APPDATA": str(self.root / "protected-roaming"),
            "LOCALAPPDATA": str(self.root / "protected-local"),
        }):
            result = self.run_fake(screenshot=True, output_dir=parent)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["checks"]["screenshot"]["status"], "PASS")
        self.assertEqual(result["checks"]["screenshot"]["evidence"]["verified_png"]["width"], 320)
        self.assertTrue((Path(result["artifacts"]) / "diagnostics.json").is_file())
        self.assertTrue((Path(result["artifacts"]) / "screenshot.png").is_file())
        self.assertFalse(Path(FakeJob.created[-1].env["APPDATA"]).exists())
        FakeJob.screenshot_bytes = b"not-png"
        result = self.run_fake(screenshot=True)
        self.assertEqual(result["checks"]["screenshot"]["status"], "FAIL")

    def test_native_false_with_complete_png_is_warning_but_pass(self):
        FakeJob.screenshot_bytes = complete_png()
        FakeJob.native_done = False
        outcome = self.run_fake(screenshot=True)
        self.assertEqual(outcome["status"], "PASS")
        screenshot = outcome["checks"]["screenshot"]
        self.assertEqual(screenshot["status"], "PASS")
        self.assertEqual(screenshot["evidence"]["native_done"], False)
        self.assertEqual(screenshot["evidence"]["verified_png"]["height"], 240)
        self.assertIn("screenshot.done=false", screenshot["note"])

    def test_truncated_or_bad_crc_png_never_passes(self):
        valid = complete_png()
        for payload in (valid[:-6], valid[:-1], valid.replace(b"IHDR", b"abcd", 1), valid + b"x"):
            with self.subTest(size=len(payload)):
                FakeJob.screenshot_bytes = payload
                FakeJob.native_done = False
                result = self.run_fake(screenshot=True)
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["checks"]["screenshot"]["status"], "FAIL")

    def test_screenshot_missing_when_requested_is_explicit_failure(self):
        result = self.run_fake(screenshot=True)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["checks"]["screenshot"]["status"], "FAIL")

    def test_only_release_executable_is_allowed(self):
        outside = self.root / "not-release.exe"
        outside.write_bytes(b"x")
        with self.assertRaises(gui.SmokeError):
            gui.safe_exe_path(outside, release_root=self.release)
        with self.assertRaises(FileNotFoundError):
            gui.safe_exe_path(self.release / "missing.exe", release_root=self.release)
        self.assertEqual(gui.safe_exe_path(self.exe, release_root=self.release), self.exe)
        with self.assertRaises(gui.SmokeError):
            gui.run_smoke(self.exe, timeout=300, launcher=FakeJob, release_root=self.release)

    def test_output_folder_rejects_real_appdata_and_release(self):
        with mock.patch.dict(os.environ, {"APPDATA": str(self.root / "RealProfile"),
                                          "LOCALAPPDATA": str(self.root / "RealLocal")}):
            (self.root / "RealProfile").mkdir()
            (self.root / "RealLocal").mkdir()
            with self.assertRaises(gui.SmokeError):
                gui._safe_output_parent(self.root / "RealProfile")
            with self.assertRaises(gui.SmokeError):
                gui._safe_output_parent(self.root / "RealLocal")
        self.assertTrue(self.release.exists())
        # PROJECT/release is also always protected regardless of test fixtures.
        with self.assertRaises(gui.SmokeError):
            gui._safe_output_parent(gui.PROJECT / "release")

    def test_isolated_environment_does_not_mutate_original_keys(self):
        with tempfile.TemporaryDirectory(prefix="env-madar-") as directory:
            previous = {"APPDATA": "REAL-A", "LOCALAPPDATA": "REAL-B",
                        "MADAR_QA_THEME": "dark", "MADAR_QA_VIEW": "old",
                        "MADAR_QA_REPORT": "REAL-REPORT"}
            untouched = previous.copy()
            env = gui.isolated_environment(previous, Path(directory), screenshot=True)
            self.assertEqual(previous, untouched)
            self.assertEqual(env["MADAR_QA_VIEW"], "sample-project")
            self.assertNotIn("MADAR_QA_THEME", env)
            self.assertNotEqual(env["MADAR_QA_REPORT"], "REAL-REPORT")
            self.assertTrue(env["MADAR_QA_SCREENSHOT"].endswith("screenshot.png"))

    def test_exception_from_launcher_does_not_edit_existing_environment(self):
        def fails(_exe, _cwd, _env):
            raise gui.SmokeError("mock launch failed before process creation")
        with self.assertRaisesRegex(gui.SmokeError, "mock launch failed"):
            gui.run_smoke(self.exe, release_root=self.release, launcher=fails,
                          base_env={"APPDATA": "original", "LOCALAPPDATA": "original"})
        self.assertEqual(len(FakeJob.created), 0)

    def test_interactive_fake_report_fullscreen_protocol_and_cleanup(self):
        payload = passing_diagnostic()
        payload["url"] = "http://127.0.0.1:49371/index.html"
        payload["uiFlow"] = {
            name: {"pass": True, "observed": (1 if name == "task_saved_to_host" else True)}
            for name in gui.INTERACTIVE_REQUIRED
        }
        FakeJob.diagnostic = payload
        result = self.run_fake(interactive=True)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(FakeJob.created[-1].closed)
        self.assertEqual(FakeJob.created[-1].env["MADAR_QA_INTERACTION"], "1")
        self.assertEqual(FakeJob.created[-1].env["MADAR_QA_VIEW"], "sample-project")
        self.assertEqual(result["checks"]["interactive_accounting_workspace_fullscreen"]["status"], "PASS")
        self.assertEqual(result["checks"]["interactive_accounting_currency_rial_display"]["status"], "PASS")
        self.assertEqual(result["checks"]["interactive_standalone_currency_rial_head"]["status"], "PASS")
        self.assertEqual(result["checks"]["interactive_standalone_unchanged_after_task"]["status"], "PASS")
        self.assertEqual(result["checks"]["interactive_finance_unchanged_after_task"]["status"], "PASS")
        self.assertFalse(Path(FakeJob.created[-1].env["APPDATA"]).exists())

    def test_interactive_missing_or_legacy_diagnostics_fail_without_real_exe(self):
        # A previous candidate with obsolete accounting-dialog QA output must
        # NOT be reported as successful, even if every generic check is green.
        no_flow = self.run_fake(interactive=True)
        self.assertEqual(no_flow["status"], "FAIL")
        self.assertEqual(no_flow["checks"]["interactive_accounting_workspace_opens"]["status"], "FAIL")
        FakeJob.diagnostic = {
            **passing_diagnostic(),
            "uiFlow": {
                "accounting_dialog_accessible": {"pass": True, "observed": True},
                "accounting_dialog_opens": {"pass": True, "observed": True},
                "task_saved_to_host": {"pass": True, "observed": 1},
            },
        }
        legacy = self.run_fake(interactive=True)
        self.assertEqual(legacy["status"], "FAIL")
        self.assertEqual(legacy["checks"]["interactive_accounting_workspace_fullscreen"]["status"], "FAIL")
        self.assertEqual(legacy["checks"]["interactive_standalone_snapshot_captured"]["status"], "FAIL")
        self.assertTrue(all(job.closed for job in FakeJob.created))

    def test_index_html_return_only_allowed_in_interactive_flow(self):
        values = passing_diagnostic()
        values["url"] = "http://127.0.0.1:49371/index.html"
        self.assertEqual(gui.validate_report(values)["loopback"]["status"], "FAIL")
        self.assertEqual(gui.validate_report(values, interactive=True)["loopback"]["status"], "PASS")
        values["url"] = "http://127.0.0.1:49371/accounting.html"
        self.assertEqual(gui.validate_report(values, interactive=True)["loopback"]["status"], "FAIL")

    def test_old_toman_flow_is_rejected_even_with_valid_task_and_host(self):
        values = passing_diagnostic()
        values["uiFlow"] = {name: {"pass": True, "observed": True}
                            for name in gui.INTERACTIVE_REQUIRED
                            if name not in ("task_saved_to_host", "standalone_currency_rial_head")}
        values["uiFlow"]["task_saved_to_host"] = {"pass": True, "observed": 1}
        values["uiFlow"]["accounting_currency_default_toman"] = {"pass": True, "observed": True}
        FakeJob.diagnostic = values
        result = self.run_fake(interactive=True)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["checks"]["interactive_standalone_currency_rial_head"]["status"], "FAIL")
        self.assertTrue(FakeJob.created[-1].closed)

    def test_interactive_failure_when_finance_safety_claim_is_false(self):
        values = passing_diagnostic()
        values["uiFlow"] = {
            name: {"pass": True, "observed": (1 if name == "task_saved_to_host" else True)}
            for name in gui.INTERACTIVE_REQUIRED
        }
        values["uiFlow"]["finance_unchanged_after_task"] = {"pass": False, "observed": False}
        FakeJob.diagnostic = values
        result = self.run_fake(interactive=True)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["checks"]["interactive_finance_unchanged_after_task"]["status"], "FAIL")
        self.assertTrue(FakeJob.created[-1].closed)

    def test_interactive_failure_when_independent_ledger_changes(self):
        values = passing_diagnostic()
        values["uiFlow"] = {
            name: {"pass": True, "observed": (1 if name == "task_saved_to_host" else True)}
            for name in gui.INTERACTIVE_REQUIRED
        }
        values["uiFlow"]["standalone_unchanged"] = {"pass": False, "observed": False}
        FakeJob.diagnostic = values
        result = self.run_fake(interactive=True)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["checks"]["interactive_standalone_unchanged"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
