"""Synthetic validation for installed-GUI-only Madar -> Taraz QA evidence.

No installed EXE is launched by these unit tests. The actual GUI interaction
is exercised separately through the --send-isolated-ui command.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "qa_installed_madar_gui_bridge_20261110.py"
SPEC = importlib.util.spec_from_file_location("mtr_madar_installed_gui_qa", SCRIPT)
QA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QA)


class DisposableProposalValidationTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory(prefix="madar-qa-taraz-bridge-ui-")
        self.addCleanup(self.sandbox.cleanup)
        self.root = Path(self.sandbox.name)
        self.local = self.root / "AppData" / "Local"
        self.local.mkdir(parents=True)
        self.pending = self.local / "Madar-Taraz-Bridge" / "pending"
        self.pending.mkdir(parents=True)
        self.task = {"id": "synthetic-card-01", "projectId": "p-sample",
                     "title": "Synthetic QA saved card"}
        self.record = {
            "schema": 1, "source": "madar", "id": "a" * 32,
            "taskId": self.task["id"], "projectId": self.task["projectId"],
            "title": self.task["title"], "createdUtc": "2026-11-10T12:00:00+00:00",
        }

    def save(self, record=None):
        path = self.pending / ("a" * 32 + ".json")
        path.write_text(json.dumps(self.record if record is None else record,
                                   ensure_ascii=False), encoding="utf-8")
        return path

    def test_accepts_one_exact_synthetic_schema_one_proposal(self):
        self.save()
        observed = QA._read_one_disposable_pending(self.local, self.task)
        self.assertEqual(observed["pendingProposalCount"], 1)
        self.assertEqual(observed["schema"], 1)
        self.assertTrue(observed["syntheticTaskIdMatched"])
        self.assertFalse(observed["containsExpenseOrLedger"])

    def test_rejects_absent_or_multiple_pending_files(self):
        with self.assertRaises(AssertionError):
            QA._read_one_disposable_pending(self.local, self.task)
        self.save()
        (self.pending / "unexpected.tmp").write_text("noise", encoding="ascii")
        with self.assertRaisesRegex(AssertionError, "one disposable pending"):
            QA._read_one_disposable_pending(self.local, self.task)

    def test_rejects_cross_card_fields_and_extra_finance(self):
        for replacement in (
            {"taskId": "other-synthetic-card"},
            {"projectId": "other-project"},
            {"title": "other title"},
            {"schema": 2},
            {"amountRial": "20000"},
            {"createdUtc": "2026-11-10T12:00:00+03:30"},
            {"id": "Z" * 32},
        ):
            with self.subTest(replacement=replacement):
                self.save({**self.record, **replacement})
                with self.assertRaises((AssertionError, ValueError)):
                    QA._read_one_disposable_pending(self.local, self.task)

    def test_rejects_duplicate_json_fields(self):
        self.save()
        file = self.pending / ("a" * 32 + ".json")
        raw = file.read_text(encoding="utf8")
        file.write_text(raw.replace('"schema": 1', '"schema": 1, "schema": 1'),
                        encoding="utf8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            QA._read_one_disposable_pending(self.local, self.task)

    def test_disallows_non_disposable_localappdata(self):
        with tempfile.TemporaryDirectory(prefix="not-madar-qa-") as wrong:
            local = Path(wrong) / "AppData" / "Local"
            local.mkdir(parents=True)
            with self.assertRaises(PermissionError):
                QA._read_one_disposable_pending(local, self.task)

    def test_disallows_symlinked_bridge_directory_if_supported(self):
        with tempfile.TemporaryDirectory(prefix="madar-ui-other-") as other:
            bridge = self.pending.parent
            self.pending.rmdir()
            bridge.rmdir()
            try:
                bridge.symlink_to(Path(other), target_is_directory=True)
            except OSError:
                self.skipTest("Windows symlink creation not available")
            with self.assertRaises(AssertionError):
                QA._read_one_disposable_pending(self.local, self.task)

    def test_ui_send_requires_exact_synthetic_target(self):
        for title in ("", "x" * 301):
            with self.subTest(title_length=len(title)):
                with self.assertRaises(ValueError):
                    QA._ui_send_once(1234, title)


if __name__ == "__main__":
    unittest.main()
