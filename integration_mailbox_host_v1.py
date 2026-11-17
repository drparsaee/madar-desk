"""Trusted native Madar host facade for explicitly authorized customer lookup.

No company/actor/workspace trust originates in browser JSON. The caller gives
an authenticated, current LAN admin token obtained from LanService.authenticate;
the host itself resolves actor lineage, approved Taraz peer-company mapping,
workspace identity, and the protected mailbox storage location. This creates
no new LAN listener, no financial writes, and no direct access to Taraz books.
"""
from __future__ import annotations

from pathlib import Path
import re

from integration_company_grant_v1 import IntegrationCompanyGrant
from integration_mailbox_authorizer_v1 import IntegrationMailboxAuthorizer
from integration_mailbox_v1 import IntegrationMailbox
from mtr_account_lineage import principal_actor_id


_HEX32 = re.compile(r"[a-f0-9]{32}\Z")


class MadarMailboxHost:
    def __init__(self, router):
        if not hasattr(router, "_key_store") or not hasattr(router, "service"):
            raise TypeError("Existing authenticated integration router required")
        self.router = router
        self.service = router.service
        self.grants = IntegrationCompanyGrant(self.service, router._key_store)

    def _scope(self, current_admin_token, *, company_id, installation_id):
        if (type(company_id) is not str or not _HEX32.fullmatch(company_id) or
                type(installation_id) is not str or not _HEX32.fullmatch(installation_id)):
            raise ValueError("Invalid explicitly selected Taraz company and installation")
        with self.service.lock:
            self.router._require_https()
            account = self.service.account_for(current_admin_token)
            if account.get("role") != "admin":
                raise PermissionError("Current LAN administrator required")
            actor = principal_actor_id(account)
            active = self.grants.resolve_active(
                company_id=company_id, installation_id=installation_id)
            if active is None:
                raise PermissionError("An explicit approved Taraz company grant is required")
            return actor, active

    def _mailbox(self, current_admin_token):
        auth = IntegrationMailboxAuthorizer(
            self.grants, host_token=lambda: current_admin_token,
            peer_key=lambda: None)
        user_path = Path(self.service.users_path)
        return IntegrationMailbox(user_path.with_name(
            user_path.stem + ".counterparties-mailbox.sqlite3"),
            authorizer=auth)

    def approve_company(self, current_admin_token, *, company_id,
                        installation_id, key_id, manual_confirmation):
        return self.grants.approve(current_admin_token, key_id=key_id,
                                   company_id=company_id,
                                   installation_id=installation_id,
                                   manual_confirmation=manual_confirmation)

    def enqueue_search(self, current_admin_token, *, company_id,
                       installation_id, request_id, query, kind="customer",
                       limit=10, cursor=None):
        if (type(request_id) is not str or not _HEX32.fullmatch(request_id)
                or type(limit) is not int or not 1 <= limit <= 20):
            raise ValueError("Invalid idempotent search request")
        actor, active = self._scope(current_admin_token,
                                    company_id=company_id,
                                    installation_id=installation_id)
        result = self._mailbox(current_admin_token).enqueue(
            workspace_id=active["workspaceId"], installation_id=installation_id,
            company_id=company_id, request_id=request_id,
            requested_actor=actor, requested_grant="counterparties.read",
            operation="Counterparties.Search", parameters={
                "query": query, "kind": kind, "limit": limit, "cursor": cursor})
        return {**result, "workspaceId": active["workspaceId"],
                "companyId": company_id, "installationId": installation_id,
                "financialEventCreated": False}

    def reconcile(self, current_admin_token, *, company_id,
                  installation_id, request_id, acknowledge=False):
        if type(request_id) is not str or not _HEX32.fullmatch(request_id):
            raise ValueError("Invalid queued request reference")
        if type(acknowledge) is not bool:
            raise ValueError("Explicit boolean ACK required")
        actor, active = self._scope(current_admin_token,
                                    company_id=company_id,
                                    installation_id=installation_id)
        scope = dict(workspace_id=active["workspaceId"],
                     installation_id=installation_id, company_id=company_id,
                     request_id=request_id, requested_actor=actor)
        mailbox = self._mailbox(current_admin_token)
        response = mailbox.reconcile(**scope)
        if acknowledge and response["status"] == "completed":
            mailbox.acknowledge_result(**scope)
            response = {**response, "acknowledged": True}
        return {**response, "workspaceId": active["workspaceId"],
                "companyId": company_id, "installationId": installation_id,
                "source": "TARAZ", "readOnly": True,
                "financialEventCreated": False}


__all__ = ["MadarMailboxHost"]
