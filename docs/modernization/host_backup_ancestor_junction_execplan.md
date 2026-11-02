# ExecPlan | Host backup parent-junction boundary

## Purpose / owner decision / exclusions

- Baseline: `6606ed6288b9ef0a3f820f2102aedfcb28bd7da1` on canonical LocalForge `main` in `D:\CoS-Test\madar-desk`; remote `refs/heads/main` matched before editing.
- MD-O15 and P0 data preservation require scheduled host backups to stay inside the explicitly selected data root. Do not follow a junction in an ancestor of that root into another directory.
- Scope: `host_backup_scheduler.py`, `tests/test_host_backup_scheduler.py`, this ExecPlan. No real APPDATA, Parsian, installed EXE, network service or customer profile.

## Existing behavior / entry points

- `HostBackupScheduler.run_once()` calls `_folder()` before `createLocalBackup()` and retention. `_folder()` checks whether the immediate `data_root` and backup folder are links, but not whether a parent of `data_root` is a Windows junction.
- A path such as `temporary/junction/company/backups` may therefore traverse a junction while the `company` and `backups` components are ordinary directories. This is a source-level hypothesis until a synthetic Windows junction test reproduces it.
- Existing baseline: `python -B -m unittest tests.test_host_backup_scheduler -q` completed 16 tests, exit 0, with disposable APPDATA/LOCALAPPDATA/USERPROFILE.

## Work plan / parity specification

1. Create a real temporary Windows junction in a disposable test directory and assert `run_once()` rejects the ancestor redirect before backup publication. Observe RED on baseline.
2. Check all ancestors of the host data root with the existing `_linked()` predicate. Keep normal local folders, JSON/SQLite backup format, lock, index, retention and host ACL unchanged.
3. Run the targeted host suite, neighboring backup tests, the safe project-wide Python/Node/React/browser/build gates, Python syntax and `git diff --check` with synthetic profiles.
4. Commit/push only after the relevant regression gates pass; compare remote SHA to local SHA. Leave unrelated untracked research untouched.

## Progress / surprises / decision log

- 2026-11-01: `RED` reproduced with a real disposable Windows `mklink /J` ancestor: `python -B -m unittest tests.test_host_backup_scheduler.HostBackupSchedulerTests.test_parent_junction_of_host_data_root_is_refused -v` reported **1 test, 1 failure**, because `HostBackupError` was not raised and the redirected synthetic folder was accepted.
- `GREEN`: `_folder()` now checks `(data_root, *data_root.parents)` with existing `_linked()` before making any backup directory. The five-module adjacent command `python -B -m unittest tests.test_host_backup_scheduler tests.test_backup_scope_truth tests.test_standalone_accounting_auto_backup tests.test_standalone_accounting_backup tests.test_standalone_accounting_identity_backup -q` passed **70/70**, zero failures. Python compile and `git diff --check` returned zero.
- The first 16-test host module baseline passed before editing. The Windows junction regression executed (not skipped) on Python 3.12.10; a temporary company profile and a temporary junction were the only test data.
- `VERIFIED`: the complete safe `npm test` runner exited **0**. Python **169/169 modules**, 1,621 tests, 2 skips, 2 expected failures, zero unexpected failures/errors/timeouts; Vite build passed; Node/React/Playwright **530/530**, zero skipped/failed. The separate packaged-EXE test was deliberately excluded by the runner.
- Two independent read-only worker audits reported additional MD-O02 and MD-O15 candidates. Their reported reproductions are preserved as **unverified integration leads** in `p0_audit_followups_20261101.md`; neither was silently modified in this change.

## Validation / acceptance and rollback

- Expected: normal synthetic host backup works; any ancestor symlink/junction fails before a backup is written; no changes to actual user or financial data.
- Negative: no customer restore, real LAN host, crash/power-loss, installed application, migration, or production release is tested here.
- Rollback is a source revert of this bounded commit, not a financial data restore. Preserve any real installations and archives unchanged.
