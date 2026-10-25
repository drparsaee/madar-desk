# Madar Desk | Development continuation checkpoint

Updated: 2026-10-21. This is a **workspace-local handoff**, not an assertion that any ChatGPT worker survives a chat or session change.

## Product goal and rules

- Develop Madar Desk toward feature parity with the *publicly documented behavior* of Trello while retaining Madar's Persian/RTL/Jalali UX, local-first Windows application, native finance and invoicing, backups, LAN access, and AI/MCP facilities.
- Keep existing financial and task records intact. Never touch real user `%APPDATA%\MadarDesk` while running checks. Run QA with `py -3.12 scripts/release_qa.py --full`, which isolates APPDATA and LOCALAPPDATA.
- Distinguish **code implemented**, **tests passed**, **EXE built and smoke-tested**, and **real-device/release acceptance**. No private Trello source or authentication is needed for documented feature parity.
- Existing RC1/RC2 outputs in `release/` must not be overwritten. Build each new candidate under a distinct name and record SHA-256.
- This folder currently has **no `.git` directory**. Do not report commits or a clean git working tree for this folder.

## Baseline and verification

- `RC2_PARITY_CANDIDATE_VERIFICATION_2026-10-21.md` contains the older candidate's hashes, isolated QA, GUI smoke, and specific release blockers. The RC2 binary was built before later LAN and list archive integration.
- `TRELLO_PARITY_MASTER_2026.md` contains 220 individually identified capabilities. The latest written snapshot states 39 code-covered, 112 partial, 69 missing. The inventory does not establish feature acceptance.
- `src/listarchive.js` contains pure board-stage archive/restore and `src/App.jsx` and `src/features.jsx` currently reference it in UI. Stage records persist even while hidden. `data_model.py` accepts and validates the optional boolean stage `archived` field.
- On resumption, `node --test tests/listarchive.test.cjs` passed 16/16, `py -3.12 -m unittest tests.test_parity_contract_inventory -v` passed 8/8, and `npm run build` exited 0 (Vite bundled 1,624 modules, chunk-size warning only).
- The new isolated full QA completed successfully on 2026-10-21 with exit 0: 17 release tests, 480 Python tests and 129 JavaScript tests passed; log `.qa-resume-full-20261021.log`. The earlier failed RC2 run remains a separate historical result.
- **New RC3 candidate built and GUI smoke-tested:** `release/Madar-Desk-v1.0-rc3-listarchive-candidate.exe`, SHA256 `90ADC1A08C7D04162BD3098C5EFC8CB0331667CF037978810CDE9F6D2445BEE1`. See `RC3_LISTARCHIVE_CANDIDATE_VERIFICATION_2026-10-21.md` for exact evidence and remaining gates.
- **Post-RC3 source drift:** concurrent edits added checks and fixes for archived-list project relocation, duplication visibility, and native last-active-stage validation. Focused Python 10/10 and JS 31/31 reruns PASS after fixes; full isolated QA was restarted to `.qa-postfix-full-20261021.log` with before/after SHA-256 checks of key files. Do not treat the RC3 EXE as containing the later source changes.
- **Current verified build candidate: RC4** `release/Madar-Desk-v1.0-rc4-listarchive-verified-candidate.exe`, 13,775,674 bytes, SHA-256 `A0B25DF2D0DCA892FCFEA1C51AB3620111E2CBF89DE8EBCE6092BFC8B206FDDC`. Full isolated QA after fixes passed with 17 release, 490 Python and 147 JavaScript tests; tracked seven key files stayed unchanged during the QA command. Build and 9/9 GUI smoke exited 0. See `RC4_LISTARCHIVE_VERIFICATION_2026-10-21.md` for exact limits.

## Next actions for any new agent / chat

1. Read this file plus `RC2_PARITY_CANDIDATE_VERIFICATION_2026-10-21.md`, `LIST_ARCHIVE_API.md` and `TRELLO_PARITY_MASTER_2026.md`; inspect live files and processes. A different agent session may be unable to access the previous session's workers.
2. Read `RC4_LISTARCHIVE_VERIFICATION_2026-10-21.md`, inspect the current on-disk files, and preserve this tested baseline. RC3 is a historical build missing later fixes. Re-run complete isolated QA whenever source changes.
3. Next P0 work: interactive list archive/restore from real Windows GUI with preserved hidden task/finance data and restart persistence; verify role permissions and safe stale revision handling. Automate what can be isolated, then keep two-device acceptance a separate explicit gate.
4. Continue Trello parity work from missing/partial rows, with separate tests and independently reviewable functionality; generate each new candidate under a **new** name and record build and smoke evidence.
5. Update this checkpoint whenever work stops or shifts. Stable release status remains unapproved until real-device/data safety gates have evidence.

## Known limitation of continuity

Workers are scoped to their originating Chat On Steroids run. The 2026-10-21 resumption call to `agents status` returned no workers or retained worker history for **this caller**. That is a visibility/session boundary; it does not prove what happened to workers in the old chat. This file is the durable recovery point independent of worker identity.
