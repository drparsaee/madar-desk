# Parsian BAK migration staging: offline preview only

**Status:** safe, strictly non-destructive **metadata preflight**. Not a
database importer, migration, reverse-engineering of production data, SQL
Server restore, or proof of accounting correctness.

**Authored in this independent tranche:**

- `parsian_migration_staging.py`: standalone pure-Python classification,
  manually supplied schema/mapping validation, reviewed-unit-claim shape
  validation, redacted JSON manifest
- `tests/test_parsian_migration_staging.py`: 23 synthetic unit tests,
  temporary synthetic 512-byte BAK probe compatibility
- This file

The existing `parsian_backup_probe.py`, `accounting_service.py` and other
application/finance sources were **read-only references**. No actual backup,
business data, APPDATA, Git state or release output was inspected or changed.

## What a TAPE signature actually proves

The pre-existing `parsian_backup_probe.identify_backup()` checks that a
selected regular `.bak` appears to have a safe size, then reads at most
**16 bytes** from an *authorized copy*. The prefix `TAPE` is **consistent
with** an SQL Server media backup. It does **not** verify the database is
readable, complete, untampered, unencrypted, belongs to Parsian, contains
the relevant edition's tables, or has any particular invoice/cost/GL fields.

The new `classify_backup_header(header: bytes, *, size_bytes: int)` receives
only a **supplied 16-byte value** and numeric size, no path. The class
`sqlserver_media_header_candidate` is intentionally weak. `TAPE` alone
**cannot parse an SQL Server schema**. Unknown headers are
`unrecognized_media_header`. Both return:

```json
{"schemaParsed": false, "backupValidityVerified": false,
 "canRestore": false, "canImport": false}
```

All public staging operations are pure and expose **no** file-open, SQL
driver, connection string, network, restore, shell command, decoder,
export/import or money writer. This code never knows an original BAK path.

## Exact API contract

| Function | Purpose | Important restriction |
| --- | --- | --- |
| `classify_backup_header(header, size_bytes=...)` | Header candidate and metadata-only classification | Exactly 16 bytes, size between 512 bytes and 50 GiB, rejects non-bytes and bool/float sizes |
| `validate_schema_inventory(inventory)` | Check manually supplied schema/table/column names and primary keys | Names are **not** extracted from BAK; no values/rows, unsafe SQL syntax or arbitrary keys |
| `validate_field_mapping(inventory, mappings, required_groups=...)` | Structural review of source-to-target mapping proposals | Finite target allowlist, unique source and target, no expressions, unit claim required for each money target |
| `validate_currency_evidence(evidence)` | Check a **claim** of reviewed RIAL/TOMAN and reference fields | The caller's `reviewId` and digest are **not authenticated**; `independentlyVerified` always `false` |
| `build_staging_manifest(header, size_bytes=..., inventory=..., mappings=..., required_groups=..., currency_evidence=...)` | Produce redacted, JSON-serializable preflight manifest | `moneyImportAllowed`, `allImportAllowed`, `canApplyToMadar` are **always false** |

The manually supplied inventory shape is exact:

```json
{
  "schemaVersion": 1,
  "tables": [
    {
      "name": "dbo.ExampleInvoice",
      "columns": ["InvoiceId", "PersonId", "DocDate", "TotalInRials"],
      "primaryKey": ["InvoiceId"]
    }
  ]
}
```

The proposed mapping is an **array** of exact four-key records:

```json
[
  {"sourceTable":"dbo.ExampleInvoice","sourceColumn":"InvoiceId",
   "targetField":"sales_invoice.id","sourceUnit":null},
  {"sourceTable":"dbo.ExampleInvoice","sourceColumn":"PersonId",
   "targetField":"sales_invoice.party_id","sourceUnit":null},
  {"sourceTable":"dbo.ExampleInvoice","sourceColumn":"DocDate",
   "targetField":"sales_invoice.date","sourceUnit":null},
  {"sourceTable":"dbo.ExampleInvoice","sourceColumn":"TotalInRials",
   "targetField":"sales_invoice.total","sourceUnit":"RIAL"}
]
```

Allowed draft mapping families: `party`, `sales_invoice`,
`purchase_bill`, `receipt`, `payment`. Target fields are strictly
enumerated in the source module. `required_groups` selects which groups
must have *all* mapped fields. `mappingComplete=True` only means the
**proposal includes the expected names**. It is not evidence of a correct
Parsian-to-Madar semantic mapping, valid foreign keys, tax treatment,
debit-credit integrity or import readiness.

Table identifiers must be `schema.table` with conservative ASCII
characters. Duplicate/case-colliding tables/columns, missing primary keys,
unknown source names, duplicate destination fields, SQL text, data records,
unrecognized currencies and mixed RIAL/TOMAN claims are rejected.
Inventory bounds: at most 128 tables, 256 columns per table and 128 field
mappings. A source may have additional fields in a real schema; this
allowlist is a **staging proposal**, not full schema coverage.

### Unit-of-accounting safety

