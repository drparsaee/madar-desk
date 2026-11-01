"""M-07 host-wiring regression gate: disposable SQLite only.

These are deliberately end-to-end RED contracts until Bridge enforces
rule_safety before enqueue/run. Never mock the safety verdict into success:
the real policy makes each allow/deny decision against a real SQLite snapshot.
No user's APPDATA, LAN server, release, or finance files are opened.
"""

from copy import deepcopy
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import automation_v1
import m07_host_guard
import native_app
import rule_safety
from app_storage import UnifiedAppStorage
from automation_due import due_events
from automation_events import card_change_events


PAST = "2026-01-01T00:00:00Z"
ADMIN = {"local": {"username": "local", "role": "admin", "projects": None}}
VIEWER = {"local": {"username": "local", "role": "viewer", "projects": ["p-sample"]}}


def event(event_id, card_id="example-2", number=0):
    return {"type": "event.publish", "eventId": event_id, "cardId": card_id,
            "trigger": "card_moved", "data": {"toColumnId": f"stage-{number}"}}


def new_cards(base, count):
    """Create distinct schema-valid cards whose lifecycle emits count events."""
    state = deepcopy(base)
    source = next(card for card in state["tasks"] if card["id"] == "example-2")
    for i in range(count):
        cloned = deepcopy(source)
        cloned.update(id=f"m07-fixture-{i:03d}", title=f"Synthetic M07 {i:03d}",
                      status="active", listId="active", dueDate="", archived=False,
                      deleted=False, cost=0, costEnabled=False)
        cloned["reports"] = []
        cloned["assignees"] = []
        cloned["labels"] = []
        cloned["labelIds"] = []
        cloned["checklist"] = []
        cloned["checklists"] = []
        cloned["customFieldValues"] = {}
        state["tasks"].append(cloned)
    return state


