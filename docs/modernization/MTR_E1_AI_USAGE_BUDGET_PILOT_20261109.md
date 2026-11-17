# E1 AI usage, consent and budget SQLite pilot | 2026-11-09

**Status:** Standalone source-only implementation with synthetic tests. Baseline HEAD: `32bd8ff` in the isolated Madar worktree. Existing `madar_ai_provider_policy.py`, `madar_ai_draft.py`, `lan.py`, UI, stores and runtime code were not edited by this worker.

## Contract

New module `madar_ai_usage_store.py` exports `AiUsageStore(path)`, `AiPrincipal`, `AiUsageError(code)`, immutable `Grant`, `Reservation` and `Usage` read results.

The caller supplies a host-authenticated `AiPrincipal(user_id, org_id, project_ids, role, authenticated, active, manageable_user_ids, approved_cloud_request_ids, proven_local_nonexecution_ids)`. These sets are **host-issued capabilities**, not parsed from a browser or trusted client boolean. A privileged host admin may `set_grant` for an authorized user/project/provider with a compare-and-swap `expected_version`; everyone else is denied. No existing grant means no AI authorization. Providers: `local_ollama`, `openai`, `gemini`, `anthropic`. Cloud is separately disabled by default.

Grant limits are monthly `requests`, `estimated_tokens`, and `cost_micro`, scoped per organization/project/user/provider and UTC calendar month. **Cost micro-units are policy units**, not a verified provider invoice, exchange rate, Rial amount or money transfer. A production pricing adapter must establish one consistent currency/unit and conservative upper bound without exceeding its authorized spend. This SQLite pilot never performs a paid operation.

### Explicit usage lifecycle

1. `set_grant`: trusted admin action with expected grant version, exact provider, expiry and bounded positive/zero integer ceilings.
2. `grant_cloud_consent`: only for a cloud provider; one user-selected request ID and host-origin 64-hex text digest, host-minted request-bound consent capability and `explicit_human_consent=True`. Expiration cannot exceed 15 minutes. Consent binds to the **current grant version**. The host must verify only the explicitly selected text is in scope. The digest must be host-keyed HMAC in production, because even plain hashes can be linkable.
3. `reserve`: `BEGIN IMMEDIATE` checks current role/grant, UTC budget headroom and (for cloud) the unexpired unused, user/project/provider/payload/grant-version-matched consent. Atomically consumes that consent and places a **full conservative request/token/cost hold before any model call**. The request ID is unique within the organization forever; event IDs support exact replay and conflict rejection. It never calls a model.
4. `mark_dispatched`: records a **dispatch intent, not a network call**. Rechecks current grant and its version, and cloud consent expiration. A revoked/modified grant or expired consent blocks dispatch; the hold is not silently released.
5. `complete`: accepts actual token/cost figures **only at or below the reserved upper bounds**. Exceeding an estimate is rejected; the provider could still overbill outside this module. Completing with smaller usage does **not** refund the reserved amount, preventing budget expansion from unverified reports.
6. `cancel`: terminal cancellation; the hold remains consumed, whether the request was marked dispatched or not.
7. `refund_undispatched_local`: the single narrow refund exception. Only a previously cancelled `local_ollama` request, **never marked dispatched**, with a host-issued per-request verified-nonexecution capability and explicit proof may release its hold. Cloud never gets refunds and a refunded request ID remains retired. No automatic fallback or retry.

`usage`, `get_grant` and `read_reservation` expose only caller-scoped metadata. These methods are independent of the user's non-AI manual order-entry flow.

## Privacy, integrity and caveats

The SQLite tables store **opaque user/org/project IDs**, provider identifiers, one-way request content digests, quotas, status, consent/expiry and audit hashes. They do not store raw prompts, conversations, personal names, contact records, API keys, account credentials, invoice data or provider responses. IDs and digests are still potentially linkable metadata: host scoping, private file permissions, encryption, retention and redaction are required before production. `ai_audit` has append-only UPDATE/DELETE prevention triggers, which cannot prevent a privileged SQLite/schema owner from tampering.

All transactions use `BEGIN IMMEDIATE`, unique event/request IDs, CAS versions and strict bounded values. A repeat returns a no-op replay; reuse with different request data fails. Caller-supplied times must originate from a trusted host **UTC clock** and never from client timestamps. Wall-clock rollback protection and invoice settlement reconciliation are **not** provided. Host must serialize exactly-once transport dispatch separately: an idempotent reservation/dispatch receipt is not permission to call a cloud provider again.

This module is not attached to MadarHost or the native app. No actual BYOK key, provider call, model download, paid spend, real user profile, finance ledger, live authorization, multi-device/UI test or installation occurred. `madar_ai_provider_policy.py` remains a separate pure privacy gate, not silently bypassed or fused by this store.

## Synthetic validation

Command: `py -3.12 -B -m unittest -q tests.test_madar_ai_usage_store`

**Observed:** 28 new tests passed on Python 3.12. Cases include default cloud denial, one-request explicit consent, false client proof, bad hashes/times/limits, CAS grant revocation, cancellation and conservative no-refund, local proof-gated refund, exact request/event replay and collision, UTC month rollover and grant/consent expiration, separate provider/user/project caps, two isolated organizations sharing the same opaque request ID, unauthorized reads, restart persistence, append-only audit, two simultaneous writers in separate threads, two simultaneous **Windows child processes** under SQLite file locking, and a socket-blocked local flow. TemporaryDirectory databases and synthetic IDs only.

Combined local regression: \`py -3.12 -B -m unittest -q tests.test_madar_ai_usage_store tests.test_madar_ai_provider_policy tests.test_madar_ai_draft\` -> **55 tests, OK** (28 new + 27 neighboring), exit 0. Individual success cannot prove the installed LAN client/cloud billing contract.

## Release gates

No changes to shared files, no commit, push, production path, migration, installation or deployment. Before a real release: host-injected principal and proof validation, authoritative UTC time, ledger recovery, OS ACL and backups, provider-specific conservative token/cost ceilings, verified dispatch-once/outbound spend control, cost settlement after provider usage, BYOK handling outside this store, and UI consent audit acceptance.
