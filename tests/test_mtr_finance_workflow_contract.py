"""Synthetic, offline tests for the Madar/Taraz design-domain safety slice.

No filesystem profile, running service, actual Taraz DB or financial posting.
"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mtr_finance_workflow_contract import (  # noqa: E402
    ConfirmationRequired,
    WorkflowContractError,
    create_amendment_draft,
    evaluate_manual_submission,
    recovery_action,
    resolve_conflict_fields,
)


def draft(**overrides):
    props = {
        "amendment_id": "amendment-002",
        "original_request_id": "finance-original-001",
        "created_by": "authorized-editor",
        "authorized": True,
        "proposed_fields": {"partyId": "party-new"},
        "baseline": {"partyId": "party-original", "quantity": 10},
    }
    props.update(overrides)
    return create_amendment_draft(**props)


class AmendmentCreationTests(unittest.TestCase):
    def test_creates_independent_identifier_and_original_reference(self):
        item = draft()
        self.assertEqual(item.amendment_id, "amendment-002")
        self.assertEqual(item.original_request_id, "finance-original-001")
        self.assertNotEqual(item.amendment_id, item.original_request_id)
        self.assertEqual(item.proposed_fields["partyId"], "party-new")

    def test_rejected_amendment_link_is_separate(self):
        item = draft(previous_rejected_amendment_id="amendment-rejected-001")
        self.assertEqual(item.previous_rejected_amendment_id, "amendment-rejected-001")
        self.assertEqual(item.original_request_id, "finance-original-001")

    def test_refuses_to_reuse_original_identifier(self):
        with self.assertRaises(WorkflowContractError):
            draft(amendment_id="finance-original-001")

    def test_refuses_unauthorized_creation(self):
        with self.assertRaises(PermissionError):
            draft(authorized=False)

    def test_open_amendment_needs_explicit_confirmation(self):
        with self.assertRaises(ConfirmationRequired):
            draft(open_amendment_exists=True)
        item = draft(open_amendment_exists=True, acknowledged_open_amendment=True)
        self.assertEqual(item.amendment_id, "amendment-002")

    def test_possible_duplicate_needs_a_separate_confirmation(self):
        with self.assertRaises(ConfirmationRequired):
            draft(similar_amendment_exists=True)
        self.assertEqual(
            draft(similar_amendment_exists=True, acknowledged_similar_amendment=True).amendment_id,
            "amendment-002",
        )

    def test_open_confirmation_does_not_waive_duplicate_confirmation(self):
        with self.assertRaises(ConfirmationRequired):
            draft(open_amendment_exists=True, acknowledged_open_amendment=True,
                  similar_amendment_exists=True)
        self.assertTrue(draft(open_amendment_exists=True, acknowledged_open_amendment=True,
                              similar_amendment_exists=True,
                              acknowledged_similar_amendment=True))

    def test_requires_baseline_of_every_proposed_field(self):
        with self.assertRaises(WorkflowContractError):
            draft(proposed_fields={"unknown": "value"})

    def test_conflict_field_cannot_reference_unrelated_field(self):
        with self.assertRaises(WorkflowContractError):
            draft(conflicting_fields=frozenset({"unrelated"}))

    def test_copies_inputs_and_does_not_modify_original_data(self):
        original = {"partyId": "party-original", "status": "approved"}
        baseline = {"partyId": original["partyId"]}
        proposed = {"partyId": "party-new"}
        item = draft(baseline=baseline, proposed_fields=proposed)
        baseline["partyId"] = "external-mutation"
        proposed["partyId"] = "external-mutation"
        self.assertEqual(item.baseline["partyId"], "party-original")
        self.assertEqual(item.proposed_fields["partyId"], "party-new")
        with self.assertRaises(TypeError):
            item.proposed_fields["partyId"] = "tamper"
        self.assertEqual(original, {"partyId": "party-original", "status": "approved"})


class ConflictAndVersionTests(unittest.TestCase):
    def test_unresolved_conflict_blocks_manual_submission(self):
        item = draft(conflicting_fields=frozenset({"partyId"}))
        gate = evaluate_manual_submission(item, authorized=True, explicit_manual_action=True,
                                          current_baseline=dict(item.baseline))
        self.assertFalse(gate.allowed)
        self.assertIn("unresolved_field_conflicts", gate.blocked_by)

    def test_unauthorized_review_is_rejected(self):
        item = draft(conflicting_fields=frozenset({"partyId"}))
        with self.assertRaises(PermissionError):
            resolve_conflict_fields(item, authorized=False,
                                    chosen_values={"partyId": "party-final"})

    def test_approved_review_does_not_mutate_prior_draft(self):
        item = draft(conflicting_fields=frozenset({"partyId"}))
        after = resolve_conflict_fields(item, authorized=True,
                                        chosen_values={"partyId": "party-final"})
        self.assertEqual(item.proposed_fields["partyId"], "party-new")
        self.assertEqual(dict(item.resolutions), {})
        self.assertEqual(after.proposed_fields["partyId"], "party-final")
        self.assertEqual(after.resolutions["partyId"], "party-final")

    def test_cannot_resolve_a_field_that_is_not_in_conflict(self):
        with self.assertRaises(WorkflowContractError):
            resolve_conflict_fields(draft(), authorized=True,
                                    chosen_values={"partyId": "other"})

    def test_reviewed_draft_does_not_send_itself(self):
        item = resolve_conflict_fields(
            draft(conflicting_fields=frozenset({"partyId"})),
            authorized=True, chosen_values={"partyId": "party-final"})
        gate = evaluate_manual_submission(item, authorized=True,
                                          explicit_manual_action=False,
                                          current_baseline=dict(item.baseline))
        self.assertFalse(gate.allowed)
        self.assertIn("manual_send_action_required", gate.blocked_by)

    def test_authorized_manual_resolved_draft_passes_pure_gate(self):
        item = resolve_conflict_fields(
            draft(conflicting_fields=frozenset({"partyId"})),
            authorized=True, chosen_values={"partyId": "party-final"})
        gate = evaluate_manual_submission(item, authorized=True,
                                          explicit_manual_action=True,
                                          current_baseline=dict(item.baseline))
        self.assertTrue(gate.allowed)
        self.assertEqual(gate.blocked_by, ())

    def test_permission_remains_required_at_submission(self):
        item = draft()
        gate = evaluate_manual_submission(item, authorized=False,
                                          explicit_manual_action=True,
                                          current_baseline=dict(item.baseline))
        self.assertFalse(gate.allowed)
        self.assertIn("not_authorized", gate.blocked_by)

    def test_stale_baseline_reopens_only_affected_field(self):
        item = draft()
        gate = evaluate_manual_submission(item, authorized=True,
                                          explicit_manual_action=True,
                                          current_baseline={"partyId": "party-another", "quantity": 10})
        self.assertFalse(gate.allowed)
        self.assertEqual(gate.affected_fields_to_review, ("partyId",))
        self.assertIn("stale_baseline_requires_review", gate.blocked_by)

    def test_unrelated_current_field_does_not_require_rechecking_all_fields(self):
        item = draft()
        gate = evaluate_manual_submission(item, authorized=True,
                                          explicit_manual_action=True,
                                          current_baseline={"partyId": "party-original",
                                                            "quantity": 10, "untrackedField": "changed"})
        self.assertTrue(gate.allowed)
        self.assertEqual(gate.affected_fields_to_review, ())

    def test_missing_dependent_field_is_stale(self):
        item = draft()
        gate = evaluate_manual_submission(item, authorized=True,
                                          explicit_manual_action=True,
                                          current_baseline={"partyId": "party-original"})
        self.assertFalse(gate.allowed)
        self.assertEqual(gate.affected_fields_to_review, ("quantity",))


class ReceiptRecoveryTests(unittest.TestCase):
    @staticmethod
    def recovery(**overrides):
        args = {"receipt_state": "unknown", "original_send_authorized": True,
                "same_request_and_payload": True, "same_idempotency_key": True}
        args.update(overrides)
        return recovery_action(**args)

    def test_unknown_receipt_is_held_not_replayed(self):
        self.assertEqual(self.recovery(), "hold_uncertain")

    def test_received_returns_existing_receipt_only(self):
        self.assertEqual(self.recovery(receipt_state="received"), "recover_receipt")

    def test_confirmed_not_received_allows_same_send_only(self):
        self.assertEqual(self.recovery(receipt_state="not_received"), "replay_same_send")

    def test_new_payload_must_not_reuse_prior_approval(self):
        self.assertEqual(self.recovery(receipt_state="not_received",
                                       same_request_and_payload=False), "hold_mismatched_request")

    def test_new_idempotency_key_must_not_reuse_prior_approval(self):
        self.assertEqual(self.recovery(receipt_state="not_received",
                                       same_idempotency_key=False), "hold_mismatched_request")

    def test_no_prior_manual_approval_refuses_replay(self):
        self.assertEqual(self.recovery(receipt_state="not_received",
                                       original_send_authorized=False), "hold_no_approval")

    def test_unrecognized_receipt_state_is_rejected(self):
        with self.assertRaises(WorkflowContractError):
            self.recovery(receipt_state="approved")


if __name__ == "__main__":
    unittest.main()
