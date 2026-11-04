"""Security characterization of the LAN HTTP origin and body framing.

Only uses a disposable loopback host and synthetic identities.
"""

import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from lan import LanService


class _Bridge:
    def __init__(self):
        self._lock = threading.RLock()

    def getState(self):
        return {"projects": [], "tasks": []}


class LanOriginAndFramingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-lan-frame-")
        self.addCleanup(temporary.cleanup)
        self.service = LanService(_Bridge(), Path(temporary.name) / "users.json",
                                  bind="127.0.0.1", port=0)
        self.service.setup_owner("test-owner", "test-only-secret-123")
        self.port = self.service.start()
        self.addCleanup(self.service.stop)

    def request(self, method, target, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
        try:
            conn.request(method, target, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_post_rejects_signed_content_length_before_login(self):
        payload = json.dumps({"username": "test-owner", "password": "test-only-secret-123"}).encode()
        # The malformed Content-Length must be refused before reading a body
        # or reaching authentication. Sending bytes after a header that is
        # already rejected can trigger a Windows TCP reset on the unread data
        # (WinError 10053), masking the actual 400 framing response. Keep this
        # a header-only framing probe, like the PATCH case below.
        status, result = self.request("POST", "/api/login",
                                      headers={"Content-Type": "application/json",
                                               "Content-Length": "+" + str(len(payload))})
        self.assertEqual(status, 400)
        self.assertEqual(result, {"error": "طول درخواست نامعتبر است."})
        self.assertEqual(self.service.sessions, {})

    def test_http11_missing_host_rejected_before_login(self):
        payload = json.dumps({"username": "test-owner", "password": "test-only-secret-123"}).encode()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
        try:
            conn.putrequest("POST", "/api/login", skip_host=True)
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(len(payload)))
            # Missing HTTP/1.1 Host is rejected before body consumption. Do
            # not send unread login bytes after the invalid header: Windows
            # can reset the connection while the 400 response is in flight.
            conn.endheaders()
            response = conn.getresponse()
            status = response.status
            result = json.loads(response.read())
        finally:
            conn.close()
        self.assertEqual(status, 400)
        self.assertEqual(result, {"error": "هدر Host الزامی است."})
        self.assertEqual(self.service.sessions, {})

    def test_patch_rejects_signed_content_length_before_routing(self):
        # The framing violation is the signed header itself. Supplying actual
        # body bytes here can make Windows abort the TCP connection when the
        # server rightly rejects the header *before* reading that body.
        # Header-only keeps the security assertion without an unread-body RST.
        status, result = self.request("PATCH", "/api/me",
                                      headers={"Content-Type": "application/json",
                                               "Content-Length": "+2"})
        self.assertEqual(status, 400)
        self.assertEqual(result, {"error": "طول درخواست نامعتبر است."})
        self.assertEqual(self.service.sessions, {})

    def test_absolute_form_http_target_rejected_before_authorization(self):
        status, result = self.request("POST", "/api/login",
                                      json.dumps({"username": "test-owner",
                                                  "password": "test-only-secret-123"}),
                                      {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        token = result["token"]
        status, _ = self.request("GET", "http://untrusted.invalid/api/state",
                                 headers={"Authorization": "Bearer " + token})
        self.assertEqual(status, 400)

    def test_network_path_form_is_not_rewritten_into_local_endpoint(self):
        status, result = self.request("POST", "/api/login",
                                      json.dumps({"username": "test-owner",
                                                  "password": "test-only-secret-123"}),
                                      {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        status, _ = self.request("GET", "//api/state",
                                 headers={"Authorization": "Bearer " + result["token"]})
        self.assertEqual(status, 400)

    def test_normal_json_post_and_relative_get_are_compatible(self):
        status, result = self.request("POST", "/api/login",
                                      json.dumps({"username": "test-owner",
                                                  "password": "test-only-secret-123"}),
                                      {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        status, result = self.request("GET", "/api/state",
                                      headers={"Authorization": "Bearer " + result["token"]})
        self.assertEqual(status, 200)
        self.assertEqual(result["state"], {"projects": [], "tasks": []})


if __name__ == "__main__":
    unittest.main()
