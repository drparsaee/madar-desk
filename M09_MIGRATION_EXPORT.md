# M-09 Migration Freedom: portable operational export

## Implemented scope (2026-10-21)

Pure JavaScript at `src/migration_export.js`, tested with `tests/migration_export.test.cjs`.
No disk, browser, LAN, SQLite, native host or production integration is performed
by this module. It is an independent API for Prime to wire behind the existing
authorized read/export and user-confirmation flow.

**Format:** `madar-operational-portable`, `schemaVersion: 1`,
`sourceModelVersion: 1`, `scope: "operational-subset"`.
Deterministic UTF-8 JSON with bounded 12,000,000-byte source and output payloads,
stable top-level record sorting by ID, and preserved list/checklist order. The
format is readable JSON with strict inbound key/type/reference validation.
Records carry their own IDs, references, and column metadata. There are no
timestamps generated during export, no hidden connection to host services and
no filesystem paths used or created.

Included data:

- Global stages and priority definitions.
- Workspaces (ID/name/archive state), project ID/name/color.
- Boards, their workspace/project references, column definitions, labels and
  archival state.
- Card ID, board/project/list and legacy global status, title, description,
  priority, due date, text labels/label IDs, archive/delete flags, task ordering,
  estimated/actual minutes and task timestamps.
- Legacy flat checklists and named checklists with item IDs, text and
  completion flags. Checklist costs are explicitly omitted.
- Optional host-provided **metadata-only** attachment manifest:
  `id,cardId,projectId,filename,mime,size,sha256`.

Not included: **all financial amounts, cost configuration, contracts, invoices,
balances, accounting ledgers, payments, approvals, cost on checklist items,
LAN users/roles, passwords, access tokens, auth/session records, connection
settings, shared Windows paths, binary attachment files, comments, reports,
custom field values/definitions, templates, automation, extension data and
unrecognized properties.** These are represented as explicit scopes in
`lossReport.omitted`. `excludedPropertyOccurrences` counts fields excluded
from the operational projection, including nested fields. It is **not** a
count of records/bytes lost and cannot by itself establish completeness.
For omitted scopes with no evidence available, `presence: "not-inspected"`
means **unknown**, not absent.

If any meaningful cost/finance field is detected in the source, export **throws**
until `acknowledgeFinancialExclusion: true` is passed. This flag only records
the caller's explicit choice to create an incomplete **operational** export.
It never creates or authorizes a finance backup. The host must offer its
separate authorized full backup, preserve all financial records, and inform
the user that this JSON cannot recover the ledger. A financial field hidden
inside an unfamiliar extension may not be recognized by the guard; it is still
excluded by the strict export allowlist and contributes to omission counts.
Users must review free-form titles/descriptions/filenames before sharing:
these fields may contain manually entered sensitive information.

Attachments are **never bundled**. `metadataCoverage:"not-collected"` means
the caller provided no metadata. `"caller-provided"` means the manifest has
one or more records; this library cannot verify that the host gave every
attachment or that any referenced file exists. This is not a backup or a
binary checksum verification. For full recovery use the host's separately
controlled attachment backup/restore.

## Integration contract for Prime

```js
import {
  previewPortableExport, createPortableExport, portableJson,
  portableTasksCsv, inspectPortableExport, importPortableSubset
} from './src/migration_export.js';

// 'state' must be an authorized, consistent, already normalized Madar v1
// snapshot (projects, boards, workspaces, stages, tasks). The host should
// ensure the viewer can export all records included in this snapshot.
// Optional attachments come from authorized per-card attachmentList calls.
const preview = previewPortableExport(state, {attachmentManifest: metadata});
// Show preview.omitted, excludedPropertyOccurrences, and sourceCounts to user.
// If preview.financialDataPresent: show separate-backup requirement and gain
// explicit acknowledgement of missing finance scope before continuing.
const bundle = createPortableExport(state, {
  attachmentManifest: metadata,
  acknowledgeFinancialExclusion: userAcknowledgedMissingFinance
});
const jsonFileContents = portableJson(bundle);      // UTF-8 .json
const csvTaskContents = portableTasksCsv(bundle);  // UTF-8 .csv with BOM

// Read-back/preview. These functions are pure and fail closed on bad inputs:
const inspection = inspectPortableExport(jsonFileContents);
const isolatedState = importPortableSubset(jsonFileContents);
// isolatedState is safe to pass to host-native validate_plus for further review.
// DO NOT assign it over the existing state or run live restore directly.
```

The module intentionally does not perform identity remapping or live-state
merging. A later host-controlled import workflow must obtain explicit
import permission, validate the isolated state against the native model,
display losses, create a separate full backup if restoring over existing
content is authorized, and either reject collisions or implement a reviewed
collision-safe remapping scheme. In particular, `importPortableSubset()`
creates new defaults for all financial data and must never replace a live
financial ledger or an existing app state. No financial restoration API exists
in M-09. Trello JSON import remains in `src/trello_import.js`; M-09 accepts
the documented Madar portable schema rather than Trello export JSON.

The optional CSV contains flat task columns only. Quoting handles commas and
line breaks, and spreadsheet formula-leading cells are prefixed with a single
quote. CSV is **not** a lossless or authenticated import path and does not
contain nested checklists or attachment manifests. A SHA-256 string in the
manifest is copied from host metadata, not recomputed from blob bytes.

## Validation evidence and limitations

Focused command:

```powershell
node --test tests/migration_export.test.cjs
```

Tests cover deterministic JSON, stable sorting, explicit loss report, finance
acknowledgement, structural exclusion of known financial/credential fields,
attachment metadata/no bytes, malformed versions and references, input
bounds, CSV quoting/injection defense, and JSON subset round-trip through
the existing Python `data_model.validate_plus` validator.

This worker has not wired the module into `src/App.jsx`, `native_app.py`, the
real app export UI or LAN permissions. No real attachments, real financial
records, production accounts, APPDATA, Drive or two-machine flows were
accessed or tested. A successful unit round-trip is not evidence of
full-data migration, full recovery or parity with Trello.
