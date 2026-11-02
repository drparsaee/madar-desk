# ExecPlan | Next version: per-user themes, card archive and host backup validation

## Source and safety
- Baseline: LocalForge private main at c2b849504a6bc4ab4c869665f466300f996c3fd9.
- New isolated sibling worktree; the dirty original checkout remains untouched.
- All tests use synthetic profile and data. Never access real user records, Parsian, installed EXEs or actual LAN services.
- The current main package reports 1.0.2; the separate public GitHub installer is v1.0.6. No publication or binary parity is claimed from this branch.

## Defects and acceptance
1. Theme toggle is currently gated by canManage and updates shared task settings. Make appearance selectable for every role with per-account local storage; no shared-state save.
2. Lane has a right-click menu but cards lack one. Add accessible card context menu and reversible, grant-checked archive separate from trash and board archive. Preserve finance fields, IDs and order; allow restore.
3. Manual host backup reported success without readback. New synthetic JSON and SQLite corruption injection tests both FAILED on baseline (false success). Validate published snapshot before returning success; show the host scheduler lastError and updated status in UI. Backups remain partial and full offline recovery is separate.

## Evidence and gates
- Initial Node tests failed for the absent archive/theme modules (RED).
- First real headless Chrome menu test failed by timeout: passive effect reset positioning after layout effect. Removed the conflicting effect; headless browser test then passed.
- Backup injected RED: two assertions expected RuntimeError but received none. After readback fix, three backup-adjacent modules passed 29 tests.
- Run full safe npm test in isolated profiles and git diff --check before commit. Do not claim deployed acceptance or any user-data backup test.
- If main changes during work, rebase/retest before a fast-forward push; avoid force push.

## Observed QA evidence
- The first complete safe test run passed 179 Python modules and the build; Node failed due to outdated source assumptions in Vitrea theme and Trash contracts, the newly active card context menu versus the former reserved right-click behavior, plus Chromium randomly selecting prohibited port 1719. These were corrected in tests to match the updated feature contract, and a safe high-port chooser avoids the unrelated flaky browser setup. No production feature was removed to satisfy tests.
- A subsequent full safe npm test passed: Python 179/179 executed modules, 1,662 reported tests (2 skipped, 2 expected failures; no unexpected failures); Vite build passed; Node 540/540 passed, 0 skipped. The opt-in packaged MadarHost EXE and real-profile migration were deliberately excluded.
- The real isolated card context-menu Playwright test passed for admin archive, read-only viewer, Escape and open action. The full App list right-click test passed with the updated card menu.
- During this work, LocalForge main advanced independently by LAN account-grant fixes. Final remote reconciliation and post-rebase verification must be recorded separately before calling this change merged.
