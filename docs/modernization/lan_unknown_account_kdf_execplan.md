# MD-O02 | Equal password verification work for unknown LAN accounts

## Baseline, scope and decision

- Source: private LocalForge `main`, `75e3bdacac7daa6845c6c8c154503da1954993ad` on 2026-11-02; `origin/main` matched after fetch.
- `PROJECT_CONTEXT.md` MD-O02 requires host-side authentication, generic login failures and rate limiting. A known username with a wrong password reaches PBKDF2, but an unknown username currently short-circuits before PBKDF2. This can reveal account existence through a timing difference even when error text is identical.
- Only `lan.py`, a new synthetic regression test and this plan may change. Do not touch operational profiles, real credentials, Parsian data, EXEs, installed versions or unrelated untracked Trello research.

## Test-first plan and parity

1. With a temporary synthetic user registry, patch the PBKDF2 function as a call counter while still running real verification. Compare a wrong password for an existing user against a wrong password for an unknown username on distinct synthetic IPs. Assert both take exactly one PBKDF2 call and both raise the same generic error. Run on unmodified source first and preserve the expected RED evidence.
2. Introduce a fixed-format dummy password hash for unknown accounts, computed once from public noncredential constants. Always invoke `verify_password` once after account lookup; the absent account must still fail regardless of the dummy comparison result. Keep the 6-attempt/120-second lockout, session issuance, account-specific counters and existing password policy unchanged.
3. Run targeted LAN authentication/security tests, then the official isolated `npm test` source suite (Python, Vite and Node/Playwright), syntax and `git diff --check`. Any failure blocks push; record exact outcomes.
4. Check `HEAD` and `origin/main` again; commit only scoped files and push to LocalForge `main` after all gates pass. Verify the remote SHA after push.

## Limits

This is a deterministic equal-work regression, not a statistical network timing study. Other factors such as account lookup, JSON parsing, lockout, TLS and OS scheduling can still affect latency. No claim of complete enumeration resistance or deployed release acceptance follows from it.

## Observed validation (2026-11-02)

- RED on unmodified `lan.py`: the new one-test synthetic module exited 1. The known synthetic account invoked PBKDF2 once, while the unknown username invoked it zero times (`AssertionError: 0 != 1`). No real account, service or database was used.
- GREEN: the same regression and four neighboring LAN modules completed **41/41 tests**, exit 0, in a disposable profile. The test also confirms that even the public dummy-hash input cannot authenticate a nonexistent account.
- Full official `npm test` exited **0**: isolated Python **178/178 modules** passed, **1,659 reported tests**, **2 skipped**, **2 expected failures**, **0 unexpected failures/errors/timeouts**; Vite build passed; serial Node/React/Playwright **530/530 tests** passed, zero skipped/failures. The packaged-host EXE test was excluded by the runner.
- Python compilation and `git diff --check` returned zero before the full suite. This evidence concerns source-level QA only; it does not prove actual LAN timing indistinguishability, Windows deployment, physical two-machine acceptance or operational data recovery.
- Commit/push and post-push remote SHA are separate delivery gates and must be recorded from Git after execution.
