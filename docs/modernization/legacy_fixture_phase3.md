# Modernization phase 3 | restore credible regression tests

## Problem, provenance, and user boundary

Madar intentionally stopped populating historical sample cards for real first-run profiles. The production code in `native_app.Bridge.__init__` now calls `empty_initial_state()`, leaving the user's new workspace empty. Many older regression tests still assumed project `p-sample` and cards `example-1` through `example-4` exist immediately. Such tests failed before they reached their actual accounting, LAN, history or authorization assertion.

This work preserves that **empty first-run production contract**. All fixtures are written only to disposable test roots. No customer profile, actual Parsian data, production SQLite, schema, permissions or installed EXE is read or changed.

## Verified baseline

- Reproducible suite helper: `tools/modernization_python_suite.py` (Python standard library subprocesses, per-module disposable `APPDATA`, `LOCALAPPDATA`, `HOME` and `TEMP`, with timeouts and JSON evidence).
- Initial baseline: 167/168 modules executed (one real packaged EXE acceptance test intentionally excluded), 136 passing, 31 failing, 0 timed out; 1,595 tests reported, 106 errors, 3 assertion failures, 2 skips and 2 expected failures.
- After 11 manual fixture adjustments and offline-session characterization: of the original 31 failing modules, 12 became passing, 19 remained (the latter rerun had 63 errors and 2 failures).

## Changes and behavioral parity

1. Added `tests/legacy_sample_fixture.py` helper. It **refuses** to populate any profile outside Python's disposable temp tree, writes the normalized old sample task state without invoking Bridge's event-producing `saveState`, and returns a freshly opened Bridge. This allows activity-count and receipt idempotency tests to start at genuine zero history.
2. Added explicit legacy data initialization in tests whose scenarios reference `p-sample`, `example-*`, including task/attachments, card archive, automation, LAN user scope, finance and standalone integrations. In cases where `saveState` has meaningful side effects, use the side-effect-free helper instead.
3. The offline-conflict test also had a separate broken mock: after simulating a lost connection it never restored a synthetic authenticated session, so `getState` retried nonexistent DPAPI credentials and returned cached offline data without running reconciliation. Restoring that **test-only** session causes genuine `three_way_merge` to exercise concurrent-edit conflict rejection; adjacent offline tests passed 7/7 without changing runtime merge logic.
4. Standalone host integration now asserts that real host provisioning produces **zero** sample cards, then inserts four historical cards explicitly into the temporary service fixture before testing TLS persistence. This tests both correct first-run behavior and restart retention.
5. The portable installation script's PSCustomObject table output truncated SHA-256 to two characters on Windows PowerShell 5.1. Added a stable `INSTALL_VERIFIED_SHA256: <64 lowercase hex digits>` output on verified install and unchanged reinstall. Test now checks the exact digest while still comparing installed/source bytes. Before the change the new assertion failed; after the change the installer and host-service combined suite reported 26 tests OK, 1 skipped.

## Evidence and open acceptance

- Five fixture modules: 28 tests OK.
- Six adjacent fixture modules: 21 tests OK.
- After introducing the reusable safe sample helper, of the 19 remaining failed modules, **17 passed**, leaving 2 failures: portable-installer textual SHA verification and host-service missing sample task; both received the bounded corrections above and a combined 26-case suite completed OK (1 optional test skipped).
- **Full source-level Python rerun on the completed working-tree content:** `python tools/modernization_python_suite.py --workers 5 --timeout 90 --report docs/modernization/full_python_phase3_final.json`. The runner reported **169 discovered, 168 executed, 168 passed, 0 failed, 0 timed out; 1,601 tests, 2 skipped, 2 expected failures, 0 unexpected failures and 0 errors**, 121.42 seconds. One optional `test_packaged_madar_host_exe.py` was deliberately not executed because it launches a separately built EXE that is absent here. This verifies the scoped source/test content, not a new compiled release.
- `npm run build` succeeded, and `node --test --test-concurrency=1 tests/*.test.cjs` finished **530/530 passed**. Three updater PowerShell scripts parsed with **0 syntax errors**, selected Python files compiled without errors, and `git diff --check` exited 0.
- The optional packaged EXE test is excluded from the 168-module Python source runner; the separately executed packaged-host smoke is recorded below. Real customer installer acceptance, LAN TLS across machines, Parsian migration trial balance and finance-role signoff remain release gates.

## Additional separately executed packaged-host acceptance

After the final 168-module source suite, PyInstaller 6.22.3 successfully built a disposable `release/MadarHost.exe` under this isolated modernization worktree. Running `python -m unittest tests.test_packaged_madar_host_exe -v` against that generated binary initially **failed** because the historical test expected four sample tasks on fresh host provisioning. The test was corrected to assert the owner's **empty-first-run** contract, then create synthetic sample cards through an authenticated HTTPS state write before checking persistence across a forced host process exit and restart. The same packaged-host test then completed **1/1 passed** in 3.185 seconds using a disposable data root, with no Windows Service registration and no production data. The generated EXE and PyInstaller intermediates remain untracked local QA products, not a signed installer or deployed artifact.
