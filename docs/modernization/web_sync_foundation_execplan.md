# ExecPlan | Web sync foundation and browser API boundary

## Purpose / owner decision / exclusions

Owner request: continue the approved Madar Web PWA development while the owner
prepares hosting infrastructure. Make the browser application backend-ready so
the server can be connected without replacing the UI or weakening the Windows
application.

- Owning worktree: `D:\CoS-Test\000- Madar\madar-web-pwa-20261106`
- Branch: `feat/madar-web-pwa-20261106`
- Starting SHA: `d48c09450251c2c74aea64a26c0f20bcebb4ae1e`
- Windows source baseline: `562b372`; this task must not modify that worktree.
- Private LocalForge is the only source remote. No push or deployment is part
  of this task.
- No public endpoint, server process, credentials, account, domain, DNS, TLS
  certificate or paid infrastructure is provisioned here.
- No financial/Parsian records or operational profiles are used in tests.

## Existing behavior

- `src/App.jsx` loads the complete task snapshot via `getState()`, normalizes
  it, and persists the complete snapshot through debounced `saveState()`.
- `src/web_storage.js` uses IndexedDB v1 and a local revision compare-and-swap.
  It has no durable sync queue or server revision baseline.
- `webBridge` inherits several preview methods, including localStorage-backed
  preferences. It reports local-only status but has no server client.
- `lan.py` `/api/state` is a private LAN API with Bearer sessions; its existing
  acceptance document describes no browser CORS/cookie contract. The separate
  `integration_api_v1.py` is intentionally a narrow in-process adapter, not a
  mounted public web API.
- Existing web MVP baseline: 32/32 targeted browser/Node tests passed,
  independent web build and standard Vite build passed, preview returned HTTP
  200. These are baseline claims from the immediately preceding task.

## Plan of work

1. Add an explicit same-origin HTTPS browser API contract and OpenAPI document.
2. Upgrade the browser database additively from v1 to v2; retain existing
   documents and add atomic sync metadata, outbox, preferences and recovery.
3. Implement a same-origin HTTP client with HttpOnly cookie sessions, CSRF,
   strict JSON/content-type handling, ETag conditional writes and idempotency.
4. Implement a durable local-first sync engine. Never auto-bootstrap over an
   existing remote workspace; preserve uncertain writes and surface conflicts.
5. Add a small login/sync UI. Keep local mode usable when no server exists.
6. Add synthetic tests, run both web and standard builds plus relevant board
   regressions, review the final diff and commit locally.

## Parity / invariants

- Local IndexedDB commit is authoritative for immediate UI feedback. A server
  failure must not roll back or erase a successful local commit.
- A queued full snapshot may be coalesced only before it becomes in-flight.
  An in-flight/uncertain request keeps its exact body and idempotency key.
- Retries of an uncertain write reuse the same idempotency key and payload.
- The server must require `If-Match` for updates or `If-None-Match: *` for the
  first snapshot. A stale revision is a conflict, never an automatic overwrite.
- A device with no known remote baseline must not replace an existing remote
  snapshot automatically. Initial upload requires an explicit user action.
- A conflict preserves both local and remote snapshots until the user chooses
  a resolution. No automatic last-write-wins or silent merge.
- Session secrets never enter localStorage, IndexedDB, URLs, logs or backup
  files. Use same-origin HttpOnly cookies; keep CSRF tokens in memory.
- The browser sends no credentials to a cross-origin API. The web server must
  reverse-proxy `/api/web/v1` on the same HTTPS origin.
- Existing LAN, accounting, finance and installed Windows code are out of
  scope. Server-side ACL and data merge remain backend responsibilities.

## Progress

- [x] Baseline branch/status, API usage and data lifecycle inspected.
- [x] API contract / OpenAPI draft and server handoff checklist.
- [x] IndexedDB v2 and durable outbox.
- [x] HTTP client and sync engine.
- [x] Sync/login/conflict UI.
- [ ] Targeted tests, builds, diff review and local commit.

## Validation and release boundaries

- Synthetic browser DB tests for v1-to-v2 retention, atomic CAS/outbox,
  preferences/recovery, in-flight retry, coalescing and conflict preservation.
- Fake-fetch tests for same-origin enforcement, CSRF, cookie-only auth, JSON
  rejection, ETag/If-Match, idempotency and status/error mapping.
- Sync-engine tests for bootstrap refusal, first upload confirmation, replay,
  network uncertainty, revision conflict and explicit resolution.
- Run `npm run web:build`, `npm run build`, new tests and relevant existing
  card/label/color/browser tests. Record every skip and failure.
- No production server is available in this task, so no real login, HTTPS,
  multi-device, deployment or remote persistence claim is allowed.

## Decision log

- 2026-11-06: Existing LAN API is not silently reused for browser internet
  traffic. The web client receives its own versioned same-origin API contract.
- 2026-11-06: Full-snapshot optimistic concurrency is retained for the first
  web sync pilot because App.jsx already commits full snapshots. Server must
  enforce scope and protected-field preservation before accepting them.
- 2026-11-06: Local-first behavior remains available without a server. A server
  being absent is a visible state, not a simulated successful connection.
