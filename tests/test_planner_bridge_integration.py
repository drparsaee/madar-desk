"""Native Bridge integration against a disposable Windows APPDATA root only."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from native_app import Bridge


@contextmanager
def isolated_bridge_profile():
    with tempfile.TemporaryDirectory(prefix="madar-planner-bridge-qa-") as scratch:
        root = Path(scratch)
        with patch.dict(os.environ, {"APPDATA": str(root / "Roaming"),
                                     "LOCALAPPDATA": str(root / "Local")}, clear=False):
            yield root


class PlannerBridgeIntegrationTests(unittest.TestCase):
    def test_planner_survives_new_bridge_with_identical_user_profile(self):
        state = {"version": 1, "inbox": [{
            "id": "new-private-task", "title": "کار مهم", "notes": "متن یادداشت",
            "createdDate": "2026-10-28", "dueDate": "", "doneAt": "",
            "repeatAnchor": "", "remindTime": "", "dismissedFor": "",
            "repeat": {"frequency": "none", "interval": 1, "calendar": "gregorian"}
        }], "entries": []}
        with isolated_bridge_profile() as root:
            first = Bridge()
            self.assertIsNone(first.plannerRead("solo"))
            self.assertEqual(first.plannerWrite("solo", state), state)
            self.assertEqual(Bridge().plannerRead("solo"), state)
            self.assertIsNone(Bridge().plannerRead("another-user"))
            self.assertTrue((root / "Roaming" / "MadarDesk" / "planner-private-v1").is_dir())
            # An invalid or future schema never replaces the last valid state.
            with self.assertRaises(ValueError):
                first.plannerWrite("solo", {"version": 2, "inbox": [], "entries": []})
            self.assertEqual(Bridge().plannerRead("solo"), state)

    def test_native_bridge_accepts_frontend_solo_and_remote_account_identity(self):
        state = {"version": 1, "inbox": [], "entries": []}
        solo = '["solo","local"]'
        remote = '["client","http://127.0.0.1:48370","","alice"]'
        with isolated_bridge_profile():
            bridge = Bridge()
            self.assertIsNone(bridge.plannerRead(solo))
            self.assertEqual(bridge.plannerWrite(solo, state), state)
            self.assertEqual(Bridge().plannerRead(solo), state)
            self.assertIsNone(bridge.plannerRead(remote))


if __name__ == "__main__":
    unittest.main()
