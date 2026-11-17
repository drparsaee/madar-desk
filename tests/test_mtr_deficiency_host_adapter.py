"""E3 host adapter: synthetic locked LanService, SQLite and receipt boundary.

No LAN listeners, external network, official finance, real user data, or
production filesystem paths. All persisted cases live in TemporaryDirectory.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sqlite3
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from mtr_deficiency_host_adapter import (
    DeficiencyHostAdapter, HostDeficiencyError, _saved_case,
)
from mtr_deficiency_store import DeficiencyStore, StoreConflict, StoreError
from mtr_deficiency_workflow import FinanceReceipt


ORG = "synthetic-org"
PROJECT = "synthetic-project"
TASK = "synthetic-task"
REQUEST = "original-request-1"
RECEIPT = "signed-receipt-1"
TOKEN_REVIEW = "r" * 42
TOKEN_ASSIGNEE = "a" * 42
TOKEN_OTHER = "o" * 42
T0 = datetime(2026, 11, 9, 10, tzinfo=timezone.utc)


class SyntheticBridge:
    def __init__(self):
        self._lock = threading.RLock()
        self.calls = 0
        self.state = {
            "projects": [{"id": PROJECT, "name": "Synthetic project"}],
            "tasks": [{
                "id": TASK, "projectId": PROJECT, "title": "Synthetic saved card",
                "mtrDeficiencyRequest": {
                    "requestId": REQUEST, "revision": 3,
                    "reviewState": "IN_FINANCE_REVIEW",
                    "expectedReceiptId": RECEIPT,
                    "receiptGeneration": 7,
                    "previousReceiptIds": ["older-receipt"],
                    "previousSendKeys": ["older-send-key"],
                },
            }],
        }
        self.connection = {"mode": "host"}

    def getState(self):
        if not self._lock._is_owned():
            raise AssertionError("must read saved card under bridge lock")
        self.calls += 1
        return deepcopy(self.state)


class SyntheticLanService:
    def __init__(self, bridge):
        self.lock = threading.RLock()
        self.bridge = bridge
        self.sessions = {
            TOKEN_REVIEW: "reviewer-a",
            TOKEN_ASSIGNEE: "assignee-a",
            TOKEN_OTHER: "other-a",
        }
        self.users = {
            "reviewer-a": {
                "username": "reviewer-a", "role": "editor",
                "projects": [PROJECT], "financeEdit": True,
            },
            "assignee-a": {
                "username": "assignee-a", "role": "editor",
                "projects": [PROJECT], "financeEdit": False,
            },
            "other-a": {
                "username": "other-a", "role": "editor",
                "projects": [PROJECT], "financeEdit": False,
            },
        }
        self.auth_calls = 0

    def account_for(self, token):
        if not self.lock._is_owned():
            raise AssertionError("must validate account under service lock")
        self.auth_calls += 1
        identity = self.sessions.get(token)
        if identity is None or identity not in self.users:
            raise PermissionError("synthetic revoked/expired session")
        return self.users[identity]


class SyntheticVerifiedReceiptSource:
    """Fixture boundary injected by host Python, NOT a browser-supplied flag."""

    def __init__(self):
        self.calls = 0
        self.updates = {}

    def verified_receipt_for(self, *, baseline):
        self.calls += 1
        fields = {
            "receipt_id": RECEIPT,
            "request_id": baseline.request_id,
            "org_id": baseline.org_id,
            "project_id": baseline.project_id,
            "revision": baseline.revision,
            "digest": baseline.digest,
            "generation": 7,
            "status": "deficiency_required",
            "source": "taraz",
            "verified_by_adapter": True,
            "occurred_at": T0,
        }
        fields.update(self.updates)
        return FinanceReceipt(**fields)


class E3HostAdapterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-e3-host-synthetic-")
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "host-deficiency.sqlite3"
        self.store = DeficiencyStore(self.db)
        self.bridge = SyntheticBridge()
        self.service = SyntheticLanService(self.bridge)
        self.synthetic_source = SyntheticVerifiedReceiptSource()
        self.adapter = self.make_adapter(receipt=self.synthetic_source)
        self.initial = self.snapshot()

    def make_adapter(self, *, receipt=None, reviewers=None, org=ORG):
        return DeficiencyHostAdapter(
            self.service, self.store, org_id=org,
            reviewer_usernames=(frozenset({"reviewer-a"}) if reviewers is None
                                else reviewers),
            verified_receipt_source=receipt,
        )

    def snapshot(self):
        base, _, _ = _saved_case(self.bridge.state, ORG, PROJECT, TASK)
        return base

    def common(self, *, current=None):
        base = current or self.snapshot()
        return {
            "project_id": PROJECT, "task_id": TASK,
            "expected_host_revision": base.revision,
            "expected_host_digest": base.digest,
        }

    def case_reference(self):
        return {
            "case_revision": self.initial.revision,
            "case_digest": self.initial.digest,
        }

    def refer(self, *, adapter=None, token=TOKEN_REVIEW, **overrides):
        args = {
            **self.common(),
            "token": token,
            "assignee_username": "assignee-a",
            "deadline": T0 + timedelta(days=2),
            "reason": "Missing supplier metadata",
            "missing_fields": frozenset({"supplier", "units"}),
            "event_id": "event-refer-1",
            "occurred_at": T0 + timedelta(minutes=1),
        }
        args.update(overrides)
        return (adapter or self.adapter).refer_from_trusted_receipt(**args)

    def save_correction(self, *, fields=None, revision=4):
        card = self.bridge.state["tasks"][0]
        card["mtrDeficiencyRequest"]["revision"] = revision
        card["mtrDeficiencyFields"] = (
            {"supplier": "saved-supplier-a", "units": "5"}
            if fields is None else fields
        )
        return self.snapshot()

    def read(self, *, adapter=None, token=TOKEN_ASSIGNEE, **kwargs):
        args = {
            "token": token, **self.common(), **self.case_reference(),
        }
        args.update(kwargs)
        return (adapter or self.adapter).read_case(**args)

    def query(self, *, token=TOKEN_REVIEW, **kwargs):
        args = {
            "token": token, **self.common(), **self.case_reference(),
        }
        args.update(kwargs)
        return self.adapter.query_first_status(**args)

    def resolve(self, *, token=TOKEN_ASSIGNEE, case_version=1,
                corrected_field_names=None, **kwargs):
        args = {
            "token": token, **self.common(), **self.case_reference(),
            "expected_case_version": case_version,
            "corrected_field_names": (
                frozenset({"supplier", "units"})
                if corrected_field_names is None else corrected_field_names
            ),
            "result_note": "Saved values reviewed",
            "event_id": "event-resolve-1",
            "occurred_at": T0 + timedelta(minutes=5),
        }
        args.update(kwargs)
        return self.adapter.resolve_saved_fields(**args)

    def send(self, *, token=TOKEN_REVIEW, case_version=2, **kwargs):
        args = {
            "token": token, **self.common(), **self.case_reference(),
            "expected_case_version": case_version,
            "explicit_manual_action": True,
            "warning_acknowledged": False,
            "new_send_key": "new-approved-send",
            "event_id": "event-intent-1",
            "occurred_at": T0 + timedelta(minutes=6),
        }
        args.update(kwargs)
        return self.adapter.manual_resend_intent(**args)

    def test_missing_independent_receipt_source_denies_referral_default(self):
        denied = self.make_adapter(receipt=None)
        with self.assertRaisesRegex(PermissionError, "independent authenticated"):
            self.refer(adapter=denied)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM cases").fetchone()[0], 0)
        self.assertEqual(self.synthetic_source.calls, 0)

    def test_browser_verification_flag_and_receipt_argument_have_no_public_api(self):
        for extra in (
            {"verified_by_adapter": True},
            {"receipt": self.synthetic_source.verified_receipt_for(
                baseline=self.initial,
            )},
            {"case": object()}, {"principal": "admin"},
            {"org_id": "foreign-org"},
        ):
            with self.subTest(extra=tuple(extra)), self.assertRaises(TypeError):
                self.refer(adapter=self.make_adapter(receipt=None), **extra)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit_events").fetchone()[0], 0)

    def test_verified_synthetic_source_allows_referral_and_persisted_read_only(self):
        result = self.refer()
        self.assertEqual(result["state"], "DEFICIENCY_ASSIGNED")
        self.assertEqual(result["version"], 1)
        self.assertEqual(result["assigneeId"], "assignee-a")
        self.assertEqual(result["deadlineUtc"], (T0 + timedelta(days=2)).isoformat())
        self.assertEqual(result["reason"], "Missing supplier metadata")
        self.assertFalse(result["postingPerformed"])
        self.assertFalse(result["financialEventCreated"])
        self.assertFalse(result["tarazReceiptIndependentlyVerifiedInResponse"])
        self.assertTrue(result["hostAuthenticated"])
        self.assertEqual(result["transportState"], "NOT_SENT_BY_HOST_ADAPTER")
        self.assertEqual(self.synthetic_source.calls, 1)
        reader = self.read()
        self.assertEqual(reader["state"], "DEFICIENCY_ASSIGNED")
        self.assertEqual(reader["events"][0]["actorId"], "reviewer-a")
        self.assertEqual(self.query()["peerDeliveryState"],
                         "UNKNOWN_REQUIRES_AUTHENTICATED_TARAZ_QUERY")
        self.assertFalse(self.query()["newSendPermitted"])
        self.store = DeficiencyStore(self.db)
        self.adapter = self.make_adapter(receipt=self.synthetic_source)
        self.assertEqual(self.read()["version"], 1)

    def test_assignee_can_resolve_only_saved_card_values_no_auto_send(self):
        self.refer()
        changed = self.save_correction()
        ready = self.resolve()
        self.assertEqual(ready["state"], "CORRECTED_READY_FOR_RESUBMIT")
        self.assertEqual(ready["version"], 2)
        self.assertEqual(ready["correctedRevision"], changed.revision)
        self.assertEqual(ready["remainingMissingFields"], [])
        self.assertIsNone(ready["sendIntentKey"])
        self.assertFalse(ready["postingPerformed"])
        with closing(sqlite3.connect(self.db)) as db:
            data = db.execute("SELECT snapshot FROM cases").fetchone()[0]
            self.assertIn("saved-supplier-a", data)
        self.assertEqual(self.query()["peerDeliveryState"],
                         "UNKNOWN_REQUIRES_AUTHENTICATED_TARAZ_QUERY")

    def test_manual_resend_requires_separate_finance_approval_only_intent(self):
        self.refer()
        self.save_correction()
        self.resolve()
        with self.assertRaises(PermissionError):
            self.send(token=TOKEN_ASSIGNEE)
        for value in (False, None, 1, 0):
            with self.subTest(value=value), self.assertRaises(PermissionError):
                self.send(explicit_manual_action=value)
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            result = self.send()
        self.assertEqual(result["state"], "MANUAL_RESUBMISSION_INTENT_ONLY")
        self.assertEqual(result["version"], 3)
        self.assertEqual(result["sendIntentKey"], "new-approved-send")
        self.assertFalse(result["postingPerformed"])
        self.assertFalse(result["financialEventCreated"])
        self.assertEqual(result["transportState"], "NOT_SENT_BY_HOST_ADAPTER")
        self.assertEqual(self.query()["peerDeliveryState"],
                         "UNKNOWN_REQUIRES_AUTHENTICATED_TARAZ_QUERY")

    def test_partial_saved_corrections_require_separate_human_warning(self):
        self.refer()
        self.save_correction(fields={"supplier": "saved-supplier-a"})
        ready = self.resolve(corrected_field_names=frozenset({"supplier"}))
        self.assertEqual(ready["remainingMissingFields"], ["units"])
        with self.assertRaisesRegex(ValueError, "warning"):
            self.send()
        response = self.send(warning_acknowledged=True)
        self.assertEqual(response["state"], "MANUAL_RESUBMISSION_INTENT_ONLY")
        self.assertFalse(response["postingPerformed"])

    def test_read_current_scope_allowed_only_case_reviewer_assignee(self):
        self.refer()
        self.assertEqual(self.read(token=TOKEN_REVIEW)["version"], 1)
        self.assertEqual(self.read(token=TOKEN_ASSIGNEE)["version"], 1)
        with self.assertRaises(PermissionError):
            self.read(token=TOKEN_OTHER)

    def test_reviewer_finance_permission_revocation_removes_read_and_query(self):
        self.refer()
        self.service.users["reviewer-a"]["financeEdit"] = False
        with self.assertRaisesRegex(PermissionError, "revoked"):
            self.read(token=TOKEN_REVIEW)
        with self.assertRaisesRegex(PermissionError, "revoked"):
            self.query(token=TOKEN_REVIEW)
        self.assertEqual(self.read(token=TOKEN_ASSIGNEE)["version"], 1)
        self.service.users["reviewer-a"]["financeEdit"] = True
        denied = self.make_adapter(receipt=None, reviewers=frozenset())
        with self.assertRaisesRegex(PermissionError, "revoked"):
            self.read(adapter=denied, token=TOKEN_REVIEW)

    def test_default_adapter_read_existing_case_without_receipt_verifier(self):
        self.refer()
        no_source = self.make_adapter(receipt=None)
        self.assertEqual(self.read(adapter=no_source)["state"], "DEFICIENCY_ASSIGNED")
        with self.assertRaisesRegex(PermissionError, "independent authenticated"):
            self.refer(adapter=no_source, event_id="new-event-2")
        self.assertEqual(self.read(adapter=no_source)["version"], 1)

    def test_revoked_token_and_detached_account_fail_before_state_read(self):
        for bad in ("short", "not-a-valid-token", None, b"x" * 40):
            with self.subTest(bad=bad), self.assertRaises(PermissionError):
                self.refer(token=bad)
        self.service.sessions.pop(TOKEN_REVIEW)
        with self.assertRaises(PermissionError):
            self.refer()
        self.assertEqual(self.bridge.calls, 0)
        self.service.sessions[TOKEN_REVIEW] = "reviewer-a"
        self.service.users["reviewer-a"] = deepcopy(self.service.users["reviewer-a"])
        # account_for returns current registry account, still valid.
        self.assertEqual(self.refer()["state"], "DEFICIENCY_ASSIGNED")

    def test_host_account_proxy_not_actual_current_registry_denied(self):
        original = self.service.account_for
        self.service.account_for = lambda token: dict(
            original(token),
        )
        with self.assertRaisesRegex(PermissionError, "registry mismatch"):
            self.refer()

    def test_reviewer_allowlist_and_editor_finance_grant_required(self):
        denied = self.make_adapter(receipt=self.synthetic_source,
                                   reviewers=frozenset())
        with self.assertRaises(PermissionError):
            self.refer(adapter=denied)
        self.service.users["reviewer-a"]["financeEdit"] = False
        with self.assertRaises(PermissionError):
            self.refer()
        self.service.users["reviewer-a"]["financeEdit"] = True
        self.service.users["reviewer-a"]["role"] = "viewer"
        with self.assertRaises(PermissionError):
            self.refer()
        self.assertEqual(self.synthetic_source.calls, 0)

    def test_assignee_must_be_current_active_editor_project_member(self):
        for name in ("missing-user", "reviewer-a"):
            if name == "missing-user":
                with self.assertRaises(PermissionError):
                    self.refer(assignee_username=name)
        acct = self.service.users["assignee-a"]
        for role, projects in (
            ("viewer", [PROJECT]),
            ("editor", ["another-project"]),
            ("editor", None),
            ("editor", []),
            ("editor", [PROJECT, PROJECT]),
        ):
            acct["role"] = role
            acct["projects"] = projects
            with self.subTest(role=role, grants=projects), self.assertRaises(PermissionError):
                self.refer()
        self.assertEqual(self.synthetic_source.calls, 0)

    def test_missing_project_or_task_and_client_offline_cache_denied(self):
        initial_state = deepcopy(self.bridge.state)
        for updated in (
            {"projects": [], "tasks": initial_state["tasks"]},
            {"projects": initial_state["projects"], "tasks": []},
            {**initial_state, "__offline": True},
            {**initial_state, "__remoteRevision": "offline"},
        ):
            self.bridge.state = deepcopy(updated)
            with self.assertRaises(PermissionError):
                self.refer()
        self.bridge.state = initial_state
        self.bridge.connection["mode"] = "client"
        with self.assertRaises(PermissionError):
            self.refer()
        self.assertEqual(self.synthetic_source.calls, 0)

    def test_marker_missing_unversioned_or_pending_finance_review_denied(self):
        card = self.bridge.state["tasks"][0]
        original = deepcopy(card["mtrDeficiencyRequest"])
        for value in (
            None, {}, {**original, "revision": 0},
            {**original, "revision": True},
            {**original, "previousReceiptIds": [RECEIPT]},
            {**original, "receiptGeneration": "7"},
            {**original, "reviewState": "APPROVED"},
        ):
            card["mtrDeficiencyRequest"] = value
            with self.subTest(value=value), self.assertRaises(
                (PermissionError, HostDeficiencyError),
            ):
                self.refer()
        card["mtrDeficiencyRequest"] = {
            **original, "reviewState": "AWAITING_FINANCE_REVIEW",
        }
        current = self.snapshot()
        with self.assertRaisesRegex(PermissionError, "pending"):
            self.refer(expected_host_digest=current.digest)
        self.assertEqual(self.synthetic_source.calls, 0)

    def test_stale_host_saved_digest_and_revision_fail_closed(self):
        self.bridge.state["tasks"][0]["title"] = "changed without revision"
        with self.assertRaisesRegex(PermissionError, "stale"):
            self.refer(expected_host_digest=self.initial.digest)
        new = self.snapshot()
        with self.assertRaisesRegex(PermissionError, "stale"):
            self.refer(expected_host_revision=4, expected_host_digest=new.digest)
        self.assertEqual(self.synthetic_source.calls, 0)

    def test_verified_source_metadata_must_match_all_original_dimensions(self):
        for changes in (
            {"receipt_id": "different-receipt"},
            {"request_id": "different-request"},
            {"org_id": "different-org"},
            {"project_id": "different-project"},
            {"revision": 99},
            {"digest": "0" * 64},
            {"generation": 8},
            {"verified_by_adapter": False},
            {"source": "madar"},
            {"status": "approved"},
        ):
            self.synthetic_source.updates = changes
            with self.subTest(changes=changes), self.assertRaises(
                (PermissionError, ValueError),
            ):
                self.refer()
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0], 0)

    def test_no_assignee_resolution_with_missing_or_unsaved_fields(self):
        self.refer()
        self.save_correction(fields={"supplier": "saved-a"})
        for chosen in (
            frozenset({"units"}),
            frozenset({"foreign-field"}),
            frozenset(),
            {"supplier"},
        ):
            with self.subTest(chosen=chosen), self.assertRaises(
                (PermissionError, HostDeficiencyError),
            ):
                self.resolve(corrected_field_names=chosen)
        self.assertEqual(self.read()["state"], "DEFICIENCY_ASSIGNED")

    def test_assignee_scope_and_stale_case_version_denied(self):
        self.refer()
        self.save_correction()
        with self.assertRaises(PermissionError):
            self.resolve(token=TOKEN_OTHER)
        with self.assertRaises(PermissionError):
            self.resolve(token=TOKEN_REVIEW)
        with self.assertRaises(StoreConflict):
            self.resolve(case_version=2)
        self.assertEqual(self.resolve()["version"], 2)
        with self.assertRaises(StoreConflict):
            self.resolve(event_id="second-resolution", case_version=1)

    def test_replay_and_conflicting_referrals_fail_closed(self):
        first = self.refer()
        self.assertTrue(self.refer()["replayed"])
        self.assertEqual(self.read()["version"], first["version"])
        with self.assertRaises(StoreConflict):
            self.refer(event_id="second-referral")
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0], 1)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM audit_events").fetchone()[0], 1)

    def test_referral_concurrency_only_one_event_wins(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(lambda _: self.refer(), range(4)))
        self.assertEqual(sum(not x["replayed"] for x in outcomes), 1)
        self.assertEqual(sum(x["replayed"] for x in outcomes), 3)

    def test_resolution_requires_incremented_revision_and_fresh_saved_digest(self):
        self.refer()
        # Saved data changed but revision not incremented.
        self.save_correction(revision=3)
        with self.assertRaisesRegex(ValueError, "newer|changed"):
            self.resolve()
        self.save_correction(revision=4)
        previous = self.snapshot()
        self.assertEqual(self.resolve()["version"], 2)
        self.bridge.state["tasks"][0]["mtrDeficiencyFields"]["supplier"] = "changed-again"
        with self.assertRaisesRegex(PermissionError, "stale"):
            self.send(expected_host_revision=previous.revision,
                      expected_host_digest=previous.digest)

    def test_local_case_audit_corruption_denies_read_and_mutation(self):
        self.refer()
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE cases SET snapshot='{}'")
            conn.commit()
        with self.assertRaises(StoreError):
            self.read()
        self.save_correction()
        with self.assertRaises(StoreError):
            self.resolve()
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM audit_events").fetchone()[0], 1)

    def test_new_saved_task_changed_request_id_cannot_read_old_case(self):
        self.refer()
        self.bridge.state["tasks"][0]["mtrDeficiencyRequest"]["requestId"] = "other-request"
        current = self.snapshot()
        with self.assertRaises(StoreError):
            self.read(expected_host_revision=current.revision,
                      expected_host_digest=current.digest)

    def test_injecting_invalid_receipt_source_at_configuration_denied(self):
        for source in (True, "signed", object()):
            with self.subTest(source=source), self.assertRaises(HostDeficiencyError):
                self.make_adapter(receipt=source)
        with self.assertRaises(HostDeficiencyError):
            DeficiencyHostAdapter(
                self.service, self.store, org_id=ORG,
                reviewer_usernames={"reviewer-a"},
            )

    def test_no_ledger_or_official_network_from_full_flow(self):
        import socket
        with patch.object(socket, "socket", side_effect=AssertionError("no network")):
            self.refer()
            self.save_correction()
            self.resolve()
            self.send()
        with closing(sqlite3.connect(self.db)) as conn:
            tables = {record[0] for record in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        self.assertEqual(tables, {"cases", "audit_events"})
        self.assertEqual(self.read()["state"], "MANUAL_RESUBMISSION_INTENT_ONLY")


if __name__ == "__main__":
    unittest.main()
