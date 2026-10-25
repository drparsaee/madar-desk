# Madar Desk: pure RIAL inventory domain (worker-12)

## Scope and status

Implemented **only** `ir_inventory_rial.py` and its isolated
`tests/test_ir_inventory_rial.py`. The domain imports the existing, unchanged
`money_policy.py` canonical RIAL bound/hash utility. It does **not** talk to
SQLite, legacy TOMAN finance, SQL Server/Parsian, APPDATA, LAN, GUI, or the
`ir_journal_v2.py` host. It has no filesystem or network operations.

**Integration status: candidate domain only; no host integration or real
persistence verification.** An unkeyed SHA256 chain detects edits relative to
an independently trusted committed head. A malicious writer able to rewrite
both the full snapshot and every hash can forge a new chain. The host must
anchor the revision durably, verify actor/document ownership independently,
and atomically commit under a CAS/unique-source constraint.

## Canonical inventory contract

- Each immutable `ItemSpec(company_id, item_id, unit,
  base_units_per_unit)` defines a unit and **exact** measurement scale. An
  example is `unit="kg", base_units_per_unit=1000` for integer gram
  quantities. `to_base_quantity(item, "1.025") == 1025`. Decimal inputs
  unable to resolve into whole base units, floats, scientific notation, and
  negative quantities are rejected. No float arithmetic is used for stock.
- `InventoryState(company_id, items, warehouse_ids, events)` contains an
  immutable, sorted company catalog and append-only typed events.
  `new_inventory_state` rejects foreign, duplicated, or excessively large
  catalogs. Inventory quantities and cumulative RIAL values are bounded.
  Catalog/version migrations require a separate validated host protocol.
- `StockEvent` carries `company_id`, actor, item, warehouse, typed
  `BusinessSource(kind, source_id)`, unit/scale, integer base quantity,
  optional project/job/cost-center, plus type-specific fields. A different
  `event_id` cannot reuse a business `source_id` in that company **even
  across source kinds**; the host's source ID namespace must therefore be
  globally unique within its company inventory stream.
- `StockAuthority` declares exactly verified actor/item/warehouse/source
  scopes and optional project/job/cost-center associations. Reversing a
  warehouse transfer also requires fresh permission on the original
  destination warehouse, which the reversal implicitly debits. This object is
  meant to be constructed from **trusted server-side evidence**, never
  accepted as user-selected values. It is embedded in the immutable
  hash-chained event to permit strict deterministic historic replay.
- The `expected_revision` argument to `append_stock_event` is a pure
  optimistic CAS preflight. Identical event ID + exact same payload/authority
  retries return the existing state. Changed event ID/same source and changed
  payload/same event ID are conflicts. The host must apply this CAS to the
  actual persisted revision inside one transaction; pure callers cannot
  prevent two concurrent processes from committing stale snapshots.
- Bounded replay recomputes FIFO consumption, staging, inventory positions,
  exact event effects and hashes from scratch. No user-supplied cached
  balance is accepted. Event, layer, authorization scope and event-slice
  ceilings guard resources (`MAX_EVENTS=10000`, `MAX_LAYERS=20000`,
  `MAX_EVENT_SLICES=256`, `MAX_QUANTITY=10^12`).

## FIFO valuation and staging

This candidate uses **FIFO**, not weighted-average. Every priced receipt
creates an immutable layer with origin-event provenance, remaining base units
and remaining total integer RIAL cost. A partial issue of `q` from remaining
layer `Q` with remaining value `V` takes `floor(V*q/Q)` RIAL; the final
issue of the remaining layer takes the exact residual `V`, so full depletion
is exact. E.g. 3 base units priced at 10 RIAL issue as 3 + 7 RIAL for
consecutive issues of 1 and 2. No round-trip TOMAN conversion.

`RECEIPT` with `cost_rial=None` goes into `StagedLot`, physically visible
as **unpriced staging** but excluded from FIFO valued inventory and the
inventory asset total. It cannot be issued or transferred. `PRICE` points
to the costless receipt's ID and transfers its entire staged quantity into
a priced layer using a separately verified total RIAL cost. Partial pricing
is not supported. `cost_rial=0` is explicitly priced zero value and differs
from `None`. A reversed price returns units to staging.

