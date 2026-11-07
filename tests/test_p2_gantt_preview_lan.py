"""Real ephemeral LAN HTTP preview checks. No actual Madar profile is opened."""
from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import native_app
from lan import LanService


class GanttLanPreviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="madar-p2-gantt-lan-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        override = patch.object(native_app, "datadir", return_value=root)
        override.start()
        self.addCleanup(override.stop)
        self.bridge = native_app.Bridge()
        fixture = native_app.initial_state()
        sample = [task for task in fixture["tasks"]
                  if task["projectId"] == "p-sample"]
        self.assertGreaterEqual(len(sample), 2)
        for task in sample:
            task["plannedStart"] = "2026-11-01"
            task["plannedEnd"] = "2026-11-03"
        sample[1]["plannedStart"] = "2026-11-04"
        sample[1]["plannedEnd"] = "2026-11-06"
        sample[1]["dependencies"] = [sample[0]["id"]]
        self.source_id, self.child_id = sample[0]["id"], sample[1]["id"]
        self.bridge.saveState(fixture)
        self.service = LanService(
            self.bridge, root / "users.json", bind="127.0.0.1", port=0)
        self.addCleanup(self.service.stop)
        self.service.setup_owner("admin-test", "synthetic-password-123")
        self.admin = self.service.authenticate(
            "admin-test", "synthetic-password-123")["token"]
        self.service.upsert_user(self.admin, {
            "username": "editor-test", "password": "synthetic-password-123",
            "role": "editor", "projects": ["p-sample"]})
        self.service.upsert_user(self.admin, {
            "username": "other-test", "password": "synthetic-password-123",
            "role": "editor", "projects": ["p-personal"]})
        self.service.upsert_user(self.admin, {
            "username": "viewer-test", "password": "synthetic-password-123",
            "role": "viewer", "projects": ["p-sample"]})
        self.editor = self.service.authenticate(
            "editor-test", "synthetic-password-123")["token"]
        self.other = self.service.authenticate(
            "other-test", "synthetic-password-123")["token"]
        self.viewer = self.service.authenticate(
            "viewer-test", "synthetic-password-123")["token"]

    def request(self, token, revision, target=None):
        return self.service.gantt_shift_preview(token, {
            "taskId": target or self.source_id,
            "days": 2, "expectedRevision": revision})

    def test_authenticated_scoped_preview_is_read_only(self):
        before = deepcopy(self.bridge.getState())
        rev = self.service.read_state(self.editor)["revision"]
        result = self.request(self.editor, rev)
        self.assertTrue(result["readOnly"])
        self.assertEqual(result["scope"], "full_host")
        self.assertEqual(result["revision"], rev)
        self.assertEqual(result["updates"][:2], [
            {"id": self.source_id, "plannedStart": "2026-11-03",
             "plannedEnd": "2026-11-05"},
            {"id": self.child_id, "plannedStart": "2026-11-06",
             "plannedEnd": "2026-11-08"}])
        self.assertEqual(self.bridge.getState(), before)
        self.assertEqual(self.service.read_state(self.editor)["revision"], rev)

    def test_rejected_grants_viewer_and_stale_revision_are_no_ops(self):
        rev = self.service.read_state(self.editor)["revision"]
        before = deepcopy(self.bridge.getState())
        with self.assertRaises(PermissionError):
            self.request(self.viewer, self.service.read_state(self.viewer)["revision"])
        other_rev = self.service.read_state(self.other)["revision"]
        with self.assertRaisesRegex(ValueError, "gantt_preview_unavailable"):
            self.request(self.other, other_rev)
        with self.assertRaisesRegex(ValueError, "gantt_preview_unavailable"):
            self.request(self.editor, rev, target="no-such-id")
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            self.request(self.editor, "stale")
        self.assertEqual(self.bridge.getState(), before)

    def test_http_post_uses_bearer_auth_without_updating_host(self):
        port = self.service.start()
        before = deepcopy(self.bridge.getState())
        rev = self.service.read_state(self.editor)["revision"]

        def post(token, revision, target):
            body = json.dumps({"taskId": target, "days": 2,
                               "expectedRevision": revision}).encode("utf8")
            req = Request(
                f"http://127.0.0.1:{port}/api/gantt/shift/preview",
                data=body, method="POST", headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                })
            with urlopen(req, timeout=8) as response:
                return json.load(response)

        result = post(self.editor, rev, self.source_id)
        self.assertTrue(result["readOnly"])
        self.assertEqual(result["changedCount"], 2)
        with self.assertRaises(HTTPError) as blocked:
            post(self.viewer, rev, self.source_id)
        self.assertEqual(blocked.exception.code, 403)
        with self.assertRaises(HTTPError) as hidden:
            post(self.other, self.service.read_state(self.other)["revision"],
                 self.source_id)
        self.assertEqual(hidden.exception.code, 400)
        self.assertEqual(json.load(hidden.exception)["error"],
                         "gantt_preview_unavailable")
        self.assertEqual(self.bridge.getState(), before)


if __name__ == "__main__":
    unittest.main()
