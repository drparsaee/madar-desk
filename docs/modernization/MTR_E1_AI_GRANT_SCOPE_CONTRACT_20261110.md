# E1 AI grant UI scoped-response hardening (2026-11-10)

**Isolated source/UI change, scoped PASS; not a trusted live cloud model permission or production mount.** This is a later same-day extension of the read-only QA notes in `MTR_E1_AI_UI_BOUNDARY_QA_20261110.md`.

## Source and checks

- `madar_ai_usage_host_adapter.py`: authenticated `MadarAiUsageHostAdapter.handle` emits a strict top-level `grantScope: {projectId,userId,provider}` for the admin-only `grant_get` and `grant_set` actions using the actual validated host request. This is a routing assertion, not an account-independent digest or separate authorization. The store still uses host-derived org/project/user HMAC pseudonyms, never a client-supplied org or role.
- `src/ai_usage_admin.jsx`: `resultOf` now requires the exact server scope echo of selected `projectId`, `userId` and provider before accepting `grant_get` or `grant_set`. Missing, foreign or inconsistent scope refuses to display a loaded grant or a successful save. CAS/version/limit checks remain. Consent intent is unchanged and never dispatches to a model.
- `tests/ai_usage_admin.test.cjs` and `tests/ai_usage_admin_host_boundary.test.cjs`: existing synthetic response fixtures now include scope echoes; two new **negative** UI tests cover missing, wrong-user, wrong-project and wrong-provider scope on both grant read and save.
- `tests/test_madar_ai_usage_host_adapter.py`: checks that real synthetic host returns exact scoped echo for grant set/get.

## Fresh direct test commands

```powershell
node --test tests/ai_usage_admin_host_boundary.test.cjs tests/ai_usage_admin.test.cjs
py -3.12 -B -m unittest -q tests.test_madar_ai_usage_host_adapter tests.test_madar_ai_usage_store tests.test_madar_ai_usage_lan_http_pilot
```

- **Node: 39/39 tests PASS, exit 0**, including two new mismatched-scope rejection tests and three remaining *characterization* tests.
- **Python: 57/57 tests PASS, exit 0**, covering synthetic host adapter, budget store and optional local HTTPS.

## Security limitations that remain

1. Scope echo comes from the injected `command` response. A caller that fabricates both the grant data and matching `grantScope` can still mislead the **visual** component; the component cannot independently verify HMAC-pseudonymous IDs or authenticate its injected callback. Only a secure, session-bound host command wrapper can establish trustworthy response provenance. The two tests labeled **OBSERVED LIMIT** intentionally document that remaining exposure, not safety passes.
2. A correctly formatted `preverified:true` cloud hint is **not proof** of user-selected-text preflight, host-keyed content digest, gesture provenance, sensitive-data screening or actual cloud permission. Its test remains labeled **OBSERVED GAP**. No external provider call or dispatch is implemented.
3. These checks are Node synthetic interactions and Python test host fixtures; no real WebView2 browser, secure origin/CSRF policy, stored production grants, host key vault, billed model response or live authorized user was tested. Do not mount this UI with a cloud-sending action on these results alone.

No commit, push, deploy, user profile or real network/service data changes were made.
