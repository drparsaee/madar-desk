# E2 principal provenance: host-only, one-use recovery capability

**Status (2026-11-10):** NEW security helper and synthetic QA implemented.
**NOT integrated with `HostRequestStore.recovery_snapshot` or
`OneShotDispatchGate.recovery_status`; therefore the earlier F1 direct
`TrustedPrincipal` constructor boundary is NOT yet fixed in production.**

Scope: the isolated shared Madar worktree, Git baseline
`32bd8ffe5ebbb0f4cd5c011c59323ed32f8647ac` at inspection. This worker
owns only NEW `mtr_host_principal_provenance.py`, NEW
`tests/test_mtr_host_principal_provenance.py` and this NEW note. The existing
`lan.py`, outbox, gate, adapter, peer and tests are read-only. There is no
network/HTTP route, real user profile, financial ledger or service activity,
commit, push, or deployment.

## API and intended owner-only use

```python
from mtr_host_principal_provenance import (
    HostPrincipalProvenance, OUTBOX_RECOVERY, GATE_RECOVERY,
)

# Exactly ONCE in the trusted host's composition root, after the real
# LanService exists. This instance must stay private to the host.
authority = HostPrincipalProvenance(service, org_id=server_owned_org_id)

# Host-only, one request: current token is checked against private registry.
sealed = authority.issue_recovery(token, audience=GATE_RECOVERY)

# Future gate read entry point, under service.lock + service.bridge._lock:
principal = authority.verify_and_consume(
    token, sealed, audience=GATE_RECOVERY,
)
# Only THEN use principal with current original request/gate checks;
# never accept a client-provided principal or a boolean verified flag.
```

**Audience constants:** `OUTBOX_RECOVERY = "mtr.e2.recovery.outbox"` and
`GATE_RECOVERY = "mtr.e2.recovery.gate"`. A capability for one audience is
not valid for the other; each verified read consumes one nonce. Issuing one
for the outbox and another for the gate is intentional. The returned
`TrustedPrincipal` contains **only** `mtr.read`, never prepare/manual-send,
receipt-ingest, posting, or replay capability.

`HostPrincipalProvenance` mints a **32-byte OS-CSPRNG secret per host authority
instance**, and `issue_recovery` mints a fresh **16-byte random nonce**. The
HMAC-SHA256 seal covers a canonical, domain-separated encoding of **actor ID,
organization, current session hash, current role, current projects, exact
read-only permissions, active/authenticated/session-valid flags, audience,
issue monotonic time, nonce and version**. The raw secret is held only in the
issuer instance, never included in the proof, outputs, repr or persisted
records. Repr redacts the capability; pickling of the issuer/proof is
explicitly denied. A Python process with arbitrary introspection rights can
access private memory, so this is **not a sandbox against malicious Python
running in the privileged host process**.

## Host provenance and validation

Under the service's existing `lock` and bridge `_lock`, issuance and
verification call `LanService.account_for(token)` and require the returned
account object to be the **same dict object** in the current
`service.users[username]` private registry, not a public-profile copy or
client dictionary. `principal_actor_id(account)` must validate the private
`accountLineage` (missing/legacy/malformed fails closed); duplicate lineage
among registered users denies identity. Current role must be admin/editor,
with `financeEdit is True` for editor, and current saved project IDs are
intersected with current private project grants. Invalid, missing, duplicated
or excessive project metadata fails closed. The principal's identity is a
stable, opaque lineage-derived ID, never username-based.

The verifier recalculates the HMAC with its own per-instance secret using
constant-time `hmac.compare_digest`, enforces a **30-second monotonic TTL**
(future-issued values rejected), checks that the token's **currently
authenticated account, actor, role, projects, session and permissions still
exactly match** the sealed snapshot, and consumes the nonce once. The
in-memory replay journal is lock-protected and bounded to 4,096 currently
unexpired nonce entries, denying **verification** at capacity rather
than allowing unlimited replay-tracking growth. Historical entries are pruned
after TTL. Restart or creation of another authority rotates the secret and
invalidates all older proof objects; caller must obtain a fresh authorized
session and new proof. No raw secret is serialized or logged.

