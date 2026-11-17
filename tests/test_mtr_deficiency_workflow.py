"""Pure offline safety tests for approved Refine 6.6-6.8 and AC-08..10."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mtr_deficiency_workflow import (  # noqa: E402
    AuditEvent,
    AssignedDeficiency,
    Baseline,
    DeficiencyError,
    FinanceReceipt,
    ManualResubmissionIntent,
    Principal,
    ReadyForManualResubmission,
    ReviewCase,
    authorize_manual_resubmission,
    refer_deficiency,
    resolve_deficiency,
)


T0 = datetime(2026, 11, 9, 10, tzinfo=timezone.utc)
DIGEST1 = "a" * 64
DIGEST2 = "b" * 64
DIGEST3 = "c" * 64
REVIEW = "finance_deficiency_refer"
FIX = "deficiency_resolve"
SEND = "finance_request_resubmit"


def principal(user_id="finance", *, org="org-1", role="taraz_finance_reviewer",
              projects=None, capabilities=None, authenticated=True, active=True):
    return Principal(
        user_id=user_id, org_id=org, role=role,
        projects=frozenset({"project-1"} if projects is None else projects),
        capabilities=frozenset({REVIEW} if capabilities is None else capabilities),
        authenticated=authenticated, active=active,
    )


def baseline(*, revision=3, digest=DIGEST1, request_id="req-1", org="org-1",
             project="project-1"):
    return Baseline(request_id, org, project, revision, digest)


def case(**overrides):
    values = dict(
        baseline=baseline(), expected_receipt_id="taraz-receipt-3",
        expected_receipt_generation=7,
        previous_receipt_ids=frozenset({"old-receipt"}),
        previous_send_keys=frozenset({"initial-send-key"}),
    )
    values.update(overrides)
    return ReviewCase(**values)


def receipt(**overrides):
    values = dict(
        receipt_id="taraz-receipt-3", request_id="req-1", org_id="org-1",
        project_id="project-1", revision=3, digest=DIGEST1, generation=7,
        status="deficiency_required", source="taraz",
        verified_by_adapter=True, occurred_at=T0,
    )
    values.update(overrides)
    return FinanceReceipt(**values)


def reviewer(**overrides):
    return principal(**overrides)


def assignee(**overrides):
    defaults = {"role": "madar_operator", "capabilities": {FIX}}
    defaults.update(overrides)
    return principal("assignee", **defaults)


def sender(**overrides):
    defaults = {"role": "madar_operator", "capabilities": {SEND}}
    defaults.update(overrides)
    return principal("sender", **defaults)


def refer(**overrides):
    args = dict(
        case=case(), receipt=receipt(), reviewer=reviewer(),
        assignee=assignee(), deadline=T0 + timedelta(days=2),
        reason="Missing supplier detail", missing_fields=frozenset({"supplier", "units"}),
        event_id="event-assign", occurred_at=T0 + timedelta(minutes=1),
    )
    args.update(overrides)
    return refer_deficiency(**args)


def resolve(**overrides):
    args = dict(
        assigned=refer(), actor=assignee(),
        corrections={"supplier": "supplier-x", "units": "5"},
        result_note="Saved updated project values",
        saved_baseline=baseline(revision=4, digest=DIGEST2),
        event_id="event-resolve", occurred_at=T0 + timedelta(minutes=5),
    )
    args.update(overrides)
    return resolve_deficiency(**args)


def manual(**overrides):
    args = dict(
        ready=resolve(), actor=sender(), explicit_manual_action=True,
        current_server_baseline=baseline(revision=4, digest=DIGEST2),
        server_revalidated=True, new_send_key="second-approved-send",
        warning_acknowledged=False, event_id="event-resubmit",
        occurred_at=T0 + timedelta(minutes=6),
    )
    args.update(overrides)
    return authorize_manual_resubmission(**args)


class HappyPathTests(unittest.TestCase):
    def test_finance_refers_authorized_person_with_reason_due_and_audit(self):
        original = case()
        item = refer(case=original)
        self.assertIsInstance(item, AssignedDeficiency)
        self.assertEqual(item.state, "DEFICIENCY_ASSIGNED")
        self.assertEqual(item.reviewer_id, "finance")
        self.assertEqual(item.assignee_id, "assignee")
        self.assertEqual(item.deadline, T0 + timedelta(days=2))
        self.assertEqual(item.reason, "Missing supplier detail")
        self.assertEqual(item.missing_fields, frozenset({"supplier", "units"}))
        self.assertEqual(item.audit[-1].actor_id, "finance")
        self.assertEqual(item.audit[-1].action, "deficiency_referred")
        self.assertEqual(dict(item.audit[-1].details)["receipt_id"], "taraz-receipt-3")
        self.assertEqual(original.audit, ())
        self.assertNotIn("taraz-receipt-3", original.previous_receipt_ids)
        self.assertIn("taraz-receipt-3", item.review.previous_receipt_ids)

    def test_assignee_resolution_creates_new_ready_state_with_audit_no_send(self):
        item = refer()
        result = resolve(assigned=item)
        self.assertIsInstance(result, ReadyForManualResubmission)
        self.assertEqual(result.state, "CORRECTED_READY_FOR_RESUBMIT")
        self.assertEqual(result.corrections, (("supplier", "supplier-x"), ("units", "5")))
        self.assertEqual(result.audit[-1].actor_id, "assignee")
        self.assertEqual(result.audit[-1].action, "deficiency_corrected_ready_only")
        self.assertEqual(item.state, "DEFICIENCY_ASSIGNED")
        self.assertEqual(item.audit[-1].action, "deficiency_referred")
        self.assertFalse(hasattr(result, "sent_to_taraz"))

    def test_only_manual_action_creates_untransmitted_intent(self):
        ready = resolve()
        intent = manual(ready=ready)
        self.assertIsInstance(intent, ManualResubmissionIntent)
        self.assertEqual(intent.state, "MANUAL_RESUBMISSION_INTENT_ONLY")
        self.assertFalse(intent.sent_to_taraz)
        self.assertFalse(intent.financial_event_created)
        self.assertEqual(intent.authorized_actor_id, "sender")
        self.assertEqual(intent.new_send_key, "second-approved-send")
        self.assertEqual([e.action for e in intent.audit], [
            "deficiency_referred",
            "deficiency_corrected_ready_only",
            "manual_resubmission_intent_only",
        ])
        self.assertEqual(ready.state, "CORRECTED_READY_FOR_RESUBMIT")

    def test_finance_may_assign_different_authorized_person_not_original_creator(self):
        new_person = principal(
            "another-assignee", role="madar_user",
            capabilities={FIX}, authenticated=False,
        )
        assigned = refer(assignee=new_person)
        self.assertEqual(assigned.assignee_id, "another-assignee")
        new_person_session = replace(new_person, authenticated=True)
        corrected = resolve(assigned=assigned, actor=new_person_session)
        self.assertEqual(corrected.audit[-1].actor_id, "another-assignee")

    def test_incomplete_business_data_allowed_only_with_warning_after_manual_action(self):
        ready = resolve(corrections={"supplier": "supplier-x"})
        self.assertEqual(ready.remaining_missing_fields, frozenset({"units"}))
        with self.assertRaisesRegex(DeficiencyError, "warning"):
            manual(ready=ready)
        intent = manual(ready=ready, warning_acknowledged=True)
        self.assertFalse(intent.sent_to_taraz)
        self.assertIn(
            ("incomplete_warning_acknowledged", "yes"),
            intent.audit[-1].details,
        )

    def test_deterministic_immutable_copy_and_original_context_unchanged(self):
        result = resolve()
        with self.assertRaises(FrozenInstanceError):
            result.state = "SENT"
        with self.assertRaises(FrozenInstanceError):
            result.corrected_baseline.revision = 100
        with self.assertRaises(TypeError):
            result.corrections[0] = ("units", "1000")
        input_values = {"supplier": "original"}
        out = resolve(corrections=input_values)
        input_values["supplier"] = "evil-change"
        self.assertEqual(out.corrections, (("supplier", "original"),))


class ReferralDenialTests(unittest.TestCase):
    def test_non_finance_role_cannot_refer_even_with_capability(self):
        with self.assertRaisesRegex(PermissionError, "finance reviewer"):
            refer(reviewer=reviewer(role="madar_admin"))

    def test_unauthed_inactive_or_unprivileged_finance_reviewer_denied(self):
        for actor in (
            reviewer(authenticated=False),
            reviewer(active=False),
            reviewer(capabilities=set()),
        ):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                refer(reviewer=actor)

    def test_reviewer_cannot_access_other_org_or_project(self):
        for actor in (
            reviewer(org="org-other"),
            reviewer(projects={"unrelated-project"}),
        ):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                refer(reviewer=actor)

    def test_assignee_must_be_active_authorized_same_org_and_project(self):
        for actor in (
            assignee(active=False),
            assignee(org="other-org"),
            assignee(projects={"project-b"}),
            assignee(capabilities=set()),
        ):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                refer(assignee=actor)

    def test_pending_review_denied_regardless_of_finance_reviewer(self):
        with self.assertRaisesRegex(DeficiencyError, "pending"):
            refer(case=case(review_state="AWAITING_FINANCE_REVIEW"))
        with self.assertRaisesRegex(DeficiencyError, "receipt"):
            refer(receipt=receipt(status="pending_review"))

    def test_unverified_or_non_taraz_or_wrong_state_receipt_denied(self):
        for proposal in (
            receipt(verified_by_adapter=False),
            receipt(source="madar"),
            receipt(status="approved"),
            receipt(status="rejected"),
            receipt(status="unknown"),
        ):
            with self.subTest(receipt=proposal), self.assertRaisesRegex(
                DeficiencyError, "verified"
            ):
                refer(receipt=proposal)

    def test_duplicate_stale_generation_unexpected_id_denied(self):
        for item, proof in (
            (case(previous_receipt_ids=frozenset({"taraz-receipt-3"})), receipt()),
            (case(), receipt(generation=6)),
            (case(), receipt(generation=8)),
            (case(), receipt(receipt_id="other-receipt")),
            (case(expected_receipt_id="old-receipt",
                  previous_receipt_ids=frozenset({"old-receipt"})),
             receipt(receipt_id="old-receipt")),
        ):
            with self.subTest(item=item, receipt=proof), self.assertRaisesRegex(
                DeficiencyError, "duplicate|stale|unexpected"
            ):
                refer(case=item, receipt=proof)

    def test_receipt_request_org_project_revision_digest_must_match_exactly(self):
        for bad in (
            receipt(request_id="another-request"),
            receipt(org_id="org-b"),
            receipt(project_id="project-b"),
            receipt(revision=2),
            receipt(revision=4),
            receipt(digest=DIGEST3),
        ):
            with self.subTest(bad=bad), self.assertRaisesRegex(
                DeficiencyError, "does not match"
            ):
                refer(receipt=bad)

    def test_future_receipt_or_nonfuture_deadline_denied(self):
        with self.assertRaisesRegex(DeficiencyError, "time"):
            refer(receipt=receipt(occurred_at=T0 + timedelta(hours=1)))
        for due in (T0, T0 + timedelta(minutes=1), T0 - timedelta(minutes=1)):
            with self.subTest(deadline=due), self.assertRaisesRegex(
                DeficiencyError, "deadline"
            ):
                refer(deadline=due)

    def test_bad_deadline_reason_and_empty_missing_fields_denied(self):
        for deadline in (None, datetime(2026, 11, 9, 12)):
            with self.subTest(deadline=deadline), self.assertRaises(DeficiencyError):
                refer(deadline=deadline)
        for reason in ("", " ", "bad\nreason"):
            with self.subTest(reason=reason), self.assertRaises(DeficiencyError):
                refer(reason=reason)
        with self.assertRaisesRegex(DeficiencyError, "missing field"):
            refer(missing_fields=frozenset())
        with self.assertRaises(DeficiencyError):
            refer(missing_fields={"supplier"})

    def test_repeat_referral_or_audit_event_cannot_reuse_history(self):
        assigned = refer()
        with self.assertRaisesRegex(DeficiencyError, "case"):
            refer(case=assigned)
        with self.assertRaisesRegex(DeficiencyError, "duplicate|stale|unexpected"):
            refer(case=assigned.review, receipt=assigned.receipt, event_id="new-event")
        initial = case(audit=(AuditEvent(
            "event-assign", "finance", "prior", T0,
            (("source", "old-event"),),
        ),))
        with self.assertRaisesRegex(DeficiencyError, "duplicate audit"):
            refer(case=initial)

    def test_missing_or_unexpected_inputs_fail_closed(self):
        with self.assertRaises(DeficiencyError):
            refer(receipt=None)
        with self.assertRaises(PermissionError):
            refer(reviewer=None)
        with self.assertRaises(DeficiencyError):
            refer(occurred_at="tomorrow")


class ResolutionDenialTests(unittest.TestCase):
    def test_cross_user_cannot_resolve_even_with_resolve_capability(self):
        with self.assertRaisesRegex(PermissionError, "assigned user"):
            resolve(actor=principal(
                "another-user", role="madar_operator", capabilities={FIX}
            ))

    def test_resolver_must_be_active_authenticated_scoped_and_capable(self):
        for actor in (
            assignee(authenticated=False), assignee(active=False),
            assignee(org="other-org"), assignee(projects={"unrelated"}),
            assignee(capabilities=set()),
        ):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                resolve(actor=actor)

    def test_resolve_before_assignment_or_after_already_ready_denied(self):
        with self.assertRaisesRegex(DeficiencyError, "assigned"):
            resolve(assigned=case())
        with self.assertRaisesRegex(DeficiencyError, "assigned"):
            resolve(assigned=resolve())

    def test_empty_or_unrelated_corrections_and_bad_results_denied(self):
        for corrections in (
            {}, {"account": "123"}, {"supplier": ""}, {"supplier": "x\ninvalid"},
        ):
            with self.subTest(corrections=corrections), self.assertRaises(DeficiencyError):
                resolve(corrections=corrections)
        for note in ("", " ", "bad\nnote"):
            with self.subTest(note=note), self.assertRaises(DeficiencyError):
                resolve(result_note=note)

    def test_baseline_must_be_newer_changed_and_same_case(self):
        for snapshot in (
            baseline(revision=3, digest=DIGEST2),
            baseline(revision=2, digest=DIGEST2),
            baseline(revision=4, digest=DIGEST1),
            baseline(revision=4, digest=DIGEST2, request_id="other"),
            baseline(revision=4, digest=DIGEST2, org="org-other"),
            baseline(revision=4, digest=DIGEST2, project="other"),
        ):
            with self.subTest(snapshot=snapshot), self.assertRaisesRegex(
                DeficiencyError, "baseline|different"
            ):
                resolve(saved_baseline=snapshot)

    def test_resolution_audit_is_monotonic_and_event_unique(self):
        with self.assertRaisesRegex(DeficiencyError, "duplicate"):
            resolve(event_id="event-assign")
        with self.assertRaisesRegex(DeficiencyError, "predates"):
            resolve(occurred_at=T0)
        with self.assertRaises(DeficiencyError):
            resolve(occurred_at=datetime(2026, 11, 9, 11))


class ManualActionDenialTests(unittest.TestCase):
    def test_cannot_submit_directly_from_finance_review_or_assignment(self):
        for value in (case(), refer()):
            with self.subTest(type=type(value).__name__), self.assertRaisesRegex(
                DeficiencyError, "not corrected"
            ):
                manual(ready=value)

    def test_manual_action_is_required_not_truthy(self):
        for explicit in (False, 0, 1, None):
            with self.subTest(explicit=explicit), self.assertRaises(PermissionError):
                manual(explicit_manual_action=explicit)

    def test_server_revalidation_is_required_not_truthy(self):
        for verified in (False, 0, 1, None):
            with self.subTest(verified=verified), self.assertRaisesRegex(
                DeficiencyError, "server"
            ):
                manual(server_revalidated=verified)

    def test_sender_must_be_authenticated_active_in_org_and_project(self):
        for actor in (
            sender(authenticated=False), sender(active=False),
            sender(org="org-other"), sender(projects={"project-other"}),
            sender(capabilities=set()),
        ):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                manual(actor=actor)

    def test_sender_can_be_another_authorized_user_not_necessarily_assignee(self):
        result = manual()
        self.assertEqual(result.authorized_actor_id, "sender")
        self.assertNotEqual(result.authorized_actor_id, result.ready.assigned.assignee_id)

    def test_stale_changed_cross_tenant_or_wrong_current_baseline_denied(self):
        for current in (
            baseline(),  # original stale
            baseline(revision=4, digest=DIGEST3),
            baseline(revision=5, digest=DIGEST2),
            baseline(revision=4, digest=DIGEST2, request_id="other"),
            baseline(revision=4, digest=DIGEST2, org="other"),
            baseline(revision=4, digest=DIGEST2, project="other"),
        ):
            with self.subTest(current=current), self.assertRaisesRegex(
                DeficiencyError, "baseline"
            ):
                manual(current_server_baseline=current)

    def test_send_key_must_be_new_valid_and_not_already_sent(self):
        for key in ("initial-send-key", "", " \t", "new\nkey"):
            with self.subTest(key=key), self.assertRaises(DeficiencyError):
                manual(new_send_key=key)

    def test_warning_acknowledgment_cannot_be_skipped_or_faked_by_truthy_int(self):
        ready = resolve(corrections={"supplier": "fixed"})
        for acknowledged in (False, None, 0, 1):
            with self.subTest(value=acknowledged), self.assertRaisesRegex(
                DeficiencyError, "warning"
            ):
                manual(ready=ready, warning_acknowledged=acknowledged)

    def test_manual_action_audit_event_unique_and_after_resolution(self):
        with self.assertRaisesRegex(DeficiencyError, "duplicate"):
            manual(event_id="event-resolve")
        with self.assertRaisesRegex(DeficiencyError, "predates"):
            manual(occurred_at=T0 + timedelta(minutes=2))


class SchemaValidationTests(unittest.TestCase):
    def test_boolean_revision_or_invalid_digest_denied(self):
        for version in (True, False, 0, -1, "3"):
            with self.subTest(revision=version), self.assertRaises(DeficiencyError):
                baseline(revision=version)
        for fingerprint in ("ABC", "B" * 64, "f" * 63, "g" * 64):
            with self.subTest(digest=fingerprint), self.assertRaises(DeficiencyError):
                baseline(digest=fingerprint)

    def test_receipt_timestamp_and_provenance_flags_must_be_well_typed(self):
        with self.assertRaises(DeficiencyError):
            receipt(occurred_at=datetime(2026, 11, 9, 12))
        with self.assertRaises(DeficiencyError):
            receipt(verified_by_adapter=1)
        with self.assertRaises(DeficiencyError):
            receipt(generation=0)

    def test_principal_grants_must_be_immutable_and_auth_explicit_bool(self):
        with self.assertRaises(DeficiencyError):
            Principal(
                "finance", "org-1", "taraz_finance_reviewer",
                {"project-1"}, frozenset({REVIEW}), True,
            )
        with self.assertRaises(DeficiencyError):
            principal(authenticated=1)
        with self.assertRaises(DeficiencyError):
            principal(active=1)

    def test_invalid_review_state_and_duplicate_audit_input_denied(self):
        with self.assertRaises(DeficiencyError):
            case(review_state="APPROVED")
        duplicate = AuditEvent("same", "actor", "init", T0, (("source", "seed"),))
        with self.assertRaisesRegex(DeficiencyError, "duplicate audit"):
            case(audit=(duplicate, duplicate))


if __name__ == "__main__":
    unittest.main()
