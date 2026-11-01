"""BD13 host contract: archived board lists retain cards, money and references.

Python validates and persists a board-local ``stage.archived`` flag. The
last-active-list rule is enforced in both the JavaScript helper and host:
a direct caller cannot bypass the UI to archive every stage of a board.

All Bridge and LAN fixtures live in a unique temporary root per test; this
module never starts a network listener or reads real APPDATA.

Run: py -3.12 -m unittest tests.test_list_archive_contract -v
"""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_storage import UnifiedAppStorage
from data_model import normalize_plus, validate_plus
from lan import LanService
import native_app
from tests.legacy_sample_fixture import seed_legacy_example_state


SAMPLE_PROJECT = "p-sample"
OTHER_PROJECT = "p-personal"
CARD_ON_ARCHIVED_LIST = "example-2"
OTHER_ARCHIVED_CARD = "example-3"
PROJECT_PRICE = 8_800_001
CARD_COST = 3_700_005
CHECKLIST_COST = 88_111


def sample_board(state):
    return next(board for board in state["boards"]
                if board.get("projectId") == SAMPLE_PROJECT)


def card(state, identifier):
    return next(task for task in state["tasks"] if task["id"] == identifier)


def project(state, identifier=SAMPLE_PROJECT):
    return next(item for item in state["projects"] if item["id"] == identifier)


def list_flag(state, list_id):
    return next(stage for stage in sample_board(state)["stages"]
                if stage["id"] == list_id)


def finance_contract():
    return {"type": "contract.set", "eventId": "bd13-finance-contract",
            "cardId": CARD_ON_ARCHIVED_LIST,
            "sale": {"customer": {"name": "BD13 contract", "reference": ""},
                     "lines": [{"id": "service", "description": "Print",
                                "quantity": 2, "unitPrice": 151_000}],
                     "discount": 0, "tax": 0, "advance": 0, "autoInvoice": True}}


class ListArchivePureContractTests(unittest.TestCase):
    def test_legacy_stage_without_archived_is_valid_and_normalization_is_immutable(self):
        source = native_app.initial_state()
        original = deepcopy(source)
        normalized = native_app.normalize_state(source)
        self.assertEqual(source, original)
        self.assertTrue(validate_plus(normalized))
        self.assertTrue(native_app.is_valid(normalized))
        self.assertTrue(all("archived" not in stage for stage in sample_board(normalized)["stages"]))
        self.assertEqual(native_app.normalize_state(normalized), normalized)

    def test_strict_optional_archived_flag_for_board_and_global_stages(self):
        baseline = native_app.normalize_state(native_app.initial_state())
        invalid_values = (None, 0, 1, "true", "false", [], {}, 1.0)
        for location in ("board", "global"):
            for value in invalid_values:
                for validator in (validate_plus, native_app.is_valid):
                    with self.subTest(location=location, value=repr(value),
                                      validator=validator.__name__):
                        changed = deepcopy(baseline)
                        stages = (sample_board(changed)["stages"] if location == "board"
                                  else changed["stages"])
                        stages[0]["archived"] = value
                        before = deepcopy(changed)
                        with self.assertRaises(ValueError):
                            validator(changed)
                        self.assertEqual(changed, before, "validator must not mutate rejected state")

    def test_python_rejects_every_stage_archived_and_retains_original_state(self):
        # The host now enforces the last-active-list invariant as well as JS,
        # preventing a direct writer from persisting an unusable board.
        state = native_app.normalize_state(native_app.initial_state())
        board = sample_board(state)
        original_ids = [s["id"] for s in board["stages"]]
        for stage in board["stages"]:
            stage["archived"] = True
        previous = deepcopy(state)
        with self.assertRaisesRegex(ValueError, "at least one active column"):
            validate_plus(state)
        with self.assertRaisesRegex(ValueError, "at least one active column"):
            native_app.is_valid(state)
        self.assertEqual(state, previous)
        self.assertEqual([s["id"] for s in sample_board(state)["stages"]], original_ids)
        for task in state["tasks"]:
            if task["boardId"] == board["id"]:
                self.assertIn(task["listId"], original_ids)


class ListArchiveFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-bd13-list-archive-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.assertTrue(self.root.is_dir())
        environment = patch.dict(os.environ, {"APPDATA": str(self.root),
                                             "LOCALAPPDATA": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        datadir = patch.object(native_app, "datadir", return_value=self.root)
        datadir.start()
        self.addCleanup(datadir.stop)
        self.bridge = seed_legacy_example_state(native_app.Bridge())
        self._assert_isolated(self.bridge)
        self.assertEqual(self.bridge.connection.get("mode"), "solo")

    def _assert_isolated(self, instance):
        for path in (instance.path, instance.unified_path,
                     instance.unified_marker, instance.finance_path,
                     instance.collab_path, instance.finance_outbox_path):
            self.assertEqual(path.resolve().parent, self.root)
        self.assertEqual(instance.backups_dir.resolve().parent, self.root)

    def _configure(self, *, sqlite=False):
        if sqlite:
            outcome = self.bridge.enableUnifiedStorage()
            self.assertEqual(outcome["mode"], "sqlite")
        state = self.bridge.getStateForUi()
        project(state)["price"] = PROJECT_PRICE
        project(state)["costEnabled"] = True
        item = card(state, CARD_ON_ARCHIVED_LIST)
        self.assertEqual(item["status"], "active")
        item.update({"cardOrder": 24, "cost": CARD_COST, "costEnabled": True,
                     "costCategory": "Print", "costDate": "2026-10-21",
                     "archived": False})
        self.assertTrue(item["checklist"])
        item["checklist"][0].update({"cost": CHECKLIST_COST,
                                      "costCategory": "Cut", "costDate": "2026-10-20"})
        another = card(state, OTHER_ARCHIVED_CARD)
        another.update({"archived": True, "cardOrder": 57, "cost": 203_000})
        self.assertEqual(sample_board(state)["id"], item["boardId"])
        self.assertEqual(item["listId"], item["status"])
        self.bridge.saveState(state)
        self.bridge.financeCommand(finance_contract())
        checked = self.bridge.getState()
        self.assertEqual(card(checked, CARD_ON_ARCHIVED_LIST)["cost"], CARD_COST)
        self.assertEqual(project(checked)["price"], PROJECT_PRICE)
        self.assertEqual(card(checked, CARD_ON_ARCHIVED_LIST)["checklist"][0]["cost"], CHECKLIST_COST)
        self.assertEqual(card(checked, OTHER_ARCHIVED_CARD)["archived"], True)
        self.assertEqual(len(self.bridge._load_finance()["contracts"]), 1)
        return checked

    def _set_list_archived(self, archived, list_id="active"):
        state = self.bridge.getStateForUi()
        list_flag(state, list_id)["archived"] = archived
        self.bridge.saveState(state)
        return state

    def _backend_snapshot(self, sqlite):
        return (UnifiedAppStorage(self.bridge.unified_path).load().sha256 if sqlite
                else self.bridge.path.read_bytes())

    def _check_roundtrip(self, *, sqlite):
        baseline = self._configure(sqlite=sqlite)
        before_tasks = deepcopy(baseline["tasks"])
        before_projects = deepcopy(baseline["projects"])
        before_global = deepcopy(baseline["stages"])
        before_other_board = deepcopy(next(b for b in baseline["boards"]
                                           if b["projectId"] == OTHER_PROJECT))
        before_finance = deepcopy(self.bridge._load_finance())
        before_stage_order = [s["id"] for s in sample_board(baseline)["stages"]]
        self.assertNotIn("archived", list_flag(baseline, "active"))

        self._set_list_archived(True)
        reopened = native_app.Bridge()
        self._assert_isolated(reopened)
        current = reopened.getState()
        self.assertIs(list_flag(current, "active")["archived"], True)
        self.assertEqual([s["id"] for s in sample_board(current)["stages"]], before_stage_order)
        self.assertEqual(current["tasks"], before_tasks,
                         "archiving list must retain every original card and financial field")
        self.assertEqual(current["projects"], before_projects)
        self.assertEqual(current["stages"], before_global)
        self.assertEqual(next(b for b in current["boards"]
                              if b["projectId"] == OTHER_PROJECT), before_other_board)
        self.assertEqual(reopened._load_finance(), before_finance)
        self.assertTrue(native_app.is_valid(current))

        # Restore is another admin/UI-level structural change with the same
        # persisted cards and finance, rather than deleting/recreating a list.
        state = reopened.getStateForUi()
        list_flag(state, "active")["archived"] = False
        result = reopened.saveState(state)
        self.assertIsInstance(result, dict)
        self.assertIn("localRevision", result)
        restored = native_app.Bridge()
        self._assert_isolated(restored)
        after = restored.getState()
        self.assertIs(list_flag(after, "active")["archived"], False)
        self.assertEqual([s["id"] for s in sample_board(after)["stages"]], before_stage_order)
        self.assertEqual(after["tasks"], before_tasks)
        self.assertEqual(after["projects"], before_projects)
        self.assertEqual(after["stages"], before_global)
        self.assertEqual(restored._load_finance(), before_finance)
        self.assertEqual(native_app.normalize_state(after), after)
        if sqlite:
            storage = UnifiedAppStorage(self.bridge.unified_path)
            self.assertTrue(storage.integrity_check())
            self.assertEqual(storage.load().bundle["tasks"], after)
        else:
            persisted = json.loads(self.bridge.path.read_text(encoding="utf8"))
            self.assertEqual(native_app.normalize_state(persisted), after)


class ListArchiveBridgeTests(ListArchiveFixture):
    def test_json_archive_and_restore_survive_restart_with_finance(self):
        self._check_roundtrip(sqlite=False)

    def test_sqlite_archive_and_restore_survive_restart_with_finance(self):
        self._check_roundtrip(sqlite=True)

    def test_bad_board_stage_archived_cannot_change_json_or_finance(self):
        self._assert_bad_archive_save(sqlite=False)

    def test_bad_board_stage_archived_cannot_change_sqlite_or_finance(self):
        self._assert_bad_archive_save(sqlite=True)

    def _assert_bad_archive_save(self, *, sqlite):
        self._configure(sqlite=sqlite)
        prior = self.bridge.getState()
        before_file = self._backend_snapshot(sqlite)
        before_finance = deepcopy(self.bridge._load_finance())
        invalid = self.bridge.getStateForUi()
        list_flag(invalid, "active")["archived"] = "true"
        with self.assertRaises(ValueError):
            self.bridge.saveState(invalid)
        self.assertEqual(self._backend_snapshot(sqlite), before_file)
        self.assertEqual(self.bridge.getState(), prior)
        self.assertEqual(self.bridge._load_finance(), before_finance)


class ListArchiveLANTests(ListArchiveFixture):
    def setUp(self):
        super().setUp()
        self._configure()
        self.host = LanService(self.bridge, self.root / "users.json",
                               bind="127.0.0.1", port=0)
        self.host.setup_owner("owner", "bd13-owner-test-password")
        self.owner = self.host.authenticate("owner", "bd13-owner-test-password")["token"]
        for user, role, projects in (("editor", "editor", [SAMPLE_PROJECT]),
                                     ("viewer", "viewer", [SAMPLE_PROJECT]),
                                     ("other", "editor", [OTHER_PROJECT])):
            self.host.upsert_user(self.owner, {"username": user,
                                               "password": f"bd13-{user}-test-password",
                                               "role": role, "projects": projects})
        self.editor = self.host.authenticate("editor", "bd13-editor-test-password")["token"]
        self.viewer = self.host.authenticate("viewer", "bd13-viewer-test-password")["token"]
        self.other = self.host.authenticate("other", "bd13-other-test-password")["token"]

    def test_admin_archive_restore_editor_view_and_no_card_finance_loss(self):
        initial = self.host.read_state(self.owner)
        initial_tasks = deepcopy(initial["state"]["tasks"])
        initial_projects = deepcopy(initial["state"]["projects"])
        initial_finance = deepcopy(self.bridge._load_finance())
        changed = deepcopy(initial["state"])
        list_flag(changed, "active")["archived"] = True
        accepted = self.host.write_state(self.owner, changed, initial["revision"])
        self.assertNotEqual(accepted["revision"], initial["revision"])
        self.assertTrue(list_flag(accepted["state"], "active")["archived"])
        self.assertEqual(accepted["state"]["tasks"], initial_tasks)
        self.assertEqual(accepted["state"]["projects"], initial_projects)
        self.assertEqual(self.bridge._load_finance(), initial_finance)

        editor_view = self.host.read_state(self.editor)
        self.assertEqual({b["projectId"] for b in editor_view["state"]["boards"]}, {SAMPLE_PROJECT})
        self.assertTrue(list_flag(editor_view["state"], "active")["archived"])
        self.assertEqual(project(editor_view["state"])["price"], 0)
        self.assertEqual(card(editor_view["state"], CARD_ON_ARCHIVED_LIST)["listId"], "active")
        other_view = self.host.read_state(self.other)
        self.assertTrue(all(b["projectId"] == OTHER_PROJECT
                            for b in other_view["state"]["boards"]))
        self.assertFalse(any(t["projectId"] == SAMPLE_PROJECT
                             for t in other_view["state"]["tasks"]))

        restored = deepcopy(accepted["state"])
        list_flag(restored, "active")["archived"] = False
        self.host.write_state(self.owner, restored, accepted["revision"])
        after = self.host.read_state(self.owner)["state"]
        self.assertIs(list_flag(after, "active")["archived"], False)
        self.assertEqual(after["tasks"], initial_tasks)
        self.assertEqual(after["projects"], initial_projects)
        self.assertEqual(self.bridge._load_finance(), initial_finance)
        reopened = native_app.Bridge()
        self._assert_isolated(reopened)
        self.assertIs(list_flag(reopened.getState(), "active")["archived"], False)

    def test_editor_viewer_cannot_archive_board_list_and_cas_is_enforced(self):
        baseline = self.host.read_state(self.editor)
        attack = deepcopy(baseline["state"])
        list_flag(attack, "active")["archived"] = True
        before = deepcopy(self.bridge.getState())
        financial_before = deepcopy(self.bridge._load_finance())
        with self.assertRaises(PermissionError):
            self.host.write_state(self.editor, attack, baseline["revision"])
        viewer_view = self.host.read_state(self.viewer)
        with self.assertRaises(PermissionError):
            self.host.write_state(self.viewer, attack, viewer_view["revision"])
        self.assertEqual(self.bridge.getState(), before)
        self.assertEqual(self.bridge._load_finance(), financial_before)

        admin_view = self.host.read_state(self.owner)
        admin_changed = deepcopy(admin_view["state"])
        list_flag(admin_changed, "active")["archived"] = True
        committed = self.host.write_state(self.owner, admin_changed, admin_view["revision"])
        self.assertNotEqual(committed["revision"], admin_view["revision"])
        stale = deepcopy(admin_view["state"])
        list_flag(stale, "review")["archived"] = True
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            self.host.write_state(self.owner, stale, admin_view["revision"])
        self.assertEqual(self.host.read_state(self.owner)["state"], committed["state"])

    def test_editor_can_edit_card_but_not_list_archive_structure(self):
        admin = self.host.read_state(self.owner)
        archived = deepcopy(admin["state"])
        list_flag(archived, "active")["archived"] = True
        self.host.write_state(self.owner, archived, admin["revision"])
        editor_view = self.host.read_state(self.editor)
        revised = deepcopy(editor_view["state"])
        card(revised, CARD_ON_ARCHIVED_LIST)["title"] = "Edited with archived list retained"
        before_finance = deepcopy(self.bridge._load_finance())
        accepted = self.host.write_state(self.editor, revised, editor_view["revision"])
        self.assertNotEqual(accepted["revision"], editor_view["revision"])
        current = self.host.read_state(self.owner)["state"]
        self.assertTrue(list_flag(current, "active")["archived"])
        self.assertEqual(card(current, CARD_ON_ARCHIVED_LIST)["listId"], "active")
        self.assertEqual(card(current, CARD_ON_ARCHIVED_LIST)["status"], "active")
        self.assertEqual(card(current, CARD_ON_ARCHIVED_LIST)["cardOrder"], 24)
        self.assertEqual(card(current, CARD_ON_ARCHIVED_LIST)["cost"], CARD_COST)
        self.assertEqual(card(current, CARD_ON_ARCHIVED_LIST)["checklist"][0]["cost"], CHECKLIST_COST)
        self.assertEqual(project(current)["price"], PROJECT_PRICE)
        self.assertTrue(card(current, OTHER_ARCHIVED_CARD)["archived"])
        self.assertEqual(self.bridge._load_finance(), before_finance)


if __name__ == "__main__":
    unittest.main()
