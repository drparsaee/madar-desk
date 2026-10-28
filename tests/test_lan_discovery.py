"""Loopback-only security and lifecycle tests for untrusted LAN host discovery.

Every live UDP send in this module targets 127.0.0.1. No real LAN broadcast,
host login, user database, TLS connection or production port is touched.
"""

import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import lan_discovery as disc
try:
    from test_lan_tls import _CERT
except ImportError:
    from tests.test_lan_tls import _CERT


def free_loopback_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.fingerprint = "a" * 64
        self.nonce = "a" * 32
        self.offer = {
            "v": 1, "kind": "offer", "nonce": self.nonce, "name": "میزبان مدار",
            "port": 48370, "fingerprint": self.fingerprint,
            "ttl": 12, "id": "0" * 16, "transport": "https",
        }

    def packet(self, obj):
        return json.dumps(obj, ensure_ascii=False).encode("utf-8")

    def test_strict_rfc1918_peer_policy_and_explicit_test_loopback(self):
        for ip in ("10.2.3.4", "172.16.9.10", "172.31.255.1", "192.168.10.55"):
            self.assertEqual(disc._peer_ipv4(ip), ip)
        for ip in ("8.8.8.8", "127.0.0.1", "169.254.1.2", "100.64.0.1",
                   "198.18.0.1", "224.0.0.1", "255.255.255.255",
                   "0.0.0.0", "::1", "192.168.1.1.evil.test", "not-an-ip", ""):
            self.assertIsNone(disc._peer_ipv4(ip), ip)
        self.assertEqual(disc._peer_ipv4("127.0.0.1", test_loopback=True), "127.0.0.1")
        self.assertIsNone(disc._peer_ipv4("8.8.8.8", test_loopback=True))

    def test_solicitation_rejects_unknown_fields_replay_and_large_payloads(self):
        good = self.packet({"v": 1, "kind": "solicit", "nonce": self.nonce})
        self.assertEqual(disc._solicitation(good), self.nonce)
        for raw in (
            b"", b"not-json", b"\xff", b"[]" + b" " * 510,
            b"x" * (disc.MAX_PACKET + 1),
            self.packet({"v": True, "kind": "solicit", "nonce": self.nonce}),
            self.packet({"v": 2, "kind": "solicit", "nonce": self.nonce}),
            self.packet({"v": 1, "kind": "solicit", "nonce": "not-a-nonce"}),
            b'{"v":1,"v":1,"kind":"solicit","nonce":"' + self.nonce.encode() + b'"}',
            self.packet({"v": 1, "kind": "solicit", "nonce": self.nonce,
                         "url": "http://127.0.0.1/admin"}),
        ):
            self.assertIsNone(disc._solicitation(raw))

    def test_offers_must_match_nonce_and_deny_ssrf_and_http_fields(self):
        self.assertEqual(disc._advertisement(self.packet(self.offer), self.nonce)["name"],
                         "میزبان مدار")
        malformed = [
            {**self.offer, "nonce": "b" * 32},
            {**self.offer, "port": 0},
            {**self.offer, "port": 65536},
            {**self.offer, "port": "48370"},
            {**self.offer, "port": True},
            {**self.offer, "fingerprint": "invalid"},
            {**self.offer, "fingerprint": None},
            {**self.offer, "transport": "http"},
            {**self.offer, "url": "http://169.254.169.254/latest/meta-data"},
            {**self.offer, "ip": "192.168.1.20"},
            {**self.offer, "host": "evil.example"},
            {**self.offer, "ttl": 0},
            {**self.offer, "ttl": 100000},
            {**self.offer, "ttl": True},
            {**self.offer, "id": "invalid"},
            {**self.offer, "name": "<script>alert(1)</script>"},
            {**self.offer, "name": "host\u202e"},
            {**self.offer, "v": True},
            {**self.offer, "kind": "other"},
        ]
        for item in malformed:
            with self.subTest(item=item):
                self.assertIsNone(disc._advertisement(self.packet(item), self.nonce))
        beacon = {key: value for key, value in self.offer.items() if key != "nonce"}
        beacon["kind"] = "beacon"
        self.assertIsNotNone(disc._advertisement(self.packet(beacon), self.nonce))
        self.assertIsNone(disc._advertisement(self.packet({**beacon, "nonce": self.nonce}),
                                              self.nonce))
        self.assertIsNone(disc._advertisement(self.packet(self.offer), "b" * 32))

    def test_fixed_udp_ports_timeout_and_no_unsafe_target_overrides(self):
        with self.assertRaisesRegex(ValueError, "fixed UDP port"):
            disc.DiscoveryResponder("test", 48370, certfile="unused", discovery_port=12345)
        with self.assertRaisesRegex(ValueError, "fixed UDP port"):
            disc.DiscoveryClient(port=12345)
        with self.assertRaisesRegex(ValueError, "test-only"):
            disc.DiscoveryClient(_test_targets=("127.0.0.1",))
        with self.assertRaisesRegex(ValueError, "test-only"):
            disc.DiscoveryResponder("test", 48370, _test_targets=("127.0.0.1",))
        with self.assertRaisesRegex(ValueError, "loopback"):
            disc.DiscoveryResponder("test", 48370, _test_loopback=True,
                                    _test_targets=("255.255.255.255",))
        with self.assertRaisesRegex(ValueError, "loopback"):
            disc.DiscoveryClient(_test_loopback=True, _test_targets=("8.8.8.8",))
        client = disc.DiscoveryClient(_test_loopback=True,
                                      _test_beacon_port=free_loopback_port())
        for timeout in (-1, 0, 0.01, 5.01, float("nan"), True, "1"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                client.discover(timeout)

    def test_cache_deduplicates_and_expires_without_pairing(self):
        client = disc.DiscoveryClient(_test_loopback=True)
        key = ("127.0.0.1", 48370)
        candidate = {"name": "A", "url": "https://127.0.0.1:48370", "verified": False}
        client._entries[key] = (candidate, time.monotonic() + 0.05)
        self.assertEqual(client.snapshot(), [candidate])
        time.sleep(0.07)
        self.assertEqual(client.snapshot(), [])

    def test_public_api_keeps_exact_integration_signature(self):
        with patch.object(disc, "DiscoveryClient") as client:
            client.return_value.discover.return_value = [{"verified": False}]
            self.assertEqual(disc.discover_hosts(0.8, port=disc.DISCOVERY_PORT),
                             [{"verified": False}])
            client.assert_called_once_with(port=disc.DISCOVERY_PORT)
            client.return_value.discover.assert_called_once_with(0.8)


class LoopbackSocketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-discovery-loopback-")
        self.addCleanup(self.temp.cleanup)
        self.cert = Path(self.temp.name) / "test.crt"
        self.cert.write_text(_CERT, encoding="ascii")
        self.discovery_port = free_loopback_port()
        self.beacon_port = free_loopback_port()
        # Avoid a collision if the OS reused the just-closed port.
        while self.beacon_port == self.discovery_port:
            self.beacon_port = free_loopback_port()
        self.responder = disc.DiscoveryResponder(
            "میزبان تست", 48370, self.cert, discovery_port=self.discovery_port,
            _test_loopback=True, _test_targets=("127.0.0.1",),
            _test_beacon_port=self.beacon_port,
        )
        self.addCleanup(self.responder.stop)

    def make_client(self):
        return disc.DiscoveryClient(port=self.discovery_port, _test_loopback=True,
                                    _test_targets=("127.0.0.1",),
                                    _test_beacon_port=self.beacon_port)

    def test_real_loopback_solicit_returns_only_untrusted_https_peer_ip(self):
        self.assertFalse(self.responder.running)
        self.assertEqual(self.responder.start(), self.discovery_port)
        self.assertEqual(self.responder.start(), self.discovery_port)
        self.assertTrue(self.responder.running)
        found = self.make_client().discover(0.35)
        self.assertEqual(len(found), 1, found)
        candidate = found[0]
        self.assertEqual(candidate["name"], "میزبان تست")
        self.assertEqual(candidate["url"], "https://127.0.0.1:48370")
        self.assertEqual(candidate["peer_ip"], "127.0.0.1")
        self.assertEqual(candidate["transport"], "https")
        self.assertEqual(candidate["verified"], False)
        self.assertTrue(candidate["requires_pairing"])
        self.assertEqual(candidate["fingerprint"], disc.certificate_fingerprint(self.cert))
        self.assertLessEqual(candidate["ttl"], disc.MAX_TTL)
        self.assertLessEqual(candidate["expires_at"], time.time() + disc.MAX_TTL + 1)
        self.responder.stop()
        self.responder.stop()
        self.assertFalse(self.responder.running)
        self.assertEqual(self.responder.start(), self.discovery_port)
        self.assertEqual(len(self.make_client().discover(0.35)), 1)

    def test_rate_limits_and_oversize_udp_does_not_respond(self):
        self.responder.start()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as requester:
            requester.bind(("127.0.0.1", 0))
            requester.settimeout(0.25)
            dst = ("127.0.0.1", self.discovery_port)
            requester.sendto(b"x" * (disc.MAX_PACKET + 30), dst)
            with self.assertRaises(socket.timeout):
                requester.recvfrom(disc.MAX_PACKET + 1)
            for index in range(12):
                requester.sendto(disc._encode({"v": 1, "kind": "solicit",
                                               "nonce": f"{index:032x}"}), dst)
            replies = []
            until = time.monotonic() + 0.45
            while time.monotonic() < until:
                requester.settimeout(max(0.01, until - time.monotonic()))
                try:
                    data, peer = requester.recvfrom(disc.MAX_PACKET + 1)
                except socket.timeout:
                    break
                self.assertEqual(peer[0], "127.0.0.1")
                self.assertEqual(peer[1], self.discovery_port)
                replies.append(disc._decode(data))
            self.assertGreaterEqual(len(replies), 1, repr({
                "responder_running": self.responder.running,
                "peer_buckets": {ip: round(bucket.tokens, 2)
                                 for ip, bucket in self.responder._peers.items()},
            }))
            self.assertLessEqual(len(replies), 3, "per-IP bucket must prevent UDP amplification")
            self.assertTrue(all(reply["kind"] == "offer" for reply in replies))

    def test_passive_beacon_is_received_without_solicit_reply(self):
        with patch.object(disc, "BEACON_INTERVAL", 0.08):
            self.responder._allow_reply = lambda _ip, _now: False
            self.responder.start()
            found = self.make_client().discover(0.4)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["name"], "میزبان تست")
        self.assertFalse(found[0]["verified"])

    def test_udp_forged_fingerprint_is_returned_only_as_unverified_hint(self):
        observed = []
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as fake:
            fake.bind(("127.0.0.1", self.discovery_port))
            fake.settimeout(0.8)
            def send_fake():
                raw, (peer, peer_port) = fake.recvfrom(disc.MAX_PACKET + 1)
                nonce = disc._solicitation(raw)
                observed.append((peer, peer_port, nonce))
                payload = {
                    "v": 1, "kind": "offer", "name": "جعلی", "port": 48370,
                    "fingerprint": "f" * 64, "ttl": 10, "id": "a" * 16,
                    "transport": "https", "nonce": nonce,
                }
                fake.sendto(disc._encode({**payload, "nonce": "b" * 32}),
                            (peer, peer_port))
                fake.sendto(disc._encode(payload), (peer, peer_port))
            worker = threading.Thread(target=send_fake, daemon=True)
            worker.start()
            found = self.make_client().discover(0.3)
            worker.join(timeout=1)
        self.assertEqual(len(observed), 1)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["fingerprint"], "f" * 64)
        self.assertEqual(found[0]["url"], "https://127.0.0.1:48370")
        self.assertEqual(found[0]["peer_ip"], "127.0.0.1")
        self.assertIs(found[0]["verified"], False)
        self.assertIs(found[0]["requires_pairing"], True)

    def test_missing_https_certificate_never_advertises_legacy_http(self):
        responder = disc.DiscoveryResponder(
            "HTTP-only", 48370, certfile=None,
            discovery_port=self.discovery_port, _test_loopback=True,
            _test_targets=("127.0.0.1",), _test_beacon_port=self.beacon_port,
        )
        with self.assertRaisesRegex(ValueError, "HTTPS certificate"):
            responder.start()
        self.assertFalse(responder.running)
        self.assertEqual(self.make_client().discover(0.12), [])


if __name__ == "__main__":
    unittest.main()
