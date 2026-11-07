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
- The native Windows application has not been installed, published, or tested
  end-to-end by this web development. The regular Vite build has passed;
  web-mode changes are gated and the native runtime remains independent.
- IndexedDB v2 adds a durable outbox, preferences and unsaved-recovery storage.
- A same-origin API v1 client and account/sync/conflict UI are connected to a
  **real local Node/SQLite backend** in `server/`. The backend is not deployed
  on the public Internet. With no server running, the dialog correctly reports
  that the API is unavailable and IndexedDB storage keeps working offline.
- Browser conflict resolution preserves separate copies and offers a backup
  before choosing the server version. Local journal entries are bound to a
  server-owned workspace identity to prevent accidental cross-account replay.

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

For a **local end-to-end test**, see `server/README.md` to create the dedicated
SQLite database, provision an administrator via the CLI and run the API. In a
second PowerShell window set
`$env:MADAR_WEB_API_PROXY='http://127.0.0.1:8781'` before `npm run web:dev`.
The same-origin development proxy is restricted to a loopback target.

Deploy the **dist-web** directory only to a trusted HTTPS host, after the
architecture and security review. A static host does not make data online.
Accounts, role rules and multi-browser synchronization have been exercised
against the real **local** API with synthetic data, not a deployed server.
The encrypted backup timer is packaged but has not been enabled on a host;
off-site retention, TLS and host configuration remain pending. A synthetic
SQLite backup-and-restore verification test
has passed locally; this does not prove real-world disaster recovery.
Production deployment templates are now in `deploy/`: Caddy HTTPS/reverse
proxy, a restricted systemd API service, an encrypted daily backup timer and
an optional rclone off-site copy. The Persian runbook is
`docs/deployment/MADAR_WEB_PRODUCTION_DEPLOYMENT_FA.md`. A checksummed web-only
deployment archive can be produced with `npm.cmd run web:release:package`.
These templates have not yet been installed or validated on a public Linux
host because no VPS/domain has been selected.
Do not enter production accounting or customer secrets until an authenticated
backend with server-side authorization, immutable audit trails, isolation and
independent backups is built and tested.
IndexedDB data is browser-origin scoped, not encrypted by this application,
and may be deleted by clearing browser storage. Export JSON files are plain
text: store them securely.

## Server integration boundary

The browser uses the isolated web adapter and `/api/web/v1` contract specified
in `docs/api/madar-web-api-v1.openapi.yaml`. The local implementation and
remaining deployment checklist are documented in `server/README.md` and
`docs/api/MADAR_WEB_API_SERVER_HANDOFF.md`. Require server-issued revision /
If-Match semantics, scoped permissions and tested durable backups. Never expose
`mockBridge` or the browser's local admin role as authorization on a hosted
service. Do not point the browser at the existing LAN Bearer API.

## QA

On 2026-11-06, `npm.cmd run test:web` passed 33 of 33 tests including the
additional backup CLI test; `npm.cmd run build`
also succeeded for regular Vite entrypoints. Browser tests provision synthetic
records in a temporary real SQLite database. These results do not establish
availability, backup recovery or security of a production hosted service.
