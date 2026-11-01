"""Tests exercise an explicitly activated host using only synthetic directories."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_app
from tests.legacy_sample_fixture import seed_legacy_example_state
from app_storage import UnifiedAppStorage


class UnifiedHostBridgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="madar-sql-qa-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        mock = patch.object(native_app, "datadir", return_value=self.root)
        mock.start()
        self.addCleanup(mock.stop)
        self.bridge = seed_legacy_example_state(native_app.Bridge())

    def contract(self, suffix="a"):
        return {"type": "contract.set", "eventId": "contract-" + suffix,
                "cardId": "example-2", "sale": {
                    "customer": {"name": "Customer", "reference": ""},
                    "lines": [{"id": "line", "description": "Design",
                               "quantity": 1, "unitPrice": 200}],
                    "discount": 0, "tax": 0, "advance": 0, "autoInvoice": True}}

    def activate(self):
        result = self.bridge.enableUnifiedStorage()
        self.assertEqual(result["mode"], "sqlite")
        self.assertEqual(result["revision"], 1)
        return UnifiedAppStorage(self.bridge.unified_path)

    def test_backup_first_migration_preserves_original_bytes_and_persists_all_domains(self):
        self.bridge.collabCommand({"type": "comment.add", "eventId": "comment-before",
                                   "cardId": "example-2", "text": "before"})
        self.bridge.financeCommand(self.contract())
        originals = {p.name: p.read_bytes() for p in (
            self.bridge.path, self.bridge.collab_path, self.bridge.finance_path)}
        store = self.activate()
        self.assertTrue(store.integrity_check())
        self.assertEqual(len(store.load().bundle["collab"]["comments"]), 1)
        self.assertEqual(len(store.load().bundle["finance"]["contracts"]), 1)
        for name, content in originals.items():
            self.assertEqual((self.root / name).read_bytes(), content)
        source_copies = list((self.root / "backups").glob("migration-originals-*/*.json"))
        self.assertEqual(len(source_copies), len(originals))
        self.assertEqual(native_app.Bridge().storageStatus()["mode"], "sqlite")
        self.assertEqual(self.bridge.enableUnifiedStorage()["revision"], 1)

    def test_live_changes_use_sqlite_only_and_survive_restart(self):
        store = self.activate()
        prior_json = self.bridge.path.read_bytes()
        state = self.bridge.getState()
        state["tasks"][0]["title"] = "SQLite task"
        self.bridge.saveState(state)
        self.bridge.collabCommand({"type": "comment.add", "eventId": "comment-after",
                                   "cardId": "example-2", "text": "after"})
        self.bridge.financeCommand(self.contract("after"))
        self.assertTrue(store.integrity_check())
        self.assertEqual(prior_json, self.bridge.path.read_bytes())
        self.assertFalse(self.bridge.collab_path.exists())
        self.assertFalse(self.bridge.finance_path.exists())
        reopened = native_app.Bridge()
        self.assertEqual(reopened.getState()["tasks"][0]["title"], "SQLite task")
        self.assertEqual(len(reopened.collabRead("comments", "example-2")), 1)
        self.assertEqual(len(reopened.financeRead()), 0)  # Unissued contract is not an invoice.
        self.assertEqual(len(store.load().bundle["finance"]["contracts"]), 1)

    def test_completed_card_and_finance_queue_are_atomic_under_failure(self):
        store = self.activate()
        state = self.bridge.getState()
        state["tasks"][1]["status"] = "done"
        before = store.load()
        with patch.object(self.bridge._unified_store, "commit", side_effect=OSError("disk failed")):
            with self.assertRaises(OSError):
                self.bridge.saveState(state)
        after = store.load()
        self.assertEqual(before.sha256, after.sha256)
        self.assertEqual(after.bundle["completion_outbox"], [])
        self.assertEqual(after.bundle["collab"]["receipts"], {})
        self.assertFalse(self.bridge.automation_outbox_path.exists())
        self.assertEqual(self.bridge.getState()["tasks"][1]["status"], "active")
        self.bridge.saveState(state)
        self.assertEqual(self.bridge.getState()["tasks"][1]["status"], "done")
        self.assertGreater(len(store.load().bundle["collab"]["receipts"]), 0)
        self.assertTrue(store.integrity_check())

    def test_full_database_backup_and_recovery_restores_finance_and_comments(self):
        store = self.activate()
        self.bridge.collabCommand({"type": "comment.add", "eventId": "first-comment",
                                   "cardId": "example-2", "text": "preserve"})
        self.bridge.financeCommand(self.contract("first"))
        saved = self.bridge.createLocalBackup()
        self.assertFalse(saved["complete"])
        self.assertEqual(saved["scope"], "sqlite-domains-only")
        self.assertIn("attachment-binaries", saved["omitted"])
        self.assertTrue(saved["name"].endswith(".sqlite3"))
        self.bridge.collabCommand({"type": "comment.add", "eventId": "second-comment",
                                   "cardId": "example-2", "text": "remove"})
        state = self.bridge.getState()
        state["tasks"][0]["title"] = "Later"
        self.bridge.saveState(state)
        result = self.bridge.restoreLocalBackup(saved["name"])
        self.assertNotEqual(result["tasks"][0]["title"], "Later")
        self.assertEqual(len(store.load().bundle["collab"]["comments"]), 1)
        self.assertEqual(len(store.load().bundle["finance"]["contracts"]), 1)
        self.assertTrue(store.integrity_check())
        self.assertTrue(list((self.root / "backups").glob("before-restore-*.sqlite3")))

    def test_legacy_task_restore_does_not_erase_financial_database(self):
        store = self.activate()
        self.bridge.financeCommand(self.contract("kept"))
        legacy = native_app.initial_state()
        legacy["tasks"][0]["title"] = "Restored from old JSON"
        file = self.bridge.backups_dir / "madar-20261020-123456-000123.json"
        self.bridge.backups_dir.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(legacy), encoding="utf8")
        self.bridge.restoreLocalBackup(file.name)
        self.assertEqual(self.bridge.getState()["tasks"][0]["title"], "Restored from old JSON")
        self.assertEqual(len(store.load().bundle["finance"]["contracts"]), 1)
        self.assertTrue(store.integrity_check())

    def test_corrupt_or_orphan_sqlite_refuses_unsafe_legacy_fallback(self):
        store = self.activate()
        self.bridge.unified_marker.unlink()
        with self.assertRaisesRegex(RuntimeError, "مهاجرت متوقف"):
            native_app.Bridge().enableUnifiedStorage()
        self.bridge.unified_marker.write_text(
            json.dumps({"schema": 1, "database": "bad.sqlite3"}), encoding="utf8")
        with self.assertRaisesRegex(RuntimeError, "نشانگر"):
            native_app.Bridge()
        self.assertTrue(store.integrity_check())

    def test_network_client_cannot_activate_host_storage(self):
        self.bridge.connection = {"mode": "client", "url": "http://127.0.0.1:1"}
        with self.assertRaises(PermissionError):
            self.bridge.enableUnifiedStorage()


if __name__ == "__main__":
    unittest.main()
