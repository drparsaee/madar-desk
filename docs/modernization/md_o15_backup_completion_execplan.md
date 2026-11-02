# MD-O15 | Automatic accounting backup completion manifest | ExecPlan

## Purpose / user decision / exclusions

Prevent an interrupted transfer of an automatic accounting backup from silently restoring the SQLite ledger without its identity or template registry. Worktree: `D:\CoS-Test\madar-desk`; initial main HEAD `fa5a693ea526231d91c5d8f11171e29f25e6d9f3`. No real profiles, Parsian backups, installed EXEs, or production files are inputs. The explicitly invoked manual one-file SQLite backup remains restorable.

## Existing behavior

`standalone_accounting_auto_backup.py::AutomaticStandaloneBackups.backup_now` publishes an automatic SQLite file then optional `.users.json` and `.templates.json` companions. `standalone_accounting_restore.py::restore_standalone_accounting` previews only existing companions; an omitted `.users.json` is currently interpreted as an old one-file backup. Rotation deletes old SQLite first, then companions. The CLI takes explicit absolute paths and two acknowledgements. Existing synthetic restore tests exercise no-clobber and rollback.

## Plan of work

1. Add a synthetic regression demonstrating omission of the identity/template after automatic backup, plus interrupted manifest publication and manual legacy compatibility.
2. Introduce a small versioned completion manifest adjacent to *every new automatic* `.sqlite3` snapshot; include strict expected filenames, sizes and SHA-256 for SQLite and each saved companion. Publish the manifest only after all files validate and sync. Never treat an automatic-pattern SQLite lacking a valid manifest as a legacy manual snapshot.
3. Before restoring, validate the manifest and every declared/undeclared companion. Revalidate before publishing any restored file. Keep existing destination no-clobber and rollback logic; retire managed manifests only after the corresponding SQLite retires.
4. Run focused, adjacent and full safe regression on synthetic tests; review diff, SHA and LocalForge main before any push.

## Parity specification

- Manual SQLite-only backups with nonautomatic names restore exactly as before.
- Automatic SQLite-only backups receive a manifest recording just the SQLite, and restore with identical revision/view.
- Automatic files with a saved identity/template require those exact byte-identical companions. Missing, extra, modified, symlinked or malformed declared files fail before destination publication.
- Missing, malformed or unrecognized-version manifests on automatic-pattern names fail closed. A copy interrupted before manifest publication remains unrestorable until completed.
- Rotation preserves newest validated backups, never discards a retained companion after a failed SQLite deletion, and does not delete unrelated files.
- No modification of accounting currency, data, event schema, identity secrets, roles or the manually backed-up legacy workflow.

## Progress

- VERIFIED: Baseline `python -B -m unittest tests.test_standalone_accounting_auto_backup tests.test_standalone_accounting_identity_backup tests.test_standalone_accounting_restore -q` passed 52/52 before implementation.
- VERIFIED: Four new red cases produced three failures and one error, including acceptance of missing identity and template companions. After implementation and interruption/undeclared-companion coverage, the adjacent run passed 58/58.
- VERIFIED: The first safe-run attempt stopped in Python after 169/170 modules passed, one unexpected error and no assertion failures. Its diagnostic was in a cleaned disposable folder; the precise transient module error is not established. An independently recorded Python rerun passed all 170/170 modules, 1630 tests reported, 2 skipped and 2 expected failures, 0 unexpected errors/failures.
- VERIFIED: A subsequent full `npm test` passed: 170/170 Python modules (1630 reported, 2 skipped, 2 expected failures), Vite build, and 530/530 serial Node tests with zero skips/failures.
- IN PROGRESS: final staged diff review, commit, private LocalForge remote SHA verification. Packaged EXE and operational migration acceptance remain outside this change.

## Surprises / decisions

- 2026-11-02: A marker-only manifest is insufficient for partial transfers: it must declare companion names, sizes and hashes and itself be atomically published last. Backward compatibility is limited to the explicit nonautomatic manual SQLite format.
- 2026-11-02: The first integrated Python safe-run produced one unexpected, unlocalized error; the rerun of the complete isolated Python suite and the subsequent full official source QA succeeded. Do not construe this as proof of zero intermittent infrastructure flakes.

## Validation and acceptance

Targeted `python -B -m unittest tests.test_standalone_accounting_auto_backup tests.test_standalone_accounting_identity_backup tests.test_standalone_accounting_restore -q`, broader synthetic suites, `git diff --check`, and local/remote SHA comparison if pushed. No installed-program, Parsian, real-user, disaster/power-loss or physical two-device test is included.
