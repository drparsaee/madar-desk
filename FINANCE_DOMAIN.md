# Madar finance domain (pure Python, schema v1)

This is an independent domain module, ready for a future Bridge/SQLite adapter.
`finance.py` **does not write files**, read `%APPDATA%`, make HTTP requests,
schedule jobs, send invoices or operate on real Google Drive accounts. The
current native host, LAN handlers, React UI and `data_model.py` are unchanged.

## Boundaries and accounting assumptions

- Currency is **whole tomans**. Amounts stored in the finance snapshot are
  nonnegative Python/JSON integers, at most `10**15` each. The public `amount`
  converter accepts an integer or an ASCII decimal string with an optional
  `.0`/`.00` suffix, using `Decimal` for exact normalization. Floats, booleans,
  negative values, fractional tomans, exponential notation, currency symbols,
  commas, `NaN` and `Infinity` are rejected. Computed sums must also fit.
- **Internal cost never determines sales invoice price.** Project `price`, card
  `cost`, checklist `cost`, and estimated/actual cost snapshots only appear in
  cost reporting. A separate, explicitly entered contract defines customer,
  item descriptions, integer quantity and unit price, fixed discount, tax
  **amount**, advance and whether to create a draft on card completion. No
  tax rate, customer metadata or legal claims are generated.
- The milestone's chosen completion unit is **one task/card**. A trusted host
  must verify a genuine **incomplete → complete** change. Current native
  `status == "done"` is recognized; the future card model may provide
  `completed is True`. The domain additionally validates that the current card
  is completed. It cannot, without the host's before/after records, prove the
  transition itself. Completing a project or billable phase is a future choice.
- One automatic **Draft** invoice can be created per card and contract
  version. Replaying a completion, including the same completion ID under a
  new request ID, does not create another invoice. An administrator may
  explicitly save a new contract version to bill a new completion event.
- No automatic final issuance. The admin must explicitly request `review`
  then `issue`, which atomically takes the next local sequential invoice
  number. The numbering is project independent and belongs to one finance
  authority/host. This is an **internal** invoice workflow; fiscal or legal
  invoicing requirements depend on jurisdiction and need a separate review.
- Cancellation is an append-only audit event. It never deletes an invoice or
  recycles its number. An invoice with any recorded post-issue payment cannot
  be cancelled by this API; refunds/credit notes are not implemented. An
  issued invoice cancelled here is only internally marked cancelled and does
  not automatically satisfy external accounting obligations.

## Public API and Bridge adapter example

```python
from finance import (
    amount, empty_finance_state, validate_finance_state,
    card_cost_summary, project_cost_summary, invoice_status,
    apply_finance_command, list_invoices, list_finance_ledger,
)

snapshot = empty_finance_state()
assert validate_finance_state(snapshot)

# Inside a Bridge-hosted database transaction/lock, from a verified LAN login:
result = apply_finance_command(
    snapshot,
    {"type": "cost.toggle", "eventId": "ui-action-456",
     "cardId": "example-1", "costEnabled": True},
    actor=session_account["username"],       # NEVER accept actor from the client
    accounts=host_users,                      # LAN account records or trusted local actor
    cards=host_tasks,                         # authoritative current card records
    projects=host_projects,                   # authoritative current projects
    now="2026-10-20T16:00:00Z",               # server clock, timezone-aware
)
if result["changed"]:
    persist_with_same_transaction(result["state"])
snapshot = result["state"]
```

Each mutation returns `{"state": complete_new_finance_snapshot,
"changed": bool, "result": operation_result}`. All inputs remain unchanged.
`eventId` must be stable across retries, unique across commands and stored
alongside the domain state in a durable transaction. Reusing it with different
actor/payload is rejected. A genuinely identical retry returns `changed=False`
and the original result, after rechecking **current authorization**.

### Financial cost fields

`card_cost_summary(card, project, *, override=None)` needs only authoritative
records, and returns `enabled`, `costEnabled`, `estimatedDirect`,
`actualDirect`, checklist lines, `estimatedTotal`, `actualTotal`,
`includedEstimated`, `includedActual`. The `costEnabled` override can be
`true`, `false` or `null`, where `null` inherits `project.costEnabled`.
Disabling a field preserves the direct and checklist amounts, but the values
are excluded from `included...` project totals. An explicit `true` on one
card enables cost even when its project default is false.

