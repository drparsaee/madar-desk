# Madar Desk | TLS hardening follow-up, 2026-11-01

**Status: source hardening in progress; NOT a release approval.** The installed
Windows customer program remains version 1.0.2; none of the changes in this
document have been installed into that program or deployed to customers.

## Changes made in the development workspace

- `lan.py`: plaintext HTTP sockets now require a literal loopback bind. A LAN
  listener accessible on `0.0.0.0`, an interface IP, or IPv6 wildcard needs
  configured TLS before a socket is opened.
- `native_app.py`: GUI hosting needs TLS certificate/key; previously saved
  insecure network-host settings fail closed on app restart. Clients refuse
  remote non-loopback HTTP *before* clearing any offline cached account and
  before sending login credentials or Bearer tokens. HTTPS verification is
  selected from a parsed URL scheme so mixed-case HTTPS cannot bypass pinning.
- `src/features.jsx`: advanced LAN-host UI requires PEM certificate and key.
  Plain HTTP remains supported only for local loopback development/tests.
- Added targeted negative tests for insecure binds, login and token
  transmission, certificate mismatch, and legacy insecure-host recovery.

## Evidence, with scope

- Python LAN-related targeted suite: 30 tests / OK (before latest HTTPS
  scheme case fix); follow-up native TLS / LAN TLS tests: 17 tests / OK.
- JS LAN UI suite: 10 tests / 10 pass. Full JavaScript sequential run:
  528 tests / 528 pass.
- After correcting several historical synthetic fixtures, an isolated
  combined Python run of native persistence, accounting/purchase, LAN TLS,
  API and updater-contract modules completed: **99 tests / OK**. This is
  selected coverage, not full-regression acceptance.
- Vite 6.4.5 production frontend build completed; emitted a non-blocking
  warning for a JavaScript chunk above 500 kB.
- Full Python discovery run, **before fixture follow-up changes**:
  1581 tests, 11 failures, 167 errors, 3 skipped, 2 expected failures.
  Do not describe it as green. A large group used pre-1.0.1 default demo data
  and needs explicitly populated *isolated* test fixtures. Other issues remain
  unclassified. Several fixture suites have subsequently been corrected, but
  full regression needs a fresh complete run.
- Limited pattern scan `scripts/audit_git_source.py`: 900 tracked files,
  321 scanned source files, 0 findings. This is not comprehensive.
- Gitleaks 8.30.1 scanned 64 Git commits (~8.51 MB) and reported one
  `private-key` match at `tests/test_lan_tls.py` (public disposable fixture,
  not intended for production). Do not suppress or claim no historical leaks
  on this evidence alone.

## Release blockers

1. Full Python regression still needs to pass or remaining defects need an
   explicit risk-based disposition; currently not established.
2. Package a **new** version (1.0.3 or later), never overwrite published 1.0.2.
   Validate offline setup, update/rollback, preserved user data and GUI in
   isolated profiles before modifying the real installation.
3. Exercise certificate lifecycle and client pin changes on an actual LAN;
   loopback tests are not an external MITM or multi-PC penetration test.
4. Historical accounting data reconciliation, Windows compatibility matrix,
   and secure operational-data backup are separate open requirements.
5. Digitally signed installer is expressly deferred by user decision.

## Safety boundary

No actual `%APPDATA%/MadarDesk` data, historical accounting profiles, Parsian
backups, or previously installed 1.0.2 executable were modified during this
hardening work. Third-party Trello extraction folders remain intentionally
untracked due to unresolved redistribution rights.
