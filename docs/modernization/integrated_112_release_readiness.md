# Madar Desk 1.0.12 — integrated accounting, usability and update settings

**Source baseline:** LocalForge 1.0.11 at `5f1c2a9225f6cdbf31b003ca7034b93c9ae2fd89`.

**Mode:** single cumulative next release for Task Manager and the independent Accounting desktop.
**Safety:** code and tests in an isolated worktree. No real users' SQLite, Parsian backups, installed 1.0.11 binaries, or production LAN services are used for acceptance.

## Implemented integration

- **FIN-01:** period profit-and-loss excludes year-close transfer entries while retaining those entries in the GL. Host reports expose a separate reconciliation between operational turnover and post-close GL. The UI labels operational income/expenses and warns against interpreting net as certified profit.
- **FIN-03:** explicit administrator-approved fixed UTC offset for company accounting posting dates (`postingUtcOffsetMinutes` + `postingCalendarMode='fixed-offset-no-dst'`). Trusted native host sends `postingToday` after applying the backend's own calendar rule; the UI uses that date for defaults and date bounds, without replacing dates already edited by the user. Existing profiles lacking an explicit setting retain the earlier UTC rule. **IANA named timezones and DST transitions are not implemented**, and the UI labels this limitation.
- **FIN-04:** read-only warnings for a goods invoice missing its separate inventory issue/COGS posting. The report explicitly states profit is unconfirmed, and identifies incomplete document/item quantities. The workflow still requires the existing explicit inventory posting.
- **FIN-02:** missing receipt/valuation on a taxed or discounted purchase is surfaced as a warning, but **not automatically valued**. Genuine cost allocation and tax policy must be approved before the block on `inventory.receive` can be relaxed.
- **FIN-05:** input-tax classification remains a policy-dependent decision and is **not automatically reclassified** from expenses into creditable input-tax assets. No fictitious recoverability calculation is introduced.
- **FIN-06:** tax invoice preflight rejects NaN, Infinity, fractional, zero, unsafe or oversized numeric inputs. This preflight remains non-submitting and not a verified Iranian tax integration.
- **UX-01/02:** invoice-field label contrast corrected on light surfaces in dark theme; a horizontally scrollable cash-flow table is keyboard focusable and labelled.
- **UX-03/04:** shortcut actions for common accounting tasks and distinct current-ledger issued unsettled AR/AP, overdue counts, and invalid-state warnings. Historical migrated balances and cash flows stay distinct.
- **UX-05:** compact invoice editor navigation on narrow screens, without removing draft/approval/issuance boundaries or changing the financial command contract.
- **Task Manager theme:** two explicit settings controls: *my personal local theme* and *shared default for users*. A change from the left quickdock updates the personal setting; viewer can change their own preference but not the shared default.
- **Both settings:** explicit check for new release, download verified installer and confirm scheduling install after exit. The renderer cannot select arbitrary URL/file/hash. The native update source remains the official public release metadata and SHA256 validation. Merely pushing LocalForge code does not make a public update available.
- **Packaged-accounting verification:** the accounting HTML inside the integrated `native_app.py` executable uses a restricted JavaScript bridge, not the standalone script bridge. The final source explicitly exposes only the three trusted update operations on this accounting surface and provides the company posting day on Solo/Server/remote LAN finance responses. This regression is covered by `test_packaged_accounting_update_v112.py`; the initial build *without this fix* was withheld and rebuilt from a distinct immutable source/worktree.
- **Upgrade:** cumulative 1.0.12 full installer source, preserving existing profile data; historical versioned builders and frozen release files are not overwritten.

## Known limits and release gates

1. **No unconditional signoff for formal accounting use.** FIN-02 and FIN-05 need explicit business/tax policy, and FIN-04 still requires an operator to post the actual inventory movement; the UI displays that fact.
2. The new company UTC offset is *fixed*, not daylight-saving-aware. Choose it only for a company that can use a constant offset; do not infer a timezone from the Windows locale.
3. Complete cumulative acceptance must use disposable profiles with verified snapshot and unchanged finance data, and inspect the built packaged desktop. Headless Chromium + mocked native calls is **not** the same as EXE/WebView2 acceptance.
4. The actual running 1.0.11 application must be closed normally before replacing it. No forced termination or production-data testing.
5. This scope contains only the **one described** small Task Manager defect: appearance toggle discrepancy. The user's other small defect was not described and has not been guessed at or fixed.
6. A local Git commit/tag is **not** a GitHub Updates release. An actual in-app update requires a later verified, publicly accessible tagged release asset.

