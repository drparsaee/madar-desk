"""Bounded transparent LAN reconnection (no real network or user profile)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, patch

import native_app
from native_app import Bridge
from lan import LanService, certificate_fingerprint


class LanAutoReconnectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="madar-reconnect-qa-")
        self.addCleanup(self.temporary.cleanup)
        self.bridge = object.__new__(Bridge)
        bridge = self.bridge
        bridge._lock = threading.RLock()
        bridge._last_client_reconnect_attempt = 0.0
        bridge.connection = {"mode": "client", "url": "https://127.0.0.1:48370",
                             "fingerprint": "a" * 64}
        bridge.remote_token = None
        bridge.remote_user = {"username": "editor", "role": "editor"}
        bridge._network_available = False
        bridge._last_network_sync = None
        bridge.client_auth_path = Path(self.temporary.name) / "lan-login.bin"
        bridge.client_auth_path.write_bytes(b"synthetic-encrypted-credentials")
        bridge._remote_login = Mock(side_effect=self.login_success)
        bridge._sync_client_from_host = Mock(return_value={"projects": [], "tasks": [],
                                                          "__remoteRevision": "r1"})
        bridge._remote_request = Mock(return_value={"user": bridge.remote_user})

    def login_success(self, *_args, **_kwargs):
        self.bridge.remote_token = "synthetic-session"
        self.bridge._network_available = True

    def test_reconnect_uses_existing_pinned_target_and_protected_credentials(self):
        with patch("native_app.protect_windows", return_value=json.dumps({
            "username": "editor", "password": "not-a-real-password"
        }).encode()), patch("native_app.time.monotonic", return_value=100):
            self.assertTrue(self.bridge._maybe_reconnect_client())
        self.bridge._remote_login.assert_called_once_with(
            "https://127.0.0.1:48370", "editor", "not-a-real-password",
            fingerprint="a" * 64)
        self.bridge._sync_client_from_host.assert_called_once()
        self.assertFalse(self.bridge.connection.get("error"))

    def test_unavailable_host_is_rate_limited_without_http_downgrade(self):
        self.bridge._remote_login.side_effect = ConnectionError("host offline")
        with patch("native_app.protect_windows", return_value=json.dumps({
            "username": "editor", "password": "synthetic-password"
        }).encode()), patch("native_app.time.monotonic", side_effect=[100, 105, 111]):
            with self.assertRaises(ConnectionError):
                self.bridge._maybe_reconnect_client()
            self.assertFalse(self.bridge._maybe_reconnect_client())
            with self.assertRaises(ConnectionError):
                self.bridge._maybe_reconnect_client()
        self.assertEqual(self.bridge._remote_login.call_count, 2)
        for call in self.bridge._remote_login.call_args_list:
            self.assertEqual(call.kwargs["fingerprint"], "a" * 64)
            self.assertTrue(call.args[0].startswith("https://"))

    def test_lan_status_triggers_reconnect_and_marks_connected(self):
        with patch("native_app.protect_windows", return_value=json.dumps({
            "username": "editor", "password": "synthetic-password"
        }).encode()), patch("native_app.time.monotonic", return_value=100):
            self.bridge.offline = Mock()
            self.bridge.offline.has_pending.return_value = False
            self.bridge.offline.folder_status.return_value = {"configured": False}
            status = self.bridge.lanStatus(True)
        self.assertEqual(status["mode"], "client")
        self.assertTrue(status["connected"])
        self.assertTrue(status["transport"] == "https")
        self.assertEqual(status["fingerprint"], "a" * 64)

    def test_invalid_protected_credentials_fail_closed(self):
        with patch("native_app.protect_windows", return_value=b'{}'), \
             patch("native_app.time.monotonic", return_value=100):
            with self.assertRaisesRegex(ValueError, "ورود"):
                self.bridge._maybe_reconnect_client()
        self.bridge._remote_login.assert_not_called()


class RealHttpsReconnectTests(unittest.TestCase):
    """Real HTTPS loopback host and two separate synthetic data authorities."""

    def test_cached_client_rejoins_host_after_outage_and_replays_pending_task(self):
        try:
            from test_lan_tls import _CERT, _KEY  # unittest discover -s tests
        except ModuleNotFoundError:
            from tests.test_lan_tls import _CERT, _KEY  # Qualified invocation

        with TemporaryDirectory(prefix="madar-real-lan-reconnect-") as dirname:
            root = Path(dirname)
            host_root, client_root = root / "host", root / "client"
            host_root.mkdir()
            client_root.mkdir()
            cert, key = root / "test.crt", root / "test.key"
            cert.write_text(_CERT, encoding="ascii")
            key.write_text(_KEY, encoding="ascii")
            with patch.object(native_app, "datadir", return_value=host_root):
                host = Bridge()
            host.saveState(native_app.initial_state())
            lan = LanService(host, host_root / "lan-users.json",
                             bind="127.0.0.1", port=0,
                             certfile=cert, keyfile=key)
            host.lan = lan
            lan.setup_owner("owner", "a-very-long-local-password")
            port = lan.start()
            with patch.object(native_app, "datadir", return_value=client_root):
                client = Bridge()
            try:
                url = f"https://127.0.0.1:{port}"
                pin = certificate_fingerprint(cert)
                status = client.lanJoin(url, "owner", "a-very-long-local-password", pin)
                self.assertEqual(status["mode"], "client")
                current = client.getState()
                first_task_id = current["tasks"][0]["id"]
                lan.stop()
                edited = {**current, "tasks": [
                    {**task, "description": "Offline edit survives a host outage"}
                    if task["id"] == first_task_id else task
                    for task in current["tasks"]
                ]}
                response = client.saveState(edited)
                self.assertTrue(response["offline"])
                self.assertTrue(client.offline.has_pending())
                # This is a new listener on the same ephemeral port. An expired
                # token must be renewed with the *original* verified TLS pin.
                lan.start()
                client._last_client_reconnect_attempt = 0
                resumed = client.lanStatus(True)
                self.assertTrue(resumed["connected"])
                self.assertFalse(client.offline.has_pending())
                saved = next(task for task in host.getState()["tasks"]
                             if task["id"] == first_task_id)
                self.assertEqual(saved["description"],
                                 "Offline edit survives a host outage")
                self.assertEqual(client.connection["fingerprint"], pin)
            finally:
                lan.stop()


if __name__ == "__main__":
    unittest.main()
