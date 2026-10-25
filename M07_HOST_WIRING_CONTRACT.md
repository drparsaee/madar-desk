# M-07 Host Wiring Contract and SQLite Regression Gate

**Snapshot:** 2026-10-21. The implementation and tests are separate work streams.
This tranche authored **only** `tests/test_m07_host_preflight.py` and this
document. Prime concurrently connected `m07_host_guard.py` to
`native_app.py`; those source files and `rule_safety.py`,
`automation_v1.py`, `app_storage.py`, and `finance.py` were inspected
read-only here.

## Observed entrypoints

1. `native_app.Bridge._save_local_state(...)` calls
   `_save_local_state_locked(...)` under the existing write guard.
   In the **activated five-domain SQLite** branch, after computing
   `card_change_events(prior, candidate)` and preparing the candidate task
   snapshot, `_save_local_state_locked` invokes:

   ```python
   from m07_host_guard import safe_card_events
   guarded = safe_card_events(
       updated, events, actor=acting, accounts=event_accounts,
       cards=state["tasks"], projects=state["projects"], now=stamp)
   updated = guarded["bundle"]
   # Existing single CAS commit for tasks, finance, collab, outbox, automation.
   self._unified_store.commit(updated, expected_revision=current.revision)
   ```

2. `m07_host_guard.safe_card_events` calls
   `rule_safety.dry_run_events` **before**
   `automation_v1.enqueue_events`. When
   `safeToExecute == False`, `SafetyHold` is raised. No next state is returned,
   and `run_batch`, backup publication and SQLite commit must not occur.
   After an accepted enqueue, `m07_host_guard._execute` calls
   `rule_safety.preflight_due_batch` on the **just-enqueued journal** before
   `automation_v1.run_batch`. The latter receives:

   ```python
   limit = inspected["safeLimit"]  # <= DEFAULT_POLICY["maxEvents"] == 25
   max_attempts = DEFAULT_POLICY["maxAttempts"]  # 3
   ```

3. `native_app.Bridge._run_engine_scheduler(actor, accounts)` reads the
   current authoritative five-domain SQLite snapshot and calls
   `m07_host_guard.safe_due_tick` with the existing candidate tasks,
   authoritative accounts/projects, trusted `today` and `now`. The guard
   performs:

   ```text
   due_events(cards, today)
       -> dry_run_events on NEW due events (<= 25, all-or-nothing)
       -> enqueue_events on cloned automation state
       -> preflight_due_batch on SAME queued snapshot and collaboration state
       -> run_batch(limit=safeLimit, max_attempts=3)
       -> host CAS commit if added/processed
   ```

   Due preflight sorts existing due jobs using
   `(nextAttemptAt, queuedAt, eventId)`, selects at most 25, and returns
   `deferred` for the remaining due jobs. A blocked job among the selected
   jobs makes `safeToExecute=False` and `safeLimit=0`. The host must not
   execute *any* selected item or consume attempts after such a verdict.
   The preflight must be made against the same snapshot that the executor
   observes under the host lock and CAS revision.

4. `m07_host_guard` imports `dry_run_events` and
   `preflight_due_batch` **by name** from `rule_safety`. Instrumented tests
   therefore patch `m07_host_guard.dry_run_events` and
   `m07_host_guard.preflight_due_batch`, not the original module attributes.
   They call the real implementations through wrappers and record actual call
   order and arguments. The actual execution functions in `automation_v1`
   are also instrumented, with denial tests raising immediately if reached.

## Acceptance assertions: `tests/test_m07_host_preflight.py`

All tests run an actual `native_app.Bridge` with
`native_app.datadir` patched to a new `tempfile.TemporaryDirectory`.
They opt in to SQLite through `enableUnifiedStorage()` and then
`enableAutomationEngine()`. This creates only temporary working files,
backups and a disposable SQLite database. The test does not start LAN,
connect to Drive, open user APPDATA or alter a release.

