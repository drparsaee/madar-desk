# ExecPlan | Preserve accounting backup companions if retirement fails

## Decision and baseline

Main SHA `757a038897f5e752c75dc72f58883666edad896f` on 2026-11-01. Protect the accounting backup contract in `PROJECT_CONTEXT.md` (MD-D08 and MD-O15). Scope is limited to `standalone_accounting_auto_backup.py`, its synthetic unit tests, and this ExecPlan. Existing unrelated untracked research files, real Windows profiles, Parsian data, installed EXEs and operational accounting databases are excluded.

## Defect to characterize

`AutomaticStandaloneBackups.backup_now()` validates a new SQLite snapshot and optional template/user companions before retention. While retiring an old backup, it currently unlinks its `.templates.json` and `.users.json` companions *before* unlinking the old `.sqlite3`. If deletion of the old SQLite file fails, the still-present old backup loses its companions and may no longer restore its saved identities/templates. A filesystem error can thus turn a previously complete recovery set into an incomplete one.

## Test-first execution

1. Create an entirely synthetic SQLite accounting source and two sidecars in a disposable directory; set retention to one.
2. Inject a filesystem failure on unlinking only the retired SQLite backup, after a new validated backup exists. Before the fix, assert that the original backup and both companions must survive; capture the red result.
3. Move the SQLite unlink before companion unlink for retired copies. A failure before deletion must leave the full old set intact; successful retirement still removes all three files. A failure after SQLite deletion may leave orphan companions, preferable to destroying companions of an existing restorable snapshot.
4. Run the targeted backup/identity/template/restore tests, then the full safe `npm test` launcher with synthetic profiles, Vite build and Node UI checks. Review `git diff --check` and commit/push to LocalForge main only after actual green gates.

## Acceptance limits

This is a bounded source-level fault-injection regression, not a Windows power-loss test or proof of complete operational recovery. No deployed version is modified. If validation is incomplete, do not push.

## Progress

- Baseline `tests.test_standalone_accounting_auto_backup`: **12/12 passed** under a disposable Windows profile.
- The first test fixture used an incomplete print-layout payload and failed template validation before exercising retention; it was corrected to use a valid synthetic issuer profile. This was a fixture error, not the red reproduction.
- **RED reproduced** against the original rotation order: the new test raised `FileNotFoundError` reading the retired `.templates.json` after an injected `PermissionError` on SQLite unlink. The old SQLite still existed, but its companion was gone.
- **GREEN** after moving the SQLite unlink before the two companion unlinks: eight adjacent accounting backup, identity, template, recovery and exit modules ran **72/72 tests OK** (exit 0) in a disposable profile. Synthetic expected-error log messages are not test failures.
- Full safe `npm test` **exit 0**: Python **169/169 modules passed**, **1,619 tests reported**, 2 skipped, 2 expected failures, no unexpected failures/errors/timeouts; Vite build passed; Node/React/Playwright **530/530 passed**, zero skipped. Opt-in packaged EXE test excluded.
- `git diff --check` returned exit 0; Windows Git printed LF-to-CRLF working-copy conversion warnings, not whitespace errors.
- LocalForge commit/push status must be recorded separately after execution; actual Windows release and customer migration remain blocked on real acceptance.
