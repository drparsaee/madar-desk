"""Synthetic, temporary-file E1 Radar CRM acceptance/security tests only."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from multiprocessing import get_context
from tempfile import TemporaryDirectory
from threading import Barrier
from types import MappingProxyType
from unittest.mock import patch
import sqlite3
import unittest

from radar_crm_store import CrmError, Principal, RadarCrmStore


T0 = "2026-11-09T09:00:00Z"
T1 = "2026-11-09T10:00:00Z"
T2 = "2026-11-09T11:00:00Z"


def principal(
    user="owner", org="tenant-a", projects=("project-a",),
    members=("owner", "staff"), **flags
):
    base = dict(
        user_id=user, org_id=org, project_ids=frozenset(projects),
        assignable_user_ids=frozenset(members), can_create=True,
        can_edit=True, can_follow_up=True, can_delete=True,
        can_manage=(user == "owner"), active=True,
    )
    base.update(flags)
    return Principal(**base)


def _process_write_same_contact(path, gate, queue, suffix):
    """Child process for Windows/spawn. Synthetic temporary DB only."""
    store = RadarCrmStore(Path(path))
    gate.wait(timeout=10)
    try:
        result = store.record_note(
            principal=principal(), project_id="project-a",
            contact_id="contact-1", event_id=f"process-event-{suffix}",
            occurred_at=T1, expected_version=1,
            note=f"یادداشت مصنوعی {suffix}")
        queue.put(("ok", result.version))
    except CrmError as error:
        queue.put(("deny", error.code))


class RadarCrmStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="synthetic-radar-crm-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "radar.sqlite"
        self.store = RadarCrmStore(self.path)
        self.owner = principal()
        self.staff = principal(
            "staff", can_create=False, can_edit=False, can_delete=False,
            can_manage=False,
        )

    def deny(self, code, call, **kwargs):
        with self.assertRaises(CrmError) as captured:
            call(**kwargs)
        self.assertEqual(captured.exception.code, code)
        self.assertNotIn("tenant-b", str(captured.exception))

    def create(self, contact_id="contact-1", event_id="event-create-1",
               principal_override=None, project_id="project-a", **kwargs):
        return self.store.create_contact(
            principal=self.owner if principal_override is None
            else principal_override,
            project_id=project_id, contact_id=contact_id, event_id=event_id,
            occurred_at=T0, name="مشتری آزمایشی", **kwargs,
        )

    def add_note(self, *, expected_version, event_id="event-note-1",
                 note="پیگیری دستی انجام شد", p=None):
        return self.store.record_note(
            principal=self.owner if p is None else p, project_id="project-a",
            contact_id="contact-1", event_id=event_id, occurred_at=T1,
            expected_version=expected_version, note=note,
            channel="call",
        )

    def reminder(self, *, expected_version=1, event_id="event-followup-1",
                 followup_id="followup-1", due_at=T2, p=None,
                 assigned_to=None):
        return self.store.schedule_followup(
            principal=self.owner if p is None else p, project_id="project-a",
            contact_id="contact-1", event_id=event_id, occurred_at=T1,
            expected_version=expected_version, followup_id=followup_id,
            due_at=due_at, subject="تماس پیگیری توسط مسئول",
            assigned_to=assigned_to,
        )

    def test_create_is_durable_across_restart_and_has_scoped_audit(self):
        receipt = self.create(contact_detail="صرفاً اطلاعات مصنوعی",
                              assignee_id="staff")
        self.assertEqual((receipt.version, receipt.replayed), (1, False))
        reopen = RadarCrmStore(self.path)
        item = reopen.get_contact(principal=self.owner,
                                  project_id="project-a",
                                  contact_id="contact-1")
        self.assertEqual(item.contact_detail, "صرفاً اطلاعات مصنوعی")
        self.assertEqual(item.owner_id, "owner")
        self.assertEqual(item.assignee_id, "staff")
        self.assertFalse(item.deleted)
        self.assertEqual(item.version, 1)
        events = reopen.list_history(principal=self.staff,
                                     project_id="project-a",
                                     contact_id="contact-1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].actor_id, "owner")
        self.assertEqual(events[0].kind, "contact_created")
        self.assertEqual(events[0].payload["after"]["assignee_id"], "staff")

    def test_replay_create_and_mutations_are_idempotent_even_after_restart(self):
        self.create()
        self.assertEqual(self.create().version, 1)
        self.assertTrue(self.create().replayed)
        first = self.add_note(expected_version=1)
        self.assertEqual(first.version, 2)
        self.store = RadarCrmStore(self.path)
        replay = self.add_note(expected_version=1)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.version, 2)
        contact = self.store.get_contact(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1")
        self.assertEqual(contact.version, 2)
        self.assertEqual(len(self.store.list_history(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1")), 2)

    def test_conflicting_event_id_rejected_without_overwriting(self):
        self.create()
        self.deny("event_conflict", self.store.create_contact,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="event-create-1",
                  occurred_at=T0, name="نام متفاوت")
        self.add_note(expected_version=1)
        self.deny("event_conflict", self.store.record_note,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="event-note-1",
                  occurred_at=T1, expected_version=1, note="متن دیگر")
        self.deny("event_conflict", self.store.record_note,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="event-note-1",
                  occurred_at=T2, expected_version=1,
                  note="پیگیری دستی انجام شد", channel="call")
        self.assertEqual(self.store.get_contact(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1").version, 2)

    def test_duplicate_event_id_across_contacts_denied_same_tenant(self):
        self.create()
        self.deny("event_conflict", self.store.create_contact,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-2", event_id="event-create-1",
                  occurred_at=T0, name="آزمایشی دیگر")
        self.deny("not_found", self.store.get_contact, principal=self.owner,
                  project_id="project-a", contact_id="contact-2")

    def test_cross_organization_and_cross_project_identifiers_isolated(self):
        self.create()
        other_org = principal("org2-owner", org="tenant-b", members=("org2-owner",))
        other_project = principal(projects=("project-b",))
        self.store.create_contact(
            principal=other_org, project_id="project-a",
            contact_id="contact-1", event_id="event-create-1",
            occurred_at=T0, name="مخاطب سازمان دیگر")
        self.store.create_contact(
            principal=other_project, project_id="project-b",
            contact_id="contact-1", event_id="event-create-1",
            occurred_at=T0, name="مخاطب پروژه دیگر")
        self.assertEqual([x.name for x in self.store.list_contacts(
            principal=self.owner, project_id="project-a")],
            ["مشتری آزمایشی"])
        self.assertEqual([x.name for x in self.store.list_contacts(
            principal=other_org, project_id="project-a")],
            ["مخاطب سازمان دیگر"])
        self.assertEqual([x.name for x in self.store.list_contacts(
            principal=other_project, project_id="project-b")],
            ["مخاطب پروژه دیگر"])
        self.deny("permission_denied", self.store.get_contact,
                  principal=self.owner, project_id="project-b",
                  contact_id="contact-1")
        self.assertEqual(len(self.store.list_history(
            principal=other_org, project_id="project-a",
            contact_id="contact-1")), 1)

    def test_unassigned_user_and_revoked_user_read_denied(self):
        self.create()
        outsider = principal("unrelated", can_manage=False,
                            members=("unrelated",))
        self.deny("not_found", self.store.get_contact, principal=outsider,
                  project_id="project-a", contact_id="contact-1")
        self.assertEqual(self.store.list_contacts(
            principal=outsider, project_id="project-a"), ())
        self.deny("not_found", self.store.list_history,
                  principal=outsider, project_id="project-a",
                  contact_id="contact-1")
        self.deny("permission_denied", self.store.get_contact,
                  principal=replace(self.owner, active=False),
                  project_id="project-a", contact_id="contact-1")
        self.deny("permission_denied", self.store.get_contact,
                  principal=replace(self.owner, project_ids=frozenset()),
                  project_id="project-a", contact_id="contact-1")

    def test_worker_can_note_but_not_edit_owner_or_soft_delete(self):
        self.create(assignee_id="staff")
        receipt = self.add_note(expected_version=1, p=self.staff)
        self.assertEqual(receipt.version, 2)
        self.deny("permission_denied", self.store.update_contact,
                  principal=self.staff, project_id="project-a",
                  contact_id="contact-1", event_id="try-edit", occurred_at=T1,
                  expected_version=2, name="غیرمجاز")
        self.deny("permission_denied", self.store.soft_delete_contact,
                  principal=self.staff, project_id="project-a",
                  contact_id="contact-1", event_id="try-delete",
                  occurred_at=T1, expected_version=2)

    def test_assignments_require_host_verified_allowed_members(self):
        self.deny("assignment_denied", self.store.create_contact,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="event-create-1",
                  occurred_at=T0, name="مخاطب", assignee_id="foreign-user")
        self.create(assignee_id="staff")
        self.deny("assignment_denied", self.store.update_contact,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="event-change-1",
                  occurred_at=T1, expected_version=1,
                  owner_id="foreign-user")
        self.deny("permission_denied", self.store.update_contact,
                  principal=replace(self.staff, can_edit=True),
                  project_id="project-a",
                  contact_id="contact-1", event_id="event-change-1",
                  occurred_at=T1, expected_version=1,
                  assignee_id="owner")
        self.assertEqual(self.store.get_contact(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1").version, 1)

    def test_edit_changes_are_versioned_and_original_values_auditable(self):
        self.create()
        result = self.store.update_contact(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1", event_id="event-update-1",
            occurred_at=T1, expected_version=1, name="نام ویرایش‌شده",
            contact_detail="صرفاً یادداشت تست")
        self.assertEqual(result.version, 2)
        event = self.store.list_history(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1")[-1]
        self.assertEqual(event.payload["before"]["name"], "مشتری آزمایشی")
        self.assertEqual(event.payload["after"]["name"], "نام ویرایش‌شده")
        self.deny("version_conflict", self.store.update_contact,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="stale-change",
                  occurred_at=T1, expected_version=1, name="رکورد قدیمی")
        self.assertEqual(self.store.get_contact(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1").name, "نام ویرایش‌شده")

    def test_noop_update_and_bad_version_do_not_create_events(self):
        self.create()
        self.deny("no_changes", self.store.update_contact,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="no-change",
                  occurred_at=T1, expected_version=1,
                  name="مشتری آزمایشی")
        self.deny("no_changes", self.store.update_contact,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="no-fields",
                  occurred_at=T1, expected_version=1)
        self.deny("invalid_version", self.store.record_note,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="bad-version",
                  occurred_at=T1, expected_version=True, note="متن")
        self.assertEqual(len(self.store.list_history(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1")), 1)

    def test_notes_and_contact_interactions_are_human_reported_only(self):
        self.create()
        with patch("socket.socket", side_effect=AssertionError("no network")):
            result = self.store.record_note(
                principal=self.owner, project_id="project-a",
                contact_id="contact-1", event_id="event-meeting",
                occurred_at=T1, expected_version=1,
                note="جلسه حضوری ثبت‌شده توسط کاربر", channel="meeting")
        self.assertEqual(result.version, 2)
        history = self.store.list_history(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1")
        self.assertEqual(history[-1].kind, "interaction_recorded")
        self.assertEqual(history[-1].actor_id, "owner")
        self.assertEqual(history[-1].payload["channel"], "meeting")
        with self.assertRaises(TypeError):
            history[-1].payload["channel"] = "altered"
        self.assertEqual(self.store.list_history(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1")[-1].payload["channel"], "meeting")

    def test_internal_due_reminders_only_assignee_and_no_auto_send(self):
        self.create(assignee_id="staff")
        with patch("socket.socket", side_effect=AssertionError("no socket")):
            self.reminder(assigned_to="staff",
                          due_at="2026-11-09T14:30:00+03:30")
            self.assertEqual(self.store.list_due_reminders(
                principal=self.owner, project_id="project-a",
                as_of="2026-11-09T11:00:00Z"), ())
            self.assertEqual(self.store.list_due_reminders(
                principal=self.staff, project_id="project-a",
                as_of="2026-11-09T10:59:59Z"), ())
            due = self.store.list_due_reminders(
                principal=self.staff, project_id="project-a",
                as_of="2026-11-09T11:00:00Z")
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].state, "scheduled")
        self.assertEqual(due[0].assigned_to, "staff")
        self.assertEqual(due[0].due_at, "2026-11-09T11:00:00.000000Z")
        self.assertEqual(due[0].subject, "تماس پیگیری توسط مسئول")

    def test_reassignment_revokes_previous_assignee_reminder_and_history_access(self):
        self.create(assignee_id="staff")
        self.reminder(assigned_to="staff")
        owner_with_new_staff = replace(
            self.owner,
            assignable_user_ids=frozenset(("owner", "staff", "replacement")),
        )
        self.store.update_contact(
            principal=owner_with_new_staff, project_id="project-a",
            contact_id="contact-1", event_id="event-reassign-1",
            occurred_at=T2, expected_version=2, assignee_id="replacement")
        self.deny("not_found", self.store.get_contact, principal=self.staff,
                  project_id="project-a", contact_id="contact-1")
        self.deny("not_found", self.store.list_history, principal=self.staff,
                  project_id="project-a", contact_id="contact-1")
        self.assertEqual(self.store.list_due_reminders(
            principal=self.staff, project_id="project-a", as_of=T2), ())
        replacement = principal(
            "replacement", members=("replacement",), can_create=False,
            can_edit=False, can_delete=False, can_manage=False)
        self.assertEqual(self.store.get_contact(
            principal=replacement, project_id="project-a",
            contact_id="contact-1").assignee_id, "replacement")
        # The previous reminder is retained historically but not silently
        # transferred to another employee without an explicit human action.
        self.assertEqual(self.store.list_due_reminders(
            principal=replacement, project_id="project-a", as_of=T2), ())

    def test_completion_requires_explicit_authorized_assignee(self):
        self.create(assignee_id="staff")
        self.reminder(assigned_to="staff")
        self.deny("permission_denied", self.store.complete_followup,
                  principal=replace(self.owner, can_manage=False),
                  project_id="project-a", contact_id="contact-1",
                  event_id="event-complete", occurred_at=T2,
                  expected_version=2, followup_id="followup-1",
                  outcome="انجام شد")
        result = self.store.complete_followup(
            principal=self.staff, project_id="project-a",
            contact_id="contact-1", event_id="event-complete",
            occurred_at=T2, expected_version=2, followup_id="followup-1",
            outcome="کاربر تأیید کرد پیگیری انجام شده")
        self.assertEqual(result.version, 3)
        self.assertEqual(self.store.list_due_reminders(
            principal=self.staff, project_id="project-a", as_of=T2), ())
        replay = self.store.complete_followup(
            principal=self.staff, project_id="project-a",
            contact_id="contact-1", event_id="event-complete",
            occurred_at=T2, expected_version=2, followup_id="followup-1",
            outcome="کاربر تأیید کرد پیگیری انجام شده")
        self.assertTrue(replay.replayed)
        self.deny("followup_closed", self.store.complete_followup,
                  principal=self.staff, project_id="project-a",
                  contact_id="contact-1", event_id="complete-again",
                  occurred_at=T2, expected_version=3,
                  followup_id="followup-1", outcome="تکرار")

    def test_followup_duplicate_id_rolls_back_contact_version_and_history(self):
        self.create()
        self.reminder()
        self.deny("followup_exists", self.store.schedule_followup,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="different-event",
                  occurred_at=T2, expected_version=2,
                  followup_id="followup-1", due_at=T2,
                  subject="دوباره")
        self.assertEqual(self.store.get_contact(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1").version, 2)
        self.assertEqual(len(self.store.list_history(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1")), 2)

    def test_soft_delete_preserves_history_and_suppresses_pending_reminders(self):
        self.create(assignee_id="staff")
        self.reminder(assigned_to="staff")
        deleted = self.store.soft_delete_contact(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1", event_id="event-delete",
            occurred_at=T2, expected_version=2)
        self.assertEqual(deleted.version, 3)
        self.deny("not_found", self.store.get_contact, principal=self.owner,
                  project_id="project-a", contact_id="contact-1")
        item = self.store.get_contact(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1", include_deleted=True)
        self.assertTrue(item.deleted)
        self.assertEqual(self.store.list_due_reminders(
            principal=self.staff, project_id="project-a",
            as_of=T2), ())
        self.assertEqual(self.store.list_contacts(
            principal=self.owner, project_id="project-a"), ())
        self.assertEqual(len(self.store.list_contacts(
            principal=self.owner, project_id="project-a",
            include_deleted=True)), 1)
        history = self.store.list_history(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1")
        self.assertEqual(len(history), 3)
        self.assertEqual(history[-1].kind, "contact_soft_deleted")
        self.assertEqual(history[-1].payload["suppressed_pending_followups"],
                         ("followup-1",))
        self.deny("contact_deleted", self.store.record_note,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="after-delete",
                  occurred_at=T2, expected_version=3, note="ممنوع")
        self.assertTrue(self.store.soft_delete_contact(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1", event_id="event-delete",
            occurred_at=T2, expected_version=2).replayed)
        self.deny("contact_exists", self.store.create_contact,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="new-create",
                  occurred_at=T0, name="جایگزین مخرب")

    def test_persisted_audit_update_delete_triggers_and_restart(self):
        self.create()
        self.add_note(expected_version=1)
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("UPDATE crm_events SET kind='forged'")
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("DELETE FROM crm_events")
        reopened = RadarCrmStore(self.path)
        events = reopened.list_history(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1")
        self.assertEqual([e.kind for e in events],
                         ["contact_created", "interaction_recorded"])

    def test_paginated_bounded_queries_and_history(self):
        for i in range(5):
            self.create(contact_id=f"contact-{i}", event_id=f"event-{i}")
        page = self.store.list_contacts(
            principal=self.owner, project_id="project-a", limit=2)
        self.assertEqual(len(page), 2)
        self.assertEqual([c.contact_id for c in page],
                         ["contact-0", "contact-1"])
        next_page = self.store.list_contacts(
            principal=self.owner, project_id="project-a", limit=2,
            after_id=page[-1].contact_id)
        self.assertEqual([c.contact_id for c in next_page],
                         ["contact-2", "contact-3"])
        self.deny("invalid_limit", self.store.list_contacts,
                  principal=self.owner, project_id="project-a", limit=0)
        self.deny("invalid_limit", self.store.list_due_reminders,
                  principal=self.owner, project_id="project-a",
                  as_of=T2, limit=101)
        self.assertEqual([e.version for e in self.store.list_history(
            principal=self.owner, project_id="project-a",
            contact_id="contact-0", after_version=0, limit=1)], [1])

    def test_input_limits_and_role_fail_closed(self):
        self.deny("invalid_identifier", self.store.create_contact,
                  principal=self.owner, project_id="project-a",
                  contact_id="../../secret", event_id="ev",
                  occurred_at=T0, name="fake")
        self.deny("invalid_time", self.store.create_contact,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="ev",
                  occurred_at="09/11/2026", name="fake")
        self.deny("invalid_text", self.store.create_contact,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="ev",
                  occurred_at=T0, name="A" * 161)
        self.deny("invalid_text", self.store.create_contact,
                  principal=self.owner, project_id="project-a",
                  contact_id="contact-1", event_id="ev",
                  occurred_at=T0, name="نام\u202eمخفی")
        self.deny("permission_denied", self.store.create_contact,
                  principal=replace(self.owner, can_create=False),
                  project_id="project-a", contact_id="contact-1",
                  event_id="ev", occurred_at=T0, name="fake")
        self.deny("invalid_database_path", RadarCrmStore,
                  database_path=Path("relative.db"))

    def test_two_connections_same_version_one_wins_no_lost_update(self):
        self.create()
        barrier = Barrier(2)
        outcomes = []

        def worker(suffix):
            own_store = RadarCrmStore(self.path)
            barrier.wait(timeout=5)
            try:
                result = own_store.record_note(
                    principal=self.owner, project_id="project-a",
                    contact_id="contact-1", event_id=f"event-{suffix}",
                    occurred_at=T1, expected_version=1,
                    note=f"داده آزمایشی {suffix}")
                return ("ok", result.version)
            except CrmError as error:
                return ("denied", error.code)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, i) for i in (1, 2)]
            outcomes = [future.result(timeout=15) for future in futures]
        self.assertEqual(sorted(outcomes),
                         [("denied", "version_conflict"), ("ok", 2)])
        self.assertEqual(len(self.store.list_history(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1")), 2)

    def test_concurrent_same_event_is_single_insert_with_replayed_receipt(self):
        self.create()
        barrier = Barrier(2)

        def worker():
            own_store = RadarCrmStore(self.path)
            barrier.wait(timeout=5)
            return own_store.record_note(
                principal=self.owner, project_id="project-a",
                contact_id="contact-1", event_id="event-repeat",
                occurred_at=T1, expected_version=1, note="همان رویداد")

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = [f.result(timeout=15)
                        for f in (pool.submit(worker), pool.submit(worker))]
        self.assertEqual([result.version for result in outcomes], [2, 2])
        self.assertEqual(sorted(result.replayed for result in outcomes),
                         [False, True])
        self.assertEqual(len(self.store.list_history(
            principal=self.owner, project_id="project-a",
            contact_id="contact-1")), 2)

    def test_two_windows_processes_cas_prevents_lost_update(self):
        self.create()
        ctx = get_context("spawn")
        gate = ctx.Barrier(2)
        queue = ctx.Queue()
        workers = [
            ctx.Process(target=_process_write_same_contact,
                        args=(str(self.path), gate, queue, suffix))
            for suffix in ("left", "right")
        ]
        try:
            for worker in workers:
                worker.start()
            observed = [queue.get(timeout=18) for _ in workers]
            for worker in workers:
                worker.join(timeout=10)
            self.assertTrue(all(worker.exitcode == 0 for worker in workers))
            self.assertEqual(sorted(observed),
                             [("deny", "version_conflict"), ("ok", 2)])
            self.assertEqual(len(self.store.list_history(
                principal=self.owner, project_id="project-a",
                contact_id="contact-1")), 2)
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=5)
            queue.close()
            queue.join_thread()


if __name__ == "__main__":
    unittest.main()
