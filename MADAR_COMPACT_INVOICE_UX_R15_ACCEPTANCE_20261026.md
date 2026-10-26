# Madar Accounting R15 | Compact familiar invoice workspace

Date: 2026-10-26. Scope: **Sales invoice UX**, not an accounting-core rewrite.
Status: built, installed side by side, tested against synthetic accounting data.

## Intent and inspiration

Use a dense desktop workflow inspired by the accessibility of established
Iranian print/accounting tools, while preserving Madar's own visual language.
The exact screenshots at chapyar.com/home/gallary were not independently
reproduced in this run; no pixel-parity or proprietary source reuse is claimed.

## Implemented

1. Invoice list is a familiar workspace with search by invoice ID/number,
   customer and status (all/draft/approved/issued). A small summary of real
   invoice counts is present; filtering is **presentation-only**.
2. Common row commands are visible: details, PDF, edit draft, approve,
   issue and settlement when relevant. Less common formats, cancellation and
   tax preflight remain one expandable action away.
3. Invoice editor has a compact command bar with New Row, Save Draft and
   Return to List; no additional accounting page is opened.
4. Primary entry is a five-column grid: description, quantity, unit price,
   line amount and actions. Account and catalog selectors are available
   in an explicit per-row advanced expander; they are not removed from the
   stored invoice model.
5. Enter advances from description to quantity to price and then a new row.
   Existing keyboard shortcuts remain available for advanced fields.
6. Total, tax, discount and final amount remain in a sticky financial summary
   on wide displays, with a compact bottom treatment on narrower windows.
7. Initial focus goes to customer search. Moving between invoice form and list
   preserves the existing unsaved-changes confirmation.
8. Existing accounting event commands, validation, CAS revision and journal
   posting rules were not modified for these UX changes.

## Verification, executed on Windows

| Test scope | Result |
|---|---|
| Vite production build | PASS |
| Entire JS test suite | **375/375 PASS**, 0 failures |
| Focused desktop/backend/identity Python tests | **39/39 PASS** |
| Real pywebview user interaction with synthetic SQLite book | **46/46 PASS** |
| Packaged R15 EXE company/password/book/backup/restore | **13/13 PASS** |
| Installed EXE chooser cancel, no unexpected book | **6/6 PASS** |
| Installed SHA-256 equals release SHA-256 | PASS |
| Old R14 release SHA-256 preserved | PASS |

The pywebview flow created a synthetic customer, entered invoice fields,
tested Enter-to-row, confirmed live total, saved a draft to real SQLite
storage and confirmed **zero financial journal entries for a draft**.
Status filters and restoration of the full list were also tested.

Source-backed evidence:

- `tests/accounting_invoice_quick_filter.test.cjs`
- `scripts/qa_r15_final_user_gui.py`
- `.qa-r15-final-user-gui-report.json`
- `scripts/qa_r15_secure_exe_journey.py`
- `scripts/operational_mohsen_r7_company_picker_exe_qa.py`
- `.qa-r15-final-js-after-compact-20261026.txt`
- `.qa-r15-invoice-compact-refined.png` (actual local window capture)

## Independent executable

- `release/Madar-Accounting-Compact-UX-R15-20261026.exe`
- **16,798,214 bytes**
- SHA-256:
  `09C86801A9F49E812B896F9DDB74777A90CFBA698FF844C3EA822457DDD01E9E`
- Installed at
  `%LOCALAPPDATA%\Programs\Madar Accounting Mohsen R15`
- Desktop shortcut: `Madar Accounting R15 - MultiCompany.lnk`
- Private empty companies directory:
  `%LOCALAPPDATA%\Madar Accounting Companies R15`

Previous R14 binaries and prior user data were **not migrated or overwritten**.
The screenshot and synthetic customer/invoice used disposable roots only.

## Not yet accepted

- Installed R15 has not been used for a full human accounting operation with
  real financial data or a real printer.
- This is still a Windows desktop program hosted by WebView2/React;
  it is not a WinUI/WPF native-control rewrite.
- Screen-reader navigation, hundreds of editable invoice rows, real
  operator ergonomics and responsive performance need further assessment.
- Tax submission, live legal acceptance, Parsian migration, encrypted
  database backup and LAN authentication are not certified.
- No verified push to local Gitea is claimed for this candidate.

**Conclusion:** R15 is a functional compact invoice UX candidate, not a
production-certified accounting or statutory e-invoicing release.
