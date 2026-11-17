"""Isolated AI entitlement tests. No Ollama, live users or external API."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import native_app
from lan import LanService


class AiUserAdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-ai-users-")
        self.root = Path(self.tmp.name)
        self.datadir_patch = patch.object(native_app, "datadir", return_value=self.root)
        self.datadir_patch.start()
        self.bridge = native_app.Bridge()
        self.bridge.saveState(native_app.initial_state())
        self.host = LanService(self.bridge, self.root / "users.json", "127.0.0.1", 0)
        self.host.setup_owner("owner", "synthetic-owner-password")
        self.port = self.host.start()
        self.url = f"http://127.0.0.1:{self.port}"
        self.owner = self.request("/api/login", {
            "username": "owner", "password": "synthetic-owner-password"
        })["token"]

    def tearDown(self):
        self.host.stop()
        self.datadir_patch.stop()
        self.tmp.cleanup()

    def request(self, route, payload=None, token=None):
        req = Request(self.url + route,
                      data=(json.dumps(payload).encode("utf8") if payload is not None else None),
                      headers={"Content-Type": "application/json",
                               **({"Authorization": "Bearer " + token} if token else {})})
        with urlopen(req, timeout=8) as result:
            return json.load(result)

    def editor(self):
        self.request("/api/user", {"username": "editor", "password": "synthetic-editor-password",
                                   "role": "editor", "projects": ["p-sample"]}, self.owner)
        return self.request("/api/login", {
            "username": "editor", "password": "synthetic-editor-password"
        })["token"]

    def assert_status(self, expected, action):
        with self.assertRaises(HTTPError) as context:
            action()
        self.assertEqual(context.exception.code, expected)

    def test_existing_accounts_deny_by_default_and_admin_revocation_immediate(self):
        editor = self.editor()
        body = {"projectId": "p-sample"}
        self.assert_status(403, lambda: self.request("/api/ai/authorize", body, editor))
        self.assert_status(403, lambda: self.request("/api/ai/authorize", body))
        self.assert_status(403, lambda: self.request("/api/user", {
            "username": "editor", "aiEnabled": True}, editor))
        self.assertFalse(next(u for u in self.request("/api/users", token=self.owner)["users"]
                              if u["username"] == "editor")["aiEnabled"])
        self.request("/api/user", {"username": "editor", "aiEnabled": True}, self.owner)
        self.assertEqual(self.request("/api/ai/authorize", body, editor),
                         {"allowed": True, "provider": "local_ollama", "policyVersion": 1})
        # No financial state, prompt or model key is transferred in this API.
        self.assert_status(403, lambda: self.request("/api/ai/authorize", {
            "projectId": "other-project"}, editor))
        self.assert_status(403, lambda: self.request("/api/ai/authorize", {
            "projectId": "not-in-state"}, self.owner))
        self.request("/api/user", {"username": "editor", "aiEnabled": False}, self.owner)
        self.assert_status(403, lambda: self.request("/api/ai/authorize", body, editor))

    def test_ai_permission_persists_but_cannot_be_escalated_from_profile(self):
        editor = self.editor()
        self.assert_status(403, lambda: self.request("/api/profile", {
            "aiEnabled": True}, editor))
        self.assert_status(400, lambda: self.request("/api/user", {
            "username": "editor", "aiEnabled": "true"}, self.owner))
        self.request("/api/user", {"username": "editor", "aiEnabled": True}, self.owner)
        self.request("/api/user", {"username": "editor", "displayName": "Sample"}, self.owner)
        self.assertTrue(self.host.users["editor"]["aiEnabled"])
        recovered = LanService(self.bridge, self.root / "users.json", "127.0.0.1", 0)
        self.assertTrue(recovered.users["editor"]["aiEnabled"])
        self.request("/api/user", {"username": "editor", "role": "viewer"}, self.owner)
        self.assertFalse(self.host.users["editor"]["aiEnabled"])
        self.assert_status(400, lambda: self.request("/api/user", {
            "username": "editor", "aiEnabled": True}, self.owner))
        self.assert_status(403, lambda: self.request("/api/ai/authorize", {
            "projectId": "p-sample"}, editor))

    def test_native_blocks_ai_when_host_policy_rejects_and_never_calls_model(self):
        client = native_app.Bridge()
        client.connection = {"mode": "client"}
        client.remote_user = {"role": "editor", "projects": ["p-sample"]}
        with patch.object(client, "getState", return_value=native_app.initial_state()), \
             patch.object(client, "_remote_request", side_effect=PermissionError("revoked")) as host, \
             patch("madar_ai_draft.generate_task_draft") as model:
            with self.assertRaises(PermissionError):
                client.aiDraftSuggest("example-2", "synthetic task", True)
            host.assert_called_once_with("/api/ai/authorize", {"projectId": "p-sample"})
            model.assert_not_called()

    def test_native_does_not_trust_incomplete_host_authorization(self):
        client = native_app.Bridge()
        client.connection = {"mode": "client"}
        client.remote_user = {"role": "editor", "projects": ["p-sample"]}
        with patch.object(client, "getState", return_value=native_app.initial_state()), \
             patch.object(client, "_remote_request", return_value={"allowed": True}), \
             patch("madar_ai_draft.generate_task_draft") as model:
            with self.assertRaises(PermissionError):
                client.aiDraftSuggest("example-2", "synthetic task", True)
            model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