## Observed integrated QA as of 2026-11-03

- Full JavaScript suite with serial browser scheduling: **606 tests, 606 passed, 0 failed**. An earlier oversubscribed parallel run caused browser-navigation timeouts; the serial rerun did not reproduce them.
- Initial full Python suite: **195 modules executed, 194 passed, 1 failed**, with 1,772 tests reported. The only failing module was `test_madar_update.py`, whose historic version expectation needed updating to the new `CURRENT_VERSION=1.0.12`. After correction, the complete run reached **195/195 passed** and **1,773 tests reported**, with 2 skips and 2 expected failures. Three new packaged-bridge tests passed afterward; a final complete suite including those tests remains the source-freeze gate.
- Three isolated Chromium demonstrations passed: accounting updater **9 checks**, Task Manager independent theme **7 checks**, and real-core synthetic P&L/stock warning **8 checks**. None installed or posted real financial data.
- Compiled **final** isolated 1.0.12 PE after packaged-bridge fix: `Madar-Desk-v1.0.12-Cumulative-20261103.exe`, SHA256 `b1f782abd45221a652aeb6e9fe5ce00ddbe1eebbdf18676c2861534a5c889e5a`.
- Compiled **final** installer: `Madar-Desk-1.0.12-Setup.exe`, **231,546,378 bytes**, SHA256 `39611ee432eef05cf7bbf882220c88d1e45d5a50c7704407d79e48b3a3d4a6a9`. Manifest SHA256 and exact sizes independently matched final files in the clean isolated release worktree. **Do not distribute the previous withheld 1.0.12 test candidate**, which had different digests.
- Actual packaged-EXE read-only WebView2/pywebview smoke **passed** on the **final** binary, with disposable `APPDATA`/`LOCALAPPDATA`: navigation to `/accounting.html`, native accounting read and command bridge availability, successful native read, and return to `/index.html`. Only this test's own synthetic EXE process was closed afterward. Evidence: `docs/modernization/evidence/integrated_112/packaged-native-bridge.json`. It did not exercise real accounting mutations or an update install.
- **Installer QA blocked, not passed**: the **previous withheld candidate's** actual Inno QA installer exited **7** after its process preflight detected an open Madar Desk 1.0.11 session. All **5** synthetic profile files and their original SQLite value (**515,200,000 RIAL**) remained intact, the old synthetic 1.0.11 executable and pointer were preserved, and no 1.0.12 QA executable was activated. Evidence: `docs/modernization/evidence/integrated_112/qa-installer-preflight-blocked.json`. The final rebuilt installer has **not** been installed or QA-installed; that acceptance gate remains open while 1.0.11 is running.
- The user still has 1.0.11 Madar Desk processes running. These have **not** been forcibly closed. No claim is made that 1.0.12 has been installed or released publicly.

## Reproduction

- Financial contract: `python -B -m unittest tests.test_accounting_core tests.test_accounting_reporting tests.test_accounting_company_posting_offset tests.test_standalone_accounting_tax_advisor tests.test_accounting_dual_updates -q`
- Theme and Settings SSR: `node --test tests/accounting_dual_settings_v112.test.cjs`
- Actual synthetic finance browser: `node scripts/qa_financial_report_integrated_v112.cjs`
- Actual synthetic accounting update browser: `node scripts/qa_accounting_update_settings_20261103.cjs`
- Task theme browser: `node scripts/qa_task_settings_theme_v112.cjs`
- New cumulative release safety: `python -B -m unittest tests.test_cumulative_112_update -q`
- Build: `npm run build`, then immutable `python -B scripts/build_integrated_v112.py --webview2 <Microsoft-signed-local-prerequisite>`.
- Packaged-accounting bridge: `python -B -m unittest tests.test_packaged_accounting_update_v112 -v`

Evidence is limited to commands actually executed; no source approval or deployment assertion is implied by the existence of this file.
