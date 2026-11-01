"""Integration adapter v1: TLS gate, key lifecycle, ACL, strict IO and CAS."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app
from integration_api_v1 import API_PREFIX, IntegrationRouter
from lan import LanService

try:
    from test_lan_tls import _CERT, _KEY
except ModuleNotFoundError:
    from tests.test_lan_tls import _CERT, _KEY


SECRET = "integration-user-password"


class IntegrationV1Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="madar-int-v1-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        with patch.object(native_app, "datadir", return_value=self.root):
            self.bridge = native_app.Bridge()
            self.bridge.saveState(native_app.initial_state())
        self.cert = self.root / "test.crt"
        self.keyfile = self.root / "test.key"
        self.cert.write_text(_CERT, encoding="ascii")
        self.keyfile.write_text(_KEY, encoding="ascii")
        self.service = LanService(self.bridge, self.root / "lan-users.json",
                                  bind="127.0.0.1", port=0,
                                  certfile=self.cert, keyfile=self.keyfile)
        self.service.setup_owner("owner", SECRET)
        self.service.start()
        self.addCleanup(self.service.stop)
        self.owner_token = self.service.authenticate("owner", SECRET)["token"]
        self.users = {}
        for name, role, projects in (
                ("viewer", "viewer", ["p-sample"]),
                ("editor", "editor", ["p-sample"]),
                ("outsider", "editor", ["p-personal"]),
                ("wide", "editor", None)):
            self.service.upsert_user(self.owner_token, {
                "username": name, "password": SECRET,
                "role": role, "projects": projects})
            self.users[name] = self.service.authenticate(name, SECRET)["token"]
        self.router = IntegrationRouter(self.service)

    def issue(self, username="editor", permissions=("read",), **kwargs):
        return self.router.issue_key(self.owner_token, username,
                                     permissions=permissions, **kwargs)

    def call(self, key, method="GET", path="/cards", payload=None, *,
             raw=None, headers=None):
        body = raw if raw is not None else (
            b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf8"))
        supplied = {"X-Madar-Integration-Key": key}
        if method == "PATCH":
            supplied["Content-Type"] = "application/json"
        supplied.update(headers or {})
        return self.router.handle(method, API_PREFIX + path, supplied, body)

    def card(self, project="p-sample"):
        return next(t for t in self.bridge.getState()["tasks"]
                    if t["projectId"] == project)

    def test_no_listener_is_opened_by_router_and_http_host_fails_closed(self):
        original_socket = self.service.server.socket
        self.assertTrue(original_socket)
        self.assertIs(self.router.service.server.socket, original_socket)
        insecure_service = LanService(self.bridge, self.root / "not-listening-users.json",
                                      bind="127.0.0.1", port=0)
        insecure_service.setup_owner("insecure", SECRET)
        insecure_service.start()
        self.addCleanup(insecure_service.stop)
        insecure_router = IntegrationRouter(insecure_service)
        self.assertEqual(insecure_router.handle("GET", API_PREFIX + "/cards").status, 503)
        with self.assertRaises(Exception):
            insecure_router.issue_key(insecure_service.authenticate("insecure", SECRET)["token"],
                                      "insecure")

    def test_requires_explicit_admin_issuance_and_separate_integration_key(self):
        with self.assertRaises(PermissionError):
            self.router.issue_key(self.users["editor"], "editor")
        with self.assertRaises(ValueError):
            self.issue(permissions=("admin",))
        with self.assertRaises(ValueError):
            self.issue(permissions=(["read"],))
        with self.assertRaises(ValueError):
            self.issue(lifetime_seconds=1)
        issued = self.issue()
        self.assertRegex(issued["key"], r"^mdv1_[A-Za-z0-9_-]{64}$")
        self.assertNotIn(issued["key"], repr(self.router._keys))
        self.assertNotIn(issued["key"], self.service.sessions)
        self.assertEqual(self.router.handle("GET", API_PREFIX + "/cards").status, 401)
        self.assertEqual(self.call(self.users["editor"]).status, 401)
        self.assertEqual(self.call(issued["key"]).status, 200)
        response = self.call(issued["key"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Madar-Integration-Version"], "1")

    def test_projection_never_contains_finance_fields_even_for_admin(self):
        for username in ("owner", "editor", "viewer"):
            key = self.issue(username)["key"]
            projects = self.call(key, path="/projects")
            cards = self.call(key)
            self.assertEqual(projects.status, 200)
            self.assertEqual(cards.status, 200)
            self.assertEqual(set(projects.json()), {"version", "projects"})
            for p in projects.json()["projects"]:
                self.assertLessEqual(set(p), {"id", "name"})
            for card in cards.json()["cards"]:
                self.assertLessEqual(set(card),
                    {"id", "projectId", "title", "status", "priority", "dueDate"})
            dump = projects.body + cards.body
            for forbidden in (b"passwordHash", b"cost", b"price", b"checklist",
                              b"finance", b"budget", b"fileLinks", b"avatarPhoto"):
                self.assertNotIn(forbidden, dump)

    def test_scopes_and_nonexistent_ids_hide_cross_project_cards(self):
        editor_key = self.issue("editor")["key"]
        outsider_key = self.issue("outsider")["key"]
        sample = self.card()
        sample_id = sample["id"]
        self.assertEqual(self.call(editor_key, path="/projects").json()["projects"][0]["id"], "p-sample")
        self.assertEqual(self.call(outsider_key, path="/cards/" + sample_id).status, 404)
        self.assertEqual(self.call(outsider_key, path="/cards").json()["cards"], [])
        self.assertEqual(self.call(outsider_key, path="/cards?projectId=p-sample").json()["cards"], [])
        self.assertEqual(self.call(editor_key, path="/cards/" + sample_id).status, 200)
        self.assertEqual(self.call(editor_key, path="/cards/missing-card").status, 404)
        self.assertEqual(self.call(editor_key, path="/cards/../../secrets").status, 404)

    def test_read_and_write_capabilities_are_distinct_from_lan_roles(self):
        card = self.card()
        original = card["title"]
        read_key = self.issue("editor")["key"]
        snapshot = self.call(read_key).json()
        body = {"title": "external change", "revision": snapshot["revision"]}
        url = "/cards/" + card["id"]
        self.assertEqual(self.call(read_key, "PATCH", url, body,
                                  headers={"Idempotency-Key": "r1"}).status, 403)
        viewer_key = self.issue("viewer", ("read", "write"))["key"]
        self.assertEqual(self.call(viewer_key, "PATCH", url, body,
                                  headers={"Idempotency-Key": "r1"}).status, 403)
        self.assertEqual(self.card()["title"], original)
        write_only = self.issue("editor", ("write",))["key"]
        self.assertEqual(self.call(write_only).status, 403)
        self.assertEqual(self.call(write_only, "PATCH", url, body,
                                  headers={"Idempotency-Key": "w1"}).status, 200)
        self.assertEqual(self.card()["title"], "external change")

    def test_patch_is_bounded_and_idempotent_with_optimistic_revision(self):
        key = self.issue("editor", ("read", "write"))["key"]
        card = self.card()
        url = "/cards/" + card["id"]
        first = self.call(key).json()
        data = {"title": "safe integration title", "revision": first["revision"]}
        before = self.bridge.getState()["tasks"][0]["title"]
        one = self.call(key, "PATCH", url, data, headers={"Idempotency-Key": "job-1"})
        self.assertEqual(one.status, 200)
        self.assertNotEqual(before, self.card()["title"])
        retry = self.call(key, "PATCH", url, data, headers={"Idempotency-Key": "job-1"})
        self.assertEqual(retry.status, 200)
        self.assertEqual(retry.body, one.body)
        new_data = {"title": "new title", "revision": first["revision"]}
        self.assertEqual(self.call(key, "PATCH", url, new_data,
                                  headers={"Idempotency-Key": "job-1"}).status, 409)
        self.assertEqual(self.call(key, "PATCH", url, new_data,
                                  headers={"Idempotency-Key": "job-2"}).status, 409)
        self.assertEqual(self.card()["title"], "safe integration title")

    def test_competing_api_keys_cannot_silently_overwrite_the_same_revision(self):
        one = self.issue("editor", ("read", "write"))["key"]
        two = self.issue("wide", ("read", "write"))["key"]
        card = self.card()
        revision = self.call(one).json()["revision"]
        path = "/cards/" + card["id"]

        def run(argument):
            key, title, request_id = argument
            return self.call(key, "PATCH", path, {"title": title, "revision": revision},
                             headers={"Idempotency-Key": request_id}).status

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(run, [(one, "first-winner", "parallel-1"),
                                                (two, "second-winner", "parallel-2")]))
        self.assertEqual(sorted(outcomes), [200, 409])
        self.assertIn(self.card()["title"], ("first-winner", "second-winner"))

    def test_malicious_or_oversized_requests_fail_without_mutation(self):
        key = self.issue("editor", ("read", "write"))["key"]
        card = self.card()
        path = "/cards/" + card["id"]
        revision = self.call(key).json()["revision"]
        original = card["title"]
        valid = {"title": "valid", "revision": revision}
        cases = [
            self.call(key, "PATCH", path, valid),  # missing idempotency
            self.call(key, "PATCH", path, valid, headers={"Idempotency-Key": "bad key"}),
            self.call(key, "PATCH", path, {**valid, "cost": 42},
                      headers={"Idempotency-Key": "m1"}),
            self.call(key, "PATCH", path, {**valid, "role": "admin"},
                      headers={"Idempotency-Key": "m2"}),
            self.call(key, "PATCH", path, {**valid, "title": "line\nnew"},
                      headers={"Idempotency-Key": "m3"}),
            self.call(key, "PATCH", path, {**valid, "revision": "abc"},
                      headers={"Idempotency-Key": "m4"}),
            self.call(key, "PATCH", path, raw=b'{"title":"first","title":"second","revision":"'
                      + revision.encode() + b'"}',
                      headers={"Idempotency-Key": "m5"}),
            self.call(key, "PATCH", path, raw=b'{"title":NaN,"revision":"' + revision.encode() + b'"}',
                      headers={"Idempotency-Key": "m6"}),
            self.call(key, "PATCH", path, raw=b"x" * 8193,
                      headers={"Idempotency-Key": "m7"}),
            self.call(key, "PATCH", path, valid,
                      headers={"Idempotency-Key": "m8", "Content-Type": "text/plain"}),
            self.call(key, "GET", "/cards?limit=-1"),
            self.call(key, "GET", "/cards?limit=1&limit=2"),
            self.call(key, "GET", "/cards?evil=1"),
            self.call(key, "GET", "/cards%2f" + card["id"]),
            self.call(key, "GET", "/cards", raw=b'{"x":1}'),
            self.call(key, "POST", path, valid),
        ]
        for response in cases:
            with self.subTest(body=response.body):
                self.assertIn(response.status, (400, 405, 413, 415))
                self.assertIn("error", response.json())
                self.assertNotIn("traceback", response.body.decode().lower())
        self.assertEqual(self.card()["title"], original)

    def test_permission_changes_take_effect_immediately_including_cached_replay(self):
        key = self.issue("editor", ("read", "write"))["key"]
        card = self.card()
        uri = "/cards/" + card["id"]
        rev = self.call(key).json()["revision"]
        data = {"title": "first success", "revision": rev}
        done = self.call(key, "PATCH", uri, data, headers={"Idempotency-Key": "same"})
        self.assertEqual(done.status, 200)
        self.service.upsert_user(self.owner_token, {
            "username": "editor", "role": "viewer", "projects": ["p-sample"],
            "password": ""})
        self.assertEqual(self.call(key, "PATCH", uri, data,
                                  headers={"Idempotency-Key": "same"}).status, 403)
        self.assertEqual(self.call(key).status, 200)
        self.service.upsert_user(self.owner_token, {
            "username": "editor", "role": "editor", "projects": ["p-personal"],
            "password": ""})
        self.assertEqual(self.call(key, "GET", uri).status, 404)
        self.assertEqual(self.call(key, "PATCH", uri, data,
                                  headers={"Idempotency-Key": "same"}).status, 404)

    def test_password_reset_revoke_expire_and_cross_router_cannot_reuse_key(self):
        issued = self.issue("editor")
        token = issued["key"]
        second_service = LanService(self.bridge, self.root / "second-users.json",
                                    certfile=self.cert, keyfile=self.keyfile, port=0,
                                    bind="127.0.0.1")
        second_service.setup_owner("different", SECRET)
        second_service.start()
        self.addCleanup(second_service.stop)
        second_router = IntegrationRouter(second_service)
        self.assertEqual(second_router.handle("GET", API_PREFIX + "/cards",
                                              {"X-Madar-Integration-Key": token}).status, 401)
        with self.assertRaises(PermissionError):
            self.router.revoke_key(self.users["editor"], issued["keyId"])
        self.service.reset_password(self.owner_token, "editor", "changed-password-456")
        self.assertEqual(self.call(token).status, 401)
        fresh = self.issue("editor")
        self.assertEqual(self.call(fresh["key"]).status, 200)
        self.assertTrue(self.router.revoke_key(self.owner_token, fresh["keyId"]))
        self.assertFalse(self.router.revoke_key(self.owner_token, fresh["keyId"]))
        self.assertEqual(self.call(fresh["key"]).status, 401)
        expiring = self.issue("editor", lifetime_seconds=60)
        import integration_api_v1
        with patch.object(integration_api_v1.time, "time",
                          return_value=expiring["expiresAt"] + 1):
            self.assertEqual(self.call(expiring["key"]).status, 401)

    def test_no_key_or_scope_leak_in_success_or_error_responses(self):
        key = self.issue("editor")["key"]
        for result in (self.call(key), self.call(key, path="/me"),
                       self.call(key, path="/projects"),
                       self.call(key, path="/cards/does-not-exist"),
                       self.call("definitely-not-a-key")):
            payload = result.body.decode("utf8")
            self.assertNotIn(key, payload)
            self.assertNotIn("passwordHash", payload)
            self.assertNotIn(SECRET, payload)
            self.assertNotIn('"projects":null', payload)


if __name__ == "__main__":
    unittest.main()
