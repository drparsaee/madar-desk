"""Offline contract tests for Madar's collaboration domain functions."""

from copy import deepcopy
import json
import unittest

from collab import (apply_command, empty_state, extract_mentions, list_activity,
                    list_comments, list_notifications, validate_state)


NOW = "2026-10-20T15:30:00Z"
LATER = "2026-10-20T15:35:00Z"


class CollaborationTests(unittest.TestCase):
    def test_project_conversation_replies_idempotency_and_acl(self):
        first = self.operate("alice", "project.comment.add", projectId="p1",
                             text="سلام @bob", replyToId="",
                             event_id="project-message-1")
        parent = first["result"]["commentId"]
        duplicate = self.operate("alice", "project.comment.add", projectId="p1",
                                 text="سلام @bob", replyToId="",
                                 event_id="project-message-1")
        self.assertEqual(first["result"], duplicate["result"])
        self.assertEqual(len(self.state["projectComments"]), 1)
        self.assertEqual(self.notices("bob")[0]["cardId"], None)
        child = self.operate("dave", "project.comment.add", projectId="p1",
                             text="پاسخ", replyToId=parent)
        self.assertEqual(self.state["projectComments"][1]["replyToId"], parent)
        self.assertTrue(child["result"]["commentId"])
        with self.assertRaises(PermissionError):
            self.operate("carol", "project.comment.add",
                         projectId="p1", text="not mine", replyToId="")
        with self.assertRaises(PermissionError):
            self.operate("bob", "project.comment.add",
                         projectId="p1", text="viewer", replyToId="")
        from collab import list_project_comments
        self.assertEqual(len(list_project_comments(
            self.state, "p1", actor="bob", accounts=self.accounts,
            cards=self.cards, projects=self.projects)), 2)
        with self.assertRaises(PermissionError):
            list_project_comments(self.state, "p1", actor="carol",
                                  accounts=self.accounts, cards=self.cards, projects=self.projects)
        with self.assertRaises(PermissionError):
            self.operate("dave", "project.comment.edit", commentId=parent, text="steal")
        self.operate("alice", "project.comment.edit", commentId=parent, text="ویرایش")
        self.operate("admin", "project.comment.delete", commentId=parent)
        self.assertEqual(self.state["projectComments"][0]["text"], "")

    def test_card_reply_requires_a_parent_in_the_same_card(self):
        parent = self.operate("alice", "comment.add", cardId="c1", text="first")["result"]["commentId"]
        reply = self.operate("dave", "comment.reply", cardId="c1",
                             replyToId=parent, text="second")
        self.assertEqual(self.comments()[1]["replyToId"], parent)
        self.assertTrue(reply["result"]["commentId"])
        with self.assertRaises(ValueError):
            self.operate("admin", "comment.reply", cardId="c2",
                         replyToId=parent, text="wrong thread")
    def setUp(self):
        self.state = empty_state()
        self.projects = [{"id": "p1"}, {"id": "p2"}]
        self.cards = [{"id": "c1", "projectId": "p1"}, {"id": "c2", "projectId": "p2"}]
        self.accounts = {
            "admin": {"username": "admin", "role": "admin", "projects": None},
            "alice": {"username": "alice", "role": "editor", "projects": ["p1"]},
            "bob": {"username": "bob", "role": "viewer", "projects": ["p1"]},
            "carol": {"username": "carol", "role": "editor", "projects": ["p2"]},
            "dave": {"username": "dave", "role": "editor", "projects": ["p1"]},
        }
        self.counter = 0

    def operate(self, actor, kind, *, time=NOW, event_id=None, **kwargs):
        self.counter += 1
        command = {"type": kind, "eventId": event_id or f"event-{self.counter}", **kwargs}
        result = apply_command(self.state, command, actor=actor, accounts=self.accounts,
                               cards=self.cards, projects=self.projects, now=time)
        self.state = result["state"]
        return result

    def comments(self, actor="alice", card="c1"):
        return list_comments(self.state, card, actor=actor, accounts=self.accounts,
                             cards=self.cards, projects=self.projects)

    def notices(self, actor="bob", unread=False):
        return list_notifications(self.state, actor=actor, accounts=self.accounts,
                                  cards=self.cards, projects=self.projects,
                                  unread_only=unread)

    def activity(self, actor="alice"):
        return list_activity(self.state, actor=actor, accounts=self.accounts,
                             cards=self.cards, projects=self.projects)

    def test_new_state_is_valid_and_json_serializable(self):
        self.assertTrue(validate_state(self.state))
        self.assertEqual(json.loads(json.dumps(self.state)), self.state)

    def test_mentions_are_deduplicated_and_email_is_not_a_mention(self):
        self.assertEqual(extract_mentions("hello @bob @bob and @dave, email a@bob.com and @carol"),
                         ["bob", "dave", "carol"])

    def test_comment_mention_scopes_and_server_supplied_author(self):
        source = deepcopy(self.state)
        output = self.operate("alice", "comment.add", cardId="c1", text="سلام @bob و @carol و @dave")
        self.assertEqual(self.state["comments"][0]["mentions"], ["bob", "dave"])
        self.assertEqual(self.state["comments"][0]["author"], "alice")
        self.assertEqual(len(output["result"]["notificationIds"]), 2)
        self.assertEqual(len(self.notices("bob")), 1)
        self.assertEqual(len(self.notices("dave")), 1)
        self.assertFalse(self.notices("carol"))
        self.assertEqual(source, empty_state())

    def test_watchers_receive_single_comment_notifications_and_self_excluded(self):
        self.operate("bob", "watch.set", cardId="c1", enabled=True)
        self.operate("alice", "watch.set", cardId="c1", enabled=True)
        self.operate("alice", "comment.add", cardId="c1", text="hi @bob")
        self.assertEqual(len(self.notices("bob")), 1)
        self.assertEqual(self.notices("bob")[0]["kind"], "mention")
        self.assertFalse(self.notices("alice"))
        self.operate("bob", "watch.set", cardId="c1", enabled=False)
        self.operate("alice", "comment.add", cardId="c1", text="a second reply")
        self.assertEqual(len(self.notices("bob")), 1)
        self.assertEqual(self.state["watchers"]["c1"], ["alice"])

    def test_viewer_may_watch_and_read_but_not_comment_or_emit_event(self):
        self.operate("bob", "watch.set", cardId="c1", enabled=True)
        self.assertEqual(self.comments("bob"), [])
        with self.assertRaises(PermissionError):
            self.operate("bob", "comment.add", cardId="c1", text="unauthorized")
        with self.assertRaises(PermissionError):
            self.operate("bob", "event.publish", cardId="c1", trigger="card_moved", data={})

    def test_project_boundary_applies_to_read_write_watch_event(self):
        self.operate("admin", "comment.add", cardId="c2", text="private")
        with self.assertRaises(PermissionError):
            self.comments("alice", "c2")
        with self.assertRaises(PermissionError):
            self.operate("alice", "comment.add", cardId="c2", text="illegal")
        with self.assertRaises(PermissionError):
            self.operate("alice", "watch.set", cardId="c2", enabled=True)
        self.assertFalse(self.activity("bob"))
        self.assertEqual(len(self.activity("admin")), 1)

    def test_comment_edit_only_author_admin_can_delete_tombstone(self):
        cid = self.operate("alice", "comment.add", cardId="c1", text="first")["result"]["commentId"]
        with self.assertRaises(PermissionError):
            self.operate("dave", "comment.edit", commentId=cid, text="hijack")
        with self.assertRaises(PermissionError):
            self.operate("dave", "comment.delete", commentId=cid)
        self.operate("alice", "comment.edit", commentId=cid, text="updated @bob", time=LATER)
        self.assertEqual(len(self.notices("bob")), 1)
        self.operate("admin", "comment.delete", commentId=cid, time=LATER)
        self.assertEqual(self.comments()[0]["text"], "")
        self.assertEqual(self.comments()[0]["mentions"], [])
        self.assertEqual(self.comments()[0]["deletedAt"], LATER)
        self.assertEqual([a["action"] for a in self.activity()[:3]],
                         ["comment.delete", "comment.edit", "comment.add"])
        with self.assertRaises(ValueError):
            self.operate("alice", "comment.edit", commentId=cid, text="revive")

    def test_edit_only_notifies_new_mentions(self):
        cid = self.operate("alice", "comment.add", cardId="c1", text="hello @bob")["result"]["commentId"]
        self.operate("alice", "comment.edit", commentId=cid, text="hello again @bob @dave")
        self.assertEqual(len(self.notices("bob")), 1)
        self.assertEqual(len(self.notices("dave")), 1)

    def test_notice_read_requires_recipient_and_cannot_bypass_revoked_scope(self):
        self.operate("alice", "comment.add", cardId="c1", text="hello @bob")
        nid = self.notices("bob")[0]["id"]
        with self.assertRaises(PermissionError):
            self.operate("dave", "notification.read", notificationId=nid)
        self.operate("bob", "notification.read", notificationId=nid, time=LATER)
        self.assertFalse(self.notices("bob", unread=True))
        self.assertEqual(self.notices("bob")[0]["readAt"], LATER)
        self.accounts["bob"]["projects"] = ["p2"]
        self.assertFalse(self.notices("bob"))
        with self.assertRaises(PermissionError):
            self.operate("bob", "notification.read", notificationId=nid)

    def test_event_idempotency_survives_json_reload_and_no_mutation(self):
        command = {"type": "comment.add", "eventId": "duplicate", "cardId": "c1", "text": "hello @bob"}
        snapshot = deepcopy(self.state)
        first = apply_command(self.state, command, actor="alice", accounts=self.accounts,
                              cards=self.cards, projects=self.projects, now=NOW)
        self.assertEqual(self.state, snapshot)
        saved = json.loads(json.dumps(first["state"]))
        again = apply_command(saved, command, actor="alice", accounts=self.accounts,
                              cards=self.cards, projects=self.projects, now=LATER)
        self.assertFalse(again["changed"])
        self.assertEqual(first["result"], again["result"])
        self.assertEqual(saved, again["state"])
        with self.assertRaisesRegex(ValueError, "Idempotency key reused"):
            apply_command(saved, {**command, "text": "other"}, actor="alice",
                          accounts=self.accounts, cards=self.cards, projects=self.projects, now=LATER)
        with self.assertRaisesRegex(ValueError, "Idempotency key reused"):
            apply_command(saved, command, actor="admin", accounts=self.accounts,
                          cards=self.cards, projects=self.projects, now=LATER)

    def test_idempotent_retry_does_not_bypass_revoked_role_or_project(self):
        command = {"type": "comment.add", "eventId": "revoked-request", "cardId": "c1", "text": "hello"}
        first = apply_command(self.state, command, actor="alice", accounts=self.accounts,
                              cards=self.cards, projects=self.projects, now=NOW)
        self.accounts["alice"]["role"] = "viewer"
        with self.assertRaises(PermissionError):
            apply_command(first["state"], command, actor="alice", accounts=self.accounts,
                          cards=self.cards, projects=self.projects, now=LATER)
        self.accounts["alice"]["role"] = "editor"
        self.accounts["alice"]["projects"] = ["p2"]
        with self.assertRaises(PermissionError):
            apply_command(first["state"], command, actor="alice", accounts=self.accounts,
                          cards=self.cards, projects=self.projects, now=LATER)

    def test_strict_command_validation_and_invalid_timestamps(self):
        commands = [
            {"type": "comment.add", "eventId": "x", "cardId": "c1", "text": "ok", "author": "admin"},
            {"type": "comment.add", "eventId": "x", "cardId": "c1", "text": ""},
            {"type": "watch.set", "eventId": "x", "cardId": "c1", "enabled": 1},
            {"type": "something.else", "eventId": "x"},
        ]
        for command in commands:
            with self.subTest(command=command), self.assertRaises(ValueError):
                apply_command(self.state, command, actor="alice", accounts=self.accounts,
                              cards=self.cards, projects=self.projects, now=NOW)
        with self.assertRaises(ValueError):
            self.operate("alice", "comment.add", cardId="c1", text="hello", time="2026-10-20T15:30:00")

    def test_corrupt_snapshot_rejected_before_processing(self):
        tampered = deepcopy(self.state)
        tampered["unknown"] = []
        with self.assertRaises(ValueError):
            validate_state(tampered)
        tampered = deepcopy(self.state)
        tampered["schemaVersion"] = 2
        with self.assertRaises(ValueError):
            validate_state(tampered)
        tampered = deepcopy(self.state)
        tampered["activity"] = [None]
        with self.assertRaises(ValueError):
            validate_state(tampered)

    def rule(self, rule_id="rule1", **changes):
        rule = {"id": rule_id, "projectId": "p1", "trigger": "card_moved",
                "conditions": [{"field": "toColumnId", "equals": "done"}],
                "actions": [{"type": "notify", "users": ["bob", "carol"], "message": "Card moved to done"}],
                "enabled": True}
        return {**rule, **changes}

    def test_only_admin_can_manage_rules_and_actions_allowlisted(self):
        with self.assertRaises(PermissionError):
            self.operate("alice", "rule.upsert", rule=self.rule())
        with self.assertRaises(ValueError):
            self.operate("admin", "rule.upsert", rule=self.rule(actions=[{"type": "shell", "command": "whoami"}]))
        with self.assertRaises(ValueError):
            self.operate("admin", "rule.upsert", rule=self.rule(conditions=[{"field": "__class__", "equals": "x"}]))
        self.assertFalse(self.state["rules"])

    def test_deterministic_rule_trigger_scope_and_dedupe(self):
        self.operate("admin", "rule.upsert", rule=self.rule())
        ignored = self.operate("alice", "event.publish", cardId="c1", trigger="card_moved",
                               data={"toColumnId": "backlog"})
        self.assertEqual(ignored["result"]["matchedRules"], 0)
        command = {"type": "event.publish", "eventId": "move-card-c1-2026", "cardId": "c1",
                   "trigger": "card_moved", "data": {"toColumnId": "done"}}
        executed = apply_command(self.state, command, actor="alice", accounts=self.accounts,
                                 cards=self.cards, projects=self.projects, now=NOW)
        self.assertEqual(executed["result"]["matchedRules"], 1)
        self.assertEqual(len(executed["result"]["notificationIds"]), 1)
        self.assertEqual(executed["state"]["notifications"][0]["recipient"], "bob")
        self.assertEqual(executed["state"]["runs"][-1]["status"], "applied")
        repeated = apply_command(executed["state"], command, actor="alice", accounts=self.accounts,
                                 cards=self.cards, projects=self.projects, now=LATER)
        self.assertEqual(executed["state"], repeated["state"])
        self.assertFalse(repeated["changed"])

    def test_rules_can_append_comment_without_rerunning_themselves(self):
        self.operate("admin", "rule.upsert", rule=self.rule(actions=[
            {"type": "comment", "text": "Work done @bob"},
            {"type": "notify", "users": ["dave"], "message": "Done"},
        ]))
        self.operate("alice", "event.publish", cardId="c1", trigger="card_moved", data={"toColumnId": "done"})
        self.assertEqual(len(self.comments()), 1)
        self.assertEqual(self.comments()[0]["author"], "alice")
        self.assertEqual(len(self.state["runs"]), 1)
        self.assertEqual({n["recipient"] for n in self.state["notifications"]}, {"bob", "dave"})
        self.assertEqual(len(self.activity()), 3)  # rule creation, comment and event

    def test_disabled_or_revoked_rule_owner_has_no_effect(self):
        self.operate("admin", "rule.upsert", rule=self.rule())
        self.accounts["admin"]["role"] = "viewer"
        self.operate("alice", "event.publish", cardId="c1", trigger="card_moved", data={"toColumnId": "done"})
        self.assertEqual(self.state["runs"][0]["status"], "skipped_scope")
        self.assertFalse(self.state["notifications"])

    def test_rule_project_and_owner_cannot_be_taken_over(self):
        self.operate("admin", "rule.upsert", rule=self.rule())
        with self.assertRaises(PermissionError):
            self.operate("admin", "rule.upsert", rule=self.rule(projectId="p2"))
        with self.assertRaises(PermissionError):
            self.operate("alice", "rule.delete", ruleId="rule1")
        self.operate("admin", "rule.delete", ruleId="rule1")
        self.assertFalse(self.state["rules"])

    def test_rule_event_limits_and_invalid_data(self):
        for i in range(21):
            self.operate("admin", "rule.upsert", rule=self.rule(f"rule-{i}"))
        with self.assertRaisesRegex(ValueError, "execution limit"):
            self.operate("alice", "event.publish", cardId="c1", trigger="card_moved", data={"toColumnId": "done"})
        self.assertFalse(self.state["runs"])
        with self.assertRaises(ValueError):
            self.operate("alice", "event.publish", cardId="c1", trigger="card_moved",
                         data={"__import__": "os"})

    def test_automation_condition_uses_type_strict_equality(self):
        self.operate("admin", "rule.upsert", rule=self.rule(conditions=[
            {"field": "completed", "equals": True}]))
        result = self.operate("alice", "event.publish", cardId="c1", trigger="card_moved",
                              data={"completed": 1})
        self.assertEqual(result["result"]["matchedRules"], 0)
        result = self.operate("alice", "event.publish", cardId="c1", trigger="card_moved",
                              data={"completed": True})
        self.assertEqual(result["result"]["matchedRules"], 1)

    def test_view_snapshots_do_not_share_mutable_references(self):
        self.operate("alice", "comment.add", cardId="c1", text="first @bob")
        comments = self.comments()
        comments[0]["text"] = "mutated"
        notices = self.notices()
        notices[0]["message"] = "mutated"
        activity = self.activity()
        activity[0]["actor"] = "admin"
        self.assertEqual(self.comments()[0]["text"], "first @bob")
        self.assertNotEqual(self.notices()[0]["message"], "mutated")
        self.assertEqual(self.activity()[0]["actor"], "alice")


if __name__ == "__main__":
    unittest.main()