| Scenario | Required host behavior |
| --- | --- |
| Pure control, 21 matching events with two actions each | Budget 40 allows only 20, blocks the 21st; preflight reports `action_budget`; SQLite unchanged |
| 26 card-created lifecycle events | `dry_run_events` rejects over `maxEvents=25` **before enqueue**; tasks, finance, collaboration, automation, outbox, SQLite revision/hash unchanged |
| 21 matching events with 42 projected actions | Full save rejected, not partially applied; zero enqueues and zero execution, all domains unchanged |
| Authenticated viewer saving a task event | Trusted `actor/accounts` fail permission preflight before enqueue; no persistent changes |
| Editor granted only another project | Scope check blocks unauthorized card event before enqueue; no persistence |
| Allowed card move matching a rule | Call order exactly **dry-run → enqueue → due preflight → run**; one comment, one receipt; task update committed, finance preserved |
| 26 already queued events in deterministic event-ID order | Inspect first **25** and defer one, invoke runner with `limit=25,max_attempts=3`; 25 processed, one pending, tasks/finance unchanged |
| Queued retry already at `attempts=3` | Due preflight returns `retry_exhausted`, `safeLimit=0`; executor untouched, attempts and entire SQLite revision unchanged |
| Queued job's original actor role revoked | Due preflight returns `permission_denied`; executor untouched, all stored domains and revision unchanged |

After denial, assertions compare five domain dictionaries **and**
`UnifiedSnapshot.revision`/`sha256`; SQLite integrity is checked via
`UnifiedAppStorage.integrity_check()`. This ensures a denial does not
silently persist a partial task write, financial event, retry transition,
receipt, audit entry or collaboration comment.

The positive test uses a real synthetic `rule.upsert` and a real card move,
exercises the Bridge save/commit, and inspects the persisted collaboration
comment, automation receipt and task state. Scheduler tests use real
`automation_v1.enqueue_events` and SQLite CAS to prepare already-queued
jobs, then call `Bridge._run_engine_scheduler`. No `rule_safety` verdict
is faked.

## Local validation evidence

```powershell
py -3.12 -m unittest discover -s tests -p test_m07_host_preflight.py -v
```

**Observed with the Prime's updated local host wiring:** 9 tests, 9 PASS,
0 failures, ~1.9 seconds (synthetic disposable SQLite). Before the current
`m07_host_guard` connection was recognized by the test spies, five assertions
were initially red because the spies were patched at `rule_safety` instead
of at `m07_host_guard` (a Python import-by-name distinction). The tests
were corrected to patch the real call sites and then passed. That earlier
mock-location failure was **not evidence that the updated host guard was
missing**.

## Remaining gates and precise limits

This is verified **local SQLite host behavior only**. It does **not** prove
the legacy JSON path is guarded. In particular, the four-domain/no-automation
branch in `native_app.py` uses a separate collaboration/outbox delivery
path and is outside this test fixture's active-engine scope.

`rule_safety.make_safety_audit` can generate a redacted hash chain but the
current `m07_host_guard.py` does not persist an independent M-07 causal
ancestry or trusted audit head. Its `maxChainDepth`,
`maxRepeatedSignature`, replay safety and stop-loss verdicts are available
in the pure preflight module; full host provenance/causal ancestry and
cross-restart proof require additional integration and tests. A hash chain
without an external trusted head does not provide tamper-proof audit.

Other untested boundaries: a *real* LAN client using session-derived roles,
interleaved two-machine writers, cross-process CAS conflict recovery,
crash-injection during a multi-domain commit, offline scheduler mode,
multi-run stop-loss under persisted audit history, non-default safety policies,
and executable release acceptance. Do not claim physical LAN QA or
production-ready M-07 based only on these tests.

**Integration requirement:** retain the current host lock and single
five-domain SQLite revision transaction; always derive actor/grants from the
authenticated session, rerun preflight on the exact candidate prior to
enqueue/execution and reject when any verdict is blocked. If a future
refactor moves orchestration or changes import aliases, update test spies
to observe the actual entrypoint rather than weakening the behavior
assertions.
