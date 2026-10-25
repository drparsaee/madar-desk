"""End-to-end release regressions through the actual Windows Bridge.

Every Bridge in this module resolves APPDATA to a fresh synthetic directory.
No actual user profile, Drive account, shared folder, or release EXE is touched.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_storage import UnifiedAppStorage
import native_app


def contract(price=165_000):
    return {
        "customer": {"name": "Release test customer", "reference": ""},
        "lines": [{"id": "line1", "description": "Release QA", "quantity": 1,
                   "unitPrice": price}],
        "discount": 0, "tax": 0, "advance": 0, "autoInvoice": True,
    }


class ReleaseBridgePersistenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-release-appdata-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, {"APPDATA": str(self.root),
                                   "LOCALAPPDATA": str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        self.bridge = native_app.Bridge()
        self.data = self.root / "MadarDesk"
        self.assertEqual(self.bridge.path, self.data / "tasks.json")

    def test_board_specific_columns_and_new_card_survive_real_save_and_restart(self):
        state = self.bridge.getState()
        sample = next(b for b in state["boards"] if b["projectId"] == "p-sample")
        personal = next(b for b in state["boards"] if b["projectId"] == "p-personal")
        personal_before = deepcopy(personal)
        sample["stages"].append({"id": "release-qa", "label": "Ready for QA",
                                  "subtitle": "", "color": "#00aabc"})
        original = next(t for t in state["tasks"] if t["id"] == "example-2")
        original["listId"] = "release-qa"
        original["cost"] = 74_000
        original["description"] = "Persistent board-specific value"

        personal_task = deepcopy(original)
        personal_task.update({"id": "release-personal-card", "projectId": "p-personal",
                              "boardId": personal["id"], "listId": "planned",
                              "status": "planned", "cost": 4_300,
                              "title": "A second board's card", "labels": [], "labelIds": [],
                              "checklist": [], "checklists": [], "reports": []})
        state["tasks"].append(personal_task)
        self.assertTrue(self.bridge.saveState(state))

        on_disk = json.loads(self.bridge.path.read_text(encoding="utf8"))
        self.assertEqual(native_app.Bridge().getState(), on_disk)
        reloaded = native_app.Bridge().getState()
        self.assertEqual(next(b for b in reloaded["boards"] if b["id"] == personal["id"]),
                         personal_before)
        self.assertEqual(next(t for t in reloaded["tasks"] if t["id"] == "example-2")
                         ["listId"], "release-qa")
        self.assertEqual(next(t for t in reloaded["tasks"] if t["id"] == "release-personal-card")
                         ["projectId"], "p-personal")

    def test_local_backup_restore_replaces_tasks_and_keeps_pre_restore_copy(self):
        original = self.bridge.getState()
        archive = self.bridge.createLocalBackup()
        self.assertEqual(Path(archive["path"]).parent, self.data / "backups")
        edited = deepcopy(original)
        edited["tasks"][0]["title"] = "Edit after creating snapshot"
        self.bridge.saveState(edited)
        restored = self.bridge.restoreLocalBackup(archive["name"])
        self.assertEqual(restored, original)
        self.assertEqual(native_app.Bridge().getState(), original)
        history = list(self.data.glob("backup-before-restore-*.json"))
        self.assertEqual(len(history), 1)
        self.assertEqual(json.loads(history[0].read_text(encoding="utf8")), edited)

    def test_rejected_backup_never_changes_existing_state_or_creates_history(self):
        before = self.bridge.path.read_bytes()
        invalid = self.data / "backups" / "madar-20261020-120000-000001.json"
        invalid.parent.mkdir(parents=True, exist_ok=True)
        broken = self.bridge.getState()
        broken["tasks"][0]["projectId"] = "unknown-project"
        invalid.write_text(json.dumps(broken), encoding="utf8")
        with self.assertRaises(ValueError):
            self.bridge.restoreLocalBackup(invalid.name)
        with self.assertRaises(ValueError):
            self.bridge.restoreLocalBackup("../tasks.json")
        self.assertEqual(self.bridge.path.read_bytes(), before)
        self.assertFalse(list(self.data.glob("backup-before-restore-*.json")))

    def test_unified_export_contains_board_collaboration_and_invoice_without_mutating_sources(self):
        self.bridge.collabCommand({"type": "comment.add", "eventId": "release-comment",
                                   "cardId": "example-2", "text": "Persisted annotation"})
        self.bridge.financeCommand({"type": "contract.set", "eventId": "release-contract",
                                    "cardId": "example-2", "sale": contract()})
        state = self.bridge.getState()
        card = next(t for t in state["tasks"] if t["id"] == "example-2")
        card["status"] = "done"
        card["listId"] = "done"
        self.bridge.saveState(state)
        source_paths = (self.bridge.path, self.bridge.collab_path,
                        self.bridge.finance_path, self.bridge.finance_outbox_path)
        originals = {p.name: p.read_bytes() for p in source_paths if p.exists()}
        exported = self.bridge.createUnifiedSqliteBackup()
        storage = UnifiedAppStorage(Path(exported["path"]))
        self.assertTrue(storage.integrity_check())
        archive = storage.load()
        self.assertEqual(archive.revision, 1)
        self.assertEqual(len(archive.bundle["collab"]["comments"]), 1)
        self.assertEqual(archive.bundle["tasks"]["boards"], state["boards"])
        self.assertEqual(len(archive.bundle["finance"]["invoices"]), 1)
        self.assertEqual(archive.bundle["finance"]["invoices"][0]["sale"]["total"], 165_000)
        for filename, content in originals.items():
            self.assertEqual((self.data / filename).read_bytes(), content, filename)
        self.assertFalse((self.data / "active.sqlite3").exists())

    def test_local_task_restore_does_not_pretend_to_restore_other_domains(self):
        """Document the present task-only restore boundary as observable behavior."""
        archive = self.bridge.createLocalBackup()
        self.bridge.financeCommand({"type": "contract.set", "eventId": "later-contract",
                                    "cardId": "example-2", "sale": contract()})
        self.bridge.collabCommand({"type": "comment.add", "eventId": "later-comment",
                                   "cardId": "example-2", "text": "After backup"})
        self.bridge.restoreLocalBackup(archive["name"])
        self.assertEqual(len(self.bridge._load_finance()["contracts"]), 1)
        self.assertEqual(len(self.bridge._load_collab()["comments"]), 1)
        # This is intentional documentation of an outstanding *full recovery* gap.


if __name__ == "__main__":
    unittest.main()
