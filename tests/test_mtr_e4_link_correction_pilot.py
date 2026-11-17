"""E4 Refine 6.15/6.16: local synthetic impact; no links are changed."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import unittest

from mtr_e4_link_correction_pilot import (
    HostImpactSnapshot, ImpactDenied, LinkedOrder, impact_preview,
    selective_correction_intent,
)
from radar_party_review_store import HostPrincipal


class WrongPartyLinkImpactTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc)
        self.principal = HostPrincipal(
            user_id="finance-1", organization_id="org-1", session_id="s-1",
            role="taraz_finance_reviewer",
            project_grants=frozenset({"project-1"}),
            capabilities=frozenset({"party_link_impact_read",
                                    "party_link_correction_review"}),
            visible_fields=frozenset(), allowed_candidate_ids=frozenset(),
            authenticated=True, active=True,
        )
        self.rows = tuple(LinkedOrder(
            order_id=f"ord-{n}", organization_id="org-1", project_id="project-1",
            customer_id="customer-1", party_id="old-party", state=state,
            finance_request_id=(f"req-{n}" if n in (4, 5) else None),
            document_ids=(("doc-5",) if n == 5 else ()),
        ) for n, state in enumerate(("open", "draft", "open", "sent", "posted"), 1))
        self.snapshot = HostImpactSnapshot(
            organization_id="org-1", project_id="project-1",
            customer_id="customer-1", old_party_id="old-party",
            proposed_party_id="new-party", revision=7, observed_at=self.now,
            expected_linked_order_count=5, linked_orders=self.rows,
        )
        self.orders = frozenset(row.order_id for row in self.rows)
        self.docs = frozenset({"doc-5"})

    def preview(self, **changes):
        params = dict(principal=self.principal, snapshot=self.snapshot,
                      allowed_order_ids=self.orders,
                      allowed_document_ids=self.docs,
                      synthetic_only=True, now=self.now)
        params.update(changes)
        return impact_preview(**params)

    def intent(self, preview, **changes):
        params = dict(preview=preview, principal=self.principal,
                      selected_order_ids=("ord-1", "ord-3"),
                      expected_revision=preview["revision"],
                      expected_digest=preview["snapshotSha256"],
                      explicit_manual_action=True)
        params.update(changes)
        return selective_correction_intent(**params)

    def test_five_visible_two_explicitly_selected_no_mutation(self):
        original = deepcopy(self.rows)
        preview = self.preview()
        self.assertEqual(len(preview["rows"]), 5)
        self.assertEqual([r["orderId"] for r in preview["rows"]],
                         [f"ord-{i}" for i in range(1, 6)])
        self.assertEqual([r["eligibleForSeparateManualCorrection"]
                          for r in preview["rows"]], [True, True, True, False, False])
        self.assertEqual(preview["rows"][4]["documentIds"], ["doc-5"])
        intent = self.intent(preview)
        self.assertEqual(intent["selectedOrderIds"], ["ord-1", "ord-3"])
        self.assertEqual(intent["status"], "UNSENT_SELECTION_INTENT")
        self.assertFalse(intent["approvedToApplyOrSend"])
        for field in ("officialDocumentsChanged", "financeRequestsChanged",
                      "ordersChanged", "partyLinkChanged"):
            self.assertFalse(intent[field])
        self.assertEqual(original, self.rows)

    def test_cannot_select_submitted_posted_or_unknown_order(self):
        preview = self.preview()
        for order_id in ("ord-4", "ord-5", "other-order"):
            with self.subTest(order_id=order_id), self.assertRaises(ImpactDenied):
                self.intent(preview, selected_order_ids=(order_id,))

    def test_manual_action_required_and_no_automatic_bulk_selection(self):
        preview = self.preview()
        with self.assertRaises(PermissionError):
            self.intent(preview, explicit_manual_action=False)
        for selected in ((), ("ord-1", "ord-1"), list(("ord-1",))):
            with self.subTest(selected=selected), self.assertRaises(ImpactDenied):
                self.intent(preview, selected_order_ids=selected)

    def test_revoked_role_session_or_scope_denied(self):
        for principal in (
            replace(self.principal, authenticated=False),
            replace(self.principal, active=False),
            replace(self.principal, role="member"),
            replace(self.principal, organization_id="org-2"),
            replace(self.principal, project_grants=frozenset()),
            replace(self.principal, capabilities=frozenset()),
        ):
            with self.subTest(principal=principal), self.assertRaises(PermissionError):
                self.preview(principal=principal)

    def test_revocation_at_selection_blocks_even_previous_preview(self):
        preview = self.preview()
        with self.assertRaises(PermissionError):
            self.intent(preview, principal=replace(self.principal, active=False))
        with self.assertRaises(PermissionError):
            self.intent(preview, principal=replace(self.principal,
                capabilities=frozenset({"party_link_impact_read"})))

    def test_missing_row_or_document_grant_denied_without_partial_results(self):
        with self.assertRaises(PermissionError):
            self.preview(allowed_order_ids=frozenset({"ord-1", "ord-2"}))
        with self.assertRaises(PermissionError):
            self.preview(allowed_document_ids=frozenset())

    def test_incomplete_duplicate_or_cross_tenant_snapshot_refused(self):
        with self.assertRaises(ImpactDenied):
            replace(self.snapshot, expected_linked_order_count=4)
        with self.assertRaises(ImpactDenied):
            replace(self.snapshot, linked_orders=(self.rows[0],) * 5)
        with self.assertRaises(ImpactDenied):
            replace(self.snapshot, linked_orders=(replace(self.rows[0],
                organization_id="org-2"), *self.rows[1:]))

    def test_source_stale_future_or_revision_stale_denied(self):
        with self.assertRaises(ImpactDenied):
            self.preview(now=self.now + timedelta(seconds=301))
        with self.assertRaises(ImpactDenied):
            self.preview(now=self.now - timedelta(seconds=31))
        preview = self.preview()
        with self.assertRaises(ImpactDenied):
            self.intent(preview, expected_revision=8)
        with self.assertRaises(ImpactDenied):
            self.intent(preview, expected_digest="f" * 64)

    def test_modified_preview_eligibility_digest_or_financial_refs_denied(self):
        preview = self.preview()
        for field, value in (("state", "open"),
                             ("eligibleForSeparateManualCorrection", True),
                             ("financeRequestId", None),
                             ("documentIds", [])):
            forged = deepcopy(preview)
            forged["rows"][4][field] = value
            with self.subTest(field=field), self.assertRaises(ImpactDenied):
                self.intent(forged, selected_order_ids=("ord-5",))

    def test_no_production_mode_or_false_official_receipt_flag(self):
        with self.assertRaises(ImpactDenied):
            self.preview(synthetic_only=False)
        forged = deepcopy(self.preview())
        forged["remoteTarazAuthorityVerified"] = True
        with self.assertRaises(ImpactDenied):
            self.intent(forged)

    def test_schema_rejects_forged_customer_and_unrecognized_status(self):
        with self.assertRaises(ImpactDenied):
            replace(self.snapshot, old_party_id="new-party")
        with self.assertRaises(ImpactDenied):
            replace(self.rows[0], state="unknown")
        with self.assertRaises(ImpactDenied):
            replace(self.snapshot, linked_orders=(replace(self.rows[0],
                customer_id="other-customer"), *self.rows[1:]))

    def test_untrusted_input_not_exposed_as_official_or_mutated(self):
        view = self.preview()
        self.assertIs(view["remoteTarazAuthorityVerified"], False)
        self.assertIs(view["partyLinkChanged"], False)
        self.assertIs(view["financeRequestsChanged"], False)
        self.assertIs(view["officialDocumentsChanged"], False)
        with self.assertRaises(ImpactDenied):
            self.intent({**view, "allHostSuppliedDependenciesVisible": False})


if __name__ == "__main__":
    unittest.main()
