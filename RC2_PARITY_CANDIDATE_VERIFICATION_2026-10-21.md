# Madar Desk RC2 Parity Candidate | Verification Record

Date: 2026-10-21. **Candidate only. NOT stable 1.0 and NOT 100% Trello feature parity.**

## Artifact

- File: `release/Madar-Desk-v1.0-rc2-parity-candidate.exe`
- Size: **13,772,061 bytes**
- SHA256: `5D230D0397FC2D1011E752060833E98636EB1812C2384122F1817691E46FD1A0`
- Builder: `npm run dist:rc` after updating package and lockfile versions to `1.0.0-rc.2`.
- Build output: `.qa-rc2-build.log`, exit 0.
- No install, migration of actual user profile, network deployment or release-channel publication performed.
- The old RC1 EXE SHA256 was rechecked and remains `A547F2EC1959382537A17FDA04A7709FDEE457D63478226B279EBC7383844C71`. The original RC1 distribution ZIP was also separately rehashed earlier in this session; no RC1 binary/ZIP was overwritten.

## Scope of candidate

- Card ordering is bounded persisted `cardOrder` 0..1,000,000 with per-board list ordering, drag/drop before/after, lane change and Alt+arrow within lists. Legacy strange-but-host-valid IDs can still **display**, but unsafe/ambiguous ID mutation is deliberately rejected.
- WorkspaceManager GUI supports selection, creation, renaming, archive/restore and moving boards with existing LAN admin restrictions. A project's boards can live in different workspaces; board navigation is scoped to selected workspace.
- Solo local UI `getStateForUi` issues a CAS hash. `saveState` verifies it under an OS-level cross-process writer lock before writing JSON/SQLite, rejects stale UI snapshots and a removed token in modern UI mode. Pure `getState` and backups do not include `__localRevision`. Existing legacy Python direct getState/saveState clients have a compatible tracked-read baseline, but untrusted tokenless callers and arbitrary external writers have not been independently exhaustively tested.
- Previously existing Persian/RTL/Jalali, finance, invoices, LAN, offline, backup, Drive and AI/MCP surfaces were retained, not replaced by Trello code.

## Automated evidence

- Fresh isolated `py -3.12 scripts/release_qa.py --full`: exit **0**, **477 Python PASS + 113 JavaScript PASS = 590 PASS**, no reported test failures. Log: `.qa-parity-final-isolated.log`.
- The runner isolates APPDATA/LOCALAPPDATA; it does not touch the user's real profile.
- Earlier dedicated CAS suite: 9/9 PASS; independent Node focused card-order and Workspace suites 37/37 PASS after legacy ID compatibility fix.
- PyInstaller build exit 0. Electron/browser packaging was not used; native Python/WebView2 entrypoint was bundled.
- Candidate EXE GUI smoke: `py -3.12 scripts/v1_gui_smoke.py --exe release/Madar-Desk-v1.0-rc2-parity-candidate.exe --timeout 90 --screenshot --output-dir .` exit **0**, 9/9 checks PASS (loopback, DOM ready, root mount, body content, bridge objects, font, 5 board columns, 4 visible sample cards, complete PNG). Log `.qa-rc2-gui-smoke.log`; evidence folder `v1-gui-smoke-1t_7n1ni`.
- Screenshot 1484x921, full PNG CRC and compressed payload verified by harness. `native_done:false` from diagnostic signal; verified file integrity is not equivalent to native screenshot callback completion or visual interaction acceptance.

## Strict outstanding gates

### Post-build evidence and source/code divergence

- Two additional synchronized threaded JSON/SQLite CAS tests were added **after the first 590-test green QA** and passed in isolation (12/12 in their focused module, including two new concurrent cases). A second complete isolated QA invocation included **479 Python tests**, with **478 passing and one network-transport ERROR** at the existing malformed-media-type acceptance request (Windows `WinError 10053`). This invocation exited **1** before reaching the JavaScript suite; it must not be represented as a clean full run. The same focused HTTP test passed on **four subsequent isolated repetitions**.
- Static inspection identified a **probable** transport trigger: the host replied 415 before consuming the bounded POST body, potentially causing a Windows TCP reset. Source-only `lan.py` and a new repeated-415 acceptance test were changed **after RC2 EXE was built**; both targeted HTTP tests then passed. This probable cause/fix is **not** included in the EXE whose hash appears above. The next candidate needs a new name, new build, hashes, smoke and complete QA.
- A pure list-archive parity module is being developed for the next tranche; it is not in the RC2 candidate.

1. Trello parity master `TRELLO_PARITY_MASTER_2026.md` lists **220 independently enumerated features**: **39 covered in observed code, 112 partial and 69 missing** (snapshot after current integration). **These are not acceptance percentages.**
2. Two separate physical Windows PCs over actual LAN: transport, certificates/pins, roles, access isolation, stale CAS, reconnect/offline, conflict handling, and full interactive session not verified in this candidate.
3. Interactive Windows GUI acceptance for actual card gestures, keyboard reordering, Workspace CRUD/ACL, persistence after restart, cross-role navigation, and realistic user dataset not performed.
4. Full recovery of attachments, LAN identity, Planner localStorage, financial records, and recovery rollback with production-like data remains a release gate. Full recovery ZIP may be plaintext and must not be automatically uploaded to Drive.
5. Mobile, enterprise, advanced Trello automation, guest/Power-Up/API parity, and numerous feature contracts are incomplete. Trello proprietary internals, private data, code or authenticated interface were not reverse engineered.
6. This candidate is not signed or approved for stable deployment. Restore/migration against real user APPDATA was intentionally **not run**.

The **only** current publication decision justified by this evidence is: standalone **experimental RC2 candidate available for controlled testing**, stable/100%-parity **NOT approved**.
