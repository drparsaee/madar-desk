# Provider-neutral CSV staging (review only)

`provider_csv_staging.stage_provider_csv(spec)` reads explicit exports from an
accounting package chosen by the user. It does not use Parsian, SQL Server,
Madar's operational database, application state, or financial postings.

This independent staging module is **not integrated into the accounting UI**.
Its results are suitable for a subsequent, separate, human-reviewed import
workflow only. No proprietary BAK/MDF/SQLite/accounting application formats
are parsed by this adapter.

## Contract v1

The caller must supply exactly three CSV sources: `parties`, `invoices` and
`transactions`. A source may contain only its CSV header when a group is
empty. The `provider` is a plain label supplied by the user, never an
assumption about the upstream application. `currency` must be exactly `RIAL`.
`TOMAN`, unknown, mixed or inferred units are rejected: no legacy conversion
is performed.

Example using **synthetic** headers (the named files below are placeholders):

```python
from provider_csv_staging import stage_provider_csv

def csv_source(path, mapping, *, value_maps=None):
    return {"path": path, "format": "csv", "encoding": "utf-8-sig",
            "delimiter": ",", "mapping": mapping,
            "valueMaps": value_maps or {}}

spec = {
    "schemaVersion": 1,
    "provider": "my-other-accounting-package",
    "currency": "RIAL",
    "datasets": {
        "parties": csv_source("parties.csv", {
            "id": "PartyNo", "name": "PartyName", "kind": "Role"},
            value_maps={"kind": {"Buyer": "customer", "Supplier": "vendor"}}),
        "invoices": csv_source("invoices.csv", {
            "id": "DocNo", "partyId": "PartyNo", "kind": "DocType",
            "date": "Date", "status": "State", "total": "Amount"},
            value_maps={"kind": {"Sale": "invoice", "Purchase": "bill"},
                        "status": {"Final": "issued", "Open": "draft"}}),
        "transactions": csv_source("transactions.csv", {
            "id": "TxnNo", "partyId": "PartyNo", "documentId": "DocNo",
            "kind": "TxnType", "date": "Date", "amount": "Amount"},
            value_maps={"kind": {"CashIn": "receipt", "CashOut": "payment"}}),
    },
    "expectations": {
        "counts": {"parties": 2, "invoices": 3, "transactions": 1},
        "totals": {"invoice": 800000, "bill": 100000,
                   "receipt": 500000, "payment": 0},
    },
}

preview = stage_provider_csv(spec)
print(preview["counts"], preview["discrepancies"])
# A subsequent preview can detect known source identities without inserting them:
known = [f["identity"] for f in preview["fingerprints"]["invoices"]]
repeat = stage_provider_csv(spec, previous_identity_fingerprints=known)
```

Allowed text encodings are `utf-8`, `utf-8-sig`, and `cp1256`; delimiters are
comma, semicolon, or tab. Headers must be unique, and **every input column**
must either be in `mapping` or named in an explicit `ignoreColumns` list. The
mapping's keys must contain all required target fields and no others. Enum
values must be canonical as documented below, or translated explicitly in
`valueMaps` for `kind` and `status`. No automated value guessing occurs.

| Group | Required canonical fields | Allowed categorical values |
| --- | --- | --- |
| `parties` | `id`, `name`, `kind` | `customer`, `vendor`, `both` |
| `invoices` | `id`, `partyId`, `kind`, `date`, `status`, `total` | `invoice`, `bill`; `draft`, `issued` |
| `transactions` | `id`, `partyId`, `documentId`, `kind`, `date`, `amount` | `receipt`, `payment` |

The date contract is **Gregorian `YYYY-MM-DD` in the years 1900 through 2100**.
This rejects common numerical Jalali dates that would otherwise appear valid
to an ISO parser. A provider that exports Jalali dates needs an independently
reviewed conversion adapter before using this contract. Money must be whole
ASCII digits, without signs, grouping or decimals. IDs must be stable and
unique per group; referenced parties/documents must exist, and receipt/payment
kinds must match the issued document. Invoice totals and settlement amounts are
compared to declared source totals when `expectations` is supplied. Duplicate
identities, overallocations and expected count/total differences are returned
under `discrepancies` with `structuralChecksPassed=False`.

`fingerprints` contains deterministic identity/content SHA-256 digests (scoped
by provider and group) for later duplicate checks. It cannot detect the same
real-world invoice exported with a new unrelated source identifier. The
caller must supply previously seen identity hashes for cross-run detection.

Even a clean preview is **not financial reconciliation**: the CSV schema has
no invoice line items, tax, discounts, returns, cheque/treasury detail,
inventory, fiscal years or double-entry journal balancing. An export may
omit economic events altogether. It is not safe to issue documents or update
ledger balances from these CSV totals. The return value always includes
`previewOnly=True` and `canApplyToMadar=False`; further import needs a
separate reviewed adapter, verified monetary units, full source coverage,
reconciliation and recovery/rollback controls.

Tests: `python -m unittest tests.test_provider_csv_staging -v`.
