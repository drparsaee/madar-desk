"""Real localhost HTTPS dispatch for the opt-in API, with disposable data."""
import json
import hashlib
from http.client import HTTPSConnection
from io import BytesIO
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import native_app
from lan import LanService, certificate_fingerprint, pinned_https_json

try:
    from test_lan_tls import _CERT, _KEY
except ModuleNotFoundError:
    from tests.test_lan_tls import _CERT, _KEY


class IntegrationHttpAcceptance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="madar-int-http-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        with patch.object(native_app, "datadir", return_value=root):
            self.bridge = native_app.Bridge()
        cert, key = root / "server.crt", root / "server.key"
        cert.write_text(_CERT, encoding="ascii")
        key.write_text(_KEY, encoding="ascii")
        self.service = LanService(self.bridge, root / "lan-users.json",
                                  bind="127.0.0.1", port=0, certfile=cert,
                                  keyfile=key)
        self.service.setup_owner("owner", "very-secret-test-password")
        self.service.start()
        self.addCleanup(self.service.stop)
        self.bridge.lan = self.service
        self.bridge.connection = {"mode": "server"}
        self.url = f"https://127.0.0.1:{self.service.port}"
        self.pin = certificate_fingerprint(cert)

    def call(self, method, path, key, *, body=None, extra=None):
        headers = {"X-Madar-Integration-Key": key, **(extra or {})}
        if body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(body).encode("utf8")
        if method == "PATCH":
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            connection = HTTPSConnection("127.0.0.1", self.service.port,
                                         context=context, timeout=5)
            try:
                connection.connect()
                fingerprint = hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()
                self.assertEqual(fingerprint, self.pin)
                connection.request(method, "/integrations/v1" + path, body=body,
                                   headers=headers)
                result = connection.getresponse()
                raw = result.read()
                if result.status >= 400:
                    raise HTTPError(self.url + path, result.status, result.reason,
                                    result.headers, BytesIO(raw))
                return json.loads(raw.decode("utf8"))
            finally:
                connection.close()
        return pinned_https_json(self.url + "/integrations/v1" + path,
                                 self.pin, method=method, headers=headers, data=body,
                                 timeout=5)

    def test_https_get_requires_key_and_hides_finance(self):
        generated = self.bridge.integrationIssueKey("owner", ["read"])
        self.assertEqual(len(generated["keyId"]), 27)
        response = self.call("GET", "/cards", generated["key"])
        self.assertIn("cards", response)
        for card in response["cards"]:
            self.assertNotIn("cost", card)
            self.assertNotIn("checklist", card)
        with self.assertRaises(HTTPError) as error:
            self.call("GET", "/cards", "bad-key")
        self.assertEqual(error.exception.code, 401)
        self.assertEqual(self.bridge.integrationRevokeKey(generated["keyId"]), {"revoked": True})
        with self.assertRaises(HTTPError) as error:
            self.call("GET", "/cards", generated["key"])
        self.assertEqual(error.exception.code, 401)

    def test_http_patch_is_revision_guarded_and_idempotent(self):
        generated = self.bridge.integrationIssueKey("owner", ["read", "write"])
        response = self.call("GET", "/cards", generated["key"])
        card = response["cards"][0]
        body = {"title": "Renamed through HTTPS API", "revision": response["revision"]}
        path = "/cards/" + card["id"]
        updated = self.call("PATCH", path, generated["key"], body=body,
                            extra={"Idempotency-Key": "integration-accept-1"})
        self.assertEqual(updated["card"]["title"], body["title"])
        replay = self.call("PATCH", path, generated["key"], body=body,
                           extra={"Idempotency-Key": "integration-accept-1"})
        self.assertEqual(updated, replay)
        with self.assertRaises(HTTPError) as error:
            self.call("PATCH", path, generated["key"], body={**body,"title":"Different"},
                      extra={"Idempotency-Key":"integration-accept-1"})
        self.assertEqual(error.exception.code, 409)


if __name__ == "__main__":
    unittest.main()
