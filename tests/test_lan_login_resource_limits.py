"""Synthetic LAN login resource-budget regression, with no operational profiles."""

import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from lan import LanService, make_account


class _Bridge:
    def __init__(self):
        self._lock = threading.RLock()

    def getState(self):
        return {"projects": [], "tasks": []}


class LanLoginResourceLimits(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="madar-login-budget-")
        self.addCleanup(scratch.cleanup)
        self.service = LanService(_Bridge(), Path(scratch.name) / "users.json",
                                  bind="127.0.0.1", port=0)
        self.service.setup_owner("synthetic-owner", "synthetic-password-2026")

    def test_oversized_credentials_do_not_reach_expensive_password_verifier(self):
        with patch("lan.verify_password") as verify:
            with self.assertRaises(ValueError):
                self.service.authenticate("synthetic-owner", "x" * 5000, "192.0.2.20")
            with self.assertRaises(ValueError):
                self.service.authenticate("u" * 5000, "wrong", "192.0.2.20")
            verify.assert_not_called()
        self.assertFalse(self.service.failed)
        self.assertFalse(self.service.sessions)

    def test_new_accounts_cannot_store_passwords_that_login_will_reject(self):
        with self.assertRaises(ValueError):
            make_account("synthetic-user", "x" * 5000)
        self.assertIn("token", self.service.authenticate(
            "synthetic-owner", "synthetic-password-2026", "192.0.2.21"))

    def test_login_http_rejects_large_declared_body_before_read_or_kdf(self):
        port = self.service.start()
        self.addCleanup(self.service.stop)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            with patch("lan.verify_password", return_value=False) as verify:
                # Test the *declared* length limit without sending a body the
                # server must reject before it reads. Unread bytes can trigger
                # Winsock 10053 when the handler closes the socket.
                conn.putrequest("POST", "/api/login")
                conn.putheader("Content-Type", "application/json")
                conn.putheader("Content-Length", "70000")
                conn.endheaders()
                response = conn.getresponse()
                status = response.status
                result = json.loads(response.read())
                verify.assert_not_called()
        finally:
            conn.close()
        self.assertEqual(status, 413)
        self.assertIn("error", result)
        self.assertFalse(self.service.sessions)

    def test_unauthenticated_nonlogin_post_is_rejected_before_json_parse(self):
        port = self.service.start()
        self.addCleanup(self.service.stop)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        # Declare an oversized JSON request but do not transmit body bytes:
        # a 403 must arrive before the handler reads/parses any JSON.
        # The old 70 KB unread body intermittently caused Windows TCP aborts.
        # Sending no body also makes a regression in auth-before-read fail
        # (the client times out waiting), rather than silently succeeding.
        try:
            conn.putrequest("POST", "/api/state")
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", "70001")
            conn.putheader("Authorization", "Bearer invalid-synthetic-token")
            conn.endheaders()
            response = conn.getresponse()
            status = response.status
            result = json.loads(response.read())
        finally:
            conn.close()
        self.assertEqual(status, 403)
        self.assertEqual(result, {"error": "جلسه ورود معتبر نیست. دوباره وارد شوید."})
        self.assertFalse(self.service.sessions)

    def test_authenticated_malformed_json_is_rejected_after_bounded_read(self):
        token = self.service.authenticate(
            "synthetic-owner", "synthetic-password-2026")["token"]
        port = self.service.start()
        self.addCleanup(self.service.stop)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            # The complete one-byte body is read; no residual request bytes
            # can race the 400 JSON response on Windows.
            conn.request("POST", "/api/state", body=b"{",
                         headers={"Content-Type": "application/json",
                                  "Authorization": "Bearer " + token})
            response = conn.getresponse()
            status = response.status
            result = json.loads(response.read())
        finally:
            conn.close()
        self.assertEqual(status, 400)
        self.assertIn("error", result)

    def test_authenticated_post_still_decodes_json_and_applies_profile(self):
        token = self.service.authenticate("synthetic-owner", "synthetic-password-2026")["token"]
        port = self.service.start()
        self.addCleanup(self.service.stop)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("POST", "/api/profile",
                         body=json.dumps({"displayName": "Synthetic Owner"}).encode(),
                         headers={"Content-Type": "application/json",
                                  "Authorization": "Bearer " + token})
            response = conn.getresponse()
            status = response.status
            result = json.loads(response.read())
        finally:
            conn.close()
        self.assertEqual(status, 200)
        self.assertEqual(result["user"]["displayName"], "Synthetic Owner")


if __name__ == "__main__":
    unittest.main()
