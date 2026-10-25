"""Deterministic end-to-end domain tests, with no real APPDATA or live services."""

import copy
from datetime import date, timedelta, datetime, timezone
import json
import unittest
from unittest.mock import patch

import automation_v1
import collab
from automation_v1 import (
    empty_state, enqueue_due, enqueue_events, retry_dead, run_batch, validate_state
)


NOW = "2026-10-21T08:00:00Z"
LATER = "2026-10-21T08:02:00Z"
ACCOUNTS = [
    {"username": "owner", "role": "admin", "projects": None},
    {"username": "alice", "role": "editor", "projects": ["project1"]},
    {"username": "bob", "role": "viewer", "projects": ["project1"]},
    {"username": "outside", "role": "editor", "projects": ["project2"]},
]
CARDS = [
    {"id": "card1", "projectId": "project1", "status": "active", "dueDate": "2026-10-23"},
    {"id": "card2", "projectId": "project2", "status": "active", "dueDate": "2026-12-10"},
]
PROJECTS = [{"id": "project1"}, {"id": "project2"}]
EVENT = {"type": "event.publish", "eventId": "event-1", "cardId": "card1",
         "trigger": "card_moved", "data": {"toColumnId": "done"}}


def rule_state():
    existing = collab.empty_state()
    command = {"type": "rule.upsert", "eventId": "add-rule", "rule": {
        "id": "rule1", "projectId": "project1", "trigger": "card_moved",
        "conditions": [{"field": "toColumnId", "equals": "done"}],
        "actions": [{"type": "comment", "text": "Finished safely"},
                    {"type": "notify", "users": ["bob"], "message": "Completed"}],
        "enabled": True
    }}
    return collab.apply_command(
        existing, command, actor="owner", accounts=ACCOUNTS,
        cards=CARDS, projects=PROJECTS, now=NOW
    )["state"]


def queue(state=None, actor="alice", event=None, now=NOW, accounts=None):
    return enqueue_events(
        empty_state() if state is None else state,
        [copy.deepcopy(EVENT if event is None else event)],
        actor=actor, accounts=ACCOUNTS if accounts is None else accounts,
        cards=CARDS, projects=PROJECTS, now=now
    )


def drain(engine, collaboration=None, *, now=NOW, accounts=None, offline=False, **kwargs):
    return run_batch(
        engine, rule_state() if collaboration is None else collaboration,
        accounts=ACCOUNTS if accounts is None else accounts,
        cards=CARDS, projects=PROJECTS, now=now, offline=offline, **kwargs
    )


