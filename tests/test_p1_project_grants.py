"""Synthetic LAN project-deletion regressions; no operational Windows profile."""

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


class ProjectGrantDeletionTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="madar-p1-grants-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        mocked_profile = patch.object(native_app, "datadir", return_value=self.root)
        mocked_profile.start()
        self.addCleanup(mocked_profile.stop)
        self.bridge = native_app.Bridge()
        self.bridge.saveState(native_app.initial_state())
        self.users_path = self.root / "lan-users.json"
        self.service = LanService(self.bridge, self.users_path, bind="127.0.0.1", port=0)
        self.service.setup_owner("admin-qa", "synthetic-password-123")
        self.admin = self.service.authenticate("admin-qa", "synthetic-password-123")["token"]

    def user(self, name, role="viewer", projects=None):
        self.service.upsert_user(self.admin, {
            "username": name, "password": "synthetic-password-123",
            "role": role, "projects": projects,
        })
        return self.service.authenticate(name, "synthetic-password-123")["token"]

    def removal(self):
        """p-personal is an empty project in the existing synthetic fixture."""
        current = self.service.read_state(self.admin)
        data = deepcopy(current["state"])
        self.assertFalse(any(t["projectId"] == "p-personal" for t in data["tasks"]))
        data["projects"] = [p for p in data["projects"] if p["id"] != "p-personal"]
        removed_boards = {b["id"] for b in data["boards"]
                          if b["projectId"] == "p-personal"}
        data["boards"] = [b for b in data["boards"] if b["id"] not in removed_boards]
        data["templates"] = [t for t in data["templates"]
                             if t["boardId"] not in removed_boards]
        return data, current["revision"]

    def restarted(self):
        """Reopen native and LAN registries from the disposable disk root."""
        bridge = native_app.Bridge()
        service = LanService(bridge, self.users_path, bind="127.0.0.1", port=0)
        admin = service.authenticate("admin-qa", "synthetic-password-123")["token"]
        return bridge, service, admin

    def test_rejects_scoped_grants_before_commit_and_preserves_access_after_restart(self):
        viewer = self.user("viewer-qa", projects=["p-personal"])
        editor = self.user("editor-qa", role="editor", projects=["p-personal"])
        prior = deepcopy(self.bridge.getState())
        registry = self.users_path.read_bytes()
        candidate, version = self.removal()

        with self.assertRaises(PermissionError) as failure:
            self.service.write_state(self.admin, candidate, version)
        self.assertIn("viewer-qa", str(failure.exception))
        self.assertIn("editor-qa", str(failure.exception))
        self.assertIn("p-personal", str(failure.exception))
        self.assertEqual(self.bridge.getState(), prior)
        self.assertEqual(self.users_path.read_bytes(), registry)

        for token in (self.admin, viewer, editor):
            self.assertIsInstance(self.service.collab_read(token, "activity"), list)
            self.assertIn("p-personal", {p["id"] for p in
                          self.service.read_state(token)["state"]["projects"]})

        restarted_bridge, restarted_service, restarted_admin = self.restarted()
        self.assertEqual(restarted_bridge.getState(), prior)
        self.assertIsInstance(restarted_service.collab_read(restarted_admin, "activity"), list)
        for username in ("viewer-qa", "editor-qa"):
            token = restarted_service.authenticate(username, "synthetic-password-123")["token"]
            self.assertIsInstance(restarted_service.collab_read(token, "activity"), list)
            self.assertEqual([p["id"] for p in
                              restarted_service.read_state(token)["state"]["projects"]],
                             ["p-personal"])

    def test_unscoped_and_unrelated_scoped_grants_allow_empty_project_deletion(self):
        all_projects = self.user("all-qa", role="editor", projects=None)
        restricted = self.user("sample-qa", projects=["p-sample"])
        candidate, version = self.removal()
        self.service.write_state(self.admin, candidate, version)

        self.assertNotIn("p-personal", {p["id"] for p in self.bridge.getState()["projects"]})
        for token in (self.admin, all_projects, restricted):
            self.assertIsInstance(self.service.collab_read(token, "activity"), list)

        _, restored, admin = self.restarted()
        self.assertNotIn("p-personal", {p["id"] for p in
                          restored.read_state(admin)["state"]["projects"]})
        token = restored.authenticate("sample-qa", "synthetic-password-123")["token"]
        self.assertEqual([p["id"] for p in restored.read_state(token)["state"]["projects"]],
                         ["p-sample"])

    def test_editor_cannot_delete_project_even_if_scoped_to_it(self):
        editor = self.user("editor-qa", role="editor", projects=["p-personal"])
        snapshot = self.service.read_state(editor)
        candidate = deepcopy(snapshot["state"])
        candidate["projects"] = []
        candidate["boards"] = []
        candidate["templates"] = []
        with self.assertRaises(PermissionError):
            self.service.write_state(editor, candidate, snapshot["revision"])
        self.assertEqual(len(self.service.read_state(editor)["state"]["projects"]), 1)

    def test_http_rejection_exposes_affected_username_without_mutating_grants(self):
        viewer = self.user("viewer-qa", projects=["p-personal"])
        candidate, version = self.removal()
        original = deepcopy(self.bridge.getState())
        port = self.service.start()

        def request(path, token, payload=None):
            address = f"http://127.0.0.1:{port}{path}"
            body = (json.dumps(payload).encode("utf8") if payload is not None
                    else None)
            req = Request(address, data=body, headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            }, method="POST" if body is not None else "GET")
            with urlopen(req, timeout=6) as response:
                return json.load(response)

        try:
            with self.assertRaises(HTTPError) as failure:
                request("/api/state", self.admin,
                        {"state": candidate, "revision": version})
            self.assertEqual(failure.exception.code, 403)
            response = json.loads(failure.exception.read().decode("utf8"))
            self.assertIn("viewer-qa", response["error"])
            self.assertIn("p-personal", response["error"])
            self.assertEqual(self.bridge.getState(), original)
            self.assertEqual([p["id"] for p in
                              request("/api/state", viewer)["state"]["projects"]],
                             ["p-personal"])
            self.assertIsInstance(request("/api/activity", self.admin)["items"], list)
        finally:
            self.service.stop()


if __name__ == "__main__":
    unittest.main()
