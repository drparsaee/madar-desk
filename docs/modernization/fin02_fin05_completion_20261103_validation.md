# FIN-02 / FIN-05 verification evidence (2026-11-03)

## Source and isolation

Baseline `6cc045446b37a23bb217cda566d785e73aed4c9e` in separate `D:\CoS-Test\madar-financial-complete-20261103` worktree. Only `accounting_core.py`, `accounting_operational_extensions.py`, new regression test and this task's new docs changed. Synthetic RIAL ledger and disposable SQLite under Python `TemporaryDirectory`. Standalone discovery tests ran with `APPDATA` and `LOCALAPPDATA` redirected to named directories under TEMP, not actual user finance profiles. No mutation of main, production host, installed EXE, Parsian, or real company ledger.

## Test results (actual observed)

| Command / scope | Result |
|---|---|
| Baseline `python -m unittest tests.test_accounting_reporting tests.test_accounting_extended_operations tests.test_accounting_partial_returns` before changes | 26 tests, OK |
| New `python -B -m unittest -v tests.test_fin02_fin05_exact_purchase_allocation_20261103` before partial taxed-return control | 15 tests, OK |
| Final post-control targeted `python -B -m unittest -v tests.test_fin02_fin05_exact_purchase_allocation_20261103 tests.test_integrated_financial_20261103 tests.test_accounting_partial_returns` | 31 tests, OK (includes 16 new) |
| Adjacent `python -B -m unittest tests.test_fin02_fin05_exact_purchase_allocation_20261103 tests.test_integrated_financial_20261103 tests.test_accounting_core tests.test_accounting_reporting tests.test_accounting_partial_returns tests.test_accounting_extended_operations tests.test_standalone_finance_acl_comprehensive` | 83 tests, OK |
| Final adjacent same named command, after taxed-partial-return guard | 84 tests, OK |
| Final post-control `python -B -m unittest discover -s tests -p 'test_accounting*.py'` | 119 tests, OK |
| Discovery `python -B -m unittest discover -s tests -p 'test_accounting*.py'` | 119 tests, OK |
| First `python -B -m unittest discover -s tests -p 'test_standalone_accounting*.py'` | 189 tests, 1 error; 2 expected failures. Unrelated local HTTP test `test_standalone_accounting_host.StandaloneLanTests.test_http_unauthenticated_post_rejects_even_malformed_payload` aborted Windows socket with WinError 10053. |
| Isolated retry of the failed HTTP test | 1 test, OK |
| Second standalone-accounting discovery with disposable app data | 189 tests, OK (expected failures=2) |
| Final post-control standalone-accounting discovery with disposable app data | 189 tests, OK (expected failures=2) |

These suites **overlap**. Do not add their counts into a unique global total. The host socket abort in the first discovery run remains an intermittent Windows test-environment observation, not a proven accounting-code defect. The new source changes and exact purchase tests did not exercise a real tax service or source legal authority.

## Financial acceptance scenarios

The new synthetic tests exercise mixed stock/service bills, nonrecoverable tax expense, line-indexed exact discount allocation, partial receipts split across warehouses, exact FIFO values from original bill, FIFO sale and COGS/reversal, transferring stock and reversing the transfer before the source receipt, cumulative integer discount on consecutive untaxed credit notes, full taxed purchase return after stock reversal, refusal of taxed partial credit without source-proven tax allocation, re-receipt of net remaining quantities, duplicate SKU lines failing closed, zero-valued unit refusing valuation, malformed allocations or fake recoverability refusing mutation, admin-only policy, stable policy across receipts, immutable duplicate event fingerprint and verified SQLite CAS/reopen. `validate_accounting_state`, `ledger_reports` trial balance and inventory-asset-to-stock value are checked.

## Boundaries and remaining gates

FIN-02 is implemented for operator-attested, complete per-line supplier discounts, with exact positive whole-unit FIFO and explicit expense-only input tax. `lineDiscounts` reference/reason are **not externally authenticated**; accountant validation of their actual business correctness is required. No support is claimed for the same catalog item appearing in two lines of a single bill, zero-valued units, changing discount policy after receipts, converting previously returned discounted bills without a source-supported allocation, or partial taxed vendor credit notes without an itemized tax source.

FIN-05 remains **blocked** for automatic recoverable VAT reclassification. Required: dated authorized tax policy, company eligibility, source invoice evidence, item-level tax split, validated GL asset/account migration, admin approval, linked reversal and return, fiscal period controls, statutory reconciliation, and independent accounting acceptance. All current taxed receipts continue under explicit existing `taxTreatment='expense'` with purchase tax recorded in expense 5200.

No installed-GUI, production accounts, real supplier invoice, actual Parsian bank/import, legal-rate verification or complete application-release acceptance was performed. The prime integration agent must run combined tests and handle separately authorized release gates.
