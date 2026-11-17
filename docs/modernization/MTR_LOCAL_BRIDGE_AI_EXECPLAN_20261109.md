# MTR local bridge return status and optional AI pilot

## Purpose, decision, exclusions

Owner priority (2026-11-09): complete controlled Madar ↔ Taraz integration, then introduce optional local AI in Madar. This pilot runs in the isolated Madar worktree `madar-p2-gantt-notifications-20261107`, baseline `32bd8ff`; Taraz checked at `653089b` and is **not modified**. No installed application, live financial data, production migration, LocalForge push, installer, or LAN protocol changes are authorized by this pilot.

## Existing behavior and inventory

`taraz_exchange.queue_saved_task()` writes schema-1 metadata to `%LOCALAPPDATA%/Madar-Taraz-Bridge/pending/<id>.json`, without ledger posting. `taraz_integration.review_request()` in independent Taraz moves it to `reviewed/<id>.json` and creates `reviewed/<id>.review.json` with `source=taraz`, state `reviewed` or `rejected`, and `financialEventCreated=false`. Existing Madar `tarazIntegrationStatus()` only counts pending files; `native_app.Bridge.tarazIntegrationQueue()` enforces LAN role and task grants. Browser fallback does not access native bridge. Ollama loopback previously enumerated `qwen3:4b` but actual inference was not established at plan time.

## Plan of work / parity and boundaries

1. Add read-only, opt-in-scoped task history inspection using the existing schema-1 proposal and receipt pair; validate source, IDs, task/project, no posting; show `unknown` on conflicting/missing/malformed receipt and `partial` when scan caps are reached.
2. Require persisted task and LAN access checks in native bridge before reading; export only an allowed native method and web fallback; TaskEditor displays explicitly labelled local observations.
3. Optional local AI adapter (loopback only, fixed installed model, timeouts, size/schema caps) generates **unapplied** draft suggestions. Native API verifies account/project grants; user must explicitly invoke it; no external fallback, finance action, or automatic edits.
4. Exercise temporary-profile synthetic queue → real Taraz source reviewer → readback; negative receipt, symlink and ACL; mock AI HTTP; run build/relevant regression. No real customer/profile data in tests.

## Expected difference / failure cases

Previous UI offered only queueing; new UI offers scoped review observation. `reviewed` is not financial approval, `pending` is not authenticated peer reception, and neither local metadata nor file existence proves Taraz peer identity. Truncated, disappeared, mismatched, or modified receipts are not promoted to success. A local folder is not LAN-ready transport. If AI is unavailable, manual editing continues normally. Repeat retrieval is read-only; repeat sending remains manual and produces a separate proposal under the pre-existing schema.

## Progress and validation

- 2026-11-09: read-only local status module, native export, task UI, synthetic end-to-end tests added; `py -3.12 -B -m unittest -v tests.test_taraz_review_status tests.test_taraz_exchange` produced 10 tests, all OK, exit 0.
- Expanded `tests.test_taraz_link_status` and `tests.test_mtr_finance_workflow_contract`: 45 Python tests OK in combined run. Adjacent `node --test tests/native_bridge_readiness.test.cjs`: 1 passed, 3 failed because historical test looks for removed `ACCOUNTING_JS_BRIDGE`; failures must not be described as passes and require baseline/intent assessment.
- Native AI method `aiDraftSuggest` now checks fresh `optedIn`, existing task and LAN role/project grant before the fixed-model local adapter. The UI offers manual text submission, draft preview and separately confirmed title-only acceptance; checklist suggestions are not applied automatically.
- `py -3.12 -B -m unittest -q tests.test_taraz_exchange tests.test_taraz_review_status tests.test_taraz_link_status tests.test_mtr_finance_workflow_contract tests.test_madar_ai_draft`: **55 tests OK**, exit 0. `node --test tests/general_ui_preferences.test.cjs`: **4/4 pass**, exit 0.
- `node_modules/.bin/vite.cmd build`: success (1692 transformed modules, 5.22s), warning for main chunk greater than 500 kB. This verifies bundled compilation, **not** WebView2 integration or installer acceptance.
- `git diff --check`: exit 0 for tracked modifications. New files are untracked and are not included in `git diff --stat` by default.
- Local `qwen3:4b` smoke invocation using only a synthetic English carton prompt and an 8-second timeout returned `DraftError('model_unavailable')`. It did **not** demonstrate successful real inference; earlier `/api/tags` enumeration is not proof of generation readiness. Two earlier shell-quoted attempts failed with Python `SyntaxError` before reaching the adapter.

## Surprises, risk, rollback, acceptance

Both Taraz review decisions reside in the **same** `reviewed` directory, distinguished by receipt payload. Taraz writes review marker after moving metadata, so crash between those operations leaves indeterminate state. No signature/HMAC authenticates this local peer; UI states are local observations only. For rollback, revert only this isolated pilot's source changes, leaving prior design/E0 documents and real profiles untouched. Formal finance workflow, true LAN transport, multi-tenant host ACL, GUI packaged application and operational acceptance remain separate gated tasks.

### Remaining acceptance gates

- Confirm local Ollama inference responsiveness independently, then validate Persian output with safe sample prompts and human review; an available model listing is insufficient.
- WebView2 real UI interactions, keyboard/focus and stale-card behavior need executable browser/desktop integration coverage beyond successful Vite compilation.
- True authenticated Taraz receipts, cross-device/host transport, race-safe marker commit and idempotent multi-company financial workflow remain out of scope for this metadata-file pilot.
- No commit, push, installer or production accounting posting has been performed here.
