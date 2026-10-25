# Madar Desk | Standalone RTL Accounting Workspace

## Status / ownership

Implemented as an independent full-screen React accounting desk, not an
accounting tab in task management. This tranche owns **only these new files**:

- src/standalone_accounting_workspace.jsx
- src/standalone_accounting_workspace.css
- tests/standalone_accounting_workspace_ui.test.cjs
- STANDALONE_ACCOUNTING_UI.md

No edits to src/App.jsx, src/standalone_main.jsx, native_app.py, LAN,
accounting_core.py, finance.py, package.json, APPDATA, SQL data or Git.
No real company balances or financial records were read or changed here.

## Dedicated route and wiring

Existing entry point observed by read-only inspection:

    accounting.html
      -> src/standalone_main.jsx
      -> StandaloneAccountingWorkspace({api,onExit,canManage})

The host exposes two exact async methods on the passed API:

    await api.standaloneAccountingRead()
    // -> {revision: 0, view: accounting_view}

    await api.standaloneAccountingCommand({
      command: {type: '...', eventId: 'evt.<uuid>', ...},
      expectedRevision: 0
    })
    // -> {revision: 1, result: commandResult, view: accounting_view}

**revision is a nonnegative safe integer**, including zero. This was verified
against worker-10's standalone_accounting.py and worker-11's host contract;
strings such as "0" are rejected as the wrong API schema. The UI stores the
last acknowledged revision and never manufactures one.

Every successful command consumes the returned authoritative view and
revision; no optimistic invented balances, synthetic documents or fake receipt
numbers are presented. Read errors or invalid TOMAN schema show an explicit
error and a refresh control, not mock state.

The component never sends user actor, company, credentials, role, financial
permission, project ID, task ID or trusted proof in either API call.
The host authenticates and authorizes independently. The canManage prop only
controls which input panels appear; **it is not server authorization**.
View-only users can see the empty/read state but cannot use write forms.

### Version conflicts and uncertain responses

- New business commands receive an eventId built from the browser's secure
  crypto.randomUUID API. No weak random-number fallback is used; inability
  to generate an ID fails closed.
- The command is sent with exactly its last validated integer
  expectedRevision. Concurrent submissions are blocked.
- On explicit CAS/revision conflict, the UI calls the trusted read API again
  and displays the new revision. The user's draft is kept, never silently
  resubmitted.
- If a response is lost or the result is ambiguous, the **same original
  command including its eventId is retained**. New financial submissions
  are blocked until a read and idempotent retry of that same command.
  This prevents accidentally doubling a deposit or payment by assigning
  a new event ID after a lost acknowledgment. The host's idempotency and
  atomic storage remain the authority.
- If the host is down or does not expose these two methods, the user receives
  an explicit availability error. No local-only success is claimed.

## Features and exact accounting_core v1 commands

| Page | Read features | Command types |
| --- | --- | --- |
| Overview | Open receivables/payables, liquid balance, issued-document count, recent journals | None |
| Sales | Standalone draft, status/number, approval, issue, cancellation, settlement shortcut | invoice.create, invoice.approve, invoice.issue, invoice.cancel |
| Purchases | Independent vendor bills and their lifecycle | bill.create, bill.approve, bill.issue, bill.cancel |
| Parties | Customer/vendor/both, actual AR/AP balances | party.register |
| Catalog | Active/inactive item list, item references for bill/invoice lines | item.create |
| Receipts/payments | Recorded and reversed settlements; allocation to one explicitly selected outstanding issued invoice/bill | receipt.record, payment.record |
| Cash/bank | Real liquid accounts/balances | funds.deposit, funds.transfer |
| Accounts/ledger | Flat v1 chart, debit-minus-credit and normal balances, journal line filter | account.create |
| Journal | Recorded journal events, double-entry manual form, reversal of eligible journal | journal.manual, journal.reverse |
| Period close | Current closed-through date and explicit irreversible closing action | period.close |

Every command has the exact object key names expected by accounting_core.py.
Approve, issue and cancel are different steps, not shortcuts silently merging
them. Issue has an explicit user-selected Gregorian posting date, defaulting
to **today's local date**, subject to backend document date, closed-period
and future-date validation. Cancellation requests a
specific reason for a draft/approved document. The settlement form chooses
one issued document and creates one allocation to that document.
The engine enforces party kind, account liquidity, original document date,
cash balance timeline, no overpayment and subledger consistency.

