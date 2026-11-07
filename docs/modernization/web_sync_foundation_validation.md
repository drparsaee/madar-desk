# Validation | Web sync foundation

## Baseline

- Starting commit: `d48c09450251c2c74aea64a26c0f20bcebb4ae1e`
- The earlier MVP's 32/32 targeted tests were reported before this continuation;
  they are not the same suite as the new server/browser integration tests.
- Current verified test baseline on 2026-11-06: `npm.cmd run test:web`
  completed with **33/33 tests passed**, zero failed or skipped, after adding
  the production-bundle browser smoke test. The command also built the
  production-mode web bundle successfully.
- `npm.cmd run build` completed successfully for the regular (non-web) Vite
  entrypoints, including `accounting.html`. No Windows installer was created
  or native EXE was launched by these commands.
- `git diff --check` returned exit 0. Git gave LF/CRLF conversion warnings,
  not errors. This is still an uncommitted development worktree.

## Required tests

- IndexedDB v1 upgrade retains existing board state.
- CAS mismatch aborts both local document and outbox mutation.
- Preference and recovery data are stored in IndexedDB, not task-state localStorage.
- Pending snapshot coalesces only before claim; in-flight payload/idempotency key
  remains byte-equivalent while newer edits become a separate pending snapshot.
- Acknowledgement rebases pending onto the new remote revision.
- Uncertain write retries with the same idempotency key.
- Initial upload is blocked until explicit confirmation.
- Existing remote state without a local baseline becomes a preserved conflict.
- 409 preserves local and remote snapshots.
- Same-origin, cookie session, CSRF, JSON content type, ETag, If-Match and
  idempotency behavior are verified with fake fetch.
- Login/session secrets never appear in localStorage, IndexedDB or backup JSON.
- Browser UI reports an unavailable backend without breaking local editing;
  financial settings remain hidden in the browser edition.

## Executed commands and scope

- `npm.cmd run test:web` (33/33 passed, includes unit tests, synthetic browser
  integration, PWA offline startup, 7 server SQLite/API tests, and browser to
  the **real locally launched** Node/SQLite API via Vite's same-origin proxy).
- `npm.cmd run build` (regular Vite build passed, including the accounting
  entrypoint; this does **not** certify the native Windows installer/runtime).
- `git diff --check` (exit 0).
- The real-server Playwright test provisions a synthetic administrator and
  temporary isolated SQLite database, performs an initial write, task/report
  mutation, protected-field checks and remote acceptance by a second browser.
- The production-bundle Playwright smoke serves the built `dist-web` files from
  a same-origin static server, proxies `/api/web/v1` to a separate SQLite API,
  signs in, bootstraps a workspace and reloads the app offline through the
  installed service worker. This exercises the production bundle but does not
  replace validation of the actual Caddy/systemd configuration on Linux.
- The server tests cover cookie/CSRF/session, Origin/Fetch Metadata, ACL,
  revision compare-and-swap, idempotent retries, atomic rollback and visibility
  of committed SQLite state through another connection.
- `node --test tests/web_server_cli.test.cjs` passed its focused test: an
  administrator and workspace snapshot were backed up, an independent
  database was copied from the backup, and account/revision/task content
  were verified there. This is a synthetic single-run rehearsal, not a
  production recovery drill.
- `node --test --test-concurrency=1 tests/label_library.test.cjs
  tests/cover_color_picker.test.cjs tests/board_lane_actions.test.cjs
  tests/cardorder.test.cjs tests/taskops.test.cjs tests/web_server_cli.test.cjs`
  completed with **40/40 passed**; these are shared UI/data regressions plus
  the CLI backup test, not a full desktop GUI test suite.
- `npm.cmd run web:release:package` built a web-only ZIP, extracted it to a
  temporary directory, verified every packaged file against `SHA256SUMS.txt`,
  and wrote an adjacent ZIP SHA-256 file. Independent Python `zipfile.testzip()`
  also returned OK and confirmed the required PWA, API, Caddy, backup and runbook
  entries, including the hosting options note. Final artifact:
  `release/madar-web-pwa-20261106T203414Z.zip`;
  SHA-256: `d9caf955fd50a3927fd76ba73d1219af49b4f4bc4e2c1b5e525b17d4372e30a1`.
  The archive has not been uploaded to a host.
- `bash -n deploy/backup.sh` and `bash -n deploy/smoke.sh` passed under Git Bash.
- PowerShell's AST parser accepted `deploy/package-release.ps1`.
- `systemd-analyze verify` passed for the API service, backup service and timer
  on Debian 13 WSL. Temporary placeholder executables were used only so the
  verifier could inspect unit syntax; no service was started. Caddy is not
  installed here, so the Caddyfile was not parser-validated.

## Pending production acceptance

The local backend is implemented under `server/`; it is not deployed. The
following are **not independently verified** on a real Internet host:
production HTTPS and Secure cookies, reverse-proxy headers, firewall/OS
isolation, real account provisioning, user/device authorization under a real
load, two separate physical devices, operations/monitoring, operational
restore under production-like conditions, long-term backup retention, and
incident recovery. Passing local synthetic
tests is not evidence of those deployment outcomes. Full desktop/native
Windows runtime regressions and legacy customer-dataset compatibility remain
outside the completed test scope.

The deployment templates use Caddy/systemd/age. systemd unit syntax and shell
script syntax were checked, but no Linux service was started and the Caddyfile
was not parser-validated because Caddy is not installed. The host/domain/provider
and off-site backup remote remain unselected.
