# ExecPlan | Preserve periodic backup bytes on index publication failure

## Decision and scope

Main baseline `6f0da57` on 2026-11-01. This isolated worktree changes only `host_backup_scheduler.py`, its synthetic tests and this plan. No installed app, real user profile, Parsian backup, account ledger or live database is touched. The host-only scheduled backup is explicitly partial, not a full recovery archive.

## Defect and red reproduction

`HostBackupScheduler._rotate` validates indexed retired files, deletes their bytes and only then calls `_publish_index` with the retained subset. A failed index publication can therefore leave the previously durable index referencing a deleted backup. On a changed revision, `run_once` first publishes the unpruned index and then rotates, so a second publication failure can occur after destructive pruning. The synthetic test injects failure into that second publication, after a valid older backup exists, and asserts that the original bytes survive.

## Smallest safe change

After validating retired files, publish the trimmed index before unlinking retired snapshots. If publication fails, do not delete. If deletion fails after publication, an unindexed orphan may remain, which is preferable to deleting a snapshot without a durable index update. Preserve all filename/path and ownership checks, deduplication, retention limit on success and host permissions.

## Validation and release gates

1. Run original scheduler module under disposable APPDATA/LOCALAPPDATA/TEMP/HOME/USERPROFILE.
2. Demonstrate new regression fails before fix, then passes after fix.
3. Run adjacent backup/recovery suites and full isolated source-level suites, including JavaScript if environment supports them; distinguish skip and failure counts.
4. Review diff, commit only scoped files, integrate with up-to-date main and push only after actual green checks. Never claim operational recovery or EXE acceptance from synthetic tests.

## Progress

- Baseline scheduler suite: 15/15 tests passed, exit code 0, isolated temporary profile.
- RED confirmed: the new regression failed with `FileNotFoundError` reading the retired snapshot after the second index publication was made to fail. The prior code had deleted its bytes.
- GREEN confirmed: `test_rotation_index_failure_keeps_retired_backup_bytes` passed with the ordering fix. The seven-module backup/recovery/restore run passed **106/106** tests after adding the `tests` import path required by the existing `test_automation_full_recovery` fixture. An initial adjacent invocation without that path had one import error, not a product assertion failure.
- Full Python source audit at the original `6f0da57` baseline plus this patch: **168/168 executed modules passed**, **1,608 tests reported**, 2 skipped, 2 expected failures, 0 unexpected failures/errors/timeouts, runner exit code 0, opt-in packaged EXE test excluded. Report: temporary synthetic QA JSON outside Git.
- An initial Vite production build succeeded. The initial Node UI run failed in browser cases because Windows Chrome refused Playwright's temporary remote-debugging profile when `USERPROFILE` was rewritten; that initial run was **not green**. After rebasing on main `c22e328` (the safe browser-compatible runner), the **complete `npm test` returned exit 0**: Python **169/169 modules passed**, **1,618 reported tests** (2 skipped, 2 expected failures, zero unexpected failures/errors/timeouts), Vite build PASS, and Node/React/Playwright **530/530 PASS**, zero skipped. The new regression is included. The browser runner preserves Windows USERPROFILE identity only for Chrome compatibility while isolating APPDATA, LOCALAPPDATA, TEMP, HOME and Playwright's actual browser profile.
- Real crash/power-loss durability and installed EXE acceptance remain untested.
