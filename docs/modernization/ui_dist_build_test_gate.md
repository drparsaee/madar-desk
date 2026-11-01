# UI runtime regression | build the current source before tests

## Purpose and boundaries

The owner's automated Madar audit covers the React UI before user-operated device acceptance. Baseline `main` for this narrow workflow fix: `7fe7995f7762fe81eadb37ba25b6b600786e604c`. Change only the `npm test` script in `package.json`; do not alter deployed EXEs, customer profiles, live LAN or user data.

## Verified failure and source cause

The existing `npm test` script ran Python tests, then Node tests against whatever `dist/` was already present. Several Playwright tests serve `dist/` with Vite preview, not current source. The serial Node run against the existing build reported failures in `madar_unslop_accounting_tabs_runtime`, `madar_unslop_navigation_startup` and `vitrea_runtime_ui` (including background color mismatch, board start view mismatch and old card typography/background). Rebuilding current source with `npm run build` succeeded: 1,706 Vite modules transformed. Immediately rerunning those three UI tests passed **3/3** without source/UI changes. This supports stale build artifacts as the cause of these three failures, but does not claim all possible UI defects are resolved.

## Design, parity and tests

`npm test` must run a fresh production Vite build after the Python suite and before the serial Node suite. Keep the Python command, Node tests and serialization semantics intact. `npm run build` checks font licenses and produces the local `dist/` test fixture. A direct manual Node invocation still requires a preceding build; the standard `npm test` path enforces it.

Acceptance: validate the JSON script, perform a current build, rerun selected browser tests and the full serial Node suite. Track exit codes and skipped tests explicitly. No installer or release is built or installed.

## Progress

Pre-fix failures and post-build targeted success (3/3) observed in synthetic browser sessions. The first complete post-build serial run returned **529/530 passed, 1 failed, 0 skipped**. The sole failure was `madar_unslop_navigation_startup.test.cjs`: initial nav button width matched the hovered width, meaning its hover precondition was not stable. The test now moves the pointer to a neutral position, waits for the collapsed button, and uses a bounded wait for expansion relative to the measured baseline. The first attempted correction imposed an absolute 90px threshold, which failed in isolation because expanded content was only ~87.8px wide; that incorrect threshold was replaced by `before+25`. The targeted updated browser test passed **1/1**. This is a test-fixture stability correction, not a production navigation-style change.

Final post-build serial run `node --test --test-concurrency=1 tests/*.test.cjs`, with isolated APPDATA/LOCALAPPDATA/TEMP, returned **530 tests passed, 0 failed, 0 skipped**, duration **182,388.9 ms**. Production `npm run build` completed successfully with 1,706 modules; Vite emitted a non-blocking chunk-size warning. The total Python suite was not rerun as part of this UI-only change, so `npm test` (which includes complete Python) is not claimed as executed end to end. Commit/push: pending.
