# Madar Desk / مدار — 1.0 RC1 verification record

**Date:** 2026-10-21  
**Workspace:** `D:\CoS-Test\madar-desk`  
**Package version:** `1.0.0-rc.1`  
**Release decision:** **Windows release candidate, NOT a verified stable 1.0 release.**

This report distinguishes working code, reproduced automated tests, isolated
Windows GUI execution, and features that are only adapters or unverified.
The earlier `release/Madar-Desk-v0.6-custom-preview.exe` is retained unchanged.
No Git repository was created; no production installation, user-data restore,
or real `%APPDATA%` migration was performed during release QA.

## Artifacts in `release/`

| File | Purpose | Evidence |
| --- | --- | --- |
| `Madar-Desk-v1.0-rc1.exe` | Windows x64 single-file desktop candidate | PyInstaller build exit 0; isolated WebView2 smoke 9/9 PASS |
| `Madar-Desk-MCP-v1.exe` | Separate opt-in, legacy read-only MCP stdio sidecar | PyInstaller exit 0; bundled EXE `initialize` + 3-tool discovery exit 0 |
| `Install-MadarDesk.ps1` | Hardened manual updater to explicit install directory | Source copied byte-identically from `scripts/Install-MadarDesk.ps1`; 17 focused tests PASS |
| `Install-Madar-Desk-v1.0-rc1.ps1` | Simpler versioned per-user copy; does not replace an older EXE | Isolated dry-run/install/no-op/bad-hash test PASS |
| `Madar-Desk-v1.0-rc1-source.zip` | Source, tests, built assets and docs | Archive CRC/list verification, exact hashes in release manifest |
| `Madar-Desk-v1.0-rc1-backupscope-verified-distribution.zip` | Updated bundle with above artifacts and this verification record | New verified artifact, supersedes earlier RC1 distribution |

An earlier `Madar-Desk-v1.0-rc1-distribution.zip` was produced before the
backup-scope correction. It is **superseded**; do not install that earlier ZIP.

The **hardened `Install-MadarDesk.ps1`** is the recommended repeatable updater
for a user-selected ordinary local folder (e.g. `D:\Apps\MadarDesk`); it requires
the explicit source EXE and destination, never runs or downloads the program,
and preserves the previous binary with rollback on ordinary errors. It is not
an MSI/MSIX or background auto-update service. Do not run both installers on
the same destination; they use different target names and policies. See
`PORTABLE_INSTALL_V1.md`.

### Windows EXE hashes recorded after RC rebuild

* Main EXE after backup-scope rebuild: **13,763,240 bytes**, SHA-256:
  `A547F2EC1959382537A17FDA04A7709FDEE457D63478226B279EBC7383844C71`
* MCP EXE: **7,757,306 bytes**, SHA-256:
  `02D8B81CD55CF318526C6ED05FF43D0F71846ED3B59E42F209FEB2E9324D415A`

These checksums measure local files, not Authenticode publisher signatures,
antivirus verdicts or proof of safety. Verify them independently when copying
outside the workspace. Final source/distribution hashes are written in the
release manifest after those archives are assembled.

## Verification evidence

* `npm run build` and Windows PyInstaller RC build: **PASS**.
* Latest complete Python + Node source regression:
  `release_qa.py --full` with `.qa-v1-rc1-backupscope-isolated.log` returned
  **exit 0** and **447 Python tests PASS + 76 JavaScript tests PASS** with
  disposable APPDATA/LOCALAPPDATA, zero test failures. The earlier
  `.qa-v1-rc1-shipping-alltests.log` is pre-correction evidence only
  (442 Python tests and 76 JavaScript tests).
* Real mounted API on pinned localhost HTTPS: GET/PATCH, access/finance isolation,
  idempotency, revoked keys, malformed body/header and `Transfer-Encoding`
  framing checks. Security integration suite **11/11 PASS**, combination **24/24
  PASS**. Both concurrent localhost listeners were on **one** machine.
* Offline full-recovery tests included five-domain activated SQLite, audit,
  receipts, pending automation jobs and actual attachment blobs; worker's
  isolated backup/restore tests **4/4 PASS**, plus corruption rejection.