The invoice/bill builder supports multiple explicit lines (1..1000),
positive whole quantity up to 1,000,000, exact integer TOMAN unit prices,
revenue versus expense account validation, optional active catalog item,
and explicit integer discount/tax. The UI invents no tax rate, shipping
policy, stock movement, payroll or commercial-source provenance.

The manual journal builder validates a balanced positive debit/credit tuple,
2..100 lines, maximum core amount, account existence, and explicitly blocks
AR 1200 / AP 2000 to prevent bypassing party subledgers.
The host's full accounting_core replay remains definitive.

### Currency and calendar

Canonical accounting_core v1 is TOMAN, with exact whole amounts
within 0..10^15. The UI uses BigInt validation before converting bounded
values to safe JavaScript integers; Persian and Arabic-Indic numerals and
correct thousand separators are accepted. Invalid grouping, fractions,
negative amounts and overflow fail closed. Read-only totals are formatted in
Persian digits, always labeled TOMAN.

There is **no RIAL input/display selector** in this tranche. Converting
every form, including manual journals, settlement and funds, must first
be verified end to end if such a selector is enabled. The backend still
stores TOMAN. The separate company/chart/V2 RIAL foundation does not
change this standalone v1 contract.

Dates are strict Gregorian ISO YYYY-MM-DD, with an explicit conservative UI
year floor of 1900 (to avoid silently treating common Persian-calendar
14xx input as Gregorian). The accounting core itself has a broader Gregorian
calendar range. **No Jalali-to-Gregorian converter is offered.**
Posting dates must not exceed today; prior closed periods are rejected
by the engine. The interface shows the current closedThrough date.

## Verification performed

    node --test tests/standalone_accounting_workspace_ui.test.cjs

**13 tests passed.** Tests cover:

- Full-screen RTL initial SSR, navigation and honest loading/empty states.
- Read-only permission and absence of write forms on initial SSR.
- Exact TOMAN parsing, 1900+ Gregorian dates, rejection of false dates.
- Host integer revision 0/positive and rejection of string revisions.
- Sale and purchase command payloads, discount/tax math, unsupported account
  kind, invalid catalog items and amount bounds.
- Invoice/bill settlement segregation, positive outstanding allocation,
  liquid account and posting-date checks.
- Balanced manual journal and AR/AP restriction.
- Dedicated API call signatures, CAS revision propagation, unique event ID
  source and no actor/company/project/task injection.
- **Synthetic direct replay against unchanged accounting_core.py** in an
  in-memory Python process: party register, item create, sale draft/approve/
  issue, cash deposit, receipt, purchase draft/approve/issue, payment,
  manual journal, reversal and period close. All synthetic assertions passed.

An isolated Vite production build also succeeded:

    ./node_modules/.bin/vite.cmd build --outDir <TEMP>/madar-standalone-worker9-qa --emptyOutDir

The output included accounting.html and its separate compiled accounting JS
and CSS assets. No production release directory or installed EXE was touched.

## Limitations / acceptance blockers

1. **No desktop end-to-end interaction was run.** SSR and command-builder
   tests prove only a subset of React behavior; click-through, focus,
   scrolling, WebView keyboard flow, localization and native financial
   permission handling need actual application acceptance tests.
2. User session management and canManage must be sourced from the trusted
   host or an authenticated role projection. The host must refuse unauthorized
   writes regardless of visual controls.
3. No cheque management, FIFO inventory, stock valuation, payroll, tax rates,
   e-invoicing, external Parsian import or migration UI is claimed.
   Catalog items are not stock ledger entries.
4. The existing ledger uses **flat account IDs** with default cash, bank,
   A/R and A/P. This page does not pretend to have fully integrated the
   separate Iranian KOL/MOEIN/TAFSILI chart or RIAL V2 posting.
5. To protect the exact contract, missing host routes return a failure.
   A mock view is never substituted for the actual persisted view.
6. Actual backend CAS race protection and SQL atomicity are worker-10's
   responsibility. This UI passes the expected revision and re-reads
   conflicts, but does not certify storage correctness.

The four owned files are ready for Prime's integration and QA. Neither
production data validation nor release readiness is asserted.
