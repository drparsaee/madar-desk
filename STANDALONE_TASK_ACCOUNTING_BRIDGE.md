# Madar standalone accounting / task bridge

## Invariants (2026-10-22)

Accounting owns its own SQLite store, customers/vendors, invoice issue and
settlement, journal postings and source identity. It operates even if the task
manager does not run. The task manager only plans work and lets the
administrator explicitly request drafts/work intake.

The browser sends only **taskId and expenseId** to the trusted native/LAN
prepare endpoint. On the host, only authenticated administrators can run
this path; the host resolves the canonical SAVED task, validates its
registered customer/vendor, quantity and exact monetary unit, then asks
independent accounting storage to prepare a draft using revision CAS.

The task's **operational description never crosses this bridge**. Only the
task title becomes the short invoice line. Each step has zero or more separate
expense items, each with unique source identity, vendor, quantity and optional
price. Source lookup makes retries idempotent; a transaction spanning both
databases is neither promised nor attempted. The task manager never directly
writes the independent accounting SQLite.

Unpriced contractor jobs have no AP/GL effect. A job can be priced, quantity
confirmed, then assigned with other approved jobs of the **same vendor** to
one batch purchase bill. Only issuing that bill posts AP and GL. Canceling
an unissued batch releases its jobs and keeps history. Ordinary invoice/bill
draft updates preserve an event trail; issued documents are immutable.

An employee-visible task retains the customer display name, execution title
and stage details. The LAN projection redacts the sale price, currency,
accounting party reference, direct costs and all per-stage expense items.
Editor task writes cannot override those host-owned financial fields.

## Currency and export constraints

The independent ledger remains integer TOMAN. RIAL-priced sales work ONLY
if each price is exactly divisible by ten; they are converted on the
authoritative host without rounding. Contractor RIAL costs fail closed.
RIAL V2 is not yet integrated with the standalone database.

Accounting invoices can be downloaded as PDF (raster Canvas JPEG pages) or
PNG (up to 20 rows). A session-editable naming pattern defaults to
madar-{kind}-{id}-{date}; optional {number}. This is a proposal, NOT the
user's unspecified final required naming convention. The browser chooses
the download destination and handles filename collisions; atomic no-clobber
file publication is NOT established. Windows GUI/real print/PDF visual
fidelity remain unverified.

## Remaining release blockers

- RIAL-native standalone journal, advanced multi-company ERP, inventory/cheque.
- Partial quantity mismatch/reconciliation workflow; current mismatch rejects.
- Issued document correction/credit memo UX; draft edits only.
- Registering new parties from the task drawer; currently pre-register in accounting.
- Native Windows GUI, physical LAN security, export collision policy, and EXE
  production acceptance not yet verified.

## Tests and scope

Synthetic tests: tests/test_standalone_contractor_flow.py,
tests/test_standalone_task_prepare.py,
tests/standalone_task_handoff_ui.test.cjs,
tests/standalone_invoice_export.test.cjs.
These exercise a 100-copy book, courier 150000 TOMAN, unknown binder and
laminator prices, vendor batches, duplicate source, CAS, ACL and structural
PDF data. No real APPDATA, production ledger or release binary was used.
