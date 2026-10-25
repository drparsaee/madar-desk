# Madar Desk | Beta User Acceptance Scenarios

**Verification:** 2026-10-21, Windows host / Python 3.12.  
**Scope:** New `tests/test_user_acceptance_workflows.py` only. All code under
`native_app.py`, `finance.py`, `accounting_service.py`, React, release and
persisted user APPDATA remains unchanged by this tranche.

## What was actually tested

Tests use a fresh `tempfile.TemporaryDirectory` per case and patch
`native_app.datadir` **before instantiating** a real `Bridge`. Each case
activates its **own** `enableUnifiedStorage()` SQLite database; the optional
fifth automation domain is independently exercised. Reads and writes cross
the actual Bridge business boundary, the real `accounting_service` reducers,
the authoritative `finance` domain and the `UnifiedAppStorage` CAS revision.
No production credentials, user directory, live network listener, Drive,
APPDATA or release are accessed. LAN identity tests instantiate the real
`LanService` but call service methods **in-process**, without `start()`.

### Automated acceptance matrix

| ID | User story & steps | Expected result | Result |
| --- | --- | --- | --- |
| UA-01 | Choose a real existing task, enter a **named individual**, 2 sales lines/quantity, explicit discount/tax/advance; save Draft, Review, Issue; record partial receipt | Customer name/source card retained; Draft initially does not post; issued AR = 2,850 tomans, after 1,000 receipt AR = 1,850; bank = 1,000; advance is not fabricated as cash | **PASS** |
| UA-02 | Record actual direct cost through `financeCommand(cost.set)`, draft supplier expense bill from `direct`, Review, Issue | Supplier identified by ID/name; purchase bill = 450 tomans; accounts payable = 450; no payment implicit | **PASS** |
| UA-03 | Attempt supplier payment with insufficient funds; then explicitly fund bank and pay 200 | Insufficient-funds command raises without any persisted revision or domain mutation; 1,000 fund deposit minus 200 leaves bank 800 and AP 250 | **PASS** |
| UA-04 | Issue sales + purchase, record receipt, then construct a **new Bridge** against the same activated DB | Invoice and bill statuses, financial source links, GL normal balances and SQLite checksum preserved | **PASS** |
| UA-05 | Take SQLite backup after issuing documents, then record a receipt and edit a task, then restore original backup | Both task snapshot and financial snapshot return to saved state; no orphan collaboration/outbox changes; restore is a **new** revision, includes safety pre-restore backup | **PASS** |
| UA-06 | With five-domain automation explicitly enabled, backup and restore after an additional receipt | Accounting and automation journal restored together, consistent verified SQLite | **PASS** |
| UA-07 | Reuse an already billed expense source with a *new* event ID; reuse an existing sales event ID with tampered content | Both rejected; no partial SQLite commit | **PASS** |
| UA-08 | Cancel unissued sales draft, create corrected draft for same task, issue replacement | Cancelled document remains visible in history; corrected draft posts once, no double AR | **PASS** |
| UA-09 | Issue a sales invoice, then try to invoice same task again under another event ID | Second issue path blocked before new draft; AR and finance revision unchanged | **PASS** |
| UA-10 | Create in-memory LAN admin/editor/viewer/scoped editor accounts, authenticate sessions and request accounting read/write through `LanService` | Only admin can read/post GL; revoked/unknown session rejected; editor, viewer and unrelated project denied; no socket opened and rejected calls do not mutate SQLite | **PASS** |
| UA-11 | Read accounting from a specific project view | Documents filtered to requested project; balance scope explicitly identifies **all-projects** for trial balance and party totals | **PASS** |

UA-02 and UA-03 run together in one test; UA-07 also checks two independent
rejection types. **10 tests / 10 passed**.

### Reproduction

```powershell
cd D:\CoS-Test\madar-desk
py -3.12 -m unittest discover -s tests -p test_user_acceptance_workflows.py -v
```

Last observed run: **10 tests, 10 PASS, approximately 6.1 seconds**.
Tests use the active host's current UTC date for posting dates to avoid
future-date false failures, but **do not patch the system clock**. Exact
assertions cover named customer/vendor, document state, task reference,
debit-credit projection, cash vs declared advance, absence of side effects on
failed writes, durable restart and backup/restore.

## Verified product limitations and user-facing gaps

These are evidence-based limits, **not failed assertions**:

**G-01: Backup is partial; full recovery needs more than the SQLite file.**
`Bridge.createLocalBackup()` itself returns
`complete=False`, `scope='sqlite-domains-only'` and an `omitted` list
containing **attachment binaries, LAN accounts, login credentials and
Planner local storage**. The test verifies these flags and confirms restoring
the SQL domains, not those external resources.

*Impact:* A user could misunderstand “backup” as complete disaster recovery
and lose attachments or account setup. **Beta action P0:** show an explicit
partial-backup warning in UI; provide and test a separate complete export/
restore path before representing this as a full backup. For beta, use a
disposable test workspace and preserve a separately verified full copy.

**G-02: Project-filtered accounting reports are not project-only balances.**
`accountingRead(projectId)` filters the returned `documents`, but the
`trialBalance` includes all projects and the party `balances` are global
totals for the involved parties. The response correctly labels
`trialBalanceScope='all-projects'` and
`partyBalancesScope='all-projects'`. This was asserted on a foreign project
view. The data shape should never be presented as a project P&L or project
cash statement.

