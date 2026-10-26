# Madar Accounting R16 | Management Dashboard

**Date:** 2026-10-26  
**Scope:** independent accounting workspace only  
**Data boundary:** synthetic, disposable test ledgers; no Parsian or existing customer ledger used for dashboard QA.

## Delivered source changes

1. `src/accounting_management_analytics.js`: read-only management analytics with explicit ISO date range, currency matching, issued-only invoice sales, GL-based revenue/expense/net balance, monthly sales, catalog products/services and uncatalogued invoice-line descriptions, and live cheque status reminders.
2. `tests/accounting_management_analytics.test.cjs`: new synthetic financial tests, including draft exclusion, return/reversal, service lines, native RIAL/TOMAN, negative balances, malformed data and overflow.
3. `src/accounting_management_dashboard.jsx` + `.css`: RTL compact cards, current local clock and Persian date, overdue/next-seven-days operational cheques, clickable charts, drill-down table and native Jalali custom date controls.
4. `src/standalone_accounting_workspace.jsx` + `.css`: mount dashboard in existing initial `overview` tab, compact duplicated generic header, retain original historical ledger details in a disclosure.
5. `scripts/qa_r16_management_dashboard_gui.py`: native WebView test on an isolated, synthetic company.
6. `Madar-Accounting-Management-Dashboard-R16-20261026.spec`, `scripts/qa_r16_secure_exe_journey.py`, `scripts/qa_r16_packaged_direct_gui.py`, `scripts/install_mohsen_r16_candidate.ps1`: unique R16 release/build/test/install paths without reusing R15 install paths.

## Financial semantics and known limitations

- Sales means issued sales invoices, net of recorded partial returns at their original issue period; draft/approved/non-issued records do not contribute to issued sales.
- Income, expenses and their difference come from posted GL journal lines and account classification in the selected date range. **The displayed income-minus-expense balance is not certified per-product or business net profit.** The interface explicitly indicates unavailable verified cost attribution.
- Product/service rankings use actual invoice line quantities and unit sales prices, corrected for recorded returned quantities. They show **gross line sales** before discount/tax allocation, not individual item profit.
- Cheque reminders use the current independent company `view.cheques` only. `received`, `deposited`, `issued`, `endorsed`, `returned` need attention; `cleared`, `cancelled`, `reversed` do not appear. Parsian archival cheques are not automatically treated as active operational cheques.
- Money uses the book's actual `RIAL`/`TOMAN` currency with no implied conversion. Dates persist as Gregorian ISO and display in Jalali, using local device time for the clock.
- **Monthly sales series currently groups by Gregorian `YYYY-MM` posting month**, even when the selected date window is Jalali. This is a known reporting limitation, not a Persian fiscal-month report; it needs a separately tested Jalali-month grouping before being labelled as such.
- No claim of formal financial audit, tax authority communication, historical Parsian cheque reconciliation, or verified individual cost-of-goods profit.

## Verification evidence

| Verification | Actual result |
| --- | --- |
| Latest Vite production build | PASS, 1,673 transformed modules |
| Complete `node --test tests/*.test.cjs` | **388 pass, 0 fail** |
| Focused accounting backend: `test_accounting_core`, `test_accounting_extended_operations`, `test_accounting_reporting` | **42 pass, 0 fail** |
| Identity/company/ACL backend: `test_standalone_accounting_identity`, `...identity_backup`, `...company_registry`, `...finance_acl_comprehensive` | **23 pass, 0 fail** |
| Native pywebview dashboard, one synthetic RIAL company, issued invoice and live cheque | **17 pass, 0 fail** (including click, Jalali inputs, recalculated sales and no GUI ledger mutation) |
| Packaged R16 EXE with explicit disposable `--data-dir` | **8 pass, 0 fail** (window, SQLite, startup/exit backup, backup integrity, normal exit) |
| R16 secure chooser/login keyboard-driven packaged journey | **NOT VERIFIED**: chooser appeared, but foreground focus was unavailable; login injection was intentionally not attempted. Harness recorded **1 pass, 12 not passed**. This does **not** establish a login defect or login success. |
| Screenshot/complete final visual sign-off | **NOT VERIFIED**: an earlier screenshot showed the dashboard; the later screenshot was skipped because another window held focus, to prevent capturing unrelated desktop content. DOM/interaction checks did complete. |
| Full Python suite | Not run in this R16 task; above backend tests are focused only. |
| Git commit / Gitea remote push | Not performed: current project root has no `.git`; do not claim release has been synchronized to LocalForge. |

## Release identity and installation

**Release file:** `D:\CoS-Test\madar-desk\release\Madar-Accounting-Management-Dashboard-R16-20261026.exe`  
**Release SHA-256:** `BF66A108A1B3C5D58B230F158FA2D23E392C5BCA4E0520FEA34F6B09B0AC6B1D`  
**Release size:** `16,812,907` bytes  
**Installed file:** `%LOCALAPPDATA%\Programs\Madar Accounting Mohsen R16\Madar-Accounting-Management-Dashboard-R16-20261026.exe`  
**Installed SHA-256:** same as release, independently recalculated after installation.  
**R16 company registry root:** `%LOCALAPPDATA%\Madar Accounting Companies R16` (new, empty immediately after install).  
**Desktop shortcut:** `Madar Accounting R16 - MultiCompany.lnk`.  
**Start Menu:** `Programs\Madar Accounting Mohsen R16`.

**R15 preserved:** its release and installed EXE both hashed to `09C86801A9F49E812B896F9DDB74777A90CFBA698FF844C3EA822457DDD01E9E`, unchanged from the prior R15 acceptance record. The installer refused overwrite paths and created only distinct R16 program and empty company-registry folders. This is not a whole-machine filesystem audit.

## Unfinished acceptance boundaries

1. Retry the packaged multi-company secure chooser/login GUI journey when the *owned* window can obtain keyboard focus, or use independent GUI automation that does not require foreground keyboard injection.
2. Perform a final unobstructed visual inspection in R16 with the actual application window on top. An obscured screenshot is not visual proof.
3. Maintain LocalForge/Gitea migration separately after reconciling the current non-Git workspace with the staging bare repository. No GitHub action is needed.
4. Introduce Persian-calendar month buckets for monthly management reporting, with leap-year and month-boundary tests. Do not relabel Gregorian buckets as Persian without recalculating them.

**Current outcome:** new dashboard source, tests, distinct package and side-by-side installation exist. Financial real-data acceptance, secure chooser/login GUI completion and Gitea synchronization are not asserted.
