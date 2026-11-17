"""E2 manual retry behavior on a disposable file inbox; no ledger write."""

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import native_app
from taraz_exchange import queue_saved_task


class ManualRetryTests(unittest.TestCase):
    REQUEST = "a" * 32

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mtr-retry-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "Madar-Taraz-Bridge"
        p = patch.dict(os.environ, {"LOCALAPPDATA": temporary.name,
                                    "APPDATA": temporary.name,
                                    "USERPROFILE": temporary.name})
        p.start()
        self.addCleanup(p.stop)
        self.state = {"tasks": [{"id": "task.1", "projectId": "project.1",
                                  "title": "Inspect synthetic print order",
                                  "checklist": []}]}

    def test_default_manual_sends_remain_independent(self):
        first = queue_saved_task(self.state, "task.1")
        second = queue_saved_task(self.state, "task.1")
        self.assertNotEqual(first["id"], second["id"])
        self.assertTrue(first["queued"])
        self.assertFalse(first["replayed"])
        self.assertEqual(len(list((self.root / "pending").glob("*.json"))), 2)

    def test_replay_matches_same_request_and_cannot_rewrite_it(self):
        first = queue_saved_task(self.state, "task.1", request_id=self.REQUEST)
        path = self.root / "pending" / (self.REQUEST + ".json")
        before = path.read_bytes()
        same = queue_saved_task(self.state, "task.1", request_id=self.REQUEST)
        self.assertTrue(first["queued"])
        self.assertFalse(same["queued"])
        self.assertTrue(same["replayed"])
        self.assertEqual(same["observedLocation"], "pending")
        self.assertEqual(before, path.read_bytes())
        self.assertFalse(same["postingPerformed"])
        self.assertEqual(len(list((self.root / "pending").iterdir())), 1)

    def test_replay_of_reviewed_same_proposal_does_not_requeue(self):
        queue_saved_task(self.state, "task.1", request_id=self.REQUEST)
        reviewed = self.root / "reviewed"
        reviewed.mkdir(exist_ok=True)
        shutil.move(str(self.root / "pending" / (self.REQUEST + ".json")),
                    str(reviewed / (self.REQUEST + ".json")))
        result = queue_saved_task(self.state, "task.1", request_id=self.REQUEST)
        self.assertTrue(result["replayed"])
        self.assertEqual(result["observedLocation"], "reviewed")
        self.assertEqual(list((self.root / "pending").iterdir()), [])

    def test_conflicting_payload_is_rejected_without_modification(self):
        queue_saved_task(self.state, "task.1", request_id=self.REQUEST)
        path = self.root / "pending" / (self.REQUEST + ".json")
        before = path.read_bytes()
        self.state["tasks"][0]["title"] = "Different order, same key"
        with self.assertRaises(ValueError):
            queue_saved_task(self.state, "task.1", request_id=self.REQUEST)
        self.assertEqual(path.read_bytes(), before)

    def test_corrupt_prior_record_or_duplicate_locations_fail_closed(self):
        queue_saved_task(self.state, "task.1", request_id=self.REQUEST)
        path = self.root / "pending" / (self.REQUEST + ".json")
        path.write_text('{"schema":1,"schema":1}', encoding="utf8")
        with self.assertRaises(ValueError):
            queue_saved_task(self.state, "task.1", request_id=self.REQUEST)
        data = {"schema": 1, "source": "madar", "id": self.REQUEST,
                "taskId": "task.1", "title": self.state["tasks"][0]["title"],
                "projectId": "project.1", "createdUtc": "2026-11-09T00:00:00+00:00"}
        path.write_text(json.dumps(data), encoding="utf8")
        reviewed = self.root / "reviewed"
        reviewed.mkdir(exist_ok=True)
        (reviewed / path.name).write_bytes(path.read_bytes())
        with self.assertRaises(RuntimeError):
            queue_saved_task(self.state, "task.1", request_id=self.REQUEST)

    def test_missing_proposal_but_review_receipt_exists_is_unknown(self):
        reviewed = self.root / "reviewed"
        reviewed.mkdir(parents=True)
        (reviewed / (self.REQUEST + ".review.json")).write_text(
            '{"state":"reviewed"}', encoding="utf8")
        with self.assertRaises(RuntimeError):
            queue_saved_task(self.state, "task.1", request_id=self.REQUEST)
        self.assertFalse((self.root / "pending").exists())

    def test_stale_request_lock_without_record_fails_closed(self):
        reviewed = self.root / "reviewed"
        reviewed.mkdir(parents=True)
        (reviewed / (self.REQUEST + ".lock")).write_bytes(b"\0")
        with self.assertRaises(RuntimeError):
            queue_saved_task(self.state, "task.1", request_id=self.REQUEST)
        self.assertFalse((self.root / "pending").exists())

    def test_invalid_request_id_rejected_before_any_file_write(self):
        for candidate in ("../x", "B" * 32, "0" * 31, "", 123, True):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                queue_saved_task(self.state, "task.1", request_id=candidate)
        self.assertFalse((self.root / "pending").exists())

    def test_exclusive_publication_collision_never_overwrites_target(self):
        target = self.root / "pending" / (self.REQUEST + ".json")
        def collide(_src, dest):
            Path(dest).write_text("occupied-by-other-writer", encoding="utf8")
            raise FileExistsError()
        with patch("taraz_exchange.os.link", side_effect=collide):
            with self.assertRaises(RuntimeError):
                queue_saved_task(self.state, "task.1", request_id=self.REQUEST)
        self.assertEqual(target.read_text(encoding="utf8"), "occupied-by-other-writer")
        self.assertEqual(list(target.parent.glob("*.tmp")), [])

    def test_reviewed_folder_symlink_cannot_be_used_for_explicit_retry(self):
        with tempfile.TemporaryDirectory(prefix="mtr-link-dest-") as outside:
            self.root.mkdir()
            try:
                (self.root / "reviewed").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink creation is unavailable")
            with self.assertRaises(PermissionError):
                queue_saved_task(self.state, "task.1", request_id=self.REQUEST)
            self.assertFalse((self.root / "pending").exists())

    def test_native_bridge_accepts_exact_manual_retry_id(self):
        bridge = native_app.Bridge()
        bridge.saveState(native_app.initial_state())
        queued = queue_saved_task(bridge.getState(), "example-2",
                                  request_id=self.REQUEST)
        self.assertTrue(queued["queued"])
        first = bridge.tarazIntegrationQueue("example-2", None, self.REQUEST)
        second = bridge.tarazIntegrationQueue("example-2", None, self.REQUEST)
        self.assertEqual(first["id"], self.REQUEST)
        self.assertFalse(first["queued"])
        self.assertTrue(first["replayed"])
        self.assertFalse(second["queued"])
        self.assertTrue(second["replayed"])
        self.assertFalse(second["postingPerformed"])


if __name__ == "__main__":
    unittest.main()
