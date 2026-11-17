"""M06: DAG persistence boundaries and server-side denial tests."""
from copy import deepcopy
import unittest

import native_app
from card_dependency_validation import validate_task_dependencies


def cards():
    return [{"id":"one", "projectId":"p", "status":"planned"},
            {"id":"two", "projectId":"p", "status":"active", "dependencies":["one"]},
            {"id":"other", "projectId":"q", "status":"planned"}]


class CardDependencyValidation(unittest.TestCase):
    def test_planning_range_is_checked_without_changing_due_date(self):
        state = native_app.normalize_state(native_app.initial_state())
        task = state["tasks"][0]
        task["plannedStart"] = "2026-11-08"
        task["plannedEnd"] = "2026-11-12"
        self.assertTrue(native_app.is_valid(state))
        task["plannedEnd"] = "2026-11-07"
        with self.assertRaises(ValueError):
            native_app.is_valid(state)
        task["plannedEnd"] = "2026-02-30"
        with self.assertRaises(ValueError):
            native_app.is_valid(state)

    def test_no_dependency_legacy_is_accepted(self):
        self.assertTrue(validate_task_dependencies(cards()[:1]))

    def test_valid_dependency_graph_is_accepted_without_edit(self):
        source = cards()
        original = deepcopy(source)
        self.assertTrue(validate_task_dependencies(source))
        self.assertEqual(original, source)

    def test_missing_predecessor_rejected(self):
        state = cards()
        state[1]["dependencies"]=["missing"]
        with self.assertRaises(ValueError): validate_task_dependencies(state)

    def test_cross_project_dependency_rejected(self):
        state = cards()
        state[1]["dependencies"]=["other"]
        with self.assertRaises(ValueError): validate_task_dependencies(state)

    def test_self_and_duplicate_rejected(self):
        for illegal in (["two"],["one","one"],[None],[""]):
            state=cards()
            state[1]["dependencies"]=illegal
            with self.subTest(illegal=illegal), self.assertRaises(ValueError):
                validate_task_dependencies(state)

    def test_cycle_rejected(self):
        state=cards()
        state[0]["dependencies"]=["two"]
        with self.assertRaisesRegex(ValueError,"CONFLICT"):
            validate_task_dependencies(state)

    def test_deleted_target_and_deleted_source_rejected(self):
        for item in (0,1):
            state=cards()
            state[item]["deleted"]=True
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_task_dependencies(state)

    def test_bounded_dependency_list(self):
        state=cards()
        state[1]["dependencies"]=["one"]*129
        with self.assertRaises(ValueError): validate_task_dependencies(state)

    def test_host_is_valid_exercises_dependency_gate(self):
        state=native_app.normalize_state(native_app.initial_state())
        one,two=state["tasks"][:2]
        two["dependencies"]=[one["id"]]
        self.assertTrue(native_app.is_valid(state))
        one["dependencies"]=[two["id"]]
        with self.assertRaisesRegex(ValueError,"CONFLICT"):
            native_app.is_valid(state)


if __name__ == '__main__': unittest.main()
