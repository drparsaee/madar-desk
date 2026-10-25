# Madar Desk RC3 | SHA-pinned candidate verification

Date: 2026-10-21. **Experimental candidate ONLY. Neither stable 1.0 nor 100% Trello parity.**

## Identity and provenance

- Preferred **SHA-pinned, non-overwritten copy**: `release/Madar-Desk-v1.0-rc3-listarchive-eeadcdac-candidate.exe`.
- Bytes verified on disk: **13,776,797**.
- SHA256 independently computed for source EXE and its new copy, both matching:
  `EEADCDAC10409C1F9D3177DDE6DDF0593C35E173778DB126892E23570AEC86D5`.
- It was copied from `release/Madar-Desk-v1.0-rc3-listarchive-candidate.exe` after a successful `npm run dist:rc` exit **0**, log `.qa-rc3-build.log`. The source files' observed modification times precede that PyInstaller build's completion time.
- `package.json` and lockfile declare `1.0.0-rc.3`. Build includes React/Vite, `src/listarchive.js`, `src/App.jsx`, host Python validation, local CAS, LAN and existing Madar modules.
- **Collision caveat:** An earlier verification document, `RC3_LISTARCHIVE_CANDIDATE_VERIFICATION_2026-10-21.md`, described a different earlier EXE of **13,776,172 bytes**, SHA256 beginning `90ADC1A0`, under the same non-unique `...rc3-listarchive-candidate.exe` filename. That earlier hash was **not** the value observed after our later rebuild and may no longer be present. Do **not** attribute the older document's artifact bytes, screenshot or test totals to the new SHA-pinned copy. A separate filename was created specifically to preserve the exact later bytes. Do not run a future build into the same filename.

## Current-source automated QA

- Isolated full release QA `py -3.12 scripts/release_qa.py --full`: exit **0**, **490 Python PASS + 147 JavaScript PASS = 637** main-suite tests, zero failures; log `.qa-bd13-reconciled-full.log`.
- `py -3.12 -m unittest tests.test_list_archive_contract -v`: **10/10 PASS** for host state validation, JSON and opt-in SQLite archive/restore/reopen, finance preservation, LAN admin/editor/viewer and stale revision conflicts in temporary APPDATA roots.
- Node focused combined suite `tests/listarchive_ui_contract.test.cjs`, `tests/boardops_archive_destination.test.cjs`, `tests/taskops.test.cjs`: **22/22 PASS**. Existing pure list archive `tests/listarchive.test.cjs`: **16/16 PASS**.
- The host enforces retention of at least one active board list in addition to frontend checks; archived columns stay in authoritative `boards[].stages` and associated task/finance records are not deleted by archive/restore.
- The full QA run preceded the build; the underlying source modification times examined for `App.jsx`, `taskops.js`, `lan.py` and related modules were earlier than the EXE's build timestamp. No full test has run against a real installed user-data profile.

## Executable smoke for the exact pinned EXE

Command:

```powershell
py -3.12 scripts/v1_gui_smoke.py --exe release/Madar-Desk-v1.0-rc3-listarchive-eeadcdac-candidate.exe --timeout 90 --screenshot --output-dir .
```

- Exit **0**, smoke report **PASS 9/9 checks**: loopback, DOM loaded, root mounted, body text, JS/pywebview bridge, bundled font, five seeded columns, four seeded visible cards and a structurally valid screenshot.
- Log `.qa-rc3-eeadcdac-gui-smoke.log`, evidence folder `v1-gui-smoke-6jefcak1`.
- PNG 1484×921, **133,814 bytes**, CRC/zlib validation PASS. The harness also returned `native_done:false`; therefore do not claim that the native screenshot callback completed or that interactive list archival was manually inspected.

## Older release verification (separate artifacts)

- RC1 EXE **13,763,240 bytes**, SHA256 `A547F2EC1959382537A17FDA04A7709FDEE457D63478226B279EBC7383844C71`.
- RC2 EXE **13,772,061 bytes**, SHA256 `5D230D0397FC2D1011E752060833E98636EB1812C2384122F1817691E46FD1A0`.
- Original verified RC1 ZIP **22,056,675 bytes**, SHA256 `6AC9B3E9F0ECBF60262694097DD6B4736441986C3C3CB88992752D49780B5C61`.
- These three older files' checksums were re-read from disk during this session and matched the recorded references. No claim is made that the earlier non-unique RC3 filename remained immutable.

## Hard gates before stable or complete parity

1. Interactive archive/restore and card reorder with a *real* Windows GUI, save/restart, multi-workspace role and financial visibility acceptance.
2. Physical two-PC Windows LAN with TLS/pinning, role downgrade, offline/reconnect, concurrent writers, disconnected/conflict handling.
3. Realistic complete backup/restore with attachments, finance, LAN identity and Planner localStorage plus rollback. No real APPDATA has been touched.
4. Code-signing/install/update and durable clean uninstall acceptance. No production deployment or user-data migration was run.
5. `TRELLO_PARITY_MASTER_2026.md` tracks **220** scoped public Trello feature contracts. BD13 has functioning code/tests but remains partial pending interactive acceptance; many other features are partial/missing. The snapshot **39 covered / 112 partial / 69 missing** is code-based, not a verified 100% Trello acceptance result.

**Decision:** This pinned EXE is available as a local **experimental candidate**. Stable/100%-parity approval is explicitly withheld.
