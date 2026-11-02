# ExecPlan | Crash-safe composite accounting restore

## Purpose and scope
Repair `docs/modernization/restore_crash_publication_open.md` on baseline `e388436cd6410211d777bf96df848427fbafa920`. Only the explicit offline `standalone_accounting_restore.py` path and synthetic regression fixtures are in scope. No production profiles, live Parsian data, installed binaries or monetary conversion.

## Existing behavior
The restore validates the SQLite source and optional completion manifest, stages a verified copy, and hard-links the SQLite destination before either optional JSON companion. A kill between these links exposes a ledger without identity and leaves the no-clobber retry blocked. In-process exceptions attempt inode-guarded rollback, but `os._exit` cannot run `finally`.

## Work plan and parity
1. Record a synthetic RED abrupt-exit test for the existing ordering and run existing targeted suites.
2. Stage the verified SQLite and declared companions in a private, exclusive destination-side transaction directory. Persist a source-specific ready record and use a process-held lock to reject overlapping restores.
3. On retry, verify source fingerprint, ready record, staged checksums and already-published hard-link identities; refuse mismatched/foreign files. Publish companions first and the SQLite ledger last. Roll back only proven owned links on ordinary exceptions.
4. Exercise hard termination after every link, failed links, foreign replacements, retry, successful legacy manual one-file restore, and concurrency. Run the official isolated safe QA, inspect diff, then commit/push to private LocalForge only if all pass.

## Acceptance / restrictions
No ledger becomes visible before every declared companion. A crash after an earlier companion or after SQLite publication can be finished by rerunning the same explicit restore; no unrelated destination file can be overwritten or deleted. Completed restores remain no-clobber on a *new* attempt; an interrupted transaction with a verified journal can be resumed. Malformed/incompatible journals fail closed. Physical power-loss durability, installed EXE and real-profile restore remain unverified.

## Progress
- VERIFIED: RED `python -B docs/modernization/audits/restore_crash_publication_red.py` (with repository `PYTHONPATH`) failed 1/1, exposing the bare destination SQLite.
- VERIFIED: pre-change adjacent suites `python -B -m unittest tests.test_standalone_accounting_restore tests.test_standalone_accounting_auto_backup tests.test_standalone_accounting_identity_backup tests.test_mohsen_r10_template_restore -q`: 63/63 passed.
- VERIFIED: post-repair historical crash audit 1/1; new kill/retry suite 6/6; adjacent accounting backup/restore tests 69/69 total.
- VERIFIED: `npm test` exit 0: 172/172 isolated Python modules (1,641 tests; 2 skipped, 2 expected failures, no unexpected failures/errors); Vite build; Node 530/530 tests (0 skipped/failures).
- TODO: final diff inspection, commit, LocalForge fast-forward push and SHA comparison.
