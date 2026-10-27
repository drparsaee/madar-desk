# Madar Desk RC13: Vitrea / Fixed Flip Clock / Windows QA (2026-10-27)

## Scope and provenance

- Local source: `D:\CoS-Test\madar-desk`, branch `main`, private LocalForge `localadmin/madar-desk`.
- Package version: `1.0.0-rc.13`. Initial source HEAD for this QA: `02da101` (fixed Persian flip clock). Harness change: `cd43a5b`. The final Git checkpoint is recorded in Git history, not inferred from EXE metadata.
- This is a disposable **QA candidate**, not a silently installed upgrade or a declaration that all Madar capabilities are production-ready.
- No real `%APPDATA%\MadarDesk` profile, Parsian database, Google account, remote GitHub repository, or existing installed application was used or modified in these GUI runs.

## Windows candidate

| Evidence | Value |
| --- | --- |
| EXE | `release/Madar-Desk-v1.0-rc13-vitrea-clock-dock-QA2-20261027.exe` |
| Length | `14,502,504` bytes |
| SHA-256 | `0975974F081E4A72469734D09C0C266D2962F0940F2E1B773C061FD9E336CCF4` |
| Runtime | Windows 10; Python 3.12.10; PyInstaller 6.22.3; pywebview / WebView2 |
| Frontend | Vite 6.4.5, 1,694 transformed modules; successful production build |
| PyInstaller | One-file/windowed build succeeded with exit code 0 |

Source snapshot: `release/Madar-Desk-v1.0-rc13-vitrea-clock-dock-QA2-20261027-source.zip`,
created through `git archive HEAD` at `d2aaeac` (tracked source only).
Its SHA-256 is `2318B60C7895CF1BE88E7E85417ABF0592681F29704F6659EABEF07CAD420F3A`.
The later publication-status correction is documentation-only and does not alter the EXE.

Build emitted non-fatal missing-hidden-import warnings for `pycparser.lextab`, `pycparser.yacctab`, and `importlib_resources.trees`. These imports were not individually exercised and warnings have not been declared harmless for all application paths.

## Visual and clock acceptance

- Persian calendar on 2026-10-27 displays **سه‌شنبه، ۵ آبان ۱۴۰۵** in isolated Windows WebView2 diagnostics.
- Fixed clock renders two large flip-style HH:MM tiles. It has no seconds, drag controls, placement selector, or clock-settings popover.
- Refresh, notifications, LAN, and Google Drive action icons moved from beside clock to the **left quickdock**. The duplicated header settings icon and profile/avatar button were removed; settings remain available from the left dock and profile from the top account capsule. Sync status remains visible in the top bar.
- Quickdock has keyboard-accessible labeled buttons and scrollable bounds for small viewports. This was confirmed with source/tests and the desktop screenshot; it is not a physical-mobile-device acceptance.
- Sample board screenshot and diagnostics for the previous dock EXE, which used the same frontend assets: `qa-evidence/rc13-vitrea-clock-dock-20261027/v1-gui-smoke-ny487066/`. A basic screenshot capture for QA2 was also attempted but failed with a Windows `Permission denied` on the temporary screenshot file. This does not invalidate the separately successful QA2 interactive screenshot and must not be hidden as a PASS.

## Automated verification

| Gate | Result | Boundaries |
| --- | --- | --- |
| Complete JavaScript suite after final dock/settings edit | **479 PASS / 0 FAIL** | Synthetic and source-driven tests, includes Vitrea Chromium synthetic fixture |
| Focused Python GUI harness tests | **32 PASS** (worker-1) | Fake window/unit contract; not a substitute for actual EXE |
| Complete Python suite after current edits | **1,492 tests; OK, 2 expected failures; exit 0** | `release/resume-python-full-after-dock-20261027.log`, elapsed 442.926 seconds; no unexpected failures |
| Production frontend build | **PASS** | `npm run build` |
| One-file QA2 EXE build | **PASS** | No installation on a second computer |
| Isolated QA2 Windows interactive smoke | **PASS** | 25 required interactive checks plus base and screenshot checks |

### QA2 actual Windows WebView2 interactive smoke

Command:

```powershell
python scripts/v1_gui_smoke.py --exe release/Madar-Desk-v1.0-rc13-vitrea-clock-dock-QA2-20261027.exe --interactive --screenshot --timeout 170 --output-dir qa-evidence/rc13-vitrea-clock-dock-QA2-20261027
```

Evidence (local QA machine only, deliberately ignored by Git):
`qa-evidence/rc13-vitrea-clock-dock-QA2-20261027/v1-gui-smoke-rbeesy87/diagnostics.json` and `screenshot.png`.

- Loopback `http://127.0.0.1:<ephemeral-port>/index.html`, React root, WebView2/pywebview bridge, Persian font, RTL, five columns and visible task cards: PASS.
- Independent accounting navigation to `/accounting.html`, overview, payments, reports, rial as source currency, and return to `/index.html`: PASS.
- Before/after snapshots of both legacy task-finance and standalone accounting state: unchanged, PASS. No accounting post action issued.
- Synthetic task creation (modal, controlled title entry, drawer) and **host persistence verified with an actual `bridge.getState()` re-read**: exactly one matching task, PASS. The check polls for at most eight seconds because UI writes are debounced.
- Native reported screenshot flag `done=false`, but the retained **1484×921 PNG, 231,638 bytes** passed complete signature/chunk CRC/zlib/scanline checks. This native callback flag discrepancy remains a diagnostic warning.
- Captured `qaBrowserErrors=[]` in this isolated scenario, not a claim that no error exists in untested routes.
- The runner used temporary APPDATA/LOCALAPPDATA and an owned Windows Job Object, only terminated its owned processes, and retained synthetic QA artifacts outside user data.

## Failures encountered and addressed

1. Three stale JavaScript tests expected clock personalization after the owner retired these controls. Tests were aligned with the new UI while calendar and authorization assertions were retained. Complete JS suite later passed.
2. Initial EXE interactive QA expected the legacy embedded `.accw-root` view, old sidebar label, and a toman-default selector. Harness now checks the independent accounting route and authoritative rial head, with fail-closed checks.
3. Navigation-based native QA could start multiple diagnostic threads on repeated `loaded` events. A scoped singleflight lock/event guard prevents races for interactive QA and bridge-readiness mode.
4. First updated interactive EXE run reached the task drawer but immediately observed no persisted task. The host save has a 320 ms debounce. The harness now polls the real host state with a fixed bound and requires exactly one saved task; the rebuilt QA2 EXE passed.

## Explicitly unverified or out of scope

- Two physical Windows machines over LAN, loss of host, offline local edits, Google Drive failover, merge/rejoin and real conflict recovery.
- Full Parsian accounting import across years, rial-vs-toman reconciliation, fiscal signing, tax or invoice-print acceptance with real records.
- Production LAN/TLS hardening, all security edge cases, backup disaster recovery, clean Windows install and mobile/low-end performance.
- Unified SQLite migration on existing operational data. Nothing in these QA runs intentionally enabled or migrated that storage. Do not infer active production SQLite merely from its source support.
- Pixel-perfect match with Vitrea across all screens, dark/light on all hardware, native screenshot callback reliability, and accessibility audit beyond the tested cases.
- The first read-only `git ls-remote` call failed authentication, but a later
  `git fetch origin main` succeeded. After verifying the exact loopback LocalForge
  origin and fast-forward ancestry, `git push origin HEAD:refs/heads/main`
  succeeded with `d675140..d2aaeac`. No external GitHub push or force-push was done.

The candidate is evidence-backed for **the isolated tested paths only**, not a full-product release sign-off.
