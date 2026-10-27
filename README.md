# مدار | Madar Desk

**Development continuity:** Read [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) before choosing the next implementation task. It links owner decisions, incomplete obligations, ideas and evidence; [LOCALFORGE_SOURCE_OF_TRUTH.md](LOCALFORGE_SOURCE_OF_TRUTH.md) remains the Git policy.

## Current development status (2026-10-27)

The active source branch is `main` of the private **LocalForge** repository
`localadmin/madar-desk`. The package source version is currently
`1.0.0-rc.13`; the much older `v0.3-preview` instructions below are retained
as historical notes, **not** as current release instructions.

Current source includes a Vitrea-inspired task-management shell and separate
accounting workspace, LAN permission checks, a versioned finance domain, and
an **explicit opt-in** unified SQLite host store. The unified database is not
automatically enabled for existing users. An active `unified-active.json`
marker determines whether this computer uses SQLite or the legacy JSON store.
The migration/restore workflows are guarded, backup-first operations.

**Do not treat an EXE filename, a passing mock test, or a visually correct
screen as proof of production readiness.** Two physical Windows clients,
Google Drive failover, complete Parsian accounting migration/reconciliation,
and clean-install acceptance remain separate tests. Accounting uses **rial**
as its canonical currency; the historical toman overview below does not
define the authoritative ledger.

Builds have immutable release names. `npm run dist` currently targets the
historical `v1.0-rc13` candidate and deliberately refuses to overwrite an
existing executable. For a new candidate, first select a distinct release
filename and run `scripts/ensure_new_release.py`, then build it using
PyInstaller with a matching distinct `--name` after `npm run build`.
Do not rename or overwrite an existing installed EXE.

Authoritative decisions and active release limitations:
[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md),
[docs/MADAR_VITREA_REDESIGN_20261027.md](docs/MADAR_VITREA_REDESIGN_20261027.md),
[docs/decision-inventory/DECISIONS.md](docs/decision-inventory/DECISIONS.md).

---

## Historical early-version documentation

An independent Windows task manager. Entirely separate from ForgeOS and Chat On Steroids. Persian RTL, personal offline mode and optional LAN host/client collaboration. Custom Kanban columns, projects, checklists, task notes, manually entered agent updates, optional per-step/project accounting, dark mode, bundled Vazirmatn font and Google Drive backup/restore.

**Windows portable preview build:** `D:\CoS-Test\madar-desk\release\Madar-Desk-v0.3-preview.exe`.
Double-click this executable. No Node, Python, or installation is required to **run** it. It uses the Microsoft Edge WebView2 Runtime, which must be installed on the target Windows computer.

**Tech:** React/Vite UI, a Python native host with pywebview/Edge WebView2 and PyInstaller. Local data is JSON with atomic writes; the UI has a loopback-only host and LAN HTTP API is available **only if deliberately enabled**.

## Run

```powershell
npm install
npm run dev
```

Open http://127.0.0.1:5173 for browser preview (demo data is stored in the browser and does not affect the desktop database).

To run the same desktop host from source:

```powershell
npm run build
npm run desktop:dev
```

To rebuild the standalone Windows executable, install the additional **build-time** Python packages `pywebview` and `pyinstaller` in Python 3.12, then run:

```powershell
npm run dist
```

Output: `release/Madar-Desk-v0.3-preview.exe`.

## Data storage

Desktop data is written atomically to `%APPDATA%\MadarDesk\tasks.json`. Existing v0.1 data is migrated to v0.2 defaults without removing projects or tasks. The initial sample project is labeled `پروژه نمونه`. Columns can be named, reordered, added and deleted; tasks from a deleted column move to another. Cards are editable and deletable. Projects can be added, renamed and deleted; deleting a project moves its tasks to another project. A manually imported or Drive-restored snapshot creates a local `backup-before-restore-*.json` before replacing active data. JSON export/import is also available without Google Drive.

### v0.2.1 productivity release

- Searches task title, description, labels, checklist, agent reports, project and Windows share link details.
- Project/task links to Windows SMB UNC shares (`\\Server\Share\Folder\file.pdf`). Clicking selects the file in **the current client's** Windows Explorer. Windows SMB rights apply; nothing is uploaded through Madar.
- Timestamped local backup and restore (`%APPDATA%\MadarDesk\backups`) plus one pre-edit automatic daily snapshot, retaining the latest 30 automatic daily snapshots.
- Each PC can choose Jalali or Gregorian display/input, stored locally. Dates remain ISO/Gregorian in common task data.
- Task cards show creation and due date, plus optional estimated/actual duration. Project-based estimation dashboard and simple offline similarity-based task templates are included.