The fallback source is existing `card.cost` and each legacy
`card.checklist[].cost`, both **estimated**. Realized/actual costs default
to zero until explicitly recorded. When named `card.checklists` exists and is
nonempty it is authoritative; the legacy flat checklist is ignored to avoid
double counting duplicated migrated items. Stable cost line IDs are
`groupId:itemId`, or `checklist-legacy:itemId` for flat legacy checklists.
Legacy items missing an ID are referred to as `checklist-legacy:legacy-N` by
index; assign stable item IDs in the host before recording a cost override.

`cost.set` accepts a full cost snapshot, including all user-assigned values:

```json
{
  "type": "cost.set", "eventId": "edit-cost-81", "cardId": "example-1",
  "value": {
    "cardId": "example-1", "costEnabled": true,
    "estimatedDirect": "20000.00", "actualDirect": 18000,
    "items": [
      {"id": "checklist-legacy:step-1-0", "estimated": 4000, "actual": 3700}
    ]
  }
}
```

Checklist overrides must reference a known current checklist item. Other
items retain their original estimated values and zero actual cost. A
`cost.toggle` command accepts only `cardId`, `costEnabled` (`true`, `false`,
`null`) and saves existing amounts intact. The host's existing native v0.2.2
card fields remain separate until an explicit migration/adapter is wired.
Previously recorded checklist costs remain in the financial report after an
item is deleted, flagged `orphaned: true`; new `cost.set` operations cannot
introduce unknown item IDs. This keeps recorded actual expenses auditable.

`project_cost_summary(state, project_id, *, actor, accounts, cards, projects)`
aggregates enabled cards in that project. Cost reporting doesn't invoice
anything and does not automatically calculate income or profit.

### Explicit card contract and invoice amounts

`contract.set` is an admin operation. It accepts an explicit contract assigned
to one `cardId`, with no inferred values:

```json
{
  "type": "contract.set", "eventId": "contract-42", "cardId": "example-1",
  "sale": {
    "customer": {"name": "Customer Ltd", "reference": "C-12"},
    "lines": [
      {"id": "design", "description": "Packaging design", "quantity": 2, "unitPrice": 100000}
    ],
    "discount": 10000,
    "tax": 0,
    "advance": 30000,
    "autoInvoice": true
  }
}
```

Required values are deliberate user input, including `tax: 0` where no
explicit tax charge was entered. The service does not compute tax percentages.
The saved sale snapshot includes exact `subtotal`, `total`, `due` and line
totals, calculated as:

```
subtotal = sum(quantity * unitPrice)
total = subtotal - discount + tax
due = total - advance
```

`0 ≤ discount ≤ subtotal`, `0 ≤ advance ≤ total`. A new `contract.set` command
appends a version to `contracts`, switches `activeContracts[cardId]` and leaves
existing invoices untouched. Customer/name/reference data are immutable in an
already created invoice.

After a verified completion transition, the **host** calls:

```python
apply_finance_command(
    snapshot,
    {"type": "completion.record", "eventId": "completion-change-123",
     "cardId": "example-1", "completionId": "task-completed-event-123"},
    actor=session_user, accounts=accounts, cards=updated_cards,
    projects=projects, now=server_iso_timestamp,
)
```

`completionId` is a durable, globally unique **business completion ID**, not
an arbitrary random key regenerated after reconnect. `completion.record`
returns only `invoiceCreated` and `duplicateCompletion`. Editors can register
the completion in an authorized project without access to invoice amounts;
viewers cannot. The trusted host must deduplicate and verify the actual task
transition before publishing this event. The domain only creates a Draft if
the card's active explicit contract has `autoInvoice=true`.

### Invoice lifecycle (append-only)

| Command | Inputs | Preconditions | Result |
| --- | --- | --- | --- |
| `invoice.review` | `invoiceId` | Draft; admin | Review |
| `invoice.issue` | `invoiceId` | Review; admin | Issued, unique sequential number |
| `invoice.payment` | `invoiceId`, `amount` | Issued; admin; `0 < amount ≤ remaining` | Records payment, Paid when balance zero |
| `invoice.revise` | `invoiceId`, full `sale`, nonempty `reason` | Draft/Review; admin | Creates new Draft, old status Superseded |
| `invoice.cancel` | `invoiceId`, nonempty `reason` | Draft/Review/Issued, no additional payments; admin | Cancelled; number retained |

