# ExecPlan | LAN partial admin account update must preserve existing grants

## Baseline and safety boundary

- 2026-11-02, LocalForge `main` and `origin/main` both at `c2b849504a6bc4ab4c869665f466300f996c3fd9`; read-only `git ls-remote origin refs/heads/main` matched.
- `PROJECT_CONTEXT.md` MD-O02 and `DECISIONS.md` require host-side scope and role enforcement. Only `lan.py`, a new synthetic test and this plan are in scope. Two pre-existing untracked Trello research directories are not ours and must remain untouched.
- No operational host, installed EXE, real user registry, Parsian, or finance data is involved.

## Reproduction (RED on baseline)

- `LanService.upsert_user` defaults omitted `role` to `viewer` and omitted `projects` to `None`, even for an existing scoped editor. A harmless admin-side profile-only or password-only update therefore silently changes permissions and widens project access to unrestricted.
- `python -B -m unittest tests.test_lan_partial_account_update_scope -v` exited **1** before code change: three synthetic tests ran and all three failed. Profile-only and password-only updates lost the existing editor role/project scope; explicit scope-only update unexpectedly downgraded the role. Fixture uses a disposable registry and a single fake project.

## Minimal change

1. Resolve the old account under the existing service lock, then derive omitted `role` and `projects` from the persisted account; new accounts keep existing defaults.
2. Keep explicit `projects: null` as the intentional unrestricted scope; an explicit promotion to admin without a projects field keeps the prior admin-unrestricted behavior.
3. Retain current validation, finance ACL, persistence and session semantics; do not modify live data or expand API surface.

## Required verification and delivery

- Run GREEN targeted regression and existing LAN/role/profile suites, then official isolated `npm test` (Python modules, Vite, Node). Record actual exit codes/counts.
- Inspect `git diff --check`, staged scope and current remote main; commit and fast-forward push to private LocalForge `main` only after green gates. Verify remote readback. No claim about real LAN or packaged EXE acceptance.

## Executed source-level evidence

- The initial implementation attempt moved role validation under the lock but left one viewer/finance guard before the role variable was resolved. An early 33-test focused run exited 1 with 27 `UnboundLocalError` errors; this was an implementation regression, **not** a passing gate. The guard was moved under the lock before subsequent QA. This failure is retained here rather than erased.
- After correction, a focused disposable-registry run of the new regression and user persistence module exited 0 (10/10 tests); the new regression was subsequently expanded to five cases, including explicit admin promotion and invalid scope rejection.
- Official `npm test` exited **0** on the final source: Python 180/180 modules passed, 1,665 tests reported, 2 skipped, 2 expected failures, zero unexpected failures/errors/timeouts; Vite production build passed; Node 530/530 tests passed, zero skipped or failed. The official runner excludes packaged EXE acceptance and real-user migration.
- Final focused regression + user persistence + HTTP LAN + role/profile suite: `python -B -m unittest tests.test_lan_partial_account_update_scope tests.test_lan_user_persistence tests.test_role_profiles tests.test_lan -q` exited **0**, **35/35 passed**. `python -B -m py_compile` for both changed Python files and `git diff --check` exited 0; only benign existing Windows LF/CRLF warnings were emitted for two font license files.
- Pre-delivery `git status` showed exactly the intended `lan.py`, new test and this plan, plus the same two unrelated untracked Trello research directories. Read-only `git ls-remote` again matched local `HEAD` at `c2b8495`. No runtime data was staged.
- Commit SHA, push and remote readback are separate delivery gates; record them only after executing them.
