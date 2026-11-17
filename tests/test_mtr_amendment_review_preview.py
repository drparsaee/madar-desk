"""Synthetic E5 preview tests. No app profiles, finance ledger or network."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import socket
import unittest
from unittest.mock import patch

from mtr_amendment_review_preview import (
    AmendmentPreviewError,
    preview_create_amendment,
    preview_manual_submission,
    preview_rejection_guidance,
    review_field_choices,
    review_changed_baseline,
)


class E5ReviewPreviewTests(unittest.TestCase):
    def setUp(self):
        self.principal = {
            "userId": "editor-1",
            "orgId": "org-a",
            "projectIds": ["project-1"],
            "canDraft": True,
            "canReview": True,
            "canSubmit": True,
        }
        self.original = {
            "requestId": "finance-original-1",
            "orgId": "org-a",
            "projectId": "project-1",
            "submitted": True,
            "revision": "revision-1",
            "fields": {
                "partyId": "party-old", "quantity": 10,
                "unitPrice": 300, "notes": "initial",
            },
        }
        self.related = [{
            "amendmentId": "amendment-open-1",
            "originalRequestId": "finance-original-1",
            "orgId": "org-a",
            "projectId": "project-1",
            "revision": "amendment-rev-1",
            "status": "in_review",
            "proposedFields": {"partyId": "party-other", "quantity": 20},
        }]

    def create(self, **overrides):
        kwargs = {
            "principal": self.principal,
            "original": self.original,
            "amendment_id": "amendment-new-2",
            "proposed_fields": {"partyId": "party-new", "quantity": 10},
            "related_amendments": (),
            "acknowledged_at": "2026-11-09T14:00:00Z",
        }
        kwargs.update(overrides)
        return preview_create_amendment(**kwargs)

    def allowed(self, **overrides):
        result = self.create(**overrides)
        self.assertTrue(result.allowed)
        self.assertIsNotNone(result.draft)
        return result.draft

    def rejects(self, code, func, *args, **kwargs):
        with self.assertRaises(AmendmentPreviewError) as seen:
            func(*args, **kwargs)
        self.assertEqual(seen.exception.code, code)
        self.assertNotIn("org-b", str(seen.exception))
        self.assertNotIn("foreign", str(seen.exception))

    def test_independent_ids_links_and_original_request_unchanged(self):
        source = deepcopy(self.original)
        preview = self.create()
        self.assertTrue(preview.allowed)
        self.assertEqual(preview.action, "preview_only")
        self.assertEqual(preview.draft.contract.amendment_id, "amendment-new-2")
        self.assertEqual(preview.draft.contract.original_request_id, source["requestId"])
        self.assertNotEqual(preview.draft.contract.amendment_id, source["requestId"])
        self.assertEqual(preview.draft.original_revision, "revision-1")
        self.assertEqual(self.original, source)
        self.assertEqual(preview.draft.status, "draft")
        self.assertEqual(preview.draft.review_events, ())

    def test_open_and_likely_duplicate_require_two_separate_acknowledgments(self):
        related = deepcopy(self.related)
        related[0]["proposedFields"] = {"partyId": "party-new", "quantity": 10}
        kwargs = {"related_amendments": related}
        blocked = self.create(**kwargs)
        self.assertFalse(blocked.allowed)
        self.assertIsNone(blocked.draft)
        self.assertEqual(blocked.blocked_by,
                         ("open_amendment_ack_required",
                          "possible_duplicate_ack_required"))
        self.assertEqual(blocked.open_amendment_ids, ("amendment-open-1",))
        self.assertEqual(blocked.possible_duplicate_ids, ("amendment-open-1",))
        only_open = self.create(**kwargs, acknowledged_open=True)
        self.assertEqual(only_open.blocked_by,
                         ("possible_duplicate_ack_required",))
        only_duplicate = self.create(**kwargs, acknowledged_duplicate=True)
        self.assertEqual(only_duplicate.blocked_by,
                         ("open_amendment_ack_required",))
        allowed = self.create(**kwargs, acknowledged_open=True,
                              acknowledged_duplicate=True)
        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.draft.conflicts, ())
        self.assertEqual([event.kind for event in allowed.draft.review_events], [
            "acknowledge_open_amendment", "acknowledge_possible_duplicate"])
        self.assertTrue(all(event.user_id == "editor-1" for event in
                            allowed.draft.review_events))
        self.assertEqual(allowed.draft.review_events[0].source_amendment_ids,
                         ("amendment-open-1",))
        self.rejects("invalid_time", self.create, **kwargs,
                     acknowledged_open=True, acknowledged_duplicate=True,
                     acknowledged_at=None)

    def test_duplicate_of_closed_amendment_warns_without_open_warning(self):
        related = deepcopy(self.related)
        related[0]["status"] = "closed"
        related[0]["proposedFields"] = {"partyId": "party-new", "quantity": 10}
        preview = self.create(related_amendments=related)
        self.assertEqual(preview.blocked_by, ("possible_duplicate_ack_required",))
        self.assertEqual(preview.open_amendment_ids, ())

    def test_open_but_different_proposal_warns_without_duplicate_warning(self):
        preview = self.create(related_amendments=self.related)
        self.assertEqual(preview.blocked_by, ("open_amendment_ack_required",))
        self.assertEqual(preview.possible_duplicate_ids, ())

    def test_open_conflict_is_field_level_and_source_qualified(self):
        draft = self.allowed(related_amendments=self.related,
                             acknowledged_open=True)
        self.assertEqual(len(draft.conflicts), 2)
        self.assertEqual([c.field for c in draft.conflicts],
                         ["partyId", "quantity"])
        first = draft.conflicts[0]
        self.assertEqual(first.baseline_value, "party-old")
        self.assertEqual(first.proposed_value, "party-new")
        self.assertEqual(first.related_value, "party-other")
        self.assertEqual(first.related_revision, "amendment-rev-1")
        self.assertEqual(first.related_amendment_id, "amendment-open-1")
        self.assertEqual(draft.contract.conflicting_fields,
                         frozenset({"partyId", "quantity"}))

    def test_human_choice_is_explicit_audited_and_immutable(self):
        draft = self.allowed(related_amendments=self.related,
                             acknowledged_open=True)
        original = deepcopy(self.original)
        resolved = review_field_choices(
            draft, principal=self.principal,
            chosen_values={"partyId": "party-approved"},
            occurred_at="2026-11-09T14:00:00+00:00",
        )
        self.assertEqual(resolved.contract.proposed_fields["partyId"],
                         "party-approved")
        self.assertEqual(draft.contract.proposed_fields["partyId"], "party-new")
        self.assertEqual(resolved.contract.resolutions["partyId"],
                         "party-approved")
        self.assertNotIn("quantity", resolved.contract.resolutions)
        self.assertEqual(len(resolved.review_events), 2)
        self.assertEqual(resolved.review_events[0].kind,
                         "acknowledge_open_amendment")
        event = resolved.review_events[-1]
        self.assertEqual(event.user_id, "editor-1")
        self.assertEqual(event.kind, "resolve_conflict")
        self.assertEqual(event.choices, (("partyId", "party-approved"),))
        self.assertEqual(event.source_amendment_ids, ("amendment-open-1",))
        self.assertEqual(original, self.original)
        with self.assertRaises(TypeError):
            resolved.contract.resolutions["quantity"] = 22
        with self.assertRaises(FrozenInstanceError):
            resolved.org_id = "org-b"

    def test_reviewer_can_choose_none_explicitly_and_no_auto_value_guess(self):
        draft = self.allowed(related_amendments=self.related,
                             acknowledged_open=True)
        result = review_field_choices(
            draft, principal=self.principal, chosen_values={"partyId": None},
            occurred_at="2026-11-09T14:00:00Z")
        self.assertIsNone(result.contract.resolutions["partyId"])
        self.assertEqual(result.review_events[-1].choices, (("partyId", None),))

    def test_unauthorized_reviewer_or_unrelated_field_cannot_change(self):
        draft = self.allowed(related_amendments=self.related,
                             acknowledged_open=True)
        denied = {**self.principal, "canReview": False}
        self.rejects("scope_denied", review_field_choices, draft,
                     principal=denied, chosen_values={"quantity": 9},
                     occurred_at="2026-11-09T14:00:00Z")
        self.rejects("scope_denied", review_field_choices, draft,
                     principal={**self.principal, "orgId": "org-b"},
                     chosen_values={"quantity": 9},
                     occurred_at="2026-11-09T14:00:00Z")
        self.rejects("unrelated_field_choice", review_field_choices, draft,
                     principal=self.principal, chosen_values={"unitPrice": 5},
                     occurred_at="2026-11-09T14:00:00Z")
        self.rejects("invalid_fields", review_field_choices, draft,
                     principal=self.principal, chosen_values={},
                     occurred_at="2026-11-09T14:00:00Z")
        self.rejects("invalid_time", review_field_choices, draft,
                     principal=self.principal, chosen_values={"quantity": 9},
                     occurred_at="not-a-time")
        self.assertEqual(len(draft.review_events), 1)
        self.assertEqual(draft.review_events[0].kind,
                         "acknowledge_open_amendment")

    def test_unresolved_conflicts_block_submission_even_on_explicit_send(self):
        draft = self.allowed(related_amendments=self.related,
                             acknowledged_open=True)
        result = preview_manual_submission(
            draft, principal=self.principal, current_original=self.original,
            current_related_amendments=self.related,
            explicit_manual_action=True)
        self.assertFalse(result.allowed)
        self.assertIn("unresolved_field_conflicts", result.blocked_by)
        self.assertEqual(result.unresolved_conflict_fields,
                         ("partyId", "quantity"))
        self.assertEqual(result.action, "preview_only")

    def test_resolving_conflicts_does_not_trigger_resubmission(self):
        draft = self.allowed(related_amendments=self.related,
                             acknowledged_open=True)
        resolved = review_field_choices(
            draft, principal=self.principal,
            chosen_values={"partyId": "party-approved", "quantity": 20},
            occurred_at="2026-11-09T14:00:00Z")
        result = preview_manual_submission(
            resolved, principal=self.principal, current_original=self.original,
            current_related_amendments=self.related, explicit_manual_action=False)
        self.assertFalse(result.allowed)
        self.assertIn("manual_send_action_required", result.blocked_by)
        with_action = preview_manual_submission(
            resolved, principal=self.principal, current_original=self.original,
            current_related_amendments=self.related, explicit_manual_action=True)
        self.assertTrue(with_action.allowed)
        self.assertEqual(with_action.blocked_by, ())
        self.assertEqual(with_action.action, "preview_only")
        self.assertEqual(self.related[0]["proposedFields"]["partyId"],
                         "party-other")

    def test_self_amendment_in_related_registry_is_not_a_competitor(self):
        draft = self.allowed()
        own_entry = {
            "amendmentId": "amendment-new-2",
            "originalRequestId": "finance-original-1",
            "orgId": "org-a",
            "projectId": "project-1",
            "revision": "new-revision-1",
            "status": "draft",
            "proposedFields": dict(draft.contract.proposed_fields),
        }
        check = preview_manual_submission(
            draft, principal=self.principal, current_original=self.original,
            current_related_amendments=[own_entry],
            explicit_manual_action=True)
        self.assertTrue(check.allowed)
        self.assertEqual(check.affected_fields_to_review, ())
        self.assertEqual(check.unresolved_conflict_fields, ())

    def test_original_no_longer_submitted_is_fail_closed(self):
        draft = self.allowed()
        retracted = {**self.original, "submitted": False}
        self.rejects("original_not_submitted", preview_manual_submission,
                     draft, principal=self.principal, current_original=retracted,
                     current_related_amendments=(), explicit_manual_action=True)
        self.rejects("original_not_submitted", review_changed_baseline,
                     draft, principal=self.principal, current_original=retracted,
                     current_related_amendments=(), chosen_values={},
                     acknowledged_dependency_fields=[],
                     acknowledged_revision_change=True,
                     occurred_at="2026-11-09T14:00:00Z")

    def test_changed_original_value_blocks_only_affected_field(self):
        draft = self.allowed()
        changed = deepcopy(self.original)
        changed["revision"] = "revision-2"
        changed["fields"]["quantity"] = 12
        result = preview_manual_submission(
            draft, principal=self.principal, current_original=changed,
            current_related_amendments=(), explicit_manual_action=True)
        self.assertFalse(result.allowed)
        self.assertEqual(result.affected_fields_to_review, ("quantity",))
        self.assertIn("stale_original_revision", result.blocked_by)
        self.assertIn("stale_baseline_requires_review", result.blocked_by)
        self.assertNotIn("partyId", result.affected_fields_to_review)
        self.assertEqual(draft.contract.baseline["quantity"], 10)

    def test_revision_changed_without_field_delta_still_blocks(self):
        draft = self.allowed()
        changed = deepcopy(self.original)
        changed["revision"] = "revision-2"
        result = preview_manual_submission(
            draft, principal=self.principal, current_original=changed,
            current_related_amendments=(), explicit_manual_action=True)
        self.assertEqual(result.affected_fields_to_review, ())
        self.assertEqual(result.blocked_by, ("stale_original_revision",))

    def test_stale_re_review_requires_explicit_values_then_fresh_send_check(self):
        draft = self.allowed()
        original = deepcopy(self.original)
        original["revision"] = "revision-2"
        original["fields"]["quantity"] = 12
        self.rejects(
            "revision_ack_required", review_changed_baseline, draft,
            principal=self.principal, current_original=original,
            current_related_amendments=(), chosen_values={"quantity": 12},
            acknowledged_dependency_fields=[], acknowledged_revision_change=False,
            occurred_at="2026-11-09T14:00:00Z")
        self.rejects(
            "incomplete_field_review", review_changed_baseline, draft,
            principal=self.principal, current_original=original,
            current_related_amendments=(), chosen_values={},
            acknowledged_dependency_fields=[], acknowledged_revision_change=True,
            occurred_at="2026-11-09T14:00:00Z")
        changed = review_changed_baseline(
            draft, principal=self.principal, current_original=original,
            current_related_amendments=(), chosen_values={"quantity": 12},
            acknowledged_dependency_fields=[], acknowledged_revision_change=True,
            occurred_at="2026-11-09T14:00:00Z")
        self.assertEqual(changed.original_revision, "revision-2")
        self.assertEqual(changed.contract.proposed_fields["quantity"], 12)
        self.assertEqual(changed.contract.baseline["quantity"], 12)
        self.assertEqual(draft.original_revision, "revision-1")
        self.assertEqual(draft.contract.proposed_fields["quantity"], 10)
        self.assertEqual(changed.review_events[-1].kind, "review_changed_baseline")
        self.assertTrue(preview_manual_submission(
            changed, principal=self.principal, current_original=original,
            current_related_amendments=(), explicit_manual_action=True).allowed)
        self.assertFalse(preview_manual_submission(
            changed, principal=self.principal, current_original=original,
            current_related_amendments=(), explicit_manual_action=False).allowed)

    def test_stale_dependency_review_only_reopens_changed_dependency(self):
        draft = self.allowed()
        original = deepcopy(self.original)
        original["revision"] = "revision-2"
        original["fields"]["notes"] = "new note"
        self.rejects(
            "incomplete_dependency_review", review_changed_baseline, draft,
            principal=self.principal, current_original=original,
            current_related_amendments=(), chosen_values={},
            acknowledged_dependency_fields=[], acknowledged_revision_change=True,
            occurred_at="2026-11-09T14:00:00Z")
        result = review_changed_baseline(
            draft, principal=self.principal, current_original=original,
            current_related_amendments=(), chosen_values={},
            acknowledged_dependency_fields=["notes"], acknowledged_revision_change=True,
            occurred_at="2026-11-09T14:00:00Z")
        self.assertEqual(result.contract.proposed_fields["partyId"], "party-new")
        self.assertEqual(result.review_events[-1].choices,
                         (("notes", "dependency_acknowledged"),))
        self.assertTrue(preview_manual_submission(
            result, principal=self.principal, current_original=original,
            current_related_amendments=(), explicit_manual_action=True).allowed)

    def test_revision_only_re_review_must_be_acknowledged(self):
        draft = self.allowed()
        original = deepcopy(self.original)
        original["revision"] = "revision-2"
        refreshed = review_changed_baseline(
            draft, principal=self.principal, current_original=original,
            current_related_amendments=(), chosen_values={},
            acknowledged_dependency_fields=[], acknowledged_revision_change=True,
            occurred_at="2026-11-09T14:00:00Z")
        self.assertEqual(refreshed.original_revision, "revision-2")
        self.assertEqual(refreshed.review_events[-1].choices, ())
        self.assertTrue(preview_manual_submission(
            refreshed, principal=self.principal, current_original=original,
            current_related_amendments=(), explicit_manual_action=True).allowed)

    def test_changed_related_needs_new_human_field_choices(self):
        draft = self.allowed(related_amendments=self.related,
                             acknowledged_open=True)
        resolved = review_field_choices(
            draft, principal=self.principal,
            chosen_values={"partyId": "party-approved", "quantity": 20},
            occurred_at="2026-11-09T14:00:00Z")
        related = deepcopy(self.related)
        related[0]["revision"] = "amendment-rev-2"
        related[0]["proposedFields"]["quantity"] = 99
        self.rejects(
            "incomplete_field_review", review_changed_baseline, resolved,
            principal=self.principal, current_original=self.original,
            current_related_amendments=related,
            chosen_values={"partyId": "party-approved"},
            acknowledged_dependency_fields=[], acknowledged_revision_change=False,
            occurred_at="2026-11-09T14:00:00Z")
        reviewed = review_changed_baseline(
            resolved, principal=self.principal,
            current_original=self.original, current_related_amendments=related,
            chosen_values={"partyId": "party-approved", "quantity": 20},
            acknowledged_dependency_fields=[], acknowledged_revision_change=False,
            occurred_at="2026-11-09T14:00:00Z")
        self.assertEqual(reviewed.contract.resolutions["quantity"], 20)
        self.assertEqual(reviewed.related_snapshots[0].revision, "amendment-rev-2")
        self.assertTrue(preview_manual_submission(
            reviewed, principal=self.principal, current_original=self.original,
            current_related_amendments=related, explicit_manual_action=True).allowed)
        self.assertEqual(resolved.related_snapshots[0].revision, "amendment-rev-1")

    def test_missing_or_added_baseline_field_is_targeted(self):
        draft = self.allowed()
        changed = deepcopy(self.original)
        changed["fields"].pop("notes")
        changed["fields"]["delivery"] = "pickup"
        result = preview_manual_submission(
            draft, principal=self.principal, current_original=changed,
            current_related_amendments=(), explicit_manual_action=True)
        self.assertEqual(result.affected_fields_to_review, ("delivery", "notes"))

    def test_related_payload_change_detected_without_revision_bump(self):
        draft = self.allowed(related_amendments=self.related,
                             acknowledged_open=True)
        resolved = review_field_choices(
            draft, principal=self.principal,
            chosen_values={"partyId": "party-approved", "quantity": 20},
            occurred_at="2026-11-09T14:00:00Z")
        changed_related = deepcopy(self.related)
        changed_related[0]["proposedFields"]["quantity"] = 55
        result = preview_manual_submission(
            resolved, principal=self.principal, current_original=self.original,
            current_related_amendments=changed_related,
            explicit_manual_action=True)
        self.assertFalse(result.allowed)
        self.assertEqual(result.affected_fields_to_review,
                         ("partyId", "quantity"))
        self.assertIn("changed_related_amendment", result.blocked_by)

    def test_new_conflicting_related_amendment_requires_new_review(self):
        draft = self.allowed()
        result = preview_manual_submission(
            draft, principal=self.principal, current_original=self.original,
            current_related_amendments=self.related, explicit_manual_action=True)
        self.assertFalse(result.allowed)
        self.assertIn("changed_related_amendment", result.blocked_by)
        self.assertIn("unresolved_field_conflicts", result.blocked_by)
        self.assertEqual(result.unresolved_conflict_fields,
                         ("partyId", "quantity"))

    def test_missing_related_record_needs_scoped_review(self):
        draft = self.allowed(related_amendments=self.related,
                             acknowledged_open=True)
        result = preview_manual_submission(
            draft, principal=self.principal, current_original=self.original,
            current_related_amendments=(), explicit_manual_action=True)
        self.assertFalse(result.allowed)
        self.assertEqual(result.affected_fields_to_review,
                         ("partyId", "quantity"))

    def test_rejected_chain_requires_existing_rejected_same_scope(self):
        rejected = deepcopy(self.related)
        rejected[0]["status"] = "rejected"
        new = self.allowed(related_amendments=rejected,
                           previous_rejected_amendment_id="amendment-open-1")
        self.assertEqual(new.contract.previous_rejected_amendment_id,
                         "amendment-open-1")
        self.assertNotEqual(new.contract.amendment_id,
                            new.contract.previous_rejected_amendment_id)
        self.rejects("rejected_reference_not_available",
                     preview_create_amendment, principal=self.principal,
                     original=self.original, amendment_id="amendment-new-2",
                     proposed_fields={"quantity": 40}, related_amendments=self.related,
                     previous_rejected_amendment_id="amendment-open-1")

    def receipt(self, **changes):
        sample = {
            "amendmentId": "amendment-new-2",
            "originalRequestId": "finance-original-1",
            "orgId": "org-a", "projectId": "project-1",
            "status": "rejected", "verifiedTarazSource": True,
            "reason": {"text": "تعداد نیازمند اصلاح است",
                       "affectedFields": ["quantity"], "structured": True},
        }
        sample.update(changes)
        return sample

    def test_verified_rejection_only_explicitly_affected_fields_suggested(self):
        draft = self.allowed()
        result = preview_rejection_guidance(
            draft, principal=self.principal, taraz_rejection=self.receipt())
        self.assertEqual(result.reason_status, "verified_structured_fields")
        self.assertEqual(result.original_request_id, "finance-original-1")
        self.assertEqual(result.rejected_amendment_id, "amendment-new-2")
        self.assertEqual(len(result.suggested_fields), 1)
        suggestion = result.suggested_fields[0]
        self.assertEqual(suggestion.field, "quantity")
        self.assertEqual(suggestion.rejected_previous_value, 10)
        self.assertEqual(suggestion.rejected_proposed_value, 10)
        self.assertIsNone(suggestion.suggested_value)
        self.assertNotIn("partyId", [f.field for f in result.suggested_fields])
        self.assertEqual(result.action, "preview_only")
        self.assertIn("draft_new_independent_amendment", result.next_actions)

    def test_empty_plaintext_and_unknown_rejection_causes_never_guess_fields(self):
        draft = self.allowed()
        variants = (
            {"text": "", "affectedFields": [], "structured": False},
            {"text": None, "affectedFields": [], "structured": False},
            {"text": "تعداد شاید درست نیست", "affectedFields": [],
             "structured": False},
            {"text": "مشکل در سفارش", "affectedFields": ["quantity"],
             "structured": False},
            {"text": "فیلد ناشناخته", "affectedFields": ["unlistedField"],
             "structured": True},
        )
        for reason in variants:
            with self.subTest(reason=reason):
                result = preview_rejection_guidance(
                    draft, principal=self.principal,
                    taraz_rejection=self.receipt(reason=reason))
                self.assertEqual(result.reason_status,
                                 "ambiguous_needs_clarification")
                self.assertEqual(result.suggested_fields, ())
                self.assertIn("manual_complete", result.next_actions)
                self.assertIn("request_finance_clarification",
                              result.next_actions)

    def test_unverified_taraz_or_wrong_org_is_never_accepted(self):
        draft = self.allowed()
        self.rejects("unverified_rejection", preview_rejection_guidance,
                     draft, principal=self.principal, taraz_rejection=self.receipt(
                         verifiedTarazSource=False))
        self.rejects("scope_denied", preview_rejection_guidance,
                     draft, principal=self.principal,
                     taraz_rejection=self.receipt(orgId="org-b"))
        self.rejects("scope_denied", preview_rejection_guidance,
                     draft, principal={**self.principal, "canDraft": False},
                     taraz_rejection=self.receipt())
        self.rejects("scope_denied", preview_rejection_guidance,
                     draft, principal=self.principal,
                     taraz_rejection=self.receipt(amendmentId="foreign-secret"))

    def test_foreign_org_and_foreign_project_related_never_leak(self):
        foreign = deepcopy(self.related)
        foreign[0]["orgId"] = "org-b"
        foreign[0]["amendmentId"] = "foreign-secret"
        foreign[0]["proposedFields"] = {"partyId": "private-party"}
        foreign_project = deepcopy(self.related)
        foreign_project[0]["projectId"] = "project-other"
        foreign_project[0]["amendmentId"] = "hidden-other-project"
        preview = self.create(
            related_amendments=foreign + foreign_project)
        self.assertTrue(preview.allowed)
        self.assertEqual(preview.open_amendment_ids, ())
        self.assertEqual(preview.possible_duplicate_ids, ())
        self.assertEqual(preview.draft.conflicts, ())
        denied_original = {**self.original, "orgId": "org-b"}
        self.rejects("scope_denied", self.create, original=denied_original)
        bad_foreign = {**denied_original, "fields": {"secret": {"nested": "private"}}}
        self.rejects("scope_denied", self.create, original=bad_foreign)
        self.rejects("scope_denied", preview_manual_submission, preview.draft,
                     principal=self.principal,
                     current_original=denied_original,
                     current_related_amendments=foreign,
                     explicit_manual_action=True)
        self.rejects("scope_denied", review_changed_baseline, preview.draft,
                     principal=self.principal, current_original=bad_foreign,
                     current_related_amendments=(), chosen_values={},
                     acknowledged_dependency_fields=[],
                     acknowledged_revision_change=False,
                     occurred_at="2026-11-09T14:00:00Z")

    def test_invalid_ids_flags_fields_and_reused_amendment_ids_rejected(self):
        self.rejects("invalid_amendment_id", self.create,
                     amendment_id="finance-original-1")
        self.rejects("invalid_input", self.create, amendment_id="bad id")
        self.rejects("original_not_submitted", self.create,
                     original={**self.original, "submitted": False})
        self.rejects("invalid_acknowledgment", self.create,
                     acknowledged_duplicate=1)
        self.rejects("invalid_fields", self.create,
                     proposed_fields={"nested": {"finance": 1}})
        self.rejects("missing_baseline_fields", self.create,
                     proposed_fields={"secretField": "x"})
        self.rejects("amendment_id_already_exists", self.create,
                     amendment_id="amendment-open-1",
                     related_amendments=self.related)
        self.rejects("scope_denied", self.create,
                     principal={**self.principal, "canDraft": False})
        self.rejects("scope_denied", self.create,
                     principal={**self.principal, "projectIds": []})

    def test_snapshot_not_affected_by_caller_mutation_and_zero_io(self):
        related = deepcopy(self.related)
        original = deepcopy(self.original)
        with patch.object(socket, "socket",
                          side_effect=AssertionError("network forbidden")), \
             patch("builtins.open",
                   side_effect=AssertionError("disk forbidden")):
            draft = self.allowed(original=original, related_amendments=related,
                                 acknowledged_open=True)
            first = preview_manual_submission(
                draft, principal=self.principal, current_original=original,
                current_related_amendments=related, explicit_manual_action=True)
        self.assertIn("unresolved_field_conflicts", first.blocked_by)
        related[0]["proposedFields"]["partyId"] = "altered"
        original["fields"]["quantity"] = 99
        self.assertEqual(draft.contract.baseline["quantity"], 10)
        self.assertEqual(draft.related_snapshots[0].proposed_fields["partyId"],
                         "party-other")
        with self.assertRaises(TypeError):
            draft.related_snapshots[0].proposed_fields["partyId"] = "hijack"


if __name__ == "__main__":
    unittest.main()
