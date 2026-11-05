"""Offline migration and referential-integrity tests for Madar's v0.3 model."""

import copy
import json
import unittest

from data_model import _digest, normalize_plus, validate_plus


def legacy():
    return {
        "version": 1,
        "projects": [
            {"id": "p1", "name": "کار", "color": "#123456", "price": 90000,
             "costEnabled": True, "fileLinks": [{"id": "f1", "name": "Original", "path": r"\\PC\Share\file.pdf"}]},
            {"id": "p2", "name": "شخصی", "price": 0},
        ],
        "tasks": [
            {"id": "t1", "projectId": "p1", "title": "اول", "description": "همه چیز",
             "status": "active", "priority": "high", "cost": 350,
             "assignees": ["editor"], "labels": ["مهم", "کار", "مهم"],
             "checklist": [{"id": "step1", "text": "تأیید", "done": True, "cost": 125}],
             "reports": [{"id": "r1", "agent": "Test", "summary": "Finished"}],
             "fileLinks": [], "extension": {"keep": ["تاریخ", 17]}},
            {"id": "t2", "projectId": "p2", "title": "دوم", "status": "done",
             "priority": "low", "labels": [], "checklist": [], "reports": []},
        ],
        "stages": [{"id": "active", "label": "در حال انجام", "color": "#ccaacc"},
                   {"id": "done", "label": "پایان", "color": "#abcabc"}],
        "settings": {"theme": "dark", "googleClientId": "safe-example"},
        "extension": {"special": {"nested": [0, 1, 2]}},
    }


