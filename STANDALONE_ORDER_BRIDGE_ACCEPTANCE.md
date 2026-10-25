# Madar Desk: independent accounting and order handoff

Scope: synthetic-source development review, 2026-10-22. This is **not** an
EXE-release certificate or an audit of real accounting data.

## Architecture and implemented paths

- Accounting UI `accounting.html` and standalone SQLite/event log remain
  independent of task execution. No task DB is written by the accounting store.
- A saved task supplies customer/accounting party ID, sale title, quantity,
  unit price and explicit currency. Operational details (`task.description`)
  are not copied into invoice events.
- An order stage can hold multiple independent expense items (including
  distinct vendors and `unitPrice: null`). The independent contractor queue
  supports intake, pricing, quantity confirmation, and single-vendor batch
  bill draft. No AP/GL is posted before official bill issue.
- Only authenticated administrator task handoff is supported. The UI sends
  `{taskId, expenseId}`; host reloads authoritative saved task data, validates
  registered parties, and commits to standalone SQLite using revision CAS.
  Source IDs prevent duplicate commercial documents on retry/double click.
- Read/edit protections redact financial metadata from non-admin task state
  including raw LAN response, and deny employee attempts to change it.
- `standaloneAccountingQuote` is a read-only, host-calculated total, using the
  existing accounting line-validation engine. No financial posting. Currency
  shown is original TOMAN/RIAL; RIAL with non-multiple-of-10 unit price
  fails closed because the independent storage is TOMAN integer.
- Ordinary invoice/bill drafts may be edited with an audit event, and the
  independent UI exposes browser-local raster PDF or PNG export. Filename
  template is configurable and sanitized; it is provisional, not a customer-
  approved filename convention.

## Specific fixes in this continuation

- Made `/api/standalone-accounting/prepare` routable through the authenticated
  LAN endpoint allowlist; an existing handler had been unreachable (404).
- Added authenticated `/api/standalone-accounting/quote` plus exact quote UI,
  including safe decimal strings for potentially large original RIAL totals.
- Added negative HTTP security checks for unauthenticated/editor calls and
  forged quote amounts, synthetic concurrent preparation and business-source
  idempotency tests.
- Bounded order customer display name, hardened PDF/PNG filenames against
  reserved Windows names, and removed a duplicated projection key.
- Updated a legacy JavaScript entry test after removing the obsolete card-
  accounting menu entry; it now checks that the independent route is used.

## Verification evidence

- Targeted 41 Python tests and 18 JS tests passed; production Vite build
  succeeded. Two more LAN HTTP tests + four exact-quote tests passed (6/6).
- All 337 JavaScript tests passed separately (`.qa-independent-order-js-20261022.log`).
- A separate eight-thread sale and eight-thread unpriced-contractor test
  passed: one persisted source per operation and no premature journal.
- First full QA attempt: 1264 Python tests, **one error** in a Python
  source-inspection startup-restore test. The specific test passed when
  run again by itself. The complete subsequent regression **passed** with
  **1272 Python tests and 337 JavaScript tests**, exit code 0, from
  `.qa-independent-order-recheck-20261022.log`. The quote HTTP and
  eight-thread idempotency tests were also exercised separately. This is
  automated-source QA only, not a substitute for manual desktop/release QA.

## Unfinished / unverified

- The ledger remains integer TOMAN; complete independent RIAL V2,
  multi-company, cheque and warehouse integrations are **not** claimed.
- Issued documents are immutable; a complete end-user issued invoice
  amendment / credit note / replacement policy still needs definition and
  implementation. Editing a draft is not equivalent.
- PNG export currently allows one page; PDF is raster and not searchable;
  long textual line descriptions can be rejected by renderer. Browser save
  behavior and physical prints were not acceptance-tested.
- An independent `Madar-Standalone-Accounting-20261022.exe` bundle was produced
  by the standalone PyInstaller command with exit code 0 and exists under
  `release/` (13,395,221 bytes at inspection). **It has not been launched or
  smoke-tested**, and is not a deployed/installed release. Real customer data,
  APPDATA, physical LAN and production were not opened or mutated in this
  continuation.

Re-run important checks without any real data using the repository commands:

```powershell
py -3.12 -B -m unittest tests.test_standalone_task_prepare tests.test_standalone_contractor_flow tests.test_standalone_accounting_quote tests.test_lan -q
node --test tests/*.test.cjs
npm run build
```
