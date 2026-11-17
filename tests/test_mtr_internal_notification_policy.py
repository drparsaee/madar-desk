"""Synthetic E6 policy tests. No Taraz, real profiles, delivery, or I/O."""
from __future__ import annotations

from copy import deepcopy
import socket
import unittest
from unittest.mock import patch

from mtr_internal_notification_policy import (
    plan_internal_notifications,
    summarize_amendments,
)


ORG = "synthetic-org-a"
PROJECT = "synthetic-project-1"
ORIGINAL_ID = "request-a1"
SCOPE = {
    "organization_id": ORG,
    "server_scoped": True,
    "actor_authenticated": True,
    "actor_authorized": True,
    "actor_id": "operator-1",
    "actor_role": "editor",
    "readable_project_ids": [PROJECT],
    "visible_fields": ["status", "amendment_id", "deficiency_summary", "actor_id", "reference"],
    "notify_authorized": True,
    "dedup_snapshot_trusted": True,
    "authoritative_revision": 4,
}
ORIGINAL = {
    "organization_id": ORG, "project_id": PROJECT,
    "server_read_authorized": True, "request_id": ORIGINAL_ID,
    "official_status": "UNDER_FINANCE_REVIEW",
    "official_status_source": "taraz",
    "official_status_server_trusted": True,
}
EVENT = {
    "organization_id": ORG, "project_id": PROJECT,
    "server_read_authorized": True, "server_event_trusted": True,
    "event_key": "event-4", "original_request_id": ORIGINAL_ID,
    "event_kind": "amendment_status_changed", "amendment_id": "amendment-a1",
    "previous_status": "AWAITING_RECEIPT", "status": "UNDER_FINANCE_REVIEW",
    "previous_revision": 3, "revision": 4,
    "actor_id": "finance-reviewer-1", "occurred_at": "2026-11-09T12:00:00Z",
}


def recipient(identifier, **updates):
    return {
        "user_id": identifier, "organization_id": ORG, "role": "viewer",
        "server_read_authorized": True, "readable_project_ids": [PROJECT],
        "related_request_ids": [ORIGINAL_ID], "internal_notifications_enabled": True,
        "visible_fields": ["status", "amendment_id", "actor_id"],
        **updates,
    }


def amendment(identifier, initial_status, **updates):
    return {
        "amendment_id": identifier,
        "organization_id": ORG,
        "project_id": PROJECT,
        "server_read_authorized": True,
        "original_request_id": ORIGINAL_ID,
        "status": initial_status,
        "status_source": "taraz",
        "status_source_trusted": True,
        "status_updated_at": "2026-11-09T12:00:00Z",
        "visible_fields": ["status", "amendment_id", "reference", "actor_id"],
        "receipt_reference": None,
        **updates,
    }


def reference(linked_amendment_id, **updates):
    return {
        "reference_id": "taraz-receipt-synthetic-1",
        "reference_kind": "receipt",
        "organization_id": ORG, "project_id": PROJECT,
        "amendment_id": linked_amendment_id, "source_system": "taraz",
        "source_actor_id": "taraz-finance-1",
        "received_at": "2026-11-09T12:01:00Z",
        "server_supplied": True,
        "source_actor_verified": True,
        "source_provenance_verified": True,
        "correlation_verified": True,
        **updates,
    }


