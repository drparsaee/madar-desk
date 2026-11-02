# ExecPlan | LAN read projection must not alias live host structures

## Source and scope

Baseline `main` / LocalForge `ffd1596856f7879cb6876a98c645d80ac76ba2f9` (2026-11-02); only two unrelated untracked Trello research directories exist. `PROJECT_CONTEXT.md` MD-O02 / MD-D06 and `docs/decision-inventory/DECISIONS.md` require host-side ACL and no unauthorized state mutation. Work only on `lan.py`, a new synthetic test and this plan; do not access operational profiles, Parsian, or installed EXE.

## Hypothesis and RED

`view_for` deep-copies state, but for a non-admin with explicit project grants it rebuilds `boards`, `templates`, and `workspaces` using entries from the **original** `data` rather than the detached `filtered` copy. If `Bridge.getState()` returns a live state reference, editing a returned `read_state()` projection can mutate host memory without save, ACL, or revision validation. Build a disposable in-memory bridge and temporary user registry, verify nested identity separation for each structure, and show the pre-fix failure.

## Minimum compatible repair

Filter structural entries from the already deep-copied projection. Keep existing project visibility, workspace derivation, task/finance redaction, API envelope and sorting behavior. Add regression for visible and hidden boards/templates/workspaces and mutation isolation.

## Acceptance

1. RED synthetic regression against current baseline, followed by GREEN after minimal source edit.
2. Adjacent LAN ACL/projection tests and full official isolated `npm test` succeed; no unexpected failure, skip inflation or test deletion.
3. `git diff --check` and exact staged-path review; commit and push only after successful full QA, with local/remote SHA comparison.
4. Scope is source-only. Physical LAN, EXE, and real-data migration remain unverified.

## Executed evidence (2026-11-02)

- Baseline local and remote `main` were both `ffd1596856f7879cb6876a98c645d80ac76ba2f9`. The two unrelated untracked Trello research directories were not touched.
- RED: `python -B -m unittest tests.test_lan_read_projection_alias -v` exited 1 with **2/2 expected assertion failures**: the first scoped read mutated the host's board/template/workspace objects, and a subsequent read observed the uncommitted board change.
- Minimal fix: three structural collections now filter entries from the already detached `filtered` deep copy, not from the live input `data`.
- GREEN: five adjacent LAN modules (`test_lan_read_projection_alias`, `test_lan_finance_projection`, `test_lan_v1_acceptance`, `test_lan_security_framing_phase4`, `test_lan_display_roles`) passed **30/30**.
- The first official `npm test` attempt returned exit 1 during its Python phase; its temporary failure log was deleted by the runner and the exact cause is **unknown**. A separate full isolated Python audit then passed **175/175 modules**, **1,650 tests reported**, **2 skipped**, **2 expected failures**, zero unexpected failures/errors/timeouts. A second full `npm test` run returned exit **0** with the same Python totals, Vite build PASS, and Node/React/Playwright **530/530 passed**, zero skipped/failures. Do not reinterpret the first failure as a pass or claim a proven transient cause.
- `git diff --check` returned exit 0. This validates source tests only, not real EXE/LAN behavior. Git commit, push, and post-push remote SHA require separate evidence.
