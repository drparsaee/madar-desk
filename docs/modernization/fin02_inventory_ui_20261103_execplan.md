# FIN-02 1.0.13: exact purchase allocation UI

## Scope / ownership

Isolated Windows worktree `D:\CoS-Test\madar-finance-ui-exact-20261103`, branch `fix/madar-finance-ui-exact-20261103`, baseline integration `0b93c50cc476dfd4abba8664f8fae6080157e47b` (contains finance commit `949cce6`). Only `src/accounting_operational_panels.jsx` and **new** tests/docs are owned. Do not change backend, previous tests, real finance data, UI theme files, main, host, installers, user APPDATA or release.

## Existing source contract

`LiveInventory` currently exposes only `single-line-uniform` for a one-line discount with divisible whole-unit cost. It blocks multi-line or fractional discounts even though `accounting_operational_extensions.py` now accepts a separately administered `per-line-exact` policy. The parent `StandaloneAccountingWorkspace` passes both `canManage` and `canAdmin` to `LiveInventory`; editors can have financial mutation rights but must not establish a new exact allocation policy. View-only users do not see financial forms.

The backend command requires `discountAllocation:'per-line-exact'`, every bill line's ordered `{lineIndex,amount}` (including service lines), `allocationReference` matching account ID syntax, `allocationReason` nonempty, full line discount sum equal the already-posted bill discount, and `taxTreatment:'expense'` for taxed receipts. A bill's `receiptDiscountAllocation` is immutable after first receipt; no initial allocation is allowed after a historical return. The core rejects taxed partial returns with no source-approved per-line tax allocation. FIFO value must remain exact integer and positive. Accounting unit remains the posted bill currency, never an assumed toman/rial conversion.

## Execution plan and acceptance

1. Introduce a pure exported exact-integer command review builder without touching the engine. It validates indexed line sums and bounds, positive stock line valuation, existing allocation policy and linked movement/return conflicts. Use BigInt internally and safe bounded numbers in the transmitted JSON. Missing or invalid evidence fails closed; no automatic split from document total.
2. Add an admin-only opt-in `per-line-exact` choice to the existing inventory form while keeping the old simple path. Display one editable amount per issued bill line including services, associated supplier line gross, grand totals and read-only preview of cost. Require explicit reference/reason, final reviewed confirmation, and freeze all fields when an existing source-backed policy exists. Reset stale form state when bill changes.
3. Verify existing editor and viewer permissions, backend contract and rejection of taxed partial credit notes, keyboard and mobile use in real synthetic Chrome, and Node tests for exact amounts and emitted payload. Existing UI contract tests containing stale old strings must continue to express truth for the simple mode; do not edit those tests.
4. Run targeted Python engine tests, source UI tests, Chromium synthetic interactions (narrow and wide), diff checks, commit only approved files; report SHA to prime. Installation and legal-tax acceptance are separate.

## Progress

- **VERIFIED initial:** `0b93c50` contains `949cce6`, clean new worktree. Existing UI and engine contract inspected. No code change yet.
- **VERIFIED source/UI:** precise integer preview and admin-only immutable source-backed line form; final confirmation; editor's simple route unchanged. Observed 4 new Node/Chrome tests PASS, 4 pre-existing inventory/company UI tests PASS and 32 backend engine tests PASS. See [`fin02_inventory_ui_20261103_validation.md`](fin02_inventory_ui_20261103_validation.md).
- **PENDING:** final staged diff review and commit SHA/prime handoff (no publish or installed-GUI acceptance implied).
