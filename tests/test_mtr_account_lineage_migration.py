"""Isolated host-only legacy lineage migration security and recovery tests.

Only disposable temp users.json and temporary SQLite E2 outbox records.
No LAN listener, production profiles, real users or finance posting.
"""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from lan import LanService, make_account
from mtr_account_lineage import principal_actor_id
from mtr_account_lineage_migration import (
    AccountLineageMigrationDenied,
    AccountLineageMigrationUncertain,
    migrate_legacy_account_lineages,
)
from mtr_host_request_store import HostRequestStore, TrustedPrincipal


PASSWORD = "synthetic-host-password-1234567890"
PROJECT = "project-synthetic-01"


class SyntheticBridge:
    def __init__(self):
        self._lock = threading.RLock()
        self.state = {
            "projects": [{"id": PROJECT}],
            "tasks": [],
            "boards": [],
        }

    def getState(self):
        return deepcopy(self.state)

    def saveState(self, state):
        self.state = deepcopy(state)


class AccountLineageMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mtr-e2-lineage-migration-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        variables = ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP",
                     "HOME", "USERPROFILE")
        patcher = patch.dict(
            os.environ, {key: str(self.root) for key in variables},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.path = self.root / "users.json"
        self.backup = self.root / "users.before-lineage.bak"
        self.bridge = SyntheticBridge()
        owner = make_account("owner", PASSWORD, "admin")
        owner["displayRole"] = "superadmin"
        editor = make_account("legacy", PASSWORD, "editor", [PROJECT])
        editor.pop("accountLineage")
        editor["displayRole"] = "editor"
        editor["financeEdit"] = True
        existing = make_account("established", PASSWORD, "editor", [PROJECT])
        existing["displayRole"] = "editor"
        self.accounts = {
            "owner": owner,
            "legacy": editor,
            "established": existing,
        }
        self.path.write_text(
            json.dumps(self.accounts, sort_keys=True),
            encoding="utf-8",
        )
        self.service = LanService(self.bridge, self.path, bind="127.0.0.1", port=0)
        self.admin_token = self.service.authenticate("owner", PASSWORD)["token"]

    def migrate(self, **changes):
        arguments = {
            "service": self.service, "admin_token": self.admin_token,
            "backup_path": self.backup,
        }
        arguments.update(changes)
        return migrate_legacy_account_lineages(**arguments)

    def persisted(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def update_fixture(self, mutate):
        accounts = deepcopy(self.service.users)
        mutate(accounts)
        self.service.users = accounts
        self.service._store_users(accounts)

    def test_admin_migrates_only_missing_lineage_after_verified_backup(self):
        exact_original = self.path.read_bytes()
        before = deepcopy(self.service.users)
        existing_lineage = before["established"]["accountLineage"]
        admin_lineage = before["owner"]["accountLineage"]
        actual_publish = self.service._publish_users
        seen = []

        def observe_publish(updated):
            self.assertEqual(self.backup.read_bytes(), exact_original)
            seen.append(hashlib.sha256(self.backup.read_bytes()).hexdigest())
            self.assertEqual(self.path.read_bytes(), exact_original)
            actual_publish(updated)

        with patch.object(self.service, "_publish_users",
                          side_effect=observe_publish) as publish:
            result = self.migrate()
        publish.assert_called_once()
        self.assertEqual(result["migratedAccounts"], 1)
        self.assertEqual(result["unchangedAccounts"], 2)
        self.assertTrue(result["backupCreated"])
        self.assertTrue(result["registryPublished"])
        self.assertFalse(result["legacyOutboxRemapped"])
        self.assertEqual(result["backupSha256"],
                         hashlib.sha256(exact_original).hexdigest())
        self.assertEqual(seen, [result["backupSha256"]])
        self.assertEqual(self.backup.read_bytes(), exact_original)
        after = self.persisted()
        self.assertEqual(after, self.service.users)
        self.assertEqual(after["owner"]["accountLineage"], admin_lineage)
        self.assertEqual(after["established"]["accountLineage"], existing_lineage)
        self.assertEqual(
            {key: val for key, val in after["legacy"].items()
             if key != "accountLineage"}, before["legacy"],
        )
        self.assertRegex(after["legacy"]["accountLineage"], r"\A[0-9a-f]{32}\Z")
        self.assertEqual(len({
            item["accountLineage"] for item in after.values()
        }), 3)
        self.assertNotIn("accountLineage", self.service._public_user(
            after["legacy"]))

    def test_second_run_is_idempotent_without_new_backup(self):
        self.migrate()
        first_lineage = self.service.users["legacy"]["accountLineage"]
        persisted = self.path.read_bytes()
        with patch.object(self.service, "_publish_users") as publish:
            again = self.migrate()
        publish.assert_not_called()
        self.assertEqual(again, {
            "migratedAccounts": 0, "unchangedAccounts": 3,
            "backupCreated": False, "registryPublished": False,
            "legacyOutboxRemapped": False,
        })
        self.assertEqual(self.path.read_bytes(), persisted)
        self.assertEqual(
            self.service.users["legacy"]["accountLineage"], first_lineage)
        self.assertTrue(self.backup.is_file())

    def test_no_admin_no_public_or_client_claim_migration(self):
        user_token = self.service.authenticate("legacy", PASSWORD)["token"]
        original = self.path.read_bytes()
        for invalid in (
            "", "random-client-token", user_token, None, True,
        ):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises((PermissionError, AccountLineageMigrationDenied)):
                    self.migrate(admin_token=invalid)
        with self.assertRaises(AccountLineageMigrationDenied):
            migrate_legacy_account_lineages(
                object(), admin_token=self.admin_token, backup_path=self.backup)
        with self.assertRaises(ValueError):
            self.service.upsert_user(self.admin_token, {
                "username": "legacy",
                "accountLineage": "f" * 32,
            })
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.backup.exists())

    def test_bad_and_duplicate_existing_lineage_fail_closed_without_backup(self):
        for malformed in (
            None, "", "A" * 32, "0" * 32, "c" * 31, 123, ["d" * 32],
            self.accounts["owner"]["accountLineage"],
        ):
            with self.subTest(lineage=repr(malformed)):
                self.update_fixture(
                    lambda accounts: accounts["legacy"].update({
                        "accountLineage": malformed,
                    })
                )
                original = self.path.read_bytes()
                with self.assertRaises(AccountLineageMigrationDenied):
                    self.migrate()
                self.assertEqual(self.path.read_bytes(), original)
                self.assertFalse(self.backup.exists())
                self.update_fixture(
                    lambda accounts: accounts["legacy"].pop("accountLineage")
                )

    def test_generated_collision_and_bad_rng_are_denied_before_backup(self):
        original = self.path.read_bytes()
        existing = self.service.users["owner"]["accountLineage"]
        for minted in (existing, "BAD", "0" * 32):
            with self.subTest(minted=minted):
                with patch("mtr_account_lineage_migration.new_account_lineage",
                           return_value=minted):
                    with self.assertRaises(AccountLineageMigrationDenied):
                        self.migrate()
        self.assertFalse(self.backup.exists())
        self.assertEqual(self.path.read_bytes(), original)

    def test_registry_mismatch_and_duplicate_json_fail_before_backup(self):
        initial = self.path.read_bytes()
        mutated = deepcopy(self.service.users)
        mutated["legacy"]["role"] = "viewer"
        self.path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(AccountLineageMigrationDenied):
            self.migrate()
        self.assertFalse(self.backup.exists())
        self.path.write_bytes(initial)
        # A duplicate top-level username is not a valid authoritative registry,
        # even if the usual JSON loader would silently pick its final value.
        duplicate = (
            b'{"owner":' + json.dumps(self.accounts["owner"]).encode("utf-8") +
            b',"owner":' + json.dumps(self.accounts["owner"]).encode("utf-8") +
            b"}"
        )
        self.path.write_bytes(duplicate)
        with self.assertRaises(AccountLineageMigrationDenied):
            self.migrate()
        self.assertFalse(self.backup.exists())
        self.path.write_bytes(initial)
        self.service.users["legacy"]["role"] = "viewer"
        with self.assertRaises(AccountLineageMigrationDenied):
            self.migrate()
        self.assertFalse(self.backup.exists())

    def test_backup_existing_or_unsafe_path_prevents_publication(self):
        original = self.path.read_bytes()
        self.backup.write_bytes(b"do not overwrite")
        with self.assertRaises(FileExistsError):
            self.migrate()
        self.assertEqual(self.backup.read_bytes(), b"do not overwrite")
        self.assertEqual(self.path.read_bytes(), original)
        self.backup.unlink()
        for target in (
            self.path,
            self.root.parent / "external-backup.bak",
            Path("relative.bak"),
            self.root / "missing" / "backup.bak",
        ):
            with self.subTest(target=target):
                with self.assertRaises((PermissionError, FileExistsError)):
                    self.migrate(backup_path=target)
                self.assertEqual(self.path.read_bytes(), original)

    def test_backup_fsync_failure_aborts_before_any_publish(self):
        original = self.path.read_bytes()
        with patch("mtr_account_lineage_migration.os.fsync",
                   side_effect=OSError("synthetic fsync sabotage")), patch.object(
                       self.service, "_publish_users") as publisher:
            with self.assertRaises(OSError):
                self.migrate()
        publisher.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.service.users, self.accounts)
        # A partially created backup must never be treated as proof to retry
        # publication. Operator chooses a new backup path after inspection.
        self.assertTrue(self.backup.exists())
        with self.assertRaises(FileExistsError):
            self.migrate()

    def test_backup_readback_sabotage_prevents_publication(self):
        original = self.path.read_bytes()
        raw_read = Path.read_bytes

        def sabotage_read(path):
            if path == self.backup:
                return b"wrong backup data"
            return raw_read(path)

        with patch.object(Path, "read_bytes", autospec=True,
                          side_effect=sabotage_read), patch.object(
                              self.service, "_publish_users") as publisher:
            with self.assertRaises(AccountLineageMigrationDenied):
                self.migrate()
        publisher.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.backup.read_bytes(), original)

    def test_publish_failure_with_successful_compensation_preserves_original(self):
        original = self.path.read_bytes()
        actual_store = self.service._store_users
        writes = []

        def publish_then_fail(users=None):
            writes.append(1)
            actual_store(users)
            if len(writes) == 1:
                raise OSError("synthetic error after file publication")

        with patch.object(self.service, "_store_users",
                          side_effect=publish_then_fail):
            with self.assertRaisesRegex(OSError, "synthetic error"):
                self.migrate()
        self.assertEqual(len(writes), 2)
        self.assertEqual(self.path.read_bytes() != b"", True)
        self.assertEqual(self.persisted(), self.accounts)
        self.assertEqual(self.service.users, self.accounts)
        self.assertEqual(self.backup.read_bytes(), original)
        self.assertFalse(self.service._delete_recovery_required)

    def test_failed_save_and_rollback_fails_closed_without_masking_outcome(self):
        original = self.path.read_bytes()
        actual_store = self.service._store_users
        calls = 0

        def persist_but_raise(users=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                actual_store(users)
            # A failed compensation did NOT write the original account data.
            raise OSError("synthetic failure after durable publication")

        with patch.object(self.service, "_store_users",
                          side_effect=persist_but_raise):
            with self.assertRaises(AccountLineageMigrationUncertain) as result:
                self.migrate()
        self.assertIn("ambiguous", str(result.exception))
        self.assertEqual(calls, 2)
        self.assertTrue(self.service._delete_recovery_required)
        self.assertNotEqual(self.persisted(), self.accounts)
        self.assertEqual(self.service.users, self.accounts)
        self.assertEqual(self.backup.read_bytes(), original)
        with self.assertRaises(PermissionError):
            self.service.account_for(self.admin_token)
        # The verified backup still contains the entire original private data.
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         hashlib.sha256(self.backup.read_bytes()).hexdigest())

    def test_delete_and_recreate_same_username_gets_unrelated_generation(self):
        self.migrate()
        before = principal_actor_id(self.service.users["legacy"])
        self.service.delete_user(self.admin_token, "legacy")
        self.assertNotIn("legacy", self.service.users)
        self.service.upsert_user(self.admin_token, {
            "username": "legacy", "role": "editor",
            "password": PASSWORD, "projects": [PROJECT],
            "financeEdit": True,
        })
        self.assertIn("legacy", self.service.users)
        self.assertNotEqual(principal_actor_id(self.service.users["legacy"]), before)
        self.assertNotIn("accountLineage",
                         self.service._public_user(self.service.users["legacy"]))

    def test_old_username_outbox_stays_quarantined_new_request_is_possible(self):
        database = HostRequestStore(self.root / "synthetic-outbox.sqlite3")
        request_id = uuid.uuid4().hex
        legacy = TrustedPrincipal(
            user_id="legacy", org_id="synthetic-org",
            session_id="synthetic-original-session",
            role="editor", project_ids=frozenset({PROJECT}),
            permissions=frozenset({"mtr.prepare", "mtr.manual_send", "mtr.read"}),
            authenticated=True, session_valid=True,
        )
        original_proposal = {
            "id": request_id, "schema": 1, "source": "madar",
            "taskId": "t-legacy", "projectId": PROJECT, "title": "old",
            "createdUtc": "2026-11-10T00:00:00+00:00",
        }
        database.prepare_request(
            principal=legacy, request_id=request_id,
            payload=original_proposal, base_revision=4,
            current_server_revision=4, prepare_key="synthetic-prepare-legacy",
            explicit_manual_action=True,
        )
        with closing(sqlite3.connect(database.path)) as connection:
            old_actor = connection.execute(
                "SELECT actor_id FROM requests WHERE request_id=?", (request_id,)
            ).fetchone()[0]
        self.assertEqual(old_actor, "legacy")
        self.migrate()
        current = principal_actor_id(self.service.users["legacy"])
        self.assertNotEqual(current, "legacy")
        new_principal = TrustedPrincipal(
            user_id=current, org_id="synthetic-org",
            session_id="synthetic-original-session",
            role="editor", project_ids=frozenset({PROJECT}),
            permissions=frozenset({"mtr.prepare", "mtr.manual_send", "mtr.read"}),
            authenticated=True, session_valid=True,
        )
        with self.assertRaises(PermissionError):
            database.request_snapshot(
                principal=new_principal, request_id=request_id,
                expected_base_revision=4,
            )
        fresh_id = uuid.uuid4().hex
        fresh = database.prepare_request(
            principal=new_principal, request_id=fresh_id,
            payload={**original_proposal, "id": fresh_id, "title": "fresh"},
            base_revision=5, current_server_revision=5,
            prepare_key="synthetic-prepare-fresh", explicit_manual_action=True,
        )
        self.assertEqual(fresh["requestId"], fresh_id)
        with closing(sqlite3.connect(database.path)) as connection:
            actors = dict(connection.execute(
                "SELECT request_id,actor_id FROM requests").fetchall())
        self.assertEqual(actors[request_id], "legacy")
        self.assertEqual(actors[fresh_id], current)


if __name__ == "__main__":
    unittest.main()
