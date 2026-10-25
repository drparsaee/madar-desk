"""Bridge-to-LAN encrypted transport integration using temporary test certificates."""

import socket
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_app
from lan import LanService, certificate_fingerprint
from tests.test_lan_tls import _CERT, _KEY


class NativeTlsBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-native-tls-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cert = self.root / "cert.pem"
        self.key = self.root / "key.pem"
        self.cert.write_text(_CERT, encoding="ascii")
        self.key.write_text(_KEY, encoding="ascii")
        mocked = patch.object(native_app, "datadir", return_value=self.root)
        mocked.start()
        self.addCleanup(mocked.stop)
        self.bridge = native_app.Bridge()
        self.pin = certificate_fingerprint(self.cert)

    def free_port(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    def test_tls_host_and_pinned_remote_bridge_round_trip(self):
        port = self.free_port()
        status = self.bridge.lanHost("owner", "long-owner-test-password", port,
                                     str(self.cert), str(self.key))
        self.addCleanup(self.bridge.lan.stop)
        self.assertEqual(status["transport"], "https")
        self.assertEqual(status["fingerprint"], self.pin)

        client_root = self.root / "client"
        client_root.mkdir()
        with patch.object(native_app, "datadir", return_value=client_root):
            client = native_app.Bridge()
            user = client._remote_login(f"https://127.0.0.1:{port}", "owner",
                                        "long-owner-test-password", fingerprint=self.pin)
            self.assertEqual(user["role"], "admin")
            self.assertEqual(client.lanStatus()["transport"], "https")
            state = client.getState()
            self.assertEqual(len(state["tasks"]), 4)
            self.assertTrue(client.remote_revision)

    def test_wrong_pin_and_missing_pin_refuse_credentials(self):
        port = self.free_port()
        self.bridge.lanHost("owner", "long-owner-test-password", port,
                            str(self.cert), str(self.key))
        self.addCleanup(self.bridge.lan.stop)
        existing_sessions = dict(self.bridge.lan.sessions)
        client_root = self.root / "wrong-client"
        client_root.mkdir()
        with patch.object(native_app, "datadir", return_value=client_root):
            client = native_app.Bridge()
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                client._remote_login(f"https://127.0.0.1:{port}", "owner",
                                     "long-owner-test-password")
            with self.assertRaises(ssl.SSLCertVerificationError):
                client._remote_login(f"https://127.0.0.1:{port}", "owner",
                                     "long-owner-test-password", fingerprint="0" * 64)
            self.assertEqual(client.connection["mode"], "solo")
            self.assertIsNone(client.remote_token)
        self.assertEqual(self.bridge.lan.sessions, existing_sessions)

    def test_server_reopens_tls_configuration_without_plaintext_downgrade(self):
        port = self.free_port()
        self.bridge.lanHost("owner", "long-owner-test-password", port,
                            str(self.cert), str(self.key))
        self.bridge.lan.stop()
        reopened = native_app.Bridge()
        self.addCleanup(reopened.lan.stop)
        self.assertEqual(reopened.lanStatus()["transport"], "https")
        self.assertEqual(reopened.lanStatus()["fingerprint"], self.pin)


if __name__ == "__main__":
    unittest.main()
