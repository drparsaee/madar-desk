# Evidence and Acceptance Rules

## Required task-level evidence

| Change class | Minimum evidence |
| --- | --- |
| Documentation / instruction policy | Links resolve, instruction precedence is explicit, no contradicting binding rules, `git diff --check` passes |
| Pure function or bug fix | Before/after behavior or reproduction, targeted automated test, relevant neighboring tests |
| API / permission / persistence | Contract tests, denied/invalid inputs, idempotency or transaction test when applicable |
| Data import / migration | Restorable backup, isolated rehearsal, counts and financial invariants, rollback plan, approval of live write |
| Deployment / release | Pre-release build/tests, archive/checkpoint, deployment evidence, live smoke test and rollback instructions |
| Multi-agent integration | Unique diff review, isolation evidence, integrated test results and remote SHA if published |

## Working loop

1. Define the expected outcome and a check that could falsify it.
2. Inspect baseline without rewriting it.
3. Make the narrowest change that satisfies the check.
4. Run targeted checks, then broader regression checks appropriate to the project.
5. Inspect final diff for accidental deletions, secrets, unrelated changes, broken paths and stale status claims.
6. Record evidence and unresolved risk. Retry within task scope; do not silently expand permissions to make a failing check pass.

## Completion vocabulary

- `DRAFT`: design exists; not implemented.
- `IMPLEMENTED`: relevant files changed, but full validation not established.
- `VERIFIED`: stated acceptance checks passed with named evidence.
- `COMMITTED`: repository contains the exact commit SHA.
- `PUSHED`: remote ref was checked against the local commit.
- `DEPLOYED`: real deployment was performed and separately verified.
- `BLOCKED`: a named prerequisite or safety gate remains unresolved.

Do not collapse these into a single `DONE`. Document test commands, exact totals when observed, failures and skips. Do not invent benchmark numbers, QA results, external approvals or data migration coverage.

## Explicit release checks

Check that all edits are scoped and authorized, the worktree contains no accidental outputs or secrets, `git diff --check` passes, and the push is a fast-forward to the approved private remote. Production effects always require independent verification.
