# Independent P0: FIFO inventory to RIAL V2 general-ledger bridge

**Status:** isolated pure candidate implementation, **not connected** to
Madar Desk's host, database, GUI, LAN, real invoices, or accounting persistence.
Only newly created `ir_inventory_journal_adapter.py`,
`tests/test_ir_inventory_journal_adapter.py`, and this handoff file belong
to this tranche. No existing domain files were changed.

## Authoritative inputs and output

`apply_inventory_gl(stock, journal, inventory_event_id, *, chart, scopes,
accounts, context, money_policy, settlement=None)` returns frozen
`InventoryGLBridgeResult` with an immutable RIAL V2 journal **candidate**,
status `POSTED`, `REVERSED`, `IDEMPOTENT` or `NO_GL`, exact RIAL value,
stock business source, optional supplier invoice, original movement ID for
returns, journal event ID, and a SHA256 digest of the stock/proof relation.
It never writes persistent data.
The proof digest is anchored to the individual immutable stock event hash,
so subsequent unrelated inventory movements do not alter this event's proof;
the current stock revision is separately returned for a durable CAS check.

The host must independently generate and attest:

- `stock`: canonical FIFO `InventoryState` containing already appended,
  validated stock events, each with server-confirmed `StockAuthority`.
- `journal`: actual current RIAL `JournalState`, not a client snapshot.
  Both histories are replayed and verified before posting.
- `accounts`: `VerifiedInventoryAccounts(base, payable_account,
  work_in_progress_account)`. `base` is existing
  `InventoryAccountMapping`; the chart is verified for company, matching
  account role, posting eligibility and downstream analytic references.
- `scopes`: `ir_journal_v2.VerifiedScopes` confirmed by the authenticated
  host. An inventory source becomes `JournalSource("independent",
  commercial_source_id, project_id)`, requiring **exact**
  `(project_id,commercial_source_id)` in
  `independent_source_scopes`. Supplier party, project, task and job
  membership must also match the chart/verified scope.
- `context`: `VerifiedGLPosting` with company, actor, fiscal period,
  posting date, server today, **both** expected snapshot revisions, and an
  explicit `COGS` or `WIP` issue policy.
- `money_policy`: company-matched immutable canonical RIAL money policy.
- `settlement` for valued `RECEIPT` or staged-receipt `PRICE`:
  `VerifiedReceiptSettlement(company_id, inventory_event_id,
  commercial_source_id, mode, exact_amount_rial, supplier_invoice_id,
  supplier_party_id)`. The amount must exactly equal the replayed FIFO
  asset delta. The host is responsible for genuine supplier invoice/receiving
  evidence, not just object type construction.

Proof objects are structured host **contracts**, not cryptographic identities.
The module cannot authenticate a client or determine whether a party or
supplier invoice is real.

## Supported journal mappings

| Inventory event | Debit | Credit | Conditions |
| --- | --- | --- | --- |
| Priced `RECEIPT` | Inventory asset | GRNI liability | Exact verified GRNI settlement |
| Priced `RECEIPT` | Inventory asset | Accounts payable | Verified vendor, bound floating party detail, invoice ID and exact invoice amount |
| Costless `RECEIPT` | none | none | Remains unpriced staging; **never** recognizes AP, GRNI or inventory value |
| `PRICE` on staged receipt | Inventory asset | GRNI or AP | Only after complete staged quantity priced in stock kernel; current movement receives verified settlement |
| `ISSUE` (COGS) | COGS expense | Inventory asset | No registered job attached; valuation from exact FIFO consumption |
| `ISSUE` (WIP) | WIP asset | Inventory asset | Explicit WIP policy, verified project/job and any associated cost center/task |
| `TRANSFER` between warehouses | none | none | Must conserve exact asset value; neither AP nor COGS created |
| `RETURN` of full issue | Exact inversion of original V2 entry | Exact inversion of original V2 entry | Uses V2 `reverse_journal` with provenance and reversal-of reference |
| `REVERSAL` | Exact inversion of original V2 entry | Exact inversion of original V2 entry | Must refer to committed, compatible prior inventory journal; no fresh invoice |

For supplier AP, the verified `supplier_invoice_id` must equal the stock
`commercial_source_id`; this is an **explicit single-document policy**
preventing a supplier invoice from being counted repeatedly under different
inventory event IDs. This policy does not model supplier invoice lines or
multiple receipts against one invoice. Those require a separately reviewed
aggregated voucher/GRNI clearing mechanism.

Price proof for a previously costless receipt belongs to its **PRICE event**.
The earlier costless `RECEIPT` has no valuation and cannot produce a financial
entry. `cost_rial=0` movements have no numeric journal lines (RIAL V2 rejects
zero debit/credit rows); they yield `NO_GL`, subject to the host's durable
nonposting audit obligation.

