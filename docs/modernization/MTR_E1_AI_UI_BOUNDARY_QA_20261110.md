# E1 AI Dashboard Host Boundary QA | 2026-11-10

**Status:** Synthetic contract and security-characterization tests only. Not installed, shipped, mounted or production accepted. Baseline worktree HEAD at test time: 32bd8ff.

**Later same-day addendum:** After this worker's original read-only QA, the prime added a host-authored `grantScope` echo and mandatory UI check for grant_get/grant_set. Direct regression became **39/39 Node** and **57/57 Python** PASS. Wrong/missing routing scope now fails closed, but HMAC-pseudonym identity cannot be verified by the browser against a fabricated *consistently scoped* response, and cloud hint provenance remains open. See `MTR_E1_AI_GRANT_SCOPE_CONTRACT_20261110.md`. The historical 37/52 counts and G1/G2 characterizations below describe the earlier unmodified component.

## Ownership and scope

Created ONLY new tests/ai_usage_admin_host_boundary.test.cjs and this document. Existing src/ai_usage_admin.jsx, tests/ai_usage_admin.test.cjs, madar_ai_usage_host_adapter.py, madar_ai_usage_store.py, src/App.jsx, lan.py and shared UI code are **read-only**. No real profile, credentials, financial data, external calls, commit, push or deploy.

The component takes AiUsageAdminPanel({command, projectId, isAdmin, users, cloudConsent, dir}). The injected command(action, data, projectId) is NOT itself a trusted host capability. A future caller must add schemaVersion:1, manualAction:true on mutations, current authenticated LAN session, project ACL, CAS and secure transport. A client isAdmin or preverified boolean is display/input data and not authorization.

## Executed checks

1. node --test tests/ai_usage_admin_host_boundary.test.cjs tests/ai_usage_admin.test.cjs -> **37 passed / zero failed**, comprising 16 NEW boundary tests and 21 previously existing UI tests.
2. node --check tests/ai_usage_admin_host_boundary.test.cjs -> exit 0.
3. py -3.12 -B -m unittest -q tests.test_madar_ai_usage_host_adapter tests.test_madar_ai_usage_store -> **52 passed / zero failed**, synthetic existing host/store tests.

The Node suite compiled the unchanged component with the installed esbuild and used synthetic React-state interactions. One boundary test sent generated synthetic JSON envelopes into the **actual Python _command parser** via local subprocess stdin. It did not construct a LanService instance or open a listener and used no real account data.

## Positive contract coverage

- Render/mount performs no action. Admin must explicitly fetch a grant before enabling a CAS save.
- Admin policy payload has exact keys: userId, provider, enabled, cloudEnabled, monthlyRequests, monthlyTokens, monthlyCostMicro, expectedVersion and eventId. Bounded amounts, stable retry event ID and matching scope arguments were asserted.
- Server CAS version_conflict or a mismatched action/version/limit blocks visual success; exact retries preserve the previous eventId. In-flight old-project read is not applied to a newly selected project.
- Revoking the UI isAdmin display flag hides admin controls. A synthetic host-side permission_denied still denies even if isAdmin is forged true.
- Cloud consent requires an exact preverified-looking hint and an explicit checkbox. A successful intent is locked within the mounted component, including after switching hint props away and back. In-flight double-click submits once; failed retry reuses the same eventId; a different request needs a fresh checkbox.
- The real host parser accepts correctly wrapped grant_get, grant_set and cloud_consent commands, and rejects absent/nonboolean/false manualAction, foreign orgId, unexpected API-key fields and a mutation-only flag on a read action.
- Static and SSR checks found no credential or prompt contents in the synthetic rendered output, and no explicit network/model-dispatch method in the component.

## Three observed security gaps (characterization, NOT security passes)

**G1: grant_get response does not independently bind user/project scope.**
The existing normalizeAiGrant function checks provider, CAS version, booleans and numerical bounds. The new test supplied a structurally valid grant snapshot containing foreign opaque user_id and project_id values: the UI accepted it and made Save available. This establishes behavior of the visual component under a malicious or misrouted response, NOT that the actual authenticated Python host leaked any foreign record. The host stores pseudonymous HMAC identifiers that the raw client cannot directly match. The trusted command wrapper or a new scoped host response contract must enforce and attest user/project/organization binding before production UI mounting.

**G2: grant_set echo can be falsely accepted across scope.**
The new test simulated a grant_set response with the expected CAS version and limits but an unrelated opaque user/project. The UI displayed save success. Again, this is a **client-side response-validation gap**, not an observed authorization failure inside the Python store. Require the trusted wrapper to verify scoped response identity and add an end-to-end wrong-scope negative test.

**G3: preverified-looking intent may be forged by the client.**
The synthetic test supplied a correctly formatted preverified:true object without any genuine host preflight. After an explicit checkbox, the UI called cloud_consent. This does not send a prompt or incur cost: the existing host pilot records consent INTENT only and has no dispatch API. Before implementing any provider send, the host must independently validate precisely selected text, privacy scope, user gesture, bound host-keyed digest, requestId and current authorization. Never infer safe transfer from a client boolean or digest.

## Integration blockers

The currently unmounted UI has no production command wrapper. Its host callback expects the embedding application to inject a trustworthy session-bound transport and manualAction JSON envelope. Tested syntactic wrapping of commands is not equivalent to tested real TLS, origin/CSRF controls, authorized UI routing, Windows WebView2, real browsers or assistive technologies. In particular, do not label these characterization tests as production security sign-off.

No source or UI component was edited to mask any finding. The three issues require separately authorized implementation/integration work.
