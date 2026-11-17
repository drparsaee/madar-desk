"""Real Madar/Taraz source interoperability on disposable local file proposals.

This is NOT installed-app/LAN acceptance or an official finance transaction.
No real profile, ledger, or service is opened.
"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from taraz_exchange import queue_saved_task
from taraz_review_status import local_task_reviews


DETACHED_TARAZ = Path(r"D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109")


class LocalCrossSourceHandoff(unittest.TestCase):
    def setUp(self):
        source = DETACHED_TARAZ / "taraz_integration.py"
        if not source.is_file() or source.is_symlink():
            self.fail("Explicit detached Taraz source is unavailable or unsafe")
        spec = importlib.util.spec_from_file_location("taraz_isolated_crosssource_qa", source)
        self.taraz = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.taraz)

        temp = tempfile.TemporaryDirectory(prefix="mtr-crosssource-local-qa-")
        self.addCleanup(temp.cleanup)
        self.local = Path(temp.name)
        env = patch.dict(os.environ, {"LOCALAPPDATA": str(self.local), "APPDATA": str(self.local)})
        env.start()
        self.addCleanup(env.stop)
        self.root = self.local / "Madar-Taraz-Bridge"
        self.state = {"tasks": [
            {"id": "task-allowed", "projectId": "project-allowed", "title": "Synthetic order"},
            {"id": "task-other", "projectId": "project-other", "title": "Other synthetic order"},
        ]}

    def test_full_manual_review_and_rejection_are_not_financial_posting(self):
        for decision in ("reviewed", "rejected"):
            with self.subTest(decision=decision):
                result = queue_saved_task(self.state, "task-allowed")
                key = result["id"]
                self.assertTrue(result["queued"])
                self.assertIs(result["postingPerformed"], False)
                inbox = self.taraz.list_requests(self.root)
                self.assertIn(key, [item["id"] for item in inbox["requests"]])
                pending = local_task_reviews("task-allowed", "project-allowed", opted_in=True)
                self.assertEqual(next(item for item in pending["items"] if item["id"] == key)["state"], "pending")
                acknowledgement = self.taraz.review_request(self.root, key, decision)
                self.assertIs(acknowledgement["financialEventCreated"], False)
                observed = local_task_reviews("task-allowed", "project-allowed", opted_in=True)
                item = next(item for item in observed["items"] if item["id"] == key)
                self.assertEqual(item["state"], decision)
                self.assertFalse(item["financialEventCreated"])
                self.assertFalse(observed["peerVerified"])
                self.assertFalse(observed["postingEnabled"])
                self.assertNotIn(key, [item["id"] for item in self.taraz.list_requests(self.root)["requests"]])

    def test_same_id_cannot_be_republished_or_changed(self):
        first = queue_saved_task(self.state, "task-allowed")
        key = first["id"]
        replay = queue_saved_task(self.state, "task-allowed", request_id=key)
        self.assertFalse(replay["queued"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(len(list((self.root / "pending").glob("*.json"))), 1)
        self.state["tasks"][0]["title"] = "Changed after send"
        with self.assertRaises(ValueError):
            queue_saved_task(self.state, "task-allowed", request_id=key)
        self.assertEqual(len(list((self.root / "pending").glob("*.json"))), 1)

    def test_corrupt_local_marker_cannot_claim_official_status(self):
        key = queue_saved_task(self.state, "task-allowed")["id"]
        self.taraz.review_request(self.root, key, "reviewed")
        marker = self.root / "reviewed" / (key + ".review.json")
        forged = json.loads(marker.read_text(encoding="utf-8"))
        forged["financialEventCreated"] = True
        marker.write_text(json.dumps(forged), encoding="utf-8")
        observed = local_task_reviews("task-allowed", "project-allowed", opted_in=True)
        self.assertEqual(observed["items"][0]["state"], "unknown")
        self.assertFalse(observed["items"][0]["financialEventCreated"])

    def test_opt_in_and_other_project_are_not_leaked(self):
        queue_saved_task(self.state, "task-other")
        self.assertEqual(local_task_reviews("task-other", "project-other", opted_in=False)["items"], [])
        self.assertEqual(local_task_reviews("task-allowed", "project-allowed", opted_in=True)["items"], [])


if __name__ == "__main__":
    unittest.main()
