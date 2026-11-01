# Madar Desk | Modernization phase 2 evidence (2026-11-01)

## Scope and source

- Isolated worktree: `D:\CoS-Test\madar-codex-modernization-phase2-20261101`
- Branch: `modernization/phase2-20261101`, originally based on LocalForge `main` SHA `482b898428b85e2e168aac1d56d438a002fcba17`.
- Preserve recent Unslop/Vitrea/RTL changes on `main`. Do **not** merge the whole older modernization branch.
- All executions use disposable Windows `APPDATA` / `LOCALAPPDATA`, temporary fake versioned executables, LAN loopback fixtures and synthetic accounting journals. No real Parsian, customer SQLite, credentials or installed EXE are test inputs.

## Changes, before/after evidence

1. **Updater profile backup:** Reject volume root even after normalization; stage ZIP as a same-volume `.partial`, verify all archived file bytes and SHA-256, index entries once with ordinal key rejection, uniquely name verified final ZIP. Three parity checks compare safe behavior with original source. Ten new/previous updater+parity tests passed before the later activation patch.
2. **Activation:** Reject a volume root and normalized-to-root `InstallRoot`. Restore/activation and updater combined suite: **19/19 passed**, including synthetic pointer/rollback, corrupted EXE hash and two distinct, verified consecutive backups. No mounted drive root was used as a fixture.
3. **LAN HTTP framing:** A new raw HTTP test demonstrated a previously accepted login request with duplicated `Content-Length` (HTTP 200, expected rejection). Reject any duplicate header name or any `Transfer-Encoding` before API dispatch, preserving the existing integration endpoint rule. Targeted regression subsequently passed.
4. **Accounting identity login:** A new test demonstrated invalid credential lengths could mutate the real *synthetic* identity registry's persistent lockout counters. Validate the same username/password boundaries as account creation before hashing or persisting a failure. Targeted regression subsequently passed; valid sign-in and finance logic remain covered by existing neighboring tests.

## Safety and acceptance boundaries

- LAN/accounting regression (10 modules): **148 tests, OK, with 2 expected failures** and no unexpected failures. Separate general ledger, rial and financial-security regression (9 modules): **117 tests, OK**.
- `npm ci` succeeded after offline cache installation failed; `npm run build` succeeded (Vite, 1706 modules). The first Node run before building `dist` failed. After building, the default concurrent run reported **528/530** passing, with 2 UI/browser selector timeouts. Those two cases passed individually (2/2), and the **complete serial Node suite passed 530/530, no skips** (`node --test --test-concurrency=1 tests/*.test.cjs`, duration about 124s). To remove the observed concurrency flake, `package.json` now runs Node tests sequentially by default. This does not remove the need for full Python or real-device acceptance.
- Remote `git ls-remote --heads origin main` returned **Authentication failed** from LocalForge. Remote synchronization and branch push must not be claimed until independently verified.

- The evidence above establishes bounded contract behavior for the executed fixtures, **not** a verified production migration, crash durability, full security audit or comprehensive Parity proof.
- Rial is the target canonical financial storage unit. Legacy TOMAN accounting remains a separate existing contract; no schema or currency conversion was performed.
- No `main` merge, installer build, real account migration or installed EXE change is included in this phase.
- LAN/accounting larger suites, Node build/tests, complete regression, independent review, branch commit and private push must be reported from their actual future command results, not inferred from a test count in this file.
