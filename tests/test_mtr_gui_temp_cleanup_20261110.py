"""Disposable WebView2 QA cleanup regression tests, never launch installed apps."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "qa_installed_madar_gui_bridge_20261110.py"
SPEC = importlib.util.spec_from_file_location("mtr_gui_qa_cleanup", SCRIPT)
QA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QA)


class DisposableGuiCleanupTests(unittest.TestCase):
    def test_real_empty_owned_qa_directory_is_removed(self):
        with QA._disposable_gui_qa_directory() as path:
            root = Path(path)
            self.assertTrue(root.is_dir())
            self.assertTrue(root.name.startswith("madar-qa-taraz-bridge-ui-"))
        self.assertFalse(root.exists())

    def test_transient_locked_browser_metrics_cleanup_is_retried(self):
        with tempfile.TemporaryDirectory(prefix="madar-qa-taraz-bridge-ui-") as path:
            count = []
            def cleanup():
                count.append(1)
                if len(count) == 1:
                    raise PermissionError("synthetic locked BrowserMetrics")
            fake = SimpleNamespace(name=path, cleanup=cleanup)
            with patch.object(QA.tempfile, "TemporaryDirectory", return_value=fake), \
                 patch.object(QA.time, "sleep") as sleep:
                with QA._disposable_gui_qa_directory() as actual:
                    self.assertEqual(actual, path)
                self.assertEqual(len(count), 2)
                sleep.assert_called_once_with(0.25)

    def test_persistent_lock_fails_closed_after_bounded_retry(self):
        with tempfile.TemporaryDirectory(prefix="madar-qa-taraz-bridge-ui-") as path:
            count = []
            def cleanup():
                count.append(1)
                raise PermissionError("synthetic persistent BrowserMetrics lock")
            fake = SimpleNamespace(name=path, cleanup=cleanup)
            with patch.object(QA.tempfile, "TemporaryDirectory", return_value=fake), \
                 patch.object(QA.time, "sleep") as sleep:
                with self.assertRaisesRegex(PermissionError, "persistent BrowserMetrics"):
                    with QA._disposable_gui_qa_directory():
                        pass
                self.assertEqual(len(count), 20)
                self.assertEqual(sleep.call_count, 19)

    def test_callback_failure_is_never_masked_by_cleanup_success(self):
        with tempfile.TemporaryDirectory(prefix="madar-qa-taraz-bridge-ui-") as path:
            count = []
            fake = SimpleNamespace(name=path, cleanup=lambda: count.append(1))
            with patch.object(QA.tempfile, "TemporaryDirectory", return_value=fake):
                with self.assertRaisesRegex(RuntimeError, "synthetic callback failed"):
                    with QA._disposable_gui_qa_directory():
                        raise RuntimeError("synthetic callback failed")
            self.assertEqual(count, [1])


if __name__ == "__main__":
    unittest.main()
