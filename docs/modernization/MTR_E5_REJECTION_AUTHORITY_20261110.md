# E5 rejection authority closure (2026-11-10)

## Scope and observed failure

This is isolated source QA in `madar-p2-gantt-notifications-20261107`,
not a LAN or Taraz production exercise. Before the fix,
`AmendmentStore.record_rejection` accepted an in-process caller's
`TrustedPrincipal(role="taraz_adapter", authenticated=True,
session_valid=True)`, `verified_by_adapter=True` and a receipt containing
`verifiedTarazSource=True`. None was independently issued or attested by
official Taraz. A disposable SQLite test showed that these inputs changed
`MANUAL_SEND_INTENT` revision 2 into `REJECTED` revision 3 and appended
`verified_rejection_observed`.

Production source search found no `record_rejection(` call site outside its
definition. The current `AmendmentHostAdapter` command allowlist contains
`create`, `review`, `manual_unsent_intent` and `query`, with no rejection
command; its own host regression checks forbidden rejection actions.
**Observed risk is in-process API misuse**, not a proven remotely reachable
LAN/HTTP exploit.

## Source behavior after closure

- `record_rejection` always raises `PermissionError` while no official,
  independently authenticated Taraz rejection attestation is wired. A caller
  boolean, principal dataclass, receipt fields, stale CAS or replay cannot
  assert rejection or write audit.
- Stored historical `REJECTED` rows remain untouched in SQLite, including
  their original receipt and immutable audit evidence. Operational
  `get_amendment` projects state as `REJECTION_UNVERIFIED` and
  `officialTarazRejectionVerified=False`.
- `audit_events` marks old `verified_rejection_observed` records as
  `historical_rejection_unverified` and hides their previously self-reported
  guidance from the operational response. The original audit row remains
  available for controlled internal forensic integrity checks.
- Public `related_amendments` projects historical rejection status as
  `rejection_unverified`. Internal preview policies conservatively treat it
  as `pending`, requiring normal human acknowledgments and preventing a new
  draft from using unverified history as a confirmed rejected reference.
  This can require re-review for drafts referencing those prior rows.
- Independent user drafts, unsent manual intent, immutable stored rows and
  CAS revisions remain in place. No financial posting or transmission occurs.

## Evidence

Red reproduction, before source fix:

```text
python -m unittest tests/test_mtr_e5_rejection_authority_boundary_20261110.py -v
Ran 2 tests ... FAILED (failures=3)
Observed: forged true/true claims reached REJECTED and appended audit.
```

After the fix and synthetic historical fixture coverage:

```text
python -m unittest tests/test_mtr_e5_rejection_authority_boundary_20261110.py tests/test_mtr_amendment_store.py tests/test_mtr_amendment_host_adapter.py tests/test_mtr_amendment_review_preview.py -q
Ran 90 tests ... OK
```

The historical fixture compares SQL amendment rows and audit rows before and
after public reads and denied replay; they match without migration.
Tests use disposable `TemporaryDirectory` databases.

## Remaining gate

There is no official Taraz attestation integration yet. Pre-fix
`REJECTED` rows must stay **unverified**, even if their stored JSON claims
`verifiedTarazSource=True`; hashes only establish consistency, not issuer
identity. A future authorized host Taraz verifier and separately reviewed
historical reconciliation policy are required before any such event may be
promoted to an official rejection. No deployment or real ledger acceptance was
performed in this task.
