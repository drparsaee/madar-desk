"""Pure state operations for Madar workspace/card extension compatibility."""

import copy
import unittest

from data_model import (
    create_workspace, delete_empty_workspace, move_board_workspace,
    normalize_plus, rename_workspace, set_workspace_archived, validate_plus,
)


def baseline():
    return normalize_plus({
        "version": 1,
        "projects": [{"id": "p1", "name": "Project", "price": 65000, "costEnabled": True}],
        "tasks": [{
            "id": "t1", "projectId": "p1", "title": "Test", "status": "active",
            "priority": "high", "cost": 155, "labels": [], "reports": [],
            "checklist": [{"id": "step1", "text": "Paid step", "done": False,
                           "cost": 125, "costCategory": "print"}],
        }],
        "stages": [{"id": "active", "label": "Active"}],
        "settings": {"theme": "light"},
    })


class WorkspaceOperations(unittest.TestCase):
    def test_create_rename_archive_restore_delete_empty_without_mutation(self):
        source = baseline()
        untouched = copy.deepcopy(source)
        state = create_workspace(source, "ws-team", "  تیم چاپ  ")
        self.assertEqual(source, untouched)
        self.assertEqual(state["workspaces"][1]["name"], "تیم چاپ")
        state = rename_workspace(state, "ws-team", "QC")
        state = set_workspace_archived(state, "ws-team")
        self.assertTrue(state["workspaces"][1]["archived"])
        state = set_workspace_archived(state, "ws-team", False)
        self.assertFalse(state["workspaces"][1]["archived"])
        state = delete_empty_workspace(state, "ws-team")
        self.assertEqual(len(state["workspaces"]), 1)
        self.assertTrue(validate_plus(state))
        self.assertEqual(normalize_plus(state), state)

    def test_move_board_is_reference_only_and_preserves_money_checklists(self):
        source = baseline()
        source_task = copy.deepcopy(source["tasks"][0])
        state = create_workspace(source, "ws-new", "Other")
        state = move_board_workspace(state, state["boards"][0]["id"], "ws-new")
        self.assertEqual(state["boards"][0]["workspaceId"], "ws-new")
        self.assertEqual(state["tasks"][0], source_task)
        self.assertEqual(state["projects"][0]["price"], 65000)
        self.assertTrue(validate_plus(state))
        self.assertEqual(normalize_plus(state), state)

    def test_references_and_last_active_workspace_guarded(self):
        original = baseline()
        with self.assertRaisesRegex(ValueError, "last active"):
            set_workspace_archived(original, original["workspaces"][0]["id"])
        with self.assertRaisesRegex(ValueError, "last workspace"):
            delete_empty_workspace(original, original["workspaces"][0]["id"])
        state = create_workspace(original, "ws-team", "Team")
        with self.assertRaisesRegex(ValueError, "already exists"):
            create_workspace(state, "ws-team", "Duplicated")
        with self.assertRaisesRegex(ValueError, "boards first"):
            delete_empty_workspace(state, original["workspaces"][0]["id"])
        state = set_workspace_archived(state, "ws-team")
        with self.assertRaisesRegex(ValueError, "active destination"):
            move_board_workspace(state, state["boards"][0]["id"], "ws-team")
        self.assertEqual(original, baseline())

    def test_workspace_helpers_refuse_malformed_or_unknown_ids(self):
        state = baseline()
        for action in [
            lambda: create_workspace(state, "", "name"),
            lambda: create_workspace(state, "new", "   "),
            lambda: create_workspace(state, "x" * 101, "A"),
            lambda: rename_workspace(state, "absent", "X"),
            lambda: set_workspace_archived(state, "absent"),
            lambda: set_workspace_archived(state, "workspace-legacy", "yes"),
            lambda: move_board_workspace(state, "unknown", "workspace-legacy"),
            lambda: delete_empty_workspace(state, "unknown"),
        ]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                action()


class CardCoverValidation(unittest.TestCase):
    def test_color_only_cover_roundtrips_without_affecting_costs(self):
        state = baseline()
        state["tasks"][0]["cover"] = {"type": "color", "color": "#AB12cc", "size": "strip"}
        self.assertTrue(validate_plus(state))
        self.assertEqual(normalize_plus(state), state)
        self.assertEqual(state["tasks"][0]["cost"], 155)
        self.assertEqual(state["tasks"][0]["checklist"][0]["cost"], 125)
        state["tasks"][0]["cover"]["size"] = "full"
        self.assertTrue(validate_plus(state))
        state["tasks"][0]["cover"] = None
        self.assertTrue(validate_plus(state))

    def test_rejects_css_script_urls_and_bad_cover_shapes(self):
        cases = [
            {"type": "url", "color": "#123456", "size": "strip"},
            {"type": "color", "color": "red; background:url(javascript:alert(1))", "size": "strip"},
            {"type": "color", "color": "#123456", "size": "full", "url": "https://test"},
            {"type": "color", "color": "#123456", "size": ["full"]},
            {"type": "color", "color": "#123456", "size": "wide"},
            {"type": "image", "src": "data:image/svg+xml,<svg onload=alert(1)>"},
            "#123456", [], {},
        ]
        for cover in cases:
            with self.subTest(cover=cover):
                state = baseline()
                state["tasks"][0]["cover"] = cover
                with self.assertRaisesRegex(ValueError, "cover"):
                    validate_plus(state)
                with self.assertRaises(ValueError):
                    normalize_plus(state)

    def test_native_validator_accepts_safe_cover_and_named_steps(self):
        from native_app import is_valid
        state = baseline()
        state["tasks"][0]["cover"] = {"type": "color", "color": "#345678", "size": "full"}
        state["tasks"][0]["checklists"].append({"id": "qa", "name": "QA", "items": [
            {"id": "check-1", "text": "Print", "done": True, "cost": 0}]})
        state["boards"][0]["customFields"] = [{"id": "sku", "name": "SKU", "type": "text"}]
        state["tasks"][0]["customFieldValues"] = {"sku": "ABC-123"}
        self.assertTrue(is_valid(state))
        self.assertEqual(normalize_plus(state), state)


if __name__ == "__main__":
    unittest.main()
