# E2 receipt authority: reproduced flaw and owner-approved fail-closed fix

Date: 2026-11-10. The investigation first inspected source READ-ONLY and
reproduced the original flaw below. After explicit prime/owner authorization,
the fix modified **only** `mtr_host_request_store.py`, the targeted existing
`tests/test_mtr_host_request_store.py` and `tests/test_mtr_e2_dispatch_gate.py`,
this worker's **NEW** receipt-boundary test and this **NEW** document. No
`lan.py`, other source or other worker's tests were edited.

**Current code state: fail-closed.** `record_query_result` retains its legacy
signature but unconditionally raises `PermissionError` before any write,
including for fabricated `taraz_adapter` principals and the literal Boolean
`verified_by_adapter=True`. No official Taraz finance-receipt verifier exists
to justify a positive path. The signed peer's metadata-only acknowledgement
does not establish an official financial receipt.

## Original defect, confirmed before fix; reachability qualification

**Pre-fix high-risk in-process trust-boundary weakness** in
`HostRequestStore.record_query_result`, **not confirmed remotely exploitable**.
The previous method in `mtr_host_request_store.py` lines 589–672 used only
`verified_by_adapter is True`, plus a `TrustedPrincipal` object whose
`taraz_adapter` role, `mtr.receipt_ingest` capability and authenticated flags
are caller-constructible. It then parsed *unverified* caller-provided JSON
with `"source":"taraz"` and checks the local original request/org/project/
revision/payload SHA/sendKey before persisting a claimed receipt. No Taraz
signature, independent original finance authority or authenticated receipt
transport was verified by that implementation.

Before the fix, on a **new, disposable TemporaryDirectory SQLite database**, a manually
authorized synthetic request is followed by an in-process, deliberately
fabricated `taraz_adapter` principal, `verified_by_adapter=True` and a
fabricated matching observation. The public method durably recorded:

- `receiptState: "received"`, a fully invented receipt ID, and
  `nextAction: "recover_existing_receipt_only"`;
- a second test can record `"not_received"` with
  `nextAction: "same_key_replay_only_after_authoritative_query"`;
- given this false local status, `OneShotDispatchGate.observe_received`
  can promote its synthetic gate state to `"observed_received"` when invoked
  by an authorized in-process caller. The dispatch permit remains consumed.

The previous `record_query_result` rejected `False`, `0`, `1`, `None`,
incorrect actor role, and mismatched request/digest/sendKey, but those checks
**do not authenticate receipt provenance**. Knowledge of bound local metadata
and access to an internal Python caller are material preconditions to this
reproducer. The test does not establish that an arbitrary external client
possesses either.

**This is false local confirmation, not a created Taraz financial receipt.**
In all reproduced cases `financialEventCreated=False` and
`transportCalled=False`. No finance books or real Taraz systems were touched.

## Public-route and integration reachability

Static source inspection (not a running HTTP penetration test):

- `lan.py` lines 1601–1611, 1660–1672, 1803–1814 permit only the
  TLS-mounted `/api/mtr/v2/prepare`, `/api/mtr/v2/manual-send` and
  `/api/mtr/v2/status` routes. Unrecognized `/api/mtr/v2/*` paths return 404.
- `mtr_lan_finance_adapter.py` lines 165–181 uses the exact
  `_ROUTES = frozenset({"prepare", "manual-send", "status"})` contract and
  does not invoke `record_query_result`.
- A repository-wide search of Python source for `record_query_result(`
  found its method definition and calls in the *existing synthetic test*
  modules `test_mtr_host_request_store.py` and
  `test_mtr_e2_dispatch_gate.py`, but no deployed/production integration
  caller. Dynamic `getattr`, future mounts, outside-process callers or
  unsurveyed code are **not** eliminated by this source search.

**Pre-fix risk classification:** High severity *if internal Python code, a future
adapter mount or a compromised plugin can invoke this method with source
metadata*. No demonstrated remotely exploitable route in the inspected
current MTR LAN router. Do not label this an internet/LAN RCE, live receipt
fraud or an official Taraz ledger mutation.

