"""Contract tests for the optional installed-GUI proposal handoff callback.

All fixtures are synthetic. These tests do not start Madar/Taraz executables,
reach the network or touch an operational user profile.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "qa_installed_madar_gui_bridge_20261110.py"
SPEC = importlib.util.spec_from_file_location("mtr_madar_gui_callback_qa", SCRIPT)
QA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QA)


class CallbackHandoffContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-qa-taraz-bridge-ui-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local = self.root / "AppData" / "Local"
        self.bridge = self.local / "Madar-Taraz-Bridge"
        self.pending = self.bridge / "pending"
        self.pending.mkdir(parents=True)
        self.task = {"id": "qa-task", "projectId": "qa-project", "title": "QA title"}
        self.proposal_id = "a" * 32
        (self.pending / (self.proposal_id + ".json")).write_text(json.dumps({
            "schema": 1, "source": "madar", "id": self.proposal_id,
            "taskId": self.task["id"], "projectId": self.task["projectId"],
            "title": self.task["title"], "createdUtc": "2026-11-10T12:00:00+00:00"
        }), encoding="utf-8")
        self.validated = QA._read_one_disposable_pending(self.local, self.task)

    def notify(self, callback, **overrides):
        arguments = dict(sandbox_root=self.root, bridge_root=self.bridge,
                         verified=self.validated, expected_task=self.task)
        arguments.update(overrides)
        return QA._notify_disposable_proposal_ready(callback, **arguments)

    def test_handoff_only_verified_exact_bridge_and_immutable_values(self):
        observed = []

        def capture(bridge, identifier, task):
            self.assertEqual(bridge, self.bridge)
            self.assertTrue(bridge.is_dir())
            self.assertTrue((bridge / "pending" / (identifier + ".json")).is_file())
            self.assertEqual(identifier, self.proposal_id)
            self.assertEqual(dict(task), self.task)
            self.assertEqual(set(task), {"id", "title", "projectId"})
            with self.assertRaises(TypeError):
                task["id"] = "other"
            observed.append(identifier)
            return "returned-value-must-not-affect-report"

        self.assertEqual(self.notify(capture), "returned-value-must-not-affect-report")
        self.assertEqual(observed, [self.proposal_id])

    def test_rejects_callback_when_send_mode_not_selected(self):
        callback = lambda *_: None
        for arguments in ({}, {"inspect_navigation": True}):
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(ValueError, "requires send_once_ui"):
                    QA.run(on_disposable_proposal_ready=callback, **arguments)
        with self.assertRaisesRegex(TypeError, "must be callable"):
            QA.run(send_once_ui=True, on_disposable_proposal_ready=object())

    def test_refuses_callback_for_unverified_or_extra_files(self):
        called = []
        with self.assertRaisesRegex(AssertionError, "validated proposal"):
            self.notify(lambda *_: called.append(1),
                        verified={**self.validated, "pendingProposalCount": 2})
        (self.pending / ("b" * 32 + ".json")).write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "exactly one"):
            self.notify(lambda *_: called.append(1))
        self.assertEqual(called, [])

    def test_refuses_outside_or_mismatched_bridge_root(self):
        called = []
        with tempfile.TemporaryDirectory(prefix="outside-qa-") as outside:
            external = Path(outside)
            for invalid in (external, self.root, self.local, self.bridge.parent):
                with self.subTest(path=invalid):
                    with self.assertRaises(PermissionError):
                        self.notify(lambda *_: called.append(1),
                                    bridge_root=invalid)
        self.assertEqual(called, [])

    def test_invalid_callable_and_missing_pending_are_fail_closed(self):
        with self.assertRaises(TypeError):
            self.notify("not-a-callable")
        (self.pending / (self.proposal_id + ".json")).unlink()
        with self.assertRaises(AssertionError):
            self.notify(lambda *_: self.fail("must not be reached"))

    def test_symlinked_bridge_does_not_reach_callback(self):
        with tempfile.TemporaryDirectory(prefix="outside-qa-") as outside:
            (self.pending / (self.proposal_id + ".json")).unlink()
            self.pending.rmdir()
            self.bridge.rmdir()
            try:
                self.bridge.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Windows symlink privilege is unavailable")
            with self.assertRaises(PermissionError):
                self.notify(lambda *_: self.fail("must not be reached"))


if __name__ == "__main__":
    unittest.main()
