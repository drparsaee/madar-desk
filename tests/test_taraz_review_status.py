"""End-to-end synthetic local inbox and guarded native history tests."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import native_app
from taraz_exchange import queue_saved_task
from taraz_review_status import local_task_reviews


class LocalRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mtr-review-qa-")
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"LOCALAPPDATA": self.tmp.name, "APPDATA": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.root = Path(self.tmp.name) / "Madar-Taraz-Bridge"
        self.state = {"tasks": [{"id": "t1", "projectId": "p1", "title": "Synthetic test task"},
                                {"id": "t2", "projectId": "p2", "title": "Other project"}]}
        taraz_path = Path(__file__).resolve().parents[3] / "000- Taraz" / "taraz-accounting-desktop"
        # In tests the Taraz implementation is loaded explicitly, never a real profile.
        import importlib.util
        spec = importlib.util.spec_from_file_location("taraz_integration_for_mtr", taraz_path / "taraz_integration.py")
        self.taraz = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.taraz)

    def test_review_and_rejection_round_trip_without_posting(self):
        for decision in ("reviewed", "rejected"):
            queued = queue_saved_task(self.state, "t1")
            identifier = queued["id"]
            self.assertFalse(queued["postingPerformed"])
            self.assertEqual(local_task_reviews("t1", "p1", opted_in=False)["items"], [])
            self.assertEqual(next(i for i in local_task_reviews("t1", "p1", opted_in=True)["items"] if i["id"] == identifier)["state"], "pending")
            found = self.taraz.list_requests(self.root)
            self.assertIn(identifier, [i["id"] for i in found["requests"]])
            reviewed = self.taraz.review_request(self.root, identifier, decision)
            self.assertFalse(reviewed["financialEventCreated"])
            actual = next(i for i in local_task_reviews("t1", "p1", opted_in=True)["items"] if i["id"] == identifier)
            # The historical Taraz source has no durable source-bound intent.
            # Its local review marker must not masquerade as the newer result.
            self.assertEqual(actual["state"], "unknown")
            self.assertFalse(actual["financialEventCreated"])
        self.assertEqual(local_task_reviews("t2", "p2", opted_in=True)["items"], [])

    def test_malformed_receipt_unknown_and_conflicting_pending_unknown(self):
        queued = queue_saved_task(self.state, "t1")
        identifier = queued["id"]
        self.taraz.review_request(self.root, identifier, "reviewed")
        marker = self.root / "reviewed" / (identifier + ".review.json")
        invalid = json.loads(marker.read_text(encoding="utf8"))
        invalid["financialEventCreated"] = True
        marker.write_text(json.dumps(invalid), encoding="utf8")
        self.assertEqual(local_task_reviews("t1", "p1", opted_in=True)["items"][0]["state"], "unknown")
        original = self.root / "reviewed" / (identifier + ".json")
        (self.root / "pending" / original.name).write_bytes(original.read_bytes())
        self.assertEqual(local_task_reviews("t1", "p1", opted_in=True)["items"][0]["state"], "unknown")

    def test_missing_created_timestamp_cannot_crash_status_read(self):
        queued = queue_saved_task(self.state, "t1")
        path = self.root / "pending" / (queued["id"] + ".json")
        record = json.loads(path.read_text(encoding="utf8"))
        del record["createdUtc"]
        path.write_text(json.dumps(record), encoding="utf8")
        result = local_task_reviews("t1", "p1", opted_in=True)
        self.assertTrue(result["supported"])
        self.assertEqual(result["items"], [])

    def test_symlink_is_unavailable_and_unrelated_proposals_hidden(self):
        queue_saved_task(self.state, "t2")
        self.assertEqual(local_task_reviews("t1", "p1", opted_in=True)["items"], [])
        with tempfile.TemporaryDirectory() as elsewhere:
            root = Path(elsewhere) / "link"
            try:
                root.symlink_to(self.root, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink creation requires Windows privilege")
            self.assertEqual(local_task_reviews("t1", "p1", opted_in=True, root=root)["state"], "unavailable")

    def test_bridge_requires_consent_and_project_acl(self):
        bridge = native_app.Bridge()
        self.assertEqual(bridge.tarazIntegrationHistory("anything", False)["state"], "disabled")
        bridge.saveState(native_app.initial_state())
        bridge.connection = {"mode": "client"}
        bridge.remote_user = {"role": "viewer", "projects": ["example-project"]}
        with patch.object(bridge, "getState", return_value=native_app.initial_state()):
            with self.assertRaises(PermissionError):
                bridge.tarazIntegrationHistory("example-2", True)

    @unittest.skip("Unrelated local AI pilot is intentionally excluded from P0 v1.0.26 MTR port")
    def test_ai_native_opt_in_acl_and_preview_only(self):
        bridge = native_app.Bridge()
        with self.assertRaises(PermissionError):
            bridge.aiDraftSuggest("example-2", "Prepare cartons", False)
        bridge.connection = {"mode": "client"}
        bridge.remote_user = {"role": "viewer", "projects": None}
        with patch.object(bridge, "getState", return_value=native_app.initial_state()):
            with self.assertRaises(PermissionError):
                bridge.aiDraftSuggest("example-2", "Prepare cartons", True)
        bridge.remote_user = {"role": "editor", "projects": []}
        with patch.object(bridge, "getState", return_value=native_app.initial_state()):
            with self.assertRaises(PermissionError):
                bridge.aiDraftSuggest("example-2", "Prepare cartons", True)
        bridge.remote_user = {"role": "admin", "projects": None}
        candidate = {"status": "preview", "requiresHumanReview": True,
                     "draft": {"title": "Check cartons", "checklist": [], "missingFields": []}}
        with patch.object(bridge, "getState", return_value=native_app.initial_state()), \
             patch.object(bridge, "_remote_request", return_value={"allowed": True, "provider": "local_ollama", "policyVersion": 1}) as authorized, \
             patch("madar_ai_draft.generate_task_draft", return_value=candidate) as adapter:
            self.assertEqual(bridge.aiDraftSuggest("example-2", "Prepare cartons", True), candidate)
            adapter.assert_called_once_with("Prepare cartons", opt_in=True)
            authorized.assert_called_once_with("/api/ai/authorize", {"projectId": "p-sample"})


if __name__ == "__main__":
    unittest.main()
