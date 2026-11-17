# E2 legacy account lineage migration (host-only isolated pilot)

This is an explicit Python operation for the **existing authenticated LAN
host administrator**, not a LAN/HTTP endpoint, installer, scheduler, or user
profile action. No old E2 outbox history is remapped, revived, or imported.

## Preconditions

- Stop conflicting external writers. The function holds `LanService.lock`
  against the current in-process LAN account writer, but **cannot** serialize
  an unrelated host process or an external filesystem editor.
- The host's actual private `users.json` exists and matches its in-memory
  registry. No pending user-deletion recovery journal is allowed.
- The caller supplies a currently valid admin session token and a new,
  absolute backup filename **in the same privately OS-ACL-protected
  directory** as `users.json`. Never pass backup paths from a client.
  On Windows, file private ACLs rely on the protected parent directory;
  Unix file creation requests mode `0600`. The function cannot independently
  attest the filesystem ACL policy.
- A legacy account is precisely one where `accountLineage` is *absent*.
  Null, malformed, noncanonical or duplicate existing lineages fail closed,
  not upgraded automatically.

## Callable and contract

```python
from pathlib import Path
from mtr_account_lineage_migration import migrate_legacy_account_lineages

# Illustrative invocation inside a trusted administrative host Python
# procedure. There is no new browser command or production script.
result = migrate_legacy_account_lineages(
    service, admin_token=existing_admin_session_token,
    backup_path=Path("D:/approved-private-host-data/users.before-lineage.bak"),
)
```

The caller must use a real `LanService` (not an arbitrary account dict),
and the service authenticates the admin token and checks the current role
inside its existing lock. Existing canonical lineage values are preserved
exactly; missing values are minted once via the host's cryptographically
secure `new_account_lineage`. Any collision rejects the entire migration.
No username, password, salt, grant, project, role or other stored field is
altered by this operation.

Before `service._publish_users(updated)`, the original `users.json` raw
bytes are copied to a **create-only** file (`O_EXCL`, no overwrite, no
symlink/junction/hardlink source), flushed with `fsync`, re-read, compared
byte-for-byte, and hashed with SHA-256. The source file is checked again
before publication. Publication uses the existing host atomic JSON writer
and its guarded compensation path. On a normal, verifiably compensated
write failure the original exception propagates. If persisted state cannot
be inspected, or memory/disk do not both match the original, an explicit
`AccountLineageMigrationUncertain` is raised and the running host is
stopped from authenticating/serving through its existing recovery hard-stop
guard. **The backup remains intact** for manual reconciliation.

The host's current recovery flag is an **in-process** guard: a restart can
clear it. Before any restart after an ambiguous failure, a trusted operator
must inspect source and backup offline, verify the printed digest using an
independent trusted tool, restore only under a separately approved procedure
and audit the resulting identities. This pilot does not implement a durable
migration transaction marker or an automated rollback/resume service.
Atomicity across separate external filesystem writers, power loss and
directory-entry durability have not been established.

## Security invariants

- An account deleted and recreated under the same username receives a
  completely new lineage and derived E2 actor ID.
- **Old username-owned HostRequestStore rows remain quarantined.** This
  function never reads, updates, or transfers their actor IDs; requesting
  them with the migrated opaque principal is denied by the existing store.
- A migrated account may prepare an entirely **new** E2 request, subject to
  independent host role, session and project authorization.
- Browser/admin user upsert payloads cannot provide `accountLineage`.
  This migration is never exposed as a network command.
- Re-running the migration when every lineage is valid is a no-op: no new
  backup, no regenerated identity, no publication.

## Synthetic validation

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
py -3.12 -B -m unittest -q tests.test_mtr_account_lineage_migration
```

Test suite: 13 disposable host/SQLite tests, including administrator
authorization, exact backup pre-publication and SHA validation, malformed
and duplicate lineage rejection, RNG collision, client injection denial,
registry mismatch/duplicate JSON, backup destination sabotage, failed
`fsync` and backup readback, safely compensated write error, uncompensated
ambiguous save and in-process hard stop, idempotency, delete/recreate,
legacy E2 outbox quarantine and new request creation. A passing synthetic
test is **not** evidence of real Windows ACL security, physical-power-loss
recoverability, or successful production account migration.
