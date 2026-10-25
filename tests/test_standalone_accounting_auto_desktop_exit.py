"""Synthetic pywebview lifecycle: mandatory exit and startup backup enforcement."""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import standalone_accounting_auto_backup as auto
import standalone_accounting_desktop as desktop
from standalone_accounting import StandaloneAccountingStore
from standalone_accounting_restore import restore_standalone_accounting

REAL_AUTOMATIC_BACKUPS = auto.AutomaticStandaloneBackups


class FakeClosingEvent:
    def __iadd__(self, callback):
        self.callback = callback
        return self


class FakeWindow:
    def __init__(self):
        self.events = types.SimpleNamespace(closing=FakeClosingEvent())
        self.alerts = []

    def evaluate_js(self, js):
        self.alerts.append(js)


class FakeHttpServer:
    server_port = 38199

    def serve_forever(self):
        return

    def shutdown(self):
        pass

    def server_close(self):
        pass


class FakeBackup:
    instances = []
    fail_on = set()

    def __init__(self, directory, **kwargs):
        self.directory = directory
        self.kwargs = kwargs
        self.calls = 0
        self.started = False
        self.stopped = False
        type(self).instances.append(self)

    def backup_now(self):
        self.calls += 1
        if self.calls in self.fail_on:
            raise OSError("synthetic unwritable financial backup disk")
        return self.directory / ("backup-" + str(self.calls))

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class AutoBackupDesktopExit(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="madar-exit-synthetic-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / "isolated-accounting"
        FakeBackup.instances = []
        FakeBackup.fail_on = set()
        self.window = FakeWindow()
        self.webview = types.ModuleType("webview")
        self.api = None
        def create_window(*args, **kwargs):
            self.api = kwargs["js_api"]
            return self.window
        self.webview.create_window = create_window
        self.webview.start = lambda: None
        patcher = patch.dict(sys.modules, {"webview": self.webview})
        patcher.start()
        self.addCleanup(patcher.stop)
        backup_patch = patch.object(auto, "AutomaticStandaloneBackups", FakeBackup)
        backup_patch.start()
        self.addCleanup(backup_patch.stop)
        server_patch = patch.object(
            desktop, "serve_accounting_page", return_value=FakeHttpServer())
        server_patch.start()
        self.addCleanup(server_patch.stop)

    def launch(self):
        return desktop.main([
            "--data-dir", str(self.root),
            "--site-dir", str(self.root / "irrelevant-site"),
        ])

    def test_failed_exit_backup_vetoes_close_then_allows_retry(self):
        FakeBackup.fail_on = {2}
        outcomes = []
        def run_ui():
            callback = self.window.events.closing.callback
            outcomes.append(callback())
            outcomes.append(callback())
        self.webview.start = run_ui
        self.launch()
        self.assertEqual(outcomes, [False, True])
        backup = FakeBackup.instances[0]
        self.assertEqual(backup.calls, 3)  # startup, failed close, retried close
        self.assertTrue(backup.started)
        self.assertTrue(backup.stopped)
        self.assertTrue(self.window.alerts)
        self.assertTrue((self.root / "standalone-accounting.sqlite3").exists())
        self.assertFalse((self.root / "tasks.json").exists())

    def test_missing_native_close_event_still_runs_exit_backup(self):
        self.launch()
        backup = FakeBackup.instances[0]
        self.assertEqual(backup.calls, 2)  # startup + unconditional finally
        self.assertTrue(backup.stopped)

    def test_financial_command_rejected_after_successful_final_backup(self):
        recorded = []
        def run_ui():
            recorded.append(self.window.events.closing.callback())
            with self.assertRaisesRegex(RuntimeError, "closing"):
                self.api.standaloneAccountingCommand({
                    "command": {"type": "party.register", "eventId": "late-1",
                                "partyId": "late-party", "name": "Late",
                                "kind": "customer"},
                    "expectedRevision": 0,
                })
        self.webview.start = run_ui
        self.launch()
        self.assertEqual(recorded, [True])
        self.assertEqual(FakeBackup.instances[0].calls, 2)
        self.assertEqual(self.api.standaloneAccountingRead()["revision"], 0)

    def test_exit_fails_closed_if_fallback_cannot_backup(self):
        FakeBackup.fail_on = {2}
        with self.assertRaisesRegex(OSError, "synthetic unwritable"):
            self.launch()
        self.assertTrue(FakeBackup.instances[0].stopped)

    def test_failed_startup_backup_prevents_desktop_launch(self):
        FakeBackup.fail_on = {1}
        with self.assertRaises(OSError):
            self.launch()
        self.assertFalse(FakeBackup.instances[0].started)
        self.assertEqual(FakeBackup.instances[0].calls, 1)

    def test_real_desktop_exit_snapshot_restores_last_committed_rial_event(self):
        def run_ui():
            first = self.api.standaloneAccountingRead()
            self.assertEqual(first["view"]["currency"], "RIAL")
            self.api.standaloneAccountingCommand({
                "command": {"type": "party.register", "eventId": "exit-1",
                            "partyId": "customer-1", "name": "Synthetic customer",
                            "kind": "customer"},
                "expectedRevision": first["revision"],
            })
            self.assertTrue(self.window.events.closing.callback())
        self.webview.start = run_ui
        with patch.object(auto, "AutomaticStandaloneBackups", REAL_AUTOMATIC_BACKUPS):
            self.launch()
        files = list((self.root / auto.BACKUP_FOLDER).glob(
            "standalone-accounting-auto-*.sqlite3"))
        self.assertEqual(len(files), 2)
        heads = [auto._check_input(p)[0] for p in files]
        self.assertEqual(sorted(heads), [0, 1])
        latest = next(p for p in files if auto._check_input(p)[0] == 1)
        restore_dir = self.root / "offline-new-directory"
        restore_dir.mkdir()
        restored = restore_standalone_accounting(
            latest, restore_dir / "standalone-accounting.sqlite3",
            plaintext_acknowledged=True, offline_acknowledged=True)
        replay = StandaloneAccountingStore(restored).read(
            actor="local", accounts={"local": {"username": "local", "role": "admin"}})
        self.assertEqual(replay["revision"], 1)
        self.assertEqual(replay["view"]["currency"], "RIAL")
        self.assertIn("customer-1", replay["view"]["parties"])


if __name__ == "__main__":
    unittest.main()
