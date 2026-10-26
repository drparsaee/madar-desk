"""Explicit-path, OFFLINE-only, no-clobber standalone-accounting SQLite restore.

Restore NEVER detects APPDATA, initializes a missing DB, overwrites a target,
migrates other ledgers or invokes the native/LAN host. It creates a *new* DB
only after verifying the plaintext backup and a temporary, consistent copy.
Operator confirmations are declarations, not checks that the app is stopped.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile

from standalone_accounting import StandaloneAccountingError
from standalone_accounting_backup import (
    SOURCE_FILENAME, StandaloneBackupError, _absolute_path, _check_snapshot,
    _readonly_sqlite, _sqlite_backup, _sync_directory, _sync_file,
    _validate_backup,
)


class StandaloneRestoreError(RuntimeError):
    """Source rejected or a safe offline restore could not be published."""


_SIDECARS = ("-wal", "-shm", "-journal")


def preview_template_companion(source: Path, destination: Path | None = None) -> dict:
    """Read-only, schema-checked companion inspection for explicit SQLite backup.

    An absent companion means a legacy SQLite-only snapshot. A damaged one
    must fail closed, rather than silently restoring finance without layouts.
    """
    from standalone_accounting_template_store import validate_library_document
    companion = source.with_suffix('.templates.json')
    _check_path_components(companion)
    if not companion.exists() and not companion.is_symlink():
        return {"present": False, "count": 0, "source": companion}
    if companion.is_symlink() or not stat.S_ISREG(companion.lstat().st_mode):
        raise StandaloneRestoreError("Template backup companion is not a regular file")
    if companion.stat().st_size > 2 * 1024 * 1024:
        raise StandaloneRestoreError("Template backup companion exceeds size limit")
    try:
        content = companion.read_bytes()
        document = validate_library_document(json.loads(content.decode('utf-8')))
    except (OSError, ValueError, UnicodeDecodeError, TypeError) as exc:
        raise StandaloneRestoreError("Template backup companion is damaged") from exc
    if destination is not None:
        target = destination.parent / 'invoice-templates.json'
        _check_path_components(target)
        if os.path.lexists(target):
            raise FileExistsError('Template restore destination already exists')
    return {"present": True, "count": len(document['templates']),
            "source": companion, "bytes": content}


def preview_identity_companion(source: Path, destination: Path | None = None) -> dict:
    """Require a valid isolated user registry before restoring it with a book."""
    from standalone_accounting_identity import validate_identity_document
    companion=source.with_suffix('.users.json')
    _check_path_components(companion)
    if not companion.exists() and not companion.is_symlink():
        return {"present":False,"count":0,"source":companion}
    if companion.is_symlink() or not stat.S_ISREG(companion.lstat().st_mode):
        raise StandaloneRestoreError('Invalid user backup companion file')
    if companion.stat().st_size > 1024*1024:
        raise StandaloneRestoreError('User backup companion too large')
    try:
        raw=companion.read_bytes()
        users=validate_identity_document(json.loads(raw.decode('utf-8')))['users']
    except (OSError,ValueError,UnicodeDecodeError,TypeError,PermissionError) as exc:
        raise StandaloneRestoreError('User backup companion damaged') from exc
    if not users:
        raise StandaloneRestoreError('Protected user backup has no accounts')
    if destination is not None:
        target=destination.parent/'local-users.json'
        _check_path_components(target)
        if os.path.lexists(target):
            raise FileExistsError('User restore destination already exists')
    return {"present":True,"count":len(users),"source":companion,"bytes":raw}


def _is_link_or_junction(path: Path) -> bool:
    """Reject existing symlinks, Windows junctions and their ancestors."""
    return path.is_symlink() or (
        hasattr(path, "is_junction") and path.is_junction()
    )


def _check_path_components(path: Path) -> None:
    for component in (path, *path.parents):
        if _is_link_or_junction(component):
            raise ValueError("Symlink/junction paths are not allowed for offline restore")


def _refuse_sidecars(path: Path, *, destination: bool) -> None:
    # A missing destination with stale -wal/-shm is NOT safe to restore into.
    # A backup with sidecars is not a standalone, offline, one-file backup.
    for suffix in _SIDECARS:
        entry = Path(str(path) + suffix)
        if os.path.lexists(entry):
            what = "destination" if destination else "source"
            raise StandaloneRestoreError(
                f"Unexpected {what} SQLite companion file: {entry.name}")


def _checked_head(connection: sqlite3.Connection) -> tuple[int, str | None]:
    revision = _check_snapshot(connection)
    if revision == 0:
        return 0, None
    digest = connection.execute(
        "SELECT digest FROM standalone_accounting WHERE id=1").fetchone()[0]
    return revision, digest


def _check_input(source: Path) -> tuple[int, str | None]:
    _check_path_components(source)
    try:
        mode = source.lstat().st_mode
    except FileNotFoundError as exc:
        raise FileNotFoundError("Explicit standalone backup source is missing") from exc
    if not stat.S_ISREG(mode):
        raise ValueError("Source must be an existing regular SQLite backup file")
    _refuse_sidecars(source, destination=False)
    # No StandaloneAccountingStore(source): its constructor can create/migrate.
    with closing(_readonly_sqlite(source)) as reader:
        reader.execute("BEGIN")
        try:
            return _checked_head(reader)
        finally:
            reader.execute("ROLLBACK")


def _check_new_destination(source: Path, destination: Path) -> None:
    if destination.name != SOURCE_FILENAME:
        raise ValueError("Restore destination must be named standalone-accounting.sqlite3")
    _check_path_components(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError("Restore destination directory must already exist")
    if source == destination or source.resolve() == destination.resolve(strict=False):
        raise ValueError("Backup source and destination must not be identical")
    if os.path.lexists(destination):
        # Includes existing hard link aliases and dangling symbolic links.
        try:
            if os.path.samefile(source, destination):
                raise ValueError("Source and destination refer to the same inode")
        except (FileNotFoundError, OSError):
            pass
        raise FileExistsError("Restore destination already exists; never overwrite")
    _refuse_sidecars(destination, destination=True)


def _remove_our_temp(temporary: Path) -> list[OSError]:
    """Only names created for this temporary file; never old backups or DBs."""
    errors = []
    for suffix in (*_SIDECARS, ""):
        try:
            Path(str(temporary) + suffix).unlink(missing_ok=True)
        except OSError as exc:
            errors.append(exc)
    return errors


def restore_standalone_accounting(
    source: Path, destination: Path, *,
    plaintext_acknowledged: bool,
    offline_acknowledged: bool,
) -> Path:
    """Restore a validated portable standalone TOMAN DB to a NONEXISTENT path.

    The host MUST be stopped, including other processes that could start it.
    Assertions do not make stopping the host detectable/enforceable here.
    """
    if plaintext_acknowledged is not True:
        raise PermissionError("Explicit plaintext accounting acknowledgement required")
    if offline_acknowledged is not True:
        raise PermissionError("Explicit OFFLINE operator acknowledgement required")
    source = _absolute_path(source, "backup source")
    destination = _absolute_path(destination, "restore destination")
    _check_new_destination(source, destination)
    original_head = _check_input(source)
    template_companion = preview_template_companion(source, destination)
    identity_companion = preview_identity_companion(source, destination)
    temporary = None
    published = False
    companion_published = False
    companion_temp = None
    template_target = destination.parent / 'invoice-templates.json'
    identity_published = False
    identity_temp = None
    identity_target = destination.parent / 'local-users.json'
    prior_error = None
    try:
        fd, name = tempfile.mkstemp(
            dir=str(destination.parent), prefix="." + destination.name + ".restore-",
            suffix=".sqlite3")
        temporary = Path(name)
        os.close(fd)
        # Online backup into a private copy avoids copying an inconsistent
        # database header or a partially checkpointed source backup.
        _sqlite_backup(source, temporary)
        snapshot_revision = _validate_backup(temporary)
        with closing(_readonly_sqlite(temporary)) as reader:
            restored_head = _checked_head(reader)
        if restored_head != original_head or snapshot_revision != original_head[0]:
            # Offline backup must be immutable across validation/copy; never
            # silently accept a different head, even with SAME revision.
            raise StandaloneRestoreError(
                "Backup snapshot head changed during OFFLINE restore verification")
        _sync_file(temporary)  # r+b on temp only: needed on Windows CRT.
        _check_new_destination(source, destination)
        _refuse_sidecars(source, destination=False)
        current_companion = preview_template_companion(source, destination)
        if current_companion['present'] != template_companion['present'] or (
            current_companion['present'] and current_companion['bytes'] != template_companion['bytes']
        ):
            raise StandaloneRestoreError('Template backup companion changed during restore')
        current_identity=preview_identity_companion(source,destination)
        if (current_identity['present']!=identity_companion['present'] or
            (current_identity['present'] and current_identity['bytes']!=identity_companion['bytes'])):
            raise StandaloneRestoreError('User backup companion changed during restore')
        if template_companion['present']:
            descriptor, companion_name = tempfile.mkstemp(
                dir=str(destination.parent), prefix='.invoice-templates.restore-', suffix='.json')
            companion_temp = Path(companion_name)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(template_companion['bytes'])
                stream.flush()
                os.fsync(stream.fileno())
        if identity_companion['present']:
            descriptor,identity_name=tempfile.mkstemp(
                dir=str(destination.parent),prefix='.local-users.restore-',suffix='.json')
            identity_temp=Path(identity_name)
            with os.fdopen(descriptor,'wb') as stream:
                stream.write(identity_companion['bytes'])
                stream.flush()
                os.fsync(stream.fileno())
        # os.link is an atomic CREATE-IF-ABSENT on the *destination filesystem*.
        # os.replace would overwrite, and copyfile/exclusive open could publish
        # a partially written DB; neither is allowed.
        os.link(str(temporary), str(destination))
        published = True
        if companion_temp is not None:
            os.link(str(companion_temp), str(template_target))
            companion_published = True
        if identity_temp is not None:
            os.link(str(identity_temp),str(identity_target))
            identity_published=True
        _sync_directory(destination.parent)  # best-effort Windows directory fsync
        return destination
    except BaseException as exc:
        prior_error = exc
        if identity_published and identity_temp is not None:
            try:
                if os.path.samefile(identity_temp,identity_target):
                    identity_target.unlink()
            except OSError as cleanup_exc:
                exc.add_note('Could not revoke restored user file: '+str(cleanup_exc))
        if companion_published and companion_temp is not None:
            try:
                if os.path.samefile(companion_temp, template_target):
                    template_target.unlink()
            except OSError as cleanup_exc:
                exc.add_note('Could not revoke restored template file: ' + str(cleanup_exc))
        # If publication succeeded but subsequent steps failed, delete *only*
        # the name we published AND only while it still points to our temp inode.
        # Never delete an independently created file or a racing replacement.
        if published and temporary is not None:
            try:
                if os.path.samefile(temporary, destination):
                    destination.unlink()
            except OSError as cleanup_exc:
                exc.add_note("Could not revoke our incomplete restore publication: " +
                             str(cleanup_exc))
        raise
    finally:
        if identity_temp is not None:
            identity_temp.unlink(missing_ok=True)
        if companion_temp is not None:
            companion_temp.unlink(missing_ok=True)
        if temporary is not None:
            cleanup_errors = _remove_our_temp(temporary)
            if cleanup_errors:
                explanation = "; ".join(str(error) for error in cleanup_errors)
                if prior_error is not None:
                    prior_error.add_note(
                        "Manual removal of temporary plaintext files required: " +
                        explanation)
                else:
                    raise StandaloneRestoreError(
                        "Restore published but temporary plaintext cleanup failed: " +
                        explanation)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Explicit OFFLINE standalone TOMAN accounting restore, "
                    "only to a NEW database file; never overwrite")
    parser.add_argument("--source", type=Path, required=True,
                        help="Absolute path to one-file, validated SQLite backup")
    parser.add_argument("--destination", type=Path, required=True,
                        help="Absolute NONEXISTENT .../standalone-accounting.sqlite3")
    parser.add_argument("--acknowledge-plaintext", action="store_true",
                        help="Accept unencrypted financial data at the destination")
    parser.add_argument("--offline", action="store_true",
                        help="Operator confirms all Madar hosts/processes are stopped")
    options = parser.parse_args(argv)
    try:
        published = restore_standalone_accounting(
            options.source, options.destination,
            plaintext_acknowledged=options.acknowledge_plaintext,
            offline_acknowledged=options.offline)
    except (PermissionError, ValueError, FileNotFoundError, FileExistsError,
            StandaloneRestoreError, StandaloneBackupError,
            StandaloneAccountingError, OSError, sqlite3.Error) as exc:
        print("Offline restore refused: " + str(exc), file=sys.stderr)
        return 1
    print("Standalone accounting OFFLINE plaintext restore created: " +
          str(published))
    return 0


if __name__ == "__main__":
    sys.exit(main())
