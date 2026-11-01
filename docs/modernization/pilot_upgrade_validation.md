# Pilot upgrade | Verification and parity

## Executable evidence

Baseline: `fbe86e6c9c74c0988a8652e734888221ed6c43e5`. Pilot implementation branch: `modernization/code-review-20261101`.

1. **Characterization:** `python -m unittest tests.test_madar_update_contract -v` passed 4/4 before this pilot edit, with disposable profile and fake EXEs.
2. **Focused validation:** after implementing drive-root rejection, same command passed 5/5 (one new negative case). `git diff --check` passed.
3. **Side-by-side comparison:** `tests/test_codex_upgrade_parity.py` executed the original preflight from Git and the changed script on separate synthetic profiles with the same content. **3/3 passed:** matching archive files and unchanged sources, fresh-profile behavior, and rejection of overlapping paths.
4. **Adjacent tests:** `python -m unittest tests.test_release_persistence tests.test_release_restore_guard tests.test_madar_update_contract tests.test_codex_upgrade_parity -q` ran in a fresh isolated `APPDATA` and `LOCALAPPDATA`. **15/15 passed, 0 errors**, and `git diff --check` succeeded (last run after the normalized-drive-root subcase was added).
5. **External agent audit:** read-only `codex exec` review was attempted but did **not** return a report. This does not constitute independent sign-off.

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
