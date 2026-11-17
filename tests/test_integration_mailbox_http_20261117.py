"""Actual Madar router + protected Mailbox authority, disposable Windows host.

Never opens or mutates a production workspace. The LAN HTTPS service used by
the parent fixture already binds a throwaway 127.0.0.1 TLS port.
"""
import json
import unittest

from tests.test_integration_company_grant_20261116 import ExplicitCompanyGrantTests
from integration_api_v1 import API_PREFIX
from integration_mailbox_authorizer_v1 import IntegrationMailboxAuthorizer
from integration_mailbox_v1 import IntegrationMailbox, sign_counterparties_reply
from mtr_account_lineage import principal_actor_id


class MailboxRouterHttpsTests(ExplicitCompanyGrantTests):
    def test_live_router_poll_reply_ack_and_revocation(self):
        code = self.router.begin_pairing(self.token, "owner", product="TARAZ")["code"]
        reply = self.router.handle("POST", API_PREFIX + "/pair",
            {"Content-Type": "application/json"}, json.dumps({
                "code": code, "product": "TARAZ", "installationId": self.install}).encode())
        self.assertEqual(reply.status, 201)
        paired = reply.json()
        key, key_id = paired["integrationCredential"], paired["keyId"]
        self.grants.approve(self.token, key_id=key_id, company_id=self.company,
                            installation_id=self.install, manual_confirmation=True)
        actor = principal_actor_id(self.service.account_for(self.token))
        authority = IntegrationMailboxAuthorizer(
            self.grants, host_token=lambda: self.token, peer_key=lambda: key_id)
        box = IntegrationMailbox(self.root / "lan-users.counterparties-mailbox.sqlite3",
                                 authorizer=authority)
        workspace = paired["workspaceId"]
        scope = {"workspaceId": workspace, "installationId": self.install,
                 "companyId": self.company}
        request_id = "b" * 32
        box.enqueue(workspace_id=workspace, installation_id=self.install,
                    company_id=self.company, request_id=request_id,
                    requested_actor=actor, requested_grant="counterparties.read",
                    operation="Counterparties.Search", parameters={
                        "query": "آرمان", "kind": "customer", "limit": 5, "cursor": None})

        def call(path, body, token=key):
            return self.router.handle("POST", API_PREFIX + path,
                {"Content-Type": "application/json",
                 "X-Madar-Integration-Key": token},
                json.dumps(body, ensure_ascii=False).encode("utf-8"))

        result = call("/mailbox/poll", {**scope, "limit": 10})
        self.assertEqual(result.status, 200, result.json())
        queued = result.json()["requests"]
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["requestId"], request_id)
        self.assertEqual(call("/mailbox/delivery-ack", {**scope,
            "requestId": request_id}).status, 200)
        projection = {"parties": [{"partyId": "c_12", "name": "آرمان",
                                    "kind": "customer"}],
                      "hasMore": False, "nextCursor": None}
        signature = sign_counterparties_reply(key.encode("ascii"), queued[0], projection)
        signed = {**scope, "requestId": request_id,
                  "result": projection, "signature": signature}
        self.assertEqual(call("/mailbox/reply", signed).status, 200)
        self.assertEqual(call("/mailbox/reply", signed).status, 200)
        self.assertEqual(box.reconcile(workspace_id=workspace,
            installation_id=self.install, company_id=self.company,
            request_id=request_id, requested_actor=actor)["result"], projection)
        self.assertEqual(call("/mailbox/poll", {**scope, "limit": 10}).json()["requests"], [])
        self.assertEqual(call("/mailbox/poll", {**scope, "limit": 10}, token="invalid").status, 401)
        self.assertEqual(call("/mailbox/poll", {**scope, "companyId": "d" * 32,
                                                    "limit": 10}).status, 403)
        self.assertTrue(self.router.revoke_key(self.token, key_id))
        self.assertEqual(call("/mailbox/poll", {**scope, "limit": 10}).status, 401)


if __name__ == "__main__":
    unittest.main()
