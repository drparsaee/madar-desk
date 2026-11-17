# MTR P0: Disposable three-database backup and restore QA

Scope: **synthetic metadata only**, with freshly created disposable temporary
Windows directories. No installed Madar/Taraz app, real profile, LAN, service,
accounting ledger, installer, signing or deployment is accessed. The temp
databases are removed on exit. No application source file is edited.

## Commands

    python -B scripts/qa_mtr_safe_backup_restore_20261110.py
    python -B -m unittest -v tests.test_mtr_safe_backup_restore_20261110

The script uses create-only native snapshot APIs for HostRequestStore,
OneShotDispatchGate and the separately isolated TarazPeerRegistry. It fails
closed if any API is unavailable. It does not run Taraz's executable.

Each of three SQLite files is backed up separately and verified for full
SQLite integrity, foreign keys, schema version, required tables, immutable
peer triggers, byte-level SHA-256 and table-content SHA-256. The manifest
must name exactly three expected snapshots. Restore verifies all three
snapshots before writing any destination, rejects missing/duplicate/extra/
corrupt/linked files, then creates three different NEW SQLite paths without
overwriting any existing file. SQLite backup may rearrange page bytes:
restored schema, row content and independent integrity checks must match,
not necessarily byte-for-byte file hashes.

## Proven synthetic invariants

- After manual Madar metadata prepare and send authorization, one-shot
  reservation plus unknown-after-attempt is persisted.
- The dispatch backup disables first-send permits. Reopening the restored
  gate cannot mint a second dispatch permit and retains query-first status
  with no automatic retry.
- A synthetic HMAC metadata peer intake and query survives Taraz registry
  archive/restore; the same request is idempotent and existing query identity
  remains reserved after class restart.
- All test directional HMAC keys exist only in memory. No genuine peer
  certificate, finance approval, official receipt or ledger posting exists.
- Negative tests reject missing or changed backups, collisions, extra or
  duplicated manifest fields, symlinks, missing APIs and invalid source scope.

## Release gaps remaining

**Not an atomic coordinated three-database backup epoch.** Snapshot calls
are sequential on quiescent synthetic databases. Real concurrent updates,
crash/power-loss, service restart, complete profile/attachment scope, secret
re-provisioning, two-PC synchronization, accounting reconciliation and
operational rollback remain untested. The manifest is checksum evidence,
not independently signed provenance. Restoring synthetic metadata does not
authenticate a financial receipt or authorize restoring production data.
This test is a bounded backup/replay safety demonstration, never an
installation or release acceptance certificate.
