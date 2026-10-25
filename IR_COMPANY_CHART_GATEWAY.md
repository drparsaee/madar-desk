# Company → Chart → RIAL V2 Gateway | Independent P0 foundation

**Status:** pure, read-only preflight. The host, SQL, APPDATA, finance data,
release binaries and existing ledger were not changed by this tranche.

Files owned: ir_company_chart_gateway.py, tests/test_ir_company_chart_gateway.py,
IR_COMPANY_CHART_GATEWAY.md.

## Function contract

preflight_company_chart_source(registry, *, authority, company_id, actor_id,
project_id, fiscal_year_id, fiscal_period_id, posting_date, today, chart,
scopes, journal_state, source_kind, references, document_id="", party_id="",
inventory_state=None, inventory_event_id="")

The function returns an immutable CompanyChartPreflight containing exact
company, project, fiscal year and period, date, actor, source kind, derived
JournalSource, registry revision, journal revision and, for stock, inventory
revision. **It is not a permit to commit a journal entry.**

Important trust boundary: VerifiedRegistryAuthority, VerifiedScopes,
CompanyRegistry, ChartSnapshot, JournalState, InventoryState and the
server-verified date must all be created or loaded by the authenticated host.
**Client input must never be promoted into trusted authority objects.**
Python frozen dataclasses can still be constructed by untrusted code;
the datatype alone does not prove authentication or source integrity.

## Verified behavior

Shared checks:

- Canonical RIAL company must be explicitly registered; no inference from
  project names, a flat account, the first matching company, or session UI.
  Only a host-authenticated finance_admin or finance_issuer with a matching
  actor ID can proceed. Finance_reader, missing membership and wrong actor
  are refused.
- Project ownership must agree in both registry assignment and unique
  host-verified project/company pairs. Every project used anywhere in chart,
  V2 task/checklist/independent-source scopes must belong to that company.
  Checklist scopes require a corresponding verified task scope.
- All chart-linked parties and V2 party scopes must match registered parties
  and host-attested party pairs for the same company.
  validate_external_references enforces the complete chart's party/project/job
  ownership references. Host supplies those verified sets; no party record or
  new balance is created here.
- Date must be canonical Gregorian YYYY-MM-DD, no future date; the selected
  fiscal year and V2 journal period must be registered, aligned, open and
  contain the posting date. replay_journal checks V2 history/closure.
- At least two and at most 100 immutable PostingReference records must use
  the source project. Existing validate_posting_reference enforces an active,
  accountable, non-group, nonfrozen and nonarchived chart account, valid
  floating detail, party and cost-center/job/task dimensions.
- Source must be a project-bound JournalSource of independent origin and be
  covered by an exact (project ID, business source ID) pair in host-built V2
  VerifiedScopes. Any matching committed business source in V2 or a company
  POSTED_LOCK is rejected even if the new event ID differs.

**Sale/purchase:** delegates company assignment, finance role, period,
registered party and stable commercial source derivation to the EXISTING
ir_company_registry.verify_sale_purchase_gl_gate. For invoices/bills, the
source party must appear on the supplied posting references, and a line
belonging to a different party fails closed. Host still has to prove that
the invoice/bill really exists, is issuable, matches its source project and
party, and has exact financial content. The gateway does not do invoicing.

**Inventory:** requires recorded PostedMovement inside a replay-validated
InventoryState, using its exact BusinessSource.source_id. No arbitrary client
document ID is allowed. Original stock authority company/source/project,
recorded actor, job and cost-center references must match. Supported
candidate movements: RECEIPT, PRICE, ISSUE, RETURN, REVERSAL. An unpriced
RECEIPT or unsupported type is rejected as a new financial posting.
Actual valuation, FIFO history, AP versus GRNI, issued invoice evidence,
source-specific journal lines, historical returns, reversals and NO_GL
behavior remain the responsibility of EXISTING
ir_inventory_journal_adapter.apply_inventory_gl.

Historical reversal warning: the gateway rejects archived/frozen account
references for new postings. Exact reversals using frozen historical chart
evidence belong to the existing audited reverse_journal path. They must not
be routed as new postings merely to bypass the chart checks.

## Precise host integration sequence

1. Authenticate actor server-side; resolve explicit company/project membership
   from locked host records. Missing or conflicting ownership stops the flow.
2. Read and replay verified company registry, ChartSnapshot, V2 JournalState
   and optionally inventory stock history under one authoritative transactional
   snapshot. Check schema versions and durable expected CAS revisions.
3. Construct VerifiedRegistryAuthority and VerifiedScopes **only from host
   records**, verifying party IDs, all project/company assignments, task and
   checklist scope, and business source identity. Do not allow callers to
   provide lists labeled verified.
4. For sale/purchase, prove the issued commercial document's legal company,
   party, project, date and stable source. For inventory, use committed
   stock event and source authority; do not derive source from event ID.
5. Build accurate PostingReference tuples from approved company chart account
   mappings. Call preflight_company_chart_source and fail closed on errors.
6. Call existing RIAL V2 posting and stock bridge functions to verify journal
   debit/credit equality, numeric precision, actual account roles, exact stock
   settlement and source idempotency. Gateway does not replace these.
7. Commit journal, stock or invoice changes, registry POSTED_LOCK, CAS revisions
   and a unique (company, commercial source) constraint **atomically** in the
   authoritative host. Roll back all changes on any failure. Re-verify the
   inputs when revisions change. Persist an independently inspectable audit.
8. Before importing old TOMAN/Parsian data, inspect the actual source schema
   and approved account mappings. The chart's 2/4/6 code convention is an
   optional NEW internal policy, not verified Parsian v39 compatibility.

## Test scope and limitations

    python -B -m unittest discover -s tests -p test_ir_company_chart_gateway.py -v

Synthetic tests exercise sale/purchase/inventory candidates, exact company
and project ownership, missing/incorrect authentication and finance role,
unregistered party, fiscal year/period/date, wrong chart/journal company,
source idempotency across event IDs, inactive/frozen/archived/group accounts,
untrusted source, unpriced receipt, mismatched original inventory actor,
conflicting inventory dimensions and
orphan task/checklist scopes. Source histories in tests are created entirely
in memory; no real financial transactions or physical data were used.

Final validation evidence:

    python -B -m unittest tests.test_ir_company_chart_gateway tests.test_ir_chart_model tests.test_ir_journal_v2 tests.test_ir_company_registry tests.test_ir_inventory_journal_adapter -q

Result: 122 tests run, 122 passed, zero failures. The gateway's own
15 synthetic cases also passed. This confirms only the tested pure Python
contracts and their observed compatibility with the four neighboring
synthetic suites; it is not a live host integration or security certification.

**Not yet verified:** real host trust construction, SQL atomicity/rollback,
authoritative business-document issuing state, production GL posting,
real APPDATA or Parsian migrations, desktop UI and release acceptance.
