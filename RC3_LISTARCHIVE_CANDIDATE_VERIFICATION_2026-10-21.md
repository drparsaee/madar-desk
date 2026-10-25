# Madar Desk RC3 List Archive Candidate | Verification record

**ARCHIVED EVIDENCE / SUPERSEDED FILE IDENTITY:** This document describes an earlier EXE with SHA256 `90ADC1A0...`. A later RC3 rebuild reused the generic filename and now has different bytes. For the independently rehashed and GUI-smoke-tested current candidate, use the **unique SHA-pinned** `release/Madar-Desk-v1.0-rc3-listarchive-eeadcdac-candidate.exe` and `RC3_EEADCDAC_CANDIDATE_EVIDENCE_2026-10-21.md`. Do not treat the older hash below as the live file's hash.

Date: 2026-10-21. **Experimental candidate. NOT stable 1.0; NOT 100% Trello parity.**

**Post-build notice:** Additional archive-integration source and regression-test changes landed after the RC3 EXE/QA above. Two new regression checks initially failed, subsequently changed source paths and focused checks passed. The original RC3 executable DOES NOT include those later fixes. A new full isolated QA is required for the later source snapshot and a new executable must be built under a distinct name. Never equate this earlier candidate's green QA with the latest mutable workspace.

## Artifact and build

- File: `release/Madar-Desk-v1.0-rc3-listarchive-candidate.exe`
- Size: **13,776,172 bytes**
- SHA256: `90ADC1A08C7D04162BD3098C5EFC8CB0331667CF037978810CDE9F6D2445BEE1`
- Source package and lockfile: `1.0.0-rc.3`; `npm run dist:rc` exits **0**.
- Build log: `.qa-rc3-build-20261021.log`; PyInstaller bundled native Python / pywebview and compiled Vite distribution. Vite emitted its bundle size warning; build completed.
- Old RC2 executable is still present under its separate name. SHA256 rechecked as `5D230D0397FC2D1011E752060833E98636EB1812C2384122F1817691E46FD1A0`.

## Scope of source assembled into RC3

- Includes source changes after the RC2 build: LAN response handling for malformed media-type bodies, synchronized CAS concurrency tests, board-local list archive/restore, archived-stage validation, and UI integration in `src/App.jsx` and `src/features.jsx`.
- List archival sets `boards[].stages[].archived` while retaining the stage and every associated task / financial record. The source settings panel offers archive and restore. The normal board view, card creation and drag/drop destinations exclude archived stages.
- Existing card order, Workspace management, finance, Jalali/RTL, backups, LAN and MCP modules remain in this source build. This is code inclusion, not independent interactive acceptance of each behavior.

## Direct verification

- `node --test tests/listarchive.test.cjs`: **16/16 PASS**, exit 0.
- `py -3.12 -m unittest tests.test_parity_contract_inventory -v`: **8/8 PASS**, exit 0.
- `npm run build`: exit 0, Vite bundled **1,624** modules.
- `py -3.12 scripts/release_qa.py --full`: **exit 0**, APPDATA and LOCALAPPDATA isolated in a disposable directory. Log: `.qa-resume-full-20261021.log`.
  - Dedicated release regression tests: **17/17 PASS**.
  - Full Python tests: **480/480 PASS**.
  - Full JavaScript tests: **129/129 PASS**.
  - Main suite total **609 PASS** (release subset is separately reported, not assumed disjoint).
- `py -3.12 scripts/v1_gui_smoke.py --exe release/Madar-Desk-v1.0-rc3-listarchive-candidate.exe --timeout 90 --screenshot --output-dir .`: **exit 0**, status **PASS**, 9/9 checks PASS.
  - Log `.qa-rc3-gui-smoke-20261021.log`; evidence `v1-gui-smoke-_ssn72k3/diagnostics.json` and `screenshot.png`.
  - Verified loopback page, DOM loaded, mounted root, native bridge, bundled font, five sample board columns, four visible sample cards, and complete 1484×921 PNG (133,718 bytes).
  - Smoke harness reports `native_done:false` for its native screenshot callback, despite validating the PNG byte stream/CRC. The screenshot was visually inspected for a populated Persian board. Neither observation verifies interaction-level behavior.

## Release and product gates still open

1. Interactive EXE actions: archive and restore lists with cards/finance, card reorder with mouse/keyboard, Workspace permissions and persisted state after restart.
2. Physical two-PC Windows LAN tests across administrator/editor/viewer, TLS/pinning, disconnected work, conflicts, reconnect, and live database transfer.
3. Full restore testing on production-like synthetic data across tasks, financial records, attachments, LAN users and Planner with rollback. No test ran against real user APPDATA.
4. `TRELLO_PARITY_MASTER_2026.md` continues to track 220 capabilities. BD13 remains **partial** until user-flow acceptance, and many Trello areas remain partial/missing.
5. No code signing, deployment, update-channel publication, real-user migration, Trello protected code capture or live remote-service integration acceptance has been performed.

**Release decision:** RC3 is a locally built and smoke-tested experimental Windows executable. It is **not approved as stable or full-parity production release**.
