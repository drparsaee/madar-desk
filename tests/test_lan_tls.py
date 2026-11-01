"""Real TLS loopback tests. Embedded test-only key is NEVER a production key."""
import json
from pathlib import Path
import ssl
import tempfile
import threading
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

from lan import LanService, certificate_fingerprint, pinned_https_json


# Disposable, public test fixture for 127.0.0.1. Generate unique certificates
# separately for deployments; this private key is intentionally not secret.
_CERT = """-----BEGIN CERTIFICATE-----
MIIDKjCCAhKgAwIBAgIUCdq96+5BppdxoDQ4K+iWh8JiVH8wDQYJKoZIhvcNAQEL
BQAwGzEZMBcGA1UEAwwQbWFkYXItdGVzdC5sb2NhbDAgFw0yNjEwMjAxNzQ1MjFa
GA8yMTI2MDkyNjE3NDUyMVowGzEZMBcGA1UEAwwQbWFkYXItdGVzdC5sb2NhbDCC
ASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAJkEfrxBrHHKz4iKvOuzVbTj
sGn+ISRrBxlMmYToDGcZIGdDKbaKXnMhhJmDMDhder4Hm8SH1II9MMOf/a0Avgdo
bY+arE1dDNUl2M5i2taMb7dwB97HPpy4KTUD4gWYAXciCq6ece9f9NLcf/pwI3S5
Fz/nTbbdmrc4vTSzLytpPBGznoLCqvith4YfG4kLXcZt9iuzT6rgFmsqxmd8xDq/
Le4g866tm9dhlGpST8H9+1FS2P3PTkBM4shl74Q7Dz3KS6XrNKrWYAARISdfZUaf
040IhxJPQLyCcwvQA2Imn7SSaETR+UAl3QxoWLQkIBafTFx6GzQNLXERfBJkNPEC
AwEAAaNkMGIwHQYDVR0OBBYEFJERogq+U7C/lVqm9KOcQOdmhNcUMB8GA1UdIwQY
MBaAFJERogq+U7C/lVqm9KOcQOdmhNcUMA8GA1UdEwEB/wQFMAMBAf8wDwYDVR0R
BAgwBocEfwAAATANBgkqhkiG9w0BAQsFAAOCAQEAZkOkfZnWiOfQTs42XNr/MKU8
mJsUNMm5/Fry39bY9B6HmMSF6VJxaeTeVx1OCoeibk5OLNxLxpkDPgwDp5D0MYJt
brnNzlfUcOe4lcWKyIR7RXGRMpMKWXnv5OSxeyZg4tKyMYzMRjaRy3n+n0g3xJID
b2GfF36szj6RbUlLqbSoWdBVO2LGGNUFVQuLkAdML8mHvdJscFTEvEa1ccGgsW3q
lgCAXjRX3y5rC8/nhr9DPC3ZtHeuI7mNLjDh4/CiWzA3Xv4PJKy3EZtPV4tYqL2T
0viZEzGpWgguuCluF1WikXKaiBhwp2wtVjJ6xHDoEucKlwklEO3LFWQDTb4Nfw==
-----END CERTIFICATE-----
"""
_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCZBH68Qaxxys+I
irzrs1W047Bp/iEkawcZTJmE6AxnGSBnQym2il5zIYSZgzA4XXq+B5vEh9SCPTDD
n/2tAL4HaG2PmqxNXQzVJdjOYtrWjG+3cAfexz6cuCk1A+IFmAF3IgqunnHvX/TS
3H/6cCN0uRc/50223Zq3OL00sy8raTwRs56Cwqr4rYeGHxuJC13GbfYrs0+q4BZr
KsZnfMQ6vy3uIPOurZvXYZRqUk/B/ftRUtj9z05ATOLIZe+EOw89ykul6zSq1mAA
ESEnX2VGn9ONCIcST0C8gnML0ANiJp+0kmhE0flAJd0MaFi0JCAWn0xcehs0DS1x
EXwSZDTxAgMBAAECggEADvtkcEjK2lpl7wPMgxRsRhmMBpi6BH+RMp4wItX4juik
JlAqZ6PNIx8rRT+Vy1MFx1Dl5Lx652SX33ONCjEaKg4EuiyGBc4gSUdbHrwJmrul
3ZNTxfGCtSQH7teqO+t560DzRE0hsTMXPMUXp7zuj8lmmBxs3MR+V0WwKtaHfgu5
FNTabdJb3HjuP0ahP0pYGgA+uaLpPkgGneLKy2l9R+cK8i0zf3r5i6wycHlgXZ8n
VxboiLRuXwHo2Y5YP9dUzxEN1vp0dMdcz2Jb7NWTfuULl+OM7u/5dCg40iuLZdn+
sr30ZvS4loKwFXu0hGcUFpjL6W4jdvw35n4Q0s3/8QKBgQDV5zJG31QDT4FW0tHj
EaLRJGDht6UpeVwU4+nQRaD5Eg2SXcp0JbVphzRz5qd9KtAXMgF1jzGfAmdRrFSI
mVbLizF2azqh98Or9k2zoKerbRzAZnIQC9+N3YglNk6LkHzxVIqSak9zcbQdJclB
fHVtRPHz2k6JtMrYJrLiVF1iyQKBgQC3IcfbfICrox3mG3vgpkMaB3Y5xTo1bQTn
F0900ALsaAFQq8pHNxW8+XGNrohPMcs4iqrCcuqFOWW1CXgH/RIjbRq3fF22aB3S
FGOJU2RXTHq/QMDmp0n947A6kZlNjcPKc8C8VXurOq4WgeIvYUUOLEZOGL5875uV
iz25VbTs6QKBgCcJ+BIZRmMISqnG9kmD+XxEMG5hrwIfxR+G7TB21MdAdTumZIHI
NBDbfUY97YmZm7rwBHYpOTw1Gxg75H29xqqFb/SV43CWIJ8s58eF5bQSyPGQgPbO
w/FHYkawX6t3JmaBMH1Ca9e9A8tiDxYlmeTkdWg1Cqp1VaQXhARss1KJAoGBAJic
vyfLBpOCeM0lREO/apYLd9vG365cLsTCKUYIfxcxyT7IGubkIep82cOfmhqdPWTe
MlWfXI8vePG4dV366R26s5QLQTFcbNWAhj6Pz0PtCTHOrbLJ4KCDGX6FjYMSzAIw
GoMYndnhKei5zpt7bQfVn7U/a6dEKp0iD4sewIrZAoGAezCivpw7p2PVdYLQB9Ev
pnsD9NadzXtggug9+o6ql3mpJDhixpFYfQFYIkoGUfpIdNBFZ+KqU8bKN5mcyXaV
LmexLsf8VQg/obcZduon/N3mCs5WWgqEV2Uxzjkp0byGN7AL/SXMWVugRb1E16k4
cezCiwEg0pi2EekRAwWY/QM=
-----END PRIVATE KEY-----
"""


class _Bridge:
    def __init__(self):
        self._lock = threading.RLock()

    def getState(self):
        return {"projects": [], "tasks": []}


class LanTLSIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="madar-tls-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cert = self.root / "test.crt"
        self.key = self.root / "test.key"
        self.cert.write_text(_CERT, encoding="ascii")
        self.key.write_text(_KEY, encoding="ascii")
        self.service = LanService(_Bridge(), self.root / "users.json",
                                  bind="127.0.0.1", port=0,
                                  certfile=self.cert, keyfile=self.key)
        self.service.setup_owner("owner", "a-very-long-local-password")
        self.port = self.service.start()
        self.addCleanup(self.service.stop)
        self.url = f"https://127.0.0.1:{self.port}"
        self.fingerprint = certificate_fingerprint(self.cert)

    def test_full_tls_login_and_authenticated_read(self):
        token = pinned_https_json(self.url + "/api/login", self.fingerprint,
                                  method="POST", data={"username": "owner",
                                                        "password": "a-very-long-local-password"})["token"]
        state = pinned_https_json(self.url + "/api/state", self.fingerprint,
                                  headers={"Authorization": "Bearer " + token})
        self.assertEqual(state["state"], {"projects": [], "tasks": []})
        # OpenSSL-style fingerprint separators are also accepted.
        colon_pin = ":".join(self.fingerprint[i:i+2] for i in range(0, 64, 2))
        self.assertEqual(pinned_https_json(self.url + "/api/state", colon_pin,
                         headers={"Authorization": "Bearer " + token})["state"], state["state"])

    def test_wrong_pin_never_sends_login(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            pinned_https_json(self.url + "/api/login", "0" * 64, method="POST",
                              data={"username": "owner", "password": "a-very-long-local-password"})
        self.assertEqual(self.service.sessions, {})
        self.assertEqual(self.service.failed, {})

    def test_invalid_pin_and_plaintext_url_fail_closed(self):
        for bad_pin in ("", "abc", "sha256:" + self.fingerprint, None):
            with self.subTest(pin=bad_pin), self.assertRaises(ValueError):
                pinned_https_json(self.url + "/api/state", bad_pin)
        with self.assertRaises(ValueError):
            pinned_https_json(self.url.replace("https:", "http:") + "/api/state",
                              self.fingerprint)
        with self.assertRaises(ValueError):
            pinned_https_json("https://example.org:443/api/state", self.fingerprint)
        self.assertEqual(self.service.sessions, {})

    def test_authenticated_http_errors_remain_http_errors(self):
        with self.assertRaises(HTTPError) as error:
            pinned_https_json(self.url + "/api/state", self.fingerprint)
        self.assertEqual(error.exception.code, 403)

    def test_incomplete_tls_configuration_cannot_start(self):
        server = LanService(_Bridge(), self.root / "users2.json",
                            bind="127.0.0.1", port=0, certfile=self.cert)
        server.setup_owner("owner", "a-very-long-local-password")
        with self.assertRaisesRegex(ValueError, "both certificate"):
            server.start()
        self.assertIsNone(server.server)


class DomainCommitTests(unittest.TestCase):
    def test_sql_commit_used_when_bridge_supports_it(self):
        bridge = _Bridge()
        bridge._commit_domain = Mock()
        service = LanService(bridge, Path("unused"))
        state = {"version": 3}
        service._commit_domain("collab", state)
        service._commit_domain("finance", state)
        self.assertEqual(bridge._commit_domain.call_count, 2)
        self.assertEqual(bridge._commit_domain.call_args_list[0].args, ("collab", state))
        self.assertEqual(bridge._commit_domain.call_args_list[1].args, ("finance", state))

    def test_failed_sql_commit_does_not_silently_fall_back_to_json(self):
        bridge = _Bridge()
        bridge._commit_domain = Mock(side_effect=RuntimeError("transaction failed"))
        service = LanService(bridge, Path("unused"))
        with self.assertRaisesRegex(RuntimeError, "transaction failed"):
            service._commit_domain("finance", {})

    def test_legacy_bridge_keeps_atomic_json_persistence(self):
        with tempfile.TemporaryDirectory(prefix="madar-domain-") as directory:
            bridge = _Bridge()
            bridge.collab_path = Path(directory) / "collab.json"
            bridge.finance_path = Path(directory) / "finance.json"
            service = LanService(bridge, Path(directory) / "users.json")
            service._commit_domain("collab", {"comments": []})
            service._commit_domain("finance", {"invoices": []})
            self.assertEqual(json.loads(bridge.collab_path.read_text("utf8")),
                             {"comments": []})
            self.assertEqual(json.loads(bridge.finance_path.read_text("utf8")),
                             {"invoices": []})
            with self.assertRaises(ValueError):
                service._commit_domain("unknown", {})


class PlaintextBindingPolicyTests(unittest.TestCase):
    def test_non_loopback_plaintext_is_rejected_before_socket_open(self):
        with tempfile.TemporaryDirectory(prefix="madar-lan-bind-") as directory:
            for bind in ("0.0.0.0", "192.168.1.10", "::", "localhost"):
                with self.subTest(bind=bind):
                    service = LanService(_Bridge(), Path(directory) / ("users-" + str(len(bind)) + bind.encode('utf8').hex() + ".json"),
                                         bind=bind, port=0)
                    service.setup_owner("owner", "temporary-password-123")
                    with self.assertRaisesRegex(ValueError, "TLS is required"):
                        service.start()
                    self.assertIsNone(service.server)
                    self.assertIsNone(service.thread)

    def test_loopback_plaintext_is_still_available_for_isolated_local_tools(self):
        with tempfile.TemporaryDirectory(prefix="madar-loopback-") as directory:
            service = LanService(_Bridge(), Path(directory) / "users.json",
                                 bind="127.0.0.1", port=0)
            service.setup_owner("owner", "temporary-password-123")
            try:
                self.assertGreater(service.start(), 0)
                self.assertIsNotNone(service.server)
            finally:
                service.stop()


if __name__ == "__main__":
    unittest.main()
