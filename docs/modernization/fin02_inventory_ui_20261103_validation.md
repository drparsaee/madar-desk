# FIN-02 1.0.13 exact discount UI: actual verification and limitations

## Baseline and ownership

Worktree `D:\CoS-Test\madar-finance-ui-exact-20261103`, base integration SHA `0b93c50cc476dfd4abba8664f8fae6080157e47b` (parent of integration already containing `949cce6`). Only `src/accounting_operational_panels.jsx` and new `tests/accounting_fin02_exact_discount_ui_20261103.test.cjs` and these new task docs were edited. No change to `accounting_core.py`, backend tax entitlement, other UI, real finance data, user APPDATA, host, installer, main or LocalForge remote.

## UI implementation and read/write boundary

The pre-existing simple uniform single-line receipt route remains available to permitted finance editors. For a discounted multi-line purchase or fractionally discounted units, an authenticated **admin-only** `per-line-exact` selector explicitly requires an exact monetary input for each source bill line, including any service line or zero-share line; exact integer sum equal to source bill discount; nonnegative bounded line values not exceeding original gross; valid alphanumeric evidence reference and nonempty documented reason; selected SKU exactly once on the bill and a receipt quantity not exceeding net available nonreturned units; explicit `taxTreatment:'expense'` on taxed bills; and a final confirmation after inspecting the preview. The form never infers percentage discount, VAT credit, or merchant invoice documentation.

`previewExactPurchaseDiscountAllocation` is a **UI-only** pure, exported validator. It uses BigInt for total and FIFO split calculations, then sends bounded exact JS integers in `lineDiscounts:[{lineIndex,amount}]` and original source reference/reason. The authenticated Python engine is the independent final authority. A previous `receiptDiscountAllocation` is surfaced read-only with the same source values. Inconsistent source data, prior conflicting receipt mode, old purchase returns without an established allocation, zero-unit valuation, negative/NaN/fractional/oversize inputs, tax policy ambiguity, and stale admin permission fail closed. Revocation clears selected admin-only policy from component state. Taxed purchase **partial** returns in this mode remain explicitly blocked by the engine until documented per-line tax allocation is available, even though taxed stock receipts expensing tax to account 5200 are supported.

## Actual tests

| Evidence | Result |
|---|---|
| JSX source bundled with esbuild in Node from the isolated worktree | PASS (`JSX BUILD PASS`) |
| `node --test tests/accounting_fin02_exact_discount_ui_20261103.test.cjs` | 4/4 PASS. Pure exact arithmetic, fail-closed invalid inputs, immutable prior policy/read-only view, real Chrome/React interaction at 390 and 1440 px |
| Browser checks in same test | PASS. Admin entered `[1,3,6]` discounts on mixed stock/service bill and submitted `per-line-exact` command with mandatory reference/reason and `taxTreatment:'expense'`; insufficient sum blocked; preview showed exact FIFO receipt value 200; changed bill cleared prior entries; stored allocation was read-only; editor could not choose new policy but could use existing `single-line-uniform`; revocation removed admin-only selection and viewer had no form. No browser page errors. |
| `NODE_PATH=D:/CoS-Test/madar-desk/node_modules node --test tests/integrated_inventory_company_controls.test.cjs` | 4/4 PASS; existing simple-mode, company-time and incomplete-COGS UI tests remain green |
| With disposable temp APPDATA/LOCALAPPDATA: `python -B -m unittest tests.test_fin02_fin05_exact_purchase_allocation_20261103 tests.test_integrated_financial_20261103 tests.test_standalone_finance_acl_comprehensive` | 32/32 PASS; engine/admin/stock/GL/returns replay tested against synthetic source records |

The suite counts overlap in the sense that they exercise the same behavior through different layers. Chrome tests mount the actual React `LiveInventory` component bundled with real dependencies in an isolated synthetic page, not a full installed WebView2 app. Test `execute` captures the command without making a host mutation; the separate Python suite exercises the actual deterministic financial engine. There was no assertion of legal input VAT recoverability, supplier document authenticity or installation acceptance.

## Remaining release boundary

Cherry-pick this source-only UI commit into the official integrated branch, run the combined Vite/Node/Python browser and host suites, package/release only after prime's normal gates. Real supplier allocations must be approved outside software; the form only records the operator's assertions. Partial taxed returns and FIN-05 recoverable input VAT remain blocked pending source-backed fiscal policy, verified tax-by-line and account routing plus reversal/closed-period controls. No live tax, bank, historical Parsian migration, production business accounts, or installed EXE were tested.
