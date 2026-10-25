# Madar Accounting — independent workspace and vendor migration

**Date:** 2026-10-21  
**Source of requirements:** direct user correction: not a small modal and not generic financial widgets. Accounting must be an independent environment, capable of eventual full migration of prior accounting records, with direct task-to-sale and work-step-to-supplier-purchase links.

## Confirmed Parsian installation, without extracting business data

- Installed application: `C:\Program Files (x86)\Parsian\Parsian.EXE`, Windows product metadata **Parsian Accounting Software**, product version **39**.
- Existing `db_1404.bak` and `db_1405.bak` start with hex `54 41 50 45` (`TAPE`), compatible with native SQL Server backup media. Related MDF/LDF files and running SQL Server services were observed.
- **No actual table, account, person, transaction or database row was read.** No SQL Server query, backup copy, database restore, license bypass or proprietary code extraction was performed.
- `parsian_backup_probe.py` reads only 16 header bytes from a selected .bak, reports format, bytes and prerequisites; it never writes or claims to import a BAK.
- **Migration gate is OPEN:** restore a *copy* to a verified isolated SQL Server, inventory schema/relationships, determine currency/unit, convert dates and account hierarchy, build reversible staging, preview totals, reconcile opening/ending trial balance, prove idempotency on sample backups, then enable production import only after human approval.

## Actual operational implementation in current project source

1. `src/accounting_workspace.jsx/.css`: full-screen RTL accounting route, separate nav and exit back to task manager; dashboard, sales, unpriced purchases, parties, accounts/GL, settlements, reports, migration/backup. Uses real host accountingRead/accountingCommand. Sections without backend maturity have explicit warnings, not fake data. Existing settlement form is still used as transitional subflow, NOT a completed full accounting UX.
2. `src/App.jsx`: direct card action `ارسال کارت به فاکتور فروش` and per-work-step `ارسال به خرید`. Sale unit quantity and price stored explicitly in task, protected by the native validator; task title becomes line description. Route opens only after existing task data is saved.
3. `purchase_intake.py`: one named supplier per unique task-step intake, explicit quantity, **NO unit price at intake time**, idempotency receipts, strict schema and card/project scope. Later `intake.price` adds unit price, and `intake.convert` creates a *purchase draft* in `accounting_core.py`. No payable exists until the bill is independently reviewed and issued.
4. `accounting_service.py` + `finance.py`: the optional purchase intake collection lives within authoritative finance state and existing SQLite/JSON atomic host finance writes, with the supplier master record registered at intake time but no GL entries until issuance. Existing double-entry financial semantics remain authoritative, not parallel ledger posting.
5. `finance_reference_guard.py`: source card cannot be silently re-parented/deleted with active or historical document/intake references.
6. `finance_visibility.py`: non-administrator LAN projections now redact the new `saleUnitPrice` in addition to pre-existing cost fields, and restore original value on authorized ordinary editor writes.

## Additional implementation in the resumed development session

- `accounting_core.py` now replays an **event-sourced catalog of goods and services** (`item.create`, `item.update`) with SKU uniqueness, explicit units, historical line descriptions, active/inactive enforcement, and strict event hash replay. `stockTracked` is always false: this is **not** an inventory/warehouse module.
- `accounting_service.py` now supports `document.create` for a genuinely **standalone** sales invoice/purchase bill linked to a named existing party and a project, without a task reference. Source links remain in the authenticated atomic finance snapshot. Its exact retry is idempotent, conflict is rejected, and payable/receivable remain unposted until approval and issue. A line may explicitly link `itemId` to an active catalog item.
- `accounting_reporting.py` computes company-wide read-only trial balance, account statements, income statement and balance sheet from posted journals including reversal entries; the overall balance sheet and trial balance must reconcile or the report fails. `accountingRead('')` exposes the result in `reports`. **With a project filter** the API returns `reports=null` rather than misleading project-specific totals.
- `accounting_core.py` and `accounting_service.py` additionally support explicit internal `funds.transfer` between liquid bank/cash accounts and a balanced `journal.manual` with 2..100 lines, reason, strict dates and standard reversible audit trail. Manual journals cannot post directly to designated AR/AP `1200`/`2000` subledger accounts. These are INTERNAL accounting entries, not a bank API or check register.
- `tests/test_accounting_catalog_standalone.py`, `tests/test_accounting_reporting.py`, `tests/test_accounting_manual_bank.py` and `tests/test_parsian_migration_staging.py` cover synthetic data only. Last verified targeted suite: 79 tests PASS across 7 relevant modules, plus py_compile PASS. A full QA run was started during additional changes; its outcome and final snapshot must be checked independently.

## Evidence and what is NOT ready

- Test groups executed in disposable state: purchase intake 4/4, accounting bridge and service focused, LAN finance visibility 20/20 combined, React standalone workspace SSR 6/6, Vite production bundle PASS.
- Full isolated release QA was started after latest changes; report its actual exit separately, never inherit RC9's earlier QA. **No new EXE containing this architecture has been built or shipped.**
- NOT yet a full accounting product: independent item/stock catalog, inventory valuation, banking/cheques, opening journal import, taxes/legal filing, financial period workflow, statutory printing, multi-company, audited user/finance permissions and fully interactive accounting GUI acceptance all need additional work.
- Migration of full original Parsian BAK is **not implemented or validated**. No safe claim of zero financial loss exists without schema and trial-balance reconciliation.
- Important unresolved business rule before importing amounts: whether Parsian source currency unit is IRR (rial) or TOMAN. Internal Madar financial domain currently records exact integer TOMAN.

**Do not reuse the old RC9 zip as evidence of these changes, and do not overwrite existing RC candidates or open live Parsian databases in tests.**
