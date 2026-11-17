"""Synthetic host-token E5 adapter tests; no LAN, Taraz, or real user data."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest

from mtr_amendment_host_adapter import (
    AmendmentHostAdapter, HostCommandError, _snapshot,
)
from mtr_amendment_store import AmendmentConflict, AmendmentStore
from mtr_amendment_review_preview import AmendmentPreviewError

ORG = "org-synthetic"
PROJECT = "project-1"
TASK = "task-1"
TOKEN = "test_session_token_" + "x" * 32
T0, T1, T2 = (
    "2026-11-09T15:00:00Z", "2026-11-09T15:01:00Z",
    "2026-11-09T15:02:00Z",
)


class SyntheticBridge:
    def __init__(self):
        self._lock = threading.RLock()
        self.connection = {"mode": "solo"}
        self.calls = 0
        self.state = {
            "projects": [{"id": PROJECT, "name": "Synthetic project"}],
            "tasks": [{
                "id": TASK, "projectId": PROJECT, "title": "Synthetic card",
                "mtrFinanceOriginal": {
                    "requestId": "original-1", "submitted": True,
                    "fields": {
                        "partyId": "old", "quantity": 2, "notes": "original",
                    },
                },
            }],
        }

    def getState(self):
        assert self._lock._is_owned(), "must hold bridge lock"
        self.calls += 1
        return deepcopy(self.state)


class SyntheticLanService:
    """Faithful account_for shape; no real socket, registry or profile."""
    def __init__(self, bridge):
        self.lock = threading.RLock()
        self.bridge = bridge
        self.sessions = {TOKEN: "reviewer-a"}
        self.accounts = {
            "reviewer-a": {
                "username": "reviewer-a", "role": "editor",
                "projects": [PROJECT], "financeEdit": True,
            }
        }
        self.auth_calls = 0

    def account_for(self, token):
        assert self.lock._is_owned(), "must hold LanService.lock"
        self.auth_calls += 1
        name = self.sessions.get(token)
        if not name or name not in self.accounts:
            raise PermissionError("expired or revoked host session")
        return self.accounts[name]


class E5HostAdapterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-e5-host-synthetic-")
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "isolated-amendments.sqlite3"
        self.store = AmendmentStore(self.db)
        self.bridge = SyntheticBridge()
        self.service = SyntheticLanService(self.bridge)
        self.adapter = AmendmentHostAdapter(
            self.service, self.store, org_id=ORG,
            finance_reviewer_usernames=frozenset({"reviewer-a"}),
        )

    def command(self, action, **overrides):
        current, _ = _snapshot(self.bridge.state, PROJECT, TASK)
        base = dict(
            action=action, projectId=PROJECT, taskId=TASK,
            expectedTaskDigest=current, amendmentId="amendment-a",
        )
        if action == "create":
            base.update(
                proposedFields={"partyId": "new"},
                createKey="create-key-00001",
                acknowledgedOpen=False, acknowledgedDuplicate=False,
                acknowledgedAt=T0, previousRejectedAmendmentId=None,
            )
        elif action == "review":
            base.update(
                reviewMode="re_review_baseline",
                expectedRowRevision=1, chosenValues={},
                operationKey="review-key-00001", occurredAt=T1,
                acknowledgedDependencyFields=[],
                acknowledgedRevisionChange=True,
            )
        elif action == "manual_unsent_intent":
            base.update(
                expectedRowRevision=1,
                sendKey="send-key-00001",
                explicitManualAction=True, occurredAt=T1,
            )
        base.update(overrides)
        return base

    def call(self, action="query", *, token=TOKEN, adapter=None, **updates):
        data = self.command(action, **updates)
        return (adapter or self.adapter).execute(
            token=token,
            command_json=json.dumps(data, sort_keys=True, ensure_ascii=False),
        )

    def create(self, **kwargs):
        return self.call("create", **kwargs)

    def test_create_query_uses_saved_original_and_host_identity_only(self):
        result = self.create()
        self.assertEqual(result["state"], "DRAFT")
        self.assertEqual(result["originalRequestId"], "original-1")
        self.assertEqual(result["rowRevision"], 1)
        self.assertTrue(result["hostAuthenticated"])
        self.assertTrue(result["hostFinanceReviewerAssigned"])
        self.assertFalse(result["sentToTaraz"])
        self.assertFalse(result["officialFinancePosted"])
        self.assertFalse(result["tarazReceiptVerified"])
        self.assertEqual(result["transportState"], "NOT_SENT_BY_ADAPTER")
        read = self.call()
        self.assertEqual(read["original"]["orgId"], ORG)
        self.assertEqual(read["original"]["projectId"], PROJECT)
        self.assertEqual(read["original"]["fields"]["partyId"], "old")
        self.assertEqual(read["originalRevisionAtReview"], read["original"]["revision"])
        self.assertEqual(read["auditCount"], 1)
        self.assertGreater(self.service.auth_calls, 1)
        self.assertGreater(self.bridge.calls, 1)

    def test_manual_intent_is_not_network_or_ledger_posting(self):
        self.create()
        response = self.call("manual_unsent_intent")
        self.assertEqual(response["state"], "MANUAL_SEND_INTENT")
        self.assertEqual(response["rowRevision"], 2)
        self.assertEqual(response["sendKey"], "send-key-00001")
        self.assertFalse(response["sentToTaraz"])
        self.assertFalse(response["officialFinancePosted"])
        self.assertFalse(response["tarazReceiptVerified"])
        self.assertEqual(self.call()["state"], "MANUAL_SEND_INTENT")
        replay = self.call("manual_unsent_intent", expectedRowRevision=2)
        self.assertTrue(replay["idempotent"])
        self.assertFalse(replay["sentToTaraz"])

    def test_manual_action_false_and_truthy_int_both_denied(self):
        self.create()
        for value in (False, 1, 0, None):
            with self.subTest(value=value), self.assertRaises(
                (PermissionError, HostCommandError)
            ):
                self.call("manual_unsent_intent", explicitManualAction=value)
        self.assertEqual(self.call()["state"], "DRAFT")

    def test_strict_json_rejects_duplicate_nested_keys_and_unknown_actor_fields(self):
        payload = self.command("query")
        encoded = json.dumps(payload)
        duplicate = encoded[:-1] + ',"taskId":"other-task"}'
        for bad in (
            duplicate,
            encoded[:-1] + ',"orgId":"foreign"}',
            encoded[:-1] + ',"principal":{"role":"admin"}}',
            encoded[:-1] + ',"verifiedTarazSource":true}',
            encoded[:-1] + ',"receipt":{"status":"rejected"}}',
            encoded[:-1] + ',"currentOriginal":{"submitted":true}}',
            '{"action":"query","nested":{"user":"alice","user":"bob"}}',
            encoded + "\n" * 9000,
            '[1,2,3]', '{"action":NaN}', "{}",
        ):
            with self.subTest(bad=bad[:35]), self.assertRaises(HostCommandError):
                self.adapter.execute(token=TOKEN, command_json=bad)
        with self.assertRaises(HostCommandError):
            self.adapter.execute(token=TOKEN, command_json=b"{}")
        with self.assertRaises(HostCommandError):
            self.adapter.execute(token=TOKEN, command_json="\ud800")

    def test_nested_duplicate_json_in_proposed_fields_rejected(self):
        raw = json.dumps(self.command("create"))
        raw = raw.replace('"partyId": "new"', '"partyId":"new","partyId":"forged"')
        with self.assertRaises(HostCommandError):
            self.adapter.execute(token=TOKEN, command_json=raw)
        self.assertEqual(self.service.auth_calls, 0)

    def test_client_and_offline_cached_bridge_rejected_before_write(self):
        self.bridge.connection["mode"] = "client"
        with self.assertRaises(PermissionError):
            self.create()
        self.assertEqual(self.service.auth_calls, 0)
        self.bridge.connection["mode"] = "solo"
        self.bridge.state["__offline"] = True
        with self.assertRaises(PermissionError):
            self.create()
        self.assertEqual(self.service.auth_calls, 1)

    def test_editor_malformed_project_grants_fail_closed(self):
        for grants in (
            ["project-1", {}], [PROJECT, 123], [PROJECT, PROJECT],
            ["project-1", "other"] * 260,
        ):
            self.service.accounts["reviewer-a"]["projects"] = grants
            with self.subTest(grants=repr(grants)[:30]), self.assertRaises(
                PermissionError
            ):
                self.create()

    def test_no_taraz_rejection_or_auto_send_actions(self):
        for action in ("rejection", "taraz_rejection", "send", "post",
                       "automatic_send", "finance_approve"):
            with self.subTest(action=action), self.assertRaises(HostCommandError):
                self.call(action)
        self.assertEqual(self.service.auth_calls, 0)

    def test_invalid_revoked_token_or_missing_host_account_denied(self):
        with self.assertRaises(PermissionError):
            self.call("create", token="invalid" * 8)
        with self.assertRaises(PermissionError):
            self.call("create", token="x")
        self.service.sessions.clear()
        with self.assertRaises(PermissionError):
            self.call("create")
        self.assertEqual(self.bridge.calls, 0)

    def test_editor_without_finance_edit_or_viewer_denied(self):
        for role, grant in (("viewer", True), ("editor", False),
                            ("editor", 1), ("unknown", True)):
            self.service.accounts["reviewer-a"]["role"] = role
            self.service.accounts["reviewer-a"]["financeEdit"] = grant
            with self.subTest(role=role, grant=grant), self.assertRaises(PermissionError):
                self.create()

    def test_project_grant_absent_none_or_mismatched_denied(self):
        for grants in (None, [], ["project-other"], [PROJECT, PROJECT]):
            self.service.accounts["reviewer-a"]["projects"] = grants
            with self.subTest(grants=grants), self.assertRaises(PermissionError):
                self.create()
        self.assertEqual(self.bridge.calls, 0)

    def test_explicit_finance_reviewer_allowlist_blocks_review_and_send(self):
        without = AmendmentHostAdapter(
            self.service, self.store, org_id=ORG,
            finance_reviewer_usernames=frozenset(),
        )
        first = self.call("create", adapter=without)
        self.assertFalse(first["hostFinanceReviewerAssigned"])
        with self.assertRaises(PermissionError):
            self.call("review", adapter=without)
        with self.assertRaises(PermissionError):
            self.call("manual_unsent_intent", adapter=without)

    def test_saved_card_and_project_membership_required(self):
        self.bridge.state["tasks"][0]["projectId"] = "other-project"
        with self.assertRaises(PermissionError):
            self.create()
        self.bridge.state["tasks"][0]["projectId"] = PROJECT
        self.bridge.state["projects"] = []
        with self.assertRaises(PermissionError):
            self.create()

    def test_fake_submitted_marker_or_missing_metadata_denied(self):
        card = self.bridge.state["tasks"][0]
        for marker in (
            None, {}, {"requestId": "original-1", "submitted": False,
                       "fields": {"partyId": "old"}},
            {"requestId": "original-1", "submitted": 1,
             "fields": {"partyId": "old"}},
            {"requestId": "original-1", "submitted": True,
             "fields": {"partyId": {"unsafe": "nested"}}},
        ):
            card["mtrFinanceOriginal"] = marker
            with self.subTest(marker=marker), self.assertRaises(
                (PermissionError, HostCommandError)
            ):
                self.create()

    def test_saved_card_edit_invalidates_stale_create_command(self):
        command = self.command("create")
        self.bridge.state["tasks"][0]["title"] = "Concurrent saved edit"
        with self.assertRaises(PermissionError):
            self.adapter.execute(token=TOKEN, command_json=json.dumps(command))
        self.assertEqual(self.service.auth_calls, 1)

    def test_old_task_digest_cannot_be_reused_after_saved_card_edit(self):
        first = self.create()
        before = self.command("manual_unsent_intent")
        self.bridge.state["tasks"][0]["title"] = "Later edit"
        with self.assertRaises(PermissionError):
            self.adapter.execute(token=TOKEN, command_json=json.dumps(before))
        with self.assertRaises(AmendmentConflict):
            self.call("manual_unsent_intent")
        self.assertEqual(self.store.get_amendment(
            principal=self._trusted_original_principal(),
            amendment_id="amendment-a",
        )["state"], "DRAFT")

    def test_changed_saved_original_request_cannot_reattach_prior_draft(self):
        self.create()
        self.bridge.state["tasks"][0]["mtrFinanceOriginal"]["requestId"] = "other-request"
        with self.assertRaises(PermissionError):
            self.call("query")
        with self.assertRaises(PermissionError):
            self.call("manual_unsent_intent")

    def test_changed_create_payload_under_same_idempotency_key_rejected(self):
        self.create()
        with self.assertRaises(AmendmentConflict):
            self.create(proposedFields={"partyId": "different"})
        with self.assertRaises(AmendmentConflict):
            self.create(createKey="create-key-00002")
        self.assertEqual(self.call()["state"], "DRAFT")

    def _trusted_original_principal(self):
        from mtr_amendment_store import TrustedPrincipal
        import hashlib
        return TrustedPrincipal(
            user_id="reviewer-a", org_id=ORG, role="editor",
            session_id="lan-" + hashlib.sha256(
                b"MTR-E5-session-v1\x00" + TOKEN.encode("ascii")
            ).hexdigest()[:40],
            project_ids=frozenset({PROJECT}),
            permissions=frozenset({
                "mtr.amendment.read", "mtr.amendment.create",
                "mtr.amendment.review", "mtr.amendment.send",
            }),
            authenticated=True, session_valid=True, active=True,
        )

    def test_re_review_stale_card_then_manual_intent_after_resolution(self):
        self.create()
        self.bridge.state["tasks"][0]["title"] = "New saved card title"
        changed = self.call("review")
        self.assertEqual(changed["rowRevision"], 2)
        self.assertEqual(changed["state"], "DRAFT")
        manual = self.call("manual_unsent_intent", expectedRowRevision=2)
        self.assertEqual(manual["state"], "MANUAL_SEND_INTENT")
        self.assertFalse(manual["sentToTaraz"])

    def test_re_review_cannot_skip_explicit_revision_ack(self):
        self.create()
        self.bridge.state["tasks"][0]["title"] = "Changed"
        with self.assertRaises(AmendmentPreviewError):
            self.call("review", acknowledgedRevisionChange=False)

    def test_host_org_is_not_from_client_body(self):
        self.create()
        other = AmendmentHostAdapter(
            self.service, self.store, org_id="other-org",
            finance_reviewer_usernames=frozenset({"reviewer-a"}),
        )
        with self.assertRaises(PermissionError):
            self.call("query", adapter=other)
        with self.assertRaises(HostCommandError):
            self.adapter.execute(token=TOKEN, command_json=json.dumps({
                **self.command("query"), "orgId": "other-org",
            }))

    def test_same_query_and_create_do_not_expose_token_or_password(self):
        self.service.accounts["reviewer-a"]["passwordHash"] = "private-secret"
        created = self.create()
        queried = self.call()
        for result in (created, queried):
            self.assertNotIn(TOKEN, repr(result))
            self.assertNotIn("private-secret", repr(result))

    def test_concurrent_identical_create_one_write_one_replay(self):
        command = json.dumps(self.command("create"))
        gate = threading.Barrier(2)
        def run():
            gate.wait()
            return self.adapter.execute(token=TOKEN, command_json=command)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(run), pool.submit(run)
            result = [a.result(timeout=15), b.result(timeout=15)]
        self.assertEqual(sorted(x["idempotent"] for x in result), [False, True])

    def test_concurrent_conflicting_manual_intents_only_one_wins(self):
        self.create()
        gate = threading.Barrier(2)
        def run(send_key):
            gate.wait()
            try:
                return ("saved", self.call("manual_unsent_intent", sendKey=send_key))
            except AmendmentConflict:
                return ("conflict", None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(run, "send-key-00001")
            b = pool.submit(run, "send-key-00002")
            results = [a.result(timeout=15), b.result(timeout=15)]
        self.assertEqual(sorted(row[0] for row in results), ["conflict", "saved"])
        self.assertEqual(self.call()["state"], "MANUAL_SEND_INTENT")

    def test_competing_saved_card_edit_rechecks_current_host_revision(self):
        command = json.dumps(self.command("create"))
        started = threading.Event()
        def issue():
            started.set()
            return self.adapter.execute(token=TOKEN, command_json=command)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.service.lock, self.bridge._lock:
                pending = pool.submit(issue)
                self.assertTrue(started.wait(2))
                self.bridge.state["tasks"][0]["title"] = "Saved while host locks held"
            # Await only after releasing the host locks: no stale snapshot.
            with self.assertRaises(PermissionError):
                pending.result(timeout=10)
        self.assertEqual(self.service.auth_calls, 1)
        with self.assertRaises(PermissionError):
            self.store.get_amendment(
                principal=self._trusted_original_principal(),
                amendment_id="amendment-a",
            )

    def test_revocation_after_create_blocks_query_and_manual_intent(self):
        self.create()
        self.service.sessions.clear()
        for action in ("query", "manual_unsent_intent", "review"):
            with self.subTest(action=action), self.assertRaises(PermissionError):
                self.call(action)

    def test_task_reassignment_rejects_other_project_even_same_task_id(self):
        self.create()
        self.bridge.state["tasks"][0]["projectId"] = "project-other"
        with self.assertRaises(PermissionError):
            self.call()

    def test_original_saved_state_never_mutated_by_adapter(self):
        before = deepcopy(self.bridge.state)
        self.create()
        self.call("manual_unsent_intent")
        self.assertEqual(before, self.bridge.state)


if __name__ == "__main__":
    unittest.main()
