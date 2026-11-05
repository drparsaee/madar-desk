"""Isolated project identity regression checks: no operational profile read."""
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_app
from project_integrity import ensure_project_identity_preserved, ensure_partial_restore_safe


class ProjectIdentityTests(unittest.TestCase):
    def setUp(self):
        self.original = native_app.initial_state()

    def test_reparent_existing_card_fails_without_mutation(self):
        candidate = deepcopy(self.original)
        original_project = candidate["tasks"][0]["projectId"]
        candidate["tasks"][0]["projectId"] = next(
            p["id"] for p in candidate["projects"] if p["id"] != original_project)
        with self.assertRaisesRegex(PermissionError, "انتقال کارت"):
            ensure_project_identity_preserved(self.original, candidate)
        self.assertEqual(self.original["tasks"][0]["projectId"], original_project)

    def test_removed_empty_project_with_other_user_grant_fails(self):
        candidate = deepcopy(self.original)
        candidate["projects"].append({"id": "empty", "name": "Empty"})
        future = deepcopy(candidate)
        future["projects"] = [p for p in future["projects"] if p["id"] != "empty"]
        with self.assertRaisesRegex(PermissionError, "دسترسی فعال"):
            ensure_project_identity_preserved(candidate, future,
                accounts={"viewer": {"role": "viewer", "projects": ["empty"]}})
        with self.assertRaisesRegex(ValueError, "تاریخچه"):
            ensure_project_identity_preserved(candidate, future,
                collaboration={"activity": [{"projectId": "empty"}]})
        ensure_project_identity_preserved(candidate, future,
            accounts={"viewer": {"role": "viewer", "projects": []}},
            collaboration={"activity": []})

    def test_bridge_rejects_reparent_before_any_persistence(self):
        with tempfile.TemporaryDirectory(prefix="madar-project-identity-") as path:
            with patch.object(native_app, "datadir", return_value=Path(path)):
                bridge = native_app.Bridge()
                bridge.saveState(native_app.initial_state())
                initial = bridge.getState()
                first_project = initial["tasks"][0]["projectId"]
                other_project = next(p["id"] for p in initial["projects"]
                                     if p["id"] != first_project)
                changed = deepcopy(initial)
                changed["tasks"][0]["projectId"] = other_project
                with self.assertRaisesRegex((ValueError, PermissionError), "project|انتقال کارت"):
                    bridge.saveState(changed)
                self.assertEqual(bridge.getState(), initial)

    def test_partial_json_restore_rejects_lost_collaboration_card(self):
        source = deepcopy(self.original)
        card = source["tasks"][0]
        candidate = deepcopy(source)
        candidate["tasks"] = [t for t in candidate["tasks"] if t["id"] != card["id"]]
        historical = {"comments": [{"cardId": card["id"],
                                   "projectId": card["projectId"]}],
                      "notifications": [], "activity": [], "watchers": {}}
        with self.assertRaisesRegex(PermissionError, "پشتیبان"):
            ensure_partial_restore_safe(source, candidate,
                collaboration=historical, finance={})
        self.assertEqual(source["tasks"][0]["id"], card["id"])

    def test_partial_restore_rejects_ledger_identity_reuse(self):
        original = deepcopy(self.original)
        absent = original["tasks"].pop()
        restored = deepcopy(original)
        restored["tasks"].append(absent)
        with self.assertRaisesRegex(PermissionError, "سند مالی قدیمی"):
            ensure_partial_restore_safe(original, restored, collaboration={},
                finance={"invoices": [{"cardId": absent["id"],
                                       "projectId": absent["projectId"]}]})

    def test_partial_restore_allows_title_recovery_without_erasing_comments(self):
        source = deepcopy(self.original)
        card = source["tasks"][0]
        candidate = deepcopy(source)
        candidate["tasks"][0]["title"] = "Restored title"
        ensure_partial_restore_safe(source, candidate,
            collaboration={"comments": [{"cardId": card["id"],
                                        "projectId": card["projectId"]}]},
            finance={"contracts": [], "invoices": []})
        self.assertNotEqual(candidate["tasks"][0]["title"], card["title"])

    def test_event_cap_is_checked_before_completion_outbox_write(self):
        with tempfile.TemporaryDirectory(prefix="madar-event-preflight-") as path:
            with patch.object(native_app, "datadir", return_value=Path(path)):
                bridge = native_app.Bridge()
                bridge.saveState(native_app.initial_state())
                before = bridge.getState()
                changed = deepcopy(before)
                changed["tasks"][1]["status"] = "done"
                original_outbox = (bridge.finance_outbox_path.read_bytes()
                                   if bridge.finance_outbox_path.exists() else None)
                with patch.object(native_app, "card_change_events",
                                  side_effect=ValueError("Too many card events in one save")):
                    with self.assertRaisesRegex(ValueError, "Too many card events"):
                        bridge.saveState(changed)
                outbox = (bridge.finance_outbox_path.read_bytes()
                          if bridge.finance_outbox_path.exists() else None)
                self.assertEqual(outbox, original_outbox)
                self.assertEqual(bridge.getState(), before)


if __name__ == "__main__":
    unittest.main()