class NotificationPolicyTests(unittest.TestCase):
    def plan(self, recipients, *, event=None, scope=None, seen=()):
        return plan_internal_notifications(
            EVENT if event is None else event, recipients,
            scope=SCOPE if scope is None else scope, seen_event_keys=seen,
        )

    def test_meaningful_amendment_event_notifies_only_authorized_related_same_project(self):
        result = self.plan([
            recipient("relevant-viewer"),
            recipient("relevant-editor", role="editor"),
            recipient("other-project", readable_project_ids=["other-project"]),
            recipient("unrelated", related_request_ids=["other-request"]),
            recipient("opted-out", internal_notifications_enabled=False),
        ])
        self.assertEqual([n["recipient_id"] for n in result["notifications"]],
                         ["relevant-viewer", "relevant-editor"])
        self.assertTrue(all(n["channel"] == "internal_only" for n in result["notifications"]))
        self.assertEqual(result["notifications"][0]["status"], "UNDER_FINANCE_REVIEW")
        self.assertEqual(result["notifications"][0]["amendment_id"], "amendment-a1")
        self.assertEqual(result["external_deliveries"], [])
        self.assertFalse(result["send_or_resend_performed"])
        self.assertFalse(result["any_mutation_performed"])

    def test_repeat_event_key_suppresses_every_notice_without_mutating_seen_keys(self):
        seen = frozenset({"event-4"})
        result = self.plan([recipient("viewer")], seen=seen)
        self.assertTrue(result["duplicate_event"])
        self.assertTrue(result["meaningful_change"])
        self.assertEqual(result["notifications"], [])
        self.assertEqual(seen, frozenset({"event-4"}))

    def test_noop_status_change_never_notifies(self):
        event = {**EVENT, "previous_status": "UNDER_FINANCE_REVIEW",
                 "event_kind": "request_status_changed"}
        result = self.plan([recipient("reader")], event=event)
        self.assertEqual(result["notifications"], [])
        self.assertFalse(result["meaningful_change"])

    def test_deficiency_assigned_is_internal_only_and_field_redacted_for_viewer(self):
        event = {
            **EVENT, "event_kind": "deficiency_assigned",
            "status": "DEFICIENCY_ASSIGNED",
            "assigned_user_id": "selected-operator",
            "deficiency_summary": "PRIVATE-DEFICIENCY",
        }
        result = self.plan([
            recipient("selected-operator", visible_fields=["status", "deficiency_summary"]),
            recipient("viewer-limited", visible_fields=["status"]),
        ], event=event)
        one, two = result["notifications"]
        self.assertEqual(one["deficiency_summary"], "PRIVATE-DEFICIENCY")
        self.assertIsNone(two["deficiency_summary"])
        self.assertIsNone(two["actor_id"])
        self.assertIsNone(two["amendment_id"])
        self.assertNotIn("PRIVATE-DEFICIENCY", repr(two))
        self.assertFalse(result["send_or_resend_performed"])

    def test_unknown_or_stale_event_revision_or_status_fails_closed(self):
        for revision in (0, 3, True, None):
            with self.subTest(revision=revision), self.assertRaises(PermissionError):
                self.plan([recipient("viewer")], event={**EVENT, "revision": revision})
        with self.assertRaises(PermissionError):
            self.plan([recipient("viewer")], scope={**SCOPE, "authoritative_revision": 5})
        with self.assertRaises(ValueError):
            self.plan([recipient("viewer")], event={**EVENT, "status": "UNKNOWN_SUCCESS"})
        with self.assertRaises(ValueError):
            self.plan([recipient("viewer")], event={**EVENT, "event_kind": "external_sms"})

    def test_unknown_scope_role_auth_dedup_snapshot_or_acl_fails_closed(self):
        for changes in (
            {"server_scoped": False},
            {"actor_authenticated": False},
            {"actor_authorized": False},
            {"actor_role": "unknown"},
            {"actor_role": []},
            {"organization_id": ""},
            {"readable_project_ids": []},
            {"notify_authorized": False},
            {"dedup_snapshot_trusted": False},
            {"visible_fields": ["secret_ledger"]},
        ):
            with self.subTest(changes=changes), self.assertRaises(PermissionError):
                self.plan([recipient("viewer")], scope={**SCOPE, **changes})
        for missing in ("server_scoped", "actor_id", "actor_role",
                        "readable_project_ids", "dedup_snapshot_trusted"):
            with self.subTest(missing=missing):
                scope = {k: v for k, v in SCOPE.items() if k != missing}
                with self.assertRaises((PermissionError, ValueError)):
                    self.plan([recipient("viewer")], scope=scope)

    def test_mixed_tenant_or_unknown_recipient_causes_no_partial_response(self):
        for bad in (
            recipient("foreign", organization_id="other-org"),
            recipient("unverified", server_read_authorized=False),
            recipient("unknown-role", role="accounting-god"),
            recipient("unknown-projects", readable_project_ids=None),
        ):
            with self.subTest(bad=bad["user_id"]), self.assertRaises(PermissionError):
                self.plan([recipient("allowed"), bad])
        with self.assertRaises(PermissionError):
            self.plan([recipient("allowed")],
                      event={**EVENT, "organization_id": "other-org"})
        with self.assertRaises(PermissionError):
            self.plan([recipient("allowed")],
                      event={**EVENT, "project_id": "private-project"})
        with self.assertRaises(ValueError):
            self.plan([recipient("duplicate"), recipient("duplicate")])

    def test_event_and_notice_inputs_unchanged_no_network_or_file_io(self):
        event, recipients, scope = deepcopy(EVENT), [recipient("viewer")], deepcopy(SCOPE)
        before = (deepcopy(event), deepcopy(recipients), deepcopy(scope))
        with (patch("socket.create_connection", side_effect=AssertionError("network")),
              patch("builtins.open", side_effect=AssertionError("file I/O"))):
            result = self.plan(recipients, event=event, scope=scope)
        self.assertEqual((event, recipients, scope), before)
        self.assertFalse(result["any_mutation_performed"])
        self.assertEqual(result["external_deliveries"], [])