## Current mitigation and future official-receipt design

1. **IMPLEMENTED:** Immediate fail-closed default. Reject `record_query_result` promotion
   of `received`/`not_received` without a new, trusted proof-verification
   path. The caller-supplied `verified_by_adapter` parameter is retained only
   for call compatibility and grants **zero authority**: even `True` is
   rejected before SQLite write. `unknown` metadata remains available in
   the separate signed-query journal without declaring an official receipt.
2. **PENDING:** Introduce an authoritative receipt verifier. Trust a distinct,
   explicitly configured *official Taraz finance-receipt* signing
   authority and verify its cryptographic envelope or a strictly authenticated
   finance API response before issuing a host-only `VerifiedFinanceReceipt`
   witness. Bind signed intent to original request, tenant, project, revision,
   payload digest, sendKey, receipt ID, financial document identity,
   signing key ID, expiry, and a one-use nonce. Keep keys and decoded
   sensitive payloads off browser and LAN API surfaces. Reject replay,
   mismatched tenant, stale/revoked authority and unknown key IDs.
3. **PENDING:** Bind the witness to the storage operation. Accept only a
   **store-instance-bound, single-purpose and consumed** trusted witness,
   verified by the store itself within its transaction. A plain
   `TrustedPrincipal`, `role="taraz_adapter"`, arbitrary dict or boolean
   is never sufficient. Reject when no verifier is bound, including in
   synthetic mode except for an expressly separate test-only fixture.
   Lock down any caller API that could mint witnesses; do not use an
   exposed `verified=True` or `is_official=True` toggle.
4. **IMPLEMENTED for operational surfaces:** Pre-verifier historical received/
   not_received rows remain stored and are validated for integrity, but public
   reads/snapshots expose only `receiptState=unknown`, `receiptId=null`,
   `receiptVerification=UNVERIFIED`, `historicalReceiptQuarantined=true`,
   `canAutoRetry=false` and a query-first/no-retry action. Gate `reserve_once`
   rejects these quarantined rows even when the public state reads unknown,
   and `observe_received` cannot transition without a future independent
   official Taraz receipt authority. Historical gate `observed_received` is
   surfaced only as `quarantined_unverified_receipt` while the consumed slot,
   raw SQLite rows and forensic audit remain unchanged.
5. **PRESERVED:** Separate peer-metadata acknowledgement from financial receipt. The
   current synthetic Taraz peer signed query only indicates metadata
   `received`/`unknown` and is **not** sufficient to mint a finance receipt.
   Do not reuse the peer HMAC key or F1 `OUTBOX_RECOVERY/GATE_RECOVERY`
   proofs as an official Taraz finance-receipt credential.

Targeted regression now covers constructed `TrustedPrincipal`,
`verified_by_adapter=True`, forged `received`, `not_received`, `unknown`,
matching and mismatching metadata, and gate reconciliation. The former
intentional `@expectedFailure` is now a **normal passing denial assertion**.

**Important historical integrity note:** tests still inspect synthetic *historical*
receipt rows, explicitly seeded using test-only direct SQLite inserts in the
two targeted test modules. This preserves integrity/backup/one-shot-gate
regression without a production `allow_unsafe` switch or pretending to
possess authentic Taraz receipts. These old untrusted records remain available
for *internal forensic validation* but are explicitly quarantined from
operational receipt confirmation and resend guidance. No live data scan,
deletion, migration or independent financial verification was done.

### Historical quarantine follow-up (owner-approved)

The `HostRequestStore._get` / `_validate_row` /
`_validate_observations` integrity checks still inspect every raw historical
observation and detect tamper; neither SQL schema nor stored records were
rewritten. The operational `HostRequestStore._as_status` projection masks
**both** `received` and `not_received` historical claims. This applies to
`receipt_status`, `request_snapshot`, `recovery_snapshot`, prepare/send return
values and downstream consumers of the projection. Ordinary `unknown`
remains `unknown` with `historicalReceiptQuarantined=false`.

