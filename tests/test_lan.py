import json
from http.client import HTTPConnection
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import native_app
from lan import LanService


class LanTests(unittest.TestCase):
    def test_http_rejects_ambiguous_framing_and_duplicate_auth_headers(self):
        # Exercise real HTTP parsing, not a simulated service method. Ambiguous
        # headers must be refused *before* any login or state operation.
        body = json.dumps({"username": "admin", "password": "admin-test-password"}).encode()

        def raw_request(method, endpoint, headers, payload=b""):
            conn = HTTPConnection("127.0.0.1", self.port, timeout=8)
            try:
                conn.putrequest(method, endpoint)
                for name, value in headers:
                    conn.putheader(name, value)
                conn.endheaders(payload)
                response = conn.getresponse()
                response.read()
                return response.status
            finally:
                conn.close()

        login_headers = [("Content-Type", "application/json"),
                         ("Content-Length", str(len(body)))]
        self.assertEqual(raw_request("POST", "/api/login", login_headers + [
            ("Content-Length", str(len(body)))], body), 400)
        self.assertEqual(raw_request("POST", "/api/login", login_headers + [
            ("Transfer-Encoding", "chunked")], body), 400)
        self.assertEqual(raw_request("GET", "/api/me", [
            ("Authorization", "Bearer " + self.token),
            ("Authorization", "Bearer " + self.token)]), 400)

    def test_standalone_prepare_http_route_is_reachable_and_admin_guarded(self):
        # Deliberately unknown synthetic task: admin reaches the validated
        # handler (400), rather than a dead endpoint (404). Unauthenticated
        # requests cannot even attempt authoritative task resolution (403).
        request = {"taskId": "unknown.synthetic", "expenseId": None}
        self.assertStatus(403, lambda: self.request(
            "/api/standalone-accounting/prepare", request))
        self.assertStatus(400, lambda: self.request(
            "/api/standalone-accounting/prepare", request, self.token))
        self.assertStatus(400, lambda: self.request(
            "/api/standalone-accounting/prepare", {
                **request, "unitPrice": 1}, self.token))

    def test_standalone_quote_http_uses_exact_accounting_engine_and_admin_acl(self):
        payload = {"quantity": 100, "unitPrice": 20000, "currency": "TOMAN"}
        self.assertStatus(403, lambda: self.request(
            "/api/standalone-accounting/quote", payload))
        editor = self.create_user("quote-editor", "editor")
        self.assertStatus(403, lambda: self.request(
            "/api/standalone-accounting/quote", payload, editor))
        quote = self.request("/api/standalone-accounting/quote", payload, self.token)
        self.assertEqual((quote["status"], quote["amountRial"]),
                         ("quote-only", "20000000"))
        self.assertStatus(400, lambda: self.request(
            "/api/standalone-accounting/quote", {**payload, "quantity": True},
            self.token))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="madar-lan-")
        self.root = Path(self.temporary.name)
        self.mock = patch.object(native_app, "datadir", return_value=self.root)
        self.mock.start()
        self.bridge = native_app.Bridge()
        # LAN contract tests require explicit synthetic projects/cards.
        # Customer first-run remains empty; do not seed production defaults.
        self.bridge.saveState(native_app.initial_state())
        self.server = LanService(self.bridge, self.root / "users.json", "127.0.0.1", 0)
        self.server.setup_owner("admin", "admin-test-password")
        self.port = self.server.start()
        self.base = f"http://127.0.0.1:{self.port}"
        self.token = self.request("/api/login", {
            "username": "admin", "password": "admin-test-password"
        })["token"]

    def tearDown(self):
        self.server.stop()
        self.mock.stop()
        self.temporary.cleanup()

    def request(self, endpoint, payload=None, token=None, method=None):
        kwargs = {}
        if payload is not None:
            kwargs["data"] = json.dumps(payload, ensure_ascii=False).encode("utf8")
        req = Request(self.base + endpoint, **kwargs,
                      headers={"Content-Type": "application/json",
                               **({"Authorization": "Bearer " + token} if token else {})},
                      method=method or ("POST" if payload is not None else "GET"))
        with urlopen(req, timeout=8) as response:
            return json.loads(response.read())

    def assertStatus(self, code, callback):
        with self.assertRaises(HTTPError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def create_user(self, username, role, projects=None):
        self.request("/api/user", {"username": username, "password": "secure-user-123",
                                   "role": role, "projects": projects}, self.token)
        return self.request("/api/login", {"username": username,
                                            "password": "secure-user-123"})["token"]

    def test_login_is_required_and_passwords_not_returned(self):
        self.assertStatus(403, lambda: self.request("/api/state"))
        self.assertStatus(403, lambda: self.request("/api/login", {
            "username": "admin", "password": "wrong"
        }))
        users = self.request("/api/users", token=self.token)["users"]
        self.assertEqual(users[0]["username"], "admin")
        self.assertNotIn("passwordHash", users[0])

    def test_viewer_can_only_read_and_sees_scoped_project(self):
        reader = self.create_user("reader", "viewer", ["p-sample"])
        response = self.request("/api/state", token=reader)
        self.assertEqual([p["id"] for p in response["state"]["projects"]], ["p-sample"])
        self.assertTrue(response["state"]["tasks"])
        self.assertStatus(403, lambda: self.request("/api/state", {
            "revision": response["revision"], "state": response["state"]
        }, reader))
        self.assertStatus(403, lambda: self.request("/api/users", token=reader))

    def test_scoped_editor_cannot_edit_other_projects_or_global_settings(self):
        writer = self.create_user("writer", "editor", ["p-sample"])
        response = self.request("/api/state", token=writer)
        state = response["state"]
        self.assertEqual(len(state["projects"]), 1)
        forbidden = json.loads(json.dumps(state))
        forbidden["settings"]["theme"] = "dark"
        self.assertStatus(403, lambda: self.request("/api/state", {
            "state": forbidden, "revision": response["revision"]
        }, writer))
        state["tasks"][0]["title"] = "وظیفه به‌روزشده"
        self.request("/api/state", {"state": state, "revision": response["revision"]}, writer)
        self.assertEqual(self.bridge.getState()["tasks"][0]["title"], "وظیفه به‌روزشده")
        self.assertEqual(len(self.bridge.getState()["projects"]), 2)

    def test_concurrent_stale_update_rejected(self):
        a = self.request("/api/state", token=self.token)
        b = self.request("/api/state", token=self.token)
        first = a["state"]
        first["tasks"][0]["title"] = "تغییر اول"
        self.request("/api/state", {"revision": a["revision"], "state": first}, self.token)
        second = b["state"]
        second["tasks"][0]["title"] = "تغییر دوم"
        self.assertStatus(409, lambda: self.request("/api/state", {
            "revision": b["revision"], "state": second
        }, self.token))
        self.assertEqual(self.bridge.getState()["tasks"][0]["title"], "تغییر اول")

    def test_non_admin_cannot_add_accounts(self):
        reader = self.create_user("reader", "viewer")
        self.assertStatus(403, lambda: self.request("/api/user", {
            "username": "hacker", "password": "test-password-123", "role": "admin"
        }, reader))

    def test_server_does_not_serve_ui_or_private_files(self):
        self.assertStatus(404, lambda: self.request("/tasks.json", token=self.token))
        self.assertStatus(404, lambda: self.request("/lan-users.json", token=self.token))

    def test_real_desktop_bridge_client_reads_and_writes_over_lan(self):
        self.create_user("worker", "editor", ["p-sample"])
        client_folder = self.root / "client-pc"
        client_folder.mkdir()
        with patch.object(native_app, "datadir", return_value=client_folder):
            client = native_app.Bridge()
        client.lanJoin(self.base, "worker", "secure-user-123")
        received = client.getState()
        self.assertEqual(len(received["projects"]), 1)
        self.assertIn("__remoteRevision", received)
        received["tasks"][0]["title"] = "تغییر از کلاینت"
        saved = client.saveState(received)
        self.assertTrue(saved["revision"])
        self.assertEqual(self.bridge.getState()["tasks"][0]["title"], "تغییر از کلاینت")
        # The same stale snapshot cannot overwrite a newer save.
        with self.assertRaisesRegex(RuntimeError, "CONFLICT"):
            client.saveState(received)
        client.lanLeave()
        self.assertEqual(client.lanStatus()["mode"], "solo")

    def test_file_links_and_time_estimates_share_only_with_authorized_project(self):
        state = self.bridge.getState()
        state["projects"][1]["fileLinks"] = [{
            "id": "f1", "name": "نقشه", "path": r"\\SERVER\Share\plan.pdf"}]
        state["tasks"][0]["estimatedMinutes"] = 180
        self.bridge.saveState(state)
        scoped = self.create_user("guest2", "viewer", ["p-personal"])
        result = self.request("/api/state", token=scoped)["state"]
        self.assertFalse(result["tasks"])
        self.assertEqual(len(result["projects"]), 1)
        member = self.create_user("member2", "editor", ["p-sample"])
        result = self.request("/api/state", token=member)
        self.assertEqual(result["state"]["projects"][0]["fileLinks"][0]["name"], "نقشه")
        self.assertEqual(result["state"]["tasks"][0]["estimatedMinutes"], 180)
        illegal = result["state"]
        illegal["projects"][0]["fileLinks"][0]["path"] = r"\\SERVER\Share\secret.pdf"
        self.assertStatus(403, lambda: self.request("/api/state", {
            "state": illegal, "revision": result["revision"]
        }, member))

    def test_user_profile_self_service_and_admin_password_reset(self):
        user_token = self.create_user("designer", "editor", ["p-sample"])
        profiles = self.request("/api/profiles", token=user_token)["users"]
        self.assertTrue(any(u["username"] == "designer" for u in profiles))
        self.assertFalse(any("passwordHash" in u for u in profiles))
        updated = self.request("/api/profile", {
            "displayName": "مسئول طراحی", "avatarIcon": "palette", "avatarPhoto": ""
        }, user_token)["user"]
        self.assertEqual(updated["avatarIcon"], "palette")
        self.assertEqual(updated["displayName"], "مسئول طراحی")
        self.assertStatus(403, lambda: self.request("/api/password", {
            "current": "wrong", "newPassword": "new-valid-secret"
        }, user_token))
        self.request("/api/password", {
            "current": "secure-user-123", "newPassword": "new-valid-secret"
        }, user_token)
        self.assertStatus(403, lambda: self.request("/api/login", {
            "username": "designer", "password": "secure-user-123"
        }))
        next_token = self.request("/api/login", {
            "username": "designer", "password": "new-valid-secret"
        })["token"]
        self.assertStatus(403, lambda: self.request("/api/reset-password", {
            "username": "designer", "newPassword": "reset-secret-new"
        }, next_token))
        self.request("/api/reset-password", {
            "username": "designer", "newPassword": "reset-secret-new"
        }, self.token)
        self.assertStatus(403, lambda: self.request("/api/state", token=next_token))
        self.assertEqual(self.request("/api/login", {
            "username": "designer", "password": "reset-secret-new"
        })["user"]["displayName"], "مسئول طراحی")

    def test_profile_image_rejects_svg_and_oversize(self):
        token = self.create_user("worker3", "editor")
        self.assertStatus(400, lambda: self.request("/api/profile", {
            "avatarIcon": "user", "avatarPhoto": "data:image/svg+xml;base64,PHN2Zz4="
        }, token))
        self.assertStatus(400, lambda: self.request("/api/profile", {
            "avatarIcon": "user", "avatarPhoto": "data:image/png;base64," + "A"*130000
        }, token))
        self.assertStatus(400, lambda: self.request("/api/profile", {
            "avatarIcon": "not-valid", "avatarPhoto": ""
        }, token))

    def test_assignees_are_checked_against_project_scope(self):
        self.create_user("narrow", "editor", ["p-personal"])
        current = self.request("/api/state", token=self.token)
        state = current["state"]
        state["tasks"][0]["assignees"] = ["narrow"]
        self.assertStatus(403, lambda: self.request("/api/state", {
            "state": state, "revision": current["revision"]
        }, self.token))
        self.create_user("wide", "editor", ["p-sample"])
        latest = self.request("/api/state", token=self.token)
        latest["state"]["tasks"][0]["assignees"] = ["wide"]
        self.request("/api/state", {
            "state": latest["state"], "revision": latest["revision"]
        }, self.token)
        self.assertStatus(400, lambda: self.request("/api/user", {
            "username": "wide", "role": "editor", "projects": ["p-personal"]
        }, self.token))
        self.request("/api/users", {"username": "wide"}, self.token)
        self.assertEqual(self.bridge.getState()["tasks"][0]["assignees"], [])


if __name__ == "__main__":
    unittest.main()
