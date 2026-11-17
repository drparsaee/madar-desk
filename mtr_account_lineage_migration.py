"""Explicit local-host ADMIN migration for legacy accountLineage, never HTTP.

The private LanService user registry is the sole authority. This migrates ONLY
legacy accounts whose accountLineage field is completely absent. It does not
touch, remap or query the old username-owned E2 outbox. A new E2 request must
be freshly prepared after migration under the new opaque actor identity.

Operator requirements: an authenticated administrator token, a trusted
absolute users.json path and a new backup path in the same private directory.
Do not mount this callable on a LAN or browser endpoint.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat

from lan import LanService
from mtr_account_lineage import (
    AccountLineageError, new_account_lineage, principal_actor_id,
)


_MAX_REGISTRY_BYTES = 32_000_000
_MAX_USERS = 10_000
_ACCOUNT_ROLES = frozenset({"admin", "editor", "viewer"})
_LINEAGE_KEY = "accountLineage"


class AccountLineageMigrationDenied(PermissionError):
    """Missing admin authority, malformed registry, or unsafe backup."""


class AccountLineageMigrationUncertain(RuntimeError):
    """Host identity publication/backup consistency needs manual recovery."""


def _plain_private_file(path: Path, *, required: bool) -> bool:
    if not isinstance(path, Path) or not path.is_absolute():
        raise AccountLineageMigrationDenied("trusted absolute private path required")
    for parent in (path.parent, *path.parent.parents):
        if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
            raise AccountLineageMigrationDenied("unsafe private directory alias")
        try:
            info = parent.lstat()
        except OSError as exc:
            raise AccountLineageMigrationDenied("private directory unavailable") from exc
        if (not stat.S_ISDIR(info.st_mode) or
                getattr(info, "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise AccountLineageMigrationDenied("unsafe private directory")
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise AccountLineageMigrationDenied("private file alias forbidden")
    try:
        info = path.lstat()
    except FileNotFoundError:
        if required:
            raise AccountLineageMigrationDenied("private registry missing")
        return False
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
            getattr(info, "st_file_attributes", 0) &
            getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise AccountLineageMigrationDenied("unsafe private file")
    return True


def _unique_pairs(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise AccountLineageMigrationDenied("duplicate private registry key")
        output[key] = value
    return output


def _private_snapshot(service: LanService) -> tuple[bytes, dict]:
    path = service.users_path
    _plain_private_file(path, required=True)
    if path.stat().st_size > _MAX_REGISTRY_BYTES:
        raise AccountLineageMigrationDenied("private registry exceeds safety bound")
    original_bytes = path.read_bytes()
    if not original_bytes or len(original_bytes) > _MAX_REGISTRY_BYTES:
        raise AccountLineageMigrationDenied("private registry empty or oversized")
    try:
        disk_users = json.loads(
            original_bytes.decode("utf-8"), object_pairs_hook=_unique_pairs,
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise AccountLineageMigrationDenied("private registry cannot be verified") from exc
    if (type(disk_users) is not dict or type(service.users) is not dict
            or len(disk_users) > _MAX_USERS or
            disk_users != service.users):
        raise AccountLineageMigrationDenied(
            "memory and disk registry disagree; migration refused"
        )
    return original_bytes, disk_users


def _build_migration(original: dict) -> tuple[dict, int]:
    updated = deepcopy(original)
    seen = set()
    missing = []
    for username, account in updated.items():
        if (type(username) is not str or not 3 <= len(username) <= 40 or
                any(not ch.isascii() or (not ch.isalnum() and ch not in "._-")
                    for ch in username) or type(account) is not dict or
                account.get("username") != username or
                account.get("role") not in _ACCOUNT_ROLES):
            raise AccountLineageMigrationDenied("invalid private account record")
        if _LINEAGE_KEY not in account:
            missing.append(username)
            continue
        try:
            principal_actor_id(account)
        except AccountLineageError as exc:
            raise AccountLineageMigrationDenied("invalid existing lineage") from exc
        lineage = account[_LINEAGE_KEY]
        if lineage in seen:
            raise AccountLineageMigrationDenied("duplicate existing lineage")
        seen.add(lineage)
    for username in missing:
        try:
            lineage = new_account_lineage()
            principal_actor_id({_LINEAGE_KEY: lineage})
        except AccountLineageError as exc:
            raise AccountLineageMigrationDenied("secure lineage creation failed") from exc
        if lineage in seen:
            raise AccountLineageMigrationDenied("generated duplicate lineage")
        updated[username][_LINEAGE_KEY] = lineage
        seen.add(lineage)
    return updated, len(missing)


def _private_verified_backup(path: Path, original: bytes) -> str:
    """Create-only exact bytes with fsync and independent bytes/hash readback."""
    _plain_private_file(path, required=False)
    if path.exists():
        raise FileExistsError("private lineage migration backup already exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as backup:
        backup.write(original)
        backup.flush()
        os.fsync(backup.fileno())
    _plain_private_file(path, required=True)
    recorded = path.read_bytes()
    expected = hashlib.sha256(original).hexdigest()
    if (recorded != original or
            hashlib.sha256(recorded).hexdigest() != expected):
        raise AccountLineageMigrationDenied(
            "private backup readback/digest mismatch; original registry unchanged"
        )
    return expected


def migrate_legacy_account_lineages(
    service: LanService, *, admin_token: str, backup_path: Path,
) -> dict:
    """Migrate missing lineage only; call explicitly from trusted host Python.

    A verified *original* registry backup precedes the existing atomic host
    publication. On an uncertain save, preserve the backup and stop this host
    instance from serving logins/actions using its existing recovery hard-stop
    guard. The caller must manually inspect/restore/restart before resuming.
    """
    if type(service) is not LanService:
        raise AccountLineageMigrationDenied("actual trusted LanService required")
    if type(admin_token) is not str or not admin_token:
        raise AccountLineageMigrationDenied("current administrator session required")
    if not isinstance(backup_path, Path) or not backup_path.is_absolute():
        raise AccountLineageMigrationDenied("absolute operator backup path required")
    with service.lock:
        try:
            admin = service.account_for(admin_token)
        except PermissionError as exc:
            # The host may also detect duplicate private account lineage at
            # authentication time. A migration can never bypass that denial,
            # but should report it as a migration precondition failure.
            raise AccountLineageMigrationDenied(
                "admin session or private identity cannot be verified"
            ) from exc
        if admin.get("role") != "admin":
            raise AccountLineageMigrationDenied("host administrator required")
        if (getattr(service, "_delete_recovery_required", False) or
                service.delete_journal_path.exists() or
                service.delete_journal_path.is_symlink()):
            raise AccountLineageMigrationDenied("pending host identity recovery")
        users_path = service.users_path
        if (not isinstance(users_path, Path) or not users_path.is_absolute()
                or backup_path.parent != users_path.parent
                or backup_path == users_path):
            raise AccountLineageMigrationDenied(
                "backup must be new file in private host registry directory"
            )
        original_bytes, original = _private_snapshot(service)
        updated, count = _build_migration(original)
        if count == 0:
            return {
                "migratedAccounts": 0, "unchangedAccounts": len(original),
                "backupCreated": False, "registryPublished": False,
                "legacyOutboxRemapped": False,
            }
        digest = _private_verified_backup(backup_path, original_bytes)
        # Ensure no unrelated external writer replaced original data while
        # our backup was being created. The host lock covers LAN writers.
        disk_again, snapshot_again = _private_snapshot(service)
        if disk_again != original_bytes or snapshot_again != original:
            raise AccountLineageMigrationDenied(
                "host registry changed during verified backup"
            )
        try:
            service._publish_users(updated)
            persisted = service._read_users()
            if persisted != updated or service.users != updated:
                raise AccountLineageMigrationUncertain(
                    "identity publish outcome inconsistent after success"
                )
        except BaseException as exc:
            # _publish_users compensates its own failed write if safe. Do not
            # assume compensation succeeded without checking both authorities.
            try:
                persisted = service._read_users()
            except BaseException as inspection:
                service._delete_recovery_required = True
                raise AccountLineageMigrationUncertain(
                    "identity save failed; disk unreadable; host stopped for recovery"
                ) from inspection
            if persisted != original or service.users != original:
                service._delete_recovery_required = True
                raise AccountLineageMigrationUncertain(
                    "identity save ambiguous; host stopped, use verified backup"
                ) from exc
            # The original contents were recovered by _publish_users; keep
            # backup for operator evidence and surface the original failure.
            raise
        return {
            "migratedAccounts": count,
            "unchangedAccounts": len(original) - count,
            "backupCreated": True,
            "backupSha256": digest,
            "backupPath": str(backup_path),
            "registryPublished": True,
            "legacyOutboxRemapped": False,
        }


__all__ = [
    "AccountLineageMigrationDenied",
    "AccountLineageMigrationUncertain",
    "migrate_legacy_account_lineages",
]
