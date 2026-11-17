# Madar Web API v1: local SQLite backend

This is a **real local HTTP server backed by SQLite**, independent from the
Windows LAN/accounting API. The server handles the task-board web projection
only. It is not an accounting or file-hosting backend, and it has not been
deployed to an Internet host.

Production templates and the Persian deployment runbook are in `deploy/` and
`docs/deployment/MADAR_WEB_PRODUCTION_DEPLOYMENT_FA.md`. From Windows PowerShell,
build a checksummed web-only deployment archive with
`npm.cmd run web:release:package`.

## Requirements and first run

- Node.js **26.8+** with built-in `node:sqlite`. No npm dependencies.
- A **private** SQLite path outside Git and any web-served directory. Never use
  an operational Parsian/Madar Windows database.
- The PWA and API must be reachable through a single configured browser origin.
  The API binds loopback only; TLS is terminated by your reverse proxy.

PowerShell commands:

```powershell
$env:MADAR_WEB_DB = 'D:\MadarPrivate\web-api.sqlite'
$env:MADAR_WEB_PUBLIC_ORIGIN = 'http://127.0.0.1:5173'
$env:MADAR_WEB_PORT = '8781'
node server/admin.cjs init
node server/admin.cjs user:add admin admin team '*'
node server/index.cjs
```

The user creation command prompts for a hidden password (12 to 1024 chars).
Non-interactive administrators may pipe a secret from a protected source via
stdin; do not put passwords in shell arguments, source code, Git, logs or
PowerShell history.

For an editor limited to one project:

```powershell
node server/admin.cjs user:add editor editor team p1
node server/admin.cjs user:list
node server/admin.cjs user:reset-password editor
node server/admin.cjs user:set-role editor viewer p1
node server/admin.cjs user:disable editor
```

The `team` argument is the **server-owned workspace ID**, independent from
workspace display IDs inside the browser snapshot. Admin accounts have full
workspace scope. Editor/viewer accounts must be granted explicit project IDs;
`-` means zero projects. `user:set-role` also accepts `*` for admin full
scope. Role or password changes revoke all existing sessions.

For local development, forward the PWA's `/api/web/v1/*` requests through
Vite's same-origin proxy to `http://127.0.0.1:8781`. Set
`MADAR_WEB_PUBLIC_ORIGIN` to the **browser page origin** (typically
`http://127.0.0.1:5173`), not to the proxy target. The proxy must preserve
the browser's `Origin` and `Sec-Fetch-Site` headers.

Open a **second PowerShell terminal** from the repository root:

```powershell
$env:MADAR_WEB_API_PROXY = 'http://127.0.0.1:8781'
npm.cmd run web:dev
```

Verify the actual Vite browser URL. If Vite picks another port, restart the
backend with `MADAR_WEB_PUBLIC_ORIGIN` matching that browser URL exactly.

## Configuration

| Name | Requirement |
| --- | --- |
| `MADAR_WEB_DB` | Required absolute or relative path to a dedicated SQLite file |
| `MADAR_WEB_PUBLIC_ORIGIN` | Required exact browser origin, HTTPS outside loopback |
| `MADAR_WEB_HOST` | Optional loopback interface, default `127.0.0.1` |
| `MADAR_WEB_PORT` | Optional port, default `8781` |

An HTTP origin outside localhost/127.0.0.1/::1 fails startup. Binding to a
non-loopback network interface fails startup. Behind a production HTTPS reverse
proxy, use `MADAR_WEB_PUBLIC_ORIGIN=https://your-actual-domain` while keeping
the backend on loopback.

No default accounts or public-signup route are created. Database migrations
through **version 3** are applied transactionally during initialization/startup:
v1 stores accounts and workspace snapshots; v2 adds isolated card/project
messages and idempotency receipts; v3 retains the previous message text before
edits and soft-deletes in the server-only `web_conversation_revisions` table.
Both preexisting v1 and v2 databases are upgraded in place; use a verified
independent SQLite backup before any non-test migration. Each snapshot write
atomically stores its state, revision, history, audit and idempotency receipt.
Receipts are retained until the administrator explicitly adopts a safe
retention/migration process; they are never recycled automatically.

## Security and limitations

- Secure, HttpOnly session and CSRF cookies in HTTPS mode, with an explicit
  **loopback HTTP exemption** for local development.
- scrypt password hashing (N=131072, r=8, p=1), server-stored session hashes,
  session rotation, 30-minute idle expiry, 12-hour absolute lifetime.
- CSRF header, cookie and server-side hash validation; exact Origin, Fetch
  Metadata validation and login throttling by account and peer IP.
- Admin structural rights; editors can edit only tasks belonging to granted
  projects; viewers can read filtered data. Finance, local paths, attachments
  and unsupported field types are rejected rather than silently stored.
- Conditional strong ETag writes; lost-response retry uses the original
  idempotency receipt. Stale revisions are rejected with HTTP 409.
- Project/card conversation routes have separate SQLite storage, server-owned
  ACL, reply/ownership checks and durable idempotency. A card moved to another
  project does not automatically expose messages from the prior project;
  old-project messages remain retained but not returned to the new scope.
- Chat messages are **not included** in snapshot JSON exports. The PWA offline
  shell and state-sync Outbox do not imply an offline Outbox for chat. Web
  mentions/notifications, full history browsing and attachments are pending.
- The readiness endpoint performs a lightweight SQLite query. SIGTERM/SIGINT
  initiate graceful HTTP shutdown and close the database after active requests.
- No CORS, upload, public account registration, raw financial record,
  accounting integration, optional MFA or self-service password reset routes.
  Password reset is available only through the private admin CLI.

**Production is not accepted yet.** Before Internet deployment, configure
TLS 1.2+/1.3 and reverse proxy, hosting isolation, external rate limits,
backups/restore drills, metrics, health alarms, credentials, request-size
limits, MFA (if required), and an audit of business reference integrity.
This local backend cannot prove safety of financial references held in a
separate native/Windows database. The snapshot API must not be treated as
authoritative for those records.

SQLite uses WAL, `synchronous=FULL`, explicit `BEGIN IMMEDIATE` for
writes and foreign keys. A **live** backup must use SQLite's backup API
or a consistent checkpoint/backup procedure, not a bare copy of the
`.sqlite` file while the server runs. Preserve the DB, WAL and SHM through
any offline file-level backup. Test restore in a separate directory before
relying on backups.

The private administrative CLI supports an online consistent SQLite backup:

```powershell
node server/admin.cjs backup 'D:\MadarPrivate\backups\web-20261106.sqlite'
node server/admin.cjs restore:verify 'D:\MadarPrivate\backups\web-20261106.sqlite'
```

Backup fails if the destination already exists; it does not overwrite prior
copies. Verification checks SQLite integrity, supported schema versions (1-3)
and the required tables, including conversation history in v3. This backup
contains private conversation text and historical edits, so encryption and
strict access controls are necessary.
To rehearse a restore, copy the backup to a **separate** private working
directory, set `MADAR_WEB_DB` to that copied file, and run
`node server/admin.cjs user:list` plus a local API smoke test. Never point a
restore rehearsal at the live account database. Store backup files encrypted
and restrict file permissions; they contain the workspace state and account
password hashes. Automatic backup scheduling and off-site recovery have not
been configured.

Run targeted tests (synthetic temporary databases only):

```powershell
node --test --test-concurrency=1 tests/web_server_api.test.cjs tests/web_server_cli.test.cjs tests/web_conversation_migration.test.cjs tests/web_gantt_chat_browser.test.cjs
```