class MigrationTests(unittest.TestCase):
    def test_card_completion_boolean_is_persistent_and_independent_of_financial_status(self):
        source = legacy()
        original = copy.deepcopy(source["tasks"][0])
        source["tasks"][0]["completed"] = True
        normalized = normalize_plus(source)
        self.assertTrue(validate_plus(normalized))
        card = normalized["tasks"][0]
        self.assertIs(card["completed"], True)
        for field in ("status", "cost", "checklist", "reports", "projectId"):
            self.assertEqual(card[field], original[field])
        card["completed"] = False
        self.assertTrue(validate_plus(normalized))
        self.assertEqual(card["status"], "active")
        for invalid in (1, "true", None):
            card["completed"] = invalid
            with self.assertRaisesRegex(ValueError, "completed"):
                validate_plus(normalized)

    def test_order_customer_label_is_bounded_and_remains_nonfinancial(self):
        state = normalize_plus(legacy())
        task = state["tasks"][0]
        task["orderCustomerName"] = "آقای فلان"
        task["salePartyId"] = "customer.account"
        task["saleQuantity"] = 100
        task["saleUnitPrice"] = 20000
        task["saleCurrency"] = "TOMAN"
        self.assertTrue(validate_plus(state))
        task["orderCustomerName"] = "x" * 301
        with self.assertRaisesRegex(ValueError, "orderCustomerName"):
            validate_plus(state)
        task["orderCustomerName"] = 123
        with self.assertRaisesRegex(ValueError, "orderCustomerName"):
            validate_plus(state)

    def test_lossless_legacy_migration_keeps_original_unchanged(self):
        original = legacy()
        snapshot = copy.deepcopy(original)
        migrated = normalize_plus(original)
        self.assertEqual(original, snapshot)
        self.assertIsNot(migrated, original)
        self.assertEqual(migrated["version"], 1)
        for key in ("projects", "stages", "settings", "extension"):
            self.assertEqual(migrated[key], snapshot[key])
        for old, new in zip(snapshot["tasks"], migrated["tasks"]):
            for key, value in old.items():
                self.assertEqual(new[key], value, key)
        self.assertEqual(migrated["tasks"][0]["checklists"][0]["items"],
                         original["tasks"][0]["checklist"])
        self.assertEqual(migrated["tasks"][0]["checklists"][0]["items"][0]["cost"], 125)
        self.assertEqual(migrated["tasks"][0]["assignees"], ["editor"])
        self.assertTrue(validate_plus(migrated))

    def test_two_legacy_projects_become_distinct_boards_with_local_columns(self):
        state = normalize_plus(legacy())
        self.assertEqual(len(state["workspaces"]), 1)
        self.assertEqual(len(state["boards"]), 2)
        boards = {b["projectId"]: b for b in state["boards"]}
        self.assertEqual(boards["p1"]["name"], "کار")
        self.assertEqual(boards["p2"]["name"], "شخصی")
        self.assertEqual(boards["p1"]["stages"], state["stages"])
        self.assertIsNot(boards["p1"]["stages"], state["stages"])
        self.assertIsNot(boards["p1"]["stages"], boards["p2"]["stages"])
        self.assertEqual(state["tasks"][0]["boardId"], boards["p1"]["id"])
        self.assertEqual(state["tasks"][0]["listId"], "active")

    def test_legacy_text_labels_gain_stable_definitions_and_references(self):
        state = normalize_plus(legacy())
        board = next(b for b in state["boards"] if b["projectId"] == "p1")
        ids = {d["name"]: d["id"] for d in board["labelDefinitions"]}
        self.assertEqual(set(ids), {"کار", "مهم"})
        self.assertEqual(state["tasks"][0]["labels"], ["مهم", "کار", "مهم"])
        self.assertEqual(state["tasks"][0]["labelIds"], [ids["مهم"], ids["کار"]])

    def test_migration_is_idempotent_and_json_roundtrip_safe(self):
        first = normalize_plus(legacy())
        second = normalize_plus(first)
        self.assertEqual(first, second)
        self.assertEqual(first, normalize_plus(json.loads(json.dumps(first))))

    def test_missing_optional_legacy_stages_and_settings_supported(self):
        state = legacy()
        state.pop("settings")
        state.pop("stages")
        for task in state["tasks"]:
            task["status"] = "active"
        migrated = normalize_plus(state)
        self.assertEqual(migrated["settings"], {})
        self.assertEqual(len(migrated["stages"]), 5)
        self.assertTrue(validate_plus(migrated))

    def test_board_specific_columns_and_archives_are_retained(self):
        state = normalize_plus(legacy())
        board = state["boards"][0]
        board["stages"].append({"id": "qa", "label": "کنترل کیفیت", "color": "#f59e0b"})
        board["archived"] = True
        state["tasks"][0]["listId"] = "qa"
        state["tasks"][0]["archived"] = True
        self.assertTrue(validate_plus(state))
        self.assertEqual(normalize_plus(state), state)
        self.assertEqual(state["tasks"][0]["status"], "active")

    def test_custom_fields_templates_and_second_workspace_survive(self):
        state = normalize_plus(legacy())
        board = state["boards"][0]
        state["workspaces"].append({"id": "ws-team", "name": "گروه", "archived": False})
        board["workspaceId"] = "ws-team"
        board["labelDefinitions"][0]["color"] = "#ffeecc"
        board["customFields"] = [
            {"id": "budget", "name": "هزینه پیش‌بینی", "type": "number"},
            {"id": "approved", "name": "تأیید", "type": "checkbox"},
            {"id": "delivery", "name": "تاریخ تحویل", "type": "date"},
            {"id": "color", "name": "رنگ", "type": "select",
             "options": [{"id": "blue", "label": "آبی"}]},
        ]
        state["tasks"][0]["customFieldValues"] = {
            "budget": 40.5, "approved": False, "delivery": "2026-10-20", "color": "blue"}
        state["tasks"][0]["checklists"].append({
            "id": "qa-list", "name": "کنترل کیفیت", "items": [
                {"id": "qa1", "text": "چاپ", "done": False}]})
        state["templates"] = [{
            "id": "template-1", "boardId": board["id"], "name": "الگوی چاپ",
            "title": "تیراژ آزمایشی", "labelIds": [board["labelDefinitions"][0]["id"]],
            "customFieldValues": {"approved": False}, "checklists": [
                {"id": "template-check", "name": "مراحل", "items": [
                    {"id": "check1", "text": "تست", "done": False}]}]},
        ]
        self.assertTrue(validate_plus(state))
        self.assertEqual(normalize_plus(state), state)

    def test_existing_board_for_project_is_reused(self):
        state = normalize_plus(legacy())
        state["boards"][0]["name"] = "اسم سفارشی"
        state["boards"][0]["stages"][0]["label"] = "در دست اقدام"
        self.assertEqual(normalize_plus(state), state)
        self.assertEqual(len(state["boards"]), 2)

    def test_checklist_items_without_native_ids_are_migrated_without_overwrite(self):
        state = legacy()
        state["tasks"][0]["checklist"] = [
            {"text": "بدون شناسه", "done": False, "cost": 2},
            {"id": "duplicate", "text": "گام اول", "done": True},
            {"id": "duplicate", "text": "گام دوم", "done": False},
        ]
        result = normalize_plus(state)
        self.assertEqual(result["tasks"][0]["checklist"], state["tasks"][0]["checklist"])
        group = result["tasks"][0]["checklists"][0]
        ids = [item["id"] for item in group["items"]]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(ids[1], "duplicate")
        self.assertEqual(result, normalize_plus(result))

    def test_generated_id_must_not_collide_with_later_valid_legacy_id(self):
        state = legacy()
        future_id = _digest("step-legacy-", "t1", 0)
        state["tasks"][0]["checklist"] = [
            {"text": "old without id", "done": False},
            {"id": future_id, "text": "already owns id", "done": True},
            {"id": future_id, "text": "duplicate", "done": False},
        ]
        before = copy.deepcopy(state)
        migrated = normalize_plus(state)
        items = migrated["tasks"][0]["checklists"][0]["items"]
        self.assertEqual(len(set(i["id"] for i in items)), 3)
        self.assertEqual(items[1]["id"], future_id)
        self.assertEqual(migrated["tasks"][0]["checklist"], before["tasks"][0]["checklist"])
        self.assertEqual(migrated, normalize_plus(migrated))

    def test_partial_legacy_named_group_missing_item_ids_is_recovered(self):
        state = normalize_plus(legacy())
        original = copy.deepcopy(state)
        group = state["tasks"][0]["checklists"][0]
        group["items"] = [
            {"text": "no id", "done": False, "cost": 3},
            {"id": "duplicate", "text": "keep first", "done": False},
            {"id": "duplicate", "text": "second", "done": True},
        ]
        result = normalize_plus(state)
        items = result["tasks"][0]["checklists"][0]["items"]
        self.assertEqual(len(set(i["id"] for i in items)), 3)
        self.assertEqual(items[1]["id"], "duplicate")
        self.assertEqual(result["tasks"][0]["checklist"], original["tasks"][0]["checklist"])
        self.assertEqual(normalize_plus(result), result)

    def test_duplicate_and_missing_legacy_named_group_ids_recovered(self):
        state = normalize_plus(legacy())
        state["tasks"][0]["checklists"] = [
            {"id": "checklist-legacy", "name": "چک‌لیست", "items": []},
            {"id": "checklist-legacy", "name": "چک‌لیست", "items": []},
            {"name": "چک‌لیست", "items": []},
        ]
        result = normalize_plus(state)
        groups = result["tasks"][0]["checklists"]
        self.assertEqual(len(set(g["id"] for g in groups)), len(groups))
        self.assertEqual(groups[0]["id"], "checklist-legacy")
        self.assertEqual(normalize_plus(result), result)

    def test_empty_or_invalid_generated_checklist_group_ids_repaired(self):
        state = normalize_plus(legacy())
        state["tasks"][0]["checklists"] = [
            {"id": "", "name": "چک‌لیست", "items": []},
            {"id": 4, "name": "چک‌لیست", "items": []},
        ]
        repaired = normalize_plus(state)
        groups = repaired["tasks"][0]["checklists"]
        self.assertTrue(all(isinstance(g["id"], str) and g["id"] for g in groups))
        self.assertEqual(len({g["id"] for g in groups}), 2)
        self.assertEqual(normalize_plus(repaired), repaired)

    def test_empty_legacy_ids_that_native_app_accepts_do_not_disappear(self):
        state = legacy()
        state["projects"][0]["id"] = ""
        state["tasks"][0]["projectId"] = ""
        state["tasks"][0]["id"] = ""
        migrated = normalize_plus(state)
        self.assertEqual(migrated["tasks"][0]["id"], "")
        self.assertEqual(migrated["tasks"][0]["projectId"], "")
        self.assertTrue(migrated["tasks"][0]["boardId"])
        self.assertEqual(normalize_plus(migrated), migrated)

    def test_future_board_without_project_link_can_hold_legacy_task(self):
        state = normalize_plus(legacy())
        state["boards"].append({
            "id": "board-independent", "workspaceId": state["workspaces"][0]["id"],
            "name": "برد مستقل", "archived": False,
            "stages": [{"id": "ready", "label": "آماده"}],
            "labelDefinitions": [], "customFields": [],
        })
        state["tasks"][0].update(boardId="board-independent", listId="ready",
                                 labelIds=[], customFieldValues={})
        self.assertTrue(validate_plus(state))
        normalized = normalize_plus(state)
        self.assertEqual(normalize_plus(normalized), normalized)
        self.assertEqual(normalized["tasks"][0]["status"], "active")
        self.assertEqual(normalized["tasks"][0]["listId"], "ready")
        self.assertEqual(normalized["tasks"][0]["labels"], ["مهم", "کار", "مهم"])


