# Madar Web PWA (isolated from Windows)

## What is implemented

- The current React/Vite board and card interface in a dedicated Vite **web** mode.
- An origin-local IndexedDB state store, with a revision compare-and-swap to block
  silent overwrites by multiple tabs. The old `madar-preview` localStorage
  remains only for the original preview/test mode; the Windows profile is never read.
- Manual JSON export/import for **Madar Web** state, with validation, explicit
  confirmation and a pre-restore download attempt.
- Installable PWA manifest, shell-only service worker, and visible **local-only**
  status. Private data and API responses are never cached by the service worker.
- Verified offline startup after the PWA first loads online and then completes
  an online navigation under the installed service worker. A cold, first-ever
  offline launch was not verified as reliable in Chromium.
- Server-required features (LAN user administration, hosted accounting, file
  attachments, Windows updater and cloud backup) are not represented as working.
- The Windows version has not been changed, rebuilt or published.

## Run

```powershell
npm ci
npm run web:dev
```

Open http://127.0.0.1:5173/ on the same machine. For the distributable build:

```powershell
npm run web:build
npm run web:preview
```

Deploy the **dist-web** directory only to a trusted HTTPS host, after the
architecture and security review. A static host does not make data online.
Cross-device synchronization, real accounts, and server backups do not exist yet.
Do not enter production accounting or customer secrets until an authenticated
backend with server-side authorization, immutable audit trails, isolation and
independent backups is built and tested.
IndexedDB data is browser-origin scoped, not encrypted by this application,
and may be deleted by clearing browser storage. Export JSON files are plain
text: store them securely.

## Next server integration boundary

Keep `src/App.jsx` independent of the transport. Implement a separate
authenticated `getState/saveState/lanStatus/syncStatus` adapter once an actual
server is selected. Require server-issued revision / If-Match semantics, scoped
permissions and durable backups. Never expose `mockBridge` or the browser's
local admin role as authorization on a hosted service.

## QA

Run `npm run web:build` and `node --test tests/web_pwa_mvp.test.cjs`.
The web test uses synthetic records only. A successful build is not evidence
of real multi-user or hosted availability.