Stored invoice records are **immutable**. Corrections append a replacement
invoice with `supersedesId`, preserving the previous customer, prices and
audit evidence. Revisions to Issued/Paid/Cancelled invoices are intentionally
blocked. A revised invoice starts in Draft and requires new review/issuance.
Issuance consumes a sequence number only once, even after process restart,
provided the whole state and receipt are committed atomically.

`invoice_status(state, invoice_id)` derives statuses Draft, Review, Issued,
Paid, Cancelled, Superseded, sequential `number`, `paidAfterAdvance` and
`remaining` from the append-only ledger. A fully covered advance can leave a
zero `due`; settlement of that case would need an explicit policy before
connecting real accounting workflows.

## Authorization and privacy

The host supplies the authenticated account objects from `lan.py`:

- `admin`: create/edit contracts, edit costs, review/issue/revise/cancel and
  record payments, and read financial reports. Existing LAN admins are global.
- `editor`: may register a verified task completion in a project they can
  access; cannot read costs or invoices by default. `financeEdit: true`
  granted **server-side** additionally permits cost recording and financial
  reads within authorized projects. This extension is advisory until added to
  server-side trusted account management.
- `viewer`: no mutations. Only explicitly trusted `financeView: true`
  enables financial read access within authorized projects.

`list_invoices(state, *, actor, accounts, cards, projects, project_id=None)`
and `list_finance_ledger(...)` filter by both role/financial grants and
project scope, returning detached copies. A specified inaccessible project
raises `PermissionError`. The host should expose only these filtered views,
never the full finance envelope, raw receipts or all-project reports.

## Integrity, migration and remaining integration work

`empty_finance_state()` initializes:

```json
{
  "schemaVersion": 1,
  "cardCosts": {}, "contracts": [], "activeContracts": {},
  "invoices": [], "ledger": [], "receipts": {},
  "completionIds": {}, "nextInvoiceNumber": 1
}
```

Every domain mutation adds an audit event with identity, action, project,
card, timestamp and relevant change. Events form a SHA-256 `prevHash`/`hash`
chain, and immutable invoice snapshots carry a `snapshotHash`. This catches
accidental/inadvertent mutations; a hostile database administrator could
recalculate hashes, so database permissions and protected append-only storage
remain necessary. `validate_finance_state` checks the schema, monetary
snapshots, references, uniqueness of issue numbers and integrity hashes.

**For integration, the prime/Bridge owner should:**

1. Put finance state in a **host-authoritative SQLite transaction** or an
   atomic versioned snapshot. Pair finance event receipts, ledger, generated
   invoice and card completion state in one transaction; use unique DB indexes
   on event IDs, completion IDs, issued numbers and immutable invoice IDs.
   Only after durable commit may a client receive success.
2. Authenticate the actor with the current session; derive `now` on the host.
   Verify the actual card transition and permissions under the same lock.
   Never let a client submit its own `accounts`, `cards`, `projects`, ledger,
   snapshot hashes, invoice number or entire finance state. Make finance
   account permission flags admin-managed and persist them securely.
3. Persist the finance state, backup/restore compatibility, versioned
   migrations and account permissions; prevent old JSON imports from silently
   discarding finance data. Account data currently has separate backup needs.
4. Connect separate authorized finance commands and filtered reads to Bridge
   and then the UI. Do **not** expose hidden amounts through existing LAN
   task/project state responses: `project.price` and `task.cost` currently
   travel inside the general task state and need appropriate server-side
   redaction before claiming financial secrecy for a viewer/editor.
5. Establish customer/legal invoice fields, required tax details, payment
   reconciliation and rules for advances and fiscal cancellation before
   issuing official documents or posting to real bookkeeping systems.

**Tests:** `python -m unittest discover -s tests -p test_finance.py -v`.
They use only in-memory fixtures and do not touch real APPDATA or issue actual
invoices. They verify exact decimal/integer conversion, card opt-in, legacy
and named checklist costs, authorization, limits, retry/idempotency, draft
generation, numbering, payment, correction/cancellation, immutable snapshots
and ledger tamper detection. Host persistence, simultaneous users, OAuth,
physical two-PC testing and real invoice delivery are **not** proven here.
