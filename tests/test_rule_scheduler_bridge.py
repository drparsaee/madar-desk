import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import native_app
from lan import LanService


class SchedulerBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(native_app, "datadir", return_value=self.root)
        self.patch.start()
        self.bridge = native_app.Bridge()

    def tearDown(self):
        self.bridge.stopScheduledJobs()
        self.patch.stop()
        self.temp.cleanup()

    def test_solo_due_date_rules_are_durable_and_idempotent(self):
        state = self.bridge.getState()
        card = next(t for t in state["tasks"] if t["id"] == "example-2")
        card["dueDate"] = datetime.now().date().isoformat()
        self.bridge.saveState(state)
        self.bridge.collabCommand({"type": "rule.upsert", "eventId": "rule-add",
                                   "rule": {"id": "rule-due", "projectId": "p-sample",
                                            "trigger": "due_soon", "conditions": [],
                                            "actions": [{"type": "comment", "text": "موعد امروز"}],
                                            "enabled": True}})
        self.assertEqual(len(self.bridge.collabRead("rules", "p-sample")), 1)
        run = self.bridge.runDueScheduler()
        self.assertGreaterEqual(run["events"], 1)
        self.assertGreaterEqual(run["new"], 1)
        self.assertEqual(len(self.bridge.collabRead("comments", "example-2")), 1)
        second = self.bridge.runDueScheduler()
        self.assertEqual(second["new"], 0)
        reopened = native_app.Bridge()
        self.assertEqual(len(reopened.collabRead("comments", "example-2")), 1)

    def test_lan_rule_view_and_scheduler_require_admin(self):
        server = LanService(self.bridge, self.root / "users.json", bind="127.0.0.1", port=0)
        server.setup_owner("admin", "long-admin-pass-2026")
        admin = server.authenticate("admin", "long-admin-pass-2026")["token"]
        server.upsert_user(admin, {"username": "reader", "password": "long-reader-pass-2026",
                                   "role": "viewer", "projects": ["p-sample"]})
        viewer = server.authenticate("reader", "long-reader-pass-2026")["token"]
        with self.assertRaises(PermissionError):
            server.collab_read(viewer, "rules", "p-sample")
        with self.assertRaises(PermissionError):
            server.run_scheduler(viewer)
        self.assertEqual(server.run_scheduler(admin)["new"], 0)


if __name__ == "__main__":
    unittest.main()
