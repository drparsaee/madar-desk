# Madar Web API v1 | Server implementation handoff

## Status

This is the implementation contract for the browser client. A separate,
local SQLite API implementation is now present under `server/`; it is not
deployed. No production domain, TLS, reverse proxy or real user accounts
are provisioned in this branch. Do not describe the application as online
until the acceptance checks below pass against a deployed server.

OpenAPI source: `docs/api/madar-web-api-v1.openapi.yaml`.
Browser implementation:

- `src/web_api_client.mjs`
- `src/web_sync_engine.mjs`
- `src/web_storage.js`
- `src/web_sync_dialog.jsx`

Local backend: `server/index.cjs`, `server/storage.cjs`,
`server/policy.cjs` and `server/admin.cjs`. Setup and limits:
`server/README.md`. The API's `PublicUser.workspaceId` is an opaque
server-owned workspace identity; the client uses it to isolate its sync journal
between accounts/workspaces.

## Deployment boundary

- Serve the PWA and API from one HTTPS origin.
- Reverse proxy `/api/web/v1/*` to the backend.
- The browser client intentionally refuses arbitrary cross-origin API URLs.
- Do not add wildcard CORS. Same-origin routing avoids browser CORS preflights.
- The only HTTP exception is local loopback development.
- Keep the Windows LAN API private and unchanged. The browser API is a separate
  adapter over the authoritative state service.

## Required endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/web/v1/health` | Exact API/contract version probe |
| GET | `/api/web/v1/csrf` | Pre-auth CSRF token and cookie |
| POST | `/api/web/v1/session` | Username/password login |
| GET | `/api/web/v1/session` | Current user and refreshed CSRF token |
| DELETE | `/api/web/v1/session` | Logout |
| GET | `/api/web/v1/state` | Authorized web-safe snapshot + ETag |
| PUT | `/api/web/v1/state` | Conditional/idempotent snapshot update |

## Authentication and browser security

1. Login credentials are accepted only over HTTPS and never logged.
2. Store passwords using Argon2id (or a current OWASP-approved password hash).
   Add rate limiting, account lockout/backoff, password reset and optional MFA.
3. Session IDs must be random, opaque and stored hashed server-side. Rotate the
   session on login and privilege changes; revoke on logout/password reset.
4. Session cookie:
   - name: `madar_web_session`
   - host-only; omit Domain
   - `Secure; HttpOnly; SameSite=Lax; Path=/api/web/v1`
   - finite idle and absolute lifetime; 12 hours maximum for the initial pilot
5. CSRF cookie:
   - name: `madar_web_csrf`
   - host-only; omit Domain
   - `Secure; HttpOnly; SameSite=Strict; Path=/api/web/v1`
   - token returned in JSON and retained by the client only in JS memory
   - compare `X-CSRF-Token` to the cookie and the session-bound server value
6. Reject state-changing requests unless Origin exactly matches the configured
   public origin and Fetch Metadata is same-origin/same-site. Do not trust
   Referer alone.
7. Set `Cache-Control: no-store` on session, CSRF, state and write responses.
   Never put session or CSRF material in a URL, localStorage, IndexedDB, logs,
   analytics, error telemetry or backup.
8. Add a restrictive CSP, HSTS, frame-ancestors, nosniff and referrer policy.
   Do not enable permissive credentialed CORS.

## State, revision and idempotency

The browser sends a web-safe snapshot with schemaVersion 1. The API must map
this projection to the authoritative workspace service without replacing
server-owned fields.

### GET

- If a workspace exists: return `exists:true`, the authorized projection,
  opaque `revision`, `updatedAt`, and a **strong** ETag header.
- If no workspace exists: return 404 JSON `error=state_not_initialized`.
- The ETag represents the current authoritative revision observed by the
  caller. A global revision is acceptable for the first pilot; unrelated
  project changes may therefore cause a safe but unnecessary conflict.

### PUT

- Require JSON, a 16 MiB body limit, `X-CSRF-Token`, `Idempotency-Key`, and
  exactly one of:
  - `If-None-Match: *` for first creation
  - `If-Match: <strong ETag>` for an update
- Missing precondition: 428.
- Stale precondition: 409 `revision_conflict`; include currentRevision if safe.
- Same idempotency key + same canonical body/precondition: replay the exact
  original status, body and ETag without a second mutation.
- Same idempotency key + different request: 409 `idempotency_key_conflict`.
- Persist the idempotency record **in the same DB transaction** as the state
  commit. Check/replay idempotency before evaluating a now-stale precondition;
  otherwise a lost successful response could be misreported as a conflict.
- Retain idempotency receipts for at least 90 days. Never recycle a key during
  its retention window.
- Return a strong new ETag and `{schemaVersion:1,revision,savedAt}`.
- Do not implement last-write-wins, unconditional PUT or silent conflict merge.

### Suggested relational tables

