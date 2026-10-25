"""M07 pure preflight acceptance tests. No APPDATA, filesystem or network."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import automation_v1
import collab
from rule_safety import (
    DEFAULT_POLICY, dry_run_events, event_signature, inspect_replay,
    make_safety_audit, preflight_due_batch, validate_safety_policy,
    verify_safety_audit,
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
    {"id": "card1", "projectId": "project1", "status": "active", "cost": 980000,
     "invoiceId": "finance-secret", "attachments": [{"id": "asset-secret"}]},
    {"id": "card2", "projectId": "project2", "status": "active"},
]
PROJECTS = [
    {"id": "project1", "price": 32000000},
    {"id": "project2", "price": 6000000},
]
EVENT = {
    "type": "event.publish", "eventId": "event1",
    "cardId": "card1", "trigger": "card_moved",
    "data": {"toColumnId": "done"},
}


def policy(**patches):
    return {**DEFAULT_POLICY, **patches}


def rule_state(*, owner="owner", enabled=True, extra_rules=0):
    state = collab.empty_state()
    for index in range(extra_rules + 1):
        item = {
            "id": "rule" + str(index), "projectId": "project1",
            "trigger": "card_moved",
            "conditions": [{"field": "toColumnId", "equals": "done"}],
            "actions": [
                {"type": "comment", "text": "Do not reveal this comment"},
                {"type": "notify", "users": ["bob"], "message": "secret info"},
            ],
            "enabled": enabled,
        }
        output = collab.apply_command(
            state, {"type": "rule.upsert", "eventId": "seed" + str(index),
                    "rule": item},
            actor="owner", accounts=ACCOUNTS, cards=CARDS,
            projects=PROJECTS, now=NOW)
        state = output["state"]
        state["rules"][-1]["owner"] = owner  # scoped fixture modification
    self_check = collab.validate_state(state)
    if not self_check:
        raise AssertionError("invalid rule_state")
    return state


def enqueue(events=None, *, actor="alice", state=None):
    if events is None:
        events = [deepcopy(EVENT)]
    return automation_v1.enqueue_events(
        automation_v1.empty_state() if state is None else state, events,
        actor=actor, accounts=ACCOUNTS, cards=CARDS, projects=PROJECTS, now=NOW)["state"]


class RuleSafetyTests(unittest.TestCase):
    def setUp(self):
        self.journal = automation_v1.empty_state()
        self.collaboration = rule_state()
        self.snapshot = (
            deepcopy(self.journal), deepcopy(self.collaboration),
            deepcopy(ACCOUNTS), deepcopy(CARDS), deepcopy(PROJECTS))

    def dry(self, events=None, *, actor="alice", journal=None,
            collaboration=None, accounts=None, cards=None, p=None,
            ancestry=None, stamp=NOW):
        return dry_run_events(
            self.journal if journal is None else journal,
            self.collaboration if collaboration is None else collaboration,
            [deepcopy(EVENT)] if events is None else events,
            actor=actor, accounts=ACCOUNTS if accounts is None else accounts,
            cards=CARDS if cards is None else cards, projects=PROJECTS,
            now=stamp, policy=p, ancestry=ancestry)

    def due(self, engine, *, collaboration=None, accounts=None, cards=None,
            stamp=NOW, p=None, ancestry=None, offline=False):
        return preflight_due_batch(
            engine, self.collaboration if collaboration is None else collaboration,
            accounts=ACCOUNTS if accounts is None else accounts,
            cards=CARDS if cards is None else cards, projects=PROJECTS,
            now=stamp, policy=p, ancestry=ancestry, offline=offline)

    def test_default_policy_defensive_copy_strict_shape_and_bounds(self):
        copy = validate_safety_policy()
        self.assertEqual(copy, DEFAULT_POLICY)
        self.assertIsNot(copy, DEFAULT_POLICY)
        copy["maxEvents"] = 99
        self.assertEqual(DEFAULT_POLICY["maxEvents"], 25)
        for invalid in ({}, [], {"maxEvents": 1}, None):
            if invalid is None:
                continue
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_safety_policy(invalid)
        for key, invalid in (("maxEvents", 0), ("maxEvents", True),
                             ("maxEvents", 101), ("maxActions", -1),
                             ("maxChainDepth", 17), ("maxAttempts", 9),
                             ("maxAttempts", False), ("maxRetriesPerBatch", 101),
                             ("maxConsecutiveFailures", 0),
                             ("maxAuditPreview", 101)):
            with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                validate_safety_policy(policy(**{key: invalid}))

    def test_clean_dry_run_lists_only_redacted_rule_action_counts(self):
        result = self.dry()
        self.assertEqual((result["safeToExecute"], result["allowed"],
                          result["blocked"], result["estimatedActions"]),
                         (True, 1, 0, 2))
        decision = result["decisions"][0]
        self.assertEqual(decision["eventId"], "event1")
        self.assertEqual(decision["outcome"], "allow")
        self.assertEqual(decision["matchedRules"], 1)
        self.assertEqual(decision["eligibleRules"], 1)
        self.assertEqual(decision["skippedScopeRules"], 0)
        self.assertEqual(decision["commentActions"], 1)
        self.assertEqual(decision["notifyActions"], 1)
        serialized = json.dumps(result)
        for private in ("Do not reveal", "secret info", "finance-secret",
                        "asset-secret", "32000000", "980000", "bob"):
            self.assertNotIn(private, serialized)

    def test_dry_run_does_not_call_any_reducer_or_scheduler_or_touch_input(self):
        with patch.object(collab, "apply_command", side_effect=AssertionError("execute")), (
             patch.object(automation_v1, "run_batch", side_effect=AssertionError("run"))), (
             patch.object(automation_v1, "retry_dead", side_effect=AssertionError("retry"))):
            first = self.dry()
            second = self.dry()
        self.assertEqual(first, second)
        self.assertEqual((self.journal, self.collaboration, ACCOUNTS, CARDS, PROJECTS),
                         self.snapshot)

    def test_rule_owner_revocation_yields_no_effect_even_for_matching_rule(self):
        revoked = self.dry(collaboration=rule_state(owner="alice"))
        self.assertEqual(revoked["allowed"], 1)
        self.assertEqual(revoked["estimatedActions"], 0)
        self.assertEqual(revoked["decisions"][0]["matchedRules"], 1)
        self.assertEqual(revoked["decisions"][0]["eligibleRules"], 0)
        self.assertEqual(revoked["decisions"][0]["skippedScopeRules"], 1)
        disabled = self.dry(collaboration=rule_state(enabled=False))
        self.assertEqual(disabled["decisions"][0]["matchedRules"], 0)

    def test_viewer_foreign_project_and_revoked_actor_refused(self):
        for actor in ("bob", "outside", "unknown"):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.dry(actor=actor)
        revoked = deepcopy(ACCOUNTS)
        revoked[1]["role"] = "viewer"
        with self.assertRaises(PermissionError):
            self.dry(accounts=revoked)

    def test_untrusted_event_actor_never_overrides_authenticated_host_actor(self):
        attacker = {**EVENT, "actor": "owner"}
        with self.assertRaises(ValueError):
            self.dry([attacker], actor="alice")
        with self.assertRaises(PermissionError):
            self.dry([EVENT], actor="bob")
        self.assertEqual(self.dry([EVENT], actor="alice")["allowed"], 1)

    def test_arbitrary_commands_and_code_piggyback_refused_before_execution(self):
        payloads = [
            {**EVENT, "type": "shell.exec"},
            {**EVENT, "python": "import os"},
            {**EVENT, "data": {"exec": "echo"}},
            {**EVENT, "trigger": "subprocess"},
            {**EVENT, "data": {"toColumnId": {"$cmd": "whoami"}}},
        ]
        with patch.object(collab, "apply_command", side_effect=AssertionError("side effect")):
            for event in payloads:
                with self.subTest(event=event), self.assertRaises(ValueError):
                    self.dry([event])

    def test_typed_rule_conditions_must_match_boolean_int_and_text_exactly(self):
        exact = self.dry(events=[{**EVENT, "data": {"toColumnId": "done"}}])
        self.assertEqual(exact["estimatedActions"], 2)
        different = self.dry(events=[{**EVENT, "data": {"toColumnId": "planned"}}])
        self.assertEqual(different["estimatedActions"], 0)

    def test_event_signature_excludes_event_id_but_preserves_card_data_and_project(self):
        sig = event_signature(EVENT, "project1")
        self.assertEqual(len(sig), 64)
        self.assertEqual(sig, event_signature({**EVENT, "eventId": "other"}, "project1"))
        self.assertNotEqual(sig, event_signature({**EVENT, "data": {}}, "project1"))
        self.assertNotEqual(sig, event_signature(EVENT, "project2"))
        self.assertNotEqual(sig, event_signature({**EVENT, "cardId": "card2"}, "project1"))

    def test_causal_depth_and_same_signature_halts_generated_event_ids(self):
        sig = event_signature(EVENT, "project1")
        other = "f" * 64
        deeper = self.dry(ancestry={"event1": [other, other, other, other]})
        self.assertFalse(deeper["safeToExecute"])
        self.assertEqual(deeper["decisions"][0]["reason"], "chain_depth")
        repeated = self.dry(ancestry={"event1": [sig, sig]})
        self.assertEqual(repeated["decisions"][0]["reason"], "repeated_signature")
        self.assertEqual(repeated["estimatedActions"], 0)
        allowed = self.dry(ancestry={"event1": [sig]})
        self.assertEqual(allowed["allowed"], 1)

    def test_loop_cutout_when_multiple_fresh_event_ids_share_signature(self):
        events = [{**EVENT, "eventId": "ev" + str(i)} for i in range(3)]
        result = self.dry(events)
        self.assertEqual((result["allowed"], result["blocked"]), (2, 1))
        self.assertEqual(result["decisions"][-1]["reason"], "batch_loop")
        self.assertFalse(result["safeToExecute"])
        self.assertEqual(result["estimatedActions"], 4)

    def test_policy_limits_total_actions_and_entire_batch_is_rejected(self):
        events = [{**EVENT, "eventId": "different" + str(i),
                   "data": {"toColumnId": "done", "priority": i}}
                  for i in range(3)]
        result = self.dry(events, p=policy(maxActions=3))
        self.assertEqual((result["allowed"], result["blocked"]), (1, 2))
        self.assertEqual(result["decisions"][1]["reason"], "action_budget")
        self.assertFalse(result["safeToExecute"])

    def test_batch_event_count_and_duplicate_ids_are_strict(self):
        with self.assertRaises(ValueError):
            self.dry([EVENT] * 26)
        with self.assertRaisesRegex(ValueError, "Duplicate eventId"):
            self.dry([EVENT, deepcopy(EVENT)])
        with self.assertRaises(ValueError):
            self.dry((EVENT,))
        self.assertEqual(self.dry([])["decisions"], [])

    def test_replay_disposition_new_queued_receipted_and_collab_crash_gap(self):
        self.assertEqual(inspect_replay(self.journal, self.collaboration,
                                        EVENT, actor="alice")["disposition"], "new")
        enqueued = enqueue()
        queued = inspect_replay(enqueued, self.collaboration, EVENT, actor="alice")
        self.assertEqual(queued["disposition"], "already_queued")
        self.assertEqual(self.dry(journal=enqueued)["duplicates"], 1)
        result = automation_v1.run_batch(enqueued, self.collaboration,
                                         accounts=ACCOUNTS, cards=CARDS,
                                         projects=PROJECTS, now=NOW)
        applied = inspect_replay(result["state"], result["collab"],
                                 EVENT, actor="alice")
        self.assertEqual(applied["disposition"], "already_applied")
        gap = inspect_replay(enqueued, result["collab"], EVENT, actor="alice")
        self.assertEqual(gap["disposition"], "collab_committed")
        self.assertEqual(self.dry(journal=enqueued,
                                  collaboration=result["collab"])["duplicates"], 1)

    def test_replay_collision_with_same_id_different_payload_or_actor_fails(self):
        queued = enqueue()
        changed = {**EVENT, "data": {"toColumnId": "review"}}
        for event, actor in ((changed, "alice"), (EVENT, "owner")):
            with self.subTest(event=event, actor=actor), self.assertRaisesRegex(
                    ValueError, "collision"):
                inspect_replay(queued, self.collaboration, event, actor=actor)

    def test_replay_survives_json_roundtrip_and_audit_is_independent(self):
        queued = json.loads(json.dumps(enqueue()))
        prior = deepcopy(queued)
        result = self.dry(journal=queued)
        self.assertEqual(result["decisions"][0]["reason"], "already_queued")
        self.assertEqual(prior, queued)

    def test_due_batch_deterministic_queue_order_and_bounded_deferral(self):
        events = [{**EVENT, "eventId": "ev-" + str(n),
                   "data": {"toColumnId": "done", "priority": n}}
                  for n in range(4)]
        queued = enqueue(events)
        queued["jobs"][0]["nextAttemptAt"] = LATER
        queued["jobs"][1]["nextAttemptAt"] = NOW
        queued["jobs"][2]["nextAttemptAt"] = NOW
        queued["jobs"][3]["nextAttemptAt"] = NOW
        self.assertTrue(automation_v1.validate_state(queued))
        result = self.due(queued, p=policy(maxEvents=2))
        self.assertEqual([i["eventId"] for i in result["decisions"]], ["ev-1", "ev-2"])
        self.assertEqual(result["deferred"], 1)
        self.assertEqual(result["safeLimit"], 2)
        later = self.due(queued, stamp=LATER, p=policy(maxEvents=2))
        self.assertEqual(later["deferred"], 2)

    def test_due_preview_never_invokes_reducer_even_for_ready_jobs(self):
        queued = enqueue()
        before = deepcopy(queued)
        with patch.object(collab, "apply_command", side_effect=AssertionError("called")):
            result = self.due(queued)
        self.assertEqual(result["allowed"], 1)
        self.assertEqual(result["estimatedActions"], 2)
        self.assertEqual(result["safeLimit"], 1)
        self.assertEqual(queued, before)

    def test_due_offline_skips_retry_attempts_and_all_effects(self):
        queued = enqueue()
        result = self.due(queued, offline=True)
        self.assertTrue(result["offline"])
        self.assertEqual(result["decisions"], [])
        self.assertEqual(result["safeLimit"], 0)
        self.assertEqual(queued["jobs"][0]["attempts"], 0)
        with self.assertRaises(ValueError):
            self.due(queued, offline="true")

    def test_due_causal_loop_and_repeated_signature_budgets(self):
        queued = enqueue()
        sig = event_signature(EVENT, "project1")
        blocked = self.due(queued, ancestry={"event1": [sig, sig]})
        self.assertFalse(blocked["safeToExecute"])
        self.assertEqual(blocked["decisions"][0]["reason"], "repeated_signature")
        self.assertEqual(blocked["safeLimit"], 0)

    def test_due_retry_budget_and_job_attempt_stop_loss(self):
        queued = enqueue([
            {**EVENT, "eventId": "retry-" + str(n),
             "data": {"toColumnId": "done", "priority": n}}
            for n in range(3)])
        for job in queued["jobs"]:
            job.update(status="retry", attempts=1,
                       lastError="transient_failure", nextAttemptAt=NOW)
        self.assertTrue(automation_v1.validate_state(queued))
        result = self.due(queued, p=policy(maxRetriesPerBatch=1))
        self.assertEqual(result["decisions"][1]["reason"], "retry_budget")
        self.assertFalse(result["safeToExecute"])
        exhausted = self.due(queued, p=policy(maxAttempts=1))
        self.assertEqual(exhausted["blocked"], 3)
        self.assertTrue(all(x["reason"] == "retry_exhausted"
                            for x in exhausted["decisions"]))

    def test_due_project_move_or_role_revocation_blocks_execution(self):
        queued = enqueue()
        changed = deepcopy(CARDS)
        changed[0]["projectId"] = "project2"
        changed_result = self.due(queued, cards=changed)
        self.assertEqual(changed_result["decisions"][0]["reason"], "project_changed")
        self.assertEqual(changed_result["safeLimit"], 0)
        revoked = deepcopy(ACCOUNTS)
        revoked[1]["role"] = "viewer"
        denied = self.due(queued, accounts=revoked)
        self.assertEqual(denied["decisions"][0]["reason"], "permission_denied")
        self.assertEqual(denied["safeLimit"], 0)

    def test_due_crash_gap_detects_collab_receipt_without_producing_actions(self):
        queued = enqueue()
        delivered = automation_v1.run_batch(
            queued, self.collaboration, accounts=ACCOUNTS,
            cards=CARDS, projects=PROJECTS, now=NOW)
        gap = self.due(queued, collaboration=delivered["collab"])
        self.assertTrue(gap["safeToExecute"])
        self.assertEqual(gap["decisions"][0]["reason"], "collab_committed")
        self.assertEqual(gap["estimatedActions"], 0)
        self.assertEqual(gap["duplicates"], 1)
        forged = deepcopy(delivered["collab"])
        forged["receipts"]["event1"]["fingerprint"] = "a" * 64
        self.assertTrue(collab.validate_state(forged))
        with self.assertRaisesRegex(ValueError, "collision"):
            self.due(queued, collaboration=forged)

    def test_circuit_stop_loss_on_consecutive_failure_history(self):
        queued = enqueue()
        queued["audit"].extend([
            {"sequence": n + 2, "eventId": "bad" + str(n),
             "outcome": "retry" if n % 2 == 0 else "dead",
             "attempt": 1, "error": "transient_failure", "at": NOW}
            for n in range(4)])
        queued["nextAudit"] = 6
        self.assertTrue(automation_v1.validate_state(queued))
        stopped = self.due(queued)
        self.assertEqual(stopped["failureStreak"], 4)
        self.assertEqual(stopped["decisions"][0]["reason"], "stop_loss")
        self.assertFalse(stopped["safeToExecute"])
        self.assertEqual(self.dry(journal=queued)["decisions"][0]["reason"], "already_queued")
        next_event = {**EVENT, "eventId": "event-new"}
        fresh = self.dry(events=[next_event], journal=queued)
        self.assertEqual(fresh["decisions"][0]["reason"], "stop_loss")

    def test_audit_preview_is_deterministic_chain_without_private_payload(self):
        dry = self.dry()
        audit = make_safety_audit(dry, now=NOW)
        repeated = make_safety_audit(json.loads(json.dumps(dry)), now=NOW)
        self.assertEqual(audit, repeated)
        self.assertEqual(audit["nextSequence"], 2)
        self.assertEqual(audit["records"][0]["sequence"], 1)
        self.assertEqual(len(audit["lastHash"]), 64)
        self.assertEqual(audit["records"][0]["previousHash"], "0" * 64)
        shifted = make_safety_audit(dry, now="2026-10-21T11:30:00+03:30")
        self.assertEqual(shifted, audit)
        private = json.dumps(audit)
        for token in ("Do not reveal", "secret info", "finance-secret",
                      "asset-secret", "bob"):
            self.assertNotIn(token, private)

    def test_audit_chains_multiple_events_and_never_alters_sources(self):
        events = [
            {**EVENT, "eventId": "evt" + str(n),
             "data": {"toColumnId": "done", "priority": n}}
            for n in range(3)]
        dry = self.dry(events)
        prior = deepcopy(dry)
        preview = make_safety_audit(dry, now=LATER, first_sequence=50,
                                    previous_hash="a" * 64)
        self.assertEqual([r["sequence"] for r in preview["records"]], [50, 51, 52])
        self.assertEqual(preview["records"][1]["previousHash"],
                         preview["records"][0]["hash"])
        self.assertEqual(preview["records"][2]["previousHash"],
                         preview["records"][1]["hash"])
        self.assertEqual(preview["nextSequence"], 53)
        self.assertEqual(dry, prior)

    def test_audit_verification_detects_edits_order_and_trusted_head_mismatch(self):
        events = [{**EVENT, "eventId": "e" + str(i),
                   "data": {"toColumnId": "done", "priority": i}}
                  for i in range(4)]
        preview = make_safety_audit(self.dry(events), now=NOW)
        baseline = deepcopy(preview["records"])
        self.assertEqual(verify_safety_audit(
            baseline, expected_final_hash=preview["lastHash"])["count"], 4)
        cases = [
            lambda records: records[0].update(actions=100),
            lambda records: records[1].update(reason="invalid"),
            lambda records: records[2].update(hash="e" * 64),
            lambda records: records[0].update(outcome=[]),
            lambda records: records[0].update(reason=[]),
            lambda records: records[0].update(sequence=5),
            lambda records: records.reverse(),
        ]
        for mutate in cases:
            changed = deepcopy(baseline)
            mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                verify_safety_audit(changed,
                                    expected_final_hash=preview["lastHash"])
        with self.assertRaisesRegex(ValueError, "trusted head"):
            verify_safety_audit(baseline[:-1],
                                expected_final_hash=preview["lastHash"])
        self.assertEqual(baseline, preview["records"])

    def test_audit_accepts_offset_sequence_and_rejects_malformed_overflow(self):
        preview = make_safety_audit(self.dry(), now=NOW,
                                    first_sequence=10,previous_hash="f"*64)
        result = verify_safety_audit(
            preview["records"], first_sequence=10,previous_hash="f"*64,
            expected_final_hash=preview["lastHash"])
        self.assertEqual(result["nextSequence"],11)
        for bad in (None, {}, "audit", [None]*10001):
            with self.subTest(value=type(bad).__name__), self.assertRaises(ValueError):
                verify_safety_audit(bad)
        with self.assertRaises(ValueError):
            verify_safety_audit(preview["records"],first_sequence=True)
        with self.assertRaises(ValueError):
            verify_safety_audit(preview["records"],previous_hash="invalid")

    def test_audit_malformed_replay_capacity_and_timestamp_rejected(self):
        dry = self.dry()
        with self.assertRaises(ValueError):
            make_safety_audit(dry, now="2026-10-21")
        with self.assertRaises(ValueError):
            make_safety_audit(dry, now=NOW, previous_hash="oops")
        with self.assertRaises(ValueError):
            make_safety_audit(dry, now=NOW, first_sequence=True)
        changed = deepcopy(dry)
        changed["decisions"][0]["commentText"] = "leak"
        with self.assertRaises(ValueError):
            make_safety_audit(changed, now=NOW)
        changed = deepcopy(dry)
        changed["decisions"][0]["actions"] = True
        with self.assertRaises(ValueError):
            make_safety_audit(changed, now=NOW)
        long = deepcopy(dry)
        long["decisions"] *= 101
        with self.assertRaisesRegex(ValueError, "limit"):
            make_safety_audit(long, now=NOW)

    def test_corrupt_engine_or_collab_state_rejected_without_mutation(self):
        journal = deepcopy(self.journal)
        journal["jobs"] = "unexpected"
        with self.assertRaises(ValueError):
            self.dry(journal=journal)
        altered = deepcopy(self.collaboration)
        altered["rules"][0]["actions"] = [{"type": "python", "code": "system"}]
        with self.assertRaises(ValueError):
            self.dry(collaboration=altered)

    def test_global_rule_account_card_and_project_caps_prevent_unbounded_preflight(self):
        collaboration = deepcopy(self.collaboration)
        collaboration["rules"] *= 2001
        with self.assertRaisesRegex(ValueError, "rules capacity"):
            self.dry(collaboration=collaboration)
        cards = deepcopy(CARDS)
        cards.extend({"id": "extra" + str(i), "projectId": "project1"}
                     for i in range(20_000))
        with self.assertRaisesRegex(ValueError, "cards capacity"):
            self.dry(cards=cards)
        accounts = deepcopy(ACCOUNTS)
        accounts.extend({"username": "extra" + str(i), "role": "viewer",
                         "projects": ["project1"]} for i in range(1_000))
        with self.assertRaisesRegex(ValueError, "accounts capacity"):
            self.dry(accounts=accounts)

    def test_ancestry_malformed_depth_and_untrusted_event_id_are_rejected(self):
        sig = event_signature(EVENT, "project1")
        for bad in (
            {"event1": sig}, {"event1": ["unhashed"]},
            {"event1": [sig] * 17}, {"INVALID !": [sig]},
            {str(i): [] for i in range(26)},
        ):
            with self.subTest(ancestry=bad), self.assertRaises(ValueError):
                self.dry(ancestry=bad)

    def test_due_replay_and_dry_run_persisted_data_remain_byte_equivalent(self):
        queued = json.loads(json.dumps(enqueue()))
        source = json.dumps([queued, self.collaboration, CARDS, PROJECTS],
                            sort_keys=True, ensure_ascii=False)
        for _ in range(10):
            expected = self.due(queued)
            actual = self.due(queued)
            self.assertEqual(actual, expected)
            self.assertEqual(self.dry(journal=queued)["duplicates"], 1)
        self.assertEqual(
            json.dumps([queued, self.collaboration, CARDS, PROJECTS],
                       sort_keys=True, ensure_ascii=False), source)


if __name__ == "__main__":
    unittest.main()
