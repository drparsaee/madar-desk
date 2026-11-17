"""Pure host-owned account lineage identity for the Madar E2 boundary.

The host MUST mint ``accountLineage`` once, on initial account creation, and
persist it in its private user registry. On edits, password resets, and
re-logins it MUST preserve that same value; on deletion and recreation it
MUST mint a new one. Never take it from a client request or public user JSON.

This module performs no I/O, authentication, account migration, or registry
mutation. Its validation cannot authenticate the origin of an otherwise
well-formed 128-bit lineage; that is the host registry's responsibility.
"""

from __future__ import annotations

import hashlib
import re
import secrets


_LINEAGE_FIELD = "accountLineage"
_LINEAGE_LENGTH_BYTES = 16
_LINEAGE_PATTERN = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_ACTOR_PREFIX = "mtr-actor-v1-"
_ACTOR_DOMAIN = b"madar.mtr.account-lineage.actor.v1\x00"
_ZERO_LINEAGE = "0" * 32
_PROHIBITED_ACTOR_OVERRIDES = frozenset({
    "actorId", "actor_id", "principalActorId", "principal_actor_id",
})


class AccountLineageError(PermissionError):
    """Refuse missing, legacy, malformed, or conflicting actor identity."""


def new_account_lineage() -> str:
    """Mint a canonical 128-bit secret-random lineage for a NEW host account.

    This is an initial-creation helper, not a password-reset or re-login
    helper. The trusted host must enforce one-time issuance and uniqueness in
    its durable private registry before using the resulting identity.
    """
    candidate = secrets.token_bytes(_LINEAGE_LENGTH_BYTES)
    if (type(candidate) is not bytes or len(candidate) != _LINEAGE_LENGTH_BYTES
            or candidate == b"\x00" * _LINEAGE_LENGTH_BYTES):
        raise AccountLineageError("secure account lineage generation failed")
    return candidate.hex()


def principal_actor_id(account: dict) -> str:
    """Derive the stable opaque E2 actor ID from a HOST-PRIVATE account row.

    The caller MUST have fetched ``account`` from its authenticated private
    registry. No supplied username, role, password, session, or actor claim is
    used as identity. Missing/legacy account lineage is denied, never mapped
    to the username or a fresh random replacement during recovery.

    An arbitrary in-process caller could fabricate a syntactically valid
    lineage in a dict. Since this pure helper has no registry authentication
    material, it cannot prove provenance. Do not expose it as an HTTP/client
    identity parser or substitute it for host-side authentication.
    """
    if type(account) is not dict or any(
        key in account for key in _PROHIBITED_ACTOR_OVERRIDES
    ):
        raise AccountLineageError("trusted private account record required")

    lineage = account.get(_LINEAGE_FIELD)
    if (type(lineage) is not str or _LINEAGE_PATTERN.fullmatch(lineage) is None
            or lineage == _ZERO_LINEAGE):
        raise AccountLineageError("valid host-private account lineage required")

    # Domain-separated digest avoids disclosing the raw registry lineage and
    # contains no username/PII. ASCII output fits HostRequestStore's 180-char
    # identifier bound and is stable across process restarts.
    digest = hashlib.sha256(_ACTOR_DOMAIN + bytes.fromhex(lineage)).hexdigest()
    return _ACTOR_PREFIX + digest


__all__ = ["AccountLineageError", "new_account_lineage", "principal_actor_id"]
