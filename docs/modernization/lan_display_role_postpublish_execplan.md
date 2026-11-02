# ExecPlan | LAN presentation-role catalog post-publication failures

## Source, scope and safety

- Baseline: private LocalForge `main` at `e15e6a2ec6b68e4ecb141a937d74056086cda3ee`, confirmed by `git fetch` and `git ls-remote` on 2026-11-02. Two unrelated untracked Trello research folders are left untouched.
- PROJECT_CONTEXT MD-D06/MD-O02 and managed-role decision require consistent role catalogs across the live host and restarts. This is presentation metadata, **not** the host ACL.
- Scope: `lan.py`, a synthetic regression module, and this plan. Use only temporary account/catalog files and synthetic identities; never read or modify installed EXEs, operational profiles, Parsian, or live data.

## Hypothesis and RED gate

`upsert_display_role` and `delete_display_role` write a catalog with `atomic_json`, then assign `self.display_roles`. A writer may publish the file and raise afterward, leaving a rejected change persisted across restart while the live host still uses the old catalog. Inject a one-shot exception after writing a synthetic catalog and require the previous catalog to remain on disk and in memory. An unexpected foreign revision must not be overwritten.

## Minimal fix and parity

For existing catalogs, centralize publication: on failure, read the persisted JSON; if it equals the candidate, compensate by writing the previous catalog; if it equals the previous catalog, propagate; otherwise fail closed. Keep existing successful edit/delete, built-in protection, active-account deletion guard and admin-only checks. Preserve session and ACL behavior. Explicitly do not claim crash atomicity or external-writer CAS.

## Verification and delivery

Run RED against unchanged source; then targeted LAN role/account/security suites, isolated official `npm test` (Python, Vite and Node), syntax and Git diff checks. Only if all pass, verify remote freshness, stage scoped paths, commit/push to LocalForge `main` and compare remote SHA. Real LAN, installed EXE and power-loss acceptance remain separate.

## Observed source QA (2026-11-02)

- **RED on baseline:** `python -B -m unittest tests.test_lan_display_role_postpublish_failure -v` exited **1**. Three synthetic tests produced two assertion failures (edit/delete survived restart despite reported failure) and one unexpected `OSError` for a foreign revision.
- **GREEN targeted:** the first four-module adjacent run, before adding two extra boundary tests, exited **0** with **23/23** tests passed. The expanded five-case synthetic module then exited **0**, **5/5** passed, including first-catalog publication and compensation-failure handling.
- **Syntax/diff:** `python -B -m py_compile lan.py tests/test_lan_display_role_postpublish_failure.py` and `git diff --check` exited **0**.
- **Official full source QA:** `npm test` exited **0** through `tools/safe_test_runner.py`. Python reported **182/182 executed modules**, **1,677 tests**, **2 skipped**, **2 expected failures**, **0 unexpected failures/errors/timeouts**. Vite build passed. The strict runner also completed Node tests and exited 0; the numeric Node summary was not retained in the observed output, so no exact Node count is asserted. The packaged EXE module was deliberately excluded.
- **Pre-delivery:** `git diff --check` exited 0 (two unrelated existing font line-ending warnings); `git ls-remote origin refs/heads/main`, local HEAD and `origin/main` all matched baseline `e15e6a2ec6b68e4ecb141a937d74056086cda3ee`. Only the scoped three files are to be staged; the two Trello research folders remain untouched.
- Git commit/push, remote SHA verification, installed EXE and real-world acceptance are separate from the above source tests.