*Impact:* A user may treat company-wide balances as project amounts.
**Beta action P0:** ensure the actual accounting UI prominently renders
the scope labels; alternatively build audited project-ledger attribution
before advertising per-project GL totals.

**G-03: Advance declared on the sales draft is not a payment transaction.**
The task-derived draft carries `advance=300`, but after issue it does not
increase the bank account or settle receivables without a separate explicit
`receipt.record`. The test confirms no artificial cash arises. This is
financially sound, but the UI may need to instruct testers to record the
real transfer separately rather than interpreting the “advance” field
as already collected money.

*Impact:* Confusion between agreed advance and received cash. **Beta action
P1:** label it “agreed advance, not yet received” and expose a receipt action.

**G-04: No real LAN transport or GUI smoke tests in this tranche.**
Tests exercise the real `LanService.accounting_command/accounting_read`
with real authentication tokens and authoritative user roles, but deliberately
do not bind a TCP port, test TLS/fingerprints, multi-device sync, browser
sessions, React forms, keyboard navigation, fonts or the executable installer.

*Impact:* 10 green tests **do not certify** a distributable beta installer or
LAN-network acceptance. **Beta action P0:** isolated two-client LAN test,
GUI task→invoice→bill clicks, permission-error presentation and packaged
EXE startup on clean Windows machine.

**G-05: Exact stored amounts are integer whole tomans.**
The GL deliberately rejects silent decimal rounding, foreign currencies
and invented tax rates. Tax and discounts are explicitly supplied by
the operator. No jurisdictional invoice compliance was tested.

*Impact:* A demo user might expect automatic VAT, exchange-rate handling
or legally compliant printable forms. **Beta action P1:** declare the
accounting scope clearly; do not promise statutory invoice/tax compliance.

**G-06: Restoration rolls back transactions intentionally.**
When a backup is restored, receipts created *after* the backup are absent
from the restored SQL history. The test verifies that behavior. This is
correct snapshot restore semantics, not recovery of later transactions.

*Impact:* In user tests, restoring without an operator review can lose
subsequent test data. **Beta action P0:** show backup timestamp, original
revision and confirmation; keep the automatically created pre-restore
snapshot and document safe roll-forward/recovery.

### Failed scenarios and blockers

**No assertion failures remained in the 10 focused acceptance tests.**
This must not be interpreted as absence of defects in untested UI/LAN
transport/installer scenarios. No real user identities, costs, attached
files or live finance records were used.

## Manual UAT checklist for the beta tester

In a **synthetic workspace**, the tester should:

1. Open a task. Create a named customer's sales draft with an explicit
   line, review it, issue it, record a **realistic** partial receipt and
   verify balance labels and issued document number.
2. Add an estimated expense and actual expense to the task. Create a
   supplier purchase draft from **actual** costs. Confirm the purchase
   appears first as draft, then as payable only after review/issue.
3. Attempt a payment exceeding available cash and verify a visible error,
   no silent credit balance change, and no accidental payment event.
4. Deposit an explicitly documented test amount, pay the supplier partially,
   and inspect debit/credit totals and remaining payable.
5. Cancel an unissued invoice draft, correct it and reissue it; verify
   the cancelled version remains in the history and cannot be counted twice.
6. Save a **partial** SQLite backup, make a reversible synthetic change,
   restore it, close and reopen the app, and confirm both task state and
   finance state match the recorded restore point.
7. Login separately as admin, editor and viewer on isolated test machines.
   Confirm a non-admin cannot access accounting or issue bills/invoices and
   cannot discover another project's tasks.
8. Run the same workflow with the automation engine activated; verify no
   duplicate invoices, comments or transfers arise on replay/restart.
9. Inspect UI labels for `TOMAN`, company-wide trial balance, global party
   balances, backup omissions and explicit cash receipts.

Record user, build commit/version, exact click path, expected vs actual,
screen recording or screenshot if consented, and a **redacted** copy of
the relevant error. Do not include customer PII or secrets in QA fixtures.

## Prime handoff: candidate fixes and release gate

No source fix was authorized in this tranche and none was applied.
Recommended prior to handing off a public or external beta:

- **P0:** backup completeness wording and recovery path (G-01, G-06);
  verify UI displays actual scope flags from `accountingRead` (G-02).
- **P0:** actual packaged Windows EXE GUI smoke tests and LAN loopback/
  cross-device tests (G-04), including admin/editor/viewer errors.
- **P1:** clarify that an entered advance is not a receipt (G-03);
  document integer-toman and tax scope (G-05).

The installed feature boundary covered by these tests is
`Bridge.accountingCommand/Read`, `Bridge.financeCommand`,
`Bridge.enableUnifiedStorage`, `Bridge.createLocalBackup/
restoreLocalBackup`, and in-process `LanService.accounting_read/
accounting_command`. All are real entrypoints, not stand-in reducers.

**Acceptance decision from this tranche:** finance flows, role enforcement
and tested SQLite persistence/recovery are **candidate-ready for controlled,
synthetic in-house user testing**. Overall application/executable beta
readiness requires the UI, real LAN transport and complete backup gates above.
