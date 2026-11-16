"""Durable, hash-only integration-key registry for the existing Madar HTTPS API.

This is not a pairing-code endpoint and never stores a usable bearer token.
The owning LAN service still authenticates administrators and checks current
user/password/project authorization on EVERY integration request.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import struct


_KEY_ID = re.compile(r"ik_[0-9a-f]{24}\Z")
_INSTALL_ID = re.compile(r"[0-9a-f]{32}\Z")
_SCHEMA = 1
_FILE_ALL_ACCESS = 0x001F01FF


@contextmanager
def _private_windows_guard(path):
    """Guard the actual file HANDLE while enforcing/verifying its protected DACL.

    A handle opened without FILE_SHARE_DELETE prevents a path swap between ACL
    verification and SQLite's own path-based open. No SQLite bytes are written
    until the DACL is verified. A Windows-only registry fails closed elsewhere.
    """
    if os.name != "nt":
        raise PermissionError("Private Windows registry ACL required")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    ptr = ctypes.c_void_p
    dword = wintypes.DWORD
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    advapi.OpenProcessToken.argtypes = (wintypes.HANDLE, dword, ctypes.POINTER(wintypes.HANDLE))
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = (wintypes.HANDLE, dword, ptr, dword,
                                            ctypes.POINTER(dword))
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = (ptr, ctypes.POINTER(ptr))
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (
        wintypes.LPCWSTR, dword, ctypes.POINTER(ptr), ctypes.POINTER(dword))
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    advapi.GetSecurityDescriptorDacl.argtypes = (
        ptr, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(ptr),
        ctypes.POINTER(wintypes.BOOL))
    advapi.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi.GetSecurityDescriptorControl.argtypes = (
        ptr, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(dword))
    advapi.GetSecurityDescriptorControl.restype = wintypes.BOOL
    advapi.GetSecurityInfo.argtypes = (
        wintypes.HANDLE, dword, dword, ctypes.POINTER(ptr),
        ctypes.POINTER(ptr), ctypes.POINTER(ptr), ctypes.POINTER(ptr),
        ctypes.POINTER(ptr))
    advapi.GetSecurityInfo.restype = dword
    advapi.SetSecurityInfo.argtypes = (
        wintypes.HANDLE, dword, dword, ptr, ptr, ptr, ptr)
    advapi.SetSecurityInfo.restype = dword
    advapi.GetAclInformation.argtypes = (ptr, ptr, dword, dword)
    advapi.GetAclInformation.restype = wintypes.BOOL
    advapi.GetAce.argtypes = (ptr, dword, ctypes.POINTER(ptr))
    advapi.GetAce.restype = wintypes.BOOL
    kernel.CreateFileW.argtypes = (
        wintypes.LPCWSTR, dword, dword, ptr, dword, dword, wintypes.HANDLE)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = (ptr,)
    kernel.LocalFree.restype = ptr

    def failed(what):
        raise PermissionError(what + " (Win32 " + str(ctypes.get_last_error()) + ")")

    def sid_string(sid):
        value = ptr()
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(value)):
            failed("Cannot inspect Windows ACL SID")
        try:
            return ctypes.wstring_at(value)
        finally:
            kernel.LocalFree(value)

    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008,
                                  ctypes.byref(token)):
        failed("Cannot identify registry owner principal")
    try:
        length = dword()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(length))
        if not 16 <= length.value <= 65536:
            raise PermissionError("Invalid current Windows token identity")
        buf = ctypes.create_string_buffer(length.value)
        if not advapi.GetTokenInformation(token, 1, buf, length,
                                          ctypes.byref(length)):
            failed("Cannot read current Windows token identity")
        current_sid = sid_string(ctypes.cast(buf, ctypes.POINTER(ptr))[0])
    finally:
        kernel.CloseHandle(token)
    if not re.fullmatch(r"S-1-(?:[0-9]+-)+[0-9]+", current_sid):
        raise PermissionError("Invalid current Windows SID")
    trusted = {current_sid, "S-1-5-18", "S-1-5-32-544"}

    handle = kernel.CreateFileW(str(path), 0x00020000 | 0x00040000,
                                0x00000001 | 0x00000002, None, 3,
                                0x00200000, None)
    if handle == wintypes.HANDLE(-1).value:
        failed("Cannot acquire non-deletable registry security handle")
    try:
        # GetSecurityInfo's returned descriptor owns the ACL and owner pointers.
        def inspect():
            owner, acl, sd = ptr(), ptr(), ptr()
            result = advapi.GetSecurityInfo(
                handle, 1, 0x00000001 | 0x00000004,
                ctypes.byref(owner), None, ctypes.byref(acl), None,
                ctypes.byref(sd))
            if result:
                raise PermissionError("Registry DACL inspection failed (Win32 " +
                                      str(result) + ")")
            try:
                if not owner or sid_string(owner) not in trusted or not acl:
                    return False
                controls, revision = wintypes.WORD(), dword()
                if not advapi.GetSecurityDescriptorControl(
                        sd, ctypes.byref(controls), ctypes.byref(revision)):
                    failed("Cannot inspect registry ACL inheritance")
                if not controls.value & 0x1000:  # SE_DACL_PROTECTED
                    return False
                class _AclInfo(ctypes.Structure):
                    _fields_ = [("count", dword), ("used", dword), ("free", dword)]
                info = _AclInfo()
                if not advapi.GetAclInformation(acl, ctypes.byref(info),
                                               ctypes.sizeof(info), 2):
                    failed("Cannot enumerate registry ACL")
                observed = set()
                for index in range(info.count):
                    ace = ptr()
                    if not advapi.GetAce(acl, index, ctypes.byref(ace)):
                        failed("Cannot inspect registry ACE")
                    kind, flags, size, rights = struct.unpack(
                        "<BBHI", ctypes.string_at(ace, 8))
                    if (kind != 0 or flags != 0 or size < 16 or
                            rights != _FILE_ALL_ACCESS):
                        return False
                    actor = sid_string(ptr(ace.value + 8))
                    if actor not in trusted or actor in observed:
                        return False
                    observed.add(actor)
                return observed == trusted
            finally:
                kernel.LocalFree(sd)

        if not inspect():
            descriptor = ptr()
            # An exact, protected ACL. No inherited, Everyone, Users or other
            # explicit trustees survive, even from a pre-existing SQLite file.
            sddl = ("D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;" +
                    current_sid + ")")
            if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                    sddl, 1, ctypes.byref(descriptor), None):
                failed("Cannot build protected registry DACL")
            try:
                present, acl, defaulted = wintypes.BOOL(), ptr(), wintypes.BOOL()
                if not advapi.GetSecurityDescriptorDacl(
                        descriptor, ctypes.byref(present), ctypes.byref(acl),
                        ctypes.byref(defaulted)) or not present.value or not acl:
                    failed("Cannot extract protected registry DACL")
                result = advapi.SetSecurityInfo(
                    handle, 1, 0x00000004 | 0x80000000, None, None, acl, None)
                if result:
                    raise PermissionError("Cannot secure registry DACL (Win32 " +
                                          str(result) + ")")
            finally:
                kernel.LocalFree(descriptor)
        if not inspect():
            raise PermissionError("Registry DACL is not private and protected")
        yield handle
    finally:
        kernel.CloseHandle(handle)


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
        for part in (self.path.parent, *self.path.parent.parents):
            if (part.is_symlink() or not part.is_dir() or
                    getattr(part.lstat(), "st_file_attributes", 0) & 0x400):
                raise PermissionError("Unsafe integration registry directory")
        if os.path.lexists(self.path):
            info = self.path.lstat()
            if (self.path.is_symlink() or not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or getattr(info, "st_file_attributes", 0) & 0x400):
                raise PermissionError("Unsafe integration registry file")

    @contextmanager
    def _connect(self, *, writable):
        self._check()
        if not writable and not os.path.lexists(self.path):
            yield None
            return
        if writable and not os.path.lexists(self.path):
            # Create an EMPTY unique file first; SQLite may not create a file
            # with inherited Windows ACLs and then write private data into it.
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR |
                             getattr(os, "O_BINARY", 0), 0o600)
            except FileExistsError:
                # A concurrently created file must pass the same ACL checks.
                pass
            else:
                os.close(fd)
        self._check()
        with _private_windows_guard(self.path):
            self._check()
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
                    # Additive v1 tables: legacy API keys remain valid, but new
                    # one-time pairing can associate them with a stable install.
                    db.execute("""CREATE TABLE IF NOT EXISTS paired_installs (
                    key_id TEXT PRIMARY KEY,
                    product TEXT NOT NULL,
                    installation_id TEXT NOT NULL,
                    paired_at REAL NOT NULL,
                    FOREIGN KEY(key_id) REFERENCES integration_keys(key_id)
                    )""")
                    db.execute("""CREATE TABLE IF NOT EXISTS registry_identity (
                    name TEXT PRIMARY KEY, value TEXT NOT NULL
                    )""")
                    if db.execute("SELECT value FROM registry_identity WHERE name='workspace'").fetchone() is None:
                        db.execute("INSERT INTO registry_identity(name,value) VALUES('workspace',?)",
                                   (secrets.token_hex(16),))
                elif db.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA:
                    raise RuntimeError("Unsupported integration registry schema")
                self._check()
                yield db
                if writable:
                    db.execute("COMMIT")
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
              password_revision, expires_at, now, limit,
              client_product=None, installation_id=None):
        self._validate_digest(digest)
        self._validate_digest(password_revision)
        if (type(key_id) is not str or not _KEY_ID.fullmatch(key_id)
                or type(username) is not str or not username or len(username) > 128
                or type(permissions) is not frozenset or
                not permissions or not permissions.issubset({"read", "write"})
                or type(expires_at) is not float or expires_at <= now
                or type(limit) is not int or limit < 1):
            raise ValueError("Invalid integration key registration")
        pairing = client_product is not None or installation_id is not None
        if pairing and (client_product not in {"TARAZ", "RADAR"} or
                        type(installation_id) is not str or
                        not _INSTALL_ID.fullmatch(installation_id)):
            raise ValueError("Invalid paired product or installation identity")
        with self._connect(writable=True) as db:
            if pairing:
                # Successful re-pair rotates credentials for this installation.
                # The old key is revoked atomically with inserting the new one.
                prior = db.execute(
                    "SELECT key_id FROM paired_installs WHERE product=? AND installation_id=?",
                    (client_product, installation_id)).fetchall()
                for (prior_key,) in prior:
                    db.execute("UPDATE integration_keys SET revoked_at=? "
                               "WHERE key_id=? AND revoked_at IS NULL", (now, prior_key))
                    db.execute("INSERT INTO integration_key_audit(key_id,action,at_epoch) "
                               "VALUES(?,?,?)", (prior_key, "rotated", now))
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
            if pairing:
                db.execute("INSERT INTO paired_installs VALUES(?,?,?,?)",
                           (key_id, client_product, installation_id, now))
            workspace = db.execute("SELECT value FROM registry_identity WHERE name='workspace'").fetchone()[0]
            if type(workspace) is not str or not _INSTALL_ID.fullmatch(workspace):
                raise RuntimeError("Corrupt integration workspace identity")
            return workspace

    def connected_installs(self, *, now):
        """Metadata only; never return bearer material or its digest."""
        with self._connect(writable=False) as db:
            if db is None:
                return []
            # Existing V1 credential databases predate pairings and may be
            # read before any subsequent writable issuance/migration. Do not
            # create/modify schema during a metadata-only read.
            has_links = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paired_installs'"
            ).fetchone()
            if not has_links:
                return []
            rows = db.execute("""SELECT p.key_id,p.product,p.installation_id,
                                      p.paired_at,k.username,k.permissions,
                                      k.expires_at,k.revoked_at
                FROM paired_installs AS p JOIN integration_keys AS k
                ON p.key_id=k.key_id ORDER BY p.paired_at DESC LIMIT 512""").fetchall()
        return [{"keyId": item[0], "product": item[1],
                 "installationId": item[2], "pairedAt": item[3],
                 "username": item[4], "permissions": json.loads(item[5]),
                 "expiresAt": int(item[6]),
                 "status": "revoked" if item[7] is not None else
                 "expired" if item[6] <= now else "active"} for item in rows]

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
