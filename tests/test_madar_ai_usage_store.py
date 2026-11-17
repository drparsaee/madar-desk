"""Synthetic E1 AI quota/consent ledger; NO real profiles/providers/network."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from multiprocessing import get_context
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch

from madar_ai_usage_store import AiPrincipal, AiUsageError, AiUsageStore


NOW = "2026-11-09T19:00:00Z"
SOON = "2026-11-09T19:05:00Z"
LATER = "2026-11-09T19:10:00Z"
LAST_NOV = "2026-11-30T23:59:59Z"
FIRST_DEC = "2026-12-01T00:00:00Z"
DIGEST = "c" * 64  # synthetic fixed host-digest placeholder; no content.


def principal(user="editor1", org="org-a", project="project-a",
              role="editor", managed=()):
    return AiPrincipal(user, org, frozenset((project,)), role, True, True,
                       frozenset(managed))


def _child_reserve(path, barrier, queue, suffix):
    store = AiUsageStore(Path(path))
    barrier.wait(timeout=10)
    try:
        row = store.reserve(
            principal=principal(), project_id="project-a",
            provider="local_ollama", request_id=f"{suffix:032x}",
            payload_digest=DIGEST, estimated_tokens=90, max_cost_micro=0,
            event_id=f"process-reserve-{suffix}", at_utc=NOW,
        )
        queue.put(("ok", row.status))
    except AiUsageError as exc:
        queue.put(("denied", exc.code))


class AiUsageStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="synthetic-ai-usage-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ai_usage.sqlite"
        self.store = AiUsageStore(self.path)
        self.editor = principal()
        self.admin = principal("admin1", role="admin", managed=("editor1",))
        self.viewer = principal("viewer1", role="viewer")

    def grant(self, *, provider="local_ollama", requests=2, tokens=200,
              cost=0, enabled=True, cloud=False, expected=0,
              event="grant-1", expires=None, user="editor1", p=None):
        return self.store.set_grant(
            principal=self.admin if p is None else p, project_id="project-a",
            user_id=user, provider=provider, enabled=enabled,
            cloud_enabled=cloud, monthly_requests=requests,
            monthly_tokens=tokens, monthly_cost_micro=cost,
            expected_version=expected, event_id=event, at_utc=NOW,
            expires_at_utc=expires,
        )

    def consent(self, request="a" * 32, provider="openai", digest=DIGEST,
                event="consent-1", at=NOW, until=SOON, human=True, p=None):
        return self.store.grant_cloud_consent(
            principal=(replace(self.editor,
                               approved_cloud_request_ids=frozenset((request,)))
                       if p is None else p),
            project_id="project-a", provider=provider, request_id=request,
            payload_digest=digest, expires_at_utc=until,
            explicit_human_consent=human, event_id=event, at_utc=at,
        )

    def reserve(self, *, provider="local_ollama", request="a" * 32,
                tokens=100, cost=0, event="reserve-1", at=NOW, digest=DIGEST,
                p=None):
        return self.store.reserve(
            principal=self.editor if p is None else p,
            project_id="project-a", provider=provider, request_id=request,
            payload_digest=digest, estimated_tokens=tokens,
            max_cost_micro=cost, event_id=event, at_utc=at,
        )

    def transition(self, kind, *, request="a" * 32, expected=1,
                   event="event-transition", at=SOON, p=None, **kwargs):
        method = getattr(self.store, kind)
        if kind == "refund_undispatched_local" and p is None:
            p = replace(self.editor,
                        proven_local_nonexecution_ids=frozenset((request,)))
        return method(
            principal=self.editor if p is None else p,
            project_id="project-a", request_id=request,
            expected_version=expected, event_id=event, at_utc=at,
            **kwargs,
        )

    def deny(self, code, call, **params):
        with self.assertRaises(AiUsageError) as caught:
            call(**params)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        self.assertNotIn("org-b", str(caught.exception))

    def usage(self, provider="local_ollama", at=NOW):
        return self.store.usage(principal=self.editor, project_id="project-a",
                                provider=provider, at_utc=at)

    def test_default_deny_ai_does_not_touch_manual_workflow(self):
        self.deny("grant_denied", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="local_ollama", request_id="a" * 32,
                  payload_digest=DIGEST, estimated_tokens=1, max_cost_micro=0,
                  event_id="first", at_utc=NOW)
        self.assertEqual(self.store.get_grant(
            principal=self.editor, project_id="project-a",
            user_id="editor1", provider="openai"), None)
        # This module exposes no manual-entry API, so it cannot block it.
        self.assertFalse(hasattr(self.store, "manual_entry"))

    def test_local_reserve_is_durable_and_uses_budget_not_just_actual(self):
        self.grant()
        row = self.reserve()
        self.assertEqual(row.status, "reserved")
        self.assertEqual(row.month_utc, "2026-11")
        self.assertEqual(row.reserved_tokens, 100)
        self.assertEqual(row.reserved_cost_micro, 0)
        self.assertFalse(row.replayed)
        self.store = AiUsageStore(self.path)
        saved = self.store.read_reservation(
            principal=self.editor, project_id="project-a",
            request_id="a" * 32)
        self.assertEqual(saved.version, 1)
        used = self.usage()
        self.assertEqual((used.charged_requests, used.charged_tokens,
                          used.charged_cost_micro), (1, 100, 0))
        self.assertEqual((used.remaining_requests, used.remaining_tokens),
                         (1, 100))

    def test_cloud_off_by_default_even_with_valid_consent_gesture(self):
        self.grant(provider="openai", requests=2, tokens=500, cost=250,
                   cloud=False)
        self.deny("grant_denied", self.store.grant_cloud_consent,
                  principal=replace(
                      self.editor,
                      approved_cloud_request_ids=frozenset(("a" * 32,))),
                  project_id="project-a",
                  provider="openai", request_id="a" * 32,
                  payload_digest=DIGEST, expires_at_utc=SOON,
                  explicit_human_consent=True, event_id="consent",
                  at_utc=NOW)
        self.assertEqual(self.usage("openai").charged_requests, 0)

    def test_cloud_consent_atomic_consumption_bound_to_request_and_digest(self):
        self.grant(provider="openai", requests=2, tokens=500, cost=250,
                   cloud=True)
        self.assertEqual(self.consent(), "recorded")
        self.assertEqual(self.consent(), "recorded_replay")
        cloud = self.reserve(provider="openai", tokens=200, cost=100)
        self.assertEqual(cloud.version, 1)
        self.deny("request_conflict", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="openai", request_id="a" * 32,
                  payload_digest="d" * 64, estimated_tokens=200,
                  max_cost_micro=100, event_id="new-event", at_utc=NOW)
        self.deny("request_exists", self.store.grant_cloud_consent,
                  principal=replace(
                      self.editor,
                      approved_cloud_request_ids=frozenset(("a" * 32,))),
                  project_id="project-a",
                  provider="openai", request_id="a" * 32,
                  payload_digest=DIGEST, expires_at_utc=SOON,
                  explicit_human_consent=True, event_id="again",
                  at_utc=NOW)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute(
                "SELECT state FROM ai_consents WHERE request_id=?",
                ("a" * 32,)).fetchone()[0], "consumed")

    def test_cloud_consent_needs_explicit_true_and_valid_expiration(self):
        self.grant(provider="gemini", requests=2, tokens=500, cost=500,
                   cloud=True)
        self.deny("consent_required", self.store.grant_cloud_consent,
                  principal=self.editor, project_id="project-a",
                  provider="gemini", request_id="a" * 32,
                  payload_digest=DIGEST, expires_at_utc=SOON,
                  explicit_human_consent=1, event_id="x", at_utc=NOW)
        self.deny("invalid_expiration", self.store.grant_cloud_consent,
                  principal=replace(
                      self.editor,
                      approved_cloud_request_ids=frozenset(("a" * 32,))),
                  project_id="project-a",
                  provider="gemini", request_id="a" * 32,
                  payload_digest=DIGEST,
                  expires_at_utc="2026-11-09T19:20:01Z",
                  explicit_human_consent=True, event_id="x", at_utc=NOW)
        self.deny("consent_required", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="gemini", request_id="a" * 32,
                  payload_digest=DIGEST, estimated_tokens=100,
                  max_cost_micro=10, event_id="reserve", at_utc=NOW)

    def test_client_true_without_host_minted_consent_or_refund_proof_is_denied(self):
        self.grant(provider="openai", requests=2, tokens=200, cost=100,
                   cloud=True)
        self.deny("consent_required", self.store.grant_cloud_consent,
                  principal=self.editor, project_id="project-a",
                  provider="openai", request_id="a" * 32,
                  payload_digest=DIGEST, expires_at_utc=SOON,
                  explicit_human_consent=True, event_id="forged-approval",
                  at_utc=NOW)
        self.grant(event="grant-local", provider="local_ollama")
        self.reserve()
        self.transition("cancel", event="cancel-local")
        self.deny("verified_nonexecution_required",
                  self.store.refund_undispatched_local,
                  principal=self.editor, project_id="project-a",
                  request_id="a" * 32, expected_version=2,
                  verified_no_execution=True, event_id="forged-proof",
                  at_utc=LATER)
        self.assertEqual(self.usage().charged_requests, 1)

    def test_expired_consent_cannot_reserve_or_dispatch(self):
        self.grant(provider="anthropic", requests=2, tokens=500, cost=500,
                   cloud=True)
        self.consent(provider="anthropic")
        self.deny("consent_required", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="anthropic", request_id="a" * 32,
                  payload_digest=DIGEST, estimated_tokens=20,
                  max_cost_micro=10, event_id="late", at_utc=SOON)
        self.reserve(provider="anthropic", tokens=20, cost=10)
        self.deny("consent_expired", self.store.mark_dispatched,
                  principal=self.editor, project_id="project-a",
                  request_id="a" * 32, expected_version=1,
                  event_id="dispatch-late", at_utc=SOON)
        self.assertEqual(self.store.read_reservation(
            principal=self.editor, project_id="project-a",
            request_id="a" * 32).version, 1)

    def test_budget_exceed_requests_tokens_and_cost(self):
        self.grant(provider="openai", requests=1, tokens=200, cost=100,
                   cloud=True)
        self.consent()
        self.reserve(provider="openai", tokens=120, cost=90)
        self.consent(request="b" * 32, event="consent-2")
        self.deny("budget_exceeded", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="openai", request_id="b" * 32,
                  payload_digest=DIGEST, estimated_tokens=50,
                  max_cost_micro=10, event_id="reserve-2", at_utc=NOW)
        self.assertEqual(self.usage("openai").charged_requests, 1)
        # A rejected reservation does not consume this separate consent.
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute(
                "SELECT state FROM ai_consents WHERE request_id=?",
                ("b" * 32,)).fetchone()[0], "granted")
        self.grant(provider="openai", requests=2, tokens=150, cost=100,
                   cloud=True, expected=1, event="grant-2")
        # Grant revision invalidates all earlier unused consent. Never
        # reuse a consent created under another administrative policy.
        self.deny("consent_required", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="openai", request_id="b" * 32,
                  payload_digest=DIGEST, estimated_tokens=40,
                  max_cost_micro=9, event_id="old-consent", at_utc=NOW)
        self.consent(request="c" * 32, event="consent-3")
        self.deny("budget_exceeded", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="openai", request_id="c" * 32,
                  payload_digest=DIGEST, estimated_tokens=40,
                  max_cost_micro=9, event_id="reserve-3", at_utc=NOW)
        self.grant(provider="openai", requests=2, tokens=500, cost=95,
                   cloud=True, expected=2, event="grant-3")
        self.consent(request="d" * 32, event="consent-4")
        self.deny("budget_exceeded", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="openai", request_id="d" * 32,
                  payload_digest=DIGEST, estimated_tokens=30,
                  max_cost_micro=6, event_id="reserve-4", at_utc=NOW)

    def test_replay_reservation_idempotent_and_collision_rejected(self):
        self.grant()
        first = self.reserve()
        again = self.reserve()
        self.assertTrue(again.replayed)
        self.assertEqual(again.version, first.version)
        self.assertEqual(self.usage().charged_requests, 1)
        self.deny("event_conflict", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="local_ollama", request_id="a" * 32,
                  payload_digest=DIGEST, estimated_tokens=101,
                  max_cost_micro=0, event_id="reserve-1", at_utc=NOW)
        self.deny("request_conflict", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="local_ollama", request_id="a" * 32,
                  payload_digest=DIGEST, estimated_tokens=100,
                  max_cost_micro=0, event_id="reserve-other", at_utc=NOW)

    def test_dispatch_completion_full_hold_not_refunded(self):
        self.grant(provider="openai", requests=2, tokens=300, cost=200,
                   cloud=True)
        self.consent()
        reserved = self.reserve(provider="openai", tokens=200, cost=150)
        dispatched = self.transition("mark_dispatched", event="dispatch",
                                     at="2026-11-09T19:01:00Z")
        self.assertEqual(dispatched.version, 2)
        self.assertTrue(self.transition("mark_dispatched", event="dispatch",
                                        at="2026-11-09T19:01:00Z").replayed)
        complete = self.transition("complete", expected=2, event="complete",
                                   actual_tokens=90, actual_cost_micro=40,
                                   at="2026-11-09T19:02:00Z")
        self.assertEqual(complete.status, "completed")
        self.assertEqual(complete.actual_tokens, 90)
        self.assertEqual(complete.actual_cost_micro, 40)
        usage = self.usage("openai")
        self.assertEqual((usage.charged_requests, usage.charged_tokens,
                          usage.charged_cost_micro), (1, 200, 150))
        self.deny("invalid_state", self.store.cancel,
                  principal=self.editor, project_id="project-a",
                  request_id="a" * 32, expected_version=3,
                  event_id="cancel-after-complete", at_utc=LATER)

    def test_actual_usage_above_reservation_fails_closed(self):
        self.grant(provider="openai", requests=2, tokens=500, cost=500,
                   cloud=True)
        self.consent()
        self.reserve(provider="openai", tokens=100, cost=50)
        self.transition("mark_dispatched", event="dispatch",
                        at="2026-11-09T19:01:00Z")
        self.deny("usage_exceeds_reservation", self.store.complete,
                  principal=self.editor, project_id="project-a",
                  request_id="a" * 32, expected_version=2,
                  actual_tokens=101, actual_cost_micro=20,
                  event_id="too-many-tokens", at_utc=LATER)
        self.deny("usage_exceeds_reservation", self.store.complete,
                  principal=self.editor, project_id="project-a",
                  request_id="a" * 32, expected_version=2,
                  actual_tokens=40, actual_cost_micro=51,
                  event_id="too-expensive", at_utc=LATER)
        self.assertEqual(self.store.read_reservation(
            principal=self.editor, project_id="project-a",
            request_id="a" * 32).status, "dispatched")

    def test_cancel_cloud_never_releases_budget_or_allows_refund(self):
        self.grant(provider="openai", requests=1, tokens=200, cost=300,
                   cloud=True)
        self.consent()
        self.reserve(provider="openai", tokens=80, cost=50)
        cancelled = self.transition("cancel", event="cancel")
        self.assertEqual(cancelled.status, "cancelled")
        self.assertTrue(self.transition("cancel", event="cancel").replayed)
        self.deny("refund_denied", self.store.refund_undispatched_local,
                  principal=replace(
                      self.editor, proven_local_nonexecution_ids=
                      frozenset(("a" * 32,))), project_id="project-a",
                  request_id="a" * 32, expected_version=2,
                  verified_no_execution=True, event_id="refund", at_utc=LATER)
        self.assertEqual(self.usage("openai").charged_requests, 1)
        self.deny("invalid_state", self.store.mark_dispatched,
                  principal=self.editor, project_id="project-a",
                  request_id="a" * 32, expected_version=2,
                  event_id="reopen", at_utc=LATER)

    def test_local_undispatched_cancel_and_proven_refund(self):
        self.grant(requests=1, tokens=100)
        self.reserve(tokens=100)
        self.transition("cancel", event="cancel")
        self.deny("verified_nonexecution_required",
                  self.store.refund_undispatched_local,
                  principal=self.editor, project_id="project-a",
                  request_id="a" * 32, expected_version=2,
                  verified_no_execution=False, event_id="refund", at_utc=LATER)
        refunded = self.transition(
            "refund_undispatched_local", expected=2, event="refund",
            at=LATER, verified_no_execution=True)
        self.assertEqual(refunded.status, "refunded")
        self.assertTrue(refunded.refunded)
        self.assertEqual(self.usage().charged_requests, 0)
        self.assertEqual(self.usage().charged_tokens, 0)
        self.assertTrue(self.transition(
            "refund_undispatched_local", expected=2, event="refund",
            at=LATER, verified_no_execution=True).replayed)
        self.deny("request_conflict", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="local_ollama", request_id="a" * 32,
                  payload_digest=DIGEST, estimated_tokens=1,
                  max_cost_micro=0, event_id="new-reserve", at_utc=NOW)
        self.reserve(request="b" * 32, tokens=50, event="new-reserve")
        self.assertEqual(self.usage().charged_requests, 1)

    def test_dispatched_local_cancellation_never_refunded(self):
        self.grant()
        self.reserve()
        self.transition("mark_dispatched", event="dispatch")
        self.transition("cancel", expected=2, event="cancel", at=LATER)
        self.deny("refund_denied", self.store.refund_undispatched_local,
                  principal=replace(
                      self.editor, proven_local_nonexecution_ids=
                      frozenset(("a" * 32,))), project_id="project-a",
                  request_id="a" * 32, expected_version=3,
                  verified_no_execution=True, event_id="refund",
                  at_utc=LATER)
        self.assertEqual(self.usage().charged_requests, 1)

    def test_dispatched_cloud_cancellation_keeps_ceiling(self):
        self.grant(provider="anthropic", requests=1, tokens=100, cost=300,
                   cloud=True)
        self.consent(provider="anthropic")
        self.reserve(provider="anthropic", tokens=100, cost=300)
        self.transition("mark_dispatched", event="dispatch",
                        at="2026-11-09T19:01:00Z")
        self.transition("cancel", expected=2, event="cancel", at=SOON)
        self.assertEqual(self.usage("anthropic").charged_cost_micro, 300)
        self.deny("refund_denied", self.store.refund_undispatched_local,
                  principal=replace(
                      self.editor, proven_local_nonexecution_ids=
                      frozenset(("a" * 32,))),
                  project_id="project-a", request_id="a" * 32,
                  expected_version=3, verified_no_execution=True,
                  event_id="refund-cloud", at_utc=LATER)

    def test_grant_revocation_and_changed_version_block_dispatch(self):
        self.grant()
        self.reserve()
        self.grant(expected=1, enabled=False, event="revoke")
        self.deny("grant_denied", self.store.mark_dispatched,
                  principal=self.editor, project_id="project-a",
                  request_id="a" * 32, expected_version=1,
                  event_id="dispatch", at_utc=SOON)
        self.grant(expected=2, enabled=True, event="reenable")
        self.deny("grant_changed", self.store.mark_dispatched,
                  principal=self.editor, project_id="project-a",
                  request_id="a" * 32, expected_version=1,
                  event_id="dispatch", at_utc=SOON)
        self.assertEqual(self.usage().charged_tokens, 100)
        self.deny("budget_exceeded", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="local_ollama", request_id="b" * 32,
                  payload_digest=DIGEST, estimated_tokens=101,
                  max_cost_micro=0, event_id="overflow", at_utc=NOW)

    def test_consent_revocation_prevents_reserve(self):
        self.grant(provider="gemini", requests=2, tokens=200, cost=100,
                   cloud=True)
        self.consent(provider="gemini")
        result = self.store.revoke_cloud_consent(
            principal=self.editor, project_id="project-a",
            request_id="a" * 32, event_id="revoke-consent", at_utc=NOW)
        self.assertEqual(result, "revoked")
        self.assertEqual(self.store.revoke_cloud_consent(
            principal=self.editor, project_id="project-a",
            request_id="a" * 32, event_id="revoke-consent", at_utc=NOW),
            "revoked_replay")
        self.deny("consent_required", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="gemini", request_id="a" * 32,
                  payload_digest=DIGEST, estimated_tokens=20,
                  max_cost_micro=10, event_id="reservation", at_utc=NOW)

    def test_expired_grant_and_utc_month_boundary_reset(self):
        self.grant(requests=1, tokens=100,
                   expires="2026-12-01T00:05:00Z")
        self.reserve(at=LAST_NOV, tokens=100)
        self.assertEqual(self.usage(at=LAST_NOV).charged_requests, 1)
        self.assertEqual(self.usage(at=FIRST_DEC).charged_requests, 0)
        self.reserve(request="b" * 32, tokens=100, event="reserve-dec",
                     at=FIRST_DEC)
        self.assertEqual(self.usage(at=FIRST_DEC).charged_requests, 1)
        self.deny("grant_denied", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="local_ollama", request_id="d" * 32,
                  payload_digest=DIGEST, estimated_tokens=1,
                  max_cost_micro=0, event_id="expired-grant",
                  at_utc="2026-12-01T00:05:00Z")
        self.assertEqual(self.store.read_reservation(
            principal=self.editor, project_id="project-a",
            request_id="a" * 32).month_utc, "2026-11")

    def test_foreign_org_project_user_and_viewer_cannot_read_or_write(self):
        self.grant()
        self.reserve()
        foreign_org = principal(org="org-b")
        foreign_project = principal(project="project-b")
        foreign_user = principal(user="user2")
        for p, project in (
            (foreign_org, "project-a"),
            (foreign_project, "project-b"),
            (foreign_user, "project-a"),
        ):
            self.deny("not_found", self.store.read_reservation,
                      principal=p, project_id=project, request_id="a" * 32)
        self.deny("access_denied", self.store.read_reservation,
                  principal=self.editor, project_id="project-b",
                  request_id="a" * 32)
        self.deny("access_denied", self.store.reserve,
                  principal=self.viewer, project_id="project-a",
                  provider="local_ollama", request_id="b" * 32,
                  payload_digest=DIGEST, estimated_tokens=1,
                  max_cost_micro=0, event_id="viewer", at_utc=NOW)
        self.deny("access_denied", self.store.set_grant,
                  principal=self.editor, project_id="project-a",
                  user_id="editor1", provider="local_ollama", enabled=True,
                  cloud_enabled=False, monthly_requests=5,
                  monthly_tokens=100, monthly_cost_micro=0,
                  expected_version=1, event_id="self-promote", at_utc=NOW)
        self.deny("access_denied", self.store.get_grant,
                  principal=self.editor, project_id="project-a",
                  user_id="user2", provider="local_ollama")

    def test_other_org_can_use_same_opaque_request_id_without_reading_this_org(self):
        self.grant()
        first = self.reserve()
        admin_b = principal("admin-b", org="org-b", role="admin",
                            managed=("editor-b",))
        editor_b = principal("editor-b", org="org-b")
        self.store.set_grant(
            principal=admin_b, project_id="project-a",
            user_id="editor-b", provider="local_ollama", enabled=True,
            cloud_enabled=False, monthly_requests=1, monthly_tokens=100,
            monthly_cost_micro=0, expected_version=0,
            event_id="grant-1", at_utc=NOW,
        )
        other = self.store.reserve(
            principal=editor_b, project_id="project-a",
            provider="local_ollama", request_id="a" * 32,
            payload_digest="d" * 64, estimated_tokens=25,
            max_cost_micro=0, event_id="reserve-1", at_utc=NOW,
        )
        self.assertEqual(other.request_id, first.request_id)
        self.assertEqual(other.reserved_tokens, 25)
        self.assertEqual(self.usage().charged_tokens, 100)
        second_usage = self.store.usage(
            principal=editor_b, project_id="project-a",
            provider="local_ollama", at_utc=NOW,
        )
        self.assertEqual(second_usage.charged_tokens, 25)
        self.assertEqual(self.store.read_reservation(
            principal=self.editor, project_id="project-a",
            request_id="a" * 32).reserved_tokens, 100)
        self.assertEqual(self.store.read_reservation(
            principal=editor_b, project_id="project-a",
            request_id="a" * 32).reserved_tokens, 25)

    def test_invalid_schema_inputs_fail_closed_without_writes(self):
        self.deny("invalid_path", AiUsageStore, path="relative.sqlite")
        self.deny("invalid_provider", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="unknown_cloud", request_id="a" * 32,
                  payload_digest=DIGEST, estimated_tokens=1,
                  max_cost_micro=0, event_id="bad", at_utc=NOW)
        self.deny("invalid_request_id", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="local_ollama", request_id="not-uuid",
                  payload_digest=DIGEST, estimated_tokens=1,
                  max_cost_micro=0, event_id="bad", at_utc=NOW)
        self.deny("invalid_digest", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="local_ollama", request_id="a" * 32,
                  payload_digest="raw prompt is prohibited",
                  estimated_tokens=1, max_cost_micro=0,
                  event_id="bad", at_utc=NOW)
        self.deny("invalid_utc", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="local_ollama", request_id="a" * 32,
                  payload_digest=DIGEST, estimated_tokens=1,
                  max_cost_micro=0, event_id="bad",
                  at_utc="2026-11-09T19:00:00+03:30")
        self.deny("invalid_budget", self.store.reserve,
                  principal=self.editor, project_id="project-a",
                  provider="local_ollama", request_id="a" * 32,
                  payload_digest=DIGEST, estimated_tokens=True,
                  max_cost_micro=0, event_id="bad", at_utc=NOW)
        self.deny("invalid_budget", self.store.set_grant,
                  principal=self.admin, project_id="project-a",
                  user_id="editor1", provider="local_ollama", enabled=True,
                  cloud_enabled=False, monthly_requests=-1,
                  monthly_tokens=100, monthly_cost_micro=0,
                  expected_version=0, event_id="bad", at_utc=NOW)
        self.deny("invalid_grant", self.store.set_grant,
                  principal=self.admin, project_id="project-a",
                  user_id="editor1", provider="local_ollama", enabled=True,
                  cloud_enabled=True, monthly_requests=1,
                  monthly_tokens=100, monthly_cost_micro=0,
                  expected_version=0, event_id="bad", at_utc=NOW)
        with closing(sqlite3.connect(self.path)) as db:
            for table in ("ai_grants", "ai_consents", "ai_reservations", "ai_audit"):
                self.assertEqual(db.execute(
                    f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_grant_cas_and_historical_event_idempotency(self):
        first = self.grant()
        self.assertEqual(first.version, 1)
        self.grant(expected=1, requests=3, event="grant-2")
        self.assertEqual(self.grant().version, 1)
        current = self.store.get_grant(
            principal=self.editor, project_id="project-a",
            user_id="editor1", provider="local_ollama")
        self.assertEqual(current.version, 2)
        self.assertEqual(current.monthly_requests, 3)
        self.deny("event_conflict", self.store.set_grant,
                  principal=self.admin, project_id="project-a",
                  user_id="editor1", provider="local_ollama", enabled=True,
                  cloud_enabled=False, monthly_requests=8,
                  monthly_tokens=200, monthly_cost_micro=0,
                  expected_version=0, event_id="grant-1", at_utc=NOW)
        self.deny("version_conflict", self.store.set_grant,
                  principal=self.admin, project_id="project-a",
                  user_id="editor1", provider="local_ollama", enabled=True,
                  cloud_enabled=False, monthly_requests=7,
                  monthly_tokens=200, monthly_cost_micro=0,
                  expected_version=1, event_id="grant-stale", at_utc=NOW)

    def test_immutable_audit_no_prompts_keys_or_pii_and_restart(self):
        self.grant(provider="openai", cloud=True, cost=100)
        self.consent()
        self.reserve(provider="openai", tokens=30, cost=10)
        self.store = AiUsageStore(self.path)
        self.assertEqual(self.usage("openai").charged_requests, 1)
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("UPDATE ai_audit SET kind='forged'")
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("DELETE FROM ai_audit")
            rows = db.execute("SELECT * FROM ai_audit").fetchall()
            self.assertEqual(len(rows), 3)
            # Only opaque IDs/metadata/digests. No personal details,
            # credentials, prompt or full request JSON is written.
            flat = repr(rows).lower()
            for banned in ("api_key", "sk-", "password", "prompt_text",
                           "john@example.com", "customer"):
                self.assertNotIn(banned, flat)
        self.assertEqual(self.store.read_reservation(
            principal=self.editor, project_id="project-a",
            request_id="a" * 32).status, "reserved")

    def test_two_threads_cannot_overbook_one_remaining_request(self):
        self.grant(requests=1, tokens=100)
        gate = Barrier(2)

        def worker(i):
            store = AiUsageStore(self.path)
            gate.wait(timeout=5)
            try:
                row = store.reserve(
                    principal=self.editor, project_id="project-a",
                    provider="local_ollama", request_id=f"{i:032x}",
                    payload_digest=DIGEST, estimated_tokens=90,
                    max_cost_micro=0, event_id=f"race-{i}", at_utc=NOW)
                return "ok", row.version
            except AiUsageError as exc:
                return "denied", exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, i) for i in (1, 2)]
            result = [f.result(timeout=15) for f in futures]
        self.assertEqual(sorted(result),
                         [("denied", "budget_exceeded"), ("ok", 1)])
        self.assertEqual(self.usage().charged_requests, 1)

    def test_two_threads_same_request_event_replay_once(self):
        self.grant(requests=1, tokens=100)
        gate = Barrier(2)

        def worker():
            store = AiUsageStore(self.path)
            gate.wait(timeout=5)
            return store.reserve(
                principal=self.editor, project_id="project-a",
                provider="local_ollama", request_id="a" * 32,
                payload_digest=DIGEST, estimated_tokens=90,
                max_cost_micro=0, event_id="same-event", at_utc=NOW)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in (1, 2)]
            receipts = [f.result(timeout=12) for f in futures]
        self.assertEqual(sorted(row.replayed for row in receipts),
                         [False, True])
        self.assertEqual([row.version for row in receipts], [1, 1])
        self.assertEqual(self.usage().charged_requests, 1)
        self.assertEqual(self.usage().charged_tokens, 90)

    def test_provider_user_and_project_quota_independence(self):
        self.grant(provider="local_ollama", requests=1, tokens=100)
        self.grant(provider="openai", requests=1, tokens=100, cost=100,
                   cloud=True, event="grant-cloud")
        self.reserve(tokens=100)
        self.consent(request="b" * 32, event="consent-other")
        self.reserve(provider="openai", request="b" * 32, event="reserve-cloud",
                     tokens=100, cost=100)
        self.assertEqual(self.usage().charged_requests, 1)
        self.assertEqual(self.usage("openai").charged_requests, 1)
        self.assertEqual(self.usage("openai").charged_cost_micro, 100)
        another_user = principal(user="editor2")
        other_admin = principal("admin1", role="admin",
                                managed=("editor1", "editor2"))
        self.grant(user="editor2", p=other_admin, event="grant-editor2",
                   requests=1, tokens=100)
        result = self.reserve(p=another_user, request="c" * 32,
                              event="reserve-editor2", tokens=50)
        self.assertEqual(result.version, 1)
        self.assertEqual(self.usage().charged_requests, 1)
        other_project_admin = principal(
            "admin1", project="project-b", role="admin",
            managed=("editor1",))
        self.store.set_grant(
            principal=other_project_admin, project_id="project-b",
            user_id="editor1", provider="local_ollama", enabled=True,
            cloud_enabled=False, monthly_requests=1, monthly_tokens=100,
            monthly_cost_micro=0, expected_version=0,
            event_id="grant-other-project", at_utc=NOW,
        )
        other_project_editor = principal(project="project-b")
        separate = self.store.reserve(
            principal=other_project_editor, project_id="project-b",
            provider="local_ollama", request_id="d" * 32,
            payload_digest=DIGEST, estimated_tokens=30, max_cost_micro=0,
            event_id="reserve-other-project", at_utc=NOW,
        )
        self.assertEqual(separate.month_utc, "2026-11")
        self.assertEqual(self.usage().charged_requests, 1)

    def test_two_processes_sqlite_begin_immediate_one_budget_winner(self):
        self.grant(requests=1, tokens=100)
        ctx = get_context("spawn")
        barrier = ctx.Barrier(2)
        queue = ctx.Queue()
        workers = [
            ctx.Process(target=_child_reserve,
                        args=(str(self.path), barrier, queue, suffix))
            for suffix in (11, 12)
        ]
        try:
            for worker in workers:
                worker.start()
            observed = [queue.get(timeout=18) for _ in workers]
            for worker in workers:
                worker.join(timeout=10)
            self.assertTrue(all(worker.exitcode == 0 for worker in workers))
            self.assertEqual(sorted(observed),
                             [("denied", "budget_exceeded"),
                              ("ok", "reserved")])
            self.assertEqual(self.usage().charged_requests, 1)
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=5)
            queue.close()
            queue.join_thread()

    def test_no_external_calls_or_model_downloads(self):
        with patch("socket.socket", side_effect=AssertionError("no network")):
            self.grant()
            self.reserve()
            self.transition("mark_dispatched", event="dispatch")
            self.transition("complete", expected=2, event="complete",
                            actual_tokens=20, actual_cost_micro=0)
        self.assertEqual(self.usage().charged_requests, 1)


if __name__ == "__main__":
    unittest.main()