class AutomationV1Tests(unittest.TestCase):
    def test_queue_and_rule_execution_audit_and_receipt(self):
        initial = empty_state()
        first = queue(initial)
        self.assertEqual(first["added"], 1)
        self.assertEqual(initial, empty_state())
        self.assertTrue(validate_state(first["state"]))
        result = drain(first["state"])
        self.assertEqual(result["applied"], 1)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(len(result["collab"]["comments"]), 1)
        self.assertEqual(result["collab"]["comments"][0]["text"], "Finished safely")
        self.assertEqual([item["recipient"] for item in result["collab"]["notifications"]], ["bob"])
        self.assertEqual(len(result["collab"]["runs"]), 1)
        self.assertEqual(result["state"]["jobs"], [])
        self.assertEqual(result["state"]["receipts"]["event-1"]["status"], "applied")
        self.assertEqual([entry["outcome"] for entry in result["state"]["audit"]],
                         ["queued", "applied"])

    def test_idempotent_enqueue_replay_restart_and_payload_collisions(self):
        first = queue()["state"]
        round_trip = json.loads(json.dumps(first))
        self.assertEqual(queue(round_trip)["added"], 0)
        self.assertEqual(queue(round_trip)["duplicates"], 1)
        result = drain(round_trip)
        after_restart = json.loads(json.dumps(result["state"]))
        again = queue(after_restart)
        self.assertEqual(again["added"], 0)
        self.assertEqual(drain(again["state"], result["collab"])["processed"], 0)
        self.assertEqual(len(result["collab"]["comments"]), 1)
        other = {**EVENT, "data": {"toColumnId": "review"}}
        with self.assertRaisesRegex(ValueError, "Idempotency key"):
            queue(after_restart, event=other)
        with self.assertRaisesRegex(ValueError, "Idempotency key"):
            queue(after_restart, actor="owner")

    def test_collab_committed_but_queue_lost_crash_replays_without_duplication(self):
        enqueued = queue()["state"]
        # Simulate a crash between durable collaboration commit and queue-journal commit.
        first = drain(enqueued)
        stale_engine = json.loads(json.dumps(enqueued))
        repaired = drain(stale_engine, first["collab"], now=LATER)
        self.assertEqual(repaired["applied"], 0)
        self.assertEqual(repaired["replayed"], 1)
        self.assertEqual(len(repaired["collab"]["comments"]), 1)
        self.assertEqual(len(repaired["collab"]["notifications"]), 1)
        self.assertEqual(repaired["state"]["receipts"]["event-1"]["status"], "replayed")

    def test_offline_skips_attempts_and_reconnect_processes_pending(self):
        state = queue()["state"]
        slept = drain(state, offline=True)
        self.assertEqual(slept["processed"], 0)
        self.assertEqual(slept["state"], state)
        self.assertEqual(slept["collab"], rule_state())
        reconnected = drain(json.loads(json.dumps(slept["state"])))
        self.assertEqual(reconnected["applied"], 1)

    def test_transient_failure_retry_backoff_exhaustion_and_manual_admin_requeue(self):
        state = queue()["state"]
        collaboration = rule_state()
        with patch.object(automation_v1.collab, "apply_command", side_effect=RuntimeError("offline")):
            first = drain(state, collaboration, max_attempts=2)
            self.assertEqual(first["retried"], 1)
            self.assertEqual(first["state"]["jobs"][0]["nextAttemptAt"], "2026-10-21T08:01:00Z")
            early = drain(first["state"], collaboration, now="2026-10-21T08:00:30Z", max_attempts=2)
            self.assertEqual(early["processed"], 0)
            failed = drain(first["state"], collaboration, now=LATER, max_attempts=2)
        self.assertEqual(failed["dead"], 1)
        self.assertEqual(failed["state"]["jobs"][0]["status"], "dead")
        self.assertEqual(failed["state"]["jobs"][0]["attempts"], 2)
        self.assertEqual(failed["state"]["audit"][-1]["error"], "transient_failure")
        self.assertNotIn("offline", json.dumps(failed["state"]))
        self.assertEqual(drain(failed["state"], now=LATER)["processed"], 0)
        requeued = retry_dead(failed["state"], "event-1", now=LATER)
        self.assertEqual(requeued["jobs"][0]["attempts"], 0)
        self.assertEqual(drain(requeued, now=LATER)["applied"], 1)

    def test_tightened_retry_budget_fails_closed_without_extra_execution(self):
        state = queue()["state"]
        collaboration = rule_state()
        with patch.object(automation_v1.collab, "apply_command", side_effect=RuntimeError("offline")):
            first = drain(state, collaboration, max_attempts=5)
        # Host configuration changed while offline, so do not execute a second time.
        limited = drain(first["state"], collaboration, now=LATER, max_attempts=1)
        self.assertEqual(limited["processed"], 1)
        self.assertEqual(limited["dead"], 1)
        self.assertEqual(limited["state"]["jobs"][0]["attempts"], 1)
        self.assertEqual(limited["collab"]["comments"], [])

    def test_enforcement_of_actor_permissions_scope_and_unknown_actions(self):
        self.assertRaises(PermissionError, queue, actor="bob")
        self.assertRaises(PermissionError, queue, actor="outside")
        for evil in [
            {**EVENT, "type": "rule.upsert"},
            {**EVENT, "actions": [{"type": "shell", "script": "echo nope"}]},
            {**EVENT, "data": {"arbitrary": "shell"}},
            {**EVENT, "trigger": "exec"},
            {**EVENT, "data": {"toColumnId": {"nested": "not allowed"}}},
        ]:
            with self.subTest(evil=evil), self.assertRaises(ValueError):
                queue(event=evil)
        # Revoking editor before delivery blocks mutation, even if it was queued earlier.
        revoked = copy.deepcopy(ACCOUNTS)
        revoked[1]["role"] = "viewer"
        state = queue()["state"]
        result = drain(state, accounts=revoked)
        self.assertEqual(result["dead"], 1)
        self.assertEqual(result["state"]["audit"][-1]["error"], "permission_denied")
        self.assertEqual(result["collab"]["comments"], [])

    def test_queued_event_cannot_retarget_a_card_moved_to_another_project(self):
        state = queue(actor="owner")["state"]
        moved_cards = copy.deepcopy(CARDS)
        moved_cards[0]["projectId"] = "project2"
        result = run_batch(state, rule_state(), accounts=ACCOUNTS, cards=moved_cards,
                           projects=PROJECTS, now=NOW)
        self.assertEqual(result["dead"], 1)
        self.assertEqual(result["state"]["audit"][-1]["error"], "project_changed")
        self.assertEqual(result["collab"]["comments"], [])
        self.assertEqual(result["collab"]["notifications"], [])

    def test_disabled_or_revoked_rule_owner_never_escalates_access(self):
        state = queue()["state"]
        disabled = rule_state()
        disabled["rules"][0]["enabled"] = False
        result = drain(state, disabled)
        self.assertEqual(result["applied"], 1)
        self.assertEqual(result["collab"]["comments"], [])
        revoked_owner = copy.deepcopy(ACCOUNTS)
        revoked_owner[0]["role"] = "viewer"
        second = drain(state, rule_state(), accounts=revoked_owner)
        self.assertEqual(second["applied"], 1)
        self.assertEqual(second["collab"]["comments"], [])
        self.assertEqual(second["collab"]["runs"][0]["status"], "skipped_scope")

    def test_due_scheduler_respects_date_window_and_dedupes_daily_events(self):
        result = enqueue_due(empty_state(), CARDS, today=date(2026,10,21), actor="alice",
                             accounts=ACCOUNTS, projects=PROJECTS, now=NOW)
        self.assertEqual(result["added"], 1)
        again = enqueue_due(result["state"], CARDS, today=date(2026,10,21), actor="alice",
                            accounts=ACCOUNTS, projects=PROJECTS, now=NOW)
        self.assertEqual(again["duplicates"], 1)
        self.assertEqual(drain(again["state"])["applied"], 1)
        next_day = enqueue_due(result["state"], CARDS, today=date(2026,10,22), actor="alice",
                               accounts=ACCOUNTS, projects=PROJECTS, now=LATER)
        self.assertEqual(next_day["added"], 1)
        self.assertNotEqual(next_day["state"]["jobs"][0]["eventId"],
                            next_day["state"]["jobs"][1]["eventId"])

    def test_batch_capacity_validation_and_partial_processing_are_bounded(self):
        events = [{**EVENT, "eventId": "e-" + str(i)} for i in range(3)]
        state = enqueue_events(empty_state(), events, actor="alice", accounts=ACCOUNTS,
                               cards=CARDS, projects=PROJECTS, now=NOW)["state"]
        result = drain(state, limit=2)
        self.assertEqual(result["processed"], 2)
        self.assertEqual(len(result["state"]["jobs"]), 1)
        complete = drain(result["state"], result["collab"], now=LATER, limit=2)
        self.assertEqual(complete["applied"], 1)
        self.assertEqual(len(complete["collab"]["comments"]), 3)
        for invalid in (0, False, 101, 1.2):
            with self.subTest(limit=invalid), self.assertRaises(ValueError):
                drain(state, limit=invalid)
        with self.assertRaises(ValueError):
            enqueue_events(empty_state(), events * 201, actor="alice",
                           accounts=ACCOUNTS, cards=CARDS, projects=PROJECTS, now=NOW)

    def test_malformed_journal_cannot_mutate_source_or_execute(self):
        state = queue()["state"]
        original = copy.deepcopy(state)
        cases = [
            lambda s: s["jobs"][0].update(command={**EVENT, "type": "shell"}),
            lambda s: s["jobs"][0].update(actor="owner"),
            lambda s: s["jobs"][0].update(fingerprint="f" * 64),
            lambda s: s["jobs"][0].update(status="applied"),
            lambda s: s["jobs"][0].update(status=[]),
            lambda s: s["jobs"][0].update(lastError=[]),
            lambda s: s["audit"][0].update(outcome="unknown"),
            lambda s: s["audit"][0].update(outcome=[]),
            lambda s: s["audit"][0].update(error=[]),
            lambda s: s.update(nextAudit=1),
            lambda s: s["jobs"][0].update(nextAttemptAt="2026-10-21"),
        ]
        for change in cases:
            corrupted = copy.deepcopy(state)
            change(corrupted)
            with self.subTest(change=change), self.assertRaises(ValueError):
                drain(corrupted)
        with self.assertRaises(ValueError):
            queue(state, event={**EVENT, "data": {"toColumnId": "other"}})
        self.assertEqual(state, original)

    def test_invalid_trigger_type_rejected_before_any_enqueue(self):
        state = empty_state()
        for trigger in ([], {"type": "card_moved"}, None, 7):
            with self.subTest(trigger=trigger), self.assertRaises(ValueError):
                queue(state, event={**EVENT, "trigger": trigger})
        self.assertEqual(state, empty_state())

    def test_enqueue_is_atomic_if_one_event_is_invalid_or_restricted(self):
        source = empty_state()
        bad = {**EVENT, "eventId": "event-2", "cardId": "card2"}
        with self.assertRaises(PermissionError):
            enqueue_events(source, [EVENT, bad], actor="alice", accounts=ACCOUNTS,
                           cards=CARDS, projects=PROJECTS, now=NOW)
        self.assertEqual(source, empty_state())


if __name__ == "__main__":
    unittest.main()