* Isolated Windows desktop smoke on **rebuilt backup-scope EXE**:
  `scripts/v1_gui_smoke.py --screenshot`
  **9/9 PASS** on rebuilt EXE. `readyState=complete`, visible native bridge,
  Vazirmatn font loaded, five Kanban columns, four sample cards. Real PNG
  **1484 × 921**, validated complete PNG CRC/IEND/zlib; visually inspected.
  Evidence: `v1-gui-smoke-gtyheu3q/diagnostics.json` and `screenshot.png`.
  Native asynchronous screenshot callback still reports `done=false` even
  though the file passes independent image verification; logged as a warning.
  Owned test-process PID was confirmed exited, and temporary profile removed.
* Portable hardened updater: **17/17 PASS** in disposable folders. Versioned
  installer: **1/1 PASS**. Neither installed onto the real user profile.
* MCP adapter: **9/9 PASS** in worker's real TLS loopback+stdio tests; its
  packaged MCP EXE separately performed JSON-RPC initialize and discovery of
  all three read-only tools, exit 0. Third-party MCP clients were not tested.
* Signed webhook outbox: **16/16 PASS** for pure deterministic queue, HMAC,
  retries and refusal; **not** a mounted delivery service.
* P0 backup-scope correction: both local JSON and SQLite backup methods now
  return `complete:false`, precise `scope`, `omitted`, and `note` fields.
  Five-domain SQL snapshot still includes only its configured database domains,
  never attachment binaries or browser Planner data. The backup UI explains
  these limitations and the offline maintenance recovery route. **6/6 synthetic
  Bridge scope tests PASS** with actual JSON and SQLite backup byte checks.

The isolated QA runner replaces APPDATA and LOCALAPPDATA for children with a
new disposable folder. Focused test reports are not substitutes for a real
two-computer or production-data acceptance test.

## Included functionality and boundaries

The RC includes existing project/workspace/board and financial workflows,
Kanban/card extras, role-aware LAN, personal Planner while app is open, reports
and CSV, Trello JSON import, native attachments, local backup, opt-in unified
SQLite storage, opt-in five-domain automation journal, a secure versioned
HTTPS REST route, offline iCalendar **file** import/export, and a bounded
read-only MCP sidecar. Financial fields are excluded from general report CSV
and from the external integration card projection.

The new automation journal is an **explicit, one-way opt-in** after SQLite
activation. Old v0.6 executables cannot read a five-domain activated snapshot.
Activation creates a pre-activation database backup; preserve that backup and
use a planned rollback, never silently downgrade a populated installation.

Full-recovery ZIP archives are **not encrypted** and can contain sensitive LAN
password hashes, financial records and attachments. They are **offline-only**:
close all writers and use `maintenance_recovery.py` with explicit confirmation;
the app refuses startup when a pending restore journal is present. Never
automatically upload these full archives to Drive. Existing task-only Drive
backup has a different, limited scope.

## Open blockers for a stable 1.0 claim

1. **Two physical computers** with real LAN permissions, reconnect, simultaneous
   saves and offline conflict scenarios have not been tested. Two localhost
   services on one machine are not equivalent.
2. **Google/Outlook OAuth calendar synchronization** is not implemented/tested.
   Only bounded `.ics` file interchange exists; no continuous external sync.
3. **Webhook outbound transport** is not activated. `webhook_outbox_v1.py` is a
   deterministic signed queue library only. TLS/SSRF-validated recipient config,
   trusted secret storage, authenticated delivery and atomic host persistence
   are still required before sending real callbacks.
4. **MCP compatibility** is limited to a bounded legacy stdio subset; latest
   protocol clients, external integrations and physical LAN remain unverified.
5. **GUI acceptance** established rendering and a valid screenshot, not every
   interactive financial, Planner, automation, import, drag-and-drop, or update
   workflow on installed systems.
6. **Reminder delivery while the program is closed**, signed installer,
   unattended update catalog, production migration/restore, full performance
   benchmark and ongoing crash telemetry are not established.

**Conclusion:** RC artifacts can be reviewed and trialed in a disposable/test
profile. Automated evidence is substantial, but the six gaps above prevent an
evidence-based declaration of final **stable v1.0**.
