"""Synthetic tests of a host-only P2 batch preflight (no persistence)."""
import copy
import unittest

from gantt_shift_guard import GanttShiftError, prepare_gantt_shift


def card(key, start, end, deps=None, project="p"):
    return {"id": key, "projectId": project, "plannedStart": start,
            "plannedEnd": end, "dependencies": deps or []}


def fixture():
    return {"version": 1, "tasks": [
        card("a", "2026-11-01", "2026-11-03"),
        card("b", "2026-11-05", "2026-11-06", ["a"]),
        card("c", "2026-11-04", "2026-11-08", ["a"]),
        card("d", "2026-11-09", "2026-11-10", ["b", "c"]),
        card("e", "2026-11-19", "2026-11-20", ["a"]),
        card("other", "2026-11-01", "2026-11-02", project="q"),
    ]}


class GanttHostGuardTests(unittest.TestCase):
    def request(self, days, task_id="a"):
        return {"taskId": task_id, "days": days, "expectedRevision": "rev1"}

    def run_guard(self, state, request, *, role="editor", projects=None,
                  actual_revision="rev1"):
        return prepare_gantt_shift(state, request, role=role,
                                   projects=["p"] if projects is None else projects,
                                   actual_revision=actual_revision)

    def denies(self, code, state, request, **options):
        with self.assertRaises(GanttShiftError) as caught:
            self.run_guard(state, request, **options)
        self.assertEqual(caught.exception.code, code)

    def test_full_host_cascade_is_pure_and_preserves_slack(self):
        state = fixture()
        original = copy.deepcopy(state)
        output = self.run_guard(state, self.request(2))
        self.assertEqual(output["scope"], "full_host")
        self.assertEqual(output["changedCount"], 4)
        self.assertEqual(output["updates"], [
            {"id": "a", "plannedStart": "2026-11-03", "plannedEnd": "2026-11-05"},
            {"id": "b", "plannedStart": "2026-11-06", "plannedEnd": "2026-11-07"},
            {"id": "c", "plannedStart": "2026-11-06", "plannedEnd": "2026-11-10"},
            {"id": "d", "plannedStart": "2026-11-11", "plannedEnd": "2026-11-12"},
        ])
        self.assertEqual(state, original)
        self.assertEqual(output["nextState"]["tasks"][5], state["tasks"][5])
        self.assertEqual(self.run_guard(state, self.request(-1))["changedCount"], 1)

    def test_revision_role_grant_and_request_are_closed(self):
        state = fixture()
        self.denies("stale_revision", state, self.request(1),
                    actual_revision="rev2")
        self.denies("forbidden", state, self.request(1), role="viewer")
        self.denies("forbidden", state, self.request(1), projects=["q"])
        self.denies("forbidden", state, self.request(1, "other"))
        self.denies("invalid_request", state, {**self.request(1), "extra": True})
        self.denies("invalid_request", state, self.request(0))
        self.denies("invalid_request", state, self.request(3661))

    def test_blocks_hidden_archived_conflicting_and_cyclic(self):
        state = fixture()
        state["tasks"].append(card("hidden", "2026-11-10", "2026-11-11",
                                   ["a"], "q"))
        self.denies("outside_project", state, self.request(2))
        state = fixture()
        state["tasks"][1]["archived"] = True
        self.denies("outside_project", state, self.request(2))
        state = fixture()
        state["tasks"][1]["dependencies"] = ["hidden"]
        self.denies("outside_project", state, self.request(2))
        state = fixture()
        state["tasks"][1]["plannedStart"] = "2026-11-02"
        self.denies("existing_conflict", state, self.request(2))
        state = fixture()
        state["tasks"][0]["dependencies"] = ["d"]
        self.denies("dependency_cycle", state, self.request(2))
        state = fixture()
        state["tasks"][1]["plannedEnd"] = ""
        self.denies("missing_plan", state, self.request(2))
        state = fixture()
        state["tasks"][0]["plannedEnd"] = "bad"
        state["tasks"] = [state["tasks"][1]] + [
            task for task in state["tasks"] if task["id"] != "b"]
        self.denies("missing_plan", state, self.request(2))
        state = fixture()
        state["tasks"][5]["dependencies"] = "bad"
        self.denies("invalid_dependency", state, self.request(2))
        self.denies("earlier_than_predecessor", fixture(), self.request(-3, "b"))

    def test_year_boundaries(self):
        state = {"tasks": [card("early", "0001-01-01", "0001-01-02")]}
        result = self.run_guard(state, self.request(1, "early"))
        self.assertEqual(result["updates"][0]["plannedStart"], "0001-01-02")
        self.denies("date_range", state, self.request(-1, "early"))
        state = {"tasks": [card("late", "9999-12-30", "9999-12-31")]}
        self.denies("date_range", state, self.request(1, "late"))


if __name__ == "__main__":
    unittest.main()