Names are illustrative; adapt to the selected database.

- `web_workspace_heads`: workspace_id PK, canonical_revision, etag, updated_at
- `web_workspace_snapshots`: workspace_id + revision, JSONB projection or
  immutable snapshot reference, created_at
- `web_idempotency`: actor_id, workspace_id, key, request_hash,
  response_status, response_body, response_etag, created_at, expires_at;
  unique(actor_id, workspace_id, key)
- `web_sessions`: session_hash, user_id, created_at, expires_at, revoked_at,
  last_seen_at, csrf_hash
- `web_audit_events`: actor, workspace, action, object IDs, prior/new
  revision, timestamp, request correlation ID. Never store passwords/tokens.

Use a DB transaction/row lock or serializable compare-and-swap for each PUT.
State, new revision, audit event and idempotency receipt commit atomically.

## Authorization and data integrity

The server is the security boundary. Client role flags, projectIds, submitted
owner IDs and UI-hidden controls are not authorization.

- Derive actor, role, workspace and project grants from the authenticated
  server-side session and membership tables.
- `viewer`: GET only; reject PUT with 403.
- `admin`: may change workspace/project/board/stage structure and tasks,
  subject to project ownership, integrity and audit rules.
- `editor`: may change task fields only within granted projects. Do not allow
  project reparenting or structural edits.
- `projectIds=null` may represent full workspace scope; otherwise filter all
  returned projects/tasks by server grants.
- For an editor PUT, compute the submitted diff against the authorized
  projection of the exact current revision. Apply only permitted task changes.
  Absence of an out-of-scope task from the submitted projection is **not** a
  delete. Preserve all out-of-scope records.
- Derive an existing task's project from the stored record, not from the
  submitted payload. Validate the new task's project/board grant.
- Preserve server-owned finance, ledger, invoice, purchase, sale, cost, audit,
  attachment and other protected fields while applying web task changes.
- Reject protected finance fields if supplied by a modified browser; the
  shipped client strips known fields before sending. Never accept accounting
  operations through this API.
- Never return finance values, financial source IDs, local paths, attachment
  bytes, API keys, host secrets or session material in the web projection.
- Apply project/task identity and restore integrity checks equivalent to the
  existing native/lan guards. Reject partial snapshots that would orphan
  comments, activity, watcher, finance or collaboration references.
- Sanitize text and validate IDs, array sizes, nested records and allowed task
  fields. Set request, response and per-workspace storage limits.

For project-scoped editors, the API may use the current canonical snapshot and
the ETag revision to build the caller's old authorized projection, diff the
incoming projection, and merge only permitted changes into the canonical
snapshot. This avoids treating hidden projects as deletions.

## Backend acceptance checklist

- [ ] HTTPS and reverse proxy serve the exact health contract.
- [ ] Login/logout/session cookies have the required flags and rotation.
- [ ] CSRF, Origin and Fetch Metadata negative tests pass.
- [ ] Viewer PUT is rejected; editor project-scope and admin structural tests pass.
- [ ] Protected finance fields are preserved server-side and absent in responses.
- [ ] First snapshot requires If-None-Match.
- [ ] Stale If-Match returns 409 without changing any record.
- [ ] Lost-response retry with the same idempotency key returns the original
      receipt and creates exactly one revision.
- [ ] Same key with changed body is rejected.
- [ ] Two-device simultaneous writes produce a visible conflict, never silent
      last-write-wins.
- [ ] DB transaction rollback leaves state, revision, audit and idempotency
      tables mutually consistent.
- [ ] Backup/restore drill proves recoverability and retention.
- [ ] Logs and telemetry contain no credentials, cookies, CSRF tokens or
      sensitive task content.
- [ ] Production deployment, monitoring, alerting, rate limits and incident
      response are documented.

### Local verification (2026-11-06)

The dedicated `server/` implementation uses Node.js `node:sqlite` and has
independent synthetic-database tests. Executed:

```text
node --test --test-concurrency=1 tests/web_server_cli.test.cjs tests/web_server_api.test.cjs
tests 8 | pass 8 | fail 0 | cancelled 0 | skipped 0
```

The local tests cover session cookies/rotation and revocation, CSRF,
Origin/Fetch Metadata checks, login throttling, project ACLs, viewer/editor
rights, finance-field rejection, safe card reports, conditional writes,
idempotent replay, concurrent write conflict, transaction rollback, separate
SQLite reads, and consistent backup verification without overwrite. Loopback
HTTP intentionally omits the cookie Secure attribute. The tests do **not**
prove production HTTPS, reverse proxy isolation, real account provisioning,
native accounting reference reconciliation, an operational restore drill,
monitoring or live server deployment.

Until the owner's actual host passes the remaining production acceptance gates,
the application remains local-first. The presence of a local SQLite API is
not evidence of Internet-hosted synchronization.
