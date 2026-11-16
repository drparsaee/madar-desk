"""Real local TLS host: integration credentials survive restart and revocation.

Fixtures live in a disposable directory. No installed app, user account, or
production ledger is read or modified.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from contextlib import closing
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

    def pair(self, code, *, installation_id="a" * 32, product="TARAZ"):
        payload = {"code": code, "product": product,
                   "installationId": installation_id}
        return self.service.integration_router.handle(
            "POST", API_PREFIX + "/pair",
            {"Content-Type": "application/json"},
            json.dumps(payload, separators=(",", ":")).encode("ascii"))

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

    def test_one_time_pairing_issues_credential_then_rotates_same_install(self):
        router = self.service.integration_router
        started = router.begin_pairing(self.owner_token(), "owner", product="TARAZ")
        self.assertRegex(started["code"], r"^[A-Z2-7]{13}$")
        self.assertTrue(started["oneTime"])
        first = self.pair(started["code"])
        self.assertEqual(first.status, 201)
        credential = first.json()["integrationCredential"]
        workspace = first.json()["workspaceId"]
        self.assertRegex(workspace, r"^[0-9a-f]{32}$")
        self.assertEqual(self.get_cards(credential).status, 200)
        self.assertEqual(self.pair(started["code"]).status, 401)
        listing = router.connected_installs(self.owner_token())
        self.assertEqual(listing["connections"][0]["status"], "active")
        self.assertNotIn(credential, repr(listing))

        new_code = router.begin_pairing(self.owner_token(), "owner")["code"]
        second = self.pair(new_code)
        self.assertEqual(second.status, 201)
        self.assertEqual(second.json()["workspaceId"], workspace)
        self.assertEqual(self.get_cards(credential).status, 401)
        newer = second.json()["integrationCredential"]
        self.assertEqual(self.get_cards(newer).status, 200)
        self.service.stop()
        self.service = self.start_host()
        self.assertEqual(self.get_cards(newer).status, 200)
        self.assertEqual(self.get_cards(credential).status, 401)

    def test_bad_pairing_code_bounded_and_unused_endpoint(self):
        router = self.service.integration_router
        good_code = router.begin_pairing(self.owner_token(), "owner")["code"]
        for _ in range(5):
            denied = self.pair("A" * 13)
            self.assertEqual(denied.status, 401)
            self.assertNotIn(good_code, repr(denied.json()))
        # A hostile LAN caller cannot cancel the admin's legitimate code by
        # making five bad guesses; only guesses are throttled.
        self.assertEqual(self.pair(good_code).status, 201)
        self.assertEqual(router.handle("POST", API_PREFIX + "/cards",
                                       {"Content-Type": "application/json"}, b"{}").status, 405)
        self.assertEqual(router.handle("GET", API_PREFIX + "/pair").status, 405)
        self.assertEqual(router.handle("POST", API_PREFIX + "/pair", {}, b"{}").status, 415)

    def test_pair_code_not_credential_and_admin_approval_required(self):
        router = self.service.integration_router
        with self.assertRaises(PermissionError):
            router.begin_pairing("unknown-token", "owner")
        code = router.begin_pairing(self.owner_token(), "owner")["code"]
        self.assertEqual(self.get_cards(code).status, 401)
        self.assertEqual(self.pair(code, product="RADAR").status, 401)
        # Wrong product consumes an attempt but does not invalidate a sound
        # administrator-approved pairing until the attempt limit is reached.
        first = self.pair(code)
        self.assertEqual(first.status, 201)
        self.assertEqual(self.get_cards(first.json()["integrationCredential"]).status, 200)

    def test_pairing_approval_invalidated_by_administrator_password_reset(self):
        router = self.service.integration_router
        code = router.begin_pairing(self.owner_token(), "owner")["code"]
        self.service.reset_password(self.owner_token(), "owner", "different-owner-password-489")
        response = self.pair(code)
        self.assertEqual(response.status, 403)
        self.assertEqual(response.json()["error"], "pairing_approval_revoked")
        self.assertEqual(self.pair(code).status, 401)
        self.assertEqual(router.connected_installs(
            self.service.authenticate("owner", "different-owner-password-489")["token"]),
            {"connections": []})

    def test_old_registry_v1_read_only_metadata_then_additive_migration(self):
        """Previously issued keys must survive schema upgrades without read writes."""
        import integration_key_registry
        registry = integration_key_registry.IntegrationKeyRegistry(self.users)
        # sqlite3.Connection.__exit__ commits but does NOT close its handle;
        # closing is necessary to permit Windows cleanup of the QA directory.
        with closing(sqlite3.connect(registry.path)) as db, db:
            db.execute("""CREATE TABLE integration_keys (
                secret_sha256 BLOB PRIMARY KEY, key_id TEXT NOT NULL UNIQUE,
                username TEXT NOT NULL, permissions TEXT NOT NULL,
                password_revision BLOB NOT NULL, expires_at REAL NOT NULL,
                revoked_at REAL)""")
            db.execute("""CREATE TABLE integration_key_audit (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id TEXT NOT NULL, action TEXT NOT NULL, at_epoch REAL NOT NULL)""")
            db.execute("PRAGMA user_version=1")
        before = registry.path.read_bytes()
        owner = self.owner_token()
        self.assertEqual(self.service.integration_router.connected_installs(owner),
                         {"connections": []})
        self.assertEqual(registry.path.read_bytes(), before)
        code = self.service.integration_router.begin_pairing(owner, "owner")["code"]
        response = self.pair(code)
        self.assertEqual(response.status, 201)
        self.assertEqual(len(self.service.integration_router.connected_installs(owner)["connections"]), 1)


if __name__ == "__main__":
    unittest.main()
