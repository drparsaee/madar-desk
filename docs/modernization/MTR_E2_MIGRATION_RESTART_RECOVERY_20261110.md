# E2 account-lineage migration: bounded restart inspection pilot

Date: 2026-11-10

## Scope and source evidence

Read-only inspection of the current migration module, its synthetic tests,
account-lineage helper, and lan.py. The only new files are:

- **NEW** mtr_account_lineage_recovery_inspect.py
- **NEW** tests/test_mtr_account_lineage_recovery_inspect_20261110.py
- **NEW** this document

The existing migration requires a current authenticated host administrator,
uses an **explicit** private users_path and a new backup in the same
directory, and saves **exact pre-migration bytes** through create-only
os.O_EXCL, fsync and SHA-256 readback before publishing lineages. On an
ambiguous publication/rollback outcome it sets the host's
_delete_recovery_required guard **in process**.

The guard is **not a durable migration-intent file**. A future process
cannot learn that earlier uncertain outcome simply by loading the private
registry. The backup itself has no signed creation receipt, transaction
journal, or separately authenticated file identity.

## Read-only operator API

    from pathlib import Path
    from mtr_account_lineage_recovery_inspect import inspect_account_lineage_recovery

    assessment = inspect_account_lineage_recovery(
        registry_path=Path("<operator-selected absolute private users.json>"),
        backup_path=Path("<operator-selected absolute existing lineage backup>"),
        expected_backup_sha256="<previously recorded trusted 64-hex SHA-256>",
        # expected_backup_size=<positive byte count>  # optional
    )

**Do not run this on live/private accounts as part of automated QA.**
The tests use only TemporaryDirectory and synthetic accounts and password
hashes. The API does not derive implicit paths, call LanService, authenticate,
publish identities, create a backup, perform a restore, or write files.

The result contains classification, reason codes, sizes, SHA-256 digests,
and counts, but never raw usernames, lineages, password hashes, tokens,
or private account details. Every classification returns:

    readOnly = true
    automaticRestoreAllowed = false
    safeToResumeHost = false
    manualOperatorReviewRequired = true
    backupProvenanceCryptographicallyProven = false

### Classification rules

| Classification | Requirements | Non-proven properties |
|---|---|---|
| VERIFIED_CONSISTENT | Both files safe and schema-valid; trusted expected backup SHA matches; identical username keys and all account fields except newly added lineages; every previously missing lineage now present and unique | Actual backup origin, live memory, host publication, permission to log in |
| RESTORE_REVIEW_REQUIRED | Valid files but missing independent digest; original pre-migration bytes still current; or partial lineage addition | Migration completed, safe automatic restore |
| BLOCKED | Missing/linked/oversized/corrupt files; wrong digest/size; changed username, existing lineage, credentials, roles, grants or other fields; duplicate/invalid lineage | Any safe recovery path |

**VERIFIED_CONSISTENT is only structural agreement of the two selected files**,
plus the caller-supplied digest. It does NOT cryptographically prove the
backup's provenance or the authenticity of that digest. A pre-recorded digest
must have an independently trustworthy origin; without one the maximum
classification is RESTORE_REVIEW_REQUIRED.

## File and data boundaries

The inspector rejects non-absolute paths, parent-traversal aliases, the same
path, different-parent files, symlinked or junction parent/files, hardlinks,
and nonregular files. Bounded inputs match the migration's 32,000,000-byte
per-file and 10,000-account limits, with project-list caps. It checks path
and opened-descriptor identity before and after the bounded read, hashes
each file, and independently re-reads both before classification. This is
still **not an atomic two-file snapshot** against privileged concurrent
mutation.

JSON must be UTF-8 with unique keys at every nesting level and no nonfinite
numbers. Account keys and embedded usernames must match; roles, password
hash format, project scopes, finance permission flags, and existing
accountLineage must be valid. Lineages are canonical lowercase nonzero
32-hex strings and unique per registry. The full account record is compared
exactly **excluding only accountLineage**, not just names/roles, to catch
credential or permission rewrites. Existing lineages must never change.
Only new unique lineages on originally legacy accounts can justify a positive
structural migration classification.

Filename, file size, modification time, and equality alone **cannot prove**
that a backup was actually created with O_EXCL, fsynced in the original
process, or retained unmodified. In particular, comparing two attacker-chosen
files, even with a freshly calculated SHA, does not authenticate either.

## Synthetic test evidence

    py -3.12 -B -m unittest -q tests.test_mtr_account_lineage_recovery_inspect_20261110
    # Ran 21 tests in 1.503s
    # OK, exit 0

Positive and negative cases cover exact lineage-only migration; missing
expected digest; unchanged/partial states; hash and size mismatches; missing,
empty and oversized files; relative/matching/different-parent paths;
symlinks and hardlinks; changed usernames, passwords, roles and grants;
duplicate/invalid/deleted/replaced lineages; malformed or duplicate JSON;
nonfinite JSON, and simulated changes between reads. Link-creation tests visibly
skip only if the OS denies creation; in this run all 21 tests passed, no skips.

No real profile, account, service, network, installer, finance file, commit,
push, deployment or original migration source was touched.

## Remaining manual release gate

An authorized operator must independently establish backup origin and digest,
review original host-account authority and project assignments, check
pending deletion journals and other recovery guards, then decide if a
manual restore is necessary. No automatic restore, remap, lineage generation,
login or restart is authorized by any status. The inspector cannot reconstruct
the crashed process's private users-memory state or invent a missing backup.
