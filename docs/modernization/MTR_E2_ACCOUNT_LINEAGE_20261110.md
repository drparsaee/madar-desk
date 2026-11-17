# E2 account-lineage identity pilot, 2026-11-10

**State:** Pure host-only helper implemented and tested. The **prime agent
subsequently wired** it into `lan.make_account`, `lan.upsert_user` and
`mtr_lan_finance_adapter` in the shared worktree; this worker **did not edit
those files**. Neither `HostRequestStore` nor `DispatchGate` was changed by
this worker. No real account was touched, no existing request rekeyed, and no
deployment or migration was performed.

## Purpose and API

Security audit F2 found that E2 outbox actor identity currently compares the
username string, so a deleted account could be replaced with another account
using the same username and gain access to the original request. This module
provides a minimal new identity convention for a later host-owned integration.

`mtr_account_lineage.py` exposes:

* `new_account_lineage() -> str`: generates 16 **OS-CSPRNG** bytes through
  `secrets.token_bytes(16)` and encodes them as **exactly 32 canonical lowercase
  hex characters**. Designed to be called **once** for each newly created
  account by the authenticated host, before durable private registry creation.
  If the RNG returns malformed or zero bytes, the function rejects it.
* `principal_actor_id(account: dict) -> str`: reads ONLY the private
  `account['accountLineage']` field. It rejects absent/legacy, malformed,
  uppercase, hyphenated, non-string, all-zero and conflicting `actorId`/
  `actor_id`/`principalActorId`/`principal_actor_id` override fields. It never
  falls back to `username`, accepts a client-provided principal identity, or
  regenerates missing lineage. It returns `mtr-actor-v1-` followed by the
  SHA-256 of domain-separated 16 lineage bytes, **77 ASCII characters**, below
  the host-store 180-character identifier bound. It contains no username,
  password, session, or raw private lineage.

**Distinct accounts with the same username and distinct lineage values
produce different actor IDs.** Password reset, role/grant change, session
renewal or even username change with the *same* lineage preserves actor ID.
SHA-256 expands a 128-bit random source to a 256-bit digest; **the security
entropy remains at most 128 bits**, not 256 bits.

## Strict provenance limit

This is a **pure** function with no I/O, host secrets, session validation or
registry lookup. It can reject a fabricated actor-ID *override* or a
malformed/legacy lineage, but **cannot cryptographically establish that an
otherwise valid 32-character lineage really belongs to the authenticated
account**. An arbitrary in-process caller could construct a syntactically
valid dict. Treating the dict as host-authoritative is only safe after the
calling host has fetched and authenticated it from the **private registry**.
Do not expose `principal_actor_id` as a client-identity validator or allow
HTTP/JS/desktop payloads to set or overwrite `accountLineage`. The separately
reported F1 forged-`TrustedPrincipal` issue is **not solved** by this helper.

## Integration contract for prime (no changes here)

1. On new-account creation **only**, the host calls `new_account_lineage()`,
   rejects collisions under its private registry lock, persists the lineage
   atomically, and never includes it in public user payloads, telemetry or
   logs. Do **not** trust an account-lineage property in admin/client JSON.
2. On user edits, password resets and login, preserve and read the original
   private lineage; on deletion permanently retire it. On recreation under
   the same username, mint a **new** lineage. Reject unexpected lineage
   changes and duplicate values instead of silently overwriting actor IDs.
3. In host-authenticated `MtrLanFinanceAdapter` prepare, manual-send and
   recovery principal construction, derive `user_id` using
   `principal_actor_id(account)` **from the actual private account record**
   under its authorization lock; then keep the existing original org/project,
   role, read capability, original session, hash, revision and send key
   checks. The store and gate can then bind their existing `actor_id` to
   stable account lineage instead of username.
4. **Existing/legacy accounts and outbox records are not migrated by this
   module.** Missing lineage MUST be denied at the new E2 boundary, not
   silently reissued during a recovery request. A separately approved
   backfilled account-lineage and existing-request migration would require
   durable backup, authenticated account provenance, account-deletion
   tombstones, rollback plan and tenant/project audit. Without sufficient
   historical evidence, old username-bound requests must fail closed.
5. Do not confuse lineage with host authentication. `TrustedPrincipal`
   construction still needs a separately verified host-only provenance
   boundary; cryptographically formatted actor IDs do not authorize actions.

The module creates no routes, services, database objects, imports of the
LanService/accounting stack, user registry writes, network calls or receipts.

## Test evidence

Command run through the Windows development connector with unique disposable
`APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`, `HOME`, `USERPROFILE` and
`PYTHONDONTWRITEBYTECODE=1` (restored after run):

```powershell
py -3.12 -B -m unittest discover -s tests -p test_mtr_account_lineage.py -v
```

Tests are synthetic and exercise random 128-bit generation, malformed RNG
fail-closed, same username/different lineage, password reset preserving
lineage, role/session/name change, strict missing and malformed input,
override rejection, non-dict payload refusal, bounds and privacy, domain
separation, private-field-free error messages, and **no auto-mint on legacy
recovery**. This is not a full-suite, real host registry or E2 operational
test. **Final observed result: 15 tests, 15 passed, 0 failures/errors,
process exit 0.** No existing production file was changed by this worker;
the previously owned security test was subsequently adjusted under prime's
explicit follow-up request. No commit, push or deployment was performed.

**Post-prime integration compatibility:** The prime agent separately assigned
this worker an update to its previously owned
`tests/test_mtr_e2_recovery_security_20261110.py` fixture. Original and
re-login sessions for the *same* synthetic account now share one private
lineage; a newly recreated account with the **same username** has a new
lineage. That case now expects **PermissionError** from the original outbox
and gate recovery readers rather than accepting the replaced identity. The
conditional forged-in-process-`TrustedPrincipal` test still reproduces its
**separate F1 provenance gap**, now using the opaque derived actor ID. The
synthetic host-peer coordinator stub also sets `_journal=None` for the newer
optional observation-journal contract. No network was used.

The two post-wiring target suites were run separately in disposable profiles:

```powershell
py -3.12 -B -m unittest discover -s tests -p test_mtr_account_lineage.py -v
py -3.12 -B -m unittest discover -s tests -p test_mtr_e2_recovery_security_20261110.py -v
```

Observed **15/15 + 15/15 passing, each exit 0**. These are bounded tests,
**not** full-suite, real LanService deletion/recreation, or production
acceptance evidence.
