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
        body = json.dumps({"username": "synthetic-owner",
                           "password": "x" * 70000}).encode()
        try:
            with patch("lan.verify_password", return_value=False) as verify:
                conn.request("POST", "/api/login", body=body,
                             headers={"Content-Type": "application/json"})
                response = conn.getresponse()
                status = response.status
                json.loads(response.read())
                verify.assert_not_called()
        finally:
            conn.close()
        self.assertEqual(status, 413)
        self.assertFalse(self.service.sessions)

    def test_unauthenticated_nonlogin_post_is_rejected_before_json_parse(self):
        port = self.service.start()
        self.addCleanup(self.service.stop)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        # The body is deliberately malformed and larger than the login budget.
        # Authorization must fail before a non-login endpoint parses it.
        body = b"{" + b"x" * 70000
        try:
            conn.request("POST", "/api/state", body=body,
                         headers={"Content-Type": "application/json",
                                  "Authorization": "Bearer invalid-synthetic-token"})
            response = conn.getresponse()
            status = response.status
            response.read()
        finally:
            conn.close()
        self.assertEqual(status, 403)
        self.assertFalse(self.service.sessions)

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
