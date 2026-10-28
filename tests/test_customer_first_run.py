"""A clean customer account must never start with sample business data."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app


class CustomerFirstRunTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-empty-first-run-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, {"APPDATA": str(self.root / "Roaming"),
                                      "LOCALAPPDATA": str(self.root / "Local")})
        env.start()
        self.addCleanup(env.stop)

    def test_new_profile_starts_with_workspace_only_and_survives_restart(self):
        bridge = native_app.Bridge()
        actual = bridge.getState()
        self.assertEqual(actual["projects"], [])
        self.assertEqual(actual["boards"], [])
        self.assertEqual(actual["tasks"], [])
        self.assertEqual([item["name"] for item in actual["workspaces"]],
                         ["فضای کاری من"])
        self.assertGreater(len(actual["stages"]), 0)
        self.assertTrue(native_app.is_valid(actual))
        first_bytes = bridge.path.read_bytes()
        self.assertEqual(native_app.Bridge().getState(), actual)
        self.assertEqual(bridge.path.read_bytes(), first_bytes)

    def test_update_does_not_clear_or_reseed_existing_profile(self):
        data_root = self.root / "Roaming" / "MadarDesk"
        data_root.mkdir(parents=True)
        legacy = native_app.normalize_state(native_app.initial_state())
        (data_root / "tasks.json").write_text(
            json.dumps(legacy, ensure_ascii=False), encoding="utf8")
        old_bytes = (data_root / "tasks.json").read_bytes()
        upgraded = native_app.Bridge()
        self.assertEqual(upgraded.getState()["projects"], legacy["projects"])
        self.assertEqual(len(upgraded.getState()["tasks"]), len(legacy["tasks"]))
        self.assertEqual((data_root / "tasks.json").read_bytes(), old_bytes)

    def test_empty_profile_stays_empty_after_normalization(self):
        empty = native_app.normalize_state(native_app.empty_initial_state())
        self.assertEqual(empty["projects"], [])
        self.assertEqual(empty["boards"], [])
        self.assertEqual(empty["tasks"], [])
        self.assertEqual(len(empty["workspaces"]), 1)


if __name__ == "__main__":
    unittest.main()
