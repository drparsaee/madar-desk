# Design | Browser API and durable sync

## Browser API

Base path: same-origin `/api/web/v1`, HTTPS only outside local development.
No arbitrary API URL setting and no CORS dependency.

- `GET /health`: API/contract version and feature capabilities.
- `GET /csrf`: pre-auth synchronizer token; cookie is Secure, SameSite=Strict.
- `POST /session`: username/password; sets an HttpOnly, Secure,
  SameSite=Lax session cookie. Response contains public user projection and a
  CSRF token, never a session token.
- `GET /session`: current public user projection and rotated CSRF token.
- `DELETE /session`: logout; requires CSRF and clears session cookie.
- `GET /state`: authorized snapshot, opaque revision and strong ETag.
- `PUT /state`: snapshot write with Idempotency-Key and either If-Match or
  If-None-Match. Stale writes return 409.

The backend must validate Origin/Fetch Metadata, cookie flags, CSRF, body
limits, JSON schema, session lifetime, login throttling, role and project ACL.
The backend must not trust client-provided role, owner, project scope, revision,
or protected finance fields. It must preserve server-owned fields and records
that are outside the caller's scope.

## Browser database v2

Retain the v1 `documents` object store. Add:

- `sync`: one journal record with remote revision/ETag, last successful sync,
  one immutable in-flight request, one coalescible pending latest snapshot,
  optional conflict snapshots and last error.
- Existing `documents`: state, preferences and recovery records under
  separate keys.

Local state write and pending-snapshot update happen in one read-write
transaction spanning `documents` and `sync`. A local revision mismatch aborts
both. This prevents a successful state write without its recovery/sync record.

The v1-to-v2 upgrade is additive: the original `documents` store and board
snapshot are retained, while the new `sync` store is created empty. Preferences
and unsaved-recovery data use separate IndexedDB keys.

## Outbox state machine

1. Every successful local state save atomically updates the pending snapshot.
2. If a request is in-flight/uncertain, retain its exact payload and key; store
   only the latest additional snapshot as pending.
3. Claiming pending promotes it to in-flight and fixes its idempotency key.
4. A network failure retains in-flight unchanged for exact retry.
5. Success acknowledges the returned remote revision and rebases the latest
   pending snapshot onto that revision.
6. A 409 fetches the remote snapshot and records a conflict. Nothing is
   discarded or auto-merged.
7. Resolving remote explicitly replaces local state after preserving a
   downloadable local backup. Resolving local explicitly queues the current
   local snapshot against the newly observed remote revision.

Initial account connection:

- Remote empty: ask before uploading this device's current state.
- Remote already populated and this device has no baseline: create a conflict
  and ask the user to choose. Never assume which copy is newer.

## UI

- Sync button opens the web account/sync dialog.
- Backup button remains separate and local.
- Without a compatible backend, show API unavailable/local-only and keep all
  local editing functional.
- Login is same-origin only. Logout does not delete local work.
- Conflict UI must identify both snapshots and require an explicit choice.
- Once authenticated with a known remote baseline, local saves are sent in the
  background. Online events and periodic retries resume a durable queue.

## Deliberate exclusions

No direct reuse of the existing LAN Bearer token API, no browser-stored JWT,
no public CORS wildcard, no localStorage auth, no financial REST, no public
file uploads, no automatic conflict merge, no server deployment.
