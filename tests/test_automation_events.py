import copy
import unittest
from automation_events import card_change_events


class EventDiffTests(unittest.TestCase):
    def test_status_only_legacy_move_still_publishes_event(self):
        before = {"tasks": [{"id": "one", "projectId": "project", "status": "active",
                             "listId": "active", "labelIds": [], "customFieldValues": {},
                             "checklists": []}]}
        after = copy.deepcopy(before)
        after["tasks"][0]["status"] = "done"
        events = card_change_events(before, after)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["trigger"], "card_moved")
        self.assertEqual(events[0]["data"], {"fromColumnId": "active", "toColumnId": "done"})

    def test_create_move_label_field_and_checklist(self):
        old = {"tasks": [{"id":"card1","projectId":"p1","status":"active","listId":"active",
                           "labelIds":["a"],"customFieldValues":{"f":1},
                           "checklists":[{"id":"todo","items":[{"id":"s1","done":False}]}]}]}
        new = copy.deepcopy(old)
        card = new["tasks"][0]
        card["status"] = card["listId"] = "done"
        card["labelIds"] = ["a", "b"]
        card["customFieldValues"]["f"] = 2
        card["checklists"][0]["items"][0]["done"] = True
        events = card_change_events(old, new)
        self.assertEqual({e["trigger"] for e in events},
                         {"card_moved","label_changed","custom_field_changed","checklist_completed"})
        self.assertEqual(card_change_events(old,new),events)
        self.assertEqual(card_change_events(new,new),[])
        self.assertEqual(card_change_events({"tasks":[]},new)[0]["trigger"],"card_created")


if __name__ == "__main__":
    unittest.main()