Chart account kinds are checked: inventory/WIP must be assets, GRNI/AP/price
clearing liabilities, COGS an expense. Account must be active, accountable,
unfrozen and unarchived when creating a new journal. A reversal delegates to
`ir_journal_v2.reverse_journal`, which reuses historical chart evidence and
exact original lines, permitting legally traceable reversal even when an old
account was subsequently archived. Stock `RETURN` and `REVERSAL` are
full-original only under the existing FIFO kernel.

**Deliberately rejected:** GL posting for `ADJUSTMENT` / cycle-count
surpluses or shrinkage until finance policy is explicitly approved, arbitrary
source-kind remapping to task/card/checklist, unverified cross-project WIP,
costless AP recognition, partial returns, changing the original reversal
amount, or inventing supplier invoices. Unsupported policy produces an error,
not a silently omitted journal.

## Deterministic identity, replay and limitations

Normal journal IDs are deterministically derived from
`(company_id, commercial_source_id)` with a versioned SHA256 digest and
`INVGL-` prefix. They do **not** use the stock `event_id`. Before posting,
the bridge replays the full journal, scans for **any** previous use of that
commercial source (including differing V2 event IDs), checks existing
posting details, and rejects conflicting reuse. Exact retried requests return
the same journal candidate without another posting; a normal retry must also
match the originally committed V2 chart/scopes/money-policy evidence digest.

For `RETURN` and `REVERSAL`, the bridge derives a **new** V2 reversal
event ID from the new stock movement's commercial source and calls
`reverse_journal` on the deterministically located original V2 posting.
The reversal's V2 `source` intentionally remains its original source,
because V2 requires the reversal source to equal the original. The new stock
source identity remains recoverable via the deterministic reversal event ID
and the returned bridge result. The host must persist the source-to-reversal
link and proof digest in its trusted **append-only audit** as part of the
same atomic transaction. V2 currently has no native field recording the new
stock reversal source, warehouse, or stock movement date.

The bridge rejects stale revisions, forged company/actor/scope, wrong chart
kinds, mismatched verified invoice/source/amount, cross-project job mapping,
future/closed-period postings, duplicate GL source under another event ID,
nonposting sources with prior financial journals, and a first financial
posting for stock already returned or reversed. The returned candidate
balances exact integer RIAL debits and credits through `post_journal` or
`reverse_journal`.

**Durability cannot be proved by this pure bridge.** SHA256 digest/history
checks only protect against changes relative to a trusted stored revision.
They do not authenticate clients or prevent someone rewriting the entire
persisted history with new hashes.

## Host wiring still required

1. Verify server actor, company, warehouse, item, project/job/task,
   supplier/party, original invoice source and authoritative fiscal date.
   Supply **host-generated** typed proofs, chart, scopes and mappings.
2. In one exclusive SQLite/CAS or equivalent financial transaction, load
   durable inventory and journal heads, validate historical replay, and
   check both revisions. Read stock events from a trusted immutable store.
3. Enforce unique keys on
   `(company_id,stock_commercial_source_id)`,
   `(company_id,stock_event_id)`,
   `(company_id,gl_commercial_source_id)` and
   `(company_id,gl_event_id)` before committing. Supplier invoice uniqueness
   must be independently verified against accounts payable/legacy finance.
4. Apply the stock event and this pure bridge with the actual committed CAS
   revisions. Append any GL lines, proof digest, no-post marker, and
   stock-to-GL trace **atomically**. Any exception must roll back inventory
   and journal together. No host integration or database safety claim has
   been performed in this tranche.
5. Reject attempts to post a priced receipt AP **again** through existing
   TOMAN finance / legacy accounting or a supplier-invoice processor. This
   adapter does not inspect existing TOMAN invoices or financial sources, so
   only the host can enforce global source deduplication.
6. Surface explicit user-visible finance status only after the durable
   transaction succeeds. `NO_GL` must be audited durably even without a V2
   journal line so restarts and late retries cannot hide incomplete work.

The FIFO stock kernel does **not** record business timestamps. Consequently,
the bridge uses the **host-attested posting date** for period checks but cannot
prove that it equals a stock issue/receipt date. The host must validate and
retain the source business date and fiscal-period policy. Cross-process CAS,
lost responses, native UI, LAN, persisted financial posting, real supplier
documents, legacy finance coexistence and integration of cost adjustments
remain unverified.

## Synthetic verification

```powershell
python -m unittest tests.test_ir_inventory_journal_adapter -v
python -m unittest tests.test_ir_inventory_journal_adapter tests.test_ir_inventory_rial tests.test_ir_journal_v2 tests.test_ir_chart_model -q
```

All tests use in-memory synthetic stock/chart/journal objects. No APPDATA,
SQL/Parsian, backup, Git, packaging, release or production state is accessed.
