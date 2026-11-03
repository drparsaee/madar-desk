# Madar Desk 1.0.11: cumulative Planner namespace fix

## Purpose

Prepare a **new** immutable installer carrying the Planner account-ID fix from
LocalForge commit `f112b709343c520bf5de895b8881934cfdf94f55`. The already
published `v1.0.10` installer is immutable and **not** repaired in place.

`plannerIdentity` emits a JSON-stringified namespace. Native persistence now
validates that exact namespace without changing its browser storage key or
SHA-256-derived private filename. Previously valid plain/Legacy identifiers,
including bracket-prefixed ones, remain valid.

## Installation contract

- Full Vite + PyInstaller program, **not** a Python-file delta.
- New `Madar-Desk-1.0.11-Setup.exe` and separate QA setup.
- Cumulative upgrade from 1.0.5, 1.0.6, 1.0.7, 1.0.8, 1.0.9, or 1.0.10.
- Previous versioned EXE and all operational profile/finance data remain
  installer-unowned; existing preflight snapshot and activation checks apply.
- New release outputs are immutable; mismatched artifacts cannot be silently
  replaced. The 1.0.10 binary and GitHub release must remain unchanged.
- Never force-close running Madar processes. Production installation requires
  the application to be closed and a successful independent snapshot preflight.

## Verification boundaries

- On the parent Planner source commit, the five separate Windows-process test
  passed using actual loopback TCP, one host/four clients, local Planner
  isolation, editor/viewer ACL, stale-write conflict, disconnect/reconnect and
  account switching. **This is not five VMs or physical Ethernet cables.**
- Parent source QA: 191/191 Python test modules (1,742 tests reported, two
  skipped, two expected failures; zero failures/errors), 599/599 Node tests,
  and Vite build pass.
- This release branch adds synthetic upgrade tests including directly from
  1.0.10. They use disposable profiles; they are not real-user migrations.
- The full Windows installer must be independently built, checked and QA-
  installed before any production install or public GitHub release. A source
  test alone is not proof that a packaged executable is correct.

## Completed isolated installer QA (2026-11-03)

- Production setup built, **not installed**: `Madar-Desk-1.0.11-Setup.exe`,
  231,539,163 bytes; SHA256
  `b2d326e31646bcf6d4682a76a2b49b838ed4589ffb20b7456f855216ba1f98e7`.
- Application EXE SHA256
  `4eed0a46973aba6701fbac83e864626b01f58b952fad7e33970197b298b49eb2`;
  verified 14,973,081 bytes. PyInstaller archive lists `planner_persistence`.
- QA installer exit code 0 under the isolated `.qa-inno-v111-cumulative`
  profile. Installed application SHA256 matched packaged application SHA256.
- SHA256 comparison found all **five** synthetic user-profile files unchanged;
  the verified full snapshot preserved their contents. Synthetic SQLite
  `PRAGMA integrity_check` returned `ok`; the synthetic Rial record and
  Planner namespace were readable after install.
- Evidence: `release/Madar-Desk-1.0.11-Setup.release.json` and
  `release/Madar-Desk-1.0.11-QA-evidence.json` in the release worktree. These
  local files are not assertions of a GitHub upload or real user installation.
- **Not completed:** interactive packaged GUI smoke, five real Windows VMs,
  Windows production installation and public release. The existing 1.0.10
  desktop processes were seen running and must not be force-closed.

## Scope and safety

Branch: `release/planner-cumulative-111-20261103` in an isolated worktree.
The LocalForge `main` source commit above has already been pushed separately.
The release worktree must be tested and safely merged before a final release.
Never read or modify real user profiles, Windows LAN configuration, Parsian
backups or other worktrees as part of synthetic acceptance.
