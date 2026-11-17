# MTR E3 | Pure deficiency-referral pilot (2026-11-09)

**Scope:** Independent Python state-transition model, not a connected finance
feature. Conservatively models approved Refine 6.6 / 6.7 / 6.8 and synthetic
AC-08, AC-09 and AC-10 in the isolated Madar worktree. **Prototype, not
operational acceptance.**

## API and behavior

File: mtr_deficiency_workflow.py

- Trusted input snapshots: Principal, Baseline, FinanceReceipt, ReviewCase.
- refer_deficiency: only an authenticated Taraz finance reviewer may refer an
  adapter-verified, matching deficiency receipt to a scoped, active assignee,
  with reason, deadline, missing-field list and audit event.
- resolve_deficiency: only the assigned authenticated user with project-level
  permission may record a correction and result on a newer saved baseline.
  Output is ReadyForManualResubmission: it does not transmit anything.
- authorize_manual_resubmission: requires a separately authorized, explicit
  manual action, exact fresh server baseline revalidation, unused send key and
  acknowledgment if commercial fields remain incomplete. Returns only
  ManualResubmissionIntent, with sent_to_taraz=False and
  financial_event_created=False.

Immutable result models separate DEFICIENCY_ASSIGNED, CORRECTED_READY_FOR_RESUBMIT
and MANUAL_RESUBMISSION_INTENT_ONLY. The receipt must match request ID, org ID,
project ID, baseline revision, SHA-256 fingerprint, expected receipt ID and
generation. Already-consumed/duplicate, pending, stale, mismatched or unverified
receipts are denied. All accepted transitions append actor/timestamp/details
to immutable audit tuples, without rewriting prior states. Cross-user,
cross-organization, cross-project, inactive, unauthenticated and wrong-role
requests are denied. Incomplete commercial information can pass a separate
human warning gate as approved in 6.6; incompleteness is not treated as an
automatic finance-posting permission.

## Mandatory integration dependencies, not yet implemented

1. **Trusted host identity and ACL:** Session authentication, role, active
   membership, organization, project grants and all capabilities MUST be
   derived from a server authority. Client booleans are not proof.
2. **Receipt provenance and enum:** A real Taraz adapter must cryptographically
   or otherwise authoritatively validate receipt provenance, status,
   organization, request and revision. Receipt/source schema and canonical
   digest need agreement with Taraz. This pilot trusts supplied verified
   evidence and cannot independently prove it.
3. **Durable idempotency and CAS:** An immutable Python result alone cannot
   consume an event permanently. Persist receipt consumption, unique send key
   and audit ID with server-side transactions; compare current baseline and
   permissions atomically at the ACTUAL manual send boundary. Two callers
   using the same stale input could otherwise each obtain a local intent.
4. **Persistence and UI:** Persist assignee/deadline/reason/resolution/audit,
   show remaining missing-data warning, separate Resolve from Manual Resubmit,
   and handle re-referral, correction expiry and concurrency explicitly.
5. **Finance boundary:** No ledger, invoice, official account, official
   receipt, server request, network, timer, notification, DB, file/profile
   mutation, or production posting is included. Formal approval is distinct
   from official finance document posting. Installed EXE, LAN/two-PC, receipt
   adapter, failure recovery and finance acceptance remain unverified.

## Synthetic verification

    python -B -m unittest discover -s tests -p test_mtr_deficiency_workflow.py -v
    python -B -m unittest discover -s tests -p test_mtr_finance_workflow_contract.py -v

These exercise only the isolated pure code, not actual Madar or Taraz runtime.
