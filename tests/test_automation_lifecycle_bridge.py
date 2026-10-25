import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_app
from lan import LanService


class LifecycleBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(native_app, "datadir", return_value=Path(self.temp.name))
        self.patch.start()
        self.bridge = native_app.Bridge()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_task_move_automatically_runs_rule_and_keeps_single_receipt(self):
        self.bridge.collabCommand({
            "type":"rule.upsert","eventId":"make-rule","rule":{
                "id":"rule-move","projectId":"p-sample","trigger":"card_moved",
                "conditions":[{"field":"toColumnId","equals":"done"}],
                "actions":[{"type":"comment","text":"به پایان رسید"}],"enabled":True
            }})
        state = self.bridge.getState()
        edited = next(card for card in state["tasks"] if card["id"] == "example-2")
        edited["status"] = edited["listId"] = "done"
        self.bridge.saveState(state)
        self.assertEqual(len(self.bridge.collabRead("comments", "example-2")), 1)
        self.assertEqual(self.bridge._pending_automation_events(), [])
        self.bridge.saveState(self.bridge.getState())
        self.assertEqual(len(self.bridge.collabRead("comments", "example-2")), 1)

    def test_lan_role_is_authoritative_for_card_events(self):
        service = LanService(self.bridge, Path(self.temp.name)/"users.json",bind="127.0.0.1",port=0)
        service.setup_owner("admin","secure-admin-password")
        admin = service.authenticate("admin","secure-admin-password")["token"]
        service.upsert_user(admin,{"username":"author","password":"secure-author-password",
                                  "role":"editor","projects":["p-sample"]})
        writer = service.authenticate("author","secure-author-password")["token"]
        service.collab_command(admin,{"type":"rule.upsert","eventId":"make-rule",
          "rule":{"id":"rule-move","projectId":"p-sample","trigger":"card_moved",
          "conditions":[],"actions":[{"type":"comment","text":"ثبت خودکار"}],"enabled":True}})
        view = service.read_state(writer)
        task = next(t for t in view["state"]["tasks"] if t["id"] == "example-2")
        task["status"] = task["listId"] = "review"
        service.write_state(writer,view["state"],view["revision"])
        comments = service.collab_read(admin,"comments","example-2")
        self.assertEqual(len(comments),1)
        self.assertEqual(comments[0]["author"],"author")


if __name__ == "__main__":
    unittest.main()
