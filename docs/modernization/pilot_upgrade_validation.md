# Pilot upgrade | Verification and parity

## Executable evidence

Baseline: `fbe86e6c9c74c0988a8652e734888221ed6c43e5`. Pilot implementation branch: `modernization/code-review-20261101`.

1. **Characterization:** `python -m unittest tests.test_madar_update_contract -v` passed 4/4 before this pilot edit, with disposable profile and fake EXEs.
2. **Focused validation:** after implementing drive-root rejection, same command passed 5/5 (one new negative case). `git diff --check` passed.
3. **Side-by-side comparison:** `tests/test_codex_upgrade_parity.py` executed the original preflight from Git and the changed script on separate synthetic profiles with the same content. **3/3 passed:** matching archive files and unchanged sources, fresh-profile behavior, and rejection of overlapping paths.
4. **Adjacent tests:** `python -m unittest tests.test_release_persistence tests.test_release_restore_guard tests.test_madar_update_contract tests.test_codex_upgrade_parity -q` ran in a fresh isolated `APPDATA` and `LOCALAPPDATA`. **15/15 passed, 0 errors**, and `git diff --check` succeeded (last run after the normalized-drive-root subcase was added).
5. **External agent audit:** read-only `codex exec` review was attempted but did **not** return a report. This does not constitute independent sign-off.
6. **Complete Python suite:** invoked `python -m unittest discover -s tests -p test_*.py -q` in disposable `APPDATA` / `LOCALAPPDATA`. The attempt was stopped after approximately 386 seconds without unittest's final test-count/result summary; exit reflected termination. The log records resource warnings and synthetic failure messages, but cannot establish the actual final number of passed/failed cases. This is **not** a completed full-regression check.

## Test matrix

| Scenario | Expected outcome | Parity requirement |
| --- | --- | --- |
| Ordinary profile with nested files | Full ZIP whose content matches input; source unchanged | Baseline/new identical file bytes |
| Fresh profile (path not present) | `FRESH_PROFILE`, no ZIP | Same |
| Backup directory is inside data directory | Non-zero exit, no ZIP | Same |
| Source is drive root | Non-zero exit before any backup | **Intentional new fail-closed rule** |
| Running Madar/MadarHost | Non-zero exit before mutation | Same, process mocked in isolated subprocess |
| Executable hash mismatch during activation | Version pointer remains old | Same, unchanged script |

## Acceptance boundaries

- This test matrix never targets `%APPDATA%\MadarDesk` or an installed version.
- Success in these cases does **not** prove release readiness; the full Python regression must pass and the new installer must be validated on clean Windows versions with accounts and historical financial backup restoration.
- No changed executable or installer is deployed as part of this pilot. Remote LocalForge branch push is a distinct gate.

## Phase-2 evidence (new isolated worktree, 2026-11-01)

- Initially 10 updater/parity tests passed, including new lock-failure cleanup, volume-root normalization and 180-file Unicode snapshot coverage.
- After adding activation root rejection and repeated-backup uniqueness: `tests.test_release_persistence`, `tests.test_release_restore_guard`, `tests.test_madar_update_contract`, `tests.test_codex_upgrade_parity` ran **19 tests, all passed**. The earlier 18/18 pass preceded the last test.
- The three original baseline parity comparisons still test ZIP bytes for valid paths, fresh-profile behavior and overlapping-path refusal. Drive-root refusal is an intentional security difference, tested only with an unmounted volume letter.
- HTTP ambiguous-header and invalid accounting login boundary tests initially failed on the current baseline (HTTP 200 instead of 400, and credential validation changed persistent lockout state), then passed after bounded fixes. Larger LAN/accounting suites and product-level testing are tracked separately in [phase2_evidence.md](phase2_evidence.md).
- Node browser test parity: full Node suite in serial mode **530/530 PASS** after `npm run build` succeeded. The default parallel invocation had two UI timeouts, both later passed in isolation. Default `package.json` Node test command now selects serial concurrency for reproducibility.
