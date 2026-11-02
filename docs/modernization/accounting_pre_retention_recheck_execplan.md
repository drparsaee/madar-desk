# MD-O15 | Recheck automatic backup before retention | ExecPlan

## Scope and decision

The owner requires that an older accounting backup is not removed unless a newer complete, restorable set has been verified. Work on LocalForge `main` with disposable synthetic SQLite data only. Do not touch real profiles, the Parsian test database, installed EXEs, or release artifacts. Preserve unrelated untracked research folders.

## Defect hypothesis and red test

After publishing and verifying a new completion manifest, `AutomaticStandaloneBackups.backup_now()` enumerates managed files and starts deleting old copies without revalidating the new manifest. A concurrent transfer, tamper or storage error during that interval may leave the new set unrestorable while retention removes the last complete copy. Use a deterministic test hook that damages only the new synthetic manifest during enumeration, then assert that the old backup survives and rotation fails closed.

## Minimum compatible correction

Recheck the newly published completion manifest and all declared members after enumeration, immediately before the first deletion. Preserve normal rotation order, existing no-clobber semantics, manifest format and manual legacy restore. This reduces a known time-of-check/time-of-use window but does not prove atomicity against concurrent writes or power failure.

## Validation gates

1. Confirm the new regression fails on current source before correction.
2. Confirm it passes after the minimal correction, along with adjacent backup/restore tests.
3. Run the complete isolated Python and Node/React suites plus Vite build; inspect diff and source/remote SHA.
4. Only if all required gates pass, commit and push to private LocalForge `main`, then read back the remote SHA. If authentication or tests fail, do not claim delivery.

## Execution evidence

- Baseline main: `4f00fd9e82e0605f64d6980107236b9ebcd07658`. `git ls-remote origin refs/heads/main` returned the same SHA on the successful retry; an earlier read failed authentication and was not counted as verification.
- RED: `python -B -m unittest tests.test_standalone_accounting_auto_backup.AutomaticBackupTests.test_new_backup_corrupted_during_enumeration_cannot_retire_last_good_copy -v` exited 1, one failure: `BackupManifestError not raised`. The synthetic manifest was damaged after the first successful publication check, while retention still proceeded.
- GREEN adjacent: four backup/identity/restore modules completed 90 tests, exit 0; `git diff --check` exit 0.
- Complete source QA: `npm test` exit 0. Isolated Python 170/170 executed modules, 1631 reported tests, 2 skipped, 2 expected failures, zero unexpected failures/errors/timeouts; Vite build passed; Node/React/Playwright 530/530 passed, zero skipped/failures.
- The change is a second pre-retention validation of the new automatic set, not an atomic protection against concurrent writes after that check. Packaged EXE, real user restore, physical LAN, power-loss durability and actual Parsian test data were not exercised.
- Commit/push and remote readback are separate delivery gates; record their actual outcome from Git rather than treating these source tests as deployment evidence.
