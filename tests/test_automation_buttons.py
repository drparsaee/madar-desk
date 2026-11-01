"""Host-bound, persistent and ACL-aware automation button integration tests."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import automation_buttons
import collab
import native_app
from lan import LanService


class ButtonTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="madar-buttons-")
        self.root = Path(self.folder.name)
        self.override = patch.object(native_app, "datadir", return_value=self.root)
        self.override.start()
        self.bridge = native_app.Bridge()
        # This suite tests automation receipts/activity from an *unchanged*
        # sample state. Saving via Bridge would itself publish four card
        # lifecycle events and invalidate those baseline counts. Prepare the
        # JSON fixture directly inside the disposable test directory before
        # opening a fresh Bridge; never change the real first-run default.
        self.bridge.path.write_text(
            json.dumps(native_app.initial_state(), ensure_ascii=False),
            encoding="utf8")
        self.bridge = native_app.Bridge()
        self.board = next(b["id"] for b in self.bridge.getState()["boards"]
                          if b.get("projectId") == "p-sample")

    def tearDown(self):
        self.override.stop()
        self.folder.cleanup()

    def definition(self, *, scope="card", actions=None, **overrides):
        definition = {
            "projectId": "p-sample", "boardId": self.board, "scope": scope,
            "icon": "bell", "title": "اعلان مهم",
            "actions": actions or [
                {"type": "notify", "users": ["writer"], "message": "A notification"},
                {"type": "comment", "text": "Automated comment"}],
            "enabled": True, "closeAfterAction": scope == "card",
        }
        return {**definition, **overrides}

    def test_durable_crud_preserves_unified_state(self):
        saved = self.bridge.automationButtonsSave(self.definition())
        self.assertTrue((self.root / "automation-buttons.json").is_file())
        self.assertEqual(saved["owner"], "local")
        self.assertEqual(self.bridge.automationButtonsList({"projectId": "p-sample"})[0]["id"], saved["id"])
        again = native_app.Bridge()
        self.assertEqual(again.automationButtonsList({"projectId": "p-sample"})[0]["id"], saved["id"])
        modified = again.automationButtonsSave({**self.definition(), "id": saved["id"],
                                                 "title": "New title"})
        self.assertEqual(modified["createdAt"], saved["createdAt"])
        self.assertEqual(len(self.bridge.automationButtonsList({"projectId": "p-sample"})), 1)
        self.assertEqual(again.automationButtonsDelete(saved["id"]), {"buttonId": saved["id"]})
        self.assertEqual(native_app.Bridge().automationButtonsList({"projectId": "p-sample"}), [])
        self.assertEqual(self.bridge.collabRead("activity"), [])

    def test_replay_execute_deduplicates_persistent_collab_effects(self):
        saved = self.bridge.automationButtonsSave(self.definition(
            actions=[{"type": "comment", "text": "An action"}]))
        request = {"buttonId": saved["id"], "cardId": "example-1", "eventId": "run-replay-1"}
        first = self.bridge.automationButtonRun(request)
        after_restart = native_app.Bridge()
        self.assertEqual(after_restart.automationButtonRun(request), first)
        comments = after_restart.collabRead("comments", "example-1")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["text"], "An action")
        self.assertEqual(len(after_restart.collabRead("activity")), 2)
        self.assertEqual(len(after_restart._load_collab()["receipts"]), 1)
        with self.assertRaises(ValueError):
            after_restart.automationButtonRun({**request, "buttonId": "other"})

    def test_unified_sqlite_collab_receipt_survives_restart(self):
        self.bridge.enableUnifiedStorage()
        saved = self.bridge.automationButtonsSave(self.definition(
            actions=[{"type": "comment", "text": "SQLite-backed result"}]))
        event = {"buttonId": saved["id"], "cardId": "example-1",
                 "eventId": "sql-run-once"}
        first = self.bridge.automationButtonRun(event)
        restarted = native_app.Bridge()
        self.assertEqual(restarted.automationButtonRun(event), first)
        self.assertEqual(len(restarted.collabRead("comments", "example-1")), 1)
        self.assertTrue(restarted._unified_store.load().bundle["collab"]["receipts"]["sql-run-once"])

    def test_invalid_actions_disabled_button_and_board_scope(self):
        with self.assertRaises(ValueError):
            self.bridge.automationButtonsSave(self.definition(
                actions=[{"type": "shell", "command": "whoami"}]))
        with self.assertRaises(ValueError):
            self.bridge.automationButtonsSave(self.definition(
                actions=[{"type": "finance", "amount": 100}]))
        with self.assertRaises(ValueError):
            self.bridge.automationButtonsSave(self.definition(icon="unexpected-icon"))
        saved = self.bridge.automationButtonsSave(self.definition(enabled=False))
        with self.assertRaises(PermissionError):
            self.bridge.automationButtonRun({"buttonId": saved["id"], "cardId": "example-1"})
        with self.assertRaises(ValueError):
            self.bridge.automationButtonsSave(self.definition(
                scope="board", closeAfterAction=True))
        board = self.bridge.automationButtonsSave(self.definition(scope="board"))
        with self.assertRaises(ValueError):
            self.bridge.automationButtonRun({"buttonId": board["id"]})
        with self.assertRaises(ValueError):
            self.bridge.automationButtonRun({"buttonId": board["id"],
                                             "cardId": "nonexistent"})

    def test_corrupt_file_fails_closed_no_reset(self):
        saved = self.bridge.automationButtonsSave(self.definition())
        path = self.root / "automation-buttons.json"
        invalid = json.loads(path.read_text(encoding="utf8"))
        invalid["buttons"][0]["actions"] = [{"type": "exec", "code": "evil"}]
        path.write_text(json.dumps(invalid), encoding="utf8")
        with self.assertRaises(ValueError):
            self.bridge.automationButtonsList({"projectId": "p-sample"})
        self.assertEqual(json.loads(path.read_text(encoding="utf8")), invalid)

    def test_host_permissions_http_read_execute_and_delete(self):
        lan = LanService(self.bridge, self.root / "users.json", bind="127.0.0.1", port=0)
        lan.setup_owner("admin", "test-password-secure")
        port = lan.start()
        base = f"http://127.0.0.1:{port}"

        def request(path, body=None, token=None):
            kwargs = {"method": "POST" if body is not None else "GET"}
            if body is not None:
                kwargs["data"] = json.dumps(body).encode("utf8")
            req = Request(base + path, headers={"Content-Type": "application/json",
                          **({"Authorization": "Bearer " + token} if token else {})},
                          **kwargs)
            with urlopen(req, timeout=10) as response:
                return json.loads(response.read())

        def denied(status, path, body=None, token=None):
            with self.assertRaises(HTTPError) as error:
                request(path, body, token)
            self.assertEqual(error.exception.code, status)

        try:
            admin = request("/api/login", {"username": "admin",
                                          "password": "test-password-secure"})["token"]
            request("/api/user", {"username": "writer", "password": "writer-password",
                                  "role": "editor", "projects": ["p-sample"]}, admin)
            request("/api/user", {"username": "visitor", "password": "viewer-password",
                                  "role": "viewer", "projects": ["p-sample"]}, admin)
            request("/api/user", {"username": "outsider", "password": "outsider-password",
                                  "role": "editor", "projects": ["p-personal"]}, admin)
            writer = request("/api/login", {"username": "writer",
                                           "password": "writer-password"})["token"]
            viewer = request("/api/login", {"username": "visitor",
                                           "password": "viewer-password"})["token"]
            outsider = request("/api/login", {"username": "outsider",
                                             "password": "outsider-password"})["token"]
            denied(403, "/api/buttons?projectId=p-sample")
            denied(403, "/api/buttons", {"type": "button.upsert", "eventId": "unauth",
                                        "button": self.definition()})
            saved = request("/api/buttons", {"type": "button.upsert", "eventId": "save-lan",
                                            "button": self.definition(actions=[
                                                {"type": "notify", "users": ["visitor"],
                                                 "message": "Ready"},
                                                {"type": "comment", "text": "Audit log"}])}, admin)["result"]
            self.assertEqual(saved["owner"], "admin")
            self.assertEqual(len(request("/api/buttons?projectId=p-sample", token=viewer)["items"]), 1)
            denied(403, "/api/buttons?projectId=p-sample", token=outsider)
            denied(403, "/api/buttons", {"type": "button.delete", "eventId": "delete-viewer",
                                        "buttonId": saved["id"]}, viewer)
            denied(403, "/api/buttons", {"type": "button.execute", "eventId": "run-viewer",
                                        "buttonId": saved["id"], "cardId": "example-1"}, viewer)
            denied(403, "/api/buttons", {"type": "button.execute", "eventId": "run-outsider",
                                        "buttonId": saved["id"], "cardId": "example-1"}, outsider)
            ran = {"type": "button.execute", "eventId": "run-writer",
                   "buttonId": saved["id"], "cardId": "example-1"}
            first = request("/api/buttons", ran, writer)["result"]
            self.assertEqual(request("/api/buttons", ran, writer)["result"], first)
            self.assertEqual(len(request("/api/notifications", token=writer)["items"]), 0)
            self.assertEqual(len(request("/api/notifications", token=viewer)["items"]), 1)
            self.assertEqual(len(request("/api/comments?cardId=example-1", token=writer)["items"]), 1)
            self.assertEqual(len(self.bridge._load_collab()["receipts"]), 1)
            self.assertEqual(request("/api/buttons", {"type": "button.delete", "eventId": "delete-ok",
                             "buttonId": saved["id"]}, admin)["result"], {"buttonId": saved["id"]})
        finally:
            lan.stop()


if __name__ == "__main__":
    unittest.main()
