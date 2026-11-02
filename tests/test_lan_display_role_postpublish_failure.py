"""Synthetic presentation-role catalog consistency after a failed publication."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from lan import LanService


class _Bridge:
    def __init__(self):
        self._lock = threading.RLock()

    def getState(self):
        return {"projects": [], "tasks": []}


class DisplayRolePostPublishFailureTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="madar-display-role-postpublish-")
        self.addCleanup(self.scratch.cleanup)
        self.service = LanService(_Bridge(), Path(self.scratch.name) / "users.json")
        self.service.setup_owner("owner", "synthetic-owner-password")
        self.admin = self.service.authenticate("owner", "synthetic-owner-password")["token"]
        self.role = {"id": "synthetic-role", "label": "Initial role", "displayMode": "basic",
                     "features": ["cards"]}
        self.service.upsert_display_role(self.admin, self.role)

    def _assert_original_catalog(self, original):
        self.assertEqual(json.loads(self.service.display_roles_path.read_text(encoding="utf8")), original)
        self.assertEqual(self.service.display_roles["synthetic-role"]["label"], "Initial role")
        reopened = LanService(_Bridge(), self.service.users_path)
        self.assertEqual(reopened.display_roles["synthetic-role"]["label"], "Initial role")

    def _postpublish_failure(self):
        from lan import atomic_json
        calls = []

        def fail_once(path, payload):
            calls.append(1)
            atomic_json(path, payload)
            if len(calls) == 1:
                raise OSError("synthetic error after catalog publication")

        return patch("lan.atomic_json", side_effect=fail_once), calls

    def test_failed_role_edit_does_not_survive_restart(self):
        before = json.loads(self.service.display_roles_path.read_text(encoding="utf8"))
        patcher, calls = self._postpublish_failure()
        with patcher, self.assertRaises(OSError):
            self.service.upsert_display_role(self.admin, {**self.role, "label": "Unconfirmed role"})
        self._assert_original_catalog(before)
        self.assertGreaterEqual(len(calls), 2)

    def test_failed_role_delete_does_not_survive_restart(self):
        before = json.loads(self.service.display_roles_path.read_text(encoding="utf8"))
        patcher, calls = self._postpublish_failure()
        with patcher, self.assertRaises(OSError):
            self.service.delete_display_role(self.admin, "synthetic-role")
        self._assert_original_catalog(before)
        self.assertGreaterEqual(len(calls), 2)

    def test_foreign_catalog_revision_is_not_overwritten(self):
        original = json.loads(self.service.display_roles_path.read_text(encoding="utf8"))
        foreign = json.loads(json.dumps(original))
        next(entry for entry in foreign["roles"] if entry["id"] == "synthetic-role")["label"] = "Foreign role"
        from lan import atomic_json

        def foreign_then_raise(path, _candidate):
            atomic_json(path, foreign)
            raise OSError("synthetic foreign writer")

        with patch("lan.atomic_json", side_effect=foreign_then_raise):
            with self.assertRaisesRegex(RuntimeError, "unexpected catalog revision"):
                self.service.upsert_display_role(self.admin, {**self.role, "label": "Unconfirmed role"})
        self.assertEqual(json.loads(self.service.display_roles_path.read_text(encoding="utf8")), foreign)
        self.assertEqual(self.service.display_roles["synthetic-role"]["label"], "Initial role")

    def test_first_catalog_publication_failure_removes_only_new_file(self):
        fresh = LanService(_Bridge(), Path(self.scratch.name) / "fresh-users.json")
        fresh.setup_owner("new-owner", "synthetic-new-owner-password")
        admin = fresh.authenticate("new-owner", "synthetic-new-owner-password")["token"]
        self.assertFalse(fresh.display_roles_path.exists())
        patcher, calls = self._postpublish_failure()
        with patcher, self.assertRaises(OSError):
            fresh.upsert_display_role(admin, self.role)
        self.assertEqual(len(calls), 1)
        self.assertFalse(fresh.display_roles_path.exists())
        self.assertNotIn("synthetic-role", fresh.display_roles)
        self.assertNotIn("synthetic-role", LanService(_Bridge(), fresh.users_path).display_roles)

    def test_catalog_compensation_failure_is_explicit(self):
        from lan import atomic_json
        calls = []

        def fail_both(path, payload):
            calls.append(1)
            if len(calls) == 1:
                atomic_json(path, payload)
            raise OSError("synthetic publication or compensation failure")

        with patch("lan.atomic_json", side_effect=fail_both):
            with self.assertRaisesRegex(RuntimeError, "catalog rollback failed"):
                self.service.upsert_display_role(self.admin, {**self.role, "label": "Unconfirmed role"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.service.display_roles["synthetic-role"]["label"], "Initial role")


if __name__ == "__main__":
    unittest.main()
