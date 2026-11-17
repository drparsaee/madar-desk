"""Only the EXISTING pinned Madar HTTPS listener may dispatch peer mailbox calls.

This module has no listener and no host-administrator enrolment endpoint. The
caller must first authenticate an active integration bearer with the existing
IntegrationRouter._authorize, then pass only server-verified peer key context.
All request-supplied scope claims are rechecked against live peer/company
binding via IntegrationMailboxAuthorizer. The raw bearer is used for a single
HMAC comparison and is never persisted or returned.
"""
from __future__ import annotations

from pathlib import Path

from integration_company_grant_v1 import IntegrationCompanyGrant
from integration_mailbox_authorizer_v1 import IntegrationMailboxAuthorizer
from integration_mailbox_v1 import IntegrationMailbox


_PATHS = frozenset({"/mailbox/poll", "/mailbox/reply", "/mailbox/delivery-ack"})
_SCOPE = frozenset({"workspaceId", "installationId", "companyId"})


def dispatch_authenticated_peer(router, *, path, payload, peer_entry, bearer):
    """Return a safe data-only result to IntegrationRouter._response.

    Only call after TLS enforcement, valid key digest, password revision,
    read permission and bounded strict JSON parsing. No browser/native token is
    ever accepted as a substitute for the authenticated integration header.
    """
    if (path not in _PATHS or type(payload) is not dict or
            type(peer_entry) is not dict or
            type(peer_entry.get("keyId")) is not str or
            type(bearer) is not str):
        raise ValueError("Invalid trusted mailbox invocation")
    required = {
        "/mailbox/poll": _SCOPE | {"limit"},
        "/mailbox/reply": _SCOPE | {"requestId", "result", "signature"},
        "/mailbox/delivery-ack": _SCOPE | {"requestId"},
    }[path]
    if set(payload) != required:
        raise ValueError("Invalid mailbox request fields")

    service = router.service
    grants = IntegrationCompanyGrant(service, router._key_store)
    key_id = peer_entry["keyId"]
    authorizer = IntegrationMailboxAuthorizer(
        grants, host_token=lambda: None, peer_key=lambda: key_id)
    users_path = Path(service.users_path)
    mailbox_path = users_path.with_name(users_path.stem + ".counterparties-mailbox.sqlite3")
    mailbox = IntegrationMailbox(mailbox_path, authorizer=authorizer)
    scope = dict(workspace_id=payload["workspaceId"],
                 installation_id=payload["installationId"],
                 company_id=payload["companyId"])
    if path == "/mailbox/poll":
        rows = mailbox.poll(**scope, peer_key_id=key_id, limit=payload["limit"])
        return {"version": 1, "requests": rows}
    if path == "/mailbox/delivery-ack":
        receipt = mailbox.acknowledge_delivery(
            **scope, request_id=payload["requestId"], peer_key_id=key_id)
        return {"version": 1, **receipt}
    receipt = mailbox.submit_reply(
        **scope, request_id=payload["requestId"], peer_key_id=key_id,
        result=payload["result"], signature=payload["signature"],
        peer_secret=bearer.encode("ascii"))
    return {"version": 1, **receipt}


__all__ = ["dispatch_authenticated_peer"]
