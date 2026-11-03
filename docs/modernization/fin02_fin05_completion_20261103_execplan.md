# FIN-02 / FIN-05 financial completion review (2026-11-03)

## Purpose, provenance, isolation

Owner requested the full finance package while explicitly forbidding invented VAT eligibility, guessed purchase valuation and unverified accounting adjustments. Baseline commit `6cc045446b37a23bb217cda566d785e73aed4c9e`, isolated branch `fix/madar-finance-completion-20261103` at `D:\CoS-Test\madar-financial-complete-20261103`. Edit scope is `accounting_core.py`, `accounting_operational_extensions.py`, new tests and this documentation only. No source main, UI, EXE, APPDATA, financial database, customer books, host or tax service modifications.

## Existing behavior and call graph

`accounting_core._issue` debits purchase expense (source line accounts) plus 5200 purchase-tax expense and credits 5100 purchase discounts and 2000 AP. No input tax entitlement exists in the model. The event-sourced `_project` replays immutable commands, checking hash chain, GL and operational inventory totals; the authenticated host persists one revision/CAS event. `accounting_operational_extensions.apply_extended` accepts `inventory.receive` for stock only when tax is explicitly treated as expense and any single-line discount divides equally into whole units. The FIFO layer is `{source,quantity,unitCost}` and inverse stock movements reverse linked GL entries. `accounting_core._partial_return` currently allocates document-level discount and tax across returned gross, rather than honoring an explicit supplier line allocation.

## Intended bounded change (FIN-02)

Add opt-in purchase stock valuation mode `discountAllocation='per-line-exact'`, with `lineDiscounts` mapping **every bill line** by `lineIndex` to an explicitly declared exact integer `amount`, total equal to the original bill discount. Require auditable `allocationReason` and `allocationReference` from the operator; preserve bill issue postings and classify all tax as expense only with `taxTreatment='expense'`. Never apply a line discount to an unrelated item. New FIFO receives split integer unit costs (within one source event) so their sum precisely equals original line cost minus its assigned discount, including fractional per-unit amounts. Mixed service lines keep their discount in 5100. The same documented allocation must apply to every receipt of a bill. Existing single-line-uniform events and snapshots continue to replay unchanged. Unit costs must remain positive, and inventory receipts cannot exceed net non-returned quantities.

Restoring inventory receipts must reverse the exact ledger entry and FIFO layers. Partial purchase returns on a bill with the new allocation rule must use that line's cumulative, exact-integer discount share. Because the previous return path could have used a different discount basis, an already-returned discounted bill with no prior recorded line allocation must fail closed before a first new-mode receipt.

## FIN-05 policy boundary

There is **no authorized dated legal/business tax-policy source** nor account-specific entitlement rule in the current source. The new receipt mode shall not introduce a recoverable VAT GL asset, tax credit, tax rate, or implicit tax capitalization. Reject `taxTreatment='recoverable'` and any unsupported routing. To enable recoverability later requires dated authoritative legal classification by the company's responsible accountant; invoice eligibility and documentary status; valid recoverable percentage per line; explicit compatible account mapping and chart migration (system asset vs historical custom account); a separate audited reclassification command with reversal and period-close protection; mixed recoverable/nonrecoverable taxes and returns; reconciliation of AP, VAT, inventory and GL; authorization and UI warnings.

## Progress and validation gates

- **VERIFIED baseline:** `python -m unittest tests.test_accounting_reporting tests.test_accounting_extended_operations tests.test_accounting_partial_returns` => 26 tests OK (synthetic).
- **VERIFIED in source tests:** explicit line allocation, fractional whole-unit FIFO, legacy-mode retention, exact reversal and fail-closed taxed partial returns; 16 new synthetic tests passed. Final adjacent financial suite 84/84 OK; final accounting discovery 119/119 OK; final standalone accounting discovery 189 tests OK with 2 known expected failures. The first discovery had one Windows socket abort in an unrelated HTTP test, which passed isolated and in two subsequent complete discovery runs. Exact run evidence and limitations are in [`_validation.md`](fin02_fin05_completion_20261103_validation.md).
- **PENDING:** final scope/diff review, `git diff --check`, local commit and prime handoff. A source commit is not a release or a tax/legal authorization.
