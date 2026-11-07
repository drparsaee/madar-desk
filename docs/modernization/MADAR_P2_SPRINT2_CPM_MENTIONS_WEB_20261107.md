# Madar P2: critical-path, scoped mentions, Web parity

Date: 2026-11-07. **Local source integration only. Not a production release, app installation, real-user migration or deployed Web PWA.**

## Branches and retained foundations

- Native P2: `feat/madar-p2-gantt-notifications-20261107`, derived from P1 Native `0b6abb9`.
- Web P2: `feat/madar-p2-web-parity-20261107`, derived from Web P1 `d233631`. The existing Web P1 tree, its SQLite API, PWA, auth, offline outbox and original commits were not overwritten.
- Stable installed Native `1.0.23` and immutable `1.0.24` P0 candidate: untouched in this sprint.
- Taraz remains a standalone accounting app; this sprint creates no billing server, account provider or checkout.

## Implemented

1. **CPM-style Gantt read model** in `src/gantt_model.js`: inclusive calendar-day task durations, per-project topological ordering, longest dependency chain, zero-slack task IDs, per-task float. Cycle, hidden/out-of-view dependencies, invalid dates, duplicate references and oversized graphs fail closed for that project. The implementation does not mutate schedules. UI in `src/gantt_view.jsx` / `.css` shows an accessible summary, representative path and textual/visual zero-float markers. **It explicitly describes the result as applying to the current authorized/filtered view only**, without holidays, resource constraints or intentional planned gaps.
2. **Eligible-user `@username` suggestions** in `src/teamplus.jsx`: card and project conversations, compose and edit; filters authenticated profile list by backend-compatible project scope and role, excludes actor and malformed/duplicate usernames. Supports mouse, keyboard, screen reader combobox, IME and retry-preserving send. If authorized accounts or a project scope are unavailable, suggestions are not fabricated.
3. **Web parity**: copied and SHA256-compared 9 matching source/test files from Native P2, then adapted only `src/App.jsx` Web-specific wiring for authorization rechecking before notification navigation and mention account/project props. Kept existing P1 Web-only authentication and offline/sync logic.

## Executed local checks

| Scope | Result | Notes |
| --- | --- | --- |
| Native `npm.cmd run build` | PASS | 1692 modules transformed; large JS chunk warning |
| Native focused `node --test` incl. Gantt, CPM, notifications, mentions, taskops, settings and Chromium | 33/33 PASS, zero skips | Before final wording-only current-view disclaimer; later targeted Gantt browser test is also executed |
| Native `py -3.12 -B tools/p1_task_only_gate.py` | 7 modules, 65 tests PASS | Explicit source-only subset, not full Python acceptance |
| Web `npm.cmd run test:web` | 51/51 PASS | Build + real SQLite/Chromium PWA, sessions, CSRF, ACL, offline, two-device synthetic conflict tests |
| Web additional focused Gantt/mentions/notifications/taskops/settings tests | 31/31 PASS | Includes browser interactions for both P2 UX features |
| Web focused after current-view disclaimer | 12/12 PASS | Gantt model + Chromium; no skipped tests |
| Shared source/test parity | 9/9 SHA256 equal | Verified immediately following transfer; Web App-specific wiring intentionally differs |

All tests are source-level or synthetic local browser tests. There was no signed package build, installed WebView2 acceptance, real multi-PC LAN, physical device, actual TLS deployment, real subscription purchase or production user-profile write in this sprint.

## Open blockers

- The historical full Native Python legacy suite remains RED. Prior isolated audit: 204 modules executed, 174 passed, 30 failed. The 7-module task-only gate is narrower and does not waive unclassified failures.
- Neither P2 branch is a released installer or deployed site; both need scoped integration review, real-world PWA and WebView2 QA and release-candidate rollback/migration checks.
- Network permission changes between app cache and backend are guarded by a backend recheck at notification navigation; no real cross-device permission-revocation deployment was tested here.
- CPM values are advisory for the current visible subset, not committed finish dates or guaranteed project deadlines. An explicit successor-impact preview and safe bulk scheduling workflow remain future work.

No GitHub/LocalForge push, public publication, production database change or replacement of an existing release was authorized or performed by this sprint.
