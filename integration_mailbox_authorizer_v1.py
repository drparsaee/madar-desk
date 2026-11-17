"""Trusted Madar host authorization boundary for the counterparties mailbox.

Instantiate ONLY in the native HTTPS host. Both callbacks must read the
currently authenticated SERVER-side request context; never use browser JSON,
envelope actor, pairing code, or client-provided key ID as session authority.
This module mounts no HTTP routes and creates no services or financial writes.
"""
from __future__ import annotations

import hmac
import re

from integration_company_grant_v1 import IntegrationCompanyGrant
from mtr_account_lineage import principal_actor_id


_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_KEY_ID = re.compile(r"ik_[0-9a-f]{24}\Z")
_OPERATIONS = frozenset(("Counterparties.Search", "Counterparties.Get"))
_HOST = frozenset(("enqueue", "reconcile", "result_ack"))
_PEER = frozenset(("poll", "delivery_ack", "reply"))


class IntegrationMailboxAuthorizer:
    """Fail-closed callable for IntegrationMailbox(authorizer=...).

    `host_token` yields a current Madar LAN session token only during a
    native, authenticated host operation. `peer_key` yields the key ID already
    authenticated by IntegrationRouter._authorize on the current HTTPS request.
    Never pass request payload fields to these callbacks.
    """

    def __init__(self, grants: IntegrationCompanyGrant, *, host_token, peer_key):
        if (type(grants) is not IntegrationCompanyGrant or
                not callable(host_token) or not callable(peer_key)):
            raise TypeError("Trusted grants and server request context required")
        self.grants = grants
        self.host_token = host_token
        self.peer_key = peer_key

    def _live_admin_actor(self, actor):
        if type(actor) is not str or not actor:
            return False
        # The private LAN users registry is authoritative. A deleted account
        # or demoted role invalidates even a previously queued request.
        for account in self.grants.service.users.values():
            if account.get("role") != "admin":
                continue
            try:
                if hmac.compare_digest(principal_actor_id(account), actor):
                    return True
            except (ValueError, PermissionError, TypeError):
                continue
        return False

    def __call__(self, *, action, workspace_id, installation_id, company_id,
                 requested_actor=None, requested_grant=None, peer_key_id=None,
                 request_id=None, operation=None):
        try:
            if (action not in _HOST | _PEER or
                    any(type(value) is not str or not _HEX32.fullmatch(value)
                        for value in (workspace_id, installation_id, company_id))):
                return False
            if request_id is not None and (type(request_id) is not str or
                                           not _HEX32.fullmatch(request_id)):
                return False
            # The mailbox first authorizes a base scope, then separately
            # re-authorizes the stored immutable envelope. The base for peer
            # actions has NO actor/grant/operation; host reconcile/ACK bases
            # carry the actor but not the operation. Never treat a partial
            # scope as a complete envelope or skip later row checks.
            if requested_grant is None and operation is None:
                if action in _PEER:
                    if requested_actor is not None:
                        return False
                elif action in ("reconcile", "result_ack"):
                    if not self._live_admin_actor(requested_actor):
                        return False
                else:
                    return False
            else:
                if (requested_grant != "counterparties.read" or
                        operation not in _OPERATIONS or
                        not self._live_admin_actor(requested_actor)):
                    return False
            active = self.grants.resolve_active(
                company_id=company_id, installation_id=installation_id)
            if (active is None or
                    not hmac.compare_digest(active["workspaceId"], workspace_id) or
                    not self.grants.verified(key_id=active["keyId"],
                                              company_id=company_id,
                                              installation_id=installation_id)):
                return False
            if action in _HOST:
                if peer_key_id is not None:
                    return False
                token = self.host_token()
                account = self.grants.service.account_for(token)
                return (account.get("role") == "admin" and
                        hmac.compare_digest(principal_actor_id(account), requested_actor))
            if (type(peer_key_id) is not str or not _KEY_ID.fullmatch(peer_key_id) or
                    not hmac.compare_digest(peer_key_id, active["keyId"])):
                return False
            authenticated = self.peer_key()
            return (type(authenticated) is str and
                    hmac.compare_digest(authenticated, peer_key_id))
        except (Exception,):
            return False


__all__ = ["IntegrationMailboxAuthorizer"]