class AmendmentSummaryTests(unittest.TestCase):
    def summarize(self, entries, *, original=None, scope=None):
        return summarize_amendments(
            ORIGINAL if original is None else original,
            entries, scope=SCOPE if scope is None else scope,
        )

    def test_all_authorized_amendments_remain_independent_from_original_status(self):
        original = deepcopy(ORIGINAL)
        entries = [
            amendment("a-open", "UNDER_FINANCE_REVIEW"),
            amendment("a-rejected", "FINANCE_REJECTED"),
            amendment("a-approved", "FINANCE_APPROVED"),
        ]
        before = deepcopy(entries)
        result = self.summarize(entries, original=original)
        self.assertEqual(result["amendment_count"], 3)
        self.assertEqual([r["amendment_id"] for r in result["amendments"]],
                         ["a-open", "a-rejected", "a-approved"])
        self.assertEqual([r["status"] for r in result["amendments"]],
                         ["UNDER_FINANCE_REVIEW", "FINANCE_REJECTED", "FINANCE_APPROVED"])
        self.assertEqual(result["original_official_status"], "UNDER_FINANCE_REVIEW")
        self.assertTrue(result["original_status_unchanged"])
        self.assertFalse(result["official_document_modified"])
        self.assertEqual(ORIGINAL, original)
        self.assertEqual(entries, before)

    def test_verified_taraz_receipt_reference_is_a_display_link_only(self):
        proof = reference("a-verified")
        row = amendment("a-verified", "FINANCE_APPROVED", receipt_reference=proof)
        output = self.summarize([row])
        link = output["amendments"][0]["receipt_reference"]
        self.assertEqual(link["reference_id"], "taraz-receipt-synthetic-1")
        self.assertEqual(link["source_system"], "taraz")
        self.assertEqual(link["source_actor_id"], "taraz-finance-1")
        self.assertIn("not_independently_verified", link["provenance"])
        self.assertEqual(output["original_official_status"], "UNDER_FINANCE_REVIEW")
        self.assertFalse(output["official_document_modified"])
        self.assertEqual(row["receipt_reference"], proof)

    def test_officially_posted_requires_verified_taraz_document_not_just_receipt(self):
        for receipt in (
            None,
            reference("a-posted", reference_kind="receipt"),
            reference("a-posted", reference_kind="document",
                      correlation_verified=False),
        ):
            with self.subTest(receipt=receipt), self.assertRaises(PermissionError):
                self.summarize([amendment("a-posted", "OFFICIALLY_POSTED",
                                          receipt_reference=receipt)])
        valid_document = reference("a-posted", reference_kind="document")
        output = self.summarize([amendment(
            "a-posted", "OFFICIALLY_POSTED", receipt_reference=valid_document,
        )])
        self.assertEqual(
            output["amendments"][0]["receipt_reference"]["reference_kind"], "document",
        )
        self.assertEqual(output["original_official_status"], "UNDER_FINANCE_REVIEW")

    def test_viewer_can_read_posted_status_without_reference_field_access(self):
        limited = {**SCOPE, "actor_role": "viewer", "visible_fields": ["status"]}
        output = self.summarize([amendment(
            "a-posted", "OFFICIALLY_POSTED",
            receipt_reference=reference("a-posted", reference_kind="document"),
        )], scope=limited)
        self.assertEqual(output["amendments"][0]["status"], "OFFICIALLY_POSTED")
        self.assertIsNone(output["amendments"][0]["receipt_reference"])
        self.assertNotIn("taraz-receipt-synthetic-1", repr(output))

    def test_unverified_provenance_or_actor_never_shown_as_official_reference(self):
        for field in ("source_actor_verified", "source_provenance_verified",
                      "correlation_verified"):
            with self.subTest(field=field):
                invalid = reference("a1", **{field: False})
                result = self.summarize(
                    [amendment("a1", "FINANCE_APPROVED", receipt_reference=invalid)])
                self.assertIsNone(result["amendments"][0]["receipt_reference"])
                self.assertNotIn("taraz-receipt-synthetic-1", repr(result))
        with self.assertRaises(PermissionError):
            self.summarize([amendment("a1", "FINANCE_APPROVED",
                                      receipt_reference=reference("a1",
                                                                  source_provenance_verified=None))])

    def test_forged_reference_or_wrong_actor_origin_is_rejected(self):
        for bad in (
            {"source_system": "client"},
            {"server_supplied": False},
            {"organization_id": "other-org"},
            {"project_id": "other-project"},
            {"amendment_id": "other-amendment"},
            {"reference_kind": "unknown"},
        ):
            with self.subTest(bad=bad), self.assertRaises(PermissionError):
                self.summarize([amendment("a1", "FINANCE_APPROVED",
                                          receipt_reference=reference("a1", **bad))])
        with self.assertRaises(ValueError):
            self.summarize([amendment("a1", "FINANCE_APPROVED",
                                      receipt_reference=reference("a1", source_actor_id=""))])

    def test_field_level_redaction_of_reference_id_and_status_in_viewer(self):
        restricted = {**SCOPE, "actor_role": "viewer",
                      "visible_fields": ["amendment_id"]}
        data = amendment("a-visible", "FINANCE_REJECTED",
                         receipt_reference=reference("a-visible"),
                         visible_fields=["amendment_id", "status"])
        result = self.summarize([data], scope=restricted)
        self.assertEqual(result["amendments"][0]["amendment_id"], "a-visible")
        self.assertIsNone(result["amendments"][0]["status"])
        self.assertIsNone(result["amendments"][0]["receipt_reference"])
        self.assertIsNone(result["original_official_status"])
        self.assertNotIn("taraz-receipt-synthetic-1", repr(result))
        self.assertNotIn("FINANCE_REJECTED", repr(result))

    def test_unknown_or_stale_status_and_untrusted_original_fail_closed(self):
        for wrong in (
            {"status": "OFFICIALLY_SAVED_MAYBE"},
            {"status_source": "browser"},
            {"status_source_trusted": False},
            {"status_updated_at": ""},
            {"status_source": "madar"},
        ):
            with self.subTest(wrong=wrong), self.assertRaises((ValueError, PermissionError)):
                self.summarize([amendment("a1", "FINANCE_APPROVED", **wrong)])
        for wrong in (
            {"official_status": "possibly_posted"},
            {"official_status_source": "madar"},
            {"official_status_server_trusted": False},
        ):
            with self.subTest(wrong=wrong), self.assertRaises((ValueError, PermissionError)):
                self.summarize([amendment("a1", "FINANCE_APPROVED")],
                               original={**ORIGINAL, **wrong})

    def test_mixed_organization_wrong_project_or_other_original_deny_entire_batch(self):
        legit = amendment("a-legit", "DRAFT")
        for other in (
            amendment("a-foreign", "DRAFT", organization_id="other-org"),
            amendment("a-project", "DRAFT", project_id="other-project"),
            amendment("a-original", "DRAFT", original_request_id="other-original"),
            amendment("a-unreadable", "DRAFT", server_read_authorized=False),
        ):
            with self.subTest(other=other["amendment_id"]), self.assertRaises(PermissionError):
                self.summarize([legit, other])
        with self.assertRaises(ValueError):
            self.summarize([legit, legit])
        with self.assertRaises(PermissionError):
            self.summarize([legit], scope={**SCOPE, "readable_project_ids": []})

    def test_summary_no_mutations_or_io_and_empty_list_is_not_a_post(self):
        original, scope = deepcopy(ORIGINAL), deepcopy(SCOPE)
        before = deepcopy((original, scope))
        with (patch("socket.create_connection", side_effect=AssertionError("network")),
              patch("builtins.open", side_effect=AssertionError("file I/O"))):
            output = self.summarize([], original=original, scope=scope)
        self.assertEqual((original, scope), before)
        self.assertEqual(output["amendments"], [])
        self.assertEqual(output["amendment_count"], 0)
        self.assertFalse(output["official_document_modified"])


if __name__ == "__main__":
    unittest.main()
