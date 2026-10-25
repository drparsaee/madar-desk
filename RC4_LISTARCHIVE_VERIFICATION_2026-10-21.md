# Madar Desk RC4 | Isolated verification and continuity

Date: 2026-10-21. **Experimental candidate, not stable or 100% Trello parity.**

## Executable

- Path: `release/Madar-Desk-v1.0-rc4-listarchive-verified-candidate.exe`
- Size: **13,775,674 bytes**
- SHA-256: `A0B25DF2D0DCA892FCFEA1C51AB3620111E2CBF89DE8EBCE6092BFC8B206FDDC`
- Source package and lock: `1.0.0-rc.4`
- Build: `npm run dist:rc` exit **0**; log `.qa-rc4-build-20261021.log`. Includes later app, Python validator and task duplication fixes not present in RC3.
- Original RC1/RC2/RC3 output filenames were not overwritten.

## Automated verification

- Focused after integration/fixes: 10/10 Python list-archive contract tests PASS, 31/31 JS list-archive/UI tests PASS. Source includes regression fixes for project deletion destinations and active duplicate cards.
- Final prebuild source QA: `py -3.12 scripts/release_qa.py --full`, **exit 0**; output `.qa-postfix-full-20261021.log`.
  - Release subset: **17/17** PASS.
  - Python: **490/490** PASS.
  - JavaScript: **147/147** PASS.
  - Main Python/JavaScript suites: **637** passing tests; the separate 17 release tests may overlap.
- The QA command compared SHA-256 of `src/App.jsx`, `src/taskops.js`, `data_model.py`, `native_app.py`, `lan.py`, `tests/test_list_archive_contract.py` and `tests/listarchive_ui_contract.test.cjs` before and after and printed `TRACKED_SOURCE_STABLE_DURING_QA`. This is a seven-file stability check, not a repository-wide freeze.
- Postbuild EXE GUI smoke: `py -3.12 scripts/v1_gui_smoke.py --exe release/Madar-Desk-v1.0-rc4-listarchive-verified-candidate.exe --timeout 90 --screenshot --output-dir .`, **exit 0**, 9/9 PASS.
- Smoke log: `.qa-rc4-gui-smoke-20261021.log`, retained evidence `v1-gui-smoke-pi4_ij7m/`. It reports DOM, native bridge and font loaded, five board columns, four visible cards and complete PNG 1484×921 (133,753 bytes). Diagnostic `native_done:false` remains; passing PNG integrity alone is not native screenshot callback completion or interactive acceptance.

## Scope and remaining gates

- Board-local list archive/restore preserves stage identity and card/finance data. Source enforces admin management and keeps the last active stage on the host; archive and restore persistence tests pass for isolated JSON/SQLite. The archive controls are present in UI source and component SSR tests.
- **Unverified:** actually clicking archive/restore in the packaged EXE, moving cards across stages with pointer/keyboard, restart of a realistic GUI session, end-to-end user permissions across two actual Windows machines, network reconnect/TLS and complete restore of every domain on production-like data.
- No real APPDATA migration, real Google Drive transfer, installed end-user acceptance, signature, deployment, or stable release approval was performed.
- Publicly documented Trello parity remains incomplete: `TRELLO_PARITY_MASTER_2026.md` currently inventories 220 features and keeps BD13 partial pending end-to-end acceptance. Retain Madar's finance/Jalali/offline differentiators while closing these gaps.

**Decision:** RC4 may be used only as a controlled local test candidate. Stable release and full Trello parity are not confirmed.
