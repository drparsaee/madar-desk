# Madar Desk RC5 | Reversible Card Trash Candidate

Verification date: 2026-10-21. **Experimental candidate only. NOT Stable 1.0; NOT 100% Trello parity.**

## Exact executable identity

- File: `D:\CoS-Test\madar-desk\release\Madar-Desk-v1.0-rc5-cardtrash-candidate.exe`
- Measured size: **13,777,731 bytes**.
- SHA256: `8B601330C003D5C7DB9C81AAABAC2BE602BAED69F42B4C4D808810997FB4CD94`.
- `package.json` and `package-lock.json` version: `1.0.0-rc.5`.
- Build: `npm run dist:rc`, **exit 0**, `.qa-rc5-cardtrash-build.log`. Includes Vite bundle, bundled Python Windows/pywebview backend and card-trash module.
- Filename preflight `scripts/ensure_new_release.py` refuses overwrite if target exists. Independently tested against the created EXE: returned **exit 3** as expected, SHA unchanged.
- Older release EXE SHA checks observed during this run:
  - RC1: `A547F2EC1959382537A17FDA04A7709FDEE457D63478226B279EBC7383844C71`.
  - RC2: `5D230D0397FC2D1011E752060833E98636EB1812C2384122F1817691E46FD1A0`.
  - RC4: `A0B25DF2D0DCA892FCFEA1C51AB3620111E2CBF89DE8EBCE6092BFC8B206FDDC`.
- No previous RC EXE was overwritten; no installation or migration of real user APPDATA was performed.

## Changes in this candidate

- `src/cardtrash.js` now powers `App.jsx` card deletion and restoration, changing only optional `task.deleted` marker.
- Normal card views, counts, reporting, Planner, duplicate suggestions and editor exclude trashed cards; a separate role-gated Trash dialog displays cards and offers restore.
- `data_model.py` and `native_app.py` validate an optional `deleted` value as a real boolean, rejecting coerced strings/numbers.
- The original card ID, board, list, task order, checklist, financial amounts, invoice/attachment references and separate persistent finance/attachment records are not purged by this operation.
- Admin/edit ACL gates and existing whole-state CAS still apply. A viewer cannot restore. Archived board/workspace rejects restore until reactivated; archived *list* is a valid retained destination.
- Permanent purge and billing cancellation deliberately out of scope.
- RC4 list archive, Workspace UI, persistent card order, Persian RTL/Jalali, offline, LAN, AI/MCP, finance and backup code remain present.

## Automated evidence

1. Fresh isolated `py -3.12 scripts/release_qa.py --full`: **exit 0**, release regression subset **19 PASS**, main Python suite **502/502 PASS**, JavaScript **176/176 PASS**, hence **678 main-suite PASS**, zero failures. The 19 release regression tests are not assumed disjoint. Output: `.qa-rc5-cardtrash-full.log`. This runner isolates APPDATA/LOCALAPPDATA.
2. Additional focused `tests.test_card_trash_contract`: **10/10 PASS**. Covers standalone JSON + opt-in SQLite saves, reopen and reverse action, real synthetic invoice/finance and uploaded attachment bytes/refs, invalid flag atomic rejection, direct LAN Admin/Editor/Viewer project grants and stale CAS.
3. Focused pure `tests/cardtrash.test.cjs`: **18/18 PASS**, immutable/finance preservation and guarded transitions; React static/SSR `tests/cardtrash_ui_contract.test.cjs`: **11/11 PASS**, role visibility, modal actions, archived containers, no permanent purge.
4. Re-run of inventory and release-name tests **10/10 PASS**, combined UI/pure focused **29/29 PASS** after documentation update.

## GUI smoke of this EXE

- `py -3.12 scripts/v1_gui_smoke.py --exe release/Madar-Desk-v1.0-rc5-cardtrash-candidate.exe --timeout 90 --screenshot --output-dir .`: **exit 0**, harness **9/9 PASS**.
- Log: `.qa-rc5-cardtrash-gui-smoke.log`.
- Evidence folder: `v1-gui-smoke-cm18aeht`.
- Checks report loopback, complete DOM, mounted app root, native bridge, loaded font, 5 sample columns, 4 sample visible cards, complete PNG **1484 × 921** and **133,253 bytes**.
- Screenshot diagnostic includes `native_done:false` despite CRC-validated PNG. Do not report native screenshot callback completion.
- Critically, the smoke **does not directly click the Trash/Restore controls**, exercise a real user's finance views, or verify GUI save/restart interactions.

## Not yet approved

- Functional Trello parity is not complete. The 220-feature public-documentation inventory was last code-snapshotted as **39 covered / 112 partial / 69 missing**; CD05 remains **partial** pending interactive and real LAN acceptance. These are inventory classifications, not a verified percentage of full Trello behavior.
- There is no physical two-Windows-PC LAN acceptance with real TLS/pinning, project roles, concurrent writes, disconnect/reconnect and recovery.
- Complete production-like backup/restore of task state, finance, attachment binaries, LAN accounts, local Planner and rollback has not been demonstrated end-to-end on a real install.
- The EXE has not undergone installer/signing/updater, realistic user migration, accessibility, interactive end-to-end role matrix or mobile/enterprise parity acceptance.
- Never upload plaintext complete recovery ZIP automatically to Drive. Never call this package Stable 1.0.

**Release decision:** RC5 is a SHA-identified **experimental Windows test candidate**, not a production-approved stable release. Remaining manual/hardware and all missing Trello feature acceptance gates must be completed before claiming 100%.
