"""Synthetic E1 LAN identity -> Radar CRM store adapter tests; no listeners."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, RLock
import time
import unittest
from unittest.mock import patch

from lan import LanService, make_account
from radar_crm_store import CrmError, RadarCrmStore
from radar_host_adapter import RadarHostAdapter, RadarHostAdapterError


T0 = "2026-11-09T15:00:00+00:00"
T1 = "2026-11-09T16:00:00+00:00"
T2 = "2026-11-09T17:00:00+00:00"


class SyntheticBridge:
    """No storage, browser or ports. Only host-owned saved-state analogue."""

    def __init__(self):
        self._lock = RLock()
        self.state = {
            "projects": [{"id": "p-one", "name": "Test 1"},
                         {"id": "p-two", "name": "Test 2"}],
            "tasks": [],
        }

    def getState(self):
        return deepcopy(self.state)


class HostAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One-time PBKDF for synthetic credentials; most tests exercise
        # real LanService.account_for() with synthetic test-only sessions.
        cls.sample_accounts = {
            "admin": make_account("admin", "synthetic-admin-password", role="admin"),
            "editor": make_account("editor", "synthetic-editor-password",
                                   role="editor", projects=["p-one"]),
            "othereditor": make_account("othereditor", "synthetic-other-password",
                                        role="editor", projects=["p-two"]),
            "viewer": make_account("viewer", "synthetic-viewer-password",
                                   role="viewer", projects=["p-one"]),
        }

    def setUp(self):
        self.temp = TemporaryDirectory(prefix="radar-host-adapter-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bridge = SyntheticBridge()
        self.service = LanService(self.bridge, self.root / "users.json",
                                  bind="127.0.0.1", port=0)
        self.service.users = deepcopy(self.sample_accounts)
        self.service._store_users()
        self.admin, self.editor, self.othereditor, self.viewer = [
            f"synthetic-test-session-{name}" for name in
            ("admin", "editor", "othereditor", "viewer")
        ]
        for token, user in (
            (self.admin, "admin"), (self.editor, "editor"),
            (self.othereditor, "othereditor"), (self.viewer, "viewer"),
        ):
            self.service.sessions[token] = (user, time.time() + 3600)
        self.store = RadarCrmStore(self.root / "synthetic-crm.sqlite")
        self.adapter = RadarHostAdapter(self.service, self.store,
                                        org_id="synthetic-tenant-a")

    def cmd(self, action, params, *, project="p-one", human=True):
        obj = {"schemaVersion": 1, "action": action, "projectId": project,
               "params": params}
        if action not in {"get_contact", "list_contacts", "list_history",
                          "list_due_reminders"}:
            obj["manualAction"] = human
        return obj

    def send(self, token, command):
        return self.adapter.handle(
            token, json.dumps(command, ensure_ascii=False,
                              separators=(",", ":")).encode("utf-8"))

    def create(self, *, token=None, contact="c-one", event="evt-create",
               project="p-one", assignee=None, human=True):
        payload = {"contactId": contact, "eventId": event,
                   "occurredAt": T0, "name": "مشتری ساختگی",
                   "contactDetail": "فقط سناریوی آزمایشی"}
        if assignee is not None:
            payload["assigneeId"] = assignee
        return self.send(self.admin if token is None else token,
                         self.cmd("create_contact", payload,
                                  project=project, human=human))

    def note(self, *, token=None, event="evt-note", expected=1):
        return self.send(self.editor if token is None else token,
                         self.cmd("record_note", {
                             "contactId": "c-one", "eventId": event,
                             "occurredAt": T1, "expectedVersion": expected,
                             "note": "پیگیری انسانی", "channel": "call",
                         }))

    def assert_deny(self, expected, token, cmd):
        with self.assertRaises((RadarHostAdapterError, CrmError, PermissionError)) as caught:
            self.send(token, cmd)
        exception = caught.exception
        self.assertEqual(getattr(exception, "code", None), expected,
                         repr(exception))
        self.assertNotIn("synthetic-tenant-b", str(exception))

    def test_in_process_full_human_flow_without_socket(self):
        with patch("socket.socket", side_effect=AssertionError("network denied")):
            created = self.create(assignee="editor")
            self.assertEqual(created["result"]["version"], 1)
            self.assertFalse(created["result"]["replayed"])
            self.assertEqual(self.note()["result"]["version"], 2)
            scheduled = self.send(self.admin, self.cmd(
                "schedule_followup", {
                    "contactId": "c-one", "eventId": "evt-followup",
                    "occurredAt": T1, "expectedVersion": 2,
                    "followupId": "followup-one", "dueAt": T2,
                    "subject": "مراجعه دستی", "assignedTo": "editor",
                }))
            self.assertEqual(scheduled["result"]["version"], 3)
            self.assertEqual(self.send(self.admin, self.cmd(
                "list_due_reminders", {"asOf": T2}))["result"], [])
            due = self.send(self.editor, self.cmd(
                "list_due_reminders", {"asOf": T2}))["result"]
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["assigned_to"], "editor")
            completed = self.send(self.editor, self.cmd(
                "complete_followup", {
                    "contactId": "c-one", "eventId": "evt-complete",
                    "occurredAt": T2, "expectedVersion": 3,
                    "followupId": "followup-one", "outcome": "انجام شد",
                }))
            self.assertEqual(completed["result"]["version"], 4)
            self.assertEqual(self.send(self.editor, self.cmd(
                "list_due_reminders", {"asOf": T2}))["result"], [])
            history = self.send(self.editor, self.cmd(
                "list_history", {"contactId": "c-one"}))["result"]
            self.assertEqual([item["kind"] for item in history],
                             ["contact_created", "interaction_recorded",
                              "followup_scheduled", "followup_completed"])
            self.assertEqual([item["actor_id"] for item in history],
                             ["admin", "editor", "admin", "editor"])
        self.assertIsNone(self.service.server)

    def test_editor_can_create_owned_contact_but_cannot_reassign_others(self):
        created = self.create(token=self.editor, contact="editor-own",
                              event="create-editor")
        self.assertEqual(created["result"]["version"], 1)
        item = self.send(self.editor, self.cmd("get_contact",
                         {"contactId": "editor-own"}))["result"]
        self.assertEqual(item["owner_id"], "editor")
        self.assertEqual(item["assignee_id"], "editor")
        self.assert_deny("assignment_denied", self.editor,
                         self.cmd("create_contact", {
                             "contactId": "bad-assignee",
                             "eventId": "another-event", "occurredAt": T0,
                             "name": "کاربر تست", "assigneeId": "admin",
                         }))
        self.assert_deny("permission_denied", self.editor,
                         self.cmd("soft_delete_contact", {
                             "contactId": "editor-own",
                             "eventId": "no-delete", "occurredAt": T1,
                             "expectedVersion": 1,
                         }))

    def test_client_actor_org_role_or_finance_fields_rejected(self):
        for extra in ("orgId", "actor", "role", "permissions", "userId",
                      "account", "tarazPartyId", "amountRial", "finance"):
            with self.subTest(extra=extra):
                invalid = self.cmd("create_contact", {
                    "contactId": "c-one", "eventId": "evt-create",
                    "occurredAt": T0, "name": "تست", extra: "forged",
                })
                self.assert_deny("invalid_params", self.admin, invalid)
                self.assert_deny("invalid_command", self.admin,
                                 {**self.cmd("list_contacts", {}), extra: "forged"})
        self.assertEqual(self.send(
            self.admin, self.cmd("list_contacts", {}))["result"], [])

    def test_strict_json_unknown_duplicates_utf8_constants_and_length(self):
        for raw, code in [
            (b'{"action":"list_contacts","action":"create_contact"}',
             "invalid_json"),
            (b'{"schemaVersion":1,"action":"list_contacts","projectId":"p-one",'
             b'"params":{"limit":1,"limit":2}}', "invalid_json"),
            (b'not-json', "invalid_json"),
            (b'{}', "unsupported_action"),
            (b'\xff', "invalid_json"),
            (b"x" * 8193, "invalid_json"),
            (b'{"schemaVersion":1,"action":"list_contacts","projectId":"p-one",'
             b'"params":{"limit":NaN}}', "invalid_json"),
        ]:
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(RadarHostAdapterError) as caught:
                    self.adapter.handle(self.admin, raw)
                self.assertEqual(caught.exception.code, code)
        for invalid in (
            {**self.cmd("list_contacts", {}), "manualAction": True},
            {**self.cmd("list_contacts", {}), "schemaVersion": True},
            self.cmd("list_contacts", {"task": {"nested": "value"}}),
            self.cmd("list_contacts", {"limit": True}),
            self.cmd("list_contacts", {"limit": 101}),
            self.cmd("create_contact", {
                "contactId": "c-one", "eventId": "event1",
                "occurredAt": T0, "name": "valid", "extra": []}),
        ):
            with self.subTest(command=repr(invalid)[:100]):
                with self.assertRaises((RadarHostAdapterError, CrmError)):
                    self.send(self.admin, invalid)

    def test_manual_action_required_all_mutations_even_on_replay(self):
        self.assert_deny("manual_action_required", self.admin,
                         self.cmd("create_contact", {
                             "contactId": "c-one", "eventId": "evt-create",
                             "occurredAt": T0, "name": "تست",
                         }, human=False))
        self.create(assignee="editor")
        self.assert_deny("manual_action_required", self.admin,
                         self.cmd("create_contact", {
                             "contactId": "c-one", "eventId": "evt-create",
                             "occurredAt": T0, "name": "مشتری ساختگی",
                             "contactDetail": "فقط سناریوی آزمایشی",
                             "assigneeId": "editor",
                         }, human=False))
        for action, params in [
            ("record_note", {"contactId": "c-one", "eventId": "note",
                             "occurredAt": T1, "expectedVersion": 1,
                             "note": "پیگیری"}),
            ("soft_delete_contact", {"contactId": "c-one", "eventId": "del",
                                     "occurredAt": T1, "expectedVersion": 1}),
        ]:
            self.assert_deny("manual_action_required", self.admin,
                             self.cmd(action, params, human=False))
        self.assertEqual(self.send(self.admin, self.cmd(
            "get_contact", {"contactId": "c-one"}))["result"]["version"], 1)

    def test_account_expiry_revocation_and_project_grant_changes(self):
        self.create(assignee="editor")
        self.assert_deny("authentication_required", "invalid-token",
                         self.cmd("list_contacts", {}))
        self.service.sessions.pop(self.editor)
        self.assert_deny("authentication_required", self.editor,
                         self.cmd("list_contacts", {}))
        self.service.sessions[self.editor] = ("editor", time.time() + 3600)
        self.service.users["editor"]["projects"] = ["p-two"]
        self.assert_deny("scope_denied", self.editor,
                         self.cmd("list_contacts", {}))
        self.service.users["editor"]["projects"] = ["p-one"]
        self.service.users["editor"]["role"] = "viewer"
        self.assert_deny("permission_denied", self.editor,
                         self.cmd("record_note", {
                             "contactId": "c-one", "eventId": "no-role",
                             "occurredAt": T1, "expectedVersion": 1,
                             "note": "denied",
                         }))
        self.service.users.pop("editor")
        self.assert_deny("authentication_required", self.editor,
                         self.cmd("list_contacts", {}))

    def test_real_password_login_is_accepted_by_account_for(self):
        token = self.service.authenticate(
            "editor", "synthetic-editor-password")["token"]
        self.assertEqual(
            self.send(token, self.cmd("list_contacts", {}))["result"], [])

    def test_denies_missing_project_and_unsaved_grant(self):
        self.assert_deny("scope_denied", self.admin,
                         self.cmd("list_contacts", {}, project="no-such-project"))
        self.assert_deny("scope_denied", self.editor,
                         self.cmd("list_contacts", {}, project="p-two"))
        self.bridge.state["projects"] = [{"id": "p-two"}]
        self.assert_deny("scope_denied", self.admin,
                         self.cmd("list_contacts", {}, project="p-one"))

    def test_malformed_saved_state_grants_and_user_registry_fail_closed(self):
        self.bridge.state["projects"].append({"id": "p-one"})
        self.assert_deny("scope_denied", self.admin,
                         self.cmd("list_contacts", {}))
        self.bridge.state["projects"].pop()
        self.service.users["editor"].pop("projects")
        self.assert_deny("scope_denied", self.editor,
                         self.cmd("list_contacts", {}))
        self.service.users["editor"]["projects"] = ["p-one", "p-one"]
        self.assert_deny("scope_denied", self.editor,
                         self.cmd("list_contacts", {}))
        self.service.users["editor"]["projects"] = ["p-one"]
        self.service.users["malformed"] = ["not an account"]
        self.assert_deny("authentication_required", self.admin,
                         self.cmd("list_contacts", {}))

    def test_no_implicit_privilege_from_client_actor_or_boolean_fields(self):
        self.assert_deny("invalid_command", self.admin, {
            **self.cmd("list_contacts", {}), "principal": {
                "role": "admin", "org_id": "synthetic-tenant-b",
            },
        })
        self.assert_deny("manual_action_required", self.admin,
                         self.cmd("create_contact", {
                             "contactId": "c-one", "eventId": "evt-create",
                             "occurredAt": T0, "name": "test",
                         }, human=1))
        self.assert_deny("invalid_params", self.admin, self.cmd(
            "record_note", {
                "contactId": "c-one", "eventId": "evt-note",
                "occurredAt": T1, "expectedVersion": True,
                "note": "not accepted",
            }))
        self.assert_deny("invalid_identifier", self.admin,
                         self.cmd("get_contact", {"contactId": "../other"}))

    def test_viewer_and_non_assignee_no_record_leaks(self):
        self.create(assignee="editor")
        self.assert_deny("permission_denied", self.viewer,
                         self.cmd("record_note", {
                             "contactId": "c-one", "eventId": "viewer-note",
                             "occurredAt": T1, "expectedVersion": 1,
                             "note": "not allowed",
                         }))
        self.assert_deny("not_found", self.viewer, self.cmd(
            "get_contact", {"contactId": "c-one"}))
        self.assertEqual(self.send(
            self.viewer, self.cmd("list_contacts", {}))["result"], [])
        self.assert_deny("scope_denied", self.othereditor,
                         self.cmd("get_contact", {"contactId": "c-one"}))
        self.assertEqual(self.send(
            self.editor, self.cmd("get_contact", {"contactId": "c-one"})
        )["result"]["owner_id"], "admin")

    def test_replay_stable_across_adapter_restart_and_cas_stale(self):
        self.create(assignee="editor")
        fresh_adapter = RadarHostAdapter(
            self.service, RadarCrmStore(self.root / "synthetic-crm.sqlite"),
            org_id="synthetic-tenant-a",
        )
        command = self.cmd("record_note", {
            "contactId": "c-one", "eventId": "evt-note",
            "occurredAt": T1, "expectedVersion": 1,
            "note": "پیگیری انسانی", "channel": "call",
        })
        first = self.send(self.editor, command)
        replay = fresh_adapter.handle(
            self.editor, json.dumps(command, ensure_ascii=False).encode())
        self.assertEqual(first["result"]["version"], 2)
        self.assertFalse(first["result"]["replayed"])
        self.assertTrue(replay["result"]["replayed"])
        self.assert_deny("event_conflict", self.editor, self.cmd(
            "record_note", {**command["params"], "note": "other text"}))
        self.assert_deny("version_conflict", self.editor, self.cmd(
            "record_note", {**command["params"], "eventId": "evt-new"}))
        self.assertEqual(len(self.send(self.editor, self.cmd(
            "list_history", {"contactId": "c-one"}))["result"]), 2)

    def test_assignment_grants_from_saved_user_registry_only(self):
        self.assert_deny("assignment_denied", self.admin, self.cmd(
            "create_contact", {
                "contactId": "c-one", "eventId": "evt-create",
                "occurredAt": T0, "name": "تست",
                "assigneeId": "othereditor",
            }))
        self.assert_deny("assignment_denied", self.admin, self.cmd(
            "create_contact", {
                "contactId": "c-one", "eventId": "evt-create",
                "occurredAt": T0, "name": "تست",
                "assigneeId": "viewer",
            }))
        self.create(assignee="editor")
        self.service.users["editor"]["projects"] = ["p-two"]
        self.assert_deny("assignment_denied", self.admin, self.cmd(
            "update_contact", {
                "contactId": "c-one", "eventId": "evt-reassign",
                "occurredAt": T1, "expectedVersion": 1,
                "assigneeId": "editor",
            }))

    def test_two_org_services_share_db_without_cross_org_leaks(self):
        self.create(assignee="editor")
        second_root = self.root / "other-host"
        second_root.mkdir()
        other_service = LanService(
            SyntheticBridge(), second_root / "users.json",
            bind="127.0.0.1", port=0,
        )
        other_service.setup_owner("admin", "other-synthetic-password")
        second_token = other_service.authenticate(
            "admin", "other-synthetic-password")["token"]
        other_adapter = RadarHostAdapter(
            other_service, self.store, org_id="synthetic-tenant-b",
        )
        raw = json.dumps(self.cmd("list_contacts", {})).encode()
        self.assertEqual(other_adapter.handle(second_token, raw)["result"], [])
        other_adapter.handle(second_token, json.dumps(self.cmd(
            "create_contact", {
                "contactId": "c-one", "eventId": "evt-create",
                "occurredAt": T0, "name": "other synthetic org",
            })).encode())
        self.assertEqual(len(self.send(
            self.admin, self.cmd("list_contacts", {}))["result"]), 1)
        self.assertEqual(other_adapter.handle(
            second_token, raw)["result"][0]["name"], "other synthetic org")
        self.assertEqual(self.send(self.admin, self.cmd(
            "get_contact", {"contactId": "c-one"}))["result"]["name"],
            "مشتری ساختگی")

    def test_concurrent_commands_one_wins_cas(self):
        self.create(assignee="editor")
        gate = Barrier(2)

        def run(index):
            gate.wait(timeout=5)
            try:
                result = self.send(self.editor, self.cmd("record_note", {
                    "contactId": "c-one", "eventId": f"evt-race-{index}",
                    "occurredAt": T1, "expectedVersion": 1,
                    "note": f"رقابت {index}",
                }))
                return "ok", result["result"]["version"]
            except CrmError as error:
                return "deny", error.code

        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(run, n) for n in (1, 2)]
            observed = [future.result(timeout=10) for future in futures]
        self.assertEqual(sorted(observed),
                         [("deny", "version_conflict"), ("ok", 2)])


if __name__ == "__main__":
    unittest.main()
