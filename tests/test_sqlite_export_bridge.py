import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_app
from tests.legacy_sample_fixture import seed_legacy_example_state
from app_storage import UnifiedAppStorage


class UnifiedSqliteExportBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.mock = patch.object(native_app, "datadir", return_value=self.root)
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.bridge = seed_legacy_example_state(native_app.Bridge())

    def test_export_four_domains_without_activating_sqlite(self):
        self.bridge.collabCommand({"type": "comment.add", "eventId": "archive-comment",
                                   "cardId": "example-2", "text": "archive test"})
        self.bridge.financeCommand({"type": "contract.set", "eventId": "archive-contract",
                                    "cardId": "example-2", "sale": {
                                        "customer": {"name": "Customer", "reference": ""},
                                        "lines": [{"id": "line", "description": "Service", "quantity": 1,
                                                   "unitPrice": 200}],
                                        "discount": 0, "tax": 0, "advance": 0,
                                        "autoInvoice": True}})
        original_files = {p.name: p.read_bytes() for p in (
            self.bridge.path, self.bridge.collab_path, self.bridge.finance_path) if p.exists()}
        exported = self.bridge.createUnifiedSqliteBackup()
        self.assertEqual(exported["revision"], 1)
        self.assertTrue(Path(exported["path"]).exists())
        self.assertTrue(UnifiedAppStorage(exported["path"]).integrity_check())
        bundle = UnifiedAppStorage(exported["path"]).load().bundle
        self.assertEqual(len(bundle["collab"]["comments"]), 1)
        self.assertEqual(len(bundle["finance"]["contracts"]), 1)
        for name, content in original_files.items():
            self.assertEqual((self.root / name).read_bytes(), content)
        self.assertFalse((self.root / "active.sqlite3").exists())
        self.assertGreaterEqual(len(list(Path(exported["sourceCopies"]).glob("*.json"))), 3)
        self.assertEqual(self.bridge.getState()["tasks"], bundle["tasks"]["tasks"])

    def test_client_must_not_export_host_data(self):
        self.bridge.connection = {"mode": "client", "url": "http://127.0.0.1:1"}
        with self.assertRaises(PermissionError):
            self.bridge.createUnifiedSqliteBackup()


if __name__ == "__main__":
    unittest.main()
