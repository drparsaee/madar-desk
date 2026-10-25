# Madar Desk v0.5 | release QA checklist

This checklist applies to the **v0.5 RC1 candidate**, not to a certified production release. Python integration tests exercise the native Bridge, HTTP LAN service and HTTPS PIN checks under disposable `APPDATA`/`LOCALAPPDATA`. A separate isolated Windows EXE smoke test has run; the full physical workflow and real Google account have not been accepted.

## Automated checks

From `D:\CoS-Test\madar-desk` on Windows with Python dependencies installed:

```powershell
py -3 scripts\release_qa.py
py -3 scripts\release_qa.py --full
```

The first invocation executes `tests/test_release_*.py`; the second also runs `npm test`, including all existing Python and JavaScript tests. Both commands create a fresh disposable Windows AppData directory for subprocesses and remove it afterward. Each release integration test also creates its own disposable AppData root. An exit code of `0` means the **automated tests** passed, not that the distribution is approved for release.

The release regression tests cover:

- Real Bridge `getState` → `saveState` → process object reinitialization; distinct boards, local columns, card values and independent projects.
- Local JSON snapshot creation, restore and pre-restore copy; corrupt/invalid backup rejected with the original state left intact.
- Verified archival SQLite export of tasks, boards, collaboration and finance; source JSON bytes unchanged.
- Real localhost LAN GET/POST, login, project-scoped board visibility, admin-only board structural writes, 409 revision conflicts, viewer write restrictions.
- Authorized editor completes a card with an explicit sales contract, produces one Draft invoice, idempotent retry, finance ACL and finance persistence after Bridge restart.
- Explicit opt-in host migration to unified SQLite, HTTP edits on active SQLite and restore of a four-domain `.sqlite3` backup after further task/collaboration edits.
- Explicit regression observation that restoring an older task-only JSON snapshot **does not roll back** finance or collaboration records.

## Manual acceptance gates

Status is intentionally **unverified** unless a real QA operator fills in evidence. Keep source/archive and all existing release EXEs intact. On any physical machine, confirm that a *dedicated throwaway Windows account/profile* is used before launching an EXE.

| Gate | Procedure | Status / evidence |
| --- | --- | --- |
| EXE boot & visual | Run the uniquely named v0.5 RC1 EXE under fresh isolated profile; verify WebView2, Persian RTL fonts, editor, finances and automation screens | One isolated EXE startup + captured screenshot checked; interactive modal workflows pending |
| Board UI workflows | Create two boards, add cards/checklists/labels, edit board-local columns, restart app; compare values | Unverified |
| Permissions and transport | Connect a second Windows PC, test admin/editor/viewer and project scoping; exercise HTTPS with configured cert and pinned fingerprint | Unverified on two physical PCs |
| Concurrent edits | Modify the same card from two clients, confirm conflict notification and deliberate recovery | Unverified in actual UI |
| Finance UI | Set explicit contract as admin, complete card as editor, confirm one Draft and admin-only issue | Unverified in actual UI |
| Local backup restore | With disposable test records, verify recoverability after restart, compare source and restored snapshots | Unit/integration tested; manual rehearsal pending |
| Complete recovery | Independently back up and restore tasks, collaboration, finance, outbox, account profiles, attachments and binary contents | SQLite covers the four data domains; end-to-end whole-app recovery unverified |
| Attachments | Upload, preview, download and ACL-check PNG/JPEG/PDF/TXT from both PCs | HTTP tests exist elsewhere; physical smoke pending |
| Google Drive | Verify actual Drive Desktop sync completion, offline queue, conflict detection and reconnect | Unverified against real Google Drive |
| Windows clean install | Run on a fresh supported Windows build, capture installation, runtime errors, fonts and screenshots | Unverified |

## Explicit release limitations

1. Legacy mode still uses separate JSON files (`tasks.json`, `collab.json`, `finance.json`, completion outbox). The host now has an **explicit opt-in migration** to four-domain transactional SQLite. In activated SQLite mode, a local `.sqlite3` backup and restore can recover those four domains together. Neither mode includes attachment binaries or LAN user/profile data in that database backup; `createUnifiedSqliteBackup` is an explicit export, not itself a switch of active storage.
2. Legacy `.json` local backups, exported task JSON and Google Drive folder snapshots cover only task state. They do not roll back finance or collaboration information. Even when SQLite is active, restoring a JSON task snapshot keeps the other domain values intact. This is a partial restore operation with possible cross-domain business inconsistencies. Select the SQLite archive when four-domain recovery is required.
3. The default LAN listener is HTTP intended for a trusted private network. An optional TLS listener and HTTPS certificate-fingerprint verification are integrated into the native Bridge and desktop LAN dialog; localhost handshake, login, restart and wrong-pin rejection are tested. Certificate provisioning, fingerprint distribution and real two-PC behavior still require physical acceptance. The desktop peer exchange has not been validated on two actual PCs with real Drive sync.
4. Domain invoice logic produces internal drafts from explicitly entered contracts. Official fiscal issuance/export, tax compliance and full accounting remain outside the verified release scope.
5. These regressions deliberately avoid touching real `%APPDATA%`, live Drive credentials, users' customer data or preexisting executable release artifacts.

For an actual release decision, record **machine and Windows version, EXE path and hash, exact commands, exit codes, screenshots, UI workflow results, physical LAN/Drive conditions, recoverable backup set, reviewer and timestamp**. A successful `--full` alone does not close the remaining manual gates.
