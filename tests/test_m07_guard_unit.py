"""M07 host-guard pure contract; synthetic event batches, no persistence."""
from copy import deepcopy
from datetime import date
import unittest

import automation_v1
import collab
from m07_host_guard import safe_card_events, safe_due_tick


AT = "2026-10-21T08:00:00+00:00"
ACCOUNTS = [
    {"username": "owner", "role": "admin", "projects": None},
    {"username": "editor", "role": "editor", "projects": ["p"]},
]
PROJECTS = [{"id": "p"}]
CARDS = [{"id": "c", "projectId": "p", "title": "test",
          "status": "active", "dueDate": "2026-10-23", "cost": 123_456}]
EVENT = {"type": "event.publish", "eventId": "e-1", "cardId": "c",
         "trigger": "card_moved", "data": {"toColumnId": "done"}}


def bundle():
    return {"automation": automation_v1.empty_state(),
            "collab": collab.empty_state(), "tasks": {"tasks": deepcopy(CARDS),
            "projects": deepcopy(PROJECTS)}, "finance": {"amount": 82_900}}


class GuardUnitTests(unittest.TestCase):
    def test_safe_card_events_bounded_atomic_candidate_without_source_mutation(self):
        source = bundle()
        original = deepcopy(source)
        out = safe_card_events(
            source, [deepcopy(EVENT)], actor="editor",
            accounts=ACCOUNTS, cards=CARDS, projects=PROJECTS, now=AT)
        self.assertEqual(out["added"], 1)
        self.assertEqual(out["processed"], 1)
        self.assertEqual(source, original)
        self.assertEqual(out["bundle"]["finance"], original["finance"])
        self.assertEqual(out["bundle"]["tasks"], original["tasks"])
        self.assertIn("e-1", out["bundle"]["automation"]["receipts"])

    def test_over_limit_rejected_before_any_event_or_finance_update(self):
        source = bundle()
        original = deepcopy(source)
        events = [{**deepcopy(EVENT), "eventId": f"event-{i:03d}"} for i in range(26)]
        with self.assertRaises(ValueError):
            safe_card_events(
                source, events, actor="editor", accounts=ACCOUNTS,
                cards=CARDS, projects=PROJECTS, now=AT)
        self.assertEqual(source, original)

    def test_due_tick_is_deterministic_and_idempotent(self):
        source = bundle()
        before = deepcopy(source)
        first = safe_due_tick(
            source, actor="editor", accounts=ACCOUNTS,
            cards=CARDS, projects=PROJECTS, now=AT, today=date(2026, 10, 21))
        self.assertEqual(source, before)
        self.assertEqual(first["added"], 1)
        again = safe_due_tick(
            first["bundle"], actor="editor", accounts=ACCOUNTS,
            cards=CARDS, projects=PROJECTS, now=AT, today=date(2026, 10, 21))
        self.assertEqual(again["added"], 0)
        self.assertEqual(again["applied"], 0)
        self.assertEqual(first["bundle"]["finance"], again["bundle"]["finance"])


if __name__ == "__main__":
    unittest.main()
