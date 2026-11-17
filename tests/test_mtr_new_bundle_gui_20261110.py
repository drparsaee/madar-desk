"""Synthetic-only contract/security tests for SHA-pinned new Madar QA GUI.

No EXE, installed Madar, user profile, Taraz service, network or ledger starts.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / "scripts" / "qa_mtr_new_bundle_gui_20261110.py"
SPEC = importlib.util.spec_from_file_location("new_madar_gui_qatest", FILE)
QA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QA)


class SyntheticBundleGuiContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-qa-bundled-taraz-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pending = self.root / "AppData" / "Local" / "Madar-Taraz-Bridge" / "pending"
        self.pending.mkdir(parents=True)
        self.task = {
            "id": "synthetic-card", "projectId": "synthetic-project",
            "title": "Synthetic printed packaging",
        }
        self.rid = "a" * 32
        self.item = {
            "schema": 1, "source": "madar", "id": self.rid,
            "taskId": self.task["id"], "projectId": self.task["projectId"],
            "title": self.task["title"],
            "createdUtc": "2026-11-10T13:00:00+00:00",
        }

    def save(self, record=None):
        file = self.pending / (self.rid + ".json")
        file.write_text(json.dumps(record if record is not None else self.item),
                        encoding="utf8")
        return file

    def test_exact_genuine_synthetic_proposal(self):
        self.save()
        self.assertEqual(QA._read_proposal(self.pending, self.task), self.item)

    def test_absent_duplicate_extra_files_rejected(self):
        with self.assertRaises(AssertionError):
            QA._read_proposal(self.pending, self.task)
        self.save()
        (self.pending / "another.tmp").write_text("noise", encoding="ascii")
        with self.assertRaises(AssertionError):
            QA._read_proposal(self.pending, self.task)

    def test_wrong_identity_and_financial_claims_rejected(self):
        for mutation in (
            {"id": "b" * 32}, {"id": "../../wrong"},
            {"taskId": "cross-task"}, {"projectId": "other-project"},
            {"title": "changed"}, {"schema": 2}, {"schema": True},
            {"source": "taraz"}, {"ledgerEntryId": "official-sounding"},
            {"amountRial": 100000},
        ):
            with self.subTest(mutation=mutation):
                self.save({**self.item, **mutation})
                with self.assertRaises(AssertionError):
                    QA._read_proposal(self.pending, self.task)

    def test_malformed_duplicate_and_oversized_rejected(self):
        file = self.save()
        invalids = (
            b"{", b"null", b"[]", b"\xff",
            file.read_bytes().replace(b'"schema": 1',
                                      b'"schema": 1, "schema": 1'),
            b" " * 32769,
        )
        for raw in invalids:
            with self.subTest(raw=raw[:12]):
                file.write_bytes(raw)
                with self.assertRaises((AssertionError, ValueError, UnicodeError)):
                    QA._read_proposal(self.pending, self.task)

    def test_symlinked_proposal_and_pending_rejected(self):
        with tempfile.TemporaryDirectory(prefix="external-synthetic-") as external:
            target = Path(external) / (self.rid + ".json")
            target.write_text(json.dumps(self.item), encoding="utf8")
            linked = self.pending / target.name
            try:
                linked.symlink_to(target)
            except OSError:
                self.skipTest("File symlink unavailable on this Windows setup")
            with self.assertRaises(PermissionError):
                QA._read_proposal(self.pending, self.task)

    def test_nonrelease_hash_pin_and_manifest_fail_closed_before_launch(self):
        with (patch.object(QA, "_hash", return_value="0" * 64),
              patch.object(QA, "_regular", return_value=None)):
            with self.assertRaisesRegex(PermissionError, "digest mismatch"):
                QA.verify_bundle()
        with patch.object(QA, "verify_bundle", side_effect=PermissionError("pin mismatch")):
            with patch.object(QA, "_module") as read_existing:
                with self.assertRaisesRegex(PermissionError, "pin mismatch"):
                    QA.run()
                read_existing.assert_not_called()

    def test_zero_profile_fallback_on_wrong_path(self):
        with tempfile.TemporaryDirectory(prefix="wrong-real-folder-") as external:
            wrong = Path(external) / "pending"
            wrong.mkdir()
            self.assertRaises(AssertionError, QA._read_proposal, wrong, self.task)

    def test_legacy_gui_readback_rejects_invalid_id_before_uia(self):
        for invalid in (None, "", "A" * 32, "../", "a" * 31, 14):
            with self.subTest(value=invalid):
                with self.assertRaises(ValueError):
                    QA._legacy_ui_readback(object(), 999, invalid)

    def test_temporary_directory_owned_cleanup_even_on_exception(self):
        captured = None
        with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
            with QA._disposable_root() as root:
                captured = root
                self.assertTrue(root.is_dir())
                (root / "qa.txt").write_text("synthetic", encoding="utf8")
                raise RuntimeError("synthetic failure")
        self.assertIsNotNone(captured)
        self.assertFalse(captured.exists())

    def test_current_exe_never_points_to_installed_madar(self):
        self.assertEqual(QA.EXE.name,
                         "Madar-Taraz-Connection-QA-20261110-NONRELEASE.exe")
        self.assertIn("MTR-MADAR-TARAZ-QA-BUNDLE", str(QA.EXE))
        self.assertEqual(len(QA.SHA_EXE), 64)
        self.assertIn("NONRELEASE", QA.EXE.name)


if __name__ == "__main__":
    unittest.main()
