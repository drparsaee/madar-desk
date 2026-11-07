# Overview | Madar Web state and transport boundary

## Source baseline

Branch `feat/madar-web-pwa-20261106`, starting commit
`d48c09450251c2c74aea64a26c0f20bcebb4ae1e`.

## Current flow

1. `App.jsx` creates the web bridge only when Vite mode is `web` and no
   `window.madar` native bridge exists.
2. Initial load calls `getState()`, `lanStatus()`, `getPreferences()`,
   `lanProfiles()`, and `syncStatus()`.
3. The complete normalized task snapshot is held in React state.
4. Mutations mark a ref dirty; a 320 ms effect calls `api.saveState(snapshot)`.
5. The web storage adapter writes IndexedDB and returns `localRevision`.
6. A 15-second timer refreshes state/status/profile methods. It is not a
   network synchronization mechanism.
7. The UI backup dialog imports/exports local JSON. There is no remote login.

## Current persistence

- Database: `madar-web-local-v1`
- Version: IndexedDB v2 (additive migration from v1)
- Object stores: `documents`, `sync`
- Key: `board-state`
- CAS: `__localRevision` in the saved document
- Preview `localStorage.madar-preview` is not the web source of truth.
- Preferences and unsaved recovery use separate IndexedDB document keys.
- Every successful local save atomically updates the pending sync snapshot.
  A local CAS failure aborts both writes.
- The outbox retains one immutable in-flight request and one coalescible
  pending latest snapshot. In-flight retries reuse the same idempotency key.
- Theme, board view and other presentation-only preferences may still use
  localStorage; no session or CSRF secret is stored there.

## Current API boundaries

- Windows host bridge: `window.madar`; untouched.
- Preview bridge: `mockBridge`; not a production API.
- Web bridge: `webBridge`; local IndexedDB only.
- Browser API client: `MadarWebApiClient`; fixed same-origin HTTPS path
  `/api/web/v1`, HttpOnly cookie session, in-memory CSRF, ETag and idempotency.
- Sync engine: `syncWebState`; explicit first upload, retry-safe outbox and
  manual conflict resolution.
- LAN REST: `lan.py`, private-network Bearer login and revision-based state.
- Integration REST library: `integration_api_v1.py`, narrow title-only
  projections and in-process mount requirement.

## Protected invariants

- Never expose the Windows profile or its LAN token to browser JavaScript.
- Never store web passwords, bearer secrets, refresh tokens or session IDs in
  browser storage or URL parameters.
- Local saves remain successful when the server is down.
- No remote overwrite without a known matching revision.
- An ambiguous network result is retried idempotently, not sent as a new write.
- A remote conflict preserves both versions.
- The server must independently authorize each user and project; UI role flags
  are not security controls.
- Browser API serialization strips known finance values/source IDs and local
  file paths. The server must also preserve canonical finance fields itself.
- Server implementation handoff: `docs/api/MADAR_WEB_API_SERVER_HANDOFF.md`.
- The web task API must not post financial entries or accept browser-supplied
  accounting authority.
