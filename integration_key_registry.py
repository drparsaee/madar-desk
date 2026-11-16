"""Durable, hash-only integration-key registry for the existing Madar HTTPS API.

This is not a pairing-code endpoint and never stores a usable bearer token.
The owning LAN service still authenticates administrators and checks current
user/password/project authorization on EVERY integration request.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import stat


_KEY_ID = re.compile(r"ik_[0-9a-f]{24}\Z")
_SCHEMA = 1


class IntegrationKeyRegistry:
    """Same-host durable revocation authority, independent of router lifetime."""

    def __init__(self, users_path):
        users_path = Path(users_path)
        if (not users_path.is_absolute() or users_path.is_symlink()
                or not users_path.parent.is_dir()
                or users_path.parent.is_symlink()):
            raise PermissionError("Trusted absolute LAN users path required")
        self.path = users_path.with_name(users_path.stem + ".integration-keys.sqlite3")

    def _check(self):
        if self.path.parent.is_symlink() or not self.path.parent.is_dir():
            raise PermissionError("Unsafe integration registry directory")
        if self.path.is_symlink():
            raise PermissionError("Linked integration registry refused")
        if self.path.exists():
            info = self.path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or getattr(info, "st_file_attributes", 0) & 0x400):
                raise PermissionError("Unsafe integration registry file")

    @contextmanager
    def _connect(self, *, writable):
        self._check()
        if not writable and not self.path.is_file():
            yield None
            return
        if writable:
            db = sqlite3.connect(self.path, timeout=8, isolation_level=None)
        else:
            db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True,
                                 timeout=8, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=8000")
            if writable:
                # DELETE journaling avoids leaving an uncheckpointed WAL file
                # outside ordinary user-profile backup tooling.
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version == 0:
                    db.execute("""CREATE TABLE integration_keys (
                        secret_sha256 BLOB PRIMARY KEY,
                        key_id TEXT NOT NULL UNIQUE,
                        username TEXT NOT NULL,
                        permissions TEXT NOT NULL,
                        password_revision BLOB NOT NULL,
                        expires_at REAL NOT NULL,
                        revoked_at REAL
                    )""")
                    db.execute("""CREATE TABLE integration_key_audit (
                        seq INTEGER PRIMARY KEY AUTOINCREMENT,
                        key_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        at_epoch REAL NOT NULL
                    )""")
                    db.execute("PRAGMA user_version=1")
                elif version != _SCHEMA:
                    raise RuntimeError("Unsupported integration registry schema")
            elif db.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA:
                raise RuntimeError("Unsupported integration registry schema")
            self._check()
            yield db
            if writable:
                db.execute("COMMIT")
                # Never persist bearer plaintext; only its SHA-256 digest.
                os.chmod(self.path, 0o600)
        except BaseException:
            if writable and db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def _validate_digest(value):
        if type(value) is not bytes or len(value) != 32:
            raise ValueError("Invalid integration credential digest")

    def issue(self, digest, *, key_id, username, permissions,
              password_revision, expires_at, now, limit):
        self._validate_digest(digest)
        self._validate_digest(password_revision)
        if (type(key_id) is not str or not _KEY_ID.fullmatch(key_id)
                or type(username) is not str or not username or len(username) > 128
                or type(permissions) is not frozenset or
                not permissions or not permissions.issubset({"read", "write"})
                or type(expires_at) is not float or expires_at <= now
                or type(limit) is not int or limit < 1):
            raise ValueError("Invalid integration key registration")
        with self._connect(writable=True) as db:
            active = db.execute(
                "SELECT COUNT(*) FROM integration_keys WHERE revoked_at IS NULL AND expires_at>?",
                (now,)).fetchone()[0]
            if active >= limit:
                raise RuntimeError("Integration key limit reached; revoke an old key")
            db.execute("INSERT INTO integration_keys VALUES(?,?,?,?,?,?,NULL)",
                       (digest, key_id, username, json.dumps(sorted(permissions)),
                        password_revision, expires_at))
            db.execute("INSERT INTO integration_key_audit(key_id,action,at_epoch) VALUES(?,?,?)",
                       (key_id, "issued", now))

    def lookup(self, digest, *, now):
        self._validate_digest(digest)
        with self._connect(writable=False) as db:
            if db is None:
                return None
            row = db.execute(
                "SELECT key_id,username,permissions,password_revision,expires_at "
                "FROM integration_keys WHERE secret_sha256=? AND revoked_at IS NULL AND expires_at>?",
                (digest, now)).fetchone()
        if row is None:
            return None
        key_id, username, raw_perms, revision, expiry = row
        try:
            perms = json.loads(raw_perms)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Corrupt integration permissions") from exc
        if (type(key_id) is not str or not _KEY_ID.fullmatch(key_id)
                or type(username) is not str or not username
                or type(perms) is not list or not perms
                or len(perms) != len(set(perms))
                or set(perms) - {"read", "write"}
                or not isinstance(revision, bytes) or len(revision) != 32
                or type(expiry) is not float or expiry <= now):
            raise RuntimeError("Corrupt integration registry entry")
        return {"keyId": key_id, "username": username,
                "permissions": frozenset(perms),
                "passwordRevision": revision, "expiresAt": expiry}

    def revoke(self, key_id, *, now):
        if type(key_id) is not str or not _KEY_ID.fullmatch(key_id):
            raise ValueError("Invalid integration key ID")
        with self._connect(writable=True) as db:
            changed = db.execute(
                "UPDATE integration_keys SET revoked_at=? WHERE key_id=? AND revoked_at IS NULL",
                (now, key_id)).rowcount
            if changed:
                db.execute(
                    "INSERT INTO integration_key_audit(key_id,action,at_epoch) VALUES(?,?,?)",
                    (key_id, "revoked", now))
            return changed == 1
