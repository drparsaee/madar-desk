# Madar Desk accounting core: integration contract

**Status (2026-10-21):** isolated Python accounting engine and tests. No native host,
React, LAN, SQLite, real bank, statutory invoice or tax authority integration has
been made by this worker. The module writes no files and performs no network I/O.

## Scope and persistent format

`accounting_core.py` implements an independent double-entry general ledger with
named customers and vendors, an extensible chart of accounts, sale invoices,
vendor bills, allocated receipts/payments, reversals and locked periods. **All
money is nonnegative integer tomans**, with individual and accumulated totals
limited to `10**15`. Floats, strings, fractions and bools are not amounts.

```python
from accounting_core import (
    empty_accounting_state, apply_accounting_command,
    accounting_view, validate_accounting_state,
)

state = empty_accounting_state()
assert validate_accounting_state(state) is True
# {'schemaVersion': 1, 'currency': 'TOMAN', 'events': []}

users = [{'username': 'owner', 'role': 'admin'}]  # verified host accounts
def execute(command):
    global state
    result = apply_accounting_command(
        state, command, actor='owner', accounts=users,
        now='2026-10-21T16:00:00+03:30',  # authenticated HOST clock
    )
    state = result['state']   # atomic persistence belongs to the host
    return result['result']
```

`apply_accounting_command` always returns `{state, changed, result}`. On
failure it raises `ValueError` or `PermissionError` and does not mutate input.
An identical retry of the same `eventId`, actor and command returns
`changed=False` with the previous result; a conflicting reuse raises. The
current authenticated actor's permissions are checked even on retry.

The persisted state contains only `events`, schema and currency. Every event
stores its canonical payload, actor, role, timestamp, result, fingerprint and
hash chain. `validate_accounting_state()` rebuilds journal/subledgers and
rechecks their consistency from events. The SHA-256 chain detects accidental
alterations but **is not an authenticated signature** and does not replace
trusted storage access controls or backups. Journal entries are projections of
append-only events; reversals create a new journal rather than editing entries.

## Setup and business documents

These examples are the exact accepted command fields; every command needs a
globally unique `eventId` that remains stable across transport retries.

```python
execute({'type': 'party.register', 'eventId': 'e-1',
         'partyId': 'buyer-1', 'name': 'Buyer Company', 'kind': 'customer'})
execute({'type': 'party.register', 'eventId': 'e-2',
         'partyId': 'printer-1', 'name': 'Paper Vendor', 'kind': 'vendor'})

execute({'type': 'invoice.create', 'eventId': 'e-3',
         'invoiceId': 'sale-10', 'partyId': 'buyer-1',
         'documentDate': '2026-10-21', 'sourceType': 'task-completion',
         'sourceId': 'completion-987',
         'lines': [{'description': 'Packaging design',
                    'quantity': 2, 'unitPrice': 300000}],
         'discount': 20000, 'tax': 0})
execute({'type': 'invoice.approve', 'eventId': 'e-4', 'invoiceId': 'sale-10'})
execute({'type': 'invoice.issue', 'eventId': 'e-5',
         'invoiceId': 'sale-10', 'postingDate': '2026-10-21'})

execute({'type': 'bill.create', 'eventId': 'e-6',
         'billId': 'purchase-20', 'partyId': 'printer-1',
         'documentDate': '2026-10-21', 'sourceType': 'task-costs',
         'sourceId': 'expense-proof-557',
         'lines': [{'description': 'Cardboard stock',
                    'quantity': 1, 'unitPrice': 170000}]})
execute({'type': 'bill.approve', 'eventId': 'e-7', 'billId': 'purchase-20'})
execute({'type': 'bill.issue', 'eventId': 'e-8',
         'billId': 'purchase-20', 'postingDate': '2026-10-21'})
```

`invoice.create` / `bill.create`: immutable line price, quantity, account ID
(optional; default revenue `4000` or expense `5000`), discount (default zero),
and explicit tax **amount** (default zero). `note` is optional. Tax amounts are
never calculated from rates: explicit sales tax posts to clearing liability
`2200`; explicit purchase tax is expensed to `5200` by this accounting policy,
**without assuming tax recoverability**. An upstream verified accounting policy
must approve those classifications. Gross subtotal minus discount plus explicit
tax equals document total. Nothing posts for a draft or approved document.

`sourceType` and `sourceId` are optional together, never individually. The
pair is unique **within noncancelled sales or purchase documents** even with distinct
event IDs, preventing accidental duplicate task invoices. The host must pass
the true durable source event (e.g. completion event or expense proof ID).
Draft correction uses `invoice.cancel` or `bill.cancel` with `reason`, followed
by a new document for the same source. Cancellation is restricted to drafts and
approved documents and leaves the cancelled version in history. Issued
documents require a compensating journal reversal instead.

## Receipts, payments and liquidity

