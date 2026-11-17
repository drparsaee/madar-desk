# MTR AI user access dashboard: isolated pilot

## Purpose, decision and exclusions

Owner requirement (2026-11-09): the Windows desktop Madar AI feature must have an administrator-controlled user dashboard, without first hosting the complete app on an Internet server. Isolated source worktree `madar-p2-gantt-notifications-20261107`, baseline `32bd8ffe5ebbb0f4cd5c011c59323ed32f8647ac`. Do not change deployed MadarHost, existing user profiles, real finance data, LocalForge main or accounting. No cloud provider, API key, billing, quota or telemetry enabled in this pilot.

## Existing behavior / overview

- `src/features.jsx:LanPanel` already manages LAN users and roles, with a host-authenticated admin-only `/api/users` list and `/api/user` update.
- `lan.py:LanService.upsert_user` persists accounts through atomic user-registry publication, preserving existing settings across updates. `lan.py:LanService.account_for` uses host-side session auth.
- `native_app.py:Bridge.aiDraftSuggest` accepts explicit opt-in and a persisted authorized task, then calls a bounded local Ollama adapter; there was no separate administrator-managed AI grant.
- Local solo mode has no LAN user registry; network mode has admin/editor/viewer permissions. The only implemented AI provider is `local_ollama`.

## Design / parity / exact boundaries

1. Introduce a single persisted account boolean `aiEnabled`, **false by default** for new and legacy LAN accounts. Only LAN admin may change it. Password and display-role edits must preserve it; viewer downgrade automatically revokes AI. Profile self-update cannot change it.
2. List AI permission in the existing host-backed users dashboard, with a per-user administrator switch and an account-editor control. This displays the local-model grant only; online models and quotas remain explicitly unavailable.
3. Add `POST /api/ai/authorize` to the existing LAN host, with current session, role, project grant, valid project and AI enabled checks on every request. A stale React/client profile cannot override it. No prompt or model secrets go to this endpoint.
4. The native client must obtain fresh approval from the LAN host **before** starting local inference. Owner-managed solo operation remains as before with explicit consent. A grant can be revoked for subsequent requests, but cannot retroactively cancel already started local inference.

## Error, security and repeated-action behavior

- Legacy/unconfigured user, viewer, revoked user, different project, missing token, invalid permission type, nonexistent project, disconnected host => no AI request.
- Repeated enabling/disabling is idempotent in the account registry. Profile self-edit and role display change cannot escalate AI permissions.
- Admin account management happens over the already existing authenticated LAN transport; HTTPS and pinning remain mandatory for remote clients. No new listener.
- Local Ollama remains unavailable on machines where its model is not running. Admin grant does not download a model, initiate online spend or imply inference success.
- Existing accounts are not modified merely by loading this source. Explicit admin changes are required to write the policy in their registry.

## Work plan and validation

- [x] Baseline LAN/bridge tests on synthetic profile. The pre-change `tests.test_lan tests.test_taraz_review_status` run had 20 tests, 2 failures in legacy `/api/standalone-accounting/prepare` and `/quote` endpoints (404 observed vs 403 expected); unrelated to new AI routes.
- [x] Add account policy, protected host endpoint and native check.
- [x] Add host-backed AI control dashboard to existing user manager.
- [x] Synthetic targeted tests: `py -3.12 -B -m unittest -q tests.test_ai_user_admin tests.test_taraz_review_status tests.test_madar_ai_draft` had 17/17 passed before the last stricter response check. Expanded adjacent LAN account lockout/deletion suite: 25/25 passed before that check.
- [x] Browser-based `node --test tests/madar_lan_user_ui_runtime.test.cjs` 1/1 passed after testing admin on/off toggle and disabled viewer; `node_modules/.bin/vite.cmd build` passed after the UI change (1692 modules), with nonblocking main-chunk size warning.
- [x] Final strict-native-response rerun: `py -3.12 -B -m unittest -q tests.test_ai_user_admin tests.test_taraz_review_status tests.test_madar_ai_draft tests.test_lan_account_lockout tests.test_lan_delete_registry_failure tests.test_lan_delete_state_atomicity` => **26 tests, OK**, exit 0 (2026-11-09).
- [x] Final `node --test tests/madar_lan_user_ui_runtime.test.cjs; git diff --check; py -3.12 -B -m py_compile lan.py native_app.py tests/test_ai_user_admin.py` => 1 browser test passed, exit 0. Earlier Vite build after final UI markup passed, no installer test.

## Rollback and release gate

Restore this pilot's source diffs only in the isolated worktree and preserve all prior untracked design files. No commit, push, EXE build, deployment or live LAN account edits without separate acceptance. UI build and localhost synthetic tests are not evidence of installed multi-PC behavior.

## Surprises and remaining acceptance

The existing LAN user-management browser test expected usernames with an `@` only once. The initial AI panel repeated the same text and triggered Playwright strict locator ambiguity; the AI panel now displays the plain username and the previously existing directory retains `@username`. The test was rerun successfully. The earlier test fixture used a nonexistent project ID; it was corrected to the synthetic `p-sample` project. No production user data was involved.

Current policy is a **single local-model grant**. It does not measure usage, enforce daily quotas or spending, choose cloud providers, store BYOK credentials, or authorize any finance operation. The UI/host currently requires a LAN owner-managed user list; standalone solo AI keeps its existing explicit opt-in flow. True installed host/client two-PC GUI, live Ollama inference, accessibility sweep and actual deployment remain NOT VERIFIED.
