# Madar Desk 1.0.11 — Financial Audit Findings (2026-11-03)

**Status:** Needs revision before relying on full accounting reports. **Baseline:** LocalForge `main` `53dcd69056ef611a810d08491b6c2fa6329e54e7`, release `v1.0.11`. Audit only; no finance code, production database, or installed application changed during this assessment.

## Test scope and provenance

- Executed 168 relevant Python tests and 76 relevant Node.js tests successfully in focused suites. These passing suites do not establish exhaustive application or legal compliance.
- Reproduced the scenarios below separately against `accounting_core.py` and/or `accounting_reporting.py` with synthetic in-memory `RIAL` ledgers; compared UI management analytics in Node.
- No production books, Parsian backups, bank feed, tax service, or operational end-to-end UI tested for this **financial** audit.
- An initial test selection contained a non-existent test-module name (`tests.test_ir_invoice_joint_issue`), producing one `ImportError` unrelated to the application. The corrected 168-test selection passed.

## Findings

### FIN-01 [P1] Closed fiscal-year profit-and-loss differs by report

**Reproduction:** Issue one synthetic sale of 1,000,000 RIAL in 2025, run `fiscal.year.close` through 2025-12-31, then request a P&L for 2025-01-01 to 2025-12-31. `ledger_reports` returns 0 revenue and net after closing, whereas `buildManagementAnalytics` returns 1,000,000 RIAL revenue/net for that same reporting period. Before closing, `ledger_reports` returns 1,000,000.

**Cause hypothesis from inspected code:** `accounting_reporting.py:91-100` counts period movements including closing transfers; `src/accounting_management_analytics.js:153-171` excludes `fiscal.year.close` journals. This is a genuine reporting-contract inconsistency, not a statement that the closing entries themselves are invalid.

**Required behavior:** Define and label operational P&L versus post-closing ledger balance, then make reports cross-reconcile without losing pre-close turnover.

### FIN-02 [P1] Stock receipt blocked on taxed or discounted purchase bill

**Reproduction:** Create and issue a two-unit purchase bill at 100 RIAL/unit. `inventory.receive` posts 200 RIAL stock when tax/discount = 0, but rejects bills with 18 RIAL tax or 10 RIAL discount: `Allocate tax/discount separately before warehouse valuation`. In the rejected cases inventory remains at zero and the purchase base remains expensed.

**Source:** `accounting_operational_extensions.py:229-251`; `accounting_core.py:618-627`. **Remediation:** Support explicit verified allocation / policy-driven valuation without inventing tax recoverability, discounts, or cost.

### FIN-03 [P1] UTC calendar-day boundary can reject local same-day postings

**Reproduction:** With the same instant represented as `2026-11-02T22:00:00Z` versus `2026-11-03T01:30:00+03:30`, a `2026-11-03` invoice posting is rejected under the former and accepted under the latter. The desktop host supplies `datetime.now(timezone.utc).isoformat()` while the frontend creates local dates.

**Source:** `accounting_core.py:519-524`, `standalone_accounting_desktop.py:217-233`, `native_app.py:2003-2016`, `src/standalone_accounting_workspace.jsx:224`. **Remediation:** Apply one explicit company posting timezone consistently and retain trusted timestamps.

### FIN-04 [P1 control] Goods invoice can be issued before stock issue / COGS

**Reproduction:** Opening inventory 2 units at 60 RIAL/unit; issue an invoice for 1 unit at 100 RIAL. Before `inventory.issue`, period GL-based P&L shows revenue 100, cost 0, net 100, and stock remains 2 units/120 RIAL. After `inventory.issue`, cost 60, net 40, stock 1 unit/60 RIAL.

**Source:** `accounting_core.py:590-632` issues invoice; separate inventory journal at `accounting_operational_extensions.py:253-271`. **Classification:** Reproduced workflow/control risk, not proof of permanently misstated P&L if operators complete matching stock issue. **Remediation:** Combined workflow, clear stock-posting status, and incomplete-COGS alert before claiming profit.

### FIN-05 [P2 conditional] Purchase tax amounts are expensed

**Reproduction:** Issue a 1,000 RIAL purchase with explicit tax 90 RIAL: `5000` purchase expense = 1,000; `5200` tax expense = 90; total recognized P&L expense = 1,090. **Source:** `accounting_core.py:618-625`. This is not always wrong: creditable input tax requires different treatment from non-creditable tax. **Remediation:** Explicit policy and separate recoverable-tax asset and expense routes, based on verified legal and business assumptions.

### FIN-06 [P3] Tax preflight accepts non-finite float quantity values

**Reproduction:** `preflight_einvoice(..., lines=[{quantity: float('nan') ...}])` and `float('inf')` produce no quantity-specific blocker. Negative and zero quantities are rejected. **Source:** `standalone_accounting_tax_advisor.py:53-56`. This preflight is explicitly non-submitting (`submissionPermitted: false`), limiting direct operational impact. **Remediation:** Require bounded finite exact numeric values.

## Release gates

1. Retest FIN-01 and FIN-03 as first priority; cross-check reports over year close and midnight in company timezone.
2. Resolve stock/tax/discount allocation and ensure COGS completion is visible.
3. Validate accounting/legal/tax policy against a dated authorized source before claiming regulatory compliance.
4. Use isolated fixtures, verify SQLite event-chain replay and balances, then perform actual installed-GUI acceptance. Do not modify production finance data for tests.
