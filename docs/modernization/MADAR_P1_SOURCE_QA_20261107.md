# Madar P1 source-level acceptance (2026-11-07)

Status: **P1 source improvements completed; production release NOT approved**.
This report covers local source work and synthetic tests only. It is not a signed installer, live profile migration, physical multi-PC test or production web deployment.

## Source lineage and changes

- Official 1.0.23 baseline: `22dbf1e` in `madar-ux-execution-20261104` (untouched).
- Native integration branch `feat/madar-v123-gantt-chat-20261107`:
  - `5618841`: a cloned card no longer inherits previous dependencies or Gantt dates.
  - `db382e7`: portable import/export rejects duplicate dependency IDs and invalid early-year calendar dates; handles ISO years `0001..0099` without `Date.UTC`'s 1900 adjustment.
  - `cc07683`: LAN project deletion rejection identifies affected usernames and project IDs while the existing authoritative project-identity guard remains in control.
- Web integration branch `feat/madar-v123-web-integration-20261107`:
  - `84d3bd3`: cloned-card independence.
  - `34ea408`: matching optional portable dependencies and planning dates, including validation; two portable module/test files were SHA256-identical across Native/Web immediately after application.
  - `d233631`: narrow-screen PWA/sync dialog/sidebar browser test, in four viewport widths.
- P0 1.0.24 candidate branch and its release artifacts are unchanged; no new installer or Git push/deploy.

## Successful synthetic verification

| Run | Observed result | Scope |
| --- | --- | --- |
| Native `node --test tests/migration_export.test.cjs tests/gantt_model.test.cjs tests/taskops.test.cjs` | 24/24 pass | Portable round trip and validation, dates, duplicates, cards, board transfer |
| Native `py -3.12 -B -m unittest tests.test_collab tests.test_collab_bridge tests.test_project_integrity tests.test_card_dependency_validation -q` | 42/42 pass | Native collaboration, project integrity and graph validation |
| Native `py -3.12 -B -m unittest tests.test_p1_project_grants tests.test_project_integrity tests.test_collab_bridge tests.test_lan_user_persistence -v` | 27/27 pass | LAN project scope, HTTP 403, restart and persistence |
| Native `npm.cmd run build` | success, 1692 transformed modules | Local Vite bundle, not packaged or installed |
| Web `npm.cmd run test:web` | 44/44 pass | Local Vite web build, Chromium, SQLite API, auth/ACL, offline and sync |
| Web `node --test tests/migration_export.test.cjs tests/taskops.test.cjs tests/web_mobile_p1.test.cjs` | 21/21 pass, 0 skipped | Portable/task tests and Chromium mobile widths 320, 375, 430, 768 |

Both Vite builds warned that their main JS bundle exceeds 500 kB. This is a performance optimization issue, not an observed build failure. The Native build's font notice line-ending side effects were restored to HEAD; no font licenses changed in the commit.

## Open gates and qualifications

1. **Full legacy Python suite is not green.** A parallel read-only audit reported 205 modules discovered, 204 executed, 174 passing, 30 failing, 0 timeouts, 1847 reported tests. The audit wrapper encountered a console encoding error while printing diagnostics and its temporary per-module report was lost. The 30 failures therefore are **not** all classified and are not waived. In the earlier P0 baseline, four representative accounting/bridge tests failed identically in baseline and integration; that does not prove all current failures inherited.
2. A wider LAN regression contained two legacy standalone-accounting HTTP expectations (`403` expected, `404` observed). The unchanged baseline/current route allowlist omits these endpoints; do not restore financial routes to Madar solely to satisfy obsolete tests. Taraz remains the independent accounting application.
3. Physical two-PC LAN and real TLS certificate deployment, mobile device manual QA, accessibility/contrast inspection, real-user data migrations, backup/restore drill and signed Windows installers are not covered by these synthetic tests.
4. Native and Web remain distinct 1.0.23-derived integration branches. A controlled joint integration and dedicated regression release gate are required before any common final release.
5. The installed official `1.0.23`, immutable `1.0.24` P0 candidate, and private operational profiles were not altered in this P1 source change.

Do not publish 1.0.24 or describe P1 as production-ready based on these findings alone.
