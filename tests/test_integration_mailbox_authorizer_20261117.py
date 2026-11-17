"""Windows LAN grant / mailbox authority; synthetic data only, no installed app."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_app
from integration_api_v1 import API_PREFIX
from integration_company_grant_v1 import IntegrationCompanyGrant
from integration_mailbox_authorizer_v1 import IntegrationMailboxAuthorizer
from integration_mailbox_v1 import IntegrationMailbox, sign_counterparties_reply
from lan import LanService
from mtr_account_lineage import principal_actor_id

try:
    from test_lan_tls import _CERT, _KEY
except ModuleNotFoundError:
    from tests.test_lan_tls import _CERT, _KEY


@unittest.skipUnless(os.name == "nt", "Windows LAN registry ACL required")
class MailboxAuthorityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="madar-mailbox-authority-qa-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.root = root
        env = patch.dict(os.environ, {"APPDATA": str(root / "appdata")})
        env.start()
        self.addCleanup(env.stop)
        with patch.object(native_app, "datadir", return_value=root):
            bridge = native_app.Bridge()
            bridge.saveState(native_app.initial_state())
        cert, key = root / "test.crt", root / "test.key"
        cert.write_text(_CERT, encoding="ascii")
        key.write_text(_KEY, encoding="ascii")
        self.service = LanService(bridge, root / "lan-users.json",
                                  bind="127.0.0.1", port=0,
                                  certfile=cert, keyfile=key)
        self.service.setup_owner("owner", "synthetic-company-authorizer-secret")
        self.service.start()
        self.addCleanup(self.service.stop)
        self.admin_token = self.service.authenticate(
            "owner", "synthetic-company-authorizer-secret")["token"]
        self.actor = principal_actor_id(self.service.account_for(self.admin_token))
        self.router = self.service.integration_router
        self.grants = IntegrationCompanyGrant(self.service, self.router._key_store)
        self.company = "c" * 32
        self.installation = "a" * 32
        self.key_id = self._pair()
        self.current_token = self.admin_token
        self.current_peer = self.key_id
        self.authorizer = IntegrationMailboxAuthorizer(
            self.grants, host_token=lambda: self.current_token,
            peer_key=lambda: self.current_peer)

    def _pair(self):
        code = self.router.begin_pairing(self.admin_token, "owner",
                                         product="TARAZ")["code"]
        payload = json.dumps({"code": code, "product": "TARAZ",
                              "installationId": self.installation}).encode()
        response = self.router.handle("POST", API_PREFIX + "/pair",
                                      {"Content-Type": "application/json"}, payload)
        self.assertEqual(response.status, 201)
        return response.json()["keyId"]

    def _approve(self):
        self.grants.approve(self.admin_token, key_id=self.key_id,
                            company_id=self.company, installation_id=self.installation,
                            manual_confirmation=True)

    def _scope(self, action="enqueue", **values):
        active = self.grants.resolve_active(
            company_id=self.company, installation_id=self.installation)
        scope = dict(action=action,
                     workspace_id=active["workspaceId"] if active else "0" * 32,
                     installation_id=self.installation, company_id=self.company,
                     requested_actor=self.actor, requested_grant="counterparties.read",
                     operation="Counterparties.Search", request_id="d" * 32,
                     peer_key_id=self.key_id if action in
                     ("poll", "reply", "delivery_ack") else None)
        scope.update(values)
        return scope

    def test_pairing_without_company_grant_is_not_directory_authority(self):
        self.assertIsNone(self.grants.resolve_active(
            company_id=self.company, installation_id=self.installation))
        self.assertFalse(self.authorizer(**self._scope()))

    def test_current_admin_and_authenticated_peer_authorize_exact_scope(self):
        self._approve()
        active = self.grants.resolve_active(company_id=self.company,
                                            installation_id=self.installation)
        self.assertEqual(active["keyId"], self.key_id)
        self.assertTrue(self.authorizer(**self._scope()))
        self.assertTrue(self.authorizer(**self._scope("reconcile")))
        self.assertTrue(self.authorizer(**self._scope("result_ack")))
        self.assertTrue(self.authorizer(**self._scope("reply")))
        self.assertTrue(self.authorizer(**self._scope(
            "poll", requested_actor=None, requested_grant=None,
            operation=None, request_id=None)))

    def test_injected_actor_scope_and_expired_host_session_fail_closed(self):
        self._approve()
        self.assertFalse(self.authorizer(**self._scope(requested_actor="evil")))
        self.assertFalse(self.authorizer(**self._scope(company_id="f" * 32)))
        self.assertFalse(self.authorizer(**self._scope(workspace_id="f" * 32)))
        self.assertFalse(self.authorizer(**self._scope(operation="Ledger.Read")))
        self.assertFalse(self.authorizer(**self._scope(requested_grant="finance.write")))
        self.current_token = "expired-token"
        self.assertFalse(self.authorizer(**self._scope()))

    def test_peer_key_must_come_from_authenticated_router_not_payload(self):
        self._approve()
        self.current_peer = "ik_" + "9" * 24
        self.assertFalse(self.authorizer(**self._scope("reply")))
        self.current_peer = self.key_id
        self.assertFalse(self.authorizer(**self._scope(
            "poll", requested_actor=None, requested_grant="counterparties.read",
            operation=None, request_id=None)))
        self.assertFalse(self.authorizer(**self._scope("poll", requested_actor="evil")))

    def test_revocation_and_rotation_require_new_grant(self):
        self._approve()
        self.assertTrue(self.authorizer(**self._scope()))
        self.assertTrue(self.router.revoke_key(self.admin_token, self.key_id))
        self.assertFalse(self.authorizer(**self._scope()))
        old = self.key_id
        self.key_id = self._pair()
        self.current_peer = self.key_id
        self.assertNotEqual(old, self.key_id)
        self.assertFalse(self.authorizer(**self._scope()))
        self._approve()
        self.assertTrue(self.authorizer(**self._scope()))

    def test_real_mailbox_uses_current_host_and_peer_authority(self):
        self._approve()
        workspace = self.grants.resolve_active(
            company_id=self.company, installation_id=self.installation)["workspaceId"]
        box = IntegrationMailbox(self.root / "private-mailbox.sqlite3",
                                 authorizer=self.authorizer)
        request = "e" * 32
        params = {"query": "آرمان", "kind": "customer", "limit": 5, "cursor": None}
        base = dict(workspace_id=workspace, installation_id=self.installation,
                    company_id=self.company)
        self.assertEqual(box.enqueue(
            **base, request_id=request, requested_actor=self.actor,
            requested_grant="counterparties.read", operation="Counterparties.Search",
            parameters=params, now=1000)["status"], "pending")
        pending = box.poll(**base, peer_key_id=self.key_id, now=1001)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["requestId"], request)
        result = {"parties": [{"partyId": "C-000125", "name": "آرمان",
                               "kind": "customer"}], "hasMore": False,
                  "nextCursor": None}
        secret = b"synthetic-only-paired-bearer-for-mailbox-signature-123456"
        signature = sign_counterparties_reply(secret, pending[0], result)
        self.assertEqual(box.submit_reply(**base, request_id=request,
                                          peer_key_id=self.key_id, result=result,
                                          signature=signature, peer_secret=secret,
                                          now=1002)["status"], "completed")
        self.assertEqual(box.reconcile(**base, request_id=request,
                                       requested_actor=self.actor, now=1003)["result"],
                         result)
        self.assertTrue(box.acknowledge_result(
            **base, request_id=request, requested_actor=self.actor,
            now=1004)["acknowledged"])
        self.current_peer = "ik_" + "9" * 24
        with self.assertRaises(PermissionError):
            box.poll(**base, peer_key_id=self.key_id, now=1005)
        self.current_peer = self.key_id
        self.current_token = "revoked-host-session"
        with self.assertRaises(PermissionError):
            box.reconcile(**base, request_id=request,
                          requested_actor=self.actor, now=1005)


if __name__ == "__main__":
    unittest.main()
