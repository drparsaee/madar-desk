# ExecPlan | LAN account registry predictable temporary filename

## Scope and source of truth

LocalForge `main` baseline `10a28b8629ea285a3ac078717dc8622d0cb62ffb` (read-only remote SHA matched after a transient authentication error). This bounded change follows MD-O02, MD-D06 and `lan_user_persistence_execplan.md`: user identity must not be lost or silently changed by an unrelated file. The two pre-existing untracked Trello research directories are out of scope. Only synthetic temporary users, no real profiles, installed EXE, Parsian data or operational releases.

## Defect and RED characterization

`LanService._store_users` always writes `users.json.tmp` with `Path.write_text` before replacing `users.json`. A pre-existing unrelated file with that exact name is truncated and then renamed into the registry. This fixed-name collision also creates a symlink/junction race and has no pre-publication `fsync`. Add a disposable-directory test that plants an unrelated sentinel `users.json.tmp` and updates an authorized synthetic profile; assert the sentinel is untouched and the profile is persisted.

RED observed on baseline: `python -B -m unittest tests.test_lan_user_persistence -v`, exit 1; 6 tests, 5 passed, 1 error because the unrelated temporary file disappeared during publication.

## Minimal compatible correction

Use the already imported `offline_exchange.atomic_json` for user-registry publication. It chooses a random per-write temporary filename, flushes and fsyncs it, then uses `os.replace` and removes its own temporary file. Preserve the existing JSON schema, role checks, in-memory commit ordering, session revocation and account behavior.

## Verification and delivery gates

1. Run the same synthetic test green; run adjacent LAN security and account tests.
2. Run official `npm test` isolated full Python/JS/Vite gate; review `git diff --check` and tracked/untracked scope.
3. Commit/push to LocalForge `main` only if gates pass and remote SHA still matches the baseline. Verify remote SHA equals the new local commit.
4. Physical power-loss durability, adversarial local filesystem permissions, installed EXE and live LAN are not validated by this source-only change.

## Executed source-only evidence (2026-11-02)

- Baseline RED: `python -B -m unittest tests.test_lan_user_persistence -v` exited 1, 6 tests, 5 passed and 1 expected observed error: the planted unrelated `users.json.tmp` was moved away by registry publication.
- GREEN: focused `python -B -m unittest tests.test_lan_user_persistence tests.test_lan_account_lockout tests.test_lan_display_roles tests.test_lan_security_framing_phase4 -q` exited 0, 24/24 passed.
- Full `npm test` exited 0: isolated Python 172/172 modules passed, 1,644 tests reported, 2 skipped, 2 expected failures, zero unexpected failures/errors/timeouts. Vite build passed; Node/React/Playwright 530/530 passed, zero skipped/failures. The packaged EXE module and real-user migration are excluded by this runner.
- `git diff --check` exited 0 with Windows line-ending warnings only. Fresh `git ls-remote origin refs/heads/main` matched baseline `10a28b8629ea285a3ac078717dc8622d0cb62ffb` after an initial transient authentication failure.
- Commit/push and final remote SHA comparison must be verified separately before claiming delivery.
