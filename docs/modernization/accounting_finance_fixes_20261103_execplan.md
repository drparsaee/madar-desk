# Accounting finance fixes: isolated implementation plan (2026-11-03)

## Purpose and source

Owner requested the audited FIN-01..06 accounting defects addressed as part of one eventual integrated finance and UX release. This worker owns only Python accounting modules, their tests and this evidence set. Starting canonical LocalForge main: `5f1c2a9225f6cdbf31b003ca7034b93c9ae2fd89`. Isolated worktree: `D:\CoS-Test\madar-finance-integrated-20261103` on `fix/madar-finance-integrated-20261103`. Source contract: [`accounting_financial_audit_20261103.md`](accounting_financial_audit_20261103.md). No real user accounts, databases, installed EXEs, production Parsian data, host or main changes.

## Existing behavior and decisions

- `accounting_reporting.py` reported the period net of *all* income/expense journals, including the balancing fiscal close. The management analytics JS already excluded close transfers. Keep the trial balance and closing journal immutable, while reporting the operational P&L separately from the after-close movements.
- `accounting_core.py` compared `postingDate` with `now[:10]`; desktop hosts pass trusted UTC clock values and frontend documents use local calendar dates. Add explicit **administrator-controlled fixed UTC offset minutes** to `company.profile.set`, requiring `postingCalendarMode="fixed-offset-no-dst"` when enabled. Unsupported named timezone/DST policies fail closed. Legacy profiles without the setting continue their historic behavior for event-chain replay; event `at` remains the original trusted timestamp. UI exposing company policy and aligning `standaloneToday()` is part of integrated release acceptance.
- Tax advisor accepted `float('nan')` and infinity. The accounting document core requires exact whole-unit integer quantities (up to `1_000_000`) and integer monetary amounts (up to `10**15`); enforce those same bounds during non-submitting preflight.
- `inventory.receive` cannot value taxed/discounted purchase stock without an explicit allocation policy. Inventing an allocation or assuming all tax is recoverable would be unsafe. `inventory.issue` remains a separate event after invoice issue; report an explicit current-state warning when tracked stock/COGS is pending, without falsely certifying profit.

## Execution plan and progress

1. **VERIFIED** Baseline characterization on unchanged canonical source: `python -m unittest tests.test_accounting_reporting tests.test_accounting_extended_operations tests.test_standalone_accounting_tax_advisor` produced **19 tests, OK**.
2. **IMPLEMENTED** Define operational and post-closing P&L side by side; retain existing report key shapes and all journals.
3. **IMPLEMENTED** Define company fixed posting offset, protect old event replay; use company day for document expiry/conversion, postings, finance period/year close and payroll date.
4. **IMPLEMENTED** Reject non-integer, non-finite, negative, zero, excessive and overflowing e-invoice amounts.
5. **IMPLEMENTED** Add conservative live stock/COGS and receipt warnings to the verified financial report. Date-scoped reports explicitly say historical inventory-tracking completeness is **not assessed**.
6. **VERIFIED (source suites)** Final focused run: 99 tests, OK (2 expected failures); general accounting discovery: 130 tests OK; standalone accounting discovery: 191 tests, OK (2 expected failures). These counts are separate suites with overlap. Tests used synthetic data and disposable APPDATA/LOCALAPPDATA where relevant. Worker commit SHA is supplied in the handoff; integration agent owns cherry-pick and combined release checks.

## Invariants and boundaries

Event payload hashes, sequence, reversal links, monetary rial/toman units, double-entry totals, source identifiers, ACL and SQLite CAS behavior must not change implicitly. A new company offset is opt-in, bounded to a quarter-hour increment from UTC-12:00 to UTC+14:00, and administrator-only through the existing company profile command; it requires explicit no-DST policy acknowledgment. The clock itself remains a trusted timestamp with timezone. The current stock warnings assess only available tracked catalog lines; they **never** certify all costs, tax treatment, historical inventory state, or a legally compliant profit figure. Financial posting for taxed/discounted purchases stays blocked pending explicit policy.

## Validation, risk and acceptance

Before/after comparison uses synthetic ledgers with fiscal close, invoice + stock issue, taxed bills, exact currency limits and timestamps on both sides of a company's local midnight. See [`_validation.md`](accounting_finance_fixes_20261103_validation.md). No actual installed WebView2/EXE, company-offset frontend calendar alignment, customer accounting, statutory source pack or production database is tested in this worker branch. Integration acceptance must cover a matching frontend company day, explicit no-DST warning, company offset control in settings and visible stock/COGS warnings before claiming those user-facing findings fully resolved.