The gate's `status`, protected `recovery_status` and internal reservation
responses label all receipt evidence as `UNVERIFIED`. A raw old gate
`observed_received` row is rendered `quarantined_unverified_receipt` with
`receiptId=null`, `mustQueryFirst=true`, `mayDispatch=false` and no retry.
Other gate states retain their physical state label, and take the quarantine
flag from the independently checked outbox snapshot. Critically,
`reserve_once` refuses historical quarantined evidence **before granting the
first slot**, preventing a masked `received` or `not_received` observation
from accidentally re-enabling dispatch. `observe_received` performs the
existing actor/session/project/role and CAS checks but always denies a new
confirmation while independent official finance attestation is unavailable.
Both stores' scoped forensic `audit_events` preserve raw historical event
actions and validated details, but explicitly label each returned event
`receiptVerification=UNVERIFIED`, `officialTarazReceipt=false`.

Synthetic negative tests now cover historical `received` and `not_received`,
masked status across read/restart/backup, a preexisting `observed_received`
gate row and its intact audit chain, historical data before reservation,
ordinary `unknown` preserving one first reservation, and actor ACL denial.
No test-only production flag and no official finance mutation were introduced.

```powershell
py -3.12 -B -m unittest -q tests.test_mtr_receipt_authority_boundary_20261110 tests.test_mtr_host_request_store tests.test_mtr_e2_dispatch_gate
# 71 tests, OK, 8.977s, exit 0 (after audit labeling change)
```

The broader synthetic E2 source integration was also run (before the final
additive forensic audit labels) with the explicit detached Taraz source
`D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109`: 168 tests, OK,
108.280s, exit 0, covering receipt-boundary, outbox, one-shot gate, LAN
finance adapter, recovery security, query observation journal, host principal
provenance, signed host-peer pilot and host-journal boundary. Only the targeted
71-case suite was rerun after the final audit-label addition.

**Release limitations:** This is operational quarantine, not a cryptographic
attestation or historical-data cleansing. Privileged SQLite/host-process
tampering, forensic data retention policy, verification of any actual live
pre-fix records, future signed official finance receipts and production
rollout are outside this scoped synthetic QA. New `receiptVerification` and
`historicalReceiptQuarantined` response fields are additive; the gate
`state="quarantined_unverified_receipt"` replaces the misleading public
historical `observed_received` label and may require downstream consumer
review. No automatic resend is authorized by any of these status projections.

## Reproduction, post-fix tests, and limits

```powershell
py -3.12 -B -m unittest -v tests.test_mtr_receipt_authority_boundary_20261110
# Pre-fix: 7 tests, OK (expected failures=1)
# Post-fix: 8 tests, OK, with zero expected failures
py -3.12 -B -m unittest -q tests.test_mtr_host_request_store
# 34/34 OK
py -3.12 -B -m unittest -q tests.test_mtr_e2_dispatch_gate
# 20/20 OK
py -3.12 -B -m unittest -q tests.test_mtr_receipt_authority_boundary_20261110 tests.test_mtr_host_request_store tests.test_mtr_e2_dispatch_gate tests.test_mtr_lan_finance_adapter tests.test_mtr_e2_recovery_security_20261110 tests.test_mtr_e2_query_observation_journal
# 109/109 OK, 45.725s, exit 0
```

The pre-fix characterization deliberately used one `@expectedFailure` to
expose a genuine defect, not falsely report a secure contract. Under the
owner-approved fail-closed implementation, **all eight security tests now
pass normally**. The included historical-row tests demonstrate storage
consistency only; they cannot certify any official Taraz finance receipt.
All generated receipt IDs, organization IDs, accounts, credentials and
databases are synthetic.
No actual LAN route was invoked, no real network/finance/Taraz/profile was
accessed, and no commit, push or deployment occurred.