class ValidationTests(unittest.TestCase):
    def test_invalid_references_or_duplicate_identifiers_rejected(self):
        cases = [
            ("missing project", lambda s: s["tasks"][0].update(projectId="unknown"), "projectId"),
            ("duplicate project", lambda s: s["projects"].append(copy.deepcopy(s["projects"][0])), "duplicate"),
            ("unknown workspace", lambda s: s["boards"][0].update(workspaceId="missing"), "workspaceId"),
            ("bad board", lambda s: s["tasks"][0].update(boardId="missing"), "boardId"),
            ("structured board reference", lambda s: s["tasks"][0].update(boardId={"x": 1}), "boardId"),
            ("bad board list", lambda s: s["tasks"][0].update(listId="missing"), "listId"),
            ("cross-linked project", lambda s: s["tasks"][0].update(projectId="p2"), "projectId"),
            ("missing label", lambda s: s["tasks"][0].update(labelIds=["missing"]), "labelIds"),
            ("duplicate list", lambda s: s["boards"][0]["stages"].append(
                copy.deepcopy(s["boards"][0]["stages"][0])), "duplicate"),
            ("bad archive flag", lambda s: s["tasks"][0].update(archived="false"), "archived"),
            ("invalid template", lambda s: s["templates"].append(
                {"id": "tmpl", "boardId": "missing", "name": "x"}), "boardId"),
        ]
        for name, change, message in cases:
            with self.subTest(name=name):
                state = normalize_plus(legacy())
                change(state)
                with self.assertRaisesRegex(ValueError, message):
                    validate_plus(state)

    def test_invalid_custom_field_values_and_options_rejected(self):
        state = normalize_plus(legacy())
        state["boards"][0]["customFields"] = [
            {"id": "n", "name": "عدد", "type": "number"},
            {"id": "d", "name": "موعد", "type": "date"},
            {"id": "o", "name": "وضعیت", "type": "select",
             "options": [{"id": "yes", "label": "بله"}]},
        ]
        for value, field in ((True, "n"), (float("inf"), "n"),
                             ("2026-02-30", "d"), ("missing", "o"),
                             ({"unexpected": 1}, "o")):
            with self.subTest(value=value, field=field):
                case = copy.deepcopy(state)
                case["tasks"][0]["customFieldValues"][field] = value
                with self.assertRaises(ValueError):
                    validate_plus(case)

    def test_invalid_named_checklists_and_malformed_json_rejected(self):
        state = normalize_plus(legacy())
        state["tasks"][0]["checklists"][0]["items"][0]["done"] = "true"
        with self.assertRaisesRegex(ValueError, "done"):
            validate_plus(state)
        for value in ({"unexpected"}, float("nan")):
            with self.subTest(value=str(value)):
                bad = legacy()
                bad["extension"] = value
                with self.assertRaises(ValueError):
                    normalize_plus(bad)

    def test_named_expenses_validate_financial_identity_across_legacy_and_named_groups(self):
        state = normalize_plus(legacy())
        task = state["tasks"][0]
        expense = {"id": "named.source.1", "description": "Print", "partyId": "vendor.1",
                   "quantity": 2, "unitPrice": 1500, "currency": "RIAL"}
        task["checklists"].append({"id": "named", "name": "Named", "items": [
            {"id": "named-step", "text": "Work", "done": False,
             "cost": 0, "expenseItems": [copy.deepcopy(expense)]}]})
        self.assertTrue(validate_plus(state))
        malformed = copy.deepcopy(state)
        malformed["tasks"][0]["checklists"][-1]["items"][0]["expenseItems"][0]["unitPrice"] = "1500"
        with self.assertRaisesRegex(ValueError, "unitPrice"):
            validate_plus(malformed)
        duplicated = copy.deepcopy(state)
        duplicated["tasks"][0]["checklist"][0]["expenseItems"] = [copy.deepcopy(expense)]
        # The compatibility mirror may hold the same legacy source; that alone is not a duplicate.
        duplicated["tasks"][0]["checklists"][0]["items"][0]["expenseItems"] = [copy.deepcopy(expense)]
        with self.assertRaisesRegex(ValueError, "duplicate id"):
            validate_plus(duplicated)
        duplicated["tasks"][0]["checklists"][-1]["items"][0]["expenseItems"] = []
        self.assertTrue(validate_plus(duplicated))

    def test_validation_has_no_side_effects(self):
        state = normalize_plus(legacy())
        reference = copy.deepcopy(state)
        self.assertTrue(validate_plus(state))
        self.assertEqual(reference, state)

    def test_invalid_legacy_input_raises_without_mutating_source(self):
        original = legacy()
        original["tasks"][0]["status"] = "unknown"
        before = copy.deepcopy(original)
        with self.assertRaisesRegex(ValueError, "status"):
            normalize_plus(original)
        self.assertEqual(original, before)


if __name__ == "__main__":
    unittest.main()
