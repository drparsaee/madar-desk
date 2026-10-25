"""Custom priority definitions, migration, persistence and LAN permissions."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app
from data_model import (DEFAULT_PRIORITY_DEFINITIONS, normalize_plus,
                        priority_definition_ids, validate_plus)
from lan import LanService


CUSTOM = {"id": "p-critical001", "label": "خیلی\u200cمهم", "color": "#FF00cc", "effect": "neon"}


class PriorityDataTests(unittest.TestCase):
    def test_legacy_optional_settings_keep_same_tasks_and_default_ids(self):
        old = native_app.initial_state()
        old["settings"].pop("priorityDefinitions", None)
        original = deepcopy(old)
        self.assertTrue(validate_plus(old))
        self.assertEqual(normalize_plus(old)["settings"], old["settings"])
        self.assertEqual(old, original)
        migrated = native_app.normalize_state(old)
        self.assertEqual(migrated["settings"]["priorityDefinitions"], DEFAULT_PRIORITY_DEFINITIONS)
        self.assertEqual([task["priority"] for task in migrated["tasks"]],
                         [task["priority"] for task in old["tasks"]])
        self.assertTrue(native_app.is_valid(migrated))
        self.assertEqual(native_app.normalize_state(migrated), migrated)
        self.assertEqual(native_app.normalize_state(json.loads(json.dumps(migrated))), migrated)

    def test_custom_priority_and_modified_builtin_are_retained(self):
        state = native_app.normalize_state(native_app.initial_state())
        state["settings"]["priorityDefinitions"][2].update({
            "label": "فوری", "color": "#Aa00cc", "effect": "pulse"})
        state["settings"]["priorityDefinitions"].append(deepcopy(CUSTOM))
        state["tasks"][0]["priority"] = CUSTOM["id"]
        self.assertTrue(native_app.is_valid(state))
        self.assertTrue(validate_plus(state))
        self.assertIn(CUSTOM["id"], priority_definition_ids(state["settings"]))
        self.assertEqual(native_app.normalize_state(state), state)
        self.assertEqual(normalize_plus(state)["tasks"][0]["priority"], CUSTOM["id"])

    def test_thirty_definitions_supported_with_last_custom_assigned(self):
        state = native_app.normalize_state(native_app.initial_state())
        extras = [{"id": f"p-extra{i:03d}", "label": f"شماره {i}",
                   "color": "#abcdef", "effect": "solid"} for i in range(27)]
        state["settings"]["priorityDefinitions"].extend(extras)
        state["tasks"][0]["priority"] = extras[-1]["id"]
        self.assertEqual(len(state["settings"]["priorityDefinitions"]), 30)
        self.assertTrue(native_app.is_valid(state))
        self.assertTrue(validate_plus(state))

    def test_invalid_lists_and_cross_references_rejected_without_mutation(self):
        good = native_app.normalize_state(native_app.initial_state())
        samples = [
            [], None, {}, "low", [*deepcopy(DEFAULT_PRIORITY_DEFINITIONS), deepcopy(DEFAULT_PRIORITY_DEFINITIONS[0])],
            deepcopy(DEFAULT_PRIORITY_DEFINITIONS[1:]),
            [*deepcopy(DEFAULT_PRIORITY_DEFINITIONS), *[
                {"id": f"p-extra{i:03d}", "label": "x", "color": "#123456", "effect": "none"}
                for i in range(28)]],
        ]
        for index, bad in enumerate(samples):
            candidate = deepcopy(good)
            candidate["settings"]["priorityDefinitions"] = bad
            before = deepcopy(candidate)
            with self.subTest(index=index), self.assertRaises(ValueError):
                native_app.is_valid(candidate)
            self.assertEqual(candidate, before)
            with self.subTest(index=index), self.assertRaises(ValueError):
                validate_plus(candidate)

        invalid_definitions = [
            {**CUSTOM, "id": "custom"},
            {**CUSTOM, "id": "__proto__"},
            {**CUSTOM, "id": "p-Abc"},
            {**CUSTOM, "id": "p-ab"},
            {**CUSTOM, "id": "p-" + "a" * 33},
            {**CUSTOM, "label": " "},
            {**CUSTOM, "label": "A" * 61},
            {**CUSTOM, "label": "x\n<script>"},
            {**CUSTOM, "color": "red"},
            {**CUSTOM, "color": "#abc"},
            {**CUSTOM, "color": "#abcdef;opacity:0"},
            {**CUSTOM, "effect": "url(javascript:alert(1))"},
            {**CUSTOM, "effect": "blink"},
            {**CUSTOM, "effect": None},
            {**CUSTOM, "effect": ["neon"]},
            {**CUSTOM, "effect": {"effect": "neon"}},
            {**CUSTOM, "extra": "hidden"},
            {key: value for key, value in CUSTOM.items() if key != "effect"},
        ]
        for index, invalid in enumerate(invalid_definitions):
            candidate = deepcopy(good)
            candidate["settings"]["priorityDefinitions"].append(invalid)
            with self.subTest(index=index), self.assertRaises(ValueError):
                native_app.is_valid(candidate)
            with self.subTest(index=index), self.assertRaises(ValueError):
                native_app.normalize_state(candidate)

        unknown = deepcopy(good)
        unknown["tasks"][0]["priority"] = "p-missing"
        with self.assertRaises(ValueError):
            native_app.is_valid(unknown)
        with self.assertRaises(ValueError):
            validate_plus(unknown)

        active_custom = deepcopy(good)
        active_custom["settings"]["priorityDefinitions"].append(deepcopy(CUSTOM))
        active_custom["tasks"][0]["priority"] = CUSTOM["id"]
        active_custom["settings"]["priorityDefinitions"].pop()
        with self.assertRaises(ValueError):
            native_app.is_valid(active_custom)


class PriorityBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="madar-priority-test-")
        self.root = Path(self.temporary.name)
        self.mock_dir = patch.object(native_app, "datadir", return_value=self.root)
        self.mock_dir.start()
        self.bridge = native_app.Bridge()

    def tearDown(self):
        self.mock_dir.stop()
        self.temporary.cleanup()

    def test_save_restart_backup_restore_and_atomic_rejection(self):
        state = self.bridge.getState()
        state["settings"]["priorityDefinitions"].append(deepcopy(CUSTOM))
        state["tasks"][0]["priority"] = CUSTOM["id"]
        self.bridge.saveState(state)
        self.assertEqual(native_app.Bridge().getState()["tasks"][0]["priority"], CUSTOM["id"])
        self.assertEqual(native_app.Bridge().getState()["settings"]["priorityDefinitions"][-1], CUSTOM)
        saved = self.bridge.path.read_bytes()

        invalid = deepcopy(self.bridge.getState())
        invalid["settings"]["priorityDefinitions"].pop()
        with self.assertRaises(ValueError):
            self.bridge.saveState(invalid)
        self.assertEqual(self.bridge.path.read_bytes(), saved)

        restored = deepcopy(self.bridge.getState())
        restored["projects"][0]["name"] = "restored"
        native_app.safe_restore(self.bridge.path, restored)
        self.assertEqual(native_app.Bridge().getState()["tasks"][0]["priority"], CUSTOM["id"])
        self.assertEqual(native_app.Bridge().getState()["settings"]["priorityDefinitions"][-1], CUSTOM)
        invalid_restore = deepcopy(restored)
        invalid_restore["settings"]["priorityDefinitions"][0]["color"] = "#badcolor"
        with self.assertRaises(ValueError):
            native_app.safe_restore(self.bridge.path, invalid_restore)
        self.assertEqual(native_app.Bridge().getState()["projects"][0]["name"], "restored")

    def test_lan_admin_updates_definitions_editor_can_use_but_not_change(self):
        lan = LanService(self.bridge, self.root / "users.json", bind="127.0.0.1", port=0)
        lan.setup_owner("admin", "strong-owner-password")
        admin = lan.authenticate("admin", "strong-owner-password")["token"]
        lan.upsert_user(admin, {"username": "editor", "password": "strong-editor-password",
                                "role": "editor", "projects": ["p-sample"]})
        editor = lan.authenticate("editor", "strong-editor-password")["token"]

        admin_view = lan.read_state(admin)
        payload = admin_view["state"]
        payload["settings"]["priorityDefinitions"].append(deepcopy(CUSTOM))
        lan.write_state(admin, payload, admin_view["revision"])
        editor_view = lan.read_state(editor)
        self.assertIn(CUSTOM, editor_view["state"]["settings"]["priorityDefinitions"])
        editor_edit = deepcopy(editor_view["state"])
        editor_edit["tasks"][0]["priority"] = CUSTOM["id"]
        lan.write_state(editor, editor_edit, editor_view["revision"])
        self.assertEqual(self.bridge.getState()["tasks"][0]["priority"], CUSTOM["id"])

        editor_view = lan.read_state(editor)
        forged = deepcopy(editor_view["state"])
        forged["settings"]["priorityDefinitions"].append({
            "id": "p-forged", "label": "forged", "color": "#123456", "effect": "solid"})
        with self.assertRaises(PermissionError):
            lan.write_state(editor, forged, editor_view["revision"])
        self.assertNotIn("p-forged", {p["id"] for p in self.bridge.getState()["settings"]["priorityDefinitions"]})


if __name__ == "__main__":
    unittest.main()