**Same-actor re-login:** old proof cannot validate against the new session
token; a new proof may be minted using the same account's immutable lineage
and current role/project grants. This grants an authenticated *read-only*
recovery capability, not permission to send again. Account deletion and
recreation under the same username with **different lineage** invalidates
the former actor's proof. Legacy accounts without lineage are denied rather
than automatically migrated or mapped to username. Tokens already revoked
by LanService fail its current `account_for` check.

## Remaining integration/security gates (for prime)

1. The real trusted host must instantiate **one** issuer after LanService
   startup, keep it private and hand exactly that instance to the approved
   future outbox/gate adapter. **Binding the issuer to the host's composition
   root is a security requirement**, not a source of authority from the UI.
   Never expose the proof, the raw account registry, or a token/seal-verifier
   as a standalone endpoint.
2. Refactor the **existing** recovery API entry points to require an actual
   `verify_and_consume` call with the host-controlled authority and current
   token **before** reading original request data. Plain `TrustedPrincipal`
   and caller-supplied `verified=True` must not remain alternative paths for
   those protected recovery reads. Simply calling this helper elsewhere does
   not close F1; an in-process caller can still construct a plain dataclass
   against the current APIs. No existing file was changed here.
3. Serialize verification **and** the authorized outbox/gate read under the
   host's existing account+card locks. Otherwise current role/project grants
   can be revoked between verification and the store read. Avoid holding
   host locks across a slow external peer query. Preserve the original outbox
   actor/org/project/original-session/digest/revision/send-key checks.
4. The seal is **one-use**; use a newly issued, correctly audience-bound seal
   for each protected read. Consuming a seal before a failed DB query is
   deliberate fail-closed behavior. Do not add an override to permit its
   replay or silently recover from consumed permits by resending.
5. Only current registry facts are bound, not historical revocation epochs;
   if the same role/project grant is revoked and restored within 30 seconds
   before first verification, this short-lived token alone does not attest
   that intermediate revocation. A separate host-managed authz-epoch check
   would be required if that stronger invariant is mandatory.
6. No cross-instance/persistent replay store exists: changing the per-instance
   key makes all old seals invalid after restart. The prior F2 account-lineage
   migration and existing username-bound outbox records remain a **separate
   fail-closed historical data gate**. Running this helper does not alter any
   historical request or finance status.

## Verification and scope

Test command (Windows PowerShell host with disposable environment variables
`APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`, `HOME`, `USERPROFILE`, and
`PYTHONDONTWRITEBYTECODE=1`, restored/removed afterward):

```powershell
py -3.12 -B -m unittest discover -s tests -p test_mtr_host_principal_provenance.py -v
```

Synthetic coverage includes: OS randomness and bounded nonce, correct
private-registry account identity; forged plain principal, forged MAC and
all mutated actor/org/session/project/role/permissions/flags; wrong audience,
nonce and issue time; one-use replay and concurrent race; same-account
re-login with new session; role/finance/project/session revocation; deleted
and recreated account with same username but new lineage; malformed/duplicate
lineage; fabricated registry copy; old proof rejection after issuer rotation;
short TTL, secret redaction/serialization prohibition, and read-only
audience restrictions, and bounded replay-journal capacity.

**Final observed run:** **23 tests, 23 passed, 0 failures/errors, exit code 0**
on Python 3.12, under a fresh disposable profile and with no real services
or network activity. Static control of the owned new files is recorded
separately from the test result.

These are synthetic unit tests of a NEW not-yet-wired component. Passing them
is not proof of real LanService integration, real host stores, a signed peer,
full E0–E7 QA, network isolation or release readiness.
