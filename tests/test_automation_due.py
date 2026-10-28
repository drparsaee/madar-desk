from datetime import date
import unittest

from automation_due import due_events
import collab


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

    def test_due_advanced_scalar_filters_respect_host_event_allowlist(self):
        card={"id":"card-1","listId":"waiting","status":"active",
              "priority":"high","completed":False,"labels":["blue","green"],
              "assignees":["person"],"dueDate":"2026-10-29"}
        event=due_events([card],today=date(2026,10,28))[0]
        self.assertEqual(event["data"],{"dueWithinDays":1,
                         "toColumnId":"waiting","priority":"high","completed":False})
        self.assertNotIn("labelId",event["data"])
        self.assertNotIn("assignee",event["data"])
        card["priority"]="x"*101
        card["completed"]="false"
        self.assertEqual(due_events([card],today=date(2026,10,28))[0]["data"],
                         {"dueWithinDays":1,"toColumnId":"waiting"})

    def test_due_advanced_event_matches_host_rule_without_altering_finance(self):
        card={"id":"card1","projectId":"project1","status":"active","listId":"waiting",
              "priority":"high","completed":False,"dueDate":"2026-10-29","cost":700000}
        accounts=[{"username":"admin","role":"admin","projects":None}]
        projects=[{"id":"project1","name":"QA"}]
        stamp="2026-10-28T09:00:00Z"
        state=collab.empty_state()
        state=collab.apply_command(state,{"type":"rule.upsert","eventId":"create1",
            "rule":{"id":"rule1","projectId":"project1","trigger":"due_soon",
                    "conditions":[{"field":"dueWithinDays","equals":1},
                                  {"field":"toColumnId","equals":"waiting"},
                                  {"field":"priority","equals":"high"}],
                    "actions":[{"type":"comment","text":"آزمون موعد پیشرفته"}],
                    "enabled":True}},actor="admin",accounts=accounts,cards=[card],projects=projects,
            now=stamp)["state"]
        event=due_events([card],today=date(2026,10,28))[0]
        applied=collab.apply_command(state,event,actor="admin",accounts=accounts,cards=[card],
                                     projects=projects,now=stamp)
        self.assertEqual(len(applied["state"]["comments"]),1)
        self.assertEqual(card["cost"],700000)
        self.assertFalse(collab.apply_command(applied["state"],event,actor="admin",
                    accounts=accounts,cards=[card],projects=projects,now=stamp)["changed"])


if __name__ == "__main__":
    unittest.main()