`ISSUE` reduces FIFO stock and value, refusing any deficit.
`TRANSFER` conserves exact layer value when moving priced stock between
two authorized warehouses. The destination gets new immutable layers
preserving original receipt provenance and costs. `ADJUSTMENT` records
`expected_quantity_base` and `counted_quantity_base`, verifies current
count baseline, requires an audit reason, FIFO-costs shortages and requires
explicit priced RIAL cost for surpluses. If any unpriced stock for this
item/warehouse exists, cycle count fails closed until staged stock is priced
or segregated by a future explicit workflow.

`RETURN` restores **the entire quantity of one prior ISSUE**, using its
original consumed FIFO costs. `REVERSAL` restores the exact original value
as a new traceable event for supported receipt/issue/transfer/adjustment/
pricing movements. It cannot be used to reverse a RETURN or another
REVERSAL, and one original cannot be both returned and reversed.
Receipt/transfer/pricing reversal requires any created lots to remain
untouched, so consumed/partially transferred stock cannot be silently
rewound. Partial returns or reversals are deliberately rejected.

Chronological application is the append order; there is no date/backdating
model in this domain. A fiscal posting period or closed-period control belongs
to the authoritative host and `ir_journal_v2`. The host should refuse stock
movements whose verified business date falls in a closed period according to
its policy.

## Pure general-ledger proposal contract

`propose_inventory_journal(state, inventory_event_id, account_mapping)`
replays the entire stock history and derives **balanced integer-RIAL** lines
with explicit `InventoryAccountMapping` roles:

| Valuation event | Debit | Credit |
| --- | --- | --- |
| Priced receipt | Inventory asset | Receipt clearing |
| FIFO issue | Issue expense / job WIP account | Inventory asset |
| Positive cycle variance | Inventory asset | Adjustment gain |
| Negative cycle variance | Adjustment loss | Inventory asset |
| Stage pricing | Inventory asset | Pricing clearing |
| Full issue return | Inventory asset | Issue expense |
| Reversal | Inverted role of original | Inverted role of original |
| Internal warehouse transfer, unpriced receipt, zero-value entry | No proposed GL lines | No proposed GL lines |

The result is a `InventoryJournalProposal` containing exactly the source
identity, company and work references and a two-line balanced proposal. The
host must independently resolve these account codes using
`ir_chart_model.validate_posting_reference`, enforce company project/job/
cost-center ownership, choose a valid open `fiscal_period_id`, register
the source through `ir_journal_v2`, validate company authorization and
atomically store financial and inventory changes together. Account mapping
is an input to the **proposal**, not evidence that a chart account exists or
that a GL journal was posted. Zero-RIAL stock changes have no ledger proposal;
the host may need a separate nonposting audit policy for such stock events.

Recommended host transaction:

1. Authenticate session and server-verify company, actor, item, warehouses,
   project/job/cost center, commercial source and original linked event.
2. Read stored inventory and finance snapshots **under the same transaction**;
   verify both revisions and replay their domain invariants.
3. Call `append_stock_event` with trusted `StockAuthority` and stored
   revision, compute `propose_inventory_journal` from new state, and submit
   its source through actual journal/chart validation.
4. Enforce a durable unique key on `(company_id, business_source_id)`, plus
   `(company_id,event_id)` and source uniqueness on the GL side as
   appropriate. Atomically commit inventory and any GL posting in the same
   finance CAS/SQLite transaction. On failure, roll back **both**.
5. Save new committed revision independently of client snapshots, audit
   actor/source evidence, and reject stale LAN or offline clients.

## Verification and open integration work

Run from the Madar Desk repository root:

```powershell
python -m unittest tests.test_ir_inventory_rial -v
```

The isolated synthetic tests cover integer precision and unit scale,
multi-lot FIFO rounding, stages/pricing, transfers, returns and reversals,
stale count and CAS, unauthorized company/item/warehouse/actor/source/work,
duplicate commercial source across event IDs, historic hash/effect
tampering, deterministic snapshots, and balancing of proposal lines.

**Not verified:** host authentication, real company ownership, actual
SQLite transactions, concurrent-process races, durability, finance dual
posting, LAN authorization, native GUI, APPDATA, SQL/Parsian, fiscal close,
release or deployment. Their completion requires separately scoped host
implementation and end-to-end tests. No production-readiness claim is
implied by passing the domain unit tests.
