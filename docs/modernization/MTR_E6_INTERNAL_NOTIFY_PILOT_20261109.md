# MTR E6: internal notice and amendment display (synthetic pilot)

**Worktree baseline:** Madar `32bd8ff`, isolated shared worktree.  
**Decisions:** Refine 6.26 / 6.28 / 6.29; AC-29 / AC-31 / AC-32 and G-01 / G-07.  
**Status:** pure prototype only, **not** the operational Madar/Taraz backend.

## Pure functions

`mtr_internal_notification_policy.plan_internal_notifications(event, recipients, *, scope, seen_event_keys)`

- Requires an upstream authenticated, server-scoped, authorized actor, explicit organization and readable project IDs, known role, trusted dedup snapshot, trusted event, authoritative event revision, and per-recipient same-org/request/project visibility. Unknown roles/ACLs, a stale revision, mixed-tenant batches, or untrusted recipients fail closed.
- For a recognized meaningful request-status change, deficiency assignment, or amendment-status change, returns **plans** addressed only to internal recipients related to that same request and project. It does **not** enqueue, send, persist, retry or log anything.
- All recipients must pass ACL validation even when a different recipient already qualifies. A single cross-organization/unknown-recipient entry rejects the batch, not just the row.
- A supplied previously-seen `event_key` suppresses duplicate notices. The caller must supply **trusted, atomic, event/payload-bound persisted dedup** for actual delivery. This function neither stores keys nor solves partial delivery/concurrent readers or forged replay keys.
- The notice field allowlist is intersected between server scope and recipient grants. Denied status, amendment identifier, deficiency summary or actor fields are returned as `None`, not filled from inaccessible content. The result always has `external_deliveries=[]` and `send_or_resend_performed=False`; no email, SMS, messenger or Taraz resend is authorized.

`mtr_internal_notification_policy.summarize_amendments(original, amendments, *, scope)`

- Requires a trusted Taraz-origin claim for the original official status and explicit same-org/project/read permission. Each amendment must refer to that original, have its **own** ID, status, update timestamp and trusted status provenance. It returns all supplied authorized amendment summaries in order, while preserving the original official status unchanged.
- Only a server-supplied, Taraz-origin reference correlated to the exact amendment with a **source actor**, source-provenance, and correlation flags explicitly verified upstream can appear as a trackable `receipt_reference`. A known unverified reference is withheld; missing/unknown provenance or wrong org/project/amendment/source fails closed.
- `FINANCE_APPROVED`, `FINANCE_REJECTED` and `OFFICIALLY_POSTED` cannot claim a local Madar source. An officially posted amendment additionally needs a trusted **document** reference, not just a transport receipt. The reference is merely displayed; no official ledger or original status is changed.
- Viewer access is restricted by the caller's project and field grants. A viewer may see a permitted status while a denied reference ID/actor is redacted. Unknown or foreign amendment rows reject the entire request to prevent partial disclosure.

## Deliberate boundaries and assumptions

The Python module imports **no Taraz source**, uses no network/filesystem,
does not access user profiles, and contains no clock or database. All input
objects are synthetic or pre-authorized by a hypothetical trusted server.
Boolean `server_*` and `*_verified` claims are **not cryptographic or
identity verification**. Passing `True` in a local dictionary is insufficient
to authorize an operational endpoint or to certify a real Taraz receipt.
Identifier and status names are *pilot schema*, not ratified production APIs.

**Unresolved release gates:** actual Taraz receipt signature/identity and
correlation verification, organization/project authorization in the server,
authorization of sensitive notice content, event version allocation, atomic
dedup and audit history, offline delivery/retention, concurrent status changes,
and full AC/G testing on separate systems. Approval, completion, posting and
receipt remain independent states. Nothing here implements E6 operationally.

## Recorded synthetic test evidence

Run from the isolated Madar worktree using Python 3.12. The executed test was
`unittest discover -s tests -p test_mtr_internal_notification_policy.py -v`
as a subprocess under `safe_test_runner.isolated_environment` with disposable
parent APPDATA/LOCALAPPDATA/HOME/TEMP.

**Result observed:** 18 tests, 0 failures, 0 errors, exit 0. Coverage includes
same-org/project/related recipients, viewer field redaction, unknown role/ACL,
cross-tenant full-batch denial, already-seen event keys, stale revisions,
unknown statuses, deficiency and amendment changes, verified/forged/withheld
references, no original-status mutation, and no network or file I/O.

No existing code, user/finance data, live backend, logs, installed programs,
Git history or delivery services were modified. No commit/push/deploy.