```python
execute({'type': 'receipt.record', 'eventId': 'e-9',
         'receiptId': 'deposit-100', 'partyId': 'buyer-1',
         'accountId': '1010', 'postingDate': '2026-10-21',
         'allocations': [{'invoiceId': 'sale-10', 'amount': 250000}]})

# A vendor payment needs enough proven balance already posted in bank/cash.
execute({'type': 'funds.deposit', 'eventId': 'e-10',
         'accountId': '1010', 'amount': 200000,
         'postingDate': '2026-10-21', 'note': 'Host verified owner funding'})
execute({'type': 'payment.record', 'eventId': 'e-11',
         'paymentId': 'transfer-42', 'partyId': 'printer-1',
         'accountId': '1010', 'postingDate': '2026-10-21',
         'allocations': [{'billId': 'purchase-20', 'amount': 170000}]})
```

Allocation amounts must be positive, unique per document within a settlement,
match one named party and never exceed that document's remaining amount. An
allocation must not be dated earlier than its issued document. One receipt may
allocate to several sales invoices; one payment may settle several vendor bills.
Overdrawn cash/bank balances, including historical negative balances caused by
backdated entries, are refused. A document's `allocated` amount and a party's
AR/AP are derived from recorded, nonreversed settlements. No unallocated cash
movements or cross-party netting are implemented.

**Proof of cash movement is the host's responsibility.** `funds.deposit` is an
explicit owner-funding journal, not a network bank deposit. Existing
`finance.py` `advance` fields are contract figures and must not automatically
post as cash or receipt without a verified payment and unique receipt event.

## Posting map and read model

| Operation | Debit | Credit |
| --- | --- | --- |
| Issue sale | AR `1200`: total; sales discounts `4100` | Revenue `4000` or line-selected revenue accounts: subtotal; tax clearing `2200` if explicitly set |
| Issue purchase bill | Purchases `5000` or line-selected expense accounts: subtotal; purchase tax expense `5200` if explicitly set | AP `2000`: total; purchase discounts `5100` |
| Receipt | Cash/bank `1000` / `1010` | AR `1200` with customer ID |
| Vendor payment | AP `2000` with vendor ID | Cash/bank `1000` / `1010` |
| Owner funding | Cash/bank | Equity `3000` |
| Journal reversal | Prior credits | Prior debits |

```python
view = accounting_view(state, actor='owner', accounts=users)
view['parties']['buyer-1']['receivable']       # outstanding customer debt
view['parties']['printer-1']['payable']        # outstanding vendor payable
view['accounts']['1010']['normalBalance']      # liquid bank balance
view['invoices']['sale-10']['allocated']       # verified allocated payments
view['journals']                               # append-only postings, balanced
```

`account.create {type,eventId,accountId,name,kind,liquid}` adds chart accounts.
Kinds: `asset`, `liability`, `equity`, `revenue`, `expense`; only assets may be
liquid. Protected built-in accounts are never deleted/renumbered. `party.kind`
may also be `both` for a customer who is simultaneously a vendor. All read
models are new copies. Admin and users with trusted `financeView`/`financeEdit`
may read; an editor with `financeEdit=True` may create parties and drafts, but
only the administrator can approve, post, settle, change chart or reverse.

## Reversals, closure and authoritative storage

```python
execute({'type': 'journal.reverse', 'eventId': 'e-12',
         'journalId': 'J:e-11', 'postingDate': '2026-10-21',
         'reason': 'Bank transfer returned'})
execute({'type': 'period.close', 'eventId': 'e-13',
         'throughDate': '2026-10-21'})
```

Reversal creates an equal and opposite entry, preserving original journal,
source and invoice/bill sequence. A posted sales/purchase document may be
reversed only after its settlement allocations have themselves been reversed.
Cash overdraft protection also applies to reversals. Reversals cannot precede
their original entry or land in a closed period. `period.close` advances the
closed-through date monotonically; there is no implicit reopening.

When integrating with Madar, the single host transaction must atomically
commit **both** existing `finance.py` state and the optional nested `accounting`
state with an optimistic revision/CAS check. The existing strict finance v1
schema does not yet accept a nested `accounting` key: Prime/host integration
must add an explicit compatible migration/validation route. Never treat
`accounting_core.py` as a second persistence writer. Map any existing finance
invoice issue to exactly one GL issue event and preserve original provenance;
avoid creating two business invoices for the same completion.

The host must validate verified session identity, account role, task/customer
ownership, event IDs, receipts, source identifiers and real payment proof. This
module checks consistency and authority based on supplied trusted data and
cannot independently prove bank movements or statutory compliance. No Iranian
tax, VAT filing or electronic fiscal invoice compliance has been implemented.

## Verification

Run from the Madar project root:

```powershell
python -m unittest tests.test_accounting_core -v
```

The focused suite tests sales and vendor GL directions, debit/credit symmetry,
multi-document allocation, no oversettlement, no overdraft (including historic
backdating), role revocation, replay collision, immutable reversals, closed
periods, tax/discount journal balance, integer boundaries, source deduplication
and tampered event data. It does not assert native GUI, bridge, LAN or database
transaction integration.
