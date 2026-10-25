"""Release-critical HTTP integration: scoped boards, CAS and financial ACL.

Requests use a random localhost port, real LAN dispatch, and synthetic APPDATA.
The server is always stopped before the temporary Windows data root is removed.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import native_app
from lan import LanService
from test_release_persistence import contract


class ReleaseLanIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-release-lan-appdata-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, {"APPDATA": str(self.root),
                                   "LOCALAPPDATA": str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        self.bridge = native_app.Bridge()
        self.server = LanService(self.bridge, self.root / "accounts.json", "127.0.0.1", 0)
        self.server.setup_owner("owner", "release-owner-password")
        self.server.start()
        self.addCleanup(self.server.stop)
        self.base = f"http://127.0.0.1:{self.server.port}"
        self.owner = self.request("/api/login", {
            "username": "owner", "password": "release-owner-password"})["token"]
        for username, role, projects in (
            ("editor", "editor", ["p-sample"]),
            ("viewer", "viewer", ["p-sample"]),
            ("other", "editor", ["p-personal"]),
        ):
            self.request("/api/user", {"username": username, "role": role,
                                        "projects": projects,
                                        "password": f"release-{username}-password"}, self.owner)
        self.editor = self._login("editor")
        self.viewer = self._login("viewer")
        self.other = self._login("other")

    def _login(self, username):
        return self.request("/api/login", {"username": username,
                            "password": f"release-{username}-password"})["token"]

    def request(self, endpoint, data=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        kwargs = {"headers": headers}
        if data is not None:
            kwargs["data"] = json.dumps(data, ensure_ascii=False).encode("utf8")
        with urlopen(Request(self.base + endpoint, **kwargs), timeout=8) as response:
            return json.loads(response.read())

    def assert_http_error(self, expected, endpoint, data=None, token=None):
        with self.assertRaises(HTTPError) as captured:
            self.request(endpoint, data, token)
        self.assertEqual(captured.exception.code, expected)
        captured.exception.close()

    def test_scope_filters_board_structure_and_only_admin_can_edit_it(self):
        admin = self.request("/api/state", token=self.owner)
        self.assertEqual({p["id"] for p in admin["state"]["projects"]},
                         {"p-personal", "p-sample"})
        sample = self.request("/api/state", token=self.editor)
        self.assertEqual({p["id"] for p in sample["state"]["projects"]}, {"p-sample"})
        self.assertEqual({b["projectId"] for b in sample["state"]["boards"]}, {"p-sample"})
        self.assertEqual({t["projectId"] for t in sample["state"]["tasks"]}, {"p-sample"})
        other = self.request("/api/state", token=self.other)
        self.assertEqual({b["projectId"] for b in other["state"]["boards"]},
                         {"p-personal"})

        malicious = deepcopy(sample["state"])
        malicious["boards"][0]["name"] = "Unauthorised board rename"
        self.assert_http_error(403, "/api/state", {"state": malicious,
                                                   "revision": sample["revision"]}, self.editor)

        admin_edit = deepcopy(admin["state"])
        board = next(b for b in admin_edit["boards"] if b["projectId"] == "p-sample")
        board["stages"].append({"id": "http-qa", "label": "QA", "subtitle": "",
                                "color": "#444444"})
        self.request("/api/state", {"state": admin_edit,
                                     "revision": admin["revision"]}, self.owner)
        after = self.request("/api/state", token=self.editor)
        self.assertIn("http-qa", [stage["id"] for stage in after["state"]["boards"][0]["stages"]])

    def test_http_editor_save_stale_cas_and_viewer_rejection(self):
        snapshot = self.request("/api/state", token=self.editor)
        first = deepcopy(snapshot["state"])
        first["tasks"][0]["title"] = "Editor update over real HTTP"
        saved = self.request("/api/state", {"state": first,
                                            "revision": snapshot["revision"]}, self.editor)
        self.assertNotEqual(saved["revision"], snapshot["revision"])
        persisted = self.request("/api/state", token=self.owner)["state"]
        self.assertEqual(next(t for t in persisted["tasks"] if t["id"] == first["tasks"][0]["id"])
                         ["title"], "Editor update over real HTTP")
        self.assertEqual(len(persisted["boards"]), 2)

        stale = deepcopy(snapshot["state"])
        stale["tasks"][0]["title"] = "Old update must be rejected"
        self.assert_http_error(409, "/api/state", {
            "state": stale, "revision": snapshot["revision"]}, self.editor)
        self.assert_http_error(403, "/api/state", {
            "state": persisted, "revision": saved["revision"]}, self.viewer)
        self.assert_http_error(403, "/api/state")
        self.assertEqual(native_app.Bridge().getState()["boards"], persisted["boards"])

    def test_http_completion_creates_one_draft_with_financial_acl_after_restart(self):
        self.request("/api/finance", {"type": "contract.set", "eventId": "release-http-contract",
                                       "cardId": "example-2", "sale": contract(248_000)}, self.owner)
        state = self.request("/api/state", token=self.editor)
        edit = deepcopy(state["state"])
        target = next(card for card in edit["tasks"] if card["id"] == "example-2")
        target["status"] = "done"
        target["listId"] = "done"
        updated = self.request("/api/state", {"state": edit,
                                              "revision": state["revision"]}, self.editor)
        first = self.request("/api/finance?projectId=p-sample", token=self.owner)["invoices"]
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["status"], "Draft")
        self.assertEqual(first[0]["sale"]["total"], 248_000)
        self.request("/api/state", {"state": updated["state"],
                                     "revision": updated["revision"]}, self.editor)
        second = self.request("/api/finance?projectId=p-sample", token=self.owner)["invoices"]
        self.assertEqual([invoice["id"] for invoice in second], [first[0]["id"]])

        for restricted in (self.editor, self.viewer, self.other):
            self.assert_http_error(403, "/api/finance?projectId=p-sample", token=restricted)
        self.assert_http_error(403, "/api/finance-status", token=self.editor)
        self.assert_http_error(403, "/api/finance", {
            "type": "contract.set", "eventId": "unauthorized-contract",
            "cardId": "example-2", "sale": contract()}, self.editor)
        self.assert_http_error(403, "/api/finance?projectId=p-sample")
        fresh_host = native_app.Bridge()
        self.assertEqual(len(fresh_host._load_finance()["invoices"]), 1)

    def test_activated_sqlite_http_lifecycle_restores_all_four_domains(self):
        """Exercise opted-in transactional host storage from real LAN requests."""
        self.assertEqual(self.bridge.storageStatus()["mode"], "json")
        prior_json = self.bridge.path.read_bytes()
        self.assertEqual(self.bridge.enableUnifiedStorage()["mode"], "sqlite")
        self.request("/api/collab", {"type": "comment.add", "eventId": "release-sql-comment",
                                     "cardId": "example-2", "text": "Before SQL backup"}, self.owner)
        self.request("/api/finance", {"type": "contract.set", "eventId": "release-sql-contract",
                                      "cardId": "example-2", "sale": contract(300_000)}, self.owner)
        before = self.request("/api/state", token=self.editor)
        edited = deepcopy(before["state"])
        card = next(t for t in edited["tasks"] if t["id"] == "example-2")
        card["status"] = "done"
        card["listId"] = "done"
        self.request("/api/state", {"state": edited,
                                     "revision": before["revision"]}, self.editor)

        snapshot = self.bridge.createLocalBackup()
        self.assertFalse(snapshot["complete"])
        self.assertEqual(snapshot["scope"], "sqlite-domains-only")
        self.assertIn("attachment-binaries", snapshot["omitted"])
        self.assertTrue(snapshot["name"].endswith(".sqlite3"))
        first_invoice = self.request("/api/finance?projectId=p-sample", token=self.owner)["invoices"]
        self.assertEqual(len(first_invoice), 1)
        self.assertEqual(first_invoice[0]["sale"]["total"], 300_000)
        later = self.request("/api/state", token=self.owner)
        later_state = deepcopy(later["state"])
        later_state["tasks"][0]["title"] = "Should be rolled back"
        self.request("/api/state", {"state": later_state,
                                     "revision": later["revision"]}, self.owner)
        self.request("/api/collab", {"type": "comment.add", "eventId": "release-sql-later",
                                     "cardId": "example-2", "text": "After SQL backup"}, self.owner)
        self.assertEqual(len(self.request("/api/comments?cardId=example-2",
                                          token=self.owner)["items"]), 2)

        self.bridge.restoreLocalBackup(snapshot["name"])
        restored = native_app.Bridge()
        self.assertEqual(restored.storageStatus()["mode"], "sqlite")
        self.assertNotEqual(restored.getState()["tasks"][0]["title"], "Should be rolled back")
        self.assertEqual(len(restored.collabRead("comments", "example-2")), 1)
        self.assertEqual([x["id"] for x in restored.financeRead("p-sample")],
                         [first_invoice[0]["id"]])
        self.assertEqual(restored.financeStatus()["pending"], 0)
        self.assertEqual(self.bridge.path.read_bytes(), prior_json)
        self.assertTrue(list(self.bridge.backups_dir.glob("before-restore-*.sqlite3")))


if __name__ == "__main__":
    unittest.main()
