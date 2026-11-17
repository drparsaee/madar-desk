"""Synthetic, no-socket E6 native Bridge.mtrNoticeCommand regression tests.

Bridge.__new__ deliberately bypasses datadir, profiles, WebView2 and startup;
only the one expected host route is monkeypatched in each test.
Run: py -3.12 -B -m unittest -v tests.test_mtr_notice_desktop_bridge_20261110
"""

import copy
import unittest
from unittest.mock import patch

from native_app import Bridge, JS_BRIDGE

PATH = "/api/mtr-notices/v1/command"
PROJECT = "project-test"
PIN = "A" * 64
TOKEN = "synthetic-session-token-1234567890"


def list_command(project=PROJECT, limit=10):
    return {"schemaVersion": 1, "action": "list",
            "params": {"projectId": project, "limit": limit}}


def mark_command(note=12):
    return {"schemaVersion": 1, "action": "mark-read",
            "params": {"noticeId": note, "manualAction": True}}


def raw_notice(**overrides):
    result = {
        "notice_id": 12, "organization_id": "ORG-HIDDEN",
        "project_id": PROJECT, "recipient_id": "editor-one",
        "channel": "internal_only",
        "event_kind": "request_status_changed",
        "read_at": None, "is_read": False,
        "actor_id": "PRIVATE-ACTOR", "status": "OFFICIALLY_POSTED",
        "deficiency_summary": "SENSITIVE-SUMMARY",
        "original_request_id": "FINANCE-REQUEST-SECRET",
        "amendment_id": "PRIVATE-AMENDMENT",
        "receipt_reference": "RECEIPT-SECRET",
        "raw_finance": {"bank": "SENSITIVE-BANK"},
        "email": "private@example.invalid",
        "external_delivery": "SHOULD-NOT-LEAK",
    }
    result.update(overrides)
    return result


def response(result):
    return {"schemaVersion": 1, "result": result}


class E6MtrNoticeDesktopBridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = Bridge.__new__(Bridge)
        self.bridge.connection = {
            "mode": "client", "url": "https://127.0.0.1:48370",
            "fingerprint": PIN}
        self.bridge.remote_token = TOKEN
        self.bridge.remote_user = {
            "username": "editor-one", "role": "editor",
            "projects": [PROJECT]}
        self.bridge._network_available = True
        self.bridge.lan = None
        self.request_patch = patch.object(
            self.bridge, "_remote_request",
            return_value=response([raw_notice()]))
        self.request = self.request_patch.start()
        self.addCleanup(self.request_patch.stop)

    def test_only_exact_list_route_payload_and_allowlisted_presentation(self):
        result = self.bridge.mtrNoticeCommand(list_command())
        self.request.assert_called_once_with(PATH, list_command())
        self.assertEqual(result, response([{
            "notice_id": 12, "project_id": PROJECT,
            "channel": "internal_only",
            "event_kind": "request_status_changed",
            "is_read": False, "read_at": None,
        }]))
        self.assertNotIn("ORG-HIDDEN", repr(result))
        self.assertNotIn("SENSITIVE", repr(result))
        self.assertNotIn("receipt_reference", repr(result))
        self.assertNotIn('"status":', repr(result))
        self.assertNotIn("actor_id", repr(result))
        self.assertNotIn("email", repr(result))

    def test_explicit_mark_read_only_and_no_client_identity_fields(self):
        self.request.return_value = response({
            "notice_id": 12, "marked_read": True, "already_read": False})
        result = self.bridge.mtrNoticeCommand(mark_command())
        self.request.assert_called_once_with(PATH, mark_command())
        self.assertEqual(result, response({
            "notice_id": 12, "marked_read": True, "already_read": False}))
        self.request.reset_mock()
        self.request.return_value = response({
            "notice_id": 12, "marked_read": False, "already_read": True})
        self.assertEqual(self.bridge.mtrNoticeCommand(mark_command())["result"]["already_read"], True)
        self.request.assert_called_once_with(PATH, mark_command())

    def test_wrong_schema_actions_limits_and_authority_never_reach_transport(self):
        forged = [
            None, [], "list", {}, {"schemaVersion": True,
                                   "action": "list", "params": {
                                       "projectId": PROJECT, "limit": 10}},
            {"schemaVersion": 2, "action": "list", "params": {
                "projectId": PROJECT, "limit": 10}},
            {"schemaVersion": 1, "action": "publish", "params": {
                "eventKey": "evt", "manualAction": True}},
            {"schemaVersion": 1, "action": "list", "params": {}},
            {"schemaVersion": 1, "action": "list", "params": {
                "projectId": PROJECT, "limit": 101}},
            {"schemaVersion": 1, "action": "list", "params": {
                "projectId": PROJECT, "limit": True}},
            {"schemaVersion": 1, "action": "list", "params": {
                "projectId": "../escape", "limit": 10}},
            {"schemaVersion": 1, "action": "list", "params": {
                "projectId": PROJECT, "limit": 10, "recipientId": "victim"}},
            {"schemaVersion": 1, "action": "list", "params": {
                "projectId": PROJECT, "limit": 10, "allowed": True}},
            {"schemaVersion": 1, "action": "mark-read", "params": {
                "noticeId": 12}},
            {"schemaVersion": 1, "action": "mark-read", "params": {
                "noticeId": 12, "manualAction": False}},
            {"schemaVersion": 1, "action": "mark-read", "params": {
                "noticeId": "12", "manualAction": True}},
            {"schemaVersion": 1, "action": "mark-read", "params": {
                "noticeId": 12, "manualAction": True, "actorId": "admin"}},
            {"schemaVersion": 1, "action": "list", "params": {
                "projectId": PROJECT, "limit": 10}, "organizationId": "owner"},
        ]
        for malformed in forged:
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                self.bridge.mtrNoticeCommand(malformed)
        self.request.assert_not_called()

    def test_no_transport_in_solo_server_http_invalid_pin_or_missing_token(self):
        baseline = copy.deepcopy(self.bridge.connection)
        for updates in (
            {"mode": "solo"},
            {"mode": "server"},
            {"url": "http://127.0.0.1:48370"},
            {"url": "https://127.0.0.1:48370/path"},
            {"url": "https://name.example:48370"},
            {"url": "https://127.0.0.1:48370?target=http"},
            {"url": "https://127.0.0.1:48370/"},
            {"fingerprint": ""},
            {"fingerprint": "a" * 63},
            {"fingerprint": "g" * 64},
            {"fingerprint": None},
        ):
            with self.subTest(updates=updates):
                self.bridge.connection = {**baseline, **updates}
                with self.assertRaises((PermissionError, ValueError)):
                    self.bridge.mtrNoticeCommand(list_command())
        self.bridge.connection = baseline
        for value in (None, "", "short", True, "x" * 513):
            with self.subTest(token=value):
                self.bridge.remote_token = value
                with self.assertRaises(PermissionError):
                    self.bridge.mtrNoticeCommand(mark_command())
        self.bridge.remote_token = TOKEN
        self.bridge._network_available = False
        with self.assertRaises(PermissionError):
            self.bridge.mtrNoticeCommand(list_command())
        self.request.assert_not_called()

    def test_host_project_grants_and_account_scope_fail_closed(self):
        user = copy.deepcopy(self.bridge.remote_user)
        with self.assertRaises(PermissionError):
            self.bridge.mtrNoticeCommand(list_command("foreign-project"))
        for altered in (
            None,
            {**user, "username": "bad user"},
            {**user, "role": "stranger"},
            {**user, "projects": ["foreign-project"]},
            {**user, "projects": "project-test"},
            {**user, "projects": [True]},
            {**user, "projects": [PROJECT, PROJECT]},
            {**user, "projects": [PROJECT] * 5001},
            {"username": "editor-one", "role": "editor"},
        ):
            self.bridge.remote_user = altered
            with self.subTest(user=altered), self.assertRaises(PermissionError):
                self.bridge.mtrNoticeCommand(list_command())
        self.bridge.remote_user = user
        self.request.assert_not_called()
        # The server authenticates current grants even for an all-project
        # client account. A None grant list is allowed by LAN public_user.
        self.bridge.remote_user["projects"] = None
        self.bridge.mtrNoticeCommand(list_command())
        self.request.assert_called_once()

    def test_foreign_recipient_project_channel_duplicates_or_unknown_kind_fail(self):
        for rows in (
            [raw_notice(project_id="wrong-project")],
            [raw_notice(recipient_id="different-user")],
            [raw_notice(channel="email")],
            [raw_notice(event_kind="unknown_finance_posted")],
            [raw_notice(notice_id=0)],
            [raw_notice(notice_id=True)],
            [raw_notice(is_read=True, read_at=None)],
            [raw_notice(read_at="today", is_read=False)],
            [raw_notice(), raw_notice()],
            [raw_notice(), raw_notice(notice_id=13)],
        ):
            self.request.return_value = response(rows)
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.bridge.mtrNoticeCommand(list_command(limit=1))

    def test_malformed_response_and_forged_ack_rejected(self):
        for malformed in (
            None, [], {"schemaVersion": 2, "result": []},
            {"schemaVersion": True, "result": []},
            {"schemaVersion": 1, "result": {}, "error": "secret"},
            {"schemaVersion": 1, "result": {"items": []}},
            {"schemaVersion": 1, "result": "finance"},
        ):
            self.request.return_value = malformed
            with self.subTest(raw=malformed), self.assertRaises(ValueError):
                self.bridge.mtrNoticeCommand(list_command())
        for raw in (
            {"notice_id": 13, "marked_read": True, "already_read": False},
            {"notice_id": 12, "marked_read": True, "already_read": True},
            {"notice_id": 12, "marked_read": False, "already_read": False},
            {"notice_id": 12, "marked_read": 1, "already_read": False},
            {"notice_id": 12, "marked_read": True, "already_read": False,
             "actor_id": "secret"},
        ):
            self.request.return_value = response(raw)
            with self.subTest(ack=raw), self.assertRaises(ValueError):
                self.bridge.mtrNoticeCommand(mark_command())

    def test_transport_exceptions_do_not_expose_raw_financial_host_body(self):
        self.request.side_effect = PermissionError(
            "HTTP 403 <secret-receipt> Finance actor and bank account")
        with self.assertRaises(RuntimeError) as captured:
            self.bridge.mtrNoticeCommand(list_command())
        self.assertEqual(str(captured.exception),
                         "Internal notice host operation unavailable.")
        self.assertNotIn("secret-receipt", str(captured.exception))

    def test_switching_session_origin_or_account_mid_request_blocks_result(self):
        base = copy.deepcopy(self.bridge.connection)
        token = self.bridge.remote_token
        user = copy.deepcopy(self.bridge.remote_user)

        def changed_token(*_):
            self.bridge.remote_token = "other-session-token-987654321"
            return response([raw_notice()])

        def changed_pin(*_):
            self.bridge.connection = {**base, "fingerprint": "b" * 64}
            return response([raw_notice()])

        def changed_account(*_):
            self.bridge.remote_user = {**user, "username": "other-user"}
            return response([raw_notice()])

        def changed_connection(*_):
            self.bridge._network_available = False
            return response([raw_notice()])

        def changed_grants_in_place(*_):
            self.bridge.remote_user["projects"].clear()
            return response([raw_notice()])

        for operation in (changed_token, changed_pin, changed_account,
                          changed_connection, changed_grants_in_place):
            self.bridge.connection = copy.deepcopy(base)
            self.bridge.remote_token = token
            self.bridge.remote_user = copy.deepcopy(user)
            self.bridge._network_available = True
            self.request.side_effect = operation
            with self.subTest(changed=operation.__name__), self.assertRaises(
                    PermissionError):
                self.bridge.mtrNoticeCommand(list_command())

    def test_bridge_js_exposes_only_named_manual_entrypoint(self):
        self.assertIn("'mtrNoticeCommand'", JS_BRIDGE)
        self.assertEqual(JS_BRIDGE.count("'mtrNoticeCommand'"), 1)


if __name__ == "__main__":
    unittest.main()
