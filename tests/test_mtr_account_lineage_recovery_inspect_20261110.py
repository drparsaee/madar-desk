"""Disposable, read-only E2 lineage restart/recovery inspection tests.

Every path is explicit and under TemporaryDirectory. No LanService, login,
server, client, real account, network, migration, ledger or restore is used.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mtr_account_lineage_recovery_inspect as inspector
from mtr_account_lineage_recovery_inspect import inspect_account_lineage_recovery


OWNER_LINEAGE = "1" * 32
EXISTING_LINEAGE = "2" * 32
MIGRATED_LINEAGE = "3" * 32
SYNTHETIC_HASH = "a" * 32 + ":" + "b" * 64


def _account(name: str, *, role="editor", lineage=None):
    result = {
        "username": name,
        "passwordHash": SYNTHETIC_HASH,
        "role": role, "projects": ["test-project"],
        "financeEdit": role == "editor",
        "financeView": role == "admin",
        "displayRole": "synthetic",
    }
    if lineage is not None:
        result["accountLineage"] = lineage
    return result


class RestartRecoveryInspectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mtr-e2-restart-inspection-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.current_path = self.root / "users.json"
        self.backup_path = self.root / "users.before-lineage.bak"
        self.original = {
            "owner": _account("owner", role="admin", lineage=OWNER_LINEAGE),
            "legacy": _account("legacy"),
            "established": _account("established", lineage=EXISTING_LINEAGE),
        }
        self.updated = deepcopy(self.original)
        self.updated["legacy"]["accountLineage"] = MIGRATED_LINEAGE
        self.write_pair()

    def write_json(self, path: Path, value: dict) -> None:
        path.write_bytes(json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8"))

    def write_pair(self, *, before=None, after=None):
        self.write_json(self.backup_path,
                        self.original if before is None else before)
        self.write_json(self.current_path,
                        self.updated if after is None else after)

    def backup_digest(self):
        return hashlib.sha256(self.backup_path.read_bytes()).hexdigest()

    def inspect(self, **updates):
        params = {
            "registry_path": self.current_path,
            "backup_path": self.backup_path,
        }
        if "expected_backup_sha256" not in updates:
            params["expected_backup_sha256"] = self.backup_digest()
        if "expected_backup_size" not in updates:
            params["expected_backup_size"] = self.backup_path.stat().st_size
        params.update(updates)
        return inspect_account_lineage_recovery(**params)

    def assert_class(self, status, name, reason=None):
        self.assertEqual(status["classification"], name, status)
        if reason is not None:
            self.assertEqual(status["reason"], reason)
        self.assertIs(status["readOnly"], True)
        self.assertIs(status["automaticRestoreAllowed"], False)
        self.assertIs(status["safeToResumeHost"], False)
        self.assertIs(status["manualOperatorReviewRequired"], True)
        self.assertIs(status["backupProvenanceCryptographicallyProven"], False)
        self.assertNotIn("password", repr(status).lower())
        self.assertNotIn(SYNTHETIC_HASH, repr(status))
        self.assertNotIn(OWNER_LINEAGE, repr(status))
        self.assertNotIn(str(self.root), repr(status))

    def test_matching_original_backup_and_exact_lineage_only_current(self):
        before = (self.backup_path.read_bytes(), self.backup_path.stat().st_mtime_ns)
        after = (self.current_path.read_bytes(), self.current_path.stat().st_mtime_ns)
        outcome = self.inspect()
        self.assert_class(outcome, "VERIFIED_CONSISTENT",
                          "structurally_exact_lineage_only_migration")
        self.assertEqual(outcome["accountCount"], 3)
        self.assertEqual(outcome["backupMissingLineageCount"], 1)
        self.assertEqual(outcome["currentMissingLineageCount"], 0)
        self.assertEqual(outcome["addedLineageCount"], 1)
        self.assertTrue(outcome["backupDigestMatchesExpected"])
        self.assertEqual(outcome["backupSizeBytes"], len(before[0]))
        self.assertEqual(outcome["registrySizeBytes"], len(after[0]))
        self.assertEqual(outcome["backupSha256"], self.backup_digest())
        self.assertEqual((self.backup_path.read_bytes(),
                          self.backup_path.stat().st_mtime_ns), before)
        self.assertEqual((self.current_path.read_bytes(),
                          self.current_path.stat().st_mtime_ns), after)

    def test_missing_independent_expected_digest_means_review_not_verified(self):
        outcome = self.inspect(expected_backup_sha256=None)
        self.assert_class(outcome, "RESTORE_REVIEW_REQUIRED",
                          "independent_backup_digest_unavailable")
        self.assertFalse(outcome["backupDigestMatchesExpected"])

    def test_unchanged_registry_matching_backup_remains_manual_review(self):
        self.write_json(self.current_path, self.original)
        status = self.inspect()
        self.assert_class(status, "RESTORE_REVIEW_REQUIRED",
                          "registry_matches_backup_no_proven_migration")
        self.assertEqual(status["currentMissingLineageCount"], 1)

    def test_unchanged_complete_registry_backup_not_evidence_of_a_migration(self):
        self.write_pair(before=self.updated, after=self.updated)
        self.assert_class(self.inspect(), "RESTORE_REVIEW_REQUIRED",
                          "registry_matches_backup_no_proven_migration")

    def test_partial_lineage_publication_requires_manual_review(self):
        more = deepcopy(self.original)
        more["legacy2"] = _account("legacy2")
        partially_migrated = deepcopy(more)
        partially_migrated["legacy"]["accountLineage"] = MIGRATED_LINEAGE
        self.write_pair(before=more, after=partially_migrated)
        status = self.inspect()
        self.assert_class(status, "RESTORE_REVIEW_REQUIRED",
                          "partial_or_ambiguous_lineage_publication")
        self.assertEqual(status["currentMissingLineageCount"], 1)

    def test_backup_digest_and_size_mismatch_fail_closed(self):
        self.assert_class(
            self.inspect(expected_backup_sha256="0" * 64),
            "BLOCKED", "backup_digest_mismatch",
        )
        self.assert_class(
            self.inspect(expected_backup_size=self.backup_path.stat().st_size + 1),
            "BLOCKED", "backup_size_mismatch",
        )
        for value in ("A" * 64, "x" * 64, "", True, 7):
            with self.subTest(value=value):
                self.assert_class(
                    self.inspect(expected_backup_sha256=value),
                    "BLOCKED", "invalid_expected_backup_digest",
                )
        for value in (-1, True, "100", 32_000_001):
            with self.subTest(value=value):
                self.assert_class(
                    self.inspect(expected_backup_size=value),
                    "BLOCKED", "invalid_expected_backup_size",
                )

    def test_missing_empty_and_oversized_current_or_backup(self):
        for path in (self.backup_path, self.current_path):
            with self.subTest(file=path.name):
                saved = path.read_bytes()
                try:
                    path.unlink()
                    self.assert_class(self.inspect(
                        expected_backup_sha256=None, expected_backup_size=None,
                    ), "BLOCKED")
                    path.write_bytes(b"")
                    self.assert_class(self.inspect(
                        expected_backup_sha256=None, expected_backup_size=None,
                    ), "BLOCKED",
                                      "private_file_empty_or_oversized")
                    with path.open("wb") as writer:
                        writer.truncate(32_000_001)
                    self.assert_class(self.inspect(
                        expected_backup_sha256=None, expected_backup_size=None,
                    ), "BLOCKED",
                                      "private_file_empty_or_oversized")
                finally:
                    path.write_bytes(saved)

    def test_same_path_relative_parent_mismatch_and_wrong_path_types(self):
        other = self.root / "other"
        other.mkdir()
        for kwargs in (
            {"backup_path": self.current_path},
            {"registry_path": Path("users.json")},
            {"backup_path": Path("users.before-lineage.bak")},
            {"backup_path": other / "users.bak"},
            {"registry_path": str(self.current_path)},
            {"backup_path": str(self.backup_path)},
            {"registry_path": self.root / "sub" / ".." / "users.json"},
        ):
            with self.subTest(kwargs=kwargs):
                self.assert_class(self.inspect(**kwargs), "BLOCKED")

    def test_symlinked_backup_file_is_denied(self):
        alias = self.root / "linked-users.bak"
        try:
            alias.symlink_to(self.backup_path)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation denied by OS: {type(exc).__name__}")
        self.assert_class(self.inspect(backup_path=alias), "BLOCKED",
                          "linked_or_unsafe_private_file")

    def test_symlinked_parent_directory_is_denied(self):
        alias_dir = self.root / "alias-folder"
        try:
            alias_dir.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"directory symlink denied by OS: {type(exc).__name__}")
        self.assert_class(self.inspect(
            registry_path=alias_dir / self.current_path.name,
            backup_path=alias_dir / self.backup_path.name,
        ), "BLOCKED", "linked_or_unsafe_private_directory")

    def test_hardlinked_alias_is_denied(self):
        alias = self.root / "hardlinked-users.bak"
        try:
            os.link(self.backup_path, alias)
        except OSError as exc:
            self.skipTest(f"hardlink creation denied by OS: {type(exc).__name__}")
        self.assert_class(self.inspect(), "BLOCKED",
                          "linked_or_unsafe_private_file")
        self.assert_class(self.inspect(backup_path=alias), "BLOCKED",
                          "linked_or_unsafe_private_file")

    def test_changed_username_set_or_nested_username_is_blocked(self):
        for mutate in (
            lambda accounts: accounts.pop("legacy"),
            lambda accounts: accounts.update({"another": _account("another")}),
            lambda accounts: accounts["legacy"].update({"username": "changed"}),
        ):
            with self.subTest(mutate=mutate):
                changed = deepcopy(self.updated)
                mutate(changed)
                self.write_json(self.current_path, changed)
                self.assert_class(self.inspect(), "BLOCKED")
        self.write_pair()

    def test_changed_password_permissions_or_other_fields_blocked(self):
        for name, value in (
            ("passwordHash", "c" * 32 + ":" + "d" * 64),
            ("role", "viewer"),
            ("projects", ["another-project"]),
            ("financeEdit", False),
            ("displayRole", "unexpected"),
        ):
            with self.subTest(field=name):
                changed = deepcopy(self.updated)
                changed["legacy"][name] = value
                self.write_json(self.current_path, changed)
                self.assert_class(self.inspect(), "BLOCKED",
                                  "private_account_fields_changed")
        self.write_pair()

    def test_existing_lineage_replaced_or_deleted_is_blocked(self):
        for change in (
            lambda accounts: accounts["owner"].update({"accountLineage": "4" * 32}),
            lambda accounts: accounts["owner"].pop("accountLineage"),
        ):
            with self.subTest(change=change):
                data = deepcopy(self.updated)
                change(data)
                self.write_json(self.current_path, data)
                self.assert_class(self.inspect(), "BLOCKED",
                                  "existing_lineage_changed")

    def test_duplicate_or_invalid_account_lineage_blocked(self):
        for source, update in (
            ("current", lambda accounts: accounts["legacy"].update(
                {"accountLineage": OWNER_LINEAGE})),
            ("backup", lambda accounts: accounts["established"].update(
                {"accountLineage": OWNER_LINEAGE})),
            ("current", lambda accounts: accounts["legacy"].update(
                {"accountLineage": "0" * 32})),
            ("backup", lambda accounts: accounts["owner"].update(
                {"accountLineage": "BAD"})),
        ):
            with self.subTest(source=source, update=update):
                before, after = deepcopy(self.original), deepcopy(self.updated)
                update(after if source == "current" else before)
                self.write_pair(before=before, after=after)
                self.assert_class(self.inspect(), "BLOCKED")
        self.write_pair()

    def test_duplicate_nested_and_top_level_json_fields_blocked(self):
        for path, raw in (
            (self.backup_path, b'{"owner":{},"owner":{}}'),
            (self.current_path, b'{"legacy":{"username":"legacy","role":"editor","role":"admin"}}'),
        ):
            saved = path.read_bytes()
            try:
                path.write_bytes(raw)
                self.assert_class(self.inspect(), "BLOCKED", "duplicate_json_field")
            finally:
                path.write_bytes(saved)

    def test_malformed_json_or_schema_blocked(self):
        for obj in (b"{", b"[]", b"null", b'{"owner":null}',
                    b'{"owner":{"username":"owner"}}'):
            with self.subTest(obj=obj):
                self.backup_path.write_bytes(obj)
                self.assert_class(self.inspect(), "BLOCKED")
        self.write_pair()

    def test_nonfinite_json_is_not_accepted_as_private_registry(self):
        malformed = self.backup_path.read_bytes().replace(
            b'"displayRole":"synthetic"', b'"displayRole":NaN', 1,
        )
        self.backup_path.write_bytes(malformed)
        self.assert_class(self.inspect(), "BLOCKED",
                          "nonfinite_private_registry_json")

    def test_invalid_project_scope_role_password_and_permission_blocked(self):
        for name, value in (
            ("role", "taraz_adapter"), ("passwordHash", "not-a-hash"),
            ("projects", ["repeated", "repeated"]), ("projects", "x"),
            ("financeEdit", 1),
        ):
            with self.subTest(field=name, value=value):
                bad = deepcopy(self.updated)
                bad["legacy"][name] = value
                self.write_json(self.current_path, bad)
                self.assert_class(self.inspect(), "BLOCKED")
        self.write_pair()

    def test_migration_backup_without_missing_lineages_cannot_be_verified(self):
        before = deepcopy(self.updated)
        after = deepcopy(before)
        after["legacy"]["accountLineage"] = "4" * 32
        self.write_pair(before=before, after=after)
        self.assert_class(self.inspect(), "BLOCKED", "existing_lineage_changed")

    def test_mutation_between_two_readbacks_blocks_verification(self):
        original_snapshot = inspector._snapshot
        calls = 0

        def replaced_snapshot(path):
            nonlocal calls
            calls += 1
            data = original_snapshot(path)
            if calls == 2:
                updated = deepcopy(self.updated)
                updated["legacy"]["accountLineage"] = "5" * 32
                self.write_json(self.current_path, updated)
            return data

        with patch.object(inspector, "_snapshot", side_effect=replaced_snapshot):
            self.assert_class(self.inspect(), "BLOCKED",
                              "private_file_changed_during_assessment")


if __name__ == "__main__":
    unittest.main()
