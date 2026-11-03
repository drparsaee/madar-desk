# Accounting finance fixes: behavior contracts

## FIN-01: close and P&L

`profitLoss` remains `{revenue, expense, net}` in the original unit, but now represents operational income/expense journals excluding `fiscal.year.close`. `profitLossReconciliation.postCloseLedgerMovements` shows revenue, expense and net movements **including** the closing journal. `closingAdjustmentNet` is the latter net minus operational net. Closing journal still appears in GL statements and account movement, while retained earnings and balance sheet use genuine posted balances. Date ranges include journal postings according to the given inclusive start/end, and a later-year close does not erase the earlier operational turnover.

## FIN-03: fixed company offset

An administrator may pass `postingUtcOffsetMinutes` to `company.profile.set`, with a signed integer multiple of 15 between -720 and +840. Enabling or changing the offset requires `postingCalendarMode="fixed-offset-no-dst"`; named timezone/DST strings fail closed. Once set it survives a later profile edit unless explicitly changed. The system derives local Gregorian `today` from the trusted timezone-aware `now` instant and configured offset in posting, closing, proforma and payroll checks. Existing profiles without this field keep `now[:10]` behavior to preserve historical event replay. The offset is a **fixed calendar policy**, not full named timezone/DST; never silently infer it from a host or client clock. Until frontend `standaloneToday()` uses the company policy or a trusted host date, UI document defaults can still differ from the backend at midnight, so FIN-03 is **backend-only** pending integration.

## FIN-06: exact preflight

`quantity` must be a Python `int` from 1 through 1,000,000, and `unitPrice` a Python `int` from 1 through 10**15. Boolean, float including NaN/Infinity, string and overflow are blockers on their exact field. `quantity * unitPrice` greater than 10**15 is a `lineTotal` blocker. Existing regulatory review blocker and `submissionPermitted=False` remain.

## FIN-02/04: live stock control

`stockCostControl` is attached to read-only `ledger_reports` results. For the **current projection only**, it compares net unreturned quantities on issued tracked goods documents with non-reversed linked stock receipts/issues. Missing sales issues emit `stock-issue-and-cogs-pending`; missing purchase receipts emit `stock-receipt-pending` or `valuation-policy-required` when document-level tax/discount exists. Even when no unmatched tracked lines are seen, `profitCertified` is always false: untracked costs, taxes, payments, services, past item tracking status and regulatory treatments are not certified by this check. A historical `through_date` yields `assessment=not-assessed` because the current catalog's past stock-tracking state is not fully reconstructable from the exposed view.

## FIN-05: external policy prerequisite

No recoverable purchase-tax asset or capitalization rule has been added. A recoverable-vs-expense tax policy requires approved business and dated legal source information before its GL routing can be validated. Existing posted entries and account mapping remain unchanged.
