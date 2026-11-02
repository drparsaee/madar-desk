# ExecPlan | LAN identity registry failure after atomic publication

## Baseline and boundary

- 2026-11-02: `main` and private LocalForge `origin/main` verified at `a6714ecb9d6e638e9f44a799e8d7189ac2dfc1dd` after fast-forward. A transient fetch authentication error was followed by successful authenticated fetch and `ls-remote`.
- PROJECT_CONTEXT MD-O02/MD-D06 and decision inventory require durable, host-enforced identity and ACL. Scope: `lan.py`, synthetic regression module, and this ExecPlan only.
- Two pre-existing untracked Trello research directories are unrelated and must remain untouched. No actual profiles, Parsian, installed EXE, or live host state may be accessed.

## RED hypothesis

`upsert_user`, `update_profile`, `change_password` and `reset_password` persist a detached candidate registry and only then update `self.users`. An atomic registry writer can successfully publish the new JSON but raise during a later step. The API then reports failure, the live host retains the old identity, yet a restart loads the new role/password/profile. Inject a one-shot post-publication exception in a disposable registry; require both disk and live state to retain the old identity and existing sessions.

## Minimum repair

Use a shared publication helper for the four existing-registry mutation paths. On a writer exception, read back the actual registry. If it is unchanged, propagate the original error; if it exactly matches our candidate, compensate by restoring the old registry before propagating; if unreadable/foreign, fail closed without overwriting. If compensation fails, report it explicitly. Do not claim cross-process compare-and-swap or power-loss atomicity. Keep normal success behavior and session revocation order.

## Gates

1. Record the failing RED synthetic regression before editing implementation.
2. Run targeted and adjacent LAN identity/security tests after the minimal fix.
3. Run official isolated `npm test` including Python, Vite build and Node; inspect exact exit and test counts.
4. Check `git diff --check`, staged paths, fresh remote `main`; commit and fast-forward push only on real green, then verify remote SHA.

## Evidence

- **RED (source baseline)**: `python -B -m unittest tests.test_lan_identity_postpublish_failure -v` exited **1** with 5 synthetic cases: 4 assertion failures (disk contained an unconfirmed role/password/profile update) and 1 unexpected `OSError` instead of a guarded foreign-revision error.
- **GREEN focused**: six identity/LAN security modules exited **0**, **36/36 tests passed** in a disposable profile. Normal role updates, session rules, existing lockout and HTTP framing checks remained green.
- **Full official `npm test`** exited **0**: isolated Python **181/181 executed modules**, **1,672 tests reported**, **2 skipped**, **2 expected failures**, zero unexpected failures/errors/timeouts; Vite build PASS; Node **540/540 passed**, zero skipped/failures. The packaged host EXE test is explicitly excluded by the runner.
- `git diff --check` and `python -B -m py_compile` exited 0. Pre-delivery remote `main` matched baseline `a6714ecb9d6e638e9f44a799e8d7189ac2dfc1dd`. Two unrelated untracked Trello research directories were left untouched.
- The compensation is for in-process exceptions after publication of an **existing** registry. First-time owner setup, concurrent external registry writers between readback and rollback, abrupt power loss, installed EXE, two-machine LAN and operational migration are not accepted by this change.
- Git commit/push and post-push SHA verification are separate delivery steps, not implied by passing source tests.