**Version 0.2.1 does not fulfill the broader SQLite/Workspace refactor defined as milestone 0.3 in ROADMAP.md.** The datastore remains JSON.

### v0.2.2 people and collaboration update

- Display name and 12 profile icons or a small user-uploaded photo, with hover tooltips showing name and role on task cards.
- Assign multiple team users to each task; the host checks project membership.
- Users can change their passwords; administrators can revoke old passwords by resetting to a new password. Other login sessions are invalidated.
- Manual Refresh at top of screen, plus 15-second automatic clean-state refresh. Local changes are pushed shortly after each edit, and stale writes are rejected with a recoverable conflict instead of overwriting the server.
- Per-card independent cost-field toggle, with optional return to the project default.
- Solo mode uses a local profile; LAN account profiles remain on the host. Account metadata is **not** included in ordinary project JSON/Drive backups; back up account files separately and securely before host migration.

Full Workspace/Board structure, file uploads and previews, comments, automation, advanced analytics and accounting invoice issuance are **planned rather than implemented**. See PRODUCT_REQUIREMENTS_2026-10-20.md.

### Finance

Project settings have a **cost field toggle**. The global setting can enable it for all current and future projects without losing existing amounts. When enabled: each project has a sale price, each task has a direct cost, and each task checklist step has a cost. Costs are non-negative integer **tomans**, displayed with ASCII comma thousands separators, e.g. `2,500,000 تومان`. Project total expenses sum task direct costs plus all checklist costs, and the estimated profit or loss is sale price minus expenses. These are forecast numbers, not accounting or tax records.

### Local network

See [NETWORK.md](NETWORK.md). The desktop owner can enable a password-protected LAN host, define users with Admin/Editor/Viewer roles and per-project scope, and colleagues can connect from their own PCs using the same EXE. Mutations enforce permissions on the server and reject stale concurrent changes. **HTTP transport does not have TLS: trusted private LAN only.**

## Google Drive

1. In Google Cloud Console, create/select a Google Cloud project, enable Google Drive API and configure its OAuth consent screen.
2. Create an OAuth client ID of **Desktop app** type. Configure test users if the consent screen is in Testing mode.
3. Open **پشتیبان‌گیری و Drive**, paste the client ID and press **اتصال حساب Google**. Sign in via your browser. There is no client secret in the program.
4. Press **ذخیره پشتیبان جدید** to upload a snapshot to the application's private Google Drive `appDataFolder` (scope `drive.appdata`).
5. On the second PC, install the same build, enter the **same OAuth client ID**, sign in with the **same Google account**, display backups and restore.

OAuth uses a local loopback callback, PKCE S256 and a checked state token. Refresh tokens are encrypted using Windows DPAPI tied to your Windows user. The Google Drive folder is private to the OAuth application; files do not appear in the normal My Drive list.

**The feature is a manual backup/restore workflow, not two-way live synchronization or conflict merging.** Restoring replaces the local snapshot after storing a local safety copy.

## Verification scope

`npm test`: runs Python unit tests for local data, version migration, accounting input validation, restore safety, invalid imports, simulated Drive calls, Windows DPAPI, LAN authentication, role/project authorization and simultaneous-write conflict protection. OAuth and real Drive upload/restore require a valid OAuth Desktop client ID and an authorized Google account; they cannot be proven from automated offline tests.

## Scope and limitations

- Google Drive transfers are **user-initiated snapshots**, with no live conflict resolution.
- Progress reports are entered manually; agent execution is not integrated in this standalone release.
- The installed Google Edge WebView2 Runtime is needed on each machine. This executable bundles Python and UI code, but not the WebView2 runtime itself.
- Vazirmatn variable font is bundled inside the EXE and licensed under SIL OFL 1.1 (included in the build resources). No separate font installation is necessary.
- Demo cards can be edited/deleted. A first-run personal workspace is created automatically.

## UI skill

Design principles are drawn from `juliobsz/skills`, skill `awwwards`, with source at https://github.com/juliobsz/skills. See `DESIGN.md` for specific decisions. The Vazirmatn webfont is bundled under SIL OFL 1.1; its license is included at `public/fonts/OFL.txt`.
