# Madar Desk 1.0: bounded automation execution engine

## Current implementation

`automation_v1.py` is an **opt-in pure Python orchestration layer**. It does
not start a thread, open a port, schedule a system timer, read disk, touch
`APPDATA`, or modify `native_app.py`. The host supplies the authenticated
actor, authorized accounts, current cards and projects, an offset-aware time,
and a transactionally persisted journal. It reuses:

- `automation_due.due_events` for deterministic per-day due-date triggers.
- `automation_events.card_change_events` as the caller's existing lifecycle
  event source. This function is already used during task saves.
- `collab.apply_command` for the **only** executable command type:
  `event.publish`. Existing role/project checks, rule ownership checks,
  rule conditions, notifications/comments, action allowlist, and durable
  `collab.receipts` remain authoritative.

The engine **does not** execute arbitrary Python, shell, JavaScript, HTTP,
webhooks, arbitrary card changes, financial actions, or user-supplied rule
commands. Invalid operations fail closed. No new UI, LAN endpoint, background
scheduler service or shipping EXE is implemented by this worker.

## Public API

```python
from automation_v1 import (
    empty_state, validate_state, enqueue_events, enqueue_due,
    run_batch, retry_dead,
)

# The host must obtain actor from the authenticated request/session.
# Do NOT copy actor or role from an incoming client event.
engine = empty_state()
queued = enqueue_events(
    engine,
    card_change_events(before_tasks, after_tasks),
    actor=authenticated_actor,
    accounts=authenticated_accounts,
    cards=after_tasks["tasks"],
    projects=after_tasks["projects"],
    now="2026-10-21T08:00:00Z",
)
engine = queued["state"]  # queued["added"], queued["duplicates"]

# Today's local calendar day must be supplied by the host. This does NOT
# use your system clock implicitly and emits no new tasks on its own.
queued = enqueue_due(
    engine, after_tasks["tasks"],
    today=date(2026, 10, 21),
    actor=authenticated_actor, accounts=authenticated_accounts,
    projects=after_tasks["projects"], now="2026-10-21T08:00:00Z",
    horizon_days=7,
)
engine = queued["state"]

result = run_batch(
    engine, collab_state,
    accounts=authenticated_accounts, cards=after_tasks["tasks"],
    projects=after_tasks["projects"], now="2026-10-21T08:01:00Z",
    limit=25, max_attempts=5, offline=False,
)
new_engine = result["state"]
new_collab = result["collab"]
# Metrics: applied, replayed, retried, dead, processed.
```

Execution returns detached, validated state. When `offline=True`, it returns
unchanged detached copies without consuming an attempt, changing audit, or
running a rule. The host must persist the queue before claiming an event was
accepted and must persist every returned engine/collaboration change.

### Durable commit / crash recovery

**Preferred:** commit the engine journal and collaboration snapshot in the
same database transaction under a single CAS revision. An event-generating
task write and its corresponding queue event should likewise be committed
atomically so a crash cannot lose an event after the card has changed.

`app_storage.py` currently permits **exactly four** bundle domains:
`tasks`, `collab`, `finance`, `completion_outbox`. It does **not** yet
include this automation journal. Storing it in that bundle requires explicit
Prime coordination to expand the schema and migration. Do not silently embed
automation data into sensitive domains or include it in a non-admin LAN view.

If a transitional integration writes two local snapshots separately, persist
**collaboration first, then the engine journal** after `run_batch`. When a
crash occurs after the collaboration write, replaying the old engine journal
with the newer `collab.receipts` produces a `replayed` result, not a second
comment or notification. This compensates for that *specific* interruption.
Writing the engine first can lose actions; it is not supported. Atomic
enqueue/task persistence is still needed to guarantee that no card event is
lost. All read/apply/commit operations must be serialized by the host lock or
CAS; concurrent consumers must not apply stale snapshots.

Persist `engine` as strict JSON and restore it with `validate_state(engine)`
before use. Job IDs and receipts survive JSON roundtrips/restarts. Duplicate
event IDs with different actors or payloads raise `ValueError`; identical
requeues do not produce new audit entries. Receipts and audit are intentionally
retained to prevent delayed duplicate events after a restart. There is no
automatic pruning because forgetting idempotency keys silently weakens
exactly-once semantics. Capacity exhaustion fails closed; maintenance needs
an explicit, reviewed retention/replay policy.

## Retry, dead letters and audit

Enqueueing records `queued`. Delivery records `applied` or `replayed`.
`RuntimeError` from the collaboration execution boundary is treated as a
transient failure and scheduled for retry after 60, 120, 240 ... seconds up
to 3600 seconds (bounded by `max_attempts`). A `PermissionError` or
`ValueError` is terminal and becomes a retained `dead` job; revoked
permissions are never bypassed.

Each queued event also stores its card's original project ID. If the card
is moved to another project before delivery, the job becomes `dead` with
`project_changed`, rather than executing rules in a different project.

`retry_dead(engine, event_id, *, now)` resets a dead letter explicitly.
It has **no internal user authentication**. Expose it **only behind a host-side
admin permission check** and an authorized journal transaction, never directly
to a client. The next delivery re-checks actor role, rule owner and project
scope. A disabled or revoked-owner rule cannot be silently escalated.

The journal schema is:

```json
{
  "schemaVersion": 1,
  "jobs": [],
  "audit": [],
  "receipts": {},
  "nextAudit": 1
}
```

Each job contains only an allowlisted event command, host-supplied actor,
fingerprint, retry fields and timestamps. Audit tracks sequence, event ID,
outcome, attempt, a **fixed error code** and offset-aware time. Error messages
and financial values are not copied into audit entries. It is an operational
log, not a tamper-proof signed record. Account and project permissions are
revalidated at execution.

Current bounds: 500 events per enqueue, 1000 queued/dead jobs, 100 jobs per
run, 8 maximum attempts, 10,000 audit entries, 10,000 receipts and a 15 MB
serialized journal cap. Rule limits inside `collab` still apply (20 matching
rules/50 actions per event).

## Integration checklist for Prime

1. Decide where to persist the journal with a host-only secure storage scope.
   Provide backup/restore and crash recovery consistent with the active host.
2. On authorized card updates, calculate `card_change_events(before, after)`
   and enqueue with authenticated actor **in the same durable card transaction**.
   Existing automatic event delivery in `native_app.py` must be coordinated
   to prevent maintaining two competing event publishers.
3. On a host-owned scheduler tick, call `enqueue_due(..., today=local_day)`,
   then `run_batch` with fresh actor/account/card/project snapshots.
4. Persist `collab` and automation journal in one revision/CAS. Support
   offline or interrupted replay without dropping receipts.
5. If exposing run history or dead-letter retries to UI, permit only authorized
   administrative access. Reader LAN state must not expose rule recipients or
   private notification data.

### Validation evidence

Run without real profile or APPDATA:

```powershell
python -m unittest discover -s tests -p test_automation_v1.py -v
```

`tests/test_automation_v1.py` covers queued event delivery, rule action
matching, notification/comment deduplication, JSON restart, stale journal vs
committed collaboration replay, offline ticks, transient retry and terminal
dead letters, authorization revocation, owner role changes, due dates, bounds,
invalid commands, malformed journals and all-or-nothing queue operations.
Tests are deterministic and run as pure in-memory state. They do not prove
Windows GUI behavior, concurrent host transaction wiring, live LAN operation,
or EXE packaging. Those integrations remain for Prime.
