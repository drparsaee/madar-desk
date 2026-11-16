"""Explicit host-administrator binding of a paired Taraz installation to a company.

This is a narrow authorization prerequisite for future counterparties mailbox
operations, NOT an automatic discovery mechanism and NOT financial authority.
The reported company identifier is NOT trusted from an unauthenticated peer:
an administrator must approve it out-of-band after a verified pairing.

No second HTTP listener, business-data store, direct accounting SQL, or
browser-controllable authorization flag is created here.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import ssl
import time

from integration_key_registry import IntegrationKeyRegistry


_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_KEY_ID = re.compile(r"ik_[0-9a-f]{24}\Z")


class CompanyGrantDenied(PermissionError):
    """Current host authorization or an explicit peer-company grant is missing."""


class IntegrationCompanyGrant:
    """Native host-only API; never mount as unauthenticated REST operation."""

    def __init__(self, service, registry: IntegrationKeyRegistry):
        if (type(registry) is not IntegrationKeyRegistry or
                not all(hasattr(service, item) for item in
                            ("account_for", "users", "lock", "server", "certfile", "keyfile"))):
            raise TypeError("Trusted existing LAN service and credential registry required")
        self.service = service
        self.registry = registry

    def _require_host(self):
        server = getattr(self.service, "server", None)
        if not (self.service.certfile and self.service.keyfile and server is not None
                and isinstance(server.socket, ssl.SSLSocket)):
            raise CompanyGrantDenied("Active trusted HTTPS host required")

    def _require_admin(self, token):
        self._require_host()
        actor = self.service.account_for(token)
        if actor.get("role") != "admin":
            raise CompanyGrantDenied("Current LAN administrator required")
        return actor

    @staticmethod
    def _validate(key_id, company_id, installation_id):
        if (type(key_id) is not str or not _KEY_ID.fullmatch(key_id) or
                type(company_id) is not str or not _HEX32.fullmatch(company_id) or
                type(installation_id) is not str or not _HEX32.fullmatch(installation_id)):
            raise ValueError("Invalid paired company and installation references")

    @staticmethod
    def _create_table(db):
        db.execute("""CREATE TABLE IF NOT EXISTS paired_company_grants (
            peer_key_id TEXT NOT NULL PRIMARY KEY,
            company_id TEXT NOT NULL,
            installation_id TEXT NOT NULL,
            approved_by TEXT NOT NULL,
            granted_at REAL NOT NULL,
            revoked_at REAL,
            FOREIGN KEY(peer_key_id) REFERENCES integration_keys(key_id)
        )""")

    def approve(self, admin_token, *, key_id, company_id, installation_id,
                manual_confirmation):
        """Bind a verified paired Taraz key to ONE operator-approved company.

        The administrator must independently compare the Taraz registered
        company ID shown in Taraz with this proposed mapping. A client JSON
        flag cannot substitute for the native host action and current session.
        """
        self._validate(key_id, company_id, installation_id)
        if manual_confirmation is not True:
            raise CompanyGrantDenied("Explicit administrator approval required")
        with self.service.lock:
            admin = self._require_admin(admin_token)
            with self.registry._connect(writable=True) as db:
                matched = db.execute("""SELECT p.product,p.installation_id,
                       k.username,k.password_revision,k.expires_at,k.revoked_at
                    FROM paired_installs p JOIN integration_keys k ON p.key_id=k.key_id
                    WHERE p.key_id=?""", (key_id,)).fetchone()
                if (matched is None or matched[0] != "TARAZ" or
                        matched[1] != installation_id or matched[5] is not None or
                        matched[4] <= time.time()):
                    raise CompanyGrantDenied("Active verified Taraz pairing required")
                account = self.service.users.get(matched[2])
                if (not account or not hmac.compare_digest(
                        hashlib.sha256(account["passwordHash"].encode("utf-8")).digest(),
                        matched[3])):
                    raise CompanyGrantDenied("Linked account is no longer authorized")
                self._create_table(db)
                existing = db.execute("""SELECT company_id,installation_id,revoked_at
                    FROM paired_company_grants WHERE peer_key_id=?""",
                    (key_id,)).fetchone()
                if existing is not None:
                    if existing[0] == company_id and existing[1] == installation_id and existing[2] is None:
                        return {"approved": True, "alreadyApproved": True,
                                "companyId": company_id, "installationId": installation_id}
                    raise CompanyGrantDenied("A previous grant must be reviewed and revoked")
                now = time.time()
                admin_identity = admin.get("accountLineage") or admin["username"]
                db.execute("""INSERT INTO paired_company_grants
                    (peer_key_id,company_id,installation_id,approved_by,granted_at,revoked_at)
                    VALUES(?,?,?,?,?,NULL)""",
                    (key_id, company_id, installation_id, admin_identity, now))
                db.execute("""INSERT INTO integration_key_audit(key_id,action,at_epoch)
                    VALUES(?,?,?)""", (key_id, "company_binding_approved", now))
                return {"approved": True, "alreadyApproved": False,
                        "companyId": company_id, "installationId": installation_id}

    def revoke(self, admin_token, *, key_id, company_id, installation_id):
        """Remove a company data grant without resetting unrelated peers."""
        self._validate(key_id, company_id, installation_id)
        with self.service.lock:
            self._require_admin(admin_token)
            with self.registry._connect(writable=True) as db:
                self._create_table(db)
                now = time.time()
                changed = db.execute("""UPDATE paired_company_grants
                    SET revoked_at=? WHERE peer_key_id=? AND company_id=?
                    AND installation_id=? AND revoked_at IS NULL""",
                    (now, key_id, company_id, installation_id)).rowcount
                if changed:
                    db.execute("""INSERT INTO integration_key_audit(key_id,action,at_epoch)
                        VALUES(?,?,?)""", (key_id, "company_binding_revoked", now))
                return {"revoked": changed == 1}

    def verified(self, *, key_id, company_id, installation_id) -> bool:
        """Narrow grant check only; caller MUST separately authenticate HTTPS peer.

        This does not establish current Madar card/project access. The router
        and mailbox authorizer MUST recheck actor rights on every operation.
        """
        self._validate(key_id, company_id, installation_id)
        with self.service.lock:
            self._require_host()
            with self.registry._connect(writable=False) as db:
                if db is None:
                    return False
                present = db.execute("""SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name='paired_company_grants'""").fetchone()
                if not present:
                    return False
                record = db.execute("""SELECT k.username,k.password_revision
                    FROM paired_company_grants g
                    JOIN integration_keys k ON k.key_id=g.peer_key_id
                    JOIN paired_installs p ON p.key_id=k.key_id
                    WHERE g.peer_key_id=? AND g.company_id=?
                      AND g.installation_id=? AND g.revoked_at IS NULL
                      AND k.revoked_at IS NULL AND k.expires_at>?
                      AND p.product='TARAZ' AND p.installation_id=?""",
                    (key_id, company_id, installation_id, time.time(),
                     installation_id)).fetchone()
                if record is None:
                    return False
                account = self.service.users.get(record[0])
                return bool(account and hmac.compare_digest(
                    hashlib.sha256(account["passwordHash"].encode("utf-8")).digest(),
                    record[1]))


__all__ = ["CompanyGrantDenied", "IntegrationCompanyGrant"]
