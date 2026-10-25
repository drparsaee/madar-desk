import json
import tempfile
import unittest
from pathlib import Path

from offline_exchange import OfflineStore, three_way_merge


def state(title="A"):
    return {"version": 1, "stages": [], "settings": {}, "projects": [{"id": "p1", "name": "Project"}],
            "tasks": [{"id": "1", "projectId": "p1", "title": title},
                      {"id": "2", "projectId": "p1", "title": "B"}]}


class OfflineExchangeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = OfflineStore(self.root)
    def tearDown(self):
        self.tmp.cleanup()

    def test_offline_cache_survives_restart_and_three_way_merges_distinct_tasks(self):
        original = state()
        self.store.remember(original, "sha-old", "bob", {"username": "bob", "role": "editor"})
        edited = state("offline-edit")
        self.store.queue(edited, "bob")
        self.assertEqual(OfflineStore(self.root).get_cached()["tasks"][0]["title"], "offline-edit")
        self.assertTrue(OfflineStore(self.root).has_pending())
        server = state()
        server["tasks"][1]["title"] = "server-edit"
        merged = self.store.reconcile(server, "sha-new", "bob")
        self.assertEqual([t["title"] for t in merged["tasks"]],
                         ["offline-edit", "server-edit"])
        self.store.ack(merged, "sha-merged", "bob")
        self.assertFalse(self.store.has_pending())
        self.assertEqual(self.store.cached_user()["role"], "editor")

    def test_overlap_is_a_conflict_never_silent_last_write_wins(self):
        self.store.remember(state(), "rev1", "bob")
        self.store.queue(state("my edit"), "bob")
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            self.store.reconcile(state("their edit"), "rev2", "bob")
        self.assertTrue(self.store.has_pending())

    def test_cannot_rebase_structure_or_another_user(self):
        self.store.remember(state(), "rev1", "bob")
        self.store.queue(state("edit"), "bob")
        with self.assertRaises(PermissionError):
            self.store.reconcile(state(), "rev2", "sara")
        changed = state()
        changed["projects"].append({"id": "p2", "name": "X"})
        with self.assertRaises(PermissionError):
            three_way_merge(state(), changed, state())

    def test_cloud_folder_publishes_immutable_sanitized_snapshots(self):
        cloud = self.root / "Google Drive"
        cloud.mkdir()
        self.store.set_sync_folder(cloud)
        original = state()
        original["tasks"][0]["fileLinks"] = [{"path": "\\\\Server\\Share\\file.txt"}]
        original["projects"][0]["fileLinks"] = [{"path": "\\\\Server\\Share\\file.txt"}]
        first = self.store.publish(current=original, username="bob", force=True)
        self.assertIsNone(self.store.publish(current=original, username="bob"))
        second = self.store.publish(current=original, username="bob", force=True)
        self.assertNotEqual(first["name"], second["name"])
        saved = json.loads(Path(first["path"]).read_text(encoding="utf8"))
        self.assertIn(first["name"],[x["name"] for x in self.store.list_snapshots()])
        self.assertEqual(self.store.read_snapshot(first["name"])["tasks"][0]["title"],"A")
        with self.assertRaises(ValueError):
            self.store.read_snapshot("../secret.json")
        self.assertNotIn("fileLinks", saved["state"]["tasks"][0])
        self.assertNotIn("fileLinks", saved["state"]["projects"][0])
        self.assertEqual(original["tasks"][0]["fileLinks"][0]["path"],
                         "\\\\Server\\Share\\file.txt")
        self.assertTrue(self.store.folder_status()["configured"])


if __name__ == "__main__":
    unittest.main()
