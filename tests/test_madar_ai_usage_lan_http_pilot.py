"""Actual loopback HTTPS API for E1 AI budgets, NO model/provider dispatch."""
import hashlib
from http.client import HTTPSConnection
import json
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import native_app
from lan import LanService, certificate_fingerprint, pinned_https_json
from madar_ai_usage_store import AiUsageStore
from tests.test_lan_tls import _CERT, _KEY


PASSWORD = "synthetic-ai-budget-strong-password"
HOST_KEY = b"synthetic-test-only-opaque-HMAC-key-1234567890"
DIGEST = "b" * 64
REQUEST = "a" * 32


class AiBudgetMountedTlsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="ai-budget-https-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        with patch.object(native_app, "datadir", return_value=self.root):
            bridge = native_app.Bridge()
            bridge.saveState(native_app.initial_state())
        cert, key = self.root / "test.crt", self.root / "test.key"
        cert.write_text(_CERT, encoding="ascii")
        key.write_text(_KEY, encoding="ascii")
        service = LanService(bridge, self.root / "users.json",
                             bind="127.0.0.1", port=0,
                             certfile=cert, keyfile=key)
        service.setup_owner("owner", PASSWORD)
        port = service.start()
        self.addCleanup(service.stop)
        self.service = service
        self.url = f"https://127.0.0.1:{port}/api/ai-usage/v1/command"
        self.pin = certificate_fingerprint(cert)
        self.owner = service.authenticate("owner", PASSWORD)["token"]
        for name, role, projects in (("editor", "editor", ["p-sample"]),
                                     ("outsider", "editor", ["p-personal"]),
                                     ("viewer", "viewer", ["p-sample"])):
            service.upsert_user(self.owner, {"username": name, "password": PASSWORD,
                                             "role": role, "projects": projects})
        # Tests must explicitly emulate the future host operator's AI-off
        # policy; installed user-admin controls do not yet manage this flag.
        service.users["editor"]["aiEnabled"] = True
        service.users["outsider"]["aiEnabled"] = True
        self.tokens = {name: service.authenticate(name, PASSWORD)["token"]
                       for name in ("editor", "outsider", "viewer")}
        self.store = AiUsageStore(self.root / "usage.sqlite")

    def mount(self):
        self.service.mount_ai_usage_pilot(self.store, org_id="synthetic-office",
                                           identity_key=HOST_KEY)

    @staticmethod
    def cmd(action, data, *, manual=True, project="p-sample"):
        packet = {"schemaVersion": 1, "action": action,
                  "projectId": project, "data": data}
        if action in ("grant_set", "cloud_consent", "consent_revoke", "reserve"):
            packet["manualAction"] = manual
        return packet

    def send(self, packet, *, token=None):
        return pinned_https_json(self.url, self.pin, method="POST", data=packet,
                                 headers={"Authorization": "Bearer " + (token or self.owner)})

    def fail(self, status, packet, *, token=None):
        with self.assertRaises(HTTPError) as raised:
            self.send(packet, token=token)
        self.assertEqual(raised.exception.code, status)
        return json.loads(raised.exception.read())

    def grant(self, *, provider="local_ollama", cloud=False):
        return self.cmd("grant_set", {
            "userId": "editor", "provider": provider, "enabled": True,
            "cloudEnabled": cloud, "monthlyRequests": 1,
            "monthlyTokens": 100, "monthlyCostMicro": 200,
            "expectedVersion": 0, "eventId": "evt-grant-1",
        })

    def reserve(self, *, request=REQUEST, provider="local_ollama"):
        return self.cmd("reserve", {
            "requestId": request, "provider": provider,
            "payloadDigest": DIGEST, "estimatedTokens": 100,
            "maxCostMicro": 0, "eventId": "evt-reserve-1",
        })

    def test_default_off_and_double_mount_refused(self):
        self.fail(404, self.grant())
        self.mount()
        with self.assertRaises(RuntimeError):
            self.mount()

    def test_https_admin_grant_and_local_reservation_are_not_dispatch(self):
        self.mount()
        granted = self.send(self.grant())
        self.assertEqual(granted["result"]["version"], 1)
        self.assertFalse(granted["result"]["cloud_enabled"])
        created = self.send(self.reserve(), token=self.tokens["editor"])
        self.assertEqual(created["result"]["status"], "reserved")
        self.assertEqual(created["action"], "reserve")
        usage = self.send(self.cmd("usage_get", {"provider": "local_ollama"}),
                          token=self.tokens["editor"])
        self.assertEqual(usage["result"]["charged_requests"], 1)
        self.assertEqual(usage["result"]["charged_tokens"], 100)
        self.assertTrue(self.send(self.reserve(), token=self.tokens["editor"])["result"]["replayed"])
        # This route cannot dispatch to a provider: absent action 400.
        self.fail(400, self.cmd("dispatch", {"provider": "openai"}),
                  token=self.tokens["editor"])

    def test_cloud_denied_without_authorized_grant_and_explicit_consent(self):
        self.mount()
        self.send(self.grant(provider="openai", cloud=False))
        error = self.fail(400, self.cmd("cloud_consent", {
            "requestId": REQUEST, "provider": "openai",
            "payloadDigest": DIGEST, "eventId": "evt-consent-1",
        }), token=self.tokens["editor"])
        self.assertEqual(error["error"], "grant_denied")

    def test_roles_scope_revocation_and_forged_identity(self):
        self.mount()
        self.fail(403, self.grant(), token=self.tokens["viewer"])
        self.fail(403, self.grant(), token=self.tokens["editor"])
        self.fail(403, self.reserve(), token=self.tokens["outsider"])
        self.fail(403, self.reserve(), token="forged-token")
        self.fail(400, {**self.grant(), "orgId": "forged"})
        self.service.users["editor"]["aiEnabled"] = False
        result = self.fail(403, self.reserve(), token=self.tokens["editor"])
        self.assertEqual(result["error"], "ai_disabled")

    def test_bad_pin_and_raw_duplicate_command_not_accepted(self):
        self.mount()
        with self.assertRaises(ssl.SSLCertVerificationError):
            pinned_https_json(self.url, "0" * 64, method="POST", data=self.grant(),
                              headers={"Authorization": "Bearer " + self.owner})
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        conn = HTTPSConnection("127.0.0.1", self.service.port, timeout=4,
                               context=context)
        try:
            conn.connect()
            self.assertEqual(hashlib.sha256(conn.sock.getpeercert(
                binary_form=True)).hexdigest(), self.pin)
            body = b'{"schemaVersion":1,"action":"grant_get","action":"reserve","projectId":"p-sample","data":{}}'
            conn.request("POST", "/api/ai-usage/v1/command", body,
                         {"Authorization": "Bearer " + self.owner,
                          "Content-Type": "application/json"})
            reply = conn.getresponse()
            self.assertEqual(reply.status, 400)
            reply.read()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
