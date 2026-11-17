"""Fail-closed unit checks for the QA-only current Madar WebView2 harness.

Tests never launch the EXE, touch a real profile, operate finance, or network.
Actual executable/GUI acceptance is the separately invoked script.
"""
from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts import qa_mtr_current_bundled_gui_20261110 as qa


class QABundledGuiGuardTests(unittest.TestCase):
    def test_exact_binary_identity_bound_to_approved_external_run(self):
        self.assertEqual(
            qa.EXE.name, "Madar-Taraz-Connection-QA-20261110-NONRELEASE.exe")
        self.assertEqual(len(qa.EXPECTED_SHA256), 64)
        self.assertIn("run-20261110-144128-10416-207ce8ba",
                      str(qa.EXE))
        self.assertEqual(qa.METHODS, (
            "tarazIntegrationOpenLocal", "tarazIntegrationPrepare",
            "tarazIntegrationQueue", "tarazIntegrationHistory"))

    def test_rejects_changed_binary_without_starting(self):
        with tempfile.TemporaryDirectory(prefix="mtr-bundled-guard-") as folder:
            replacement = Path(folder) / "not-approved.exe"
            replacement.write_bytes(b"MZ" + b"synthetic nonbinary")
            with (patch.object(qa, "EXE", replacement),
                  patch.object(qa.subprocess, "Popen") as launch):
                with self.assertRaisesRegex(PermissionError, "pin mismatch"):
                    qa.verify_pinned_executable()
                launch.assert_not_called()

    def test_bad_manual_send_argument_fails_before_launch(self):
        with patch.object(qa, "verify_pinned_executable") as verify:
            with self.assertRaises(TypeError):
                qa.run(send_once_ui="yes")
            verify.assert_not_called()

    def test_ui_settings_probe_never_invokes_taraz_launcher(self):
        class FakeUI:
            def _run_owned_uia(self, pid, script, *, timeout):
                self_pid = pid
                self.assertion_result = (self_pid, script, timeout)
                return {"settingsModalOpened": True,
                        "tarazSettingsTabOpened": True}
        fake = FakeUI()
        answer = qa._settings_probe(fake, 12345)
        self.assertTrue(answer["settingsModalOpened"])
        self.assertEqual(fake.assertion_result[0], 12345)
        script = fake.assertion_result[1]
        self.assertIn("InvokeOnly 'تنظیمات مدار'", script)
        self.assertIn("InvokeOnly 'اتصال تراز'", script)
        self.assertNotIn("tarazIntegrationOpenLocal", script)
        self.assertNotIn("InvokeOnly 'بازکردن تراز'", script)
        self.assertNotIn("InvokeOnly 'ارسال به تراز'", script)

    def test_disallows_second_qa_instance(self):
        class AlreadyRunning:
            info = {"name": qa.EXE.name, "exe": str(qa.EXE)}
            @staticmethod
            def is_running():
                return True
        with patch("psutil.process_iter", return_value=[AlreadyRunning()]):
            with self.assertRaisesRegex(RuntimeError, "already running"):
                qa._assert_no_other_qa_instance()

    def test_review_history_mode_is_mutually_exclusive(self):
        with patch.object(qa, "verify_pinned_executable") as verify:
            with self.assertRaisesRegex(ValueError, "Select exactly one"):
                qa.run(send_once_ui=True, reviewed_history_ui=True)
            verify.assert_not_called()

    def test_invalid_review_mode_flag_fails_before_launch(self):
        with patch.object(qa, "verify_pinned_executable") as verify:
            with self.assertRaises(TypeError):
                qa.run(reviewed_history_ui="true")
            verify.assert_not_called()

    def test_history_uia_script_scoped_to_owned_window(self):
        class FakeUI:
            def _run_owned_uia(self, pid, script, *, timeout):
                self.args = (pid, script, timeout)
                return {"reviewedHistoryRendered": True}
        fake = FakeUI()
        self.assertTrue(qa._history_ui_readback(fake, 12345, "a" * 32)
                        ["reviewedHistoryRendered"])
        pid, script, timeout = fake.args
        self.assertEqual(pid, 12345)
        self.assertEqual(timeout, 35)
        self.assertIn("FromHandle([IntPtr]__HWND__)", script)
        self.assertIn("Button 'وضعیت تراز'", script)
        self.assertIn("بررسی‌شده در تراز (غیرمالی)", script)
        self.assertIn("HISTORY_RESULT_ALREADY_VISIBLE_BEFORE_USER_CLICK", script)
        self.assertIn("sameVisibleNodeContainsReviewedAndRequestId", script)
        self.assertNotIn("InvokeOnly 'بازکردن تراز'", script)
        self.assertNotIn("tarazIntegrationOpenLocal", script)

    def test_history_refuses_malformed_id_before_uia(self):
        class FakeUI:
            def _run_owned_uia(self, *args, **kwargs):
                self.fail("Must not invoke UIA")
        with self.assertRaisesRegex(ValueError, "exact request ID"):
            qa._history_ui_readback(FakeUI(), 10, "../bad")

    def _synthetic_review_fixture(self, root):
        bridge = root / "AppData" / "Local" / "Madar-Taraz-Bridge"
        pending = bridge / "pending"
        pending.mkdir(parents=True)
        task = {"id": "qa-task", "projectId": "qa-project",
                "title": "Synthetic readback fixture"}
        request = {"schema": 1, "source": "madar", "id": "a" * 32,
                   "taskId": task["id"], "projectId": task["projectId"],
                   "title": task["title"],
                   "createdUtc": "2026-11-10T00:00:00+00:00"}
        (pending / (request["id"] + ".json")).write_text(
            json.dumps(request, ensure_ascii=False), encoding="utf-8")
        return bridge, task, request

    def test_detached_synthetic_review_and_native_reader_uses_only_sandbox(self):
        with tempfile.TemporaryDirectory(prefix="madar-qa-bundled-taraz-") as path:
            root = Path(path)
            bridge, task, request = self._synthetic_review_fixture(root)
            result = qa._review_disposable_proposal(root, task, request)
            self.assertTrue(result["nativePythonReaderObservedReviewed"])
            self.assertTrue(result["nonfinancialReviewReceipt"])
            self.assertFalse(result["financialEventCreated"])
            self.assertTrue((bridge / "reviewed" / (request["id"] + ".json")).is_file())
            self.assertFalse((bridge / "pending" / (request["id"] + ".json")).exists())
            self.assertFalse((root / "AppData" / "Local" / "MadarDesk").exists())

    def test_review_refuses_non_sandbox_prefix(self):
        with tempfile.TemporaryDirectory(prefix="unrelated-qa-") as path:
            root = Path(path)
            _, task, request = self._synthetic_review_fixture(root)
            with self.assertRaisesRegex(PermissionError, "sandbox"):
                qa._review_disposable_proposal(root, task, request)

    def test_review_refuses_mismatched_task_without_mutation(self):
        with tempfile.TemporaryDirectory(prefix="madar-qa-bundled-taraz-") as path:
            root = Path(path)
            bridge, task, request = self._synthetic_review_fixture(root)
            with self.assertRaisesRegex(ValueError, "synthetic card"):
                qa._review_disposable_proposal(
                    root, {**task, "id": "other-task"}, request)
            self.assertTrue((bridge / "pending" / (request["id"] + ".json")).is_file())
            self.assertFalse((bridge / "reviewed").exists())

    def test_review_refuses_duplicate_pending_proposal(self):
        with tempfile.TemporaryDirectory(prefix="madar-qa-bundled-taraz-") as path:
            root = Path(path)
            bridge, task, request = self._synthetic_review_fixture(root)
            (bridge / "pending" / ("b" * 32 + ".json")).write_text(
                json.dumps({**request, "id": "b" * 32}), encoding="utf-8")
            with self.assertRaisesRegex(PermissionError, "one genuine"):
                qa._review_disposable_proposal(root, task, request)
            self.assertFalse((bridge / "reviewed").exists())


if __name__ == "__main__":
    unittest.main()
