"""Synthetic, isolated preflight tests; never touch disk/APPDATA or host APIs."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
import unittest

from ai_change_review import (
    ApprovalReceipt, ReviewError, approve_plan, decode_proposal_json,
    plan_undo, validate_proposal,
)


NOW = "2026-10-21T12:00:00Z"
REV = "a" * 64
NEXT_REV = "b" * 64
PROMPT_SHA = "c" * 64


class AiReviewTests(unittest.TestCase):
    def setUp(self):
        self.task = {
            "id": "task-123", "projectId": "project-1", "title": "بررسی طرح",
            "status": "active", "priority": "medium", "dueDate": "",
            "cost": 987654321, "costCategory": "private",
            "checklist": [{"id": "step-1", "text": "Private",
                           "cost": 421, "done": False}],
            "reports": [{"id": "r1", "summary": "history"}],
            "arbitraryExtension": {"preserve": [1, 2]},
        }
        self.budget = {
            "perProposalMaxCredits": 150,
            "remainingCredits": 200,
            "maxTotalTokens": 3000,
        }
        self.proposal = {
            "schemaVersion": 1, "proposalId": "proposal-1",
            "taskId": "task-123", "projectId": "project-1",
            "expectedRevision": REV,
            "changes": {"title": "طرح اصلاح شد", "dueDate": "2026-10-25",
                        "priority": "high"},
            "provenance": {
                "source": "ai", "provider": "local-model",
                "model": "model-synthetic-1", "inputSha256": PROMPT_SHA,
                "evidenceIds": ["task-123", "report-r1"],
                "generatedAt": NOW,
            },
            "usage": {"inputTokens": 200, "outputTokens": 100,
                      "estimatedCredits": 75},
        }

    def plan(self, *, proposal=None, task=None, revision=REV,
             opt_in=True, can_edit=True, project_grants=("project-1",),
             priorities=("low", "medium", "high"), budget=None, now=NOW):
        return validate_proposal(
            self.proposal if proposal is None else proposal,
            task=self.task if task is None else task,
            revision=revision, opt_in=opt_in, can_edit=can_edit,
            project_grants=project_grants, priorities=priorities,
            budget=self.budget if budget is None else budget, now=now,
        )

    def approve(self, plan, *, task=None, revision=REV, opt_in=True,
                can_edit=True, project_grants=("project-1",),
                budget=None, now=NOW, approval=None, reviewer="manager-1"):
        approval = approval if approval is not None else {
            "decision": "approve", "planDigest": plan.digest,
            "reviewer": reviewer, "approvalId": "approval-1",
        }
        return approve_plan(
            plan, task=self.task if task is None else task,
            revision=revision, approval=approval, reviewer=reviewer,
            opt_in=opt_in, can_edit=can_edit,
            project_grants=project_grants,
            budget=self.budget if budget is None else budget, now=now,
        )

    def rejects(self, expected_code, callable_, *args, **kwargs):
        with self.assertRaises(ReviewError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected_code)

    def test_happy_path_immutable_diff_and_readonly_review(self):
        original_task, original_proposal = deepcopy(self.task), deepcopy(self.proposal)
        plan = self.plan()
        self.assertEqual([x.field for x in plan.changes],
                         ["dueDate", "priority", "title"])
        self.assertEqual(plan.changes[2].before, "بررسی طرح")
        self.assertEqual(plan.changes[2].after, "طرح اصلاح شد")
        self.assertEqual(len(plan.digest), 64)
        self.assertEqual(plan.provenance.input_sha256, PROMPT_SHA)
        self.assertEqual(plan.provenance.evidence_ids, ("task-123", "report-r1"))
        self.assertEqual(self.task, original_task)
        self.assertEqual(self.proposal, original_proposal)
        with self.assertRaises(FrozenInstanceError):
            plan.changes[0].after = "Tampered"
        with self.assertRaises(FrozenInstanceError):
            plan.provenance.input_sha256 = "d" * 64
        self.assertEqual(self.plan(), plan)

    def test_untrusted_json_decoder_accepts_only_bounded_unique_utf8_object(self):
        raw = json.dumps(self.proposal, ensure_ascii=False).encode("utf-8")
        parsed = decode_proposal_json(raw)
        self.assertEqual(self.plan(proposal=parsed), self.plan())
        self.assertEqual(decode_proposal_json(raw.decode("utf-8")), parsed)
        self.rejects("duplicate_json_key", decode_proposal_json,
                     '{"schemaVersion":1,"schemaVersion":1}')
        self.rejects("duplicate_json_key", decode_proposal_json,
                     '{"provenance":{"source":"ai","source":"manual"}}')
        for raw_bad in (b'\xff', "[]", "null", '"string"', "NaN", "Infinity",
                        "{", object()):
            with self.subTest(raw=raw_bad):
                self.rejects("invalid_json", decode_proposal_json, raw_bad)
        self.rejects("proposal_too_large", decode_proposal_json,
                     b" " * 16_385)

    def test_explicit_human_approval_returns_candidate_and_audit_charge_intents(self):
        plan = self.plan()
        result = self.approve(plan)
        self.assertEqual(result.candidate_task["title"], "طرح اصلاح شد")
        self.assertEqual(result.candidate_task["dueDate"], "2026-10-25")
        self.assertEqual(result.candidate_task["priority"], "high")
        self.assertEqual(result.candidate_task["status"], "active")
        self.assertEqual(result.candidate_task["cost"], self.task["cost"])
        self.assertEqual(result.candidate_task["checklist"], self.task["checklist"])
        self.assertEqual(result.candidate_task["arbitraryExtension"],
                         self.task["arbitraryExtension"])
        self.assertEqual(self.task["title"], "بررسی طرح")
        result.candidate_task["checklist"][0]["cost"] = 0
        self.assertEqual(self.task["checklist"][0]["cost"], 421)
        self.assertEqual(result.budget_remaining_credits, 125)
        self.assertEqual(result.receipt.charged_credits, 75)
        self.assertEqual(result.audit["reviewer"], "manager-1")
        self.assertEqual(result.audit["planDigest"], plan.digest)
        self.assertEqual(result.audit["changedFields"],
                         ["dueDate", "priority", "title"])
        self.assertNotIn("cost", result.audit)
        self.assertNotIn("customer", result.audit)
        self.assertNotIn("secret", result.audit)

    def test_opt_in_is_strict_and_not_part_of_model_supplied_payload(self):
        self.rejects("opt_in_required", self.plan, opt_in=False)
        self.rejects("opt_in_required", self.plan, opt_in="true")
        self.rejects("opt_in_required", self.plan, opt_in=1)
        plan = self.plan()
        self.rejects("opt_in_required", self.approve, plan, opt_in=False)
        mutated = deepcopy(self.proposal)
        mutated["optIn"] = True
        self.rejects("invalid_proposal", self.plan, proposal=mutated)

    def test_role_and_project_grants_must_come_from_trusted_context(self):
        self.rejects("permission_denied", self.plan, can_edit=False)
        self.rejects("permission_denied", self.plan, can_edit=1)
        self.rejects("project_denied", self.plan, project_grants=("other",))
        self.rejects("project_denied", self.plan, project_grants=None)
        self.rejects("project_denied", self.plan, project_grants="project-1")
        plan = self.plan()
        self.rejects("permission_denied", self.approve, plan, can_edit=False)
        self.rejects("project_denied", self.approve, plan,
                     project_grants=("other",))

    def test_rejects_all_sensitive_or_side_effecting_paths(self):
        forbidden = [
            "status", "cost", "costEnabled", "costDate", "price", "finance",
            "invoices", "ledger", "account", "role", "projects", "users",
            "assignees", "checklist", "reports", "fileLinks", "attachments",
            "automation", "code", "command", "shell", "url", "script",
            "webhook", "deleted", "archived", "__proto__", "foo.bar",
            "title.__class__", "/tasks/0/title",
        ]
        for field in forbidden:
            with self.subTest(field=field):
                changed = deepcopy(self.proposal)
                changed["changes"] = {field: "anything"}
                self.rejects("disallowed_field", self.plan, proposal=changed)
        altered = deepcopy(self.proposal)
        altered["changes"]["finance"] = {"amount": 100}
        self.rejects("disallowed_field", self.plan, proposal=altered)

    def test_strict_root_proposal_schema_and_version(self):
        for field, value in [
            ("schemaVersion", 2), ("schemaVersion", True),
            ("taskId", "incorrect"), ("projectId", "other"),
            ("expectedRevision", "b" * 64),
        ]:
            with self.subTest(field=field):
                proposal = deepcopy(self.proposal)
                proposal[field] = value
                expected = {
                    "schemaVersion": "invalid_proposal", "taskId": "task_mismatch",
                    "projectId": "project_denied", "expectedRevision": "revision_conflict",
                }[field]
                self.rejects(expected, self.plan, proposal=proposal)
        for operation in ("delete", "execute", "httpRequest", "writeFile"):
            proposal = deepcopy(self.proposal)
            proposal[operation] = {"url": "https://example.test"}
            self.rejects("invalid_proposal", self.plan, proposal=proposal)

    def test_rejects_inactive_or_malformed_task_and_invalid_revision(self):
        for field in ("deleted", "archived"):
            task = deepcopy(self.task)
            task[field] = True
            self.rejects("inactive_task", self.plan, task=task)
        task = deepcopy(self.task)
        task["title"] = 9
        self.rejects("invalid_task", self.plan, task=task)
        self.rejects("invalid_digest", self.plan, revision="bad")
        task = deepcopy(self.task)
        task["finance"] = {1, 2}
        self.rejects("invalid_task", self.plan, task=task)

    def test_no_effect_and_invalid_content(self):
        for value, expected in [
            ("بررسی طرح", "no_effect"), ("  ", "invalid_text"),
            ("a" * 161, "invalid_text"), ("safe\u202espoof", "invalid_text"),
            ("ok\nnewline", "invalid_text"), (42, "disallowed_field"),
            (True, "disallowed_field"), (["unsafe"], "disallowed_field"),
        ]:
            with self.subTest(value=value):
                proposal = deepcopy(self.proposal)
                proposal["changes"] = {"title": value}
                self.rejects(expected, self.plan, proposal=proposal)
        for value in ("2026-02-30", "2026/03/01", "2026-1-01", "2033-13-01"):
            proposal = deepcopy(self.proposal)
            proposal["changes"] = {"dueDate": value}
            self.rejects("invalid_date", self.plan, proposal=proposal)
        proposal = deepcopy(self.proposal)
        proposal["changes"] = {"priority": "undefined"}
        self.rejects("invalid_priority", self.plan, proposal=proposal)

    def test_budget_cap_token_cap_and_type_poisoning(self):
        for key, value, reason in [
            ("perProposalMaxCredits", 1, "budget_exceeded"),
            ("remainingCredits", 74, "budget_exceeded"),
            ("maxTotalTokens", 299, "token_cap_exceeded"),
            ("remainingCredits", True, "invalid_budget"),
            ("remainingCredits", -1, "invalid_budget"),
            ("perProposalMaxCredits", 10**12, "invalid_budget"),
        ]:
            budget = deepcopy(self.budget)
            budget[key] = value
            self.rejects(reason, self.plan, budget=budget)
        for key, value, reason in [
            ("inputTokens", True, "invalid_usage"),
            ("outputTokens", -1, "invalid_usage"),
            ("estimatedCredits", 151, "budget_exceeded"),
            ("inputTokens", 5000, "token_cap_exceeded"),
        ]:
            prop = deepcopy(self.proposal)
            prop["usage"][key] = value
            self.rejects(reason, self.plan, proposal=prop)
        plan = self.plan()
        smaller_budget = deepcopy(self.budget)
        smaller_budget["remainingCredits"] = 74
        self.rejects("budget_exceeded", self.approve, plan, budget=smaller_budget)

    def test_provenance_cannot_be_missing_forged_silently_or_outdated(self):
        cases = [
            ("source", "manual", "invalid_provenance"),
            ("inputSha256", "unknown", "invalid_digest"),
            ("provider", "\n", "invalid_text"),
            ("model", "", "invalid_text"),
            ("generatedAt", "2020-01-01T00:00:00Z", "stale_proposal"),
            ("generatedAt", "2026-10-22T00:00:00Z", "stale_proposal"),
            ("generatedAt", "2026-10-21", "invalid_time"),
            ("evidenceIds", ["dup", "dup"], "invalid_provenance"),
            ("evidenceIds", list(map(str, range(9))), "invalid_provenance"),
        ]
        for key, value, expected in cases:
            with self.subTest(key=key, value=value):
                prop = deepcopy(self.proposal)
                prop["provenance"][key] = value
                self.rejects(expected, self.plan, proposal=prop)
        prop = deepcopy(self.proposal)
        prop["provenance"]["externalCommand"] = "run now"
        self.rejects("invalid_provenance", self.plan, proposal=prop)

    def test_approval_requires_exact_human_identity_and_explicit_matching_digest(self):
        plan = self.plan()
        base = {"decision": "approve", "planDigest": plan.digest,
                "reviewer": "manager-1", "approvalId": "approval-1"}
        for field, value, reason in [
            ("decision", "auto", "approval_required"),
            ("decision", True, "approval_required"),
            ("planDigest", "0" * 64, "approval_plan_mismatch"),
            ("reviewer", "ai-model", "approval_identity_mismatch"),
            ("approvalId", "bad id", "invalid_id"),
        ]:
            review = dict(base)
            review[field] = value
            self.rejects(reason, self.approve, plan, approval=review)
        review = dict(base)
        review["approvedAutomatically"] = True
        self.rejects("approval_required", self.approve, plan, approval=review)
        self.rejects("approval_required", self.approve, plan, approval={})

    def test_stale_revision_and_task_snapshot_refuse_changes_even_if_fields_same(self):
        plan = self.plan()
        self.rejects("revision_conflict", self.approve, plan, revision=NEXT_REV)
        changed = deepcopy(self.task)
        changed["cost"] += 1
        self.rejects("task_conflict", self.approve, plan, task=changed)
        changed = deepcopy(self.task)
        changed["title"] = "updated by coworker"
        self.rejects("task_conflict", self.approve, plan, task=changed)
        self.rejects("stale_proposal", self.approve, plan,
                     now="2026-10-23T12:00:00Z")

    def test_tampered_frozen_plan_replacement_cannot_be_approved(self):
        plan = self.plan()
        self.rejects("plan_tampered", self.approve, replace(plan, estimated_credits=0))
        self.rejects("plan_tampered", self.approve, replace(plan, task_id="other"))
        self.rejects("plan_tampered", self.approve, replace(plan, digest="f" * 64))
        self.rejects("invalid_plan", self.approve, replace(plan, changes=tuple()))

    def test_canonical_snapshot_ignores_dict_order_but_not_finance_changes(self):
        plan = self.plan()
        task = dict(reversed(list(self.task.items())))
        self.assertEqual(self.plan(task=task), plan)
        task["cost"] = self.task["cost"] + 1
        self.assertNotEqual(self.plan(task=task).digest, plan.digest)
        self.assertEqual(self.plan(task=task).changes, plan.changes)

    def test_limits_bound_proposal_and_snapshot_without_side_effect(self):
        prop = deepcopy(self.proposal)
        prop["provenance"]["model"] = "m" * 17_000
        self.rejects("proposal_too_large", self.plan, proposal=prop)
        task = deepcopy(self.task)
        task["extra"] = "x" * 200_000
        self.rejects("invalid_task", self.plan, task=task)
        prop = deepcopy(self.proposal)
        prop["changes"] = {}
        self.rejects("disallowed_field", self.plan, proposal=prop)

    def test_undo_planning_requires_durable_receipt_and_new_revision(self):
        plan = self.plan()
        approved = self.approve(plan)
        candidate = approved.candidate_task
        unchanged = deepcopy(candidate)
        self.rejects("uncommitted_approval", plan_undo, approved.receipt,
                     committed_revision=NEXT_REV, task=candidate, revision=NEXT_REV,
                     persisted=False, opt_in=True, can_edit=True,
                     project_grants=("project-1",))
        undo = plan_undo(
            approved.receipt, committed_revision=NEXT_REV,
            task=candidate, revision=NEXT_REV, persisted=True,
            opt_in=True, can_edit=True, project_grants=("project-1",),
        )
        self.assertEqual(candidate, unchanged)
        self.assertEqual(undo.task_id, "task-123")
        self.assertEqual(undo.expected_revision, NEXT_REV)
        self.assertEqual([(x.field, x.before, x.after) for x in undo.changes],
                         [(x.field, x.after, x.before) for x in plan.changes])
        with self.assertRaises(FrozenInstanceError):
            undo.digest = "other"
        self.rejects("revision_conflict", plan_undo, approved.receipt,
                     committed_revision=NEXT_REV, task=candidate, revision=REV,
                     persisted=True, opt_in=True, can_edit=True,
                     project_grants=("project-1",))

    def test_undo_refuses_any_subsequent_change_even_in_unedited_private_field(self):
        receipt = self.approve(self.plan()).receipt
        candidate = self.approve(self.plan()).candidate_task
        candidate["cost"] += 1
        self.rejects("task_conflict", plan_undo, receipt,
                     committed_revision=NEXT_REV, task=candidate, revision=NEXT_REV,
                     persisted=True, opt_in=True, can_edit=True,
                     project_grants=("project-1",))

    def test_undo_needs_fresh_permission_and_is_plan_only(self):
        approved = self.approve(self.plan())
        kw = dict(committed_revision=NEXT_REV, task=approved.candidate_task,
                  revision=NEXT_REV, persisted=True, opt_in=True,
                  can_edit=True, project_grants=("project-1",))
        self.rejects("opt_in_required", plan_undo, approved.receipt,
                     **{**kw, "opt_in": False})
        self.rejects("permission_denied", plan_undo, approved.receipt,
                     **{**kw, "can_edit": False})
        self.rejects("project_denied", plan_undo, approved.receipt,
                     **{**kw, "project_grants": ("other",)})
        self.assertEqual(self.task["title"], "بررسی طرح")
        self.assertEqual(self.approve(self.plan()).candidate_task["title"],
                         "طرح اصلاح شد")

    def test_undo_checks_receipt_shape_and_bounded_fields(self):
        applied = self.approve(self.plan())
        original = applied.receipt
        args = dict(committed_revision=NEXT_REV, task=applied.candidate_task,
                    revision=NEXT_REV, persisted=True, opt_in=True,
                    can_edit=True, project_grants=("project-1",))
        self.rejects("invalid_id", plan_undo,
                     replace(original, approval_id="untrusted id"), **args)
        self.rejects("invalid_digest", plan_undo,
                     replace(original, source_task_sha256="bad"), **args)
        self.rejects("invalid_receipt", plan_undo,
                     replace(original, charged_credits=True), **args)
        self.rejects("invalid_receipt", plan_undo,
                     replace(original, changes=tuple()), **args)
        self.rejects("invalid_receipt", plan_undo,
                     replace(original, changes=original.changes + original.changes),
                     **args)


if __name__ == "__main__":
    unittest.main()
