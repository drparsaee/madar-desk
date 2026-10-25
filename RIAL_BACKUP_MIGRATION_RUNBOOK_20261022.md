# Madar RIAL / migration / financial backups

## Release scope and limitations

- NEW standalone ledgers use integer **RIAL** (schemaVersion 2). Existing
  TOMAN schemaVersion 1 ledgers remain TOMAN and are never silently recast.
- Task order sales and new step expenses use RIAL; older TOMAN order prices
  may be explicitly converted x10. Legacy financial workspaces and older
  task `cost` fields have not been comprehensively migrated.
- Standalone accounting and the main desktop's standalone financial SQLite
  use validated snapshots at startup, every **300 seconds** while the host
  runs, and mandatory snapshot on normal closing. At most **60** managed
  snapshot files remain; pruning starts only after verifying the new backup.
  Backups are **plaintext** SQLite in the explicitly chosen private data root
  under `standalone-accounting-backups`. Protect with operating-system access
  controls; encrypted offsite backup is NOT implemented.
- A forced process kill, hardware crash, or power failure cannot reliably run
  any exit hook. The 300-second schedule mitigates but does not eliminate loss.
- On a backup failure during normal close, the app attempts to veto closing.
  The actual Windows GUI veto, network and power-loss tests remain unverified.
- This automatic backup policy presently protects **standalone accounting**;
  legacy/unified finance stores and attachments require their separate backup
  workflows and are not automatically covered by this 60-copy rotation.

## Transfer from a previous accounting system

The source's actual SQL schema, currency and balance reconciliation must be
independently verified. A raw Parsian `.bak` **cannot** currently be imported
or restored by these tools; the old proprietary SQL Server data must first be
exported and mapped to the reviewed CSV/JSON contract by an authorized
operator. Never guess units or production account mappings.

All commands below use explicit user-selected OFFLINE synthetic/test paths;
the target must be named `standalone-accounting.sqlite3` and MUST NOT exist.

**Import parties CSV only** (columns `partyId,name,kind`):

```powershell
py -3.12 standalone_legacy_party_import.py --source "C:\example\parties.csv" --destination "C:\new-private-folder\standalone-accounting.sqlite3"
# After preview and approval, append --apply
```

**Import reviewed normalized JSON** (version 1, explicit currency TOMAN or
RIAL, parties, documents, settlements, optional openingDeposits):

```powershell
py -3.12 standalone_legacy_export_import.py --source "C:\example\reviewed-finance.json" --destination "C:\new-private-folder\standalone-accounting.sqlite3" --offline-ack --plaintext-ack
# After reconciling preview and source SHA256, append --apply
```

This importer supports invoice/bill draft/issued, receipts, payments and
explicit opening deposits. It is not a general import of stock, cheques,
multi-company journals, tax rules or unknown software exports. Incoming
historical dates must be canonical Gregorian dates and balances must be
reconciled by an authorized accountant before operational use.

**Convert a portable independent TOMAN v1 backup to NEW RIAL v2**:

```powershell
py -3.12 standalone_rial_migration.py --source "C:\example\standalone-toman-backup.sqlite3" --destination "C:\new-private-folder\standalone-accounting.sqlite3" --offline-ack --plaintext-ack
# Preview first; after reconciliation append --apply
```

The old source and existing financial databases are never overwritten.

## Restore and acceptance

Stop all finance hosts. Choose one validated auto snapshot. Restore only to
a **new, nonexistent** destination using `standalone_accounting_restore.py`
with explicit OFFLINE and plaintext acknowledgement; follow
`STANDALONE_ACCOUNTING_RESTORE.md`. Verify source currency, historical
reconciliation, event revision, invoice totals and counterparties before
moving the recovered DB into any approved production directory.

Release QA is separate from production acceptance. Synthetic tests do not
establish correct real Parsian import, network security, physical backup
durability, Windows GUI dialogs or on-disk encryption.
