# Madar Desk 1.0: optional fifth automation domain in UnifiedAppStorage

## Status / compatibility contract

`app_storage.py` now accepts either **four legacy domains** or the same four
plus **`automation`** in each *complete* SQLite revision:

| Bundle form | Domains | Accepted? |
|---|---|---|
| Legacy | `tasks, collab, finance, completion_outbox` | Yes, unchanged |
| Opt-in | All four above **plus** `automation` | Yes, atomic CAS |
| Partial or extra keys | Anything else | No |

The journal is validated by `automation_v1.validate_state` before a write
and whenever a revision is read. The first four domains retain their original
validators. The exact old 4-key serialized blobs, SHA-256 digests and historic
snapshots are not rewritten or upgraded by simply opening the database.

**No SQL migration**: SQLite still has `user_version=1` and exactly
`app_revisions`, `app_head` and `app_imports`. The existing revision row
already stores the **entire JSON bundle** as a BLOB and authenticates it with
SHA-256. A five-key bundle fits in that same row. There is no extra table,
separate persistence channel or second transaction. WAL, SQLite
`BEGIN IMMEDIATE`, a single `app_head` CAS update and the immutable revision
history continue to operate as before.

This is backward-compatible with **previous four-domain data, imports and
SQLite backup files when read by the new code**. It does *not* mean an old
four-domain-only release binary can open an activated five-domain revision:
that older validator rejects unknown bundle keys. Do not downgrade the app
binary after enabling automation without a planned restore to an earlier
four-domain backup. Existing backups retain their original bytes.

## Public API, explicitly opt in

```python
from app_storage import (
    UnifiedAppStorage, with_automation, validated_bundle,
    RevisionConflict,
)
from automation_v1 import enqueue_events, run_batch

store = UnifiedAppStorage(explicit_local_sqlite_path)  # Never use APPDATA implicitly
old_snapshot = store.load()                           # None or four-/five-domain snapshot

# Activate only with a host-approved, expected-revision CAS.
# Can also initialize a new DB with store.commit(with_automation(four_bundle), expected_revision=0).
if "automation" not in old_snapshot.bundle:
    upgraded = with_automation(old_snapshot.bundle)
    snapshot = store.commit(upgraded, expected_revision=old_snapshot.revision)
else:
    snapshot = old_snapshot

# The host supplies a session-authenticated actor, not a client-supplied identity.
queue_result = enqueue_events(
    snapshot.bundle["automation"], events,
    actor=trusted_actor, accounts=current_accounts,
    cards=snapshot.bundle["tasks"]["tasks"],
    projects=snapshot.bundle["tasks"]["projects"],
    now="2026-10-21T09:30:00Z",
)
next_bundle = {**snapshot.bundle, "automation": queue_result["state"]}
queued_revision = store.commit(next_bundle, expected_revision=snapshot.revision)

# The engine returns detached collaboration/journal snapshots; save BOTH.
output = run_batch(
    queued_revision.bundle["automation"], queued_revision.bundle["collab"],
    accounts=current_accounts,
    cards=queued_revision.bundle["tasks"]["tasks"],
    projects=queued_revision.bundle["tasks"]["projects"],
    now="2026-10-21T09:31:00Z",
)
new_bundle = {
    **queued_revision.bundle,
    "automation": output["state"], "collab": output["collab"],
}
committed = store.commit(new_bundle, expected_revision=queued_revision.revision)
```

`with_automation(four_bundle, journal=None)` returns a **detached, strictly
validated five-domain bundle**. The default journal is
`automation_v1.empty_state()`. It cannot be called on an already activated
bundle. `validated_bundle(bundle)` accepts both exact shapes; it never
synthesizes a missing automation journal. Size limits remain 15 MB per
domain, 45 MB total for legacy four-key bundles and 60 MB total for activated
five-key bundles.

### CAS, crash consistency and data-loss guards

- `commit(bundle, expected_revision=N)` validates all domains *before* SQL,
  then inserts one checksummed revision and CAS-updates the head in **one
  transaction**. Failure rolls back all domains, including the automation
  queue, audit and receipts.
- Concurrent writers using the same revision cannot both win. A stale writer
  receives `RevisionConflict`; it must **reload, reconcile and retry**,
  never blindly overwrite a newer journal.
- Once a five-domain head exists, a four-domain `commit` is **rejected**
  instead of silently discarding automation jobs. This check runs under the
  same write transaction. An old-history four-domain `restore` over an
  activated head is also rejected: otherwise pending jobs/receipts could be
  lost. Explicit full five-domain `restore` remains supported and appends
  a new auditable revision.
- `load()`, `load_revision()`, `history()`, `integrity_check()` and
  WAL-aware `backup_database()` recognize both historical forms. Opening
  a four-domain DB does not change any existing snapshot.
- `import_legacy(...)` **still imports the original four domains only**,
  with byte-exact backup-first behavior and its pre-existing import manifest.
  Activate the fifth domain in a **separate CAS revision after successful
  import**. Retrying the same legacy import returns the current head without
  reverting the automation journal.

### Required Prime/host integration

The five-domain durable storage contract is available. It is **not yet wired
into `native_app.py`, `lan.py`, the React UI, or the running EXE**.
Prime must select this storage opt-in, use latest revisions for the host's
read/edit cycle, and commit task edits and their generated automation events
in **the same five-domain write**. Likewise, applying
`automation_v1.run_batch()` must commit both returned `collab` and
`automation` states atomically, not two separate files. Enforce authenticated
roles before journal operations, especially administrative retry and history
inspection. Never expose raw journal/receipts to unauthorized LAN users.

The existing Windows lifecycle engine already generates automation events
through its own path. Prime needs to coordinate that publisher with this
journal to prevent two independent delivery systems, even though collab
receipts make identical event IDs replay-safe.

No implicit export, Drive backup, scheduler thread, LAN route, migration
execution or UI switch is added here.

## Verification

All tests use synthetic data, disposable SQLite files and explicit paths.
No real profile, APPDATA or Git operations:

```powershell
python -m unittest discover -s tests -p test_automation_storage.py -v
python -m unittest discover -s tests -p test_app_storage.py -v
python -m unittest discover -s tests -p test_automation_v1.py -v
```

The new suite checks the unchanged old schema and snapshots, explicit
activation, no journal downgrade, import and byte-exact legacy source backups,
atomic five-domain commit and replay, reopen, WAL rollback after SQL trigger
failure, forced process exit before COMMIT, concurrent CAS conflict, audit,
old/new SQLite backups, five-domain history restore, and malformed journal
rejection. These tests do **not** prove the full host UI/LAN/EXE integration;
they verify the storage boundary and its API only.
