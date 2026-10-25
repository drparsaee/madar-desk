# Madar Accounting | Mohsen-style UX R9 — acceptance and remaining risks

Date: 2026-10-25. This is **a working, side-by-side Windows candidate**, not a
production-certified accounting system and not a proprietary Mohsensoft clone.

## What changed in R9

- Added invoice print-layout editor with A4/A5, portrait/landscape, margins,
  font, color, safe embedded logo, field labels, show/hide, x/y positioning,
  pointer dragging, column visibility, signature and preview.
- Custom invoice PDF uses document fields and a canvas renderer, with
  multi-page PDF and no posting of accounting events. PNG is refused when the
  invoice spans pages so rows cannot be silently omitted.
- Per-company local template library: invoice-entry rows, print layouts and
  distinct **print-only** issuer profiles. Create, edit, list/select, copy,
  set default and delete. Entry-template JSON export/import from R8 retained.
- Issuer printing is separated from accounting company/ledger identity.
  A user-defined issuer affects only printable fields, never journals.
- Sidecar template library has atomic publishing and a previous-version copy.
  The five-minute/on-exit financial backup now saves a corresponding JSON
  template companion where templates exist. SQLite restore is separate:
  **automatic restoration of template companion is not integrated into the
  offline restore wizard**. Preserve the companion when restoring a backup.
- Invoice-entry keyboard commands: Enter advances to the next cell,
  Tab/Shift+Tab remain native, Ctrl+Insert adds a row, Alt+Shift+D duplicates,
  Ctrl+Delete removes a row. Added per-row copy and delete buttons.
- Added actual XLSX (OOXML ZIP with typed numbers) and Unicode RTF invoice
  exports. No currency-unit conversion is performed. Values and subtotals
  are checked before export; untrusted formula-like text is made inert.

## Objective evidence run on the user's Windows computer

| Test | Result |
| --- | --- |
| `npm run build` after code changes | PASS, Vite 6.4.4 |
| `node --test tests/*.test.cjs` final run | 372 PASS / 0 FAIL |
| Five relevant Python test modules, including two-company E2E | 43 PASS / 0 FAIL |
| R9 `pywebview` synthetic company, browser DOM and file-template flows | 33 PASS / 0 FAIL |
| R9 packaged EXE startup, verified automatic backups, exit | 7 PASS / 0 FAIL |
| Installed R9 EXE chooser cancellation and no unwanted ledger | 6 PASS / 0 FAIL |
| Installed R9 SHA-256 equals release SHA-256 | PASS |
| R8 release SHA-256 equals earlier recorded R8 hash | PASS |
| R5 standalone database file exists | PASS (read-only existence check only) |

### Core evidence

`scripts/operational_mohsen_r9_gui_qa.py` ran an actual Windows pywebview
instance with an isolated synthetic company. The result is in
`.qa-mohsen-r9-ribbon-verified-20261025/report.json`.
This tests live DOM behavior including saving all three template types,
and confirms that storing templates did not increment ledger revision or
create a journal entry.

`tests/test_mohsen_r9_company_e2e.py` issued a real synthetic invoice in
company A, checked independent empty company B, verified backup replay,
restored company A to a new offline test folder and checked that A's invoice
did not appear in B. Template and issuer stores were separate as well.

`tests/accounting_structured_invoice_export.test.cjs` independently opens
generated XLSX contents with Python zipfile/ElementTree. Real Excel/Word
desktop opening, printer behavior and screenshots of those apps were **not**
tested and are not claimed.

## Build and installation

- Release: `release/Madar-Accounting-Mohsen-UX-R9-20261025.exe`
- Size: **16,725,990 bytes**.
- SHA-256: `BEA2AB8688E6D87A8F072769BB73DD226717F2116FC63FD3DABA3A10F0B737FF`.
- Installed: `%LOCALAPPDATA%\Programs\Madar Accounting Mohsen R9`.
- Fresh company hub: `%LOCALAPPDATA%\Madar Accounting Companies R9`.
- Desktop shortcut: `Madar Accounting R9 - MultiCompany.lnk`.
- Start Menu shortcut with equivalent name under `Madar Accounting Mohsen R9`.
- Install was separate, with no migration or overwriting of R5/R6/R7/R8.
- Company hub was empty immediately after installation, verified on disk.

## Explicitly not accepted or not yet finished

1. The interface remains a **desktop-hosted React/WebView2 UI** with Windows
   ribbon styling, not a full WinUI/WPF native-controls rewrite.
2. Full, live REA native-UI reverse engineering of Mohsensoft was unavailable
   on the Windows provider; R8's static resource/help analysis remains the
   evidence and no proprietary code was reused.
3. No physical printer test; no desktop Excel/Word acceptance; no visually
   certified identical FastReport/Mohsensoft reproduction.
4. An editor exists, but unrestricted component placement, column widths,
   printed bank details, and full WYSIWYG designer parity are not established.
5. Switching independent companies **without closing the current session**
   is not present; selecting at launch remains supported. Installed EXE
   creation flow with live clicks has not been exhaustively tested.
6. Catalog autocomplete/default sale prices, very large interactive invoice
   performance and on-device printer settings need further work.
7. Company templates have backup companions, but the dedicated offline
   restore wizard currently restores only the financial SQLite book.
8. No Parsian v39 live migration, no real financial input, no professional
   accountant or legal/tax acceptance, no second Windows device/LAN test.
9. No new changes were made to the R5 test invoice `PS1405-INV68-TEST`.
   Earlier recorded R5 values remain the historical baseline, not a newly
   re-evaluated financial result in this run.

Status: **R9 candidate installed and synthetic-tested; financial production
sign-off is intentionally withheld**.
