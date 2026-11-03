# Madar Desk 1.0.10 cumulative release contract

## Purpose and scope

Prepare the source-only release metadata, immutable cumulative Windows build
entry point and synthetic regression tests for 1.0.10, to be cherry-picked
after the new Focalboard-inspired board and prior UI fixes have been integrated.

Base: canonical LocalForge main `45f3a596abe1496147a0e2b2e453b8a93de80624`.
Worktree: `D:\CoS-Test\madar-20261103-cumulative-installer-110-worker5`.
Only packaging, metadata, tests and release documentation change in this task.
No application features, operational data, installation, real binary build,
GitHub publication or main-branch writes are part of this work.

## Existing contract and design

- The existing 1.0.9 entry point `scripts/build_integrated_v109.py` and its
  release artifacts remain unchanged. `scripts/build_p0_release_candidate.py`
  builds the *entire* Vite app and PyInstaller program before compiling a
  versioned QA and production Inno setup. It demands a Microsoft-signed
  offline WebView2 prerequisite and refuses to overwrite existing outputs.
- The current Inno payload installs just the new versioned program EXE and
  a launcher, runs a verified snapshot of the offline desktop profile before
  activation, and verifies binary SHA256. It never owns finance, host or
  customer backup files. Existing `onlyifdoesntexist` and monotonic activation
  remain intact.
- `madar_update.py` expects the exact file name
  `Madar-Desk-1.0.10-Setup.exe` for a GitHub release tagged `v1.0.10`;
  providing the filename contract does not publish such a release.

## Changes

1. `scripts/build_integrated_v110.py` gives 1.0.10 separate immutable output
   names, a verified post-build SHA256 release descriptor, and rejects any
   conflicting program/QA/setup/manifest output before starting a build.
2. `package.json`, both root `package-lock.json` version fields, and
   `madar_update.CURRENT_VERSION` agree on 1.0.10. The default `npm run dist`
   points to the new full builder. Source consistency is checked before build.
3. `tests/test_cumulative_110_update.py` uses only disposable Windows
   folders to simulate direct upgrades from 1.0.5, 1.0.6, and installed 1.0.9
   to 1.0.10. It verifies full, checksum-checked desktop ZIP snapshots;
   unchanged synthetic SQLite journal/WAL/SHM, host and local profiles,
   attachments, older backups and prior EXE; rollback and integrity refusal.
4. Older 1.0.9 source tests remain usable for regression verification; current
   metadata expectations follow the new version while the 1.0.9 builder stays
   frozen.

## Expected release behavior and rollback

The same 1.0.10 EXE is installed for all supported starting versions without
intermediate installers. A release-specific folder, pointer and prior-program
retention support explicit recovery. Re-running the same installer does not
overwrite an existing binary. Automatic downgrade is refused; operator
rollback requires the old executable's expected hash and the explicit
`-AllowRollback` flag. Existing profiles and finance transactions are not
converted by the installer, so a future financial schema conversion requires
its own separate reconciliation and approval.

## Progress and verification

- **VERIFIED**: initial new 1.0.10 tests were red against baseline source
  (missing builder and stale version metadata), demonstrating a genuine gate.
- **VERIFIED (synthetic only)**: `python -m unittest
  tests.test_cumulative_110_update tests.test_cumulative_109_update
  tests.test_madar_update_contract tests.test_madar_update
  tests.test_portable_installer tests.test_release_restore_guard -q` passed:
  **49 tests run, 48 passed, 1 skipped** (optional historical RC binary).
  Python `py_compile` for the new builder and tests passed, as did
  `git diff --check`. The pre-existing 1.0.9 tests remain green.
- **NOT RUN**: PyInstaller, Inno Setup compilation, Windows installer
  execution, signing, deployment, native GUI/host integration QA and real
  customer financial migration. The prime must perform full final QA after
  cherry-picking and integrating the UI/board changes.
