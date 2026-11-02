# Madar Desk 1.0.9 cumulative installer: isolated implementation plan

## Purpose and decisions

User requirement: a single 1.0.9 Windows setup must deliver the full current
application from any installed 1.0.4, 1.0.5, 1.0.6, 1.0.7 or 1.0.8 without
sequential patch installs. Keep existing desktop/host profiles, standalone
accounting SQLite, WAL files and backups intact. Preserve rollback access to
older executable versions. This source task cannot validate live financial
schema migration, a real installer, a signed EXE or installed-user acceptance.

Owned worktree: `D:\CoS-Test\madar-20261103-cumulative-installer-worker5`,
baseline `f4d8f7c22af675b570603c44d72cf7c295103e33`. Source edits only;
no Git push, real installation, profile/database writes or application build.

## Existing behavior and design

- `scripts/build_p0_release_candidate.py` already builds a *full* Vite bundle
  into a PyInstaller one-file application and packages it into a versioned
  Inno installer. Historical wrappers 1.0.5–1.0.8 are release-specific.
- `scripts/madar-update.iss` backs up `{userappdata}\MadarDesk` via a verified
  preflight and activates a version pointer after checking the EXE digest.
  The installer does not own finance, host or backup data.
- `scripts/Madar-Activate-Version.ps1` currently permits lower versions to
  activate, including when run by an earlier 1.0.4 setup. The versioned Inno
  file rule may overwrite an existing same-version executable.
- `madar_update.py` has a build-time current-version constant; source and
  release metadata must agree at the final integration build.

## Work items and parity specification

1. Introduce synthetic upgrade acceptance for each 1.0.4–1.0.8 profile,
   preserving exactly all synthetic desktop files, SQLite/WAL/SHM bytes,
   local/host profiles and prior backup archives while activating one 1.0.9
   executable. Assert one verified new ZIP and intact previous EXE/pointer.
2. Assert old setup cannot downgrade after 1.0.9; preserve explicit manual
   rollback, with target EXE checksum and safe path validation.
3. Prevent same-version installer overwrite. Existing matching EXE can be
   activated idempotently; conflicting EXE fails hash activation.
4. Add a frozen 1.0.9 full-build wrapper checking source package/update
   versions, requiring a signed Microsoft WebView2 prerequisite, preserving
   immutable artifact names and an exact SHA256 sidecar.
5. Run RED-before and PASS-after synthetic tests, neighboring update tests,
   PowerShell parser validation, Python compile and diff check.

## Security, finance and validation boundaries

No finance migration/conversion happens in setup: canonical rial ledger,
profiles, credentials and Parsian copies remain untouched. A separate data
schema migration requires an isolated reconciliation with financial invariants
before operational use. Only `{app}/versions/1.0.9`, launch files and the
version pointer may be changed by the installer; backup files are append-only.
Release acceptance still requires source feature integration, signed customer
binary, two-PC data-preservation rehearsal and manual rollback smoke test.

## Progress and observed evidence

- **VERIFIED (synthetic only)**. 2026-11-03: the new cumulative acceptance
  suite passed for each prior version 1.0.4 through 1.0.8. It verifies exact
  source ZIP contents, synthetic finance SQLite/WAL, host and local profile
  bytes, pre-existing backups, SHA rejection, version monotonicity and a
  separately requested manual rollback.
- Existing `tests.test_madar_update_contract` and `tests.test_madar_update`
  passed together with the new suite (23/23). Portable installer and restore
  guard regressions passed (18 passed, 1 optional binary skipped).
- Release metadata on this worktree now aligns `package.json`, both
  `package-lock.json` version fields, `madar_update.CURRENT_VERSION` and the
  `npm run dist` entrypoint to **1.0.9**, with a source-only test gate.
- **BLOCKED for actual build:** final integration, dedicated QA approval,
  signed prerequisite and actual binary creation remain under the prime
  release owner; this worker did not run `npm run dist` or a binary installer.
- Inno setup has not been compiled or installed during this worker task;
  real user/host/SQLite migration and installation remain unverified.

## Surprises / decisions

- The codebase contains previous 1.0.2–1.0.8 release scripts; 1.0.9 must
  select the latest *integrated* source instead of copying a historical EXE.
- Prevent accidental downgrade in the activation helper, while retaining
  explicit owner-directed verified rollback via an opt-in switch.
- Older **already-distributed** installer binaries embed their own scripts;
  a new activation helper cannot retroactively change those older EXEs. The
  monotonic guard applies to this new helper and future builds that include it.