class M07HostPreflightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-m07-host-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        datadir = patch.object(native_app, "datadir", return_value=self.root)
        datadir.start()
        self.addCleanup(datadir.stop)
        self.bridge = native_app.Bridge()
        self.bridge.saveState(native_app.initial_state())
        self.assertEqual(self.bridge.enableUnifiedStorage()["mode"], "sqlite")
        self.assertEqual(self.bridge.enableAutomationEngine()["mode"], "active")
        self.store = UnifiedAppStorage(self.bridge.unified_path)
        self.assertTrue(self.store.integrity_check())
        self.assertEqual(set(self.store.load().bundle),
                         {"tasks", "collab", "finance", "completion_outbox", "automation"})

    def snapshot(self):
        return self.store.load()

    def unchanged(self, before):
        after = self.snapshot()
        self.assertEqual(after.revision, before.revision)
        self.assertEqual(after.sha256, before.sha256)
        for key in ("tasks", "finance", "collab", "automation", "completion_outbox"):
            self.assertEqual(after.bundle[key], before.bundle[key], key)
        self.assertTrue(self.store.integrity_check())

    def rule(self, trigger="card_created", actions=None):
        if actions is None:
            actions = [{"type": "comment", "text": "Synthetic M07 notification"}]
        self.bridge.collabCommand({
            "type": "rule.upsert", "eventId": "m07-rule-" + trigger,
            "rule": {"id": "m07-rule-" + trigger, "projectId": "p-sample",
                     "trigger": trigger, "conditions": [],
                     "actions": actions, "enabled": True}})

    def queue(self, events, *, actor="local"):
        before = self.snapshot()
        bundle = deepcopy(before.bundle)
        cards, projects = bundle["tasks"]["tasks"], bundle["tasks"]["projects"]
        queued = automation_v1.enqueue_events(
            bundle["automation"], events, actor=actor, accounts=ADMIN,
            cards=cards, projects=projects, now=PAST)
        bundle["automation"] = queued["state"]
        self.store.commit(bundle, expected_revision=before.revision)
        return queued

    def test_disposable_sqlite_control_dry_run_is_pure_and_reports_budget_denial(self):
        self.rule(actions=[
            {"type": "comment", "text": "First"},
            {"type": "comment", "text": "Second"}])
        before = self.snapshot()
        candidate = new_cards(before.bundle["tasks"], 21)
        events = card_change_events(before.bundle["tasks"], candidate)
        self.assertEqual(len(events), 21)
        report = rule_safety.dry_run_events(
            before.bundle["automation"], before.bundle["collab"], events,
            actor="local", accounts=ADMIN, cards=candidate["tasks"],
            projects=candidate["projects"], now=PAST)
        self.assertEqual(report["blocked"], 1)
        self.assertFalse(report["safeToExecute"])
        self.assertEqual(report["decisions"][-1]["reason"], "action_budget")
        self.unchanged(before)

    def test_save_rejects_more_than_25_events_before_enqueue_and_keeps_all_domains(self):
        before = self.snapshot()
        candidate = new_cards(before.bundle["tasks"], 26)
        self.assertEqual(len(card_change_events(before.bundle["tasks"], candidate)), 26)
        with (patch.object(m07_host_guard, "dry_run_events",
                           wraps=m07_host_guard.dry_run_events) as preflight,
              patch.object(automation_v1, "enqueue_events",
                           side_effect=AssertionError("enqueue before M07 gate")) as enqueue,
              patch.object(automation_v1, "run_batch",
                           side_effect=AssertionError("run before M07 gate")) as run):
            with self.assertRaises((ValueError, PermissionError, RuntimeError)):
                self.bridge._save_local_state(
                    candidate, actor="local", accounts=ADMIN)
            self.assertEqual(preflight.call_count, 1)
            enqueue.assert_not_called()
            run.assert_not_called()
        self.unchanged(before)

    def test_save_rejects_action_budget_before_task_and_finance_commit(self):
        self.rule(actions=[
            {"type": "comment", "text": "First"},
            {"type": "comment", "text": "Second"}])
        before = self.snapshot()
        candidate = new_cards(before.bundle["tasks"], 21)
        # The real preflight permits the first 20 then blocks the 21st.
        with (patch.object(m07_host_guard, "dry_run_events",
                           wraps=m07_host_guard.dry_run_events) as preflight,
              patch.object(automation_v1, "enqueue_events",
                           side_effect=AssertionError("budget-denied enqueue")) as enqueue,
              patch.object(automation_v1, "run_batch",
                           side_effect=AssertionError("budget-denied run")) as run):
            with self.assertRaises((ValueError, PermissionError, RuntimeError)):
                self.bridge._save_local_state(candidate, actor="local", accounts=ADMIN)
            self.assertEqual(preflight.call_count, 1)
            self.assertEqual(preflight.call_args.args[2].__len__(), 21)
            enqueue.assert_not_called()
            run.assert_not_called()
        self.unchanged(before)

    def test_save_authoritative_viewer_grant_denial_precedes_enqueue(self):
        before = self.snapshot()
        candidate = new_cards(before.bundle["tasks"], 1)
        with (patch.object(m07_host_guard, "dry_run_events",
                           wraps=m07_host_guard.dry_run_events) as preflight,
              patch.object(automation_v1, "enqueue_events",
                           side_effect=AssertionError("unauthorized enqueue")) as enqueue):
            with self.assertRaises(PermissionError):
                self.bridge._save_local_state(candidate, actor="local", accounts=VIEWER)
            self.assertEqual(preflight.call_count, 1)
            enqueue.assert_not_called()
        self.unchanged(before)

    def test_allowed_card_move_previews_before_enqueue_and_due_before_run(self):
        self.rule(trigger="card_moved")
        before = self.snapshot()
        candidate = deepcopy(before.bundle["tasks"])
        target = next(card for card in candidate["tasks"] if card["id"] == "example-2")
        self.assertNotEqual(target["status"], "review")
        target["status"] = "review"
        target["listId"] = "review"
        events = card_change_events(before.bundle["tasks"], candidate)
        self.assertEqual(len(events), 1)
        calls = []

        def observe(name, real):
            def wrapped(*args, **kwargs):
                outcome = real(*args, **kwargs)
                calls.append((name, kwargs.copy(), deepcopy(outcome)))
                return outcome
            return wrapped

        with (patch.object(m07_host_guard, "dry_run_events",
                           side_effect=observe("dry", m07_host_guard.dry_run_events)),
              patch.object(automation_v1, "enqueue_events",
                           side_effect=observe("enqueue", automation_v1.enqueue_events)),
              patch.object(m07_host_guard, "preflight_due_batch",
                           side_effect=observe("due", m07_host_guard.preflight_due_batch)),
              patch.object(automation_v1, "run_batch",
                           side_effect=observe("run", automation_v1.run_batch))):
            self.assertTrue(self.bridge._save_local_state(
                candidate, actor="local", accounts=ADMIN))
        self.assertEqual([c[0] for c in calls], ["dry", "enqueue", "due", "run"])
        self.assertTrue(calls[0][2]["safeToExecute"])
        self.assertEqual(calls[0][2]["allowed"], 1)
        self.assertTrue(calls[2][2]["safeToExecute"])
        self.assertEqual(calls[3][1]["limit"], calls[2][2]["safeLimit"])
        self.assertEqual(calls[3][1]["max_attempts"], 3)
        after = self.snapshot()
        self.assertGreater(after.revision, before.revision)
        self.assertEqual(after.bundle["finance"], before.bundle["finance"])
        self.assertEqual(len(after.bundle["collab"]["comments"]), 1)
        self.assertEqual(len(after.bundle["automation"]["receipts"]), 1)
        self.assertEqual(next(card["status"] for card in after.bundle["tasks"]["tasks"]
                              if card["id"] == "example-2"), "review")
        self.assertTrue(self.store.integrity_check())

    def test_restricted_editor_cannot_enqueue_other_projects_card_event(self):
        before = self.snapshot()
        candidate = new_cards(before.bundle["tasks"], 1)
        limited = {"local": {"username": "local", "role": "editor",
                             "projects": ["p-personal"]}}
        with (patch.object(m07_host_guard, "dry_run_events",
                           wraps=m07_host_guard.dry_run_events) as preflight,
              patch.object(automation_v1, "enqueue_events",
                           side_effect=AssertionError("foreign project queued")) as enqueue):
            with self.assertRaises(PermissionError):
                self.bridge._save_local_state(candidate, actor="local", accounts=limited)
            preflight.assert_called_once()
            enqueue.assert_not_called()
        self.unchanged(before)

    def test_due_scheduler_preflights_deterministic_order_limit_25_and_max_attempts_3(self):
        events = [event(f"m07-queued-{i:02d}", number=i) for i in range(26)]
        self.queue(events)
        before = self.snapshot()
        self.assertEqual(len(before.bundle["automation"]["jobs"]), 26)
        invocations = []
        real_preflight = m07_host_guard.preflight_due_batch
        real_run = automation_v1.run_batch

        def inspect(*args, **kwargs):
            result = real_preflight(*args, **kwargs)
            invocations.append(("preflight", deepcopy(result), deepcopy(kwargs)))
            return result

        def execute(*args, **kwargs):
            invocations.append(("run", None, deepcopy(kwargs)))
            return real_run(*args, **kwargs)

        with (patch.object(m07_host_guard, "preflight_due_batch", side_effect=inspect),
              patch.object(automation_v1, "run_batch", side_effect=execute)):
            result = self.bridge._run_engine_scheduler("local", ADMIN)
        self.assertEqual([item[0] for item in invocations], ["preflight", "run"])
        inspected = invocations[0][1]
        self.assertTrue(inspected["safeToExecute"])
        self.assertEqual(inspected["safeLimit"], 25)
        self.assertEqual(inspected["deferred"], 1)
        self.assertEqual([x["eventId"] for x in inspected["decisions"]],
                         [f"m07-queued-{i:02d}" for i in range(25)])
        kwargs = invocations[-1][2]
        self.assertEqual(kwargs["limit"], 25)
        self.assertEqual(kwargs["max_attempts"], 3)
        self.assertEqual(result["pending"], 1)
        after = self.snapshot()
        self.assertEqual(len(after.bundle["automation"]["jobs"]), 1)
        self.assertEqual(after.bundle["automation"]["jobs"][0]["eventId"],
                         "m07-queued-25")
        self.assertEqual(after.bundle["tasks"], before.bundle["tasks"])
        self.assertEqual(after.bundle["finance"], before.bundle["finance"])

    def test_due_retry_exhausted_at_three_denies_entire_run_without_commit(self):
        self.queue([event("m07-stop-loss")])
        now = self.snapshot()
        altered = deepcopy(now.bundle)
        job = altered["automation"]["jobs"][0]
        job.update(status="retry", attempts=3,
                   lastError="transient_failure", nextAttemptAt=PAST)
        automation_v1.validate_state(altered["automation"])
        self.store.commit(altered, expected_revision=now.revision)
        before = self.snapshot()
        preview = rule_safety.preflight_due_batch(
            before.bundle["automation"], before.bundle["collab"],
            accounts=ADMIN, cards=before.bundle["tasks"]["tasks"],
            projects=before.bundle["tasks"]["projects"], now=PAST)
        self.assertFalse(preview["safeToExecute"])
        self.assertEqual(preview["safeLimit"], 0)
        self.assertEqual(preview["decisions"][0]["reason"], "retry_exhausted")
        with (patch.object(m07_host_guard, "preflight_due_batch",
                           wraps=m07_host_guard.preflight_due_batch) as preflight,
              patch.object(automation_v1, "run_batch",
                           side_effect=AssertionError("exhausted event executed")) as run):
            try:
                self.bridge._run_engine_scheduler("local", ADMIN)
            except (PermissionError, ValueError, RuntimeError):
                pass
            preflight.assert_called_once()
            run.assert_not_called()
        self.unchanged(before)

    def test_due_revoked_role_denies_run_with_no_task_finance_or_queue_changes(self):
        self.queue([event("m07-revoked")])
        before = self.snapshot()
        preview = rule_safety.preflight_due_batch(
            before.bundle["automation"], before.bundle["collab"],
            accounts=VIEWER, cards=before.bundle["tasks"]["tasks"],
            projects=before.bundle["tasks"]["projects"], now=PAST)
        self.assertFalse(preview["safeToExecute"])
        self.assertEqual(preview["decisions"][0]["reason"], "permission_denied")
        with (patch.object(m07_host_guard, "preflight_due_batch",
                           wraps=m07_host_guard.preflight_due_batch) as preflight,
              patch.object(automation_v1, "run_batch",
                           side_effect=AssertionError("revoked actor executed")) as run):
            try:
                self.bridge._run_engine_scheduler("local", VIEWER)
            except (PermissionError, ValueError, RuntimeError):
                pass
            preflight.assert_called_once()
            run.assert_not_called()
        self.unchanged(before)


if __name__ == "__main__":
    unittest.main()
