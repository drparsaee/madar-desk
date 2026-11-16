"""One-use, short-lived administrator-approved integration pairing capability.

The pairing code is never stored on disk and is never an API credential. The
router consumes it under its existing TLS and administrator authorization.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time


_CODE = re.compile(r"[A-Z2-7]{13}\Z")
_INSTALL = re.compile(r"[0-9a-f]{32}\Z")


class PairingDenied(PermissionError):
    pass


class OneTimePairing:
    """One pending invitation; throttle guesses without revoking a real code.

    A LAN caller sending five bad codes must not invalidate the legitimate
    administrator-issued invitation, but also cannot guess at unlimited speed.
    """

    def __init__(self):
        self._pending = None

    def begin(self, *, username, product, permissions, approver_username,
              approver_revision, approver_lineage, valid_seconds=300):
        if (type(username) is not str or not username or
                type(product) is not str or product not in ("TARAZ", "RADAR") or
                type(permissions) is not frozenset or
                not permissions or not permissions.issubset({"read", "write"}) or
                type(approver_username) is not str or not approver_username or
                type(approver_revision) is not bytes or len(approver_revision) != 32 or
                (approver_lineage is not None and type(approver_lineage) is not str) or
                type(valid_seconds) is not int or not 30 <= valid_seconds <= 300):
            raise ValueError("Invalid pairing authorization")
        code = base64.b32encode(secrets.token_bytes(8)).decode("ascii").rstrip("=")
        now = time.time()
        self._pending = {"digest": hashlib.sha256(code.encode("ascii")).digest(),
                         "username": username, "product": product,
                         "approverUsername": approver_username,
                         "approverRevision": approver_revision,
                         "approverLineage": approver_lineage,
                         "permissions": permissions, "expiresAt": now + valid_seconds,
                         "attempts": 0, "cooldownUntil": 0.0}
        return {"code": code, "expiresAt": int(now + valid_seconds),
                "product": product, "username": username,
                "permissions": sorted(permissions), "oneTime": True}

    def consume(self, *, code, product, installation_id):
        record = self._pending
        now = time.time()
        if record is None or now >= record["expiresAt"]:
            self._pending = None
            raise PairingDenied("Invalid or expired pairing code")
        match = (type(code) is str and _CODE.fullmatch(code) is not None
                 and type(product) is str and product == record["product"]
                 and type(installation_id) is str and
                 _INSTALL.fullmatch(installation_id) is not None
                 and hmac.compare_digest(
                     hashlib.sha256(code.encode("ascii")).digest(),
                     record["digest"]))
        if not match:
            if now >= record["cooldownUntil"]:
                record["attempts"] += 1
                if record["attempts"] >= 5:
                    record["attempts"] = 0
                    record["cooldownUntil"] = now + 30.0
            raise PairingDenied("Invalid or expired pairing code")
        # Consume BEFORE any credential issuance. A failed DB write requires a
        # fresh administrator code rather than allowing ambiguous replay.
        self._pending = None
        return {"username": record["username"],
                "permissions": record["permissions"],
                "approverUsername": record["approverUsername"],
                "approverRevision": record["approverRevision"],
                "approverLineage": record["approverLineage"],
                "product": record["product"], "installationId": installation_id}
