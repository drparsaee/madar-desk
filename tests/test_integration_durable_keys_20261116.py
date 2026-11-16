"""Real local TLS host: integration credentials survive restart and revocation.

Fixtures live in a disposable directory. No installed app, user account, or
production ledger is read or modified.
"""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app
from integration_api_v1 import API_PREFIX, IntegrationRouter
from integration_key_registry import IntegrationKeyRegistry
from lan import LanService

try:
    from test_lan_tls import _CERT, _KEY
except ModuleNotFoundError:
    from tests.test_lan_tls import _CERT, _KEY


class DurableIntegrationKeysTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-durable-keys-qa-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"APPDATA": str(self.root / "appdata")})
        self.env.start()
        self.addCleanup(self.env.stop)
        with patch.object(native_app, "datadir", return_value=self.root):
            self.bridge = native_app.Bridge()
            self.bridge.saveState(native_app.initial_state())
        self.cert = self.root / "test.crt"
        self.key = self.root / "test.key"
        self.cert.write_text(_CERT, encoding="ascii")
        self.key.write_text(_KEY, encoding="ascii")
        self.users = self.root / "lan-users.json"
        self.service = self.start_host(create_owner=True)

    def start_host(self, *, create_owner=False):
        service = LanService(self.bridge, self.users,
                             bind="127.0.0.1", port=0,
                             certfile=self.cert, keyfile=self.key)
        if create_owner:
            service.setup_owner("owner", "durable-local-password")
        service.start()
        self.addCleanup(lambda: service.stop() if service.server else None)
        return service

    def owner_token(self):
        return self.service.authenticate("owner", "durable-local-password")["token"]

    def get_cards(self, key):
        return self.service.integration_router.handle(
            "GET", API_PREFIX + "/cards", {"X-Madar-Integration-Key": key})

    def test_key_remains_authorized_after_router_and_host_restart(self):
        key = self.service.integration_router.issue_key(
            self.owner_token(), "owner", permissions=("read",))
        self.assertEqual(self.get_cards(key["key"]).status, 200)
        registry = IntegrationKeyRegistry(self.users)
        self.assertTrue(registry.path.is_file())
        self.assertNotIn(key["key"].encode("ascii"), registry.path.read_bytes())
        self.assertIn(hashlib.sha256(key["key"].encode()).digest(), registry.path.read_bytes())

        # Same host/service but fresh API-router instance.
        self.service.integration_router = IntegrationRouter(self.service)
        self.assertEqual(self.get_cards(key["key"]).status, 200)

        self.service.stop()
        self.service = self.start_host()
        self.assertEqual(self.get_cards(key["key"]).status, 200)
        self.assertTrue(self.service.integration_router.revoke_key(
            self.owner_token(), key["keyId"]))
        self.assertEqual(self.get_cards(key["key"]).status, 401)
        self.service.stop()
        self.service = self.start_host()
        self.assertEqual(self.get_cards(key["key"]).status, 401)

    def test_revocation_is_immediate_across_router_instances(self):
        left = self.service.integration_router
        key = left.issue_key(self.owner_token(), "owner")
        right = IntegrationRouter(self.service)
        self.assertEqual(right.handle("GET", API_PREFIX + "/cards",
                                      {"X-Madar-Integration-Key": key["key"]}).status, 200)
        self.assertTrue(left.revoke_key(self.owner_token(), key["keyId"]))
        self.assertEqual(right.handle("GET", API_PREFIX + "/cards",
                                      {"X-Madar-Integration-Key": key["key"]}).status, 401)

    def test_separate_hosts_cannot_reuse_credential(self):
        key = self.service.integration_router.issue_key(self.owner_token(), "owner")
        another_users = self.root / "another-users.json"
        isolated = LanService(self.bridge, another_users,
                              bind="127.0.0.1", port=0,
                              certfile=self.cert, keyfile=self.key)
        isolated.setup_owner("owner", "durable-local-password")
        isolated.start()
        self.addCleanup(isolated.stop)
        self.assertEqual(isolated.integration_router.handle(
            "GET", API_PREFIX + "/cards",
            {"X-Madar-Integration-Key": key["key"]}).status, 401)

    def test_registry_rejects_symlink_if_supported(self):
        registry = IntegrationKeyRegistry(self.users)
        target = self.root / "target.txt"
        target.write_text("no", encoding="utf-8")
        try:
            registry.path.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Current Windows account cannot create a symlink")
        with self.assertRaises(PermissionError):
            registry.lookup(b"0" * 32, now=0.)


if __name__ == "__main__":
    unittest.main()
