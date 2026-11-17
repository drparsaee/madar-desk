"""Negative security gates for the cross-app *synthetic-only* local UI cycle.

The full GUI click path is invoked separately by the QA script, never by this
unittest (to prevent accidental real/installed app launches during discovery).
"""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch
import os


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "qa_mtr_two_ui_local_cycle_20261110.py"
SPEC = importlib.util.spec_from_file_location("mtr_two_ui_local_cycle_qa", SCRIPT)
QA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QA)
GUI_SCRIPT = SCRIPT.with_name("qa_installed_madar_gui_bridge_20261110.py")
GUI_SPEC = importlib.util.spec_from_file_location("mtr_gui_window_wait_qa", GUI_SCRIPT)
GUI = importlib.util.module_from_spec(GUI_SPEC)
GUI_SPEC.loader.exec_module(GUI)


class CrossAppLocalCycleSafety(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-qa-taraz-bridge-ui-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bridge = self.root / "AppData" / "Local" / "Madar-Taraz-Bridge"
        self.pending = self.bridge / "pending"
        self.pending.mkdir(parents=True)
        self.task = {"id": "synthetic-card", "projectId": "synthetic-project",
                     "title": "Synthetic packaging request"}
        self.request_id = "a" * 32
        self.record = {
            "schema": 1, "source": "madar", "id": self.request_id,
            "taskId": self.task["id"], "projectId": self.task["projectId"],
            "title": self.task["title"], "createdUtc": "2026-11-10T00:00:00+00:00",
        }

    def save(self, data=None):
        path = self.pending / (self.request_id + ".json")
        path.write_text(json.dumps(self.record if data is None else data,
                                   ensure_ascii=False), encoding="utf-8")
        return path

    def test_only_exact_sandbox_root_is_eligible(self):
        root, local = QA._canonical_sandbox(self.bridge)
        self.assertEqual(root, self.root)
        self.assertEqual(local, self.root / "AppData" / "Local")

    def test_wrong_local_path_denied(self):
        with tempfile.TemporaryDirectory(prefix="unrelated-user-directory-") as wrong:
            folder = Path(wrong) / "AppData" / "Local" / "Madar-Taraz-Bridge"
            folder.mkdir(parents=True)
            with self.assertRaises(PermissionError):
                QA._canonical_sandbox(folder)

    def test_only_selected_saved_card_is_allowed(self):
        self.save()
        self.assertEqual(QA._read_qa_proposal(self.bridge, self.request_id, self.task),
                         self.record)
        for mismatch in ({"title": "changed"}, {"taskId": "other"},
                         {"projectId": "other"}, {"schema": 2},
                         {"source": "taraz"}, {"id": "b" * 32},
                         {"amountRial": "1000"}):
            with self.subTest(mismatch=mismatch):
                self.save({**self.record, **mismatch})
                with self.assertRaises(ValueError):
                    QA._read_qa_proposal(self.bridge, self.request_id, self.task)

    def test_invalid_id_and_missing_proposal_denied(self):
        for identifier in ("../", "A" * 32, "", "a" * 31, None):
            with self.subTest(identifier=identifier):
                with self.assertRaises(PermissionError):
                    QA._read_qa_proposal(self.bridge, identifier, self.task)
        with self.assertRaises(PermissionError):
            QA._read_qa_proposal(self.bridge, self.request_id, self.task)

    def test_duplicate_fields_denied(self):
        path = self.save()
        raw = path.read_text(encoding="utf-8").replace('"schema": 1',
                                                        '"schema": 1, "schema": 1')
        path.write_text(raw, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            QA._read_qa_proposal(self.bridge, self.request_id, self.task)

    def test_rejects_nonhex_path_traversal_and_bad_identifier_types(self):
        self.save()
        for identifier in ("../" + "a" * 32, "../pending", "a" * 32 + "/../",
                           "a" * 33, "A" * 32, "g" * 32, "a" * 31, "a" * 32 + "\x00",
                           1, False, ["a" * 32], Path("a" * 32)):
            with self.subTest(identifier=repr(identifier)):
                with self.assertRaises(PermissionError):
                    QA._read_qa_proposal(self.bridge, identifier, self.task)

    def test_rejects_oversized_proposal_before_parsing(self):
        path = self.pending / (self.request_id + ".json")
        path.write_bytes(b" " * 32769)
        with self.assertRaisesRegex(PermissionError, "expected pending"):
            QA._read_qa_proposal(self.bridge, self.request_id, self.task)

    def test_rejects_malformed_json_and_wrong_top_level(self):
        path = self.pending / (self.request_id + ".json")
        for raw in (b"{", b"not json", b"\xff", b"[]", b"null", b"{}",
                    b'{"schema":1,"source":"madar"}'):
            with self.subTest(raw=repr(raw)):
                path.write_bytes(raw)
                with self.assertRaises((ValueError, TypeError, UnicodeError)):
                    QA._read_qa_proposal(self.bridge, self.request_id, self.task)

    def test_rejects_symlinked_proposal_file_without_reading_target(self):
        with tempfile.TemporaryDirectory(prefix="external-synthetic-qa-") as unrelated:
            external = Path(unrelated) / "synthetic.json"
            external.write_text(json.dumps(self.record), encoding="utf8")
            linked = self.pending / (self.request_id + ".json")
            try:
                linked.symlink_to(external)
            except OSError:
                self.skipTest("Windows file symlinks unavailable")
            with self.assertRaises(PermissionError):
                QA._read_qa_proposal(self.bridge, self.request_id, self.task)

    def test_rejects_actual_outside_path_escape(self):
        with tempfile.TemporaryDirectory(prefix="outside-qa-") as external:
            wrong_root = Path(external) / "AppData" / "Local" / "Madar-Taraz-Bridge"
            wrong_root.mkdir(parents=True)
            with self.assertRaises(PermissionError):
                QA._canonical_sandbox(wrong_root)
            with self.assertRaises((PermissionError, FileNotFoundError)):
                QA._canonical_sandbox(self.bridge / "pending" / "../../../../outside")

    def test_rejects_symlink_alias_to_real_qa_bridge(self):
        """Check the supplied alias, not merely its resolved target path."""
        with tempfile.TemporaryDirectory(prefix="synthetic-outside-alias-") as external:
            alias = Path(external) / "alias-to-qa-bridge"
            try:
                alias.symlink_to(self.bridge, target_is_directory=True)
            except OSError:
                self.skipTest("Windows directory symlinks unavailable")
            with self.assertRaises(PermissionError):
                QA._canonical_sandbox(alias)

    def test_rejects_linked_pending_directory(self):
        """The pending parent itself must not be a link to another folder."""
        with tempfile.TemporaryDirectory(prefix="external-synthetic-pending-") as external:
            outside = Path(external)
            (outside / (self.request_id + ".json")).write_text(
                json.dumps(self.record), encoding="utf8")
            self.pending.rmdir()
            try:
                self.pending.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Windows directory symlinks unavailable")
            with self.assertRaises(PermissionError):
                QA._read_qa_proposal(self.bridge, self.request_id, self.task)

    def test_rejects_missing_or_invalid_created_utc(self):
        """Proposal must carry a parsable timestamp with an explicit UTC zone."""
        for bad_timestamp in (None, "", 0, "2026-11-10T12:00:00",
                              "2026-11-10T12:00:00+03:30", "not-a-time",
                              "2026-11-10T12:00:00+00:00" * 3):
            with self.subTest(createdUtc=bad_timestamp):
                self.save({**self.record, "createdUtc": bad_timestamp})
                with self.assertRaises(ValueError):
                    QA._read_qa_proposal(self.bridge, self.request_id, self.task)

    def test_callback_failure_propagates_through_orchestrator_and_mock_qa_cleans(self):
        """Pure mocks: no installed EXE/browser or real reviewer is executed."""
        temp_roots = []
        callback_count = []

        def fake_gui_run(*, send_once_ui, on_disposable_proposal_ready):
            self.assertTrue(send_once_ui)
            with tempfile.TemporaryDirectory(prefix="madar-qa-taraz-bridge-ui-") as temp:
                root = Path(temp)
                temp_roots.append(root)
                bridge = root / "AppData" / "Local" / "Madar-Taraz-Bridge"
                pending = bridge / "pending"
                pending.mkdir(parents=True)
                (pending / (self.request_id + ".json")).write_text(
                    json.dumps(self.record), encoding="utf8")
                self.assertTrue((pending / (self.request_id + ".json")).is_file())
                callback_count.append(1)
                return on_disposable_proposal_ready(
                    bridge, self.request_id, MappingProxyType(dict(self.task)))

        fake_gui = SimpleNamespace(run=fake_gui_run)
        with (patch.object(QA, "_load_script", return_value=fake_gui) as loader,
              patch.object(QA, "_review_with_installed_taraz_and_real_browser",
                           side_effect=RuntimeError("synthetic reviewer failure")) as review):
            with self.assertRaisesRegex(RuntimeError, "synthetic reviewer failure"):
                QA.run(decision="reviewed")
            loader.assert_called_once()
            review.assert_called_once()
        self.assertEqual(callback_count, [1])
        self.assertEqual(len(temp_roots), 1)
        self.assertFalse(temp_roots[0].exists(), "Mock disposable sandbox leaked on callback failure")

    def test_gui_window_wait_retries_same_pid_without_unrelated_fallback(self):
        # A built-in WebView diagnostic can precede the native HWND becoming
        # visible; the only valid candidate comes from a QA-owned snapshot.
        with patch.object(GUI, "_visible_owned_qa_windows_once",
                          side_effect=[[], [], [(1920 * 1080, 424242)]]) as scan:
            hwnd = GUI._owned_qa_hwnd(os.getpid(), wait_seconds=0.3, poll_seconds=0.001)
        self.assertEqual(hwnd, 424242)
        self.assertEqual(scan.call_count, 3)
        self.assertEqual(scan.call_args.args, (os.getpid(),))

    def test_gui_window_wait_refuses_ambiguous_and_missing_owned_windows(self):
        with patch.object(GUI, "_visible_owned_qa_windows_once",
                          return_value=[(10000, 101), (20000, 202)]):
            with self.assertRaisesRegex(RuntimeError, "Ambiguous QA-owned windows"):
                GUI._owned_qa_hwnd(os.getpid(), wait_seconds=0)
        with patch.object(GUI, "_visible_owned_qa_windows_once", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "No large visible QA-owned"):
                GUI._owned_qa_hwnd(os.getpid(), wait_seconds=0)

    def test_gui_window_wait_rejects_invalid_pid_and_budgets(self):
        for pid, seconds, poll in ((0, 1, 0.25), (-5, 1, 0.25),
                                   (True, 1, 0.25), (os.getpid(), -1, 0.25),
                                   (os.getpid(), 21, 0.25), (os.getpid(), 1, 0)):
            with self.subTest(pid=pid, seconds=seconds, poll=poll):
                with self.assertRaises(ValueError):
                    GUI._owned_qa_hwnd(pid, wait_seconds=seconds, poll_seconds=poll)

    def test_gui_window_wait_denies_missing_or_reused_qa_process(self):
        import psutil

        with patch("psutil.Process", side_effect=psutil.NoSuchProcess(99999999)):
            with self.assertRaisesRegex(RuntimeError, "Cannot verify own QA process identity"):
                GUI._owned_qa_hwnd(99999999, wait_seconds=0)

        gone = SimpleNamespace(create_time=lambda: 123.0, is_running=lambda: False)
        with (patch("psutil.Process", return_value=gone),
              patch.object(GUI, "_visible_owned_qa_windows_once") as scan):
            with self.assertRaisesRegex(RuntimeError, "exited/reused"):
                GUI._owned_qa_hwnd(765432, wait_seconds=0)
            scan.assert_not_called()

        creation_times = iter((123.0, 456.0))
        reused = SimpleNamespace(create_time=lambda: next(creation_times),
                                 is_running=lambda: True)
        with (patch("psutil.Process", return_value=reused),
              patch.object(GUI, "_visible_owned_qa_windows_once") as scan):
            with self.assertRaisesRegex(RuntimeError, "exited/reused"):
                GUI._owned_qa_hwnd(765432, wait_seconds=0)
            scan.assert_not_called()

    def test_source_boundary_does_not_claim_finance_authority(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"officialFinancialReceiptVerified": False', source)
        self.assertIn('"ledgerPostingPerformed": False', source)
        self.assertIn('"installedTarazGuiWasLaunched": False', source)
        self.assertIn('"realUserProfileAccessed": False', source)

    def test_rejects_all_nondecision_modes_without_launching_any_exe(self):
        for proposed in ("", "issued", "approved", "paid", "pending", None, False):
            with self.subTest(proposed=proposed), self.assertRaises(ValueError):
                QA.run(decision=proposed)


if __name__ == "__main__":
    unittest.main()
