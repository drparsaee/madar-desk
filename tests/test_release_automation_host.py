"""Host-level opt-in automation journal integration on disposable SQLite."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app
from tests.legacy_sample_fixture import seed_legacy_example_state
from app_storage import UnifiedAppStorage


class AutomationHostAcceptance(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-auto-host-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        with patch.object(native_app, "datadir", return_value=self.root):
            self.bridge = seed_legacy_example_state(native_app.Bridge())

    def activate(self):
        self.assertEqual(self.bridge.storageStatus()["mode"], "json")
        self.bridge.enableUnifiedStorage()
        report = self.bridge.enableAutomationEngine()
        self.assertEqual(report["mode"], "active")
        self.assertTrue(Path(report["preActivationBackup"]).exists())
        return report

    def test_opt_in_is_backup_first_and_reopens_without_losing_tasks(self):
        original = deepcopy(self.bridge.getState())
        with self.assertRaises(RuntimeError):
            self.bridge.enableAutomationEngine()
        report = self.activate()
        self.assertEqual(self.bridge.enableAutomationEngine()["mode"], "active")
        current = UnifiedAppStorage(self.bridge.unified_path).load()
        self.assertIn("automation", current.bundle)
        self.assertEqual(current.bundle["tasks"]["tasks"], original["tasks"])
        self.assertIn("automation", UnifiedAppStorage(self.bridge.unified_path).load().bundle)
        self.assertTrue(self.bridge._unified_store.integrity_check())

    def test_card_events_commit_with_automation_receipts_in_one_revision(self):
        self.activate()
        previous = self.bridge._unified_store.load()
        state = deepcopy(self.bridge.getState())
        card = deepcopy(state["tasks"][0])
        card["id"] = "automation-host-new-card"
        card["title"] = "Engine event test"
        state["tasks"].append(card)
        self.assertTrue(self.bridge.saveState(state))
        latest = self.bridge._unified_store.load()
        self.assertGreater(latest.revision, previous.revision)
        self.assertTrue(any(t["id"] == card["id"] for t in latest.bundle["tasks"]["tasks"]))
        self.assertGreaterEqual(len(latest.bundle["automation"]["audit"]), 1)
        self.assertGreaterEqual(len(latest.bundle["automation"]["receipts"]), 1)
        self.assertTrue(self.bridge._unified_store.integrity_check())

    def test_scheduler_reuses_sqlite_engine_when_explicitly_active(self):
        self.activate()
        result = self.bridge.runDueScheduler()
        self.assertIn("pending", result)
        self.assertIn("new", result)
        self.assertEqual(self.bridge.automationEngineStatus()["mode"], "active")


if __name__ == "__main__":
    unittest.main()
