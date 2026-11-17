"""Disposable, in-process host session/ACL/event E6 integration tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path
import tempfile
from threading import RLock
import unittest
from unittest.mock import patch

from lan import LanService
from mtr_internal_notification_store import InternalNotificationStore, NoticeConflictError
from mtr_lan_notification_adapter import (
    MtrLanNotificationAdapter, TrustedHostNoticeEvent, _sha_task,
)


PROJECT = "project-1"
TASK = "task-1"
REQUEST = "request-1"
EVENT = "event-1"
ORG = "host-organization"


def user(name, role, projects, *, enabled=True):
    return {
        "username": name, "role": role, "projects": projects,
        "internalNotificationsEnabled": enabled,
    }


class FakeBridge:
    def __init__(self):
        self._lock = RLock()
        self.state = {
            "projects": [{"id": PROJECT}, {"id": "project-2"}],
            "tasks": [{"id": TASK, "projectId": PROJECT,
                       "assignees": ["editor", "viewer"], "title": "synthetic"}],
        }

    def getState(self):
        return deepcopy(self.state)


class FakeHost:
    def __init__(self):
        self.bridge = FakeBridge()
        self.lock = RLock()
        self.users = {
            "admin": user("admin", "admin", None),
            "editor": user("editor", "editor", [PROJECT]),
            "viewer": user("viewer", "viewer", [PROJECT]),
            "out": user("out", "editor", ["project-2"]),
            "not-assigned": user("not-assigned", "editor", [PROJECT]),
            "opted-out": user("opted-out", "viewer", [PROJECT], enabled=False),
        }
        self.sessions = {"admin-token-123": "admin", "editor-token-123": "editor",
                         "viewer-token-123": "viewer", "out-token-123": "out",
                         "opted-out-token": "opted-out"}
        self.lookup_count = 0

    def account_for(self, token):
        self.lookup_count += 1
        name = self.sessions.get(token)
        if name is None or name not in self.users:
            raise PermissionError("Invalid or expired synthetic LAN session")
        return self.users[name]


class FakeHostEventJournal:
    def __init__(self, host):
        self.events = {
            EVENT: TrustedHostNoticeEvent(
                event_key=EVENT, task_id=TASK,
                task_sha256=_sha_task(host.bridge.getState()["tasks"][0]),
                project_id=PROJECT, original_request_id=REQUEST,
                event_kind="request_status_changed", actor_id="editor",
                occurred_at="2026-11-09T13:00:00Z",
                previous_revision=2, revision=3,
                previous_status="READY_TO_SUBMIT", status="UNDER_FINANCE_REVIEW",
            )
        }
        self.calls = 0

    def get_event(self, key):
        self.calls += 1
        return self.events.get(key)


class LanInternalNoticeAdapterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-lan-notice-synthetic-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        env = patch.dict(os.environ, {
            "APPDATA": str(root), "LOCALAPPDATA": str(root),
            "USERPROFILE": str(root), "HOME": str(root),
            "TEMP": str(root), "TMP": str(root),
        })
        env.start()
        self.addCleanup(env.stop)
        self.host = FakeHost()
        self.journal = FakeHostEventJournal(self.host)
        self.db = root / "inbox.sqlite3"
        self.store = InternalNotificationStore(self.db)
        self.adapter = MtrLanNotificationAdapter(
            self.host, self.store, org_id=ORG,
            trusted_event_source=self.journal.get_event,
        )

    def publish(self, token="editor-token-123", key=EVENT):
        return self.adapter.publish(token, key)

    def inbox(self, token="editor-token-123", **kwargs):
        return self.adapter.list_notifications(token, **kwargs)

    def test_host_derived_project_assignment_and_role_field_acl(self):
        result = self.publish()
        self.assertEqual(result["inserted"], 3)
        self.assertEqual(result["external_deliveries"], [])
        self.assertFalse(result["taraz_posting_performed"])
        admin = self.inbox("admin-token-123")
        editor = self.inbox()
        viewer = self.inbox("viewer-token-123")
        self.assertEqual(len(admin), 1)
        self.assertEqual(len(editor), 1)
        self.assertEqual(len(viewer), 1)
        self.assertEqual(editor[0]["actor_id"], "editor")
        self.assertIsNone(viewer[0]["actor_id"])
        self.assertEqual(viewer[0]["status"], "UNDER_FINANCE_REVIEW")
        self.assertEqual(self.inbox("out-token-123"), [])
        self.assertNotIn("receipt_reference", admin[0])
        self.assertNotIn("email", admin[0])
        self.assertEqual(admin[0]["channel"], "internal_only")

    def test_replay_is_idempotent_after_store_restart(self):
        self.assertEqual(self.publish()["inserted"], 3)
        restarted = MtrLanNotificationAdapter(
            self.host, InternalNotificationStore(self.db), org_id=ORG,
            trusted_event_source=self.journal.get_event,
        )
        self.assertEqual(restarted.publish("editor-token-123", EVENT)["replayed"], 3)
        self.assertEqual(len(self.inbox()), 1)

    def test_changed_payload_same_event_key_conflicts_atomically(self):
        self.publish()
        original = self.journal.events[EVENT]
        self.journal.events[EVENT] = replace(original, status="DEFICIENCY_ASSIGNED")
        with self.assertRaises(NoticeConflictError):
            self.publish()
        self.assertEqual(self.inbox()[0]["status"], "UNDER_FINANCE_REVIEW")

    def test_concurrent_duplicate_events_are_single_inserts(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.publish(), range(8)))
        self.assertEqual(sum(row["inserted"] for row in results), 3)
        self.assertEqual(sum(row["replayed"] for row in results), 21)
        self.assertEqual(len(self.inbox()), 1)

    def test_expired_and_forged_session_rejected_before_event_lookup(self):
        calls = self.journal.calls
        with self.assertRaises(PermissionError):
            self.publish("bad-session-x")
        self.assertEqual(self.journal.calls, calls)
        self.host.sessions.pop("editor-token-123")
        with self.assertRaises(PermissionError):
            self.publish()
        with self.assertRaises(PermissionError):
            self.inbox()

    def test_viewer_cannot_publish_or_override_event_data(self):
        with self.assertRaises(PermissionError):
            self.publish("viewer-token-123")
        with self.assertRaises(TypeError):
            self.adapter.publish("editor-token-123", EVENT, actor_id="viewer")
        with self.assertRaises(ValueError):
            self.adapter.publish("editor-token-123", {"event_key": EVENT})
        with self.assertRaises(ValueError):
            self.adapter.publish("editor-token-123", "unsafe/../event")

    def test_untrusted_provider_result_and_actor_rejected(self):
        saved = self.journal.events[EVENT]
        self.journal.events[EVENT] = {"event_key": EVENT, "actor_id": "editor"}
        with self.assertRaises(PermissionError):
            self.publish()
        self.journal.events[EVENT] = replace(saved, actor_id="out")
        with self.assertRaises(PermissionError):
            self.publish()
        self.journal.events[EVENT] = replace(saved, event_key="different-event")
        with self.assertRaises(PermissionError):
            self.publish()

    def test_stale_saved_task_and_removed_project_fail_closed(self):
        self.host.bridge.state["tasks"][0]["title"] = "modified after event"
        with self.assertRaises(PermissionError):
            self.publish()
        self.host.bridge.state["tasks"][0]["title"] = "synthetic"
        self.host.bridge.state["projects"] = [{"id": "project-2"}]
        with self.assertRaises(PermissionError):
            self.publish()

    def test_unassigned_editor_denied_publish_and_unrelated_users_not_notified(self):
        self.host.sessions["unassigned-token-123"] = "not-assigned"
        with self.assertRaises(PermissionError):
            self.publish("unassigned-token-123")
        self.publish()
        self.assertEqual(self.inbox("unassigned-token-123"), [])

    def test_project_grant_revocation_denies_list_and_mark(self):
        self.publish()
        notice_id = self.inbox()[0]["notice_id"]
        self.host.users["editor"]["projects"] = []
        self.assertEqual(self.inbox(), [])
        with self.assertRaises(PermissionError):
            self.adapter.mark_read("editor-token-123", notice_id)
        with self.assertRaises(PermissionError):
            self.publish()

    def test_role_downgrade_redacts_at_read_time_and_blocks_publish(self):
        self.publish()
        self.assertEqual(self.inbox()[0]["actor_id"], "editor")
        self.host.users["editor"]["role"] = "viewer"
        self.assertIsNone(self.inbox()[0]["actor_id"])
        with self.assertRaises(PermissionError):
            self.publish()

    def test_per_user_private_field_grants_only_attenuate_role_permissions(self):
        self.publish()
        self.assertEqual(self.inbox()[0]["actor_id"], "editor")
        self.host.users["editor"]["internalNotificationFields"] = ["status"]
        self.assertIsNone(self.inbox()[0]["actor_id"])
        self.host.users["editor"]["internalNotificationFields"] = [
            "status", "deficiency_summary",
        ]
        with self.assertRaises(PermissionError):
            self.inbox()
        with self.assertRaises(PermissionError):
            self.publish()

    def test_private_deficiency_summary_only_admin_can_read(self):
        old = self.journal.events[EVENT]
        self.journal.events[EVENT] = replace(
            old, event_kind="deficiency_assigned", status="DEFICIENCY_ASSIGNED",
            assigned_user_id="viewer", deficiency_summary="private synthetic detail",
        )
        self.publish("admin-token-123")
        self.assertEqual(self.inbox("admin-token-123")[0]["deficiency_summary"],
                         "private synthetic detail")
        self.assertIsNone(self.inbox()[0]["deficiency_summary"])
        self.assertIsNone(self.inbox("viewer-token-123")[0]["deficiency_summary"])

    def test_deficiency_assignee_must_match_current_host_assignment(self):
        old = self.journal.events[EVENT]
        self.journal.events[EVENT] = replace(
            old, event_kind="deficiency_assigned", status="DEFICIENCY_ASSIGNED",
            assigned_user_id="out",
        )
        with self.assertRaises(PermissionError):
            self.publish()

    def test_unsupported_official_finance_statuses_rejected(self):
        event = self.journal.events[EVENT]
        for status in ("FINANCE_APPROVED", "FINANCE_REJECTED", "OFFICIALLY_POSTED"):
            with self.subTest(status=status):
                self.journal.events[EVENT] = replace(event, status=status)
                with self.assertRaises(PermissionError):
                    self.publish()
        self.assertEqual(self.inbox(), [])

    def test_disabled_internal_notifications_deny_read_and_recipient(self):
        self.publish()
        with self.assertRaises(PermissionError):
            self.inbox("opted-out-token")
        self.assertEqual(len(self.inbox()), 1)
        note = self.inbox()[0]["notice_id"]
        self.host.users["editor"]["internalNotificationsEnabled"] = False
        with self.assertRaises(PermissionError):
            self.inbox()
        with self.assertRaises(PermissionError):
            self.adapter.mark_read("editor-token-123", note)

    def test_only_current_user_can_mark_read(self):
        self.publish()
        editor_id = self.inbox()[0]["notice_id"]
        with self.assertRaises(PermissionError):
            self.adapter.mark_read("viewer-token-123", editor_id)
        marked = self.adapter.mark_read("editor-token-123", editor_id)
        self.assertTrue(marked["marked_read"])
        self.assertTrue(self.inbox()[0]["is_read"])
        self.assertTrue(self.adapter.mark_read("editor-token-123", editor_id)["already_read"])

    def test_no_recipient_flag_means_no_notices(self):
        for account in self.host.users.values():
            account.pop("internalNotificationsEnabled", None)
        result = self.publish()
        self.assertEqual(result["inserted"], 0)

    def test_registry_account_mismatch_and_invalid_role_fail_closed(self):
        original = self.host.users["editor"]
        self.host.account_for = lambda _: deepcopy(original)
        with self.assertRaises(PermissionError):
            self.publish()
        self.host.account_for = lambda _: original
        original["role"] = "unknown-role"
        with self.assertRaises(PermissionError):
            self.publish()

    def test_real_lanservice_session_on_synthetic_host_without_listener(self):
        # Actual LanService.account_for checks a PBKDF2-authenticated session.
        # No HTTP server is started; accounts and database live only in temp.
        bridge = FakeBridge()
        service = LanService(bridge, self.db.parent / "synthetic-users.json",
                             bind="127.0.0.1", port=0)
        service.setup_owner("owner", "synthetic-owner-password-long")
        token = service.authenticate("owner", "synthetic-owner-password-long")["token"]
        service.users["owner"]["internalNotificationsEnabled"] = True
        source = TrustedHostNoticeEvent(
            event_key="real-session-event", task_id=TASK,
            task_sha256=_sha_task(bridge.getState()["tasks"][0]),
            project_id=PROJECT, original_request_id=REQUEST,
            event_kind="request_status_changed", actor_id="owner",
            occurred_at="2026-11-09T13:00:00Z",
            previous_revision=0, revision=1,
            previous_status="DRAFT", status="READY_TO_SUBMIT",
        )
        adapter = MtrLanNotificationAdapter(
            service, self.store, org_id=ORG,
            trusted_event_source=lambda key: source if key == source.event_key else None,
        )
        self.assertEqual(adapter.publish(token, source.event_key)["inserted"], 1)
        self.assertEqual(adapter.list_notifications(token)[0]["status"],
                         "READY_TO_SUBMIT")
        service.sessions.pop(token)
        with self.assertRaises(PermissionError):
            adapter.list_notifications(token)


if __name__ == "__main__":
    unittest.main()
