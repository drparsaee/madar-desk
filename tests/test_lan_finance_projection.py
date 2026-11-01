"""M05 finance ACL acceptance against disposable LAN bridge and state store.

In-process LanService exercises host write/CAS and projection, not two-PC LAN.
"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import native_app
from tests.legacy_sample_fixture import seed_legacy_example_state
from lan import LanService


class LanFinanceProjection(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="madar-finance-lan-test-")
        self.root = Path(self.temp.name)
        self.mock = patch.object(native_app, "datadir", return_value=self.root)
        self.mock.start()
        self.bridge = seed_legacy_example_state(native_app.Bridge())
        self.server = LanService(self.bridge, self.root / "users.json", "127.0.0.1", 0)
        self.server.setup_owner("admin", "admin-test-password")
        self.admin = self.server.authenticate_owner_token()
        self.server.upsert_user(self.admin, {"username":"editor","password":"editor-test-password",
                                             "role":"editor","projects":["p-sample"]})
        self.server.upsert_user(self.admin, {"username":"viewer","password":"viewer-test-password",
                                             "role":"viewer","projects":["p-sample"]})
        self.editor = self.server.authenticate("editor", "editor-test-password")["token"]
        self.viewer = self.server.authenticate("viewer", "viewer-test-password")["token"]
        state = self.bridge.getState()
        state["projects"][1]["price"] = 888
        state["tasks"][0]["cost"] = 350
        state["tasks"][0]["costEnabled"] = True
        state["tasks"][0]["costCategory"] = "shipping"
        state["tasks"][0]["checklist"][0]["cost"] = 75
        self.bridge.saveState(state)

    def tearDown(self):
        self.mock.stop()
        self.temp.cleanup()

    def test_nonadmin_projection_excludes_all_structured_costs(self):
        admin = self.server.read_state(self.admin)["state"]
        self.assertEqual(admin["tasks"][0]["cost"], 350)
        self.assertEqual(admin["projects"][1]["price"], 888)
        for token in (self.editor, self.viewer):
            state = self.server.read_state(token)["state"]
            self.assertEqual([p["id"] for p in state["projects"]], ["p-sample"])
            self.assertEqual(state["projects"][0]["price"], 0)
            card = state["tasks"][0]
            self.assertEqual(card["cost"], 0)
            self.assertEqual(card["costCategory"], "")
            self.assertIsNone(card["costEnabled"])
            self.assertEqual(card["checklist"][0]["cost"], 0)
            self.assertEqual(card["checklists"][0]["items"][0]["cost"], 0)

    def test_editor_can_save_nonfinance_and_finance_survives(self):
        read = self.server.read_state(self.editor)
        edited = read["state"]
        edited["tasks"][0]["title"] = "Safe updated task"
        edited["tasks"][0]["checklist"][0]["done"] = True
        self.server.write_state(self.editor, edited, read["revision"])
        saved = self.bridge.getState()
        self.assertEqual(saved["tasks"][0]["title"], "Safe updated task")
        self.assertEqual(saved["tasks"][0]["cost"], 350)
        self.assertEqual(saved["tasks"][0]["checklist"][0]["cost"], 75)
        self.assertEqual(saved["tasks"][0]["checklists"][0]["items"][0]["cost"], 75)

    def test_editor_cannot_inject_cost_or_delete_paid_card(self):
        read = self.server.read_state(self.editor)
        changed = deepcopy(read["state"])
        changed["tasks"][0]["cost"] = 9000
        with self.assertRaises(PermissionError):
            self.server.write_state(self.editor, changed, read["revision"])
        changed = deepcopy(read["state"])
        changed["tasks"] = [x for x in changed["tasks"] if x["id"] != changed["tasks"][0]["id"]]
        with self.assertRaises(PermissionError):
            self.server.write_state(self.editor, changed, read["revision"])
        self.assertEqual(self.bridge.getState()["tasks"][0]["cost"], 350)

    def test_unrelated_hidden_project_and_stale_cas_safe(self):
        read = self.server.read_state(self.editor)
        self.assertTrue(all(t["projectId"] == "p-sample" for t in read["state"]["tasks"]))
        first = deepcopy(read["state"])
        first["tasks"][0]["title"] = "first"
        self.server.write_state(self.editor, first, read["revision"])
        old = deepcopy(read["state"])
        old["tasks"][0]["title"] = "second"
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            self.server.write_state(self.editor, old, read["revision"])
