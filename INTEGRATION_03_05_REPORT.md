# Madar Desk | v0.5 integration preview | evidence and limits

Date: 2026-10-20. Status: **technical preview, NOT completed production 0.5**.
The original v0.2.2 executable and v0.3 preview remain untouched.

## Implemented

- Additive legacy-safe Workspace/Board/List/Card model with board-specific stages, label definitions,
  custom fields, named checklists, templates and migration validation. Native bridge legacy
  checklist IDs are now normalized without replacing the original flat legacy records.
- Trello-inspired card label colors, inline expandable checklist, advanced filters, local saved
  searches, Markdown editing, user profiles, DateClock and 15-second client refresh from the
  previous preview.
- LAN server with per-project access, admin/editor/viewer, comments, @mentions, notifications,
  activity, allowlisted rule core, offline cache/queue and three-way merging.
- Drive for desktop folder snapshots and explicit restore, without syncing SMB targets.
- **Experimental peer exchange**: two PCs using the **same LAN account**, same selected Drive
  synced folder and the **same pairing code** may publish authenticated immutable card events
  while the LAN host is unavailable. The peer journal uses HMAC-SHA256 derived with PBKDF2,
  scoped project IDs and original LAN state revision. It does not accept workspace/board
  structure changes or files and reports conflicts instead of last-write-wins. It merges back
  into LAN client pending drafts for host-side permission checks on rejoin. The folder transport
  itself is not authenticated by Google to this program and events are **not encrypted**.
- Standalone tested SQLite revision/CAS store with WAL, FULL synchronous, snapshot integrity,
  audit history and immutable legacy backup-before-import. **Not used as the primary data
  store by the app yet**: tasks.json/collab.json/finance.json are still separate active files.
  The host additionally exposes an explicit unified SQLite export and independently verified
  snapshot without changing its active JSON storage.
- Finance domain: explicit card sales contract with customer and agreed prices, independent
  opt-in internal costs, financial commands and append-only audit ledger. An authorized
  incomplete-to-complete transition can create **one internal Draft invoice** for that
  card+contract. Issuing a numbered invoice requires administrator review/approval. A durable
  completion outbox survives application interruptions; ledger integration currently persists
  in its own finance.json. Windows/LAN Bridge and basic project finance UI wired.
- Host-side attachments now support authenticated upload/list/download, strict 4 MiB
  PNG/JPEG/PDF/TXT allowlist, small passive image/text previews, deletion tombstones,
  request idempotency, SQLite metadata and binary checksum verification. The user's SMB
  links remain separate. A full attachment backup must be triggered separately.
- Rule Builder UI exposes safe notify/comment rule definitions. Real card lifecycle updates
  publish idempotent events through a persistent outbox, and a scheduler checks due dates
  hourly while the host process is running (or manually on demand). The schedule does not
  run while the host is powered off.

## Critical outstanding work

1. This build has **not been run against two physical Windows machines or real Google Drive**.
   Local temp-folder peer tests simulate file delivery; eventual cloud sync and identity
   revocation cannot be asserted. Peer sharing supports one LAN username only, not arbitrary
   multiple users. The peer exchange requires a strong manually shared code and the selected
   Windows Drive folder must actually be synchronized by the Google client.
2. LAN still uses private-network HTTP without TLS. Cloud events are HMAC authenticated but
   plaintext; a shared Google folder is not an authorization boundary. Do not use for secrets.
3. Host state, collaboration, finance and outbox are not yet one SQLite transaction. Finance
   data must be backed up independently; existing task-only JSON backups do not constitute a
   complete financial backup. Never overwrite real tasks.json with test data.
4. Workflow features not fully implemented: secure downloadable previews for all attachment
   types (PDF is download-only), one consolidated all-domain backup/restore wizard,
   complete workspace CRUD, board-specific ACL/restore, rich Markdown renderer, shared saved
   searches, full conditions/actions editor, background due-date operation when host is off,
   mobile client, push notifications, full audit of all card changes, fully tested multi-board E2E.
5. External fiscal invoices, tax rules, required business identifiers, financial document
   output and the jurisdiction-specific accounting ledger have not been implemented.
6. Install smoke test on an independent clean Windows machine, physical two-device LAN/Drive
   outage/rejoin test, full UI interaction tests and actual recovery rehearsal are outstanding.
7. There is no Git repo at the workspace root. Source ZIP is an archival snapshot and does not
   substitute for version control/traceable commits.

## Verification

Latest local observations on 2026-10-20:

- `npm test`: **212 Python tests PASS, 10 JavaScript tests PASS** (exit code 0).
- `npm run build`: Vite v6.4.4 successfully built React assets (exit code 0).
- `npm run dist`: **PASS** (PyInstaller Windows onefile; exit code 0).
  PyInstaller emitted nonblocking hidden-import warnings for pycparser.lextab,
  pycparser.yacctab and importlib_resources.trees. Other code paths that might
  depend on those optional imports have not been specifically tested.
- `Madar-Desk-v0.5-integration-preview.exe`: **13,484,055 bytes**.
- EXE SHA-256:
  `E43287A7FA1D108144059226CF18C54751240105356B9DCF2EDBD641178F5686`
- Windows EXE QA with isolated `.qa-v05-integration-final` APPDATA: WebView2
  `readyState=complete`, React root length `34393`, `bridgeType=object`,
  `pywebviewType=object`, `fontLoaded=true`, `theme=light`,
  `stageCount=5`, port `1238`. The file
  `release/Madar-Desk-v0.5-integration-preview-final.png` was created
  (**138,853 bytes**) and visually inspected. It shows the new finance and
  automation buttons; this is a smoke test, not interactive E2E testing.
  `screenshot.done=false` in the initial JSON diagnostic is not treated as
  proof of callback completion, despite the existing image file.
- Only QA process IDs `13024` (child) and `26348` (parent) were stopped
  after checking their executable paths; production/installed processes were
  not stopped.
- Real HTTP request tests cover LAN attachment list/download/write ACL,
  finance and rules read permission, and scheduler admin-only operation.
- `createUnifiedSqliteBackup` integration test confirms a verified
  four-domain archive can be created without activating SQLite or modifying
  original JSON source bytes. Attachment binary backups remain separate.

These checks do **not** prove complete features, clean-system installation or
real multi-PC/Google Drive connectivity.

## Risk policy

Never overwrite v0.2.2 or v0.3 preview. The new EXE uses a distinct filename and isolated
QA APPDATA. No real customer data migration or Drive connection is performed during QA.
The version label reflects integrated work, **not** certification of all v0.3-0.5 features.
