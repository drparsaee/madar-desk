"""Read-only E2 account-lineage migration/restart inspection.

An operator explicitly supplies two private, same-directory, absolute file
paths: the *current* host users JSON and the migration's create-only original
registry backup. This module never restores or publishes any identity, mints
lineages, logs in, starts LAN, or accesses implicit profile locations.

There is NO durable signed provenance manifest in the current migration.
VERIFIED_CONSISTENT means strictly that the candidate files have the exact
structural legacy->post-migration relationship and the candidate backup bytes
match an *independently held* SHA-256 digest supplied by the operator. It
cannot establish the historical origin of that digest, host-memory state,
live lock ownership, backup fsync, or permission to resume authentication.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

from mtr_account_lineage import AccountLineageError, principal_actor_id


_MAX_REGISTRY_BYTES = 32_000_000
_MAX_USERS = 10_000
_MAX_PROJECTS_PER_USER = 1_000
_USERNAME = re.compile(r"[A-Za-z0-9._-]{3,40}\Z", re.ASCII)
_PASSWORD_HASH = re.compile(r"[0-9a-f]{32}:[0-9a-f]{64}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ROLES = frozenset({"admin", "editor", "viewer"})
_LINEAGE = "accountLineage"


class _InspectionBlocked(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _result(classification: str, reason: str, **safe: object) -> dict:
    return {
        "schemaVersion": 1,
        "classification": classification,
        "reason": reason,
        "readOnly": True,
        "automaticRestoreAllowed": False,
        "safeToResumeHost": False,
        "manualOperatorReviewRequired": True,
        "backupProvenanceCryptographicallyProven": False,
        **safe,
    }


def _plain_private_path(path: Path) -> os.stat_result:
    # Do not resolve first: resolve() would conceal symlink/junction traversal.
    if (not isinstance(path, Path) or not path.is_absolute()
            or ".." in path.parts):
        raise _InspectionBlocked("explicit_absolute_path_required")
    for parent in (path.parent, *path.parent.parents):
        try:
            info = parent.lstat()
        except OSError as exc:
            raise _InspectionBlocked("private_path_unavailable") from exc
        if (parent.is_symlink()
                or getattr(parent, "is_junction", lambda: False)()
                or not stat.S_ISDIR(info.st_mode)
                or getattr(info, "st_file_attributes", 0) &
                   getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise _InspectionBlocked("linked_or_unsafe_private_directory")
    try:
        info = path.lstat()
    except OSError as exc:
        raise _InspectionBlocked("private_file_missing_or_unreadable") from exc
    if (path.is_symlink() or getattr(path, "is_junction", lambda: False)()
            or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or getattr(info, "st_file_attributes", 0) &
               getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise _InspectionBlocked("linked_or_unsafe_private_file")
    if not 0 < info.st_size <= _MAX_REGISTRY_BYTES:
        raise _InspectionBlocked("private_file_empty_or_oversized")
    return info


def _snapshot(path: Path) -> tuple[bytes, str, int]:
    before = _plain_private_path(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as source:
            opened = os.fstat(source.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or opened.st_dev != before.st_dev
                    or opened.st_ino != before.st_ino):
                raise _InspectionBlocked("private_file_changed_during_read")
            raw = source.read(_MAX_REGISTRY_BYTES + 1)
            after_read = os.fstat(source.fileno())
    except OSError as exc:
        raise _InspectionBlocked("private_file_read_failed") from exc
    after = _plain_private_path(path)
    if (not raw or len(raw) > _MAX_REGISTRY_BYTES
            or len(raw) != before.st_size
            or (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns) !=
               (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
            or (opened.st_dev, opened.st_ino, opened.st_size) !=
               (after_read.st_dev, after_read.st_ino, after_read.st_size)):
        raise _InspectionBlocked("private_file_changed_during_read")
    return raw, hashlib.sha256(raw).hexdigest(), len(raw)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _InspectionBlocked("duplicate_json_field")
        result[key] = value
    return result


def _reject_nonfinite(_):
    raise _InspectionBlocked("nonfinite_private_registry_json")


def _validate_registry(raw: bytes) -> tuple[dict, frozenset[str]]:
    try:
        registry = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                              parse_constant=_reject_nonfinite)
    except (UnicodeError, ValueError, RecursionError, OverflowError) as exc:
        if isinstance(exc, _InspectionBlocked):
            raise
        raise _InspectionBlocked("malformed_private_registry_json") from exc
    if type(registry) is not dict or not 1 <= len(registry) <= _MAX_USERS:
        raise _InspectionBlocked("invalid_private_registry_schema")
    lineages = set()
    missing = set()
    for username, account in registry.items():
        if (type(username) is not str or _USERNAME.fullmatch(username) is None
                or type(account) is not dict or account.get("username") != username
                or type(account.get("role")) is not str
                or account["role"] not in _ROLES
                or type(account.get("passwordHash")) is not str
                or _PASSWORD_HASH.fullmatch(account["passwordHash"]) is None):
            raise _InspectionBlocked("invalid_private_account_schema_or_username")
        projects = account.get("projects", ...)
        if projects is ... or (projects is not None and
                (type(projects) is not list or len(projects) > _MAX_PROJECTS_PER_USER
                 or any(type(project) is not str or not 1 <= len(project) <= 180
                        for project in projects)
                 or len(set(projects)) != len(projects))):
            raise _InspectionBlocked("invalid_private_account_project_scope")
        for key in ("financeEdit", "financeView"):
            if key in account and type(account[key]) is not bool:
                raise _InspectionBlocked("invalid_private_account_permission")
        if _LINEAGE not in account:
            missing.add(username)
            continue
        try:
            principal_actor_id(account)
        except AccountLineageError as exc:
            raise _InspectionBlocked("invalid_account_lineage") from exc
        lineage = account[_LINEAGE]
        if lineage in lineages:
            raise _InspectionBlocked("duplicate_account_lineage")
        lineages.add(lineage)
    return registry, frozenset(missing)


def inspect_account_lineage_recovery(
    registry_path: Path,
    backup_path: Path,
    *,
    expected_backup_sha256: str | None = None,
    expected_backup_size: int | None = None,
) -> dict:
    """Assess two explicit private files without modifying either.

    A pre-recorded, separately held SHA-256 is REQUIRED to classify an exact
    successful structural migration as VERIFIED_CONSISTENT. Without it, even
    a perfect-looking pair needs manual restoration/provenance review.

    BLOCKED is for unsafe, missing, malformed, contradictory or corrupt data.
    RESTORE_REVIEW_REQUIRED is for intact but insufficiently proven recovery.
    All classifications forbid automatic restoration and host resumption.
    """
    try:
        if (not isinstance(registry_path, Path)
                or not isinstance(backup_path, Path)
                or not registry_path.is_absolute() or not backup_path.is_absolute()
                or ".." in registry_path.parts or ".." in backup_path.parts
                or registry_path == backup_path
                or registry_path.parent != backup_path.parent):
            raise _InspectionBlocked("unsafe_or_nonmatching_explicit_paths")
        if (expected_backup_sha256 is not None and
                (type(expected_backup_sha256) is not str
                 or _SHA256.fullmatch(expected_backup_sha256) is None)):
            raise _InspectionBlocked("invalid_expected_backup_digest")
        if (expected_backup_size is not None and
                (type(expected_backup_size) is not int
                 or not 1 <= expected_backup_size <= _MAX_REGISTRY_BYTES)):
            raise _InspectionBlocked("invalid_expected_backup_size")
        registry_raw, registry_hash, registry_size = _snapshot(registry_path)
        backup_raw, backup_hash, backup_size = _snapshot(backup_path)
        if (registry_path.samefile(backup_path)):
            raise _InspectionBlocked("same_physical_file")
        if (expected_backup_sha256 is not None and
                backup_hash != expected_backup_sha256):
            raise _InspectionBlocked("backup_digest_mismatch")
        if (expected_backup_size is not None
                and backup_size != expected_backup_size):
            raise _InspectionBlocked("backup_size_mismatch")
        backup, missing_original = _validate_registry(backup_raw)
        current, missing_current = _validate_registry(registry_raw)
        # Both files are re-read at the end to fail closed on changes between
        # snapshots; no cross-file transaction/OS-exclusive lock is claimed.
        if (_snapshot(registry_path)[0] != registry_raw
                or _snapshot(backup_path)[0] != backup_raw):
            raise _InspectionBlocked("private_file_changed_during_assessment")
        safe = {
            "registrySha256": registry_hash, "registrySizeBytes": registry_size,
            "backupSha256": backup_hash, "backupSizeBytes": backup_size,
            "accountCount": len(backup),
            "backupMissingLineageCount": len(missing_original),
            "currentMissingLineageCount": len(missing_current),
            "backupDigestMatchesExpected": expected_backup_sha256 is not None,
        }
        if backup.keys() != current.keys():
            raise _InspectionBlocked("username_set_changed")
        for name in backup:
            before, after = backup[name], current[name]
            # The migration is *only* allowed to add previously absent lineage.
            if ({k: v for k, v in before.items() if k != _LINEAGE} !=
                    {k: v for k, v in after.items() if k != _LINEAGE}):
                raise _InspectionBlocked("private_account_fields_changed")
            if _LINEAGE in before and before[_LINEAGE] != after.get(_LINEAGE):
                raise _InspectionBlocked("existing_lineage_changed")
        if backup == current:
            return _result("RESTORE_REVIEW_REQUIRED", "registry_matches_backup_no_proven_migration", **safe)
        if not missing_original:
            raise _InspectionBlocked("backup_has_no_legacy_lineage_to_migrate")
        if missing_current:
            return _result("RESTORE_REVIEW_REQUIRED", "partial_or_ambiguous_lineage_publication", **safe)
        if expected_backup_sha256 is None:
            return _result("RESTORE_REVIEW_REQUIRED", "independent_backup_digest_unavailable", **safe)
        return _result(
            "VERIFIED_CONSISTENT", "structurally_exact_lineage_only_migration",
            addedLineageCount=len(missing_original),
            **safe,
        )
    except _InspectionBlocked as exc:
        return _result("BLOCKED", exc.code)
    except (OSError, ValueError, RecursionError) as exc:
        # No credentials, account details, supplied paths or exception text
        # enter public results. This is an operator-only assessment.
        return _result("BLOCKED", "private_inspection_failed")


__all__ = ["inspect_account_lineage_recovery"]
