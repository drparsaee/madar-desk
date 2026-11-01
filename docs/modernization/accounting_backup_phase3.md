# Standalone accounting manual backup publication: phase 3 ExecPlan

## Purpose / decision / exclusions

- Owner requires preservation of existing financial data during modernization. This narrow change concerns manual `standalone_accounting_backup.py`, with no change to source database, schema, currency or restore contract.
- Worktree: `D:\CoS-Test\madar-codex-modernization-phase2-20261101`, baseline commit `60beedd` on `modernization/phase2-20261101`.
- Only synthetic `TemporaryDirectory` files are used in tests. Legacy `TOMAN` data is preserved exactly; migration to target `RIAL` is outside this work.

## Existing behavior and measurable defect

- `backup_standalone_accounting` copies via SQLite online backup to a temporary file; `_validate_backup` checks SQLite integrity, event replay, revision and currency; `_sync_file` flushes the temporary file.
- `os.link` atomically publishes the temporary file at a new destination, preserving the no-clobber contract. `_sync_directory` follows publication; the `finally` block removes temporary files.
- **Observed in source:** if `_sync_directory` raises after successful link, the caller receives an exception while the published backup is still present. This differs from the restore path's guarded rollback and violates the backup module's error contract. Actual filesystem crash durability is not inferred from this source inspection.

## Plan of work

1. Add synthetic failing tests in `tests/test_standalone_accounting_backup.py` for directory sync error after successful publication, and for concurrent replacement of the published name.
2. Implement a guarded rollback only when the destination is still the same inode as the temporary copy. Preserve a racing replacement. Do not remove any other target, source or backup.
3. Run focused and adjacent backup/restore tests and `git diff --check`; record results below.

## Parity specification

- Normal backup and restore: existing contents, revision, event history and currencies remain byte/semantic equivalent under the current tests.
- Existing destination: no overwrite, no deletion; a racing destination published by another process remains.
- Sync failure before publication: no new backup path and no retained partial SQLite files.
- Sync failure **after** link: no newly published destination remains if it still aliases our temporary file; a racing replacement is never deleted. Error is propagated.
- The original source database is not opened for writing, migrated or deleted. No changes to historic `TOMAN` and target `RIAL` separation.

## Progress and surprises / decision log

- 2026-11-01: `VERIFIED` for this scoped defect. Baseline `python -B -m unittest tests.test_standalone_accounting_backup tests.test_standalone_accounting_restore` returned **64 tests OK** before modification.
- Red test: the two new publication-failure cases returned **1 failure and 1 pass** (`test_directory_sync_failure_revokes_own_new_publication` failed because the destination still existed).
- After guarded rollback: both new tests **2/2 OK**. Adjacent command `python -B -m unittest tests.test_standalone_accounting_backup tests.test_standalone_accounting_restore tests.test_standalone_accounting_identity_backup tests.test_standalone_accounting_auto_backup` returned **81 tests OK**. `git diff --check` returned exit code 0.
- Restore already uses `os.path.samefile` to ensure it only removes its own publication on a later failure; reuse the narrow approach instead of rewriting backup flow.
- The `samefile`-then-`unlink` check is not an atomic compare-and-delete operation: a replacement arriving in the interval between those two system calls remains a theoretical concurrency risk. The tests cover replacement *before* the ownership check. Production filesystem races and power-loss durability were not tested.

## Validation and acceptance

- A synthetic test must fail before the correction and pass after it. Test one case where the publish destination still belongs to this backup; another where it has been replaced by unrelated data.
- Existing backup and restore and neighboring identity/auto-backup suites passed as recorded above. `git diff --check` passed. Files modified by other workers in this shared worktree were preserved.
- Out of scope: real backup/recovery of user accounts, Parsian data, installer, site release, crash/power loss durability test, live migration, Git commit or push.
