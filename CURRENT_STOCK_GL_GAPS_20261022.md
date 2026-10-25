# Madar Desk: actual stock-to-GL host gap (2026-10-22)

## Evidence boundary

This is a read-only code-path audit by Prime after saved worker-12 could not
resume. It is **not** a successful mounted integration, a release test, or
evidence from live company records. Searched the current `app_storage.py`,
`native_app.py`, `lan.py`, `finance.py`, `accounting_service.py` and
`src/accounting_workspace.jsx` for `ir_inventory_rial`,
`ir_inventory_journal_adapter`, `apply_inventory_gl`,
`InventoryGLBridgeResult`, `stockCommand`, `inventoryCommand`, and
`StockAuthority`. All six yielded **no references** to those symbols.

## Existing functionality, not to rebuild

- `ir_inventory_rial.py` provides a pure replayable FIFO stock domain.
- `ir_inventory_journal_adapter.py:283+` supplies `apply_inventory_gl`
  with host-verified stock, journal, chart, scopes, accounts, inventory and
  journal revisions, and optional verified settlement evidence.
- Pure mapping documents GRNI/AP for priced receipt, COGS/WIP for issues,
  no GL for costless receipt/transfer, and traceable reversal. Unsupported
  adjustment policy fails closed.
- `app_storage.py:489+` has a real SQLite BEGIN IMMEDIATE revision-CAS
  bundle commit, but current schema has only tasks/collab/finance/outbox
  and optional automation. There is no durable stock domain attached to
  that same atomic bundle.

## P0 blocking integration facts

1. **No trusted stock write route:** neither `native_app.py` nor `lan.py`
   authenticates and submits a stock movement to the FIFO kernel.
2. **No stock persistence:** current `UnifiedAppStorage` validates only
   existing domains; it cannot atomically store a revised `InventoryState`
   alongside the RIAL finance journal.
3. **Missing host proofs:** genuine company/project/warehouse/item/party,
   fiscal period, chart account mapping, supplier invoice evidence, and
   commercial-source uniqueness are not resolved at an authenticated host
   boundary for inventory.
4. **Dual-post risk:** the existing supplier purchase adapter and a future
   inventory AP bridge must not both recognize the same commercial bill as
   payable. GRNI-to-AP and invoice-to-receipt allocation need an explicit
   policy. The pure stock bridge deliberately supports only a single-document
   AP receipt, not multiple receipts against one supplier invoice.
5. **Crash and replay:** the bridge result's journal and stock state must
   be committed in the SAME CAS transaction, with immutable stock-to-GL
   proof, `NO_GL` marker, source uniqueness and rollback on failure.

## Safe next implementation boundary

Design an **opt-in** inventory extension with a strict versioned serializer
and append-only validator; never silently migrate legacy card/item lists into
stock. Implement one authenticated local + LAN command endpoint that derives
all stock scopes from trusted company/project/warehouse mappings, then calls
the pure FIFO and GL adapters. Persist inventory + finance RIAL in one
`UnifiedAppStorage.commit` after comparing both original revisions and unique
commercial source. Reject all financial stock operations when the registry or
stock store is not explicitly initialized and verified. No separate
`RIALJournalStorage` transaction is an acceptable substitute for joint CAS.

### Minimum negative synthetic acceptance tests

- Wrong company, project, warehouse, item, supplier, fiscal period, or actor;
  stale inventory/journal CAS; alternate stock event ID with same commercial
  source; failure after SQLite INSERT but before COMMIT; partial source retry.
- Unpriced receipt/transfer cannot create payable or GL amount; priced
  receipt cannot create AP twice via supplier bill and stock bridge;
  return/reversal preserves link and exact amount; closed period rejects.
- Direct old-client whole-bundle write must not remove any activated stock
  history or inject unpaired valued movement; LAN requests supply intent,
  not trusted chart/scopes or financial posting evidence.

**Status:** Blocked for host integration, not implemented. No real APPDATA,
SQL Server, Parsian backups, Git, or release files were inspected or changed
for this audit.
