# Madar Accounting R14 | Familiar invoice navigation UX

**Date:** 2026-10-26. **Scope:** standalone Windows accounting invoice interface.
**Status:** source implemented; tested with a real pywebview and disposable ledger;
R14 EXE built and installed separately. Not production-certified.

## User-reported defect

The R13 invoice page mixed the invoice list, large edit form, print settings,
templates and advanced tools. Invoice creation did not have an obvious way
back to the familiar invoice list, creating a disorienting workflow.

## Changes made

1. Every non-home section has a visible **Back to Home** command in the top ribbon.
2. Invoice creation/editing has an explicit **Back to Invoice List** button in
   the top ribbon, contextual breadcrumb and form footer.
3. The invoice list and invoice form are mutually exclusive during invoice editing.
   One clear **New Invoice** button opens the entry form; a saved draft returns
   to the invoice list.
4. Abandoning an invoice with edited data requires explicit confirmation.
   Rejecting the confirmation keeps every current form value, with no new
   financial command. Back from an untouched form does not require confirmation.
5. Opening a new invoice automatically suggests an existing-year-safe ID
   (for example `INV-1405-0001`) without creating a financial record.
6. Primary fields and line entry remain visible. Tax/discount/due-date options,
   catalog tools, keyboard shortcut reference, templates, print layout and
   issuer designer move into clearly labeled expandable panels.
7. The editor description now shows three familiar actions: select customer,
   enter lines and save a draft. User-facing labels avoid technical terms
   where possible.
8. Existing accounting commands, CAS, roles, tax fields and ledger rules
   are unchanged; editing, corrections and advanced options remain available.

## Verification

- `npm run build`: **success**, with no JSX warnings at final build.
- `node --test tests/*.test.cjs`: **372/372 pass**, 0 failures.
- `py -3.12 scripts/qa_r14_invoice_navigation_smoke.py`: real pywebview,
  **25/25 PASS** on synthetic temporary data.
- GUI walk covered entering the invoice list, starting a new invoice,
  suggested invoice number, initially collapsed advanced tools, unsaved-change
  confirmation both rejected and accepted, return to list, reopen, set customer,
  line description, quantity and unit price, update live total, submit draft,
  return to list, and persistence in actual SQLite with **zero journal postings**.
- Installed R14 chooser cancel test: **6/6 pass** with clean process exit and
  no unexpected company or ledger creation.
- Installed R14 EXE SHA-256 equals release; R13 EXE SHA unchanged.

## Release and isolation

- `release/Madar-Accounting-Invoice-UX-R14-20261026.exe`
- **16,796,420 bytes**
- SHA-256:
  `24EE0A7F817B9405BE564A9D362C4613ABB39297E616582BBFF5E0BC91963FCB`
- Installed:
  `%LOCALAPPDATA%\Programs\Madar Accounting Mohsen R14\`
- Desktop:
  `Madar Accounting R14 - MultiCompany.lnk`
- Independent company root:
  `%LOCALAPPDATA%\Madar Accounting Companies R14\`

No R13, Parsian or real accounting database was overwritten or migrated.
R14 starts with a **new, empty** company hub. Existing R13 companies
are deliberately not auto-migrated.

## Limits

- The 25 GUI checks exercised synthetic pywebview with the freshly built
  frontend and a real standalone SQLite backend. They were not all repeated
  from inside the installed frozen R14 EXE.
- The frozen EXE was tested for installation, hash and chooser cancellation,
  not a complete multi-user financial acceptance.
- Broader UX testing with genuine nontechnical users, accessible keyboard
  navigation, physical printing, old-company migration, production legal and
  finance acceptance remain open tasks.
