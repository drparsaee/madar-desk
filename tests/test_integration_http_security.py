"""Black-box security acceptance of the mounted integration API over TLS sockets.

Real HTTPSConnection with a pinned test certificate, no mocks of router dispatch.
Each test uses disposable APPDATA/Bridge/account stores on 127.0.0.1.
No real user data or physical LAN host is contacted.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.client import HTTPConnection, HTTPSConnection
import json
import os
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch

import native_app
from lan import LanService, certificate_fingerprint, pinned_https_json

try:
    from test_lan_tls import _CERT, _KEY  # Existing test-only public TLS fixture.
except ModuleNotFoundError:
    from tests.test_lan_tls import _CERT, _KEY


SECRET = "acceptance-local-password"
PREFIX = "/integrations/v1"
CARD_FIELDS = {"id", "projectId", "title", "status", "priority", "dueDate"}
PROJECT_FIELDS = {"id", "name"}


class MountedIntegrationSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-mounted-api-audit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"APPDATA": str(self.root / "appdata")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.bridge = self._bridge("tls-host")
        self.bridge.saveState(native_app.initial_state())
        self.cert = self.root / "server-test.crt"
        self.key = self.root / "server-test.key"
        self.cert.write_text(_CERT, encoding="ascii")
        self.key.write_text(_KEY, encoding="ascii")
        self.service = LanService(self.bridge, self.root / "tls-host" / "lan-users.json",
                                  bind="127.0.0.1", port=0,
                                  certfile=self.cert, keyfile=self.key)
        self.service.setup_owner("admin", SECRET)
        self.service.start()
        self.addCleanup(self.service.stop)
        self.bridge.lan = self.service
        self.bridge.connection = {"mode": "server"}
        self.port = self.service.port
        self.fingerprint = certificate_fingerprint(self.cert)
        self.admin_token = self.service.authenticate("admin", SECRET)["token"]
        for name, role, grants in (
                ("editor", "editor", ["p-sample"]),
                ("outsider", "editor", ["p-personal"]),
                ("viewer", "viewer", ["p-sample"]),
                ("zero", "viewer", [])):
            self.service.upsert_user(self.admin_token, {
                "username": name, "password": SECRET,
                "role": role, "projects": grants})

    def _bridge(self, relative):
        folder = self.root / relative
        folder.mkdir(parents=True, exist_ok=True)
        with patch.object(native_app, "datadir", return_value=folder):
            return native_app.Bridge()

    def _issue(self, username="editor", permissions=("read",), ttl=3600):
        return self.bridge.integrationIssueKey(username, list(permissions),
                                               lifetime_seconds=ttl)

    def _connection(self, *, tls=True):
        if tls:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            connection = HTTPSConnection("127.0.0.1", self.port, timeout=4,
                                         context=context)
            connection.connect()
            cert = connection.sock.getpeercert(binary_form=True)
            self.assertEqual(hashlib.sha256(cert).hexdigest(), self.fingerprint)
        else:
            connection = HTTPConnection("127.0.0.1", self.port, timeout=4)
        return connection

    def _request(self, method, path, *, key=None, headers=(), body=b"",
                 content_length=None):
        """Send real raw HTTP headers, including duplicates, over verified TLS.

        Explicit low-level putheader() allows testing ambiguities that a dict
        request client normally collapses or normalizes away.
        """
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False,
                              separators=(",", ":")).encode("utf8")
        values = list(headers)
        if key is not None:
            values.append(("X-Madar-Integration-Key", key))
        if content_length is None and body:
            content_length = len(body)
        if content_length is not None and content_length != "omit":
            values.append(("Content-Length", str(content_length)))
        conn = self._connection()
        try:
            conn.putrequest(method, path)
            for name, value in values:
                conn.putheader(name, value)
            conn.endheaders(body if body else None)
            response = conn.getresponse()
            raw = response.read(200_000)
            status = response.status
            returned_headers = {k.lower(): v for k, v in response.getheaders()}
            try:
                value = json.loads(raw)
            except (UnicodeDecodeError, ValueError):
                self.fail(f"Non-JSON HTTP response, status={status}, prefix={raw[:100]!r}")
            self.assertIsInstance(value, dict)
            self.assertEqual(returned_headers.get("cache-control"), "no-store")
            return status, value, returned_headers
        finally:
            conn.close()

    @staticmethod
    def _patch_body(revision, title):
        return {"title": title, "revision": revision}

    def _sample_card(self):
        return next(item for item in self.bridge.getState()["tasks"]
                    if item["projectId"] == "p-sample")

    def test_duplicate_sensitive_and_content_headers_fail_closed(self):
        key = self._issue()["key"]
        cases = [
            ("/cards", "GET", [("X-Madar-Integration-Key", key)]),
            ("/cards", "GET", [("x-madar-integration-key", "other")]),
            ("/cards", "GET", [("Content-Length", "0"), ("content-length", "0")]),
            ("/cards", "GET", [("Content-Type", "application/json"),
                              ("content-type", "application/json")]),
        ]
        for path, method, extra in cases:
            with self.subTest(extra=extra):
                status, payload, _ = self._request(method, PREFIX + path, key=key,
                                                    headers=extra)
                self.assertEqual(status, 400)
                self.assertIn("error", payload)
        state = self._request("GET", PREFIX + "/cards", key=key)[1]
        card = state["cards"][0]
        body = self._patch_body(state["revision"], "must-not-mutate")
        write_key = self._issue(permissions=("read", "write"))["key"]
        status, _, _ = self._request(
            "PATCH", PREFIX + "/cards/" + card["id"], key=write_key,
            body=body, headers=[("Content-Type", "application/json"),
                                ("Idempotency-Key", "duplicate"),
                                ("idempotency-key", "duplicate")])
        self.assertEqual(status, 400)
        self.assertNotEqual(self._sample_card()["title"], "must-not-mutate")

    def test_plaintext_server_does_not_mount_integration_route(self):
        plain_bridge = self._bridge("http-host")
        plain = LanService(plain_bridge, self.root / "http-host" / "users.json",
                           bind="127.0.0.1", port=0)
        plain.setup_owner("plain-owner", SECRET)
        plain.start()
        self.addCleanup(plain.stop)
        conn = HTTPConnection("127.0.0.1", plain.port, timeout=4)
        try:
            conn.request("GET", PREFIX + "/cards", headers={
                "X-Madar-Integration-Key": self._issue()["key"]})
            response = conn.getresponse()
            status = response.status
            body = json.loads(response.read())
        finally:
            conn.close()
        self.assertEqual(status, 404)
        self.assertIn("error", body)
        self.assertIsNone(plain.integration_router)

    def test_integration_key_cannot_authenticate_at_legacy_lan_endpoint(self):
        key = self._issue("admin", ("read", "write"))["key"]
        for path in ("/api/state", "/api/finance",
                     "/api/finance-status", "/api/finance-overview",
                     "/api/users"):
            with self.subTest(path=path):
                code, payload, _ = self._request("GET", path, headers=[
                    ("Authorization", "Bearer " + key)])
                self.assertEqual(code, 403)
                self.assertIn("error", payload)
        lan_token = self.service.authenticate("admin", SECRET)["token"]
        for bad_key in (None, "Bearer " + lan_token, lan_token, "invalid"):
            with self.subTest(bad_key=bool(bad_key)):
                code, _, _ = self._request("GET", PREFIX + "/cards", key=bad_key)
                self.assertEqual(code, 401)
        # The adapter deliberately publishes no key management over REST.
        self.assertEqual(self._request("POST", PREFIX + "/keys", key=key,
                                       body={"username": "admin"})[0], 405)
        self.assertEqual(self._request("GET", PREFIX + "/keys", key=key)[0], 404)

    def test_project_scope_and_cross_account_visibility_over_tls(self):
        editor = self._issue("editor")["key"]
        outsider = self._issue("outsider")["key"]
        zero = self._issue("zero")["key"]
        sample_id = self._sample_card()["id"]
        self.assertEqual([p["id"] for p in self._request(
            "GET", PREFIX + "/projects", key=editor)[1]["projects"]], ["p-sample"])
        self.assertEqual([p["id"] for p in self._request(
            "GET", PREFIX + "/projects", key=outsider)[1]["projects"]], ["p-personal"])
        self.assertEqual(self._request("GET", PREFIX + "/projects", key=zero)[1]["projects"], [])
        self.assertEqual(self._request("GET", PREFIX + "/cards", key=zero)[1]["cards"], [])
        self.assertEqual(self._request("GET", PREFIX + "/cards/" + sample_id, key=editor)[0], 200)
        self.assertEqual(self._request("GET", PREFIX + "/cards/" + sample_id, key=outsider)[0], 404)
        self.assertEqual(self._request("GET", PREFIX + "/cards/" + sample_id, key=zero)[0], 404)
        self.assertEqual(self._request("GET", PREFIX + "/cards?projectId=p-sample",
                                       key=outsider)[1]["cards"], [])
        self.assertEqual(self._request("GET", PREFIX + "/cards/does-not-exist",
                                       key=editor)[0], 404)

    def test_no_finance_projection_or_other_private_fields_even_for_admin(self):
        state = self.bridge.getState()
        state["projects"][0]["price"] = 907001234
        state["tasks"][0]["cost"] = 809001234
        if state["tasks"][0].get("checklist"):
            state["tasks"][0]["checklist"][0]["cost"] = 909008765
        self.bridge.saveState(state)
        for username in ("admin", "editor", "viewer"):
            key = self._issue(username)["key"]
            _, projects, _ = self._request("GET", PREFIX + "/projects", key=key)
            _, cards, _ = self._request("GET", PREFIX + "/cards", key=key)
            for project in projects["projects"]:
                self.assertLessEqual(set(project), PROJECT_FIELDS)
            for card in cards["cards"]:
                self.assertLessEqual(set(card), CARD_FIELDS)
            document = json.dumps([projects, cards])
            for secret in ("907001234", "809001234", "909008765",
                           "passwordHash", '"price"', '"cost"', '"finance"',
                           '"checklist"', '"fileLinks"'):
                self.assertNotIn(secret, document)
            for endpoint in ("/finance", "/finance-status", "/finance-overview",
                             "/invoices", "/users", "/attachments"):
                self.assertEqual(self._request("GET", PREFIX + endpoint,
                                               key=key)[0], 404)

    def test_patch_replay_conflict_and_live_role_scope_revocation(self):
        key = self._issue("editor", ("read", "write"))["key"]
        listing = self._request("GET", PREFIX + "/cards", key=key)[1]
        card = listing["cards"][0]
        path = PREFIX + "/cards/" + card["id"]
        body = self._patch_body(listing["revision"], "https-audited-title")
        header = [("Content-Type", "application/json"),
                  ("Idempotency-Key", "http-audit-1")]
        first_code, first, _ = self._request("PATCH", path, key=key,
                                            headers=header, body=body)
        self.assertEqual(first_code, 200)
        replay_code, replay, _ = self._request("PATCH", path, key=key,
                                              headers=header, body=body)
        self.assertEqual((replay_code, replay), (200, first))
        changed = self._patch_body(listing["revision"], "different-payload")
        self.assertEqual(self._request("PATCH", path, key=key,
                                       headers=header, body=changed)[0], 409)
        self.assertEqual(self._request("PATCH", path, key=key,
                                       headers=[("Content-Type", "application/json"),
                                                ("Idempotency-Key", "different-key")],
                                       body=changed)[0], 409)
        self.service.upsert_user(self.admin_token, {"username": "editor",
                                                     "role": "viewer",
                                                     "projects": ["p-sample"],
                                                     "password": ""})
        self.assertEqual(self._request("PATCH", path, key=key,
                                       headers=header, body=body)[0], 403)
        self.assertEqual(self._request("GET", path, key=key)[0], 200)
        self.service.upsert_user(self.admin_token, {"username": "editor",
                                                     "role": "editor",
                                                     "projects": ["p-personal"],
                                                     "password": ""})
        self.assertEqual(self._request("GET", path, key=key)[0], 404)
        self.assertEqual(self._request("PATCH", path, key=key,
                                       headers=header, body=body)[0], 404)
        self.assertEqual(self._sample_card()["title"], "https-audited-title")

    def test_viewer_cannot_patch_and_reset_or_deletion_revokes_key_over_tls(self):
        viewer = self._issue("viewer", ("read", "write"))["key"]
        listing = self._request("GET", PREFIX + "/cards", key=viewer)[1]
        card = listing["cards"][0]
        uri = PREFIX + "/cards/" + card["id"]
        body = self._patch_body(listing["revision"], "forbidden-viewer-update")
        headers = [("Content-Type", "application/json"),
                   ("Idempotency-Key", "viewer-update-1")]
        self.assertEqual(self._request("PATCH", uri, key=viewer,
                                       body=body, headers=headers)[0], 403)
        self.assertNotEqual(self._sample_card()["title"], "forbidden-viewer-update")
        editor = self._issue("editor")["key"]
        self.assertEqual(self._request("GET", PREFIX + "/cards", key=editor)[0], 200)
        self.service.reset_password(self.admin_token, "editor", "reset-local-password-567")
        self.assertEqual(self._request("GET", PREFIX + "/cards", key=editor)[0], 401)
        new_editor = self._issue("editor")["key"]
        self.assertEqual(self._request("GET", PREFIX + "/cards", key=new_editor)[0], 200)
        self.assertTrue(self.service.delete_user(self.admin_token, "editor"))
        self.assertEqual(self._request("GET", PREFIX + "/cards", key=new_editor)[0], 401)

    def test_simultaneous_https_patch_has_one_revision_winner(self):
        key1 = self._issue("editor", ("read", "write"))["key"]
        key2 = self._issue("admin", ("read", "write"))["key"]
        revision_view = self._request("GET", PREFIX + "/cards", key=key1)[1]
        path = PREFIX + "/cards/" + revision_view["cards"][0]["id"]
        def write(args):
            key, title, req_id = args
            return self._request(
                "PATCH", path, key=key,
                headers=[("Content-Type", "application/json"),
                         ("Idempotency-Key", req_id)],
                body=self._patch_body(revision_view["revision"], title))[0]
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(write, [
                (key1, "concurrent-editor", "parallel-editor"),
                (key2, "concurrent-admin", "parallel-admin")]))
        self.assertEqual(sorted(results), [200, 409])
        self.assertIn(self._sample_card()["title"],
                      ("concurrent-editor", "concurrent-admin"))

    def test_malformed_body_headers_and_url_have_controlled_failures(self):
        key = self._issue("editor", ("read", "write"))["key"]
        state = self._request("GET", PREFIX + "/cards", key=key)[1]
        path = PREFIX + "/cards/" + state["cards"][0]["id"]
        clean = self._sample_card()["title"]
        header = [("Content-Type", "application/json"),
                  ("Idempotency-Key", "malformed-test")]
        samples = [
            ("PATCH", path, header, b"{broken", None, 400),
            ("PATCH", path, header, b"[]", None, 400),
            ("PATCH", path, header, b'{"title":NaN}', None, 400),
            ("PATCH", path, header, b'{"title":"one","title":"two"}', None, 400),
            ("PATCH", path, header, {"title":"new","revision":state["revision"],
                                     "role":"admin"}, None, 400),
            ("PATCH", path, header, {"title":"x\nother","revision":state["revision"]},
             None, 400),
            ("PATCH", path, header, {"title":"new","revision":"abc"}, None, 400),
            ("PATCH", path, header, b"Z" * 8193, None, 413),
            ("PATCH", path, header, b"", "invalid", 400),
            ("PATCH", path, header, b"", "-1", 413),
            ("PATCH", path, header, b"", "8193", 413),
            ("PATCH", path, [("Content-Type","text/plain"),
                             ("Idempotency-Key","malformed")], b"{}", None, 415),
            ("GET", PREFIX + "/cards?limit=1&limit=2", [], b"", None, 400),
            ("GET", PREFIX + "/cards%2fhidden", [], b"", None, 400),
            ("GET", PREFIX + "/cards", [], b"abc", None, 400),
            ("POST", PREFIX + "/cards", [], b"{}", None, 405),
        ]
        for method, endpoint, headers, body, declared, expected in samples:
            with self.subTest(method=method, endpoint=endpoint, expected=expected):
                code, result, _ = self._request(
                    method, endpoint, key=key, headers=headers,
                    body=body, content_length=declared)
                self.assertEqual(code, expected)
                self.assertIn("error", result)
                self.assertNotIn("traceback", str(result).lower())
        self.assertEqual(self._sample_card()["title"], clean)

    def test_transfer_encoding_must_not_bypass_body_framing(self):
        """Security regression: the mount must reject unsupported chunked bodies.

        HTTP/1.0's short-lived connection is NOT a substitute for strict framing
        if reverse proxies may later front this API.
        """
        key = self._issue()["key"]
        status, result, _ = self._request(
            "GET", PREFIX + "/cards", key=key,
            headers=[("Transfer-Encoding", "chunked")],
            body=b"0\r\n\r\n", content_length="omit")
        self.assertEqual(status, 400, msg=f"chunked GET unexpectedly accepted: {result!r}")

    def test_wrong_tls_certificate_pin_never_transmits_integration_key(self):
        key = self._issue()["key"]
        before = len(self.service.sessions)
        with self.assertRaises(ssl.SSLCertVerificationError):
            pinned_https_json(
                f"https://127.0.0.1:{self.port}{PREFIX}/cards",
                "0" * 64, headers={"X-Madar-Integration-Key": key},
                timeout=4)
        self.assertEqual(len(self.service.sessions), before)
        self.assertEqual(self._request("GET", PREFIX + "/cards", key=key)[0], 200)


if __name__ == "__main__":
    unittest.main()
