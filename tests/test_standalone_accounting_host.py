"""Standalone host/LAN boundary tests; synthetic temp dirs, never real APPDATA."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lan import (
    LanService, standalone_command_request, standalone_finance_access,
    standalone_finance_accounts,
)
from native_app import Bridge, JS_BRIDGE


ADMIN = {"username": "admin", "role": "admin",
         "passwordHash": "SENSITIVE", "projects": None}
EDITOR = {"username": "editor", "role": "editor",
          "financeView": True, "financeEdit": True,
          "passwordHash": "DO_NOT_SEND", "projects": ["task-project"]}
READER = {"username": "reader", "role": "viewer",
          "financeView": True, "financeEdit": True,
          "passwordHash": "DO_NOT_SEND"}
VIEWER = {"username": "viewer", "role": "viewer",
          "financeView": False, "financeEdit": False}
WRITE_ONLY = {"username": "writer", "role": "editor", "financeEdit": True}
ROSTER = {x["username"]: dict(x) for x in (ADMIN, EDITOR, READER, VIEWER, WRITE_ONLY)}


class FakeStandaloneStore:
    instances = []
    def __init__(self, db_path, *, default_currency="TOMAN"):
        self.path = Path(db_path)
        self.default_currency = default_currency
        self.calls = []
        type(self).instances.append(self)

    def read(self, *, actor, accounts):
        self.calls.append(("read", actor, accounts))
        return {"revision": 0, "view": {"standalone": True}}

    def command(self, command, *, actor, accounts, expected_revision, now):
        self.calls.append(("command", command, actor, accounts, expected_revision, now))
        return {"revision": expected_revision + 1, "result": {"ok": True},
                "view": {"standalone": True}}


def minimal_bridge(data_dir, *, mode="solo"):
    """Do not call Bridge.__init__ (which initializes tasks/APPDATA)."""
    bridge = Bridge.__new__(Bridge)
    bridge.path = Path(data_dir) / "tasks.json"
    bridge._lock = threading.RLock()
    bridge.connection = {"mode": mode}
    bridge.lan = None
    return bridge


class StandaloneHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-standalone-host-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bridge = minimal_bridge(self.root)
        FakeStandaloneStore.instances = []
        module = types.ModuleType("standalone_accounting")
        module.StandaloneAccountingStore = FakeStandaloneStore
        patcher = patch.dict(sys.modules, {"standalone_accounting": module})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_store_is_lazily_imported_only_when_api_called(self):
        self.assertFalse(FakeStandaloneStore.instances)
        self.assertFalse((self.root / "standalone-accounting.sqlite3").exists())
        self.bridge.standaloneAccountingRead()
        self.assertEqual(len(FakeStandaloneStore.instances), 1)
        self.assertEqual(FakeStandaloneStore.instances[0].path,
                         self.root / "standalone-accounting.sqlite3")
        self.assertFalse((self.root / "finance.json").exists())
        self.assertFalse((self.root / "tasks.json").exists())

    def test_local_standalone_read_uses_trusted_local_admin(self):
        result = self.bridge.standaloneAccountingRead()
        self.assertRegex(result.pop("postingToday"), r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(result, {"revision": 0, "view": {"standalone": True},
                                  "capabilities": {
                                      "canView": True, "canManage": True,
                                      "canDraft": True, "canAdmin": True}})
        action, actor, accounts = FakeStandaloneStore.instances[0].calls[0]
        self.assertEqual((action, actor), ("read", "local"))
        self.assertEqual(accounts["local"]["role"], "admin")
        self.assertTrue(accounts["local"]["financeView"])
        self.assertNotIn("projects", accounts["local"])

    def test_local_standalone_command_contract_and_utc_clock(self):
        output = self.bridge.standaloneAccountingCommand(
            {"command": {"type": "journal.post", "businessId": "sample"},
             "expectedRevision": 3})
        self.assertEqual(output["revision"], 4)
        call = FakeStandaloneStore.instances[0].calls[0]
        self.assertEqual(call[0], "command")
        self.assertEqual(call[1], {"type": "journal.post", "businessId": "sample"})
        self.assertEqual(call[2], "local")
        self.assertEqual(call[4], 3)
        self.assertTrue(call[5].endswith("+00:00"))

    def test_command_envelope_strict_no_principal_or_company_override(self):
        bad = (
            None, [], {},
            {"command": {}, "expectedRevision": 0, "actor": "admin"},
            {"command": {}, "expectedRevision": 0, "companyId": "company-A"},
            {"command": {}, "expectedRevision": True},
            {"command": {}, "expectedRevision": 1.0},
            {"command": {}, "expectedRevision": "1"},
            {"command": {}, "expectedRevision": -1},
            {"command": [], "expectedRevision": 0},
            {"command": {}, "expectedRevision": None},
            {"command": {}}, {"expectedRevision": 0},
        )
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.bridge.standaloneAccountingCommand(value)
        self.assertEqual(FakeStandaloneStore.instances, [])

    def test_access_read_requires_finance_view_but_admin_allowed(self):
        standalone_finance_access("admin", ROSTER, mutation=False)
        standalone_finance_access("reader", ROSTER, mutation=False)
        standalone_finance_access("editor", ROSTER, mutation=False)
        # Explicit financeEdit grants read access even when financeView=False.
        standalone_finance_access("writer", ROSTER, mutation=False)
        for user in ("viewer", "missing"):
            with self.subTest(user=user), self.assertRaises(PermissionError):
                standalone_finance_access(user, ROSTER, mutation=False)

    def test_mutation_requires_admin_or_editor_grant_never_viewer(self):
        standalone_finance_access("admin", ROSTER, mutation=True)
        standalone_finance_access("editor", ROSTER, mutation=True)
        for user in ("viewer", "reader", "missing"):
            with self.subTest(user=user), self.assertRaises(PermissionError):
                standalone_finance_access(user, ROSTER, mutation=True)
        standalone_finance_access("writer", ROSTER, mutation=True)

    def test_editor_needs_explicit_finance_edit_permission(self):
        restricted = {**ROSTER, "editor": {**EDITOR, "financeEdit": False}}
        with self.assertRaises(PermissionError):
            standalone_finance_access("editor", restricted, mutation=True)
        standalone_finance_access("editor", restricted, mutation=False)

    def test_password_hashes_and_projects_not_given_to_isolated_store(self):
        result = self.bridge._standalone_accounting_read_local(
            actor="editor", accounts=ROSTER)
        self.assertIn("view", result)
        self.assertEqual(result["capabilities"], {
            "canView": True, "canManage": True, "canDraft": True,
            "canAdmin": False})
        accounts = FakeStandaloneStore.instances[0].calls[0][2]
        self.assertEqual(set(accounts["editor"]),
                         {"username", "role", "financeView", "financeEdit"})
        self.assertNotIn("SENSITIVE", repr(accounts))
        self.assertNotIn("DO_NOT_SEND", repr(accounts))
        self.assertNotIn("task-project", repr(accounts))

    def test_finance_read_only_capabilities_are_host_derived(self):
        result = self.bridge._standalone_accounting_read_local(
            actor="reader", accounts=ROSTER)
        self.assertEqual(result["capabilities"], {
            "canView": True, "canManage": False, "canDraft": False,
            "canAdmin": False})
        with self.assertRaises(PermissionError):
            self.bridge._standalone_accounting_read_local(
                actor="viewer", accounts=ROSTER)

    def test_direct_helper_denied_principal_before_db_instantiation(self):
        with self.assertRaises(PermissionError):
            self.bridge._standalone_accounting_read_local(
                actor="viewer", accounts=ROSTER)
        with self.assertRaises(PermissionError):
            self.bridge._standalone_accounting_command_local(
                {"command": {}, "expectedRevision": 0},
                actor="reader", accounts=ROSTER)
        self.assertEqual(FakeStandaloneStore.instances, [])

    def test_remote_read_never_imports_or_opens_local_db(self):
        self.bridge.connection = {"mode": "client"}
        self.bridge._remote_request = Mock(return_value={"revision": 11, "view": {}})
        self.assertEqual(self.bridge.standaloneAccountingRead()["revision"], 11)
        self.bridge._remote_request.assert_called_once_with("/api/standalone-accounting")
        self.assertEqual(FakeStandaloneStore.instances, [])

    def test_remote_command_never_imports_or_opens_local_db(self):
        self.bridge.connection = {"mode": "client"}
        self.bridge._remote_request = Mock(return_value={
            "revision": 8, "result": {"ok": True}, "view": {}})
        command = {"command": {"type": "sample"}, "expectedRevision": 7}
        self.assertEqual(self.bridge.standaloneAccountingCommand(command)["revision"], 8)
        self.bridge._remote_request.assert_called_once_with(
            "/api/standalone-accounting", command)
        self.assertEqual(FakeStandaloneStore.instances, [])

    def test_remote_connection_failure_never_falls_back_to_local(self):
        self.bridge.connection = {"mode": "client"}
        self.bridge._remote_request = Mock(side_effect=ConnectionError("offline"))
        with self.assertRaises(ConnectionError):
            self.bridge.standaloneAccountingRead()
        with self.assertRaises(ConnectionError):
            self.bridge.standaloneAccountingCommand(
                {"command": {"type": "sample"}, "expectedRevision": 1})
        self.assertEqual(FakeStandaloneStore.instances, [])

    def test_account_guard_rejects_forged_username_and_invalid_registry(self):
        modified = {**ROSTER, "editor": {**EDITOR, "username": "admin"}}
        with self.assertRaises(PermissionError):
            standalone_finance_access("editor", modified, mutation=True)
        for invalid in ({}, {"editor": None}, [], None):
            with self.subTest(invalid=invalid), self.assertRaises(PermissionError):
                standalone_finance_accounts(invalid)

    def test_js_bridge_exposes_two_methods(self):
        self.assertIn("'standaloneAccountingRead'", JS_BRIDGE)
        self.assertIn("'standaloneAccountingCommand'", JS_BRIDGE)


class StandaloneLanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-standalone-lan-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bridge = minimal_bridge(self.root, mode="server")
        FakeStandaloneStore.instances = []
        module = types.ModuleType("standalone_accounting")
        module.StandaloneAccountingStore = FakeStandaloneStore
        patcher = patch.dict(sys.modules, {"standalone_accounting": module})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = LanService(
            self.bridge, self.root / "lan-users.json",
            bind="127.0.0.1", port=0)
        self.service.users = {key: dict(value) for key, value in ROSTER.items()}
        self.tokens = {}
        import time
        for user in ROSTER:
            token = "token-" + user
            self.service.sessions[token] = (user, time.time() + 3600)
            self.tokens[user] = token
        self.bridge.lan = self.service

    def test_service_requires_real_token_before_reading_store(self):
        with self.assertRaises(PermissionError):
            self.service.standalone_accounting_read("missing")
        self.assertEqual(FakeStandaloneStore.instances, [])

    def test_lan_reader_requires_view_and_sanitized_acl(self):
        result = self.service.standalone_accounting_read(self.tokens["reader"])
        self.assertEqual(result["view"]["standalone"], True)
        self.assertEqual(result["capabilities"], {
            "canView": True, "canManage": False, "canDraft": False,
            "canAdmin": False})
        editor = self.service.standalone_accounting_read(self.tokens["editor"])
        self.assertEqual(editor["capabilities"], {
            "canView": True, "canManage": True, "canDraft": True,
            "canAdmin": False})
        accounts = FakeStandaloneStore.instances[0].calls[0][2]
        self.assertNotIn("passwordHash", accounts["admin"])
        self.assertNotIn("projects", accounts["editor"])
        with self.assertRaises(PermissionError):
            self.service.standalone_accounting_read(self.tokens["viewer"])

    def test_lan_viewer_mutation_blocked_and_editor_allowed(self):
        payload = {"command": {"type": "sample"}, "expectedRevision": 2}
        with self.assertRaises(PermissionError):
            self.service.standalone_accounting_command(self.tokens["reader"], payload)
        with self.assertRaises(PermissionError):
            self.service.standalone_accounting_command(self.tokens["viewer"], payload)
        result = self.service.standalone_accounting_command(self.tokens["editor"], payload)
        self.assertEqual(result["revision"], 3)
        call = FakeStandaloneStore.instances[-1].calls[0]
        self.assertEqual(call[2], "editor")

    def test_lan_invalid_envelope_denied_before_any_db(self):
        with self.assertRaises(ValueError):
            self.service.standalone_accounting_command(
                self.tokens["admin"], {"command": {}, "expectedRevision": False})
        self.assertEqual(FakeStandaloneStore.instances, [])

    def http(self, endpoint, *, method="GET", token=None, data=None):
        headers = {}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if data is not None:
            headers["Content-Type"] = "application/json"
        raw = json.dumps(data).encode("utf8") if data is not None else None
        req = Request(f"http://127.0.0.1:{self.service.port}{endpoint}", data=raw,
                      headers=headers, method=method)
        try:
            with urlopen(req, timeout=4) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf8"))

    def test_http_get_post_end_to_end_with_fake_standalone_store(self):
        self.service.start()
        self.addCleanup(self.service.stop)
        status, view = self.http("/api/standalone-accounting",
                                 token=self.tokens["reader"])
        self.assertEqual((status, view["revision"]), (200, 0))
        self.assertFalse(view["capabilities"]["canManage"])
        self.assertFalse(view["capabilities"]["canDraft"])
        status, update = self.http(
            "/api/standalone-accounting", token=self.tokens["editor"],
            method="POST", data={"command": {"type": "sample"}, "expectedRevision": 5})
        self.assertEqual((status, update["revision"]), (200, 6))
        self.assertEqual(len(FakeStandaloneStore.instances), 2)

    def test_http_no_token_no_read_and_viewer_forbidden(self):
        self.service.start()
        self.addCleanup(self.service.stop)
        status, _ = self.http("/api/standalone-accounting")
        self.assertEqual(status, 403)
        status, _ = self.http("/api/standalone-accounting",
                              token=self.tokens["viewer"])
        self.assertEqual(status, 403)
        self.assertEqual(FakeStandaloneStore.instances, [])

    def test_http_rejects_invalid_payload_or_query(self):
        self.service.start()
        self.addCleanup(self.service.stop)
        status, _ = self.http("/api/standalone-accounting?projectId=a",
                              token=self.tokens["admin"])
        self.assertEqual(status, 400)
        status, _ = self.http("/api/standalone-accounting", method="POST",
                              token=self.tokens["admin"],
                              data={"command": {}, "expectedRevision": True})
        self.assertEqual(status, 400)
        self.assertEqual(FakeStandaloneStore.instances, [])

    def test_http_unauthenticated_post_rejects_even_malformed_payload(self):
        self.service.start()
        self.addCleanup(self.service.stop)
        status, _ = self.http("/api/standalone-accounting", method="POST",
                              data={"command": {}, "expectedRevision": True})
        self.assertEqual(status, 403)
        self.assertEqual(FakeStandaloneStore.instances, [])

    def test_http_get_and_post_do_not_touch_tasks_or_finance(self):
        self.bridge.getState = Mock(side_effect=AssertionError("task manager access"))
        self.bridge._load_finance = Mock(side_effect=AssertionError("finance access"))
        self.service.start()
        self.addCleanup(self.service.stop)
        self.assertEqual(self.http("/api/standalone-accounting",
                         token=self.tokens["admin"])[0], 200)
        self.assertEqual(self.http(
            "/api/standalone-accounting", method="POST",
            token=self.tokens["admin"],
            data={"command": {"type": "sample"}, "expectedRevision": 0})[0], 200)
        self.bridge.getState.assert_not_called()
        self.bridge._load_finance.assert_not_called()


class RealStandaloneStorageHostTests(unittest.TestCase):
    """Actual worker-10 SQLite store through Bridge and LAN, isolated temp paths."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-standalone-real-host-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bridge = minimal_bridge(self.root)

    def test_real_store_local_read_and_command_and_revision_conflict(self):
        from standalone_accounting import AccountingRevisionConflict
        first = self.bridge.standaloneAccountingRead()
        self.assertEqual(first["revision"], 0)
        self.assertEqual(first["view"]["currency"], "RIAL")
        self.assertEqual(first["view"]["parties"], {})
        self.assertTrue((self.root / "standalone-accounting.sqlite3").is_file())
        payload = {"command": {"type": "party.register", "eventId": "real-1",
                               "partyId": "customer-1", "name": "Synthetic",
                               "kind": "customer"},
                   "expectedRevision": 0}
        committed = self.bridge.standaloneAccountingCommand(payload)
        self.assertEqual(committed["revision"], 1)
        self.assertIn("customer-1", self.bridge.standaloneAccountingRead()["view"]["parties"])
        with self.assertRaises(AccountingRevisionConflict):
            self.bridge.standaloneAccountingCommand(payload)
        # Standalone is persistent across recreated Bridge shells, not in tasks.json.
        reopened = minimal_bridge(self.root)
        self.assertEqual(reopened.standaloneAccountingRead()["revision"], 1)
        for other in ("tasks.json", "finance.json", "madar-unified.sqlite3"):
            self.assertFalse((self.root / other).exists())

    def test_real_lan_http_mutation_and_read_are_isolated(self):
        service = LanService(self.bridge, self.root / "lan-users.json",
                             bind="127.0.0.1", port=0)
        service.users = {key: dict(value) for key, value in ROSTER.items()}
        import time
        service.sessions["editor-token"] = ("editor", time.time() + 3600)
        service.sessions["reader-token"] = ("reader", time.time() + 3600)
        service.sessions["viewer-token"] = ("viewer", time.time() + 3600)
        self.bridge.connection = {"mode": "server"}
        self.bridge.lan = service
        self.bridge.getState = Mock(side_effect=AssertionError("tasks must be isolated"))
        self.bridge._load_finance = Mock(
            side_effect=AssertionError("old finance must be isolated"))
        service.start()
        self.addCleanup(service.stop)

        def send(method, token, command=None):
            headers = {"Authorization": "Bearer " + token}
            body = None
            if command is not None:
                body = json.dumps(command).encode("utf8")
                headers["Content-Type"] = "application/json"
            req = Request("http://127.0.0.1:" + str(service.port) +
                          "/api/standalone-accounting", data=body,
                          headers=headers, method=method)
            try:
                with urlopen(req, timeout=4) as resp:
                    return resp.status, json.load(resp)
            except HTTPError as exc:
                return exc.code, json.loads(exc.read().decode("utf8"))

        payload = {"command": {"type": "party.register", "eventId": "lan-issue-1",
                               "partyId": "supplier-1", "name": "Paper",
                               "kind": "vendor"},
                   "expectedRevision": 0}
        self.assertEqual(send("GET", "reader-token")[1]["revision"], 0)
        changed_status, changed = send("POST", "editor-token", payload)
        self.assertEqual((changed_status, changed["revision"]), (200, 1))
        self.assertIn("supplier-1",
                      send("GET", "reader-token")[1]["view"]["parties"])
        self.assertEqual(send("POST", "viewer-token", payload)[0], 403)
        self.assertEqual(send("POST", "editor-token", payload)[0], 409)
        self.assertEqual(send("GET", "bad-token")[0], 403)
        self.bridge.getState.assert_not_called()
        self.bridge._load_finance.assert_not_called()
        self.assertFalse((self.root / "finance.json").exists())
        self.assertFalse((self.root / "tasks.json").exists())


if __name__ == "__main__":
    unittest.main()
