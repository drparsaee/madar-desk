"""Synthetic host-only E6 SQLite inbox acceptance/fault tests (no real profile)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from mtr_internal_notification_policy import plan_internal_notifications
from mtr_internal_notification_store import (
    HostPrincipal, HostRecipientGrant, InternalNotificationStore,
    NoticeConflictError, NoticeContractError,
)


ORG = "synthetic-org-1"
PROJECT = "synthetic-project-1"
REQUEST = "synthetic-request-1"
ACTOR = "synthetic-finance-actor"
EVENT_KEY = "synthetic-event-100"
ROOT = Path(__file__).resolve().parents[1]


def publisher(*, org=ORG, project=PROJECT, actor=ACTOR, **changes):
    fields = {
        "organization_id": org, "user_id": "synthetic-host-operator",
        "role": "editor", "readable_project_ids": frozenset({project}),
        "visible_fields": frozenset({"status", "actor_id", "amendment_id",
                                     "deficiency_summary"}),
        "host_verified": True, "authenticated": True, "can_publish": True,
        "verified_event_actor_id": actor,
    }
    return HostPrincipal(**{**fields, **changes})


def viewer(user, *, org=ORG, projects=(PROJECT,), fields=("status", "actor_id",
                                                          "amendment_id"), **changes):
    principal = {
        "organization_id": org, "user_id": user, "role": "viewer",
        "readable_project_ids": frozenset(projects),
        "visible_fields": frozenset(fields), "host_verified": True,
        "authenticated": True, "can_read": True, "can_mark_read": True,
    }
    return HostPrincipal(**{**principal, **changes})


def entitlement(user, *, org=ORG, projects=(PROJECT,), requests=(REQUEST,),
                fields=("status", "actor_id", "amendment_id"), **changes):
    data = {
        "organization_id": org, "user_id": user, "role": "viewer",
        "readable_project_ids": frozenset(projects),
        "related_request_ids": frozenset(requests),
        "visible_fields": frozenset(fields),
        "host_verified": True, "notifications_enabled": True,
    }
    return HostRecipientGrant(**{**data, **changes})


def policy_plan(users=("alice",), *, org=ORG, project=PROJECT,
                request=REQUEST, event_key=EVENT_KEY, kind="amendment_status_changed",
                status="UNDER_FINANCE_REVIEW", actor=ACTOR, extra=None):
    event = {
        "organization_id": org, "project_id": project,
        "server_read_authorized": True, "server_event_trusted": True,
        "event_key": event_key, "original_request_id": request,
        "event_kind": kind, "actor_id": actor,
        "previous_status": "AWAITING_RECEIPT", "status": status,
        "occurred_at": "2026-11-09T12:00:00Z",
        "previous_revision": 2, "revision": 3,
        "amendment_id": "synthetic-amendment-1",
        "assigned_user_id": "alice",
        "deficiency_summary": "Synthetic confidential deficiency",
    }
    if extra:
        event.update(extra)
    recipients = [{
        "user_id": user, "role": "viewer", "organization_id": org,
        "server_read_authorized": True,
        "readable_project_ids": [project],
        "related_request_ids": [request],
        "internal_notifications_enabled": True,
        "visible_fields": ["status", "actor_id", "amendment_id",
                           "deficiency_summary"],
    } for user in users]
    scope = {
        "organization_id": org, "server_scoped": True,
        "actor_authenticated": True, "actor_authorized": True,
        "actor_id": actor, "actor_role": "editor",
        "readable_project_ids": [project],
        "visible_fields": ["status", "actor_id", "amendment_id",
                           "deficiency_summary"],
        "notify_authorized": True, "dedup_snapshot_trusted": True,
        "authoritative_revision": 3,
    }
    return plan_internal_notifications(event, recipients, scope=scope,
                                       seen_event_keys=[])


class NotificationStoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtr-e6-notice-store-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = patch.dict(os.environ, {
            "APPDATA": str(self.root), "LOCALAPPDATA": str(self.root),
            "USERPROFILE": str(self.root), "HOME": str(self.root),
            "TEMP": str(self.root), "TMP": str(self.root),
        })
        env.start()
        self.addCleanup(env.stop)
        self.path = self.root / "synthetic-inbox.sqlite3"
        self.store = InternalNotificationStore(self.path)

    def publish(self, plan=None, *, users=("alice",), actor=None,
                recipient_grants=None, principal=None, project=PROJECT):
        if plan is None:
            plan = policy_plan(users)
        if recipient_grants is None:
            recipient_grants = [entitlement(user) for user in users]
        return self.store.publish_plan(
            plan, principal=principal or publisher(actor=actor or ACTOR),
            project_id=project, recipient_grants=recipient_grants,
        )

    def count(self, table):
        self.assertIn(table, {"inbox_notices", "inbox_reads", "inbox_audit"})
        with closing(sqlite3.connect(self.path)) as conn:
            return conn.execute("SELECT count(*) FROM " + table).fetchone()[0]

    def test_publish_real_policy_output_and_inbox_read_is_internal_only(self):
        result = self.publish(users=("alice", "bob"))
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["replayed"], 0)
        self.assertEqual(result["external_deliveries"], [])
        self.assertFalse(result["taraz_posting_performed"])
        alice = self.store.list_notifications(principal=viewer("alice"))
        self.assertEqual(len(alice), 1)
        self.assertEqual(alice[0]["channel"], "internal_only")
        self.assertEqual(alice[0]["event_key"], EVENT_KEY)
        self.assertEqual(alice[0]["status"], "UNDER_FINANCE_REVIEW")
        self.assertEqual(alice[0]["actor_id"], ACTOR)
        self.assertFalse(alice[0]["is_read"])
        self.assertNotIn("receipt_reference", alice[0])
        self.assertNotIn("document_id", alice[0])
        self.assertEqual(self.count("inbox_notices"), 2)
        self.assertEqual(self.count("inbox_audit"), 2)

    def test_restart_persists_inbox_and_idempotent_same_payload_replay(self):
        plan = policy_plan(("alice",))
        first = self.publish(plan)
        reloaded = InternalNotificationStore(self.path)
        self.assertEqual(first["inserted"], 1)
        second = reloaded.publish_plan(
            deepcopy(plan), principal=publisher(), project_id=PROJECT,
            recipient_grants=[entitlement("alice")],
        )
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["replayed"], 1)
        self.assertEqual(self.count("inbox_notices"), 1)
        self.assertEqual(self.count("inbox_audit"), 1)
        self.assertEqual(len(reloaded.list_notifications(principal=viewer("alice"))), 1)

    def test_same_recipient_event_key_different_payload_fails_and_keeps_old_data(self):
        original = policy_plan(("alice",))
        self.publish(original)
        changed = deepcopy(original)
        changed["notifications"][0]["status"] = "FINANCE_APPROVED"
        with self.assertRaises(NoticeConflictError):
            self.publish(changed)
        self.assertEqual(self.count("inbox_notices"), 1)
        self.assertEqual(self.count("inbox_audit"), 1)
        notes = self.store.list_notifications(principal=viewer("alice"))
        self.assertEqual(notes[0]["status"], "UNDER_FINANCE_REVIEW")

    def test_atomic_multi_recipient_conflict_rolls_back_other_new_recipient(self):
        self.publish(policy_plan(("alice",)))
        conflicted = policy_plan(("bob", "alice"))
        conflicted["notifications"][1]["status"] = "FINANCE_APPROVED"
        with self.assertRaises(NoticeConflictError):
            self.publish(conflicted, users=("bob", "alice"))
        self.assertEqual(self.count("inbox_notices"), 1)
        self.assertEqual(self.count("inbox_audit"), 1)
        self.assertEqual(self.store.list_notifications(principal=viewer("bob")), [])

    def test_mark_read_requires_owner_acl_is_persistent_and_audit_append_only(self):
        self.publish(users=("alice", "bob"))
        notice_id = self.store.list_notifications(principal=viewer("alice"))[0]["notice_id"]
        mark = self.store.mark_read(notice_id, principal=viewer("alice"))
        self.assertTrue(mark["marked_read"])
        self.assertFalse(mark["already_read"])
        other = self.store.mark_read(notice_id, principal=viewer("alice"))
        self.assertFalse(other["marked_read"])
        self.assertTrue(other["already_read"])
        reloaded = InternalNotificationStore(self.path)
        self.assertTrue(reloaded.list_notifications(principal=viewer("alice"))[0]["is_read"])
        self.assertFalse(reloaded.list_notifications(principal=viewer("bob"))[0]["is_read"])
        self.assertEqual(self.count("inbox_reads"), 1)
        self.assertEqual(self.count("inbox_audit"), 3)  # 2 insert + 1 read

    def test_immutable_notice_read_and_audit_rows_reject_updates_and_deletes(self):
        self.publish()
        note_id = self.store.list_notifications(principal=viewer("alice"))[0]["notice_id"]
        self.store.mark_read(note_id, principal=viewer("alice"))
        with closing(sqlite3.connect(self.path)) as conn:
            for table in ("inbox_notices", "inbox_reads", "inbox_audit"):
                with self.subTest(table=table):
                    with self.assertRaises(sqlite3.DatabaseError):
                        conn.execute("DELETE FROM " + table)
                    with self.assertRaises(sqlite3.DatabaseError):
                        conn.execute("UPDATE " + table + " SET organization_id='forged'")
            self.assertEqual(conn.execute("SELECT count(*) FROM inbox_audit").fetchone()[0], 2)

    def test_cross_organization_project_user_read_and_mark_idor_denied(self):
        self.publish(users=("alice",))
        note_id = self.store.list_notifications(principal=viewer("alice"))[0]["notice_id"]
        self.assertEqual(self.store.list_notifications(principal=viewer("other-user")), [])
        self.assertEqual(self.store.list_notifications(principal=viewer("alice", org="other-org")), [])
        self.assertEqual(self.store.list_notifications(principal=viewer(
            "alice", projects=("other-project",))), [])
        for bad in (
            viewer("other-user"), viewer("alice", org="other-org"),
            viewer("alice", projects=("other-project",)),
        ):
            with self.subTest(bad=bad), self.assertRaises(PermissionError):
                self.store.mark_read(note_id, principal=bad)
        with self.assertRaises(PermissionError):
            self.store.list_notifications(principal=viewer("alice"), recipient_id="bob")
        with self.assertRaises(PermissionError):
            self.store.list_notifications(principal=viewer("alice"), project_id="other-project")
        self.assertEqual(self.count("inbox_reads"), 0)

    def test_org_isolation_allows_same_recipient_and_event_key_in_distinct_orgs(self):
        self.publish()
        other_org = "synthetic-org-2"
        alt = policy_plan(("alice",), org=other_org)
        result = self.publish(
            alt, users=("alice",),
            principal=publisher(org=other_org),
            recipient_grants=[entitlement("alice", org=other_org)],
        )
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(self.count("inbox_notices"), 2)
        self.assertEqual(len(self.store.list_notifications(principal=viewer("alice"))), 1)
        self.assertEqual(len(self.store.list_notifications(
            principal=viewer("alice", org=other_org))), 1)

    def test_host_grant_must_match_org_project_request_and_actor(self):
        plan = policy_plan()
        for grants in (
            [], [entitlement("alice", org="other-org")],
            [entitlement("alice", projects=("other-project",))],
            [entitlement("alice", requests=("other-request",))],
            [entitlement("alice", notifications_enabled=False)],
            [entitlement("alice", host_verified=False)],
            [entitlement("alice", role="unknown")],
        ):
            with self.subTest(grants=grants), self.assertRaises(PermissionError):
                self.publish(plan, recipient_grants=grants)
        with self.assertRaises(PermissionError):
            self.publish(plan, principal=publisher(actor="different-actor"))
        self.assertEqual(self.count("inbox_notices"), 0)

    def test_viewer_role_is_allowed_read_but_not_publish_and_unknown_identity_denied(self):
        plan = policy_plan()
        for principal in (
            publisher(host_verified=False),
            publisher(authenticated=False),
            publisher(can_publish=False),
            publisher(role="viewer"),
            publisher(role="unknown"),
        ):
            with self.subTest(principal=principal), self.assertRaises(PermissionError):
                self.publish(plan, principal=principal)
        self.publish(plan)
        for principal in (
            viewer("alice", host_verified=False),
            viewer("alice", authenticated=False),
            viewer("alice", role="unknown"),
            viewer("alice", can_read=False),
        ):
            with self.subTest(principal=principal), self.assertRaises(PermissionError):
                self.store.list_notifications(principal=principal)
        with self.assertRaises(PermissionError):
            self.store.mark_read(1, principal=viewer("alice", can_mark_read=False))

    def test_changing_visible_permissions_re_redacts_on_read(self):
        self.publish()
        restricted = self.store.list_notifications(
            principal=viewer("alice", fields=("status",)),
        )[0]
        self.assertIsNone(restricted["actor_id"])
        self.assertIsNone(restricted["amendment_id"])
        self.assertEqual(restricted["status"], "UNDER_FINANCE_REVIEW")
        no_sensitive_fields = self.store.list_notifications(
            principal=viewer("alice", fields=()),
        )[0]
        self.assertIsNone(no_sensitive_fields["status"])
        self.assertIsNone(no_sensitive_fields["actor_id"])
        self.assertIsNone(no_sensitive_fields["amendment_id"])
        self.assertNotIn(ACTOR, repr(no_sensitive_fields))

    def test_denied_grant_field_rejects_unredacted_policy_payload(self):
        plan = policy_plan()
        with self.assertRaises(PermissionError):
            self.publish(plan, recipient_grants=[
                entitlement("alice", fields=("status",)),
            ])
        self.assertEqual(self.count("inbox_notices"), 0)

    def test_only_explicit_policy_contract_accepted_no_external_or_unverified_refs(self):
        base = policy_plan()
        variations = []
        for key, value in (
            ("external_deliveries", ["smtp"]),
            ("send_or_resend_performed", True),
            ("any_mutation_performed", True),
            ("kind", "email_notification"),
            ("meaningful_change", False),
            ("duplicate_event", True),
        ):
            changed = deepcopy(base)
            changed[key] = value
            variations.append(changed)
        for field in ("receipt_reference", "official_document_id", "url",
                      "email", "credential", "ledger"):
            changed = deepcopy(base)
            changed["notifications"][0][field] = "UNVERIFIED_SECRET_" + field
            variations.append(changed)
        for changed in variations:
            with self.subTest(changed=changed), self.assertRaises((
                PermissionError, NoticeContractError,
            )):
                self.publish(changed)
        self.assertEqual(self.count("inbox_notices"), 0)
        self.assertEqual(self.count("inbox_audit"), 0)
        self.assertFalse((self.root / "Madar-Taraz-Bridge").exists())

    def test_empty_or_noop_plan_does_not_persist_notification(self):
        plan = policy_plan(users=())
        result = self.publish(plan, users=())
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(self.count("inbox_notices"), 0)
        already_seen = deepcopy(plan)
        already_seen["duplicate_event"] = True
        result = self.publish(already_seen, users=())
        self.assertEqual(result["inserted"], 0)

    def test_accepted_payload_has_no_network_email_cloud_or_taraz_io(self):
        plan = policy_plan()
        before = deepcopy(plan)
        with (
            patch("socket.create_connection", side_effect=AssertionError("network forbidden")),
            patch("socket.socket.connect", side_effect=AssertionError("network forbidden")),
        ):
            self.publish(plan)
            self.store.list_notifications(principal=viewer("alice"))
        self.assertEqual(plan, before)
        self.assertFalse((self.root / "Madar-Taraz-Bridge").exists())

    def test_threaded_writers_have_one_insert_not_duplicate_audits(self):
        plan = policy_plan()
        barrier = threading.Barrier(8, timeout=20)

        def race():
            barrier.wait(timeout=20)
            instance = InternalNotificationStore(self.path)
            return instance.publish_plan(
                deepcopy(plan), principal=publisher(),
                project_id=PROJECT, recipient_grants=[entitlement("alice")],
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            outcomes = list(executor.map(lambda _: race(), range(8)))
        self.assertEqual(sum(item["inserted"] for item in outcomes), 1)
        self.assertEqual(sum(item["replayed"] for item in outcomes), 7)
        self.assertEqual(self.count("inbox_notices"), 1)
        self.assertEqual(self.count("inbox_audit"), 1)

    def test_real_windows_process_writers_same_key_are_idempotent(self):
        if os.name != "nt":
            self.skipTest("Real Windows process race requires Windows")
        script = (
            "import os, pathlib, time, json\n"
            "from mtr_internal_notification_store import HostPrincipal,HostRecipientGrant,"
            "InternalNotificationStore\n"
            "from mtr_internal_notification_policy import plan_internal_notifications\n"
            "root=pathlib.Path(os.environ['E6_TEST_ROOT'])\n"
            "pathlib.Path(os.environ['E6_READY']).write_text('ready')\n"
            "end=time.monotonic()+20\n"
            "while not (root/'GO').exists():\n"
            "  if time.monotonic()>end: raise TimeoutError('barrier')\n"
            "  time.sleep(.02)\n"
            "org='synthetic-org-1'; project='synthetic-project-1'; request='synthetic-request-1'\n"
            "event={'organization_id':org,'project_id':project,'server_read_authorized':True,"
            "'server_event_trusted':True,'event_key':'synthetic-event-100','original_request_id':request,"
            "'event_kind':'amendment_status_changed','amendment_id':'synthetic-amendment-1',"
            "'previous_status':'AWAITING_RECEIPT','status':'UNDER_FINANCE_REVIEW',"
            "'previous_revision':2,'revision':3,'actor_id':'synthetic-finance-actor',"
            "'occurred_at':'2026-11-09T12:00:00Z'}\n"
            "rec=[{'user_id':'alice','role':'viewer','organization_id':org,"
            "'server_read_authorized':True,'readable_project_ids':[project],"
            "'related_request_ids':[request],'internal_notifications_enabled':True,"
            "'visible_fields':['status','actor_id','amendment_id']}]\n"
            "scope={'organization_id':org,'server_scoped':True,'actor_authenticated':True,"
            "'actor_authorized':True,'actor_id':'synthetic-finance-actor','actor_role':'editor',"
            "'readable_project_ids':[project],'visible_fields':['status','actor_id','amendment_id'],"
            "'notify_authorized':True,'dedup_snapshot_trusted':True,'authoritative_revision':3}\n"
            "p=plan_internal_notifications(event,rec,scope=scope,seen_event_keys=[])\n"
            "actor=HostPrincipal(org,'synthetic-host-operator','editor',frozenset({project}),"
            "frozenset({'status','actor_id','amendment_id'}),True,True,can_publish=True,"
            "verified_event_actor_id='synthetic-finance-actor')\n"
            "grant=HostRecipientGrant(org,'alice','viewer',frozenset({project}),"
            "frozenset({request}),frozenset({'status','actor_id','amendment_id'}),True,True)\n"
            "db=InternalNotificationStore(root/'synthetic-inbox.sqlite3')\n"
            "print(json.dumps(db.publish_plan(p,principal=actor,project_id=project,"
            "recipient_grants=[grant])),flush=True)\n"
        )
        go = self.root / "GO"
        children = []
        try:
            for i in range(4):
                ready = self.root / f"ready-{i}"
                child = subprocess.Popen(
                    [sys.executable, "-B", "-c", script],
                    cwd=str(ROOT),
                    env=dict(os.environ, E6_TEST_ROOT=str(self.root), E6_READY=str(ready)),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                children.append((child, ready))
            deadline = time.monotonic() + 15
            while not all(ready.exists() for _, ready in children) and time.monotonic() < deadline:
                if any(proc.poll() is not None for proc, _ in children):
                    break
                time.sleep(.02)
            self.assertTrue(all(ready.exists() for _, ready in children))
            go.touch()
            results = []
            for proc, _ in children:
                output, error = proc.communicate(timeout=35)
                self.assertEqual(proc.returncode, 0, error[-1600:])
                results.append(__import__("json").loads(output))
            self.assertEqual(sum(item["inserted"] for item in results), 1)
            self.assertEqual(sum(item["replayed"] for item in results), 3)
            self.assertEqual(self.count("inbox_notices"), 1)
            self.assertEqual(self.count("inbox_audit"), 1)
        finally:
            go.touch()
            for proc, _ in children:
                if proc.poll() is None:
                    proc.kill()
                proc.communicate(timeout=10)

    def test_bad_database_and_invalid_path_fail_closed(self):
        garbage = self.root / "garbage.sqlite3"
        garbage.write_bytes(b"NOT A SQLITE DATABASE")
        with self.assertRaises(sqlite3.DatabaseError):
            InternalNotificationStore(garbage)
        with self.assertRaises(NoticeContractError):
            InternalNotificationStore("relative-file.sqlite3")
        folder = self.root / "dir.sqlite3"
        folder.mkdir()
        with self.assertRaises(PermissionError):
            InternalNotificationStore(folder)


if __name__ == "__main__":
    unittest.main()
