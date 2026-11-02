"""Synthetic LAN projection isolation: reading must not mutate host state."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from unittest import TestCase

from lan import LanService


class LiveStateBridge:
    """Return the same mutable state reference, like the desktop host bridge."""

    def __init__(self):
        self._lock = RLock()
        self.state = {
            "projects": [{"id": "p-visible", "price": 400},
                         {"id": "p-hidden", "price": 900}],
            "tasks": [{"id": "t-visible", "projectId": "p-visible", "cost": 70},
                      {"id": "t-hidden", "projectId": "p-hidden", "cost": 90}],
            "boards": [
                {"id": "b-visible", "projectId": "p-visible", "workspaceId": "w-visible",
                 "meta": {"label": "original-board"}},
                {"id": "b-hidden", "projectId": "p-hidden", "workspaceId": "w-hidden",
                 "meta": {"label": "hidden-board"}},
            ],
            "templates": [
                {"id": "tpl-visible", "boardId": "b-visible", "fields": {"hint": "original-template"}},
                {"id": "tpl-hidden", "boardId": "b-hidden", "fields": {"hint": "hidden-template"}},
            ],
            "workspaces": [
                {"id": "w-visible", "prefs": {"name": "original-workspace"}},
                {"id": "w-hidden", "prefs": {"name": "hidden-workspace"}},
            ],
            "stages": [], "settings": {},
        }

    def getState(self):
        return self.state


class LanReadProjectionAliasTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="madar-lan-projection-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.bridge = LiveStateBridge()
        self.service = LanService(self.bridge, Path(self.tmp.name) / "users.json",
                                  bind="127.0.0.1", port=0)
        self.service.setup_owner("admin", "synthetic-admin-password")
        admin_token = self.service.authenticate_owner_token()
        self.service.upsert_user(admin_token, {
            "username": "editor", "password": "synthetic-editor-password",
            "role": "editor", "projects": ["p-visible"],
        })
        self.editor_token = self.service.authenticate(
            "editor", "synthetic-editor-password")["token"]

    def test_scoped_projection_is_detached_from_host_structures(self):
        before = deepcopy(self.bridge.state)
        result = self.service.read_state(self.editor_token)["state"]
        self.assertEqual([x["id"] for x in result["boards"]], ["b-visible"])
        self.assertEqual([x["id"] for x in result["templates"]], ["tpl-visible"])
        self.assertEqual([x["id"] for x in result["workspaces"]], ["w-visible"])
        self.assertEqual(result["projects"][0]["price"], 0)
        self.assertEqual(result["tasks"][0]["cost"], 0)

        # An in-process reader may mutate the returned projection. It must
        # never modify the live host cache without the authorized save path.
        result["boards"][0]["meta"]["label"] = "tampered-board"
        result["templates"][0]["fields"]["hint"] = "tampered-template"
        result["workspaces"][0]["prefs"]["name"] = "tampered-workspace"
        self.assertEqual(self.bridge.state, before)

    def test_mutating_one_projection_does_not_change_subsequent_reads(self):
        first = self.service.read_state(self.editor_token)
        first["state"]["boards"][0]["meta"]["label"] = "uncommitted"
        second = self.service.read_state(self.editor_token)
        self.assertEqual(second["state"]["boards"][0]["meta"]["label"],
                         "original-board")
        self.assertEqual(first["revision"], second["revision"])
