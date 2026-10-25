from datetime import date
import unittest

from automation_due import due_events


class SchedulerTests(unittest.TestCase):
    def test_today_nearby_archived_completed_and_invalid_dates(self):
        cards = [{"id": "today", "dueDate": "2026-10-20", "status": "active"},
                 {"id": "future", "dueDate": "2026-10-22", "status": "active"},
                 {"id": "outside", "dueDate": "2026-11-20", "status": "active"},
                 {"id": "late", "dueDate": "2026-10-19", "status": "active"},
                 {"id": "done", "dueDate": "2026-10-20", "status": "done"},
                 {"id": "archived", "dueDate": "2026-10-20", "archived": True},
                 {"id": "bad", "dueDate": "2026-02-30"}]
        events = due_events(cards, today=date(2026, 10, 20))
        self.assertEqual([x["cardId"] for x in events], ["today", "future"])
        self.assertEqual([x["data"]["dueWithinDays"] for x in events], [0, 2])
        self.assertEqual(due_events(cards, today=date(2026, 10, 20)), events)
        self.assertNotEqual(due_events(cards, today=date(2026, 10, 21))[0]["eventId"], events[1]["eventId"])

    def test_invalid_window_and_duplicate(self):
        with self.assertRaises(ValueError):
            due_events([], today="2026-10-20")
        with self.assertRaises(ValueError):
            due_events([], today=date.today(), horizon_days=365)
        with self.assertRaises(ValueError):
            due_events([{"id": "one"}, {"id": "one"}], today=date.today())


if __name__ == "__main__":
    unittest.main()
