# Madar P2 Sprint 4: authenticated host-only Gantt shift preflight

Date: 2026-11-07. **Read-only backend milestone. NOT atomic batch scheduling, deployment, migration or release.**

## Isolation

- Native P2: feat/madar-p2-gantt-notifications-20261107; Web P2: feat/madar-p2-web-parity-20261107.
- Official installed app, candidate 1.0.24, P1 worktrees, live profiles and Taraz are out of scope.
- Sprint 3's existing UI still stages drag previews and **does not** apply impacted successors. No bulk-save button was introduced.

## Implemented and security boundaries

1. Separate pure host preflights: Python gantt_shift_guard.py / prepare_gantt_shift, and Web server/gantt_shift_guard.cjs / prepareGanttShift. Inputs: authoritative full host snapshot, exact request {taskId,days,expectedRevision}, and trusted role, project grants and actual revision. Never use filtered UI tasks as the host authority.
2. Calendar-day finish-to-start DAG, converging/cascading successors, preserving durations/slack, no unrelated-project writes. Fail-closed for missing/invalid dates, duplicate edges, cycles, pre-existing conflicts, unknown/archived/outside-project dependencies, revoked grants, stale revisions and date overflow.
3. Native LAN: authenticated POST /api/gantt/shift/preview, under the existing account + bridge locks; revision is account-view-based, matching GET /api/state. Viewer 403; stale 409; hidden/missing targets share one generic error. No persistence/offline journal writes.
4. Web: POST /api/web/v1/gantt/shift/preview requires active session, Origin/fetch-metadata and CSRF. Rechecks the authoritative SQLite workspace revision and current scoped grants. Viewer 403; stale revision 409; hidden/missing targets 404 without revealing existence. Returns only authorized date proposals, never private task names. Does not insert workspace heads, snapshots, audit events or idempotency receipts.
5. HTTP response fields: readOnly=true, revision, scope=full_host, changedCount and updates with each authorized card ID, plannedStart and plannedEnd. Pure helpers also produce an in-memory nextState but never persist it.

## Local synthetic verification

| Environment | Exact scope | Observed |
| --- | --- | --- |
| Native | Python unittest tests/test_gantt_host_guard.py | 4/4 PASS |
| Native | Python unittest tests/test_p2_gantt_preview_lan.py | 3/3 PASS, including real loopback HTTP, viewer/grants/stale revision and no-write |
| Web | Node tests/gantt_host_guard.test.cjs and tests/web_server_api.test.cjs | 14/14 PASS; CSRF/ACL, HTTP, no workspace write |
| Native | py -3.12 -B tools/p1_task_only_gate.py | 7 selected modules / 65 tests PASS |
| Web | npm.cmd run test:web | Vite 6.4.5 Web build PASS (1700 modules), 55/55 tests PASS, no skips |

Sprint 3 evidence: MADAR_P2_SPRINT3_SHIFT_PREVIEW_20261107.md.

## Critical unfinished release gates

- **No batch commit API exists.** Future commit must revalidate on the full latest host snapshot inside the same write transaction/lock, check current grants and revision/CAS, validate the candidate and persist all successors or none. This preview is not an authorization token.
- Native legacy JSON lacks the same durable multi-domain transaction guarantees as unified SQLite; future batch writes must require a proved-safe mode or stay disabled.
- Web/PWA offline journaling and optimistic UI must not bypass server-side guards, silently coalesce multiple saves or mark uncommitted batches as synced.
- No downstream writes, real two-PC LAN/TLS, installed WebView2 QA, signed installer, live migration or public release.
- The previously unresolved Native full Python legacy suite is a separate release gate; narrow tests do not waive it.
- The Web Vite build reported a non-blocking bundle-size warning (main JS about 892 kB).
