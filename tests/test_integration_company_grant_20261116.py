"""Explicit company binding is never inferred from pairing or client JSON.

Disposable Windows LAN/SQLite hosts; no installed app or financial data.
"""
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import native_app
from integration_api_v1 import API_PREFIX
from integration_company_grant_v1 import IntegrationCompanyGrant, CompanyGrantDenied
from lan import LanService

try:
    from test_lan_tls import _CERT, _KEY
except ModuleNotFoundError:
    from tests.test_lan_tls import _CERT, _KEY


@unittest.skipUnless(os.name == "nt", "Windows private integration registry required")
class ExplicitCompanyGrantTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="madar-company-grant-qa-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        env = patch.dict(os.environ, {"APPDATA": str(self.root / "appdata")})
        env.start()
        self.addCleanup(env.stop)
        with patch.object(native_app, "datadir", return_value=self.root):
            bridge = native_app.Bridge()
            bridge.saveState(native_app.initial_state())
        cert, key = self.root / "test.crt", self.root / "test.key"
        cert.write_text(_CERT, encoding="ascii")
        key.write_text(_KEY, encoding="ascii")
        self.service = LanService(bridge, self.root / "lan-users.json",
                                  bind="127.0.0.1", port=0,
                                  certfile=cert, keyfile=key)
        self.service.setup_owner("owner", "company-grant-test-secret")
        self.service.start()
        self.addCleanup(self.service.stop)
        self.token = self.service.authenticate("owner", "company-grant-test-secret")["token"]
        self.router = self.service.integration_router
        self.grants = IntegrationCompanyGrant(self.service, self.router._key_store)
        self.company = "c" * 32
        self.install = "a" * 32

    def pair(self, installation_id=None):
        code = self.router.begin_pairing(self.token, "owner", product="TARAZ")["code"]
        body = json.dumps({"code": code, "product": "TARAZ",
                           "installationId": installation_id or self.install}).encode()
        response = self.router.handle("POST", API_PREFIX + "/pair",
                                      {"Content-Type": "application/json"}, body)
        self.assertEqual(response.status, 201)
        return response.json()["keyId"]

    def test_pairing_never_auto_approves_unverified_company(self):
        key_id = self.pair()
        self.assertFalse(self.grants.verified(key_id=key_id, company_id=self.company,
                                              installation_id=self.install))
        with self.assertRaises(CompanyGrantDenied):
            self.grants.approve(self.token, key_id=key_id,
                                company_id=self.company, installation_id=self.install,
                                manual_confirmation=False)
        self.assertFalse(self.grants.verified(key_id=key_id, company_id=self.company,
                                              installation_id=self.install))

    def test_exact_admin_approval_company_and_installation_scope_revoke(self):
        key_id = self.pair()
        out = self.grants.approve(self.token, key_id=key_id,
                                  company_id=self.company, installation_id=self.install,
                                  manual_confirmation=True)
        self.assertTrue(out["approved"])
        self.assertFalse(out["alreadyApproved"])
        again = self.grants.approve(self.token, key_id=key_id,
                                    company_id=self.company, installation_id=self.install,
                                    manual_confirmation=True)
        self.assertTrue(again["alreadyApproved"])
        self.assertTrue(self.grants.verified(key_id=key_id, company_id=self.company,
                                             installation_id=self.install))
        self.assertFalse(self.grants.verified(key_id=key_id, company_id="d" * 32,
                                              installation_id=self.install))
        self.assertFalse(self.grants.verified(key_id=key_id, company_id=self.company,
                                              installation_id="b" * 32))
        with self.assertRaises(CompanyGrantDenied):
            self.grants.approve(self.token, key_id=key_id,
                                company_id="d" * 32, installation_id=self.install,
                                manual_confirmation=True)
        self.assertTrue(self.grants.revoke(self.token, key_id=key_id,
                                           company_id=self.company,
                                           installation_id=self.install)["revoked"])
        self.assertFalse(self.grants.verified(key_id=key_id, company_id=self.company,
                                              installation_id=self.install))

    def test_key_revocation_and_rotation_do_not_inherit_company_grant(self):
        key_id = self.pair()
        self.grants.approve(self.token, key_id=key_id, company_id=self.company,
                            installation_id=self.install, manual_confirmation=True)
        new_key = self.pair()
        self.assertFalse(self.grants.verified(key_id=key_id,
                                              company_id=self.company,
                                              installation_id=self.install))
        self.assertFalse(self.grants.verified(key_id=new_key,
                                              company_id=self.company,
                                              installation_id=self.install))
        self.grants.approve(self.token, key_id=new_key, company_id=self.company,
                            installation_id=self.install, manual_confirmation=True)
        self.assertTrue(self.grants.verified(key_id=new_key, company_id=self.company,
                                             installation_id=self.install))
        self.assertTrue(self.router.revoke_key(self.token, new_key))
        self.assertFalse(self.grants.verified(key_id=new_key, company_id=self.company,
                                              installation_id=self.install))

    def test_wrong_approval_scope_or_lost_admin_session_fails_closed(self):
        key_id = self.pair()
        with self.assertRaises(CompanyGrantDenied):
            self.grants.approve(self.token, key_id=key_id, company_id=self.company,
                                installation_id="e" * 32, manual_confirmation=True)
        with self.assertRaises(PermissionError):
            self.grants.approve("no-admin-session", key_id=key_id,
                                company_id=self.company, installation_id=self.install,
                                manual_confirmation=True)
        self.assertFalse(self.grants.verified(key_id=key_id, company_id=self.company,
                                              installation_id=self.install))


if __name__ == "__main__":
    unittest.main()
