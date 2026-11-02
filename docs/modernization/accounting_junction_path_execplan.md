# ExecPlan | Reject Windows junction paths in standalone accounting backup

## Decision and baseline

- Baseline: `87291e76635c198bbc8c86b96c9c6a7a7be13930` from local `main`.
- P0 data safety and MD-O15: an explicit backup source/destination must not be redirected through a Windows junction. Existing restore code already rejects junctions, but `standalone_accounting_backup._refuse_symlinks` checks only symbolic links.
- Scope: `standalone_accounting_backup.py`, synthetic backup tests, this plan. No operational profiles, Parsian data, installed EXEs or other working trees.
- The first remote fetch failed with a LocalForge HTTP authentication error. A later authenticated `ls-remote` and `fetch origin main` both succeeded and returned the same baseline SHA. Push still requires its own verification.

## Red/green and parity

1. Baseline synthetic backup test module: 30/30 passed in disposable profile.
2. Add real temporary Windows junction cases for both source-parent and destination-parent redirection. The expected behavior is fail-closed before a new backup is published.
3. Demonstrate red before changing source, then use the same `is_junction` detection as the existing restore path in `_refuse_symlinks`.
4. Run targeted and adjacent tests with synthetic profiles; run complete safe Python and Node/React/Playwright and Vite build gates before commit/push. Preserve all unrelated untracked research and historical test reports.

## Acceptance limits

This validates only path-redirect protection for the manual backup function, not complete Windows crash durability, real customer restoration, or a release. A failed remote authentication is a delivery blocker, not a reason to report a successful push.

## Executed evidence

- Before the new test, the isolated manual-backup module passed **30/30**.
- RED: the new Windows junction test failed with `AssertionError: ValueError not raised` for a real temporary source-parent junction. The first red run reported **31 tests, one assertion failure, zero skips**. Both test paths were synthetic and temporary.
- GREEN: after extending `_refuse_symlinks` to reject `Path.is_junction()`, the adjacent manual/automatic/identity backup modules passed **47/47**, zero skips.
- The first full safe `npm test` attempt did **not** pass: **168/169 Python modules**, 1,620 reported tests, one error. Its ephemeral diagnostic was not retained, so the failed module is not attributed. A subsequent independent full Python run passed **169/169 modules**, 1,620 reported tests, 2 skips, 2 expected failures, zero unexpected failures/errors/timeouts.
- The next `npm test` attempt passed Python but failed the Vite build because the isolated worktree had no `node_modules` dependencies. A worktree-local, untracked junction to the existing development dependency directory resolved this environment-only issue.
- The final complete safe `npm test` returned **exit 0**: Python **169/169 modules**, **1,620 reported tests**, 2 skipped and 2 expected failures, zero unexpected failures/errors/timeouts; Vite build passed; Node/React/Playwright **530/530** passed, zero skipped. Packaged EXE acceptance remained excluded.
- Python AST parse and `git diff --check` passed. No real customer, Parsian, installed EXE or operational database was accessed for tests.