**Current new standalone Madar accounting uses RIAL; historical existing TOMAN
ledgers retain TOMAN and must not be reinterpreted or imported silently.**
RIAL and TOMAN differ by a factor of **10**. No assumption is made from column naming,
application brand, file extension or arbitrary metadata.

`sourceUnit="RIAL"` inside a field mapping is only a human-supplied
**claim**. The optional review-claim shape is:

```json
{
  "sourceUnit":"RIAL",
  "method":"restored_schema_and_trial_balance",
  "evidenceSha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "reviewId":"review-2026-01"
}
```

Its `evidenceSha256` is syntax-checked, **not** checked against a restored
backup, signed report, trial balance, trusted ledger head or an authenticated
reviewer. Therefore `validate_currency_evidence` returns
`status='review_claim_only'` and `independentlyVerified=False` even for
a well-formed claim. Attempts to supply extra flags like
`{"verified":true}` are rejected.

When a RIAL mapping and RIAL claim are supplied, the preview now prints
`RIAL_identity_requires_reconciliation`; for an explicit TOMAN claim it prints
`TOMAN_to_RIAL_requires_exact_multiply_by_10_per_amount`. Both are **non-executable
conversion requirements**, not evidence that a column in Parsian really uses
the claimed currency. Any future importer must verify source currency from
the detached restored source and reconciled financial statements; it must
fail closed rather than guessing or rounding. Contradictory units are rejected.

No caller-provided assertion, token, digest or mapping is able to flip
the manifest's `moneyImportAllowed=False` value.

## Redacted manifest

`build_staging_manifest` returns only classification, supplied inventory
counts, mapping totals/completeness and destination-field gaps,
proposal-metadata digest, **unverified** currency-claim status, explanatory
conversion-plan text and explicit blockers.

It does **not** return business records, source table/column names, paths,
review IDs, supplied evidence hashes, account names, party names, passwords,
attachments or amounts. The field-proposal digest is a hash of the **declared
mapping metadata**, not the BAK file, not a verified schema identity and
not evidence of authorization. The direct `validate_schema_inventory`
validator returns supplied identifiers for programmatic validation; use the
redacted manifest, not this intermediate structure, in user-facing logs.

The four non-negotiable manifest blockers are:

1. The original backup has **not been restored or schema-verified**.
2. No unit has been independently verified and authenticated.
3. Source-to-target mapping has not been tested against the restored schema.
4. No reconciled trial balance or transactional import/rollback exists.

## Verification and results

```powershell
cd D:\CoS-Test\madar-desk
py -3.12 -m unittest discover -s tests -p test_parsian_migration_staging.py -q
py -3.12 -m py_compile parsian_migration_staging.py tests/test_parsian_migration_staging.py
```

**Result:** 23/23 synthetic tests **PASS**, `py_compile` **PASS**.
Tests include synthetic in-memory TAPE/unknown headers, boundary sizes,
unsafe/malformed schema inventories, SQL-like injected identifiers, row-data
rejection, duplicate mappings, unsupported fields, mixed or unknown units,
forged `verified` claims, RIAL and TOMAN status, mismatch denial, JSON
manifest redaction, absence of file I/O, input immutability and one
**fabricated 512-byte `.bak`** written/read solely inside an isolated
`TemporaryDirectory`. No private BAK is opened or copied.

## Gates before any future real migration

The real importer **does not exist in this tranche** and must not be
advertised as ready.

1. A separately authorized specialist verifies **ownership and provenance**
   of a *copy* without changing the originals.
2. A separate isolated SQL Server environment performs an **authorized
   restore**, checks `RESTORE VERIFYONLY` / actual database consistency and
   enumerates the edition-specific schema, relationships and column units.
   These operations are **not** performed here.
3. A finance owner independently checks RIAL vs TOMAN against source UI,
   vendor documentation and reconciled period totals, including any mixed
   unit fields. A trusted host must authenticate and record this signoff.
4. Review and version a complete mapping for charts, parties, sales,
   purchases, payments, receipts, taxes, vouchers, source IDs and duplicate
   avoidance. Confirm date conventions (Gregorian/Jalali), cancellations,
   reversals, references, opening balances and document numbering.
5. Validate trial balance parity (debits=credits), party AR/AP, bank/cash,
   source-document totals and conversion exactness with explicit exceptions
   and independently reviewed reconciliation evidence.
6. Only then implement a **separate**, approved, transactional importer
   into a cloned empty Madar workspace with CAS, crash rollback, backups and
   replay/idempotency, plus UAT on synthetic/anonymized examples. Never write
   directly into a user's live accounting ledger from a BAK signature.

**Prime integration contract:** keep this module pure and non-authoritative;
never use `mappingComplete` or a review claim as an import permission. The
real application/finance commit path must remain separate and require
authenticated authorization, evidence verification, reconciled numbers,
user approval and transactional rollback. Until those gates exist, show
the preview as **blocked for all imports**, including non-money documents
that could indirectly generate financial entries.
