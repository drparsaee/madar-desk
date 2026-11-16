"""Windows per-file DACL gate for the hash-only Madar integration registry.

ONLY synthetic disposable directories; no actual APPDATA, LAN login or ledger.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import integration_key_registry as module
from integration_key_registry import IntegrationKeyRegistry


@unittest.skipUnless(os.name == "nt", "Real Windows security descriptors required")
class WindowsRegistryAclTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-registry-acl-qa-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.registry = IntegrationKeyRegistry(self.base / "lan-users.json")

    def issue(self, *, now=1000.0):
        return self.registry.issue(
            hashlib.sha256(b"synthetic-unknown-bearer").digest(),
            key_id="ik_" + "a" * 24,
            username="qa-user",
            permissions=frozenset({"read"}),
            password_revision=hashlib.sha256(b"synthetic-password-revision").digest(),
            expires_at=now + 3600., now=now, limit=512)

    def assert_private_actual_dacl(self):
        self.assertTrue(self.registry.path.is_file())
        self.assertFalse(self.registry.path.is_symlink())
        # An independent Windows ACL utility confirms that inherited ACEs are
        # absent, and no broad trustee has an explicit grant.
        result = subprocess.run(
            ["icacls.exe", str(self.registry.path)], capture_output=True,
            text=True, timeout=15, check=True)
        body = result.stdout
        self.assertNotIn("(I)", body)
        self.assertNotIn("Everyone:", body)
        self.assertNotIn("Authenticated Users:", body)
        self.assertNotIn("\\Users:", body)
        self.assertIn("SYSTEM:", body)
        self.assertIn("Administrators:", body)
        # Native DACL verification is stricter than icacls string matching:
        # exact three allow ACEs, current SID/SYSTEM/Admins and protected flag.
        with module._private_windows_guard(self.registry.path):
            pass

    def test_creates_private_registry_before_first_sqlite_write(self):
        actual_connect = sqlite3.connect
        calls = []
        def observing_connect(*args, **kwargs):
            self.assert_private_actual_dacl()
            calls.append(args)
            return actual_connect(*args, **kwargs)
        with patch.object(module.sqlite3, "connect", side_effect=observing_connect):
            workspace = self.issue()
        self.assertEqual(len(workspace), 32)
        self.assertEqual(len(calls), 1)
        self.assert_private_actual_dacl()
        self.assertNotIn(b"synthetic-unknown-bearer", self.registry.path.read_bytes())

    def test_read_only_legacy_v1_migrates_acl_not_database(self):
        # Historical v1 pre-pairing DB: created by SQLite with inherited ACL.
        with closing(sqlite3.connect(self.registry.path)) as db, db:
            db.execute("""CREATE TABLE integration_keys(
                secret_sha256 BLOB PRIMARY KEY,
                key_id TEXT NOT NULL UNIQUE,
                username TEXT NOT NULL,
                permissions TEXT NOT NULL,
                password_revision BLOB NOT NULL,
                expires_at REAL NOT NULL, revoked_at REAL)""")
            db.execute("""CREATE TABLE integration_key_audit(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id TEXT NOT NULL, action TEXT NOT NULL, at_epoch REAL NOT NULL)""")
            db.execute("PRAGMA user_version=1")
        before = hashlib.sha256(self.registry.path.read_bytes()).hexdigest()
        self.assertEqual(self.registry.connected_installs(now=1000.), [])
        self.assertEqual(hashlib.sha256(self.registry.path.read_bytes()).hexdigest(), before)
        self.assert_private_actual_dacl()
        workspace = self.issue()
        self.assertRegex(workspace, r"^[a-f0-9]{32}$")

    def test_existing_v1_rows_persist_after_acl_hardening_and_new_issue(self):
        old_digest = hashlib.sha256(b"synthetic-legacy-bearer").digest()
        old_revision = hashlib.sha256(b"synthetic-old-password").digest()
        with closing(sqlite3.connect(self.registry.path)) as db, db:
            db.execute("""CREATE TABLE integration_keys(
                secret_sha256 BLOB PRIMARY KEY, key_id TEXT NOT NULL UNIQUE,
                username TEXT NOT NULL, permissions TEXT NOT NULL,
                password_revision BLOB NOT NULL, expires_at REAL NOT NULL,
                revoked_at REAL)""")
            db.execute("""CREATE TABLE integration_key_audit(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, key_id TEXT NOT NULL,
                action TEXT NOT NULL, at_epoch REAL NOT NULL)""")
            db.execute("""INSERT INTO integration_keys VALUES(?,?,?,?,?,?,NULL)""", (
                old_digest, "ik_" + "b"*24, "original", '["read"]',
                old_revision, 5000.))
            db.execute("PRAGMA user_version=1")
        old = self.registry.lookup(old_digest, now=1000.)
        self.assertEqual(old["username"], "original")
        before = self.registry.path.read_bytes()
        self.assertTrue(before)
        self.assertRegex(self.issue(), r"^[a-f0-9]{32}$")
        self.assertEqual(self.registry.lookup(old_digest, now=1000.), old)
        self.assert_private_actual_dacl()

    def test_real_extra_world_read_ace_is_removed_not_inherited(self):
        self.issue()
        # Windows Everyone SID is stable across all locales.
        subprocess.run(["icacls.exe", str(self.registry.path),
                        "/grant", "*S-1-1-0:(R)"],
                       capture_output=True, text=True, timeout=15, check=True)
        current = subprocess.run(["icacls.exe", str(self.registry.path)],
                                 capture_output=True, text=True, timeout=15,
                                 check=True).stdout
        self.assertTrue("S-1-1-0" in current or "Everyone:" in current)
        record = self.registry.lookup(hashlib.sha256(
            b"synthetic-unknown-bearer").digest(), now=1000.)
        self.assertIsNotNone(record)
        self.assert_private_actual_dacl()

    def test_windows_acl_failure_prevents_any_sqlite_connection(self):
        self.registry.path.write_bytes(b"opaque-synthetic-unchanged")
        old = self.registry.path.read_bytes()
        with patch.object(module, "_private_windows_guard",
                          side_effect=PermissionError("synthetic DACL failure")), \
             patch.object(module.sqlite3, "connect") as connect:
            with self.assertRaisesRegex(PermissionError, "DACL failure"):
                self.registry.lookup(b"x" * 32, now=1000.)
            connect.assert_not_called()
        self.assertEqual(self.registry.path.read_bytes(), old)

    def test_rejects_hardlinked_registry(self):
        self.issue()
        linked = self.base / "synthetic-other-hardlink.sqlite3"
        try:
            os.link(self.registry.path, linked)
        except OSError:
            self.skipTest("Hardlinks unavailable for this temporary volume")
        with self.assertRaises(PermissionError):
            self.registry.lookup(hashlib.sha256(
                b"synthetic-unknown-bearer").digest(), now=1000.)

    def test_rejects_registry_symlink_without_modifying_target(self):
        dest = self.base / "original-target.sqlite3"
        dest.write_bytes(b"synthetic-target")
        try:
            self.registry.path.symlink_to(dest)
        except OSError:
            self.skipTest("Symlink creation unavailable on this Windows account")
        with self.assertRaises(PermissionError):
            self.issue()
        self.assertEqual(dest.read_bytes(), b"synthetic-target")

    def test_missing_read_does_not_create_registry(self):
        self.assertIsNone(self.registry.lookup(b"z"*32, now=1000.))
        self.assertEqual(self.registry.connected_installs(now=1000.), [])
        self.assertFalse(self.registry.path.exists())


if __name__ == "__main__":
    unittest.main()
