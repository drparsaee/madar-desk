"""Workspace structure, grants and compare-and-swap contract on disposable data.

The data-model helpers intentionally contain no user-ACL checks. LAN host
authorization and whole-state revision checks are verified separately.
"""

from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data_model import (create_workspace, delete_empty_workspace,
                        move_board_workspace, normalize_plus,
                        rename_workspace, set_workspace_archived, validate_plus)
from lan import LanService
import native_app
from tests.legacy_sample_fixture import seed_legacy_example_state


def enriched_state():
    state = native_app.initial_state()
    state["projects"][1].update(price=28_000_087, costEnabled=True)
    state["tasks"][0]["cost"] = 1_000_015
    state["tasks"][0]["checklist"][0]["cost"] = 777
    return native_app.normalize_state(state)


def protected_fields(state):
    """Data excluded from all workspace operations, including finance."""
    return {
        "projects": deepcopy(state["projects"]),
        "tasks": deepcopy(state["tasks"]),
        "settings": deepcopy(state["settings"]),
        "stages": deepcopy(state["stages"]),
    }


class PureWorkspaceContractTests(unittest.TestCase):
    def test_legacy_normalization_immutable_and_workspace_move_is_lossless(self):
        raw = native_app.initial_state()
        raw["projects"][1].update(price=28_000_087, costEnabled=True)
        raw["tasks"][0]["cost"] = 1_000_015
        raw["tasks"][0]["checklist"][0]["cost"] = 777
        source = deepcopy(raw)
        normalized = normalize_plus(raw)
        self.assertEqual(raw, source)
        self.assertEqual([w["id"] for w in normalized["workspaces"]], ["workspace-legacy"])
        self.assertTrue(validate_plus(normalized))
        finance = protected_fields(normalized)
        added = create_workspace(normalized, "workspace-production", "  تولید  ")
        self.assertEqual(added["workspaces"][1]["name"], "تولید")
        renamed = rename_workspace(added, "workspace-production", "کارگاه")
        board = next(b for b in renamed["boards"] if b["projectId"] == "p-sample")
        moved = move_board_workspace(renamed, board["id"], "workspace-production")
        board_after = next(b for b in moved["boards"] if b["id"] == board["id"])
        self.assertEqual(board_after["workspaceId"], "workspace-production")
        self.assertEqual(protected_fields(moved), finance)
        self.assertEqual(normalize_plus(moved), moved)
        self.assertTrue(all(b["workspaceId"] == "workspace-legacy"
                            for b in normalized["boards"]))

    def test_archive_restore_last_active_and_board_reference_guards(self):
        initial = normalize_plus(enriched_state())
        with self.assertRaisesRegex(ValueError, "last active"):
            set_workspace_archived(initial, "workspace-legacy")
        other = create_workspace(initial, "workspace-other", "دوم")
        archived = set_workspace_archived(other, "workspace-other")
        self.assertTrue(archived["workspaces"][1]["archived"])
        with self.assertRaisesRegex(ValueError, "active destination"):
            move_board_workspace(archived, other["boards"][0]["id"], "workspace-other")
        revived = set_workspace_archived(archived, "workspace-other", False)
        transferred = move_board_workspace(revived, revived["boards"][0]["id"], "workspace-other")
        with self.assertRaisesRegex(ValueError, "boards first"):
            delete_empty_workspace(transferred, "workspace-other")
        with self.assertRaisesRegex(ValueError, "last workspace"):
            delete_empty_workspace(initial, "workspace-legacy")
        deleted = delete_empty_workspace(revived, "workspace-other")
        self.assertEqual([w["id"] for w in deleted["workspaces"]], ["workspace-legacy"])
        self.assertTrue(validate_plus(deleted))

    def test_capacity_bad_reference_and_input_immutability(self):
        state = normalize_plus(enriched_state())
        full = deepcopy(state)
        full["workspaces"].extend({"id": f"workspace-{i}", "name": f"گروه {i}",
                                   "archived": False} for i in range(99))
        self.assertEqual(len(full["workspaces"]), 100)
        self.assertTrue(validate_plus(full))
        frozen = deepcopy(full)
        with self.assertRaises(ValueError):
            create_workspace(full, "workspace-overflow", "بیش از حد")
        self.assertEqual(full, frozen)
        with self.assertRaisesRegex(ValueError, "unknown workspace"):
            invalid = deepcopy(state)
            invalid["boards"][0]["workspaceId"] = "missing-workspace"
            validate_plus(invalid)
        with self.assertRaisesRegex(ValueError, "active destination"):
            move_board_workspace(state, state["boards"][0]["id"], "unknown-workspace")


class WorkspaceLANContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-workspace-contract-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {"APPDATA": str(self.root),
                                            "LOCALAPPDATA": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        mock_dir = patch.object(native_app, "datadir", return_value=self.root)
        mock_dir.start()
        self.addCleanup(mock_dir.stop)
        self.bridge = seed_legacy_example_state(native_app.Bridge())
        self.host = LanService(self.bridge, self.root / "users.json", bind="127.0.0.1", port=0)
        self.host.setup_owner("owner", "password-owner-contract")
        self.owner = self.host.authenticate("owner", "password-owner-contract")["token"]
        for username, role, grants in (("editor", "editor", ["p-sample"]),
                                       ("viewer", "viewer", ["p-sample"]),
                                       ("other", "editor", ["p-personal"])):
            self.host.upsert_user(self.owner, {"username": username,
                                               "role": role, "projects": grants,
                                               "password": f"password-{username}-contract"})
        self.editor = self.host.authenticate("editor", "password-editor-contract")["token"]
        self.viewer = self.host.authenticate("viewer", "password-viewer-contract")["token"]
        self.other = self.host.authenticate("other", "password-other-contract")["token"]

    def test_admin_can_create_and_move_workspace_but_editor_viewer_cannot_change_structure(self):
        admin = self.host.read_state(self.owner)
        created = create_workspace(admin["state"], "workspace-print", "چاپ")
        board = next(b for b in created["boards"] if b["projectId"] == "p-sample")
        moved = move_board_workspace(created, board["id"], "workspace-print")
        committed = self.host.write_state(self.owner, moved, admin["revision"])
        self.assertNotEqual(committed["revision"], admin["revision"])
        editor = self.host.read_state(self.editor)
        other = self.host.read_state(self.other)
        self.assertEqual({w["id"] for w in editor["state"]["workspaces"]}, {"workspace-print"})
        self.assertEqual({w["id"] for w in other["state"]["workspaces"]}, {"workspace-legacy"})
        self.assertEqual({p["id"] for p in editor["state"]["projects"]}, {"p-sample"})

        forged = rename_workspace(editor["state"], "workspace-print", "unauthorized")
        with self.assertRaises(PermissionError):
            self.host.write_state(self.editor, forged, editor["revision"])
        with self.assertRaises(PermissionError):
            self.host.write_state(self.viewer, editor["state"],
                                  self.host.read_state(self.viewer)["revision"])
        self.assertEqual(self.host.read_state(self.owner)["state"]["workspaces"][-1]["name"], "چاپ")

    def test_admin_workspace_stale_revision_cannot_overwrite_newer_change(self):
        first = self.host.read_state(self.owner)
        newer = create_workspace(first["state"], "workspace-now", "جدید")
        result = self.host.write_state(self.owner, newer, first["revision"])
        stale = create_workspace(first["state"], "workspace-stale", "قدیمی")
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            self.host.write_state(self.owner, stale, first["revision"])
        actual = self.host.read_state(self.owner)
        self.assertEqual(actual["revision"], result["revision"])
        self.assertEqual(actual["state"], result["state"])
        self.assertNotIn("workspace-stale", [w["id"] for w in actual["state"]["workspaces"]])

    def test_editor_card_order_cas_preserves_other_projects_and_finance(self):
        snapshot = self.host.read_state(self.owner)
        baseline = deepcopy(snapshot["state"])
        baseline["projects"][1]["price"] = 3_000_001
        baseline["tasks"][0]["cost"] = 7_000_007
        baseline["tasks"][0]["checklist"][0]["cost"] = 57_001
        self.host.write_state(self.owner, baseline, snapshot["revision"])
        editor = self.host.read_state(self.editor)
        before = self.host.read_state(self.owner)["state"]
        other_tasks = {card["id"]: deepcopy(card) for card in before["tasks"]
                       if card["projectId"] != "p-sample"}
        sample_card = next(t for t in editor["state"]["tasks"] if t["projectId"] == "p-sample")
        # An editor sees a financially redacted projection (zeroed costs).
        # After their ordering-only write the server must preserve the *true*
        # original values, not copy those redacted zeros into source records.
        privileged_card = next(t for t in before["tasks"] if t["id"] == sample_card["id"])
        original_cost = privileged_card["cost"]
        original_checklist = deepcopy(privileged_card["checklist"])
        reordered = deepcopy(editor["state"])
        matching = next(t for t in reordered["tasks"] if t["id"] == sample_card["id"])
        matching["cardOrder"] = 42
        result = self.host.write_state(self.editor, reordered, editor["revision"])
        self.assertNotEqual(result["revision"], editor["revision"])
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            self.host.write_state(self.editor, reordered, editor["revision"])
        after = self.host.read_state(self.owner)["state"]
        persisted = next(t for t in after["tasks"] if t["id"] == sample_card["id"])
        self.assertEqual(persisted["cardOrder"], 42)
        self.assertEqual((persisted["cost"], persisted["checklist"]),
                         (original_cost, original_checklist))
        self.assertEqual({card["id"]: card for card in after["tasks"]
                          if card["projectId"] != "p-sample"}, other_tasks)
        self.assertEqual(after["projects"], before["projects"])


if __name__ == "__main__":
    unittest.main()
