"""Optional cross-repo E2 smoke against a specified Taraz source checkout.

Supply MTR_TARAZ_SOURCE as the directory containing taraz_integration.py.
Uses only a synthetic TemporaryDirectory redirected through LOCALAPPDATA;
does not start either desktop or open an accounting database.
"""

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from taraz_exchange import queue_saved_task
from taraz_review_status import local_task_reviews
from mtr_e2_send_journal import prepare_manual_send


class CrossAppE2Tests(unittest.TestCase):
    def setUp(self):
        src = os.environ.get("MTR_TARAZ_SOURCE")
        if not src:
            self.skipTest("Set MTR_TARAZ_SOURCE to an isolated Taraz source worktree")
        path = Path(src) / "taraz_integration.py"
        if not path.is_file():
            self.skipTest("No Taraz source module at explicit path")
        spec = importlib.util.spec_from_file_location("mtr_taraz_e2_isolated", path)
        self.taraz = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.taraz)
        temporary = tempfile.TemporaryDirectory(prefix="mtr-e2-cross-")
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(os.environ, {
            "LOCALAPPDATA": temporary.name,
            "APPDATA": temporary.name,
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.root = Path(temporary.name) / "Madar-Taraz-Bridge"
        self.state = {"tasks": [{"id": "task-e2", "projectId": "project-e2",
                                  "title": "Synthetic packaging review"}]}

    def test_manual_send_review_return_and_same_id_replay(self):
        request_id = "e" * 32
        first = queue_saved_task(self.state, "task-e2", request_id=request_id)
        self.assertTrue(first["queued"])
        self.assertEqual([x["id"] for x in self.taraz.list_requests(self.root)["requests"]],
                         [request_id])
        reviewed = self.taraz.review_request(self.root, request_id, "reviewed")
        self.assertIs(reviewed["financialEventCreated"], False)
        self.assertEqual(self.taraz.list_requests(self.root)["requests"], [])
        observed = local_task_reviews("task-e2", "project-e2", opted_in=True, root=self.root)
        self.assertEqual(observed["items"][0]["state"], "reviewed")
        self.assertIs(observed["peerVerified"], False)  # not cryptographically authenticated
        self.assertFalse(observed["postingEnabled"])
        intent_file = self.root / "reviewed" / (request_id + ".intent.json")
        saved_intent = intent_file.read_bytes()
        intent_file.write_bytes(b'{"schema":1,"invalid":"tampered"}')
        self.assertEqual(
            local_task_reviews("task-e2", "project-e2", opted_in=True, root=self.root)["items"][0]["state"],
            "unknown",
        )
        intent_file.write_bytes(saved_intent)
        retry = queue_saved_task(self.state, "task-e2", request_id=request_id)
        self.assertFalse(retry["queued"])
        self.assertTrue(retry["replayed"])
        self.assertEqual(retry["observedLocation"], "reviewed")
        again = self.taraz.review_request(self.root, request_id, "reviewed")
        self.assertEqual(again, reviewed)
        with self.assertRaises((ValueError, RuntimeError)):
            self.taraz.review_request(self.root, request_id, "rejected")
        self.state["tasks"][0]["title"] = "Mutated after the first manual send"
        with self.assertRaises(ValueError):
            queue_saved_task(self.state, "task-e2", request_id=request_id)
        self.assertEqual(list((self.root / "pending").glob("*.json")), [])

    def test_persist_before_first_send_cross_app_review_then_reopen(self):
        intent = prepare_manual_send(
            self.state, "task-e2", actor_scope="solo:local"
        )
        self.assertFalse((self.root / "pending").exists())
        first = queue_saved_task(self.state, "task-e2", request_id=intent["id"])
        self.assertEqual(first["id"], intent["id"])
        decision = self.taraz.review_request(self.root, intent["id"], "rejected")
        self.assertEqual(decision["state"], "rejected")
        recovered_intent = prepare_manual_send(
            self.state, "task-e2", actor_scope="solo:local"
        )
        self.assertEqual(recovered_intent["id"], intent["id"])
        self.assertTrue(recovered_intent["reused"])
        result = queue_saved_task(
            self.state, "task-e2", request_id=recovered_intent["id"]
        )
        self.assertTrue(result["replayed"])
        self.assertEqual(result["observedLocation"], "reviewed")
        self.assertEqual(
            local_task_reviews("task-e2", "project-e2", opted_in=True,
                               root=self.root)["items"][0]["state"],
            "rejected"
        )
        self.assertFalse(list((self.root / "pending").glob("*.json")))


if __name__ == "__main__":
    unittest.main()
