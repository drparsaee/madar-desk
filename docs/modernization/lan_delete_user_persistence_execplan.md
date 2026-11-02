# ExecPlan | LAN user deletion persistence failure

## Baseline and scope

Local `main` at `72f0acd0732e5d2a14430e0cb64a89a19217580a`; origin points to private LocalForge. Initial `git ls-remote` authentication failed, so remote equality must be rechecked before any push. The only pre-existing untracked paths are unrelated Trello research directories. Follow `PROJECT_CONTEXT.md` MD-O02/MD-D06 and `docs/decision-inventory/DECISIONS.md`: authorization changes must persist before being exposed to sessions. Never use installed EXE, real profiles, Parsian data or operational finance.

## Characterization and change

`LanService.delete_user` currently mutates `self.users` and revokes sessions before `_store_users` returns. On a synthetic disk failure, the API raises but a previously valid user is already removed from live authorization. The method also saves task unassignments before persisting the registry; test the observable failure boundary separately rather than silently claiming multi-file atomicity.

1. Add synthetic failure-injection regression: failed registry write preserves user identity, active session, registry bytes and task assignments (when no tasks require unassignment, the latter is vacuous). Record red-before result.
2. Publish a detached candidate registry before modifying live authorization/session state. Preserve existing successful delete behavior and no-clobber semantics.
3. Run focused LAN suites and full isolated `npm test`; inspect diff and Git status.
4. Commit/push only after all gates pass and a fresh remote SHA confirms no divergence. If LocalForge authentication remains unavailable, retain validated source locally without claiming delivery.

## Explicit limitation

The multi-file operation of task unassignment plus account deletion has no crash-atomic transaction. This bounded change fixes the proven in-memory authorization inconsistency on registry-write failure; real power-loss durability and installed-host behavior remain unverified.

## Executed source-only evidence (2026-11-02)

- RED: `python -B -m unittest tests.test_lan_user_persistence.UserPersistenceFailureTests.test_failed_user_deletion_keeps_account_session_and_registry -v` exited 1: the synthetic editor's session had already been revoked despite a mocked registry write failure.
- GREEN: `python -B -m unittest tests.test_lan_user_persistence tests.test_lan_account_lockout tests.test_lan_display_roles tests.test_lan_security_framing_phase4 -q` exited 0, 25/25 passed.
- Full `npm test` exited 0: isolated Python 172/172 modules passed, 1,645 tests reported, 2 skips and 2 expected failures, no unexpected failures/errors/timeouts; Vite build passed; Node/React/Playwright 530/530 passed.
- `git diff --check` exited 0, with only Windows line-ending warning. Remote `main` SHA matched local baseline on retry after a transient authentication error. No packaged EXE, real-user migration, actual LAN device, power-loss test or Parsian data was exercised.
- Delivery requires a separate successful commit, push and remote SHA readback; this record does not by itself prove publication.
