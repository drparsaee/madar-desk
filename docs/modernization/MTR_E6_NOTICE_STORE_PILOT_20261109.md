# E6 internal notice inbox: local durable SQLite pilot

**Scope:** Owner-authorized standalone E6 pilot for Refine 6.26, 6.28 and
6.29 (especially AC-31 and G-01/G-07). **No production integration or
accounting action**. Worktree baseline: Madar `32bd8ff`.

## Inputs and responsibilities

Source: `mtr_internal_notification_policy.plan_internal_notifications`.
The new `mtr_internal_notification_store.InternalNotificationStore` accepts
only the exact internal-only plan shape emitted by that pure policy. It
deliberately **does not** accept references to official receipts, financial
documents, external URLs, mail addresses, SMS, cloud destinations, ledger
actions or arbitrary extra payload fields.

The caller supplies the **absolute location** of a new SQLite database;
there is no automatic discovery or use of a real Madar profile. The parent
folder must exist, and file/parent symlinks, reparse points and nonfiles are
rejected. The caller must explicitly supply:

1. `HostPrincipal` with host-verified, authenticated organization, operator,
   role, permitted project IDs, field visibility, operation rights and
   verified event actor (when publishing).
2. `HostRecipientGrant` for each recipient, including host-attested
   organization, project/request access, role, allowed notice fields and
   internal-notification consent.
3. An authorized `project_id` and an unmodified or equivalent
   `plan_internal_notifications` decision.

**Critical trust boundary:** Python dataclasses and `host_verified=True`
are **not proof of authentication or of finance provenance**. Only a
real authenticated MadarHost backend can construct trustworthy objects.
Client-supplied principals, ACLs, source actors or policy plans must never
be accepted as host assertions. A plan is a *notification suggestion*, not
authorization to post to Taraz or proof of an official receipt.

## Persistence behavior

- `publish_plan(plan, *, principal, project_id, recipient_grants)` checks
  organization/project/request/actor, role, current recipient entitlements,
  field grants and exact internal-only shape **before** writing anything.
  An invalid recipient fails the whole batch.
- SQLite writes execute inside `BEGIN IMMEDIATE` transactions with
  `synchronous=FULL`, `journal_mode=WAL` and
  `UNIQUE(organization_id, recipient_id, event_key)`.
  A repeat with the same immutable payload and verified event actor returns
  `replayed`, not another notice or audit event. Reusing the key with changed
  payload/project/request/actor raises `NoticeConflictError` and rolls back
  all newly inserted rows in that batch.
- `list_notifications(*, principal, project_id=None, recipient_id=None)`
  returns only the authenticated principal's own notices for their authorized
  organization/projects, bounded to 100; current field grants are applied
  again at read time. A project or another recipient cannot be selected
  without matching host authorization.
- `mark_read(notice_id, *, principal)` requires the current user's own
  project and recipient access. Read acknowledgment appends one immutable
  `inbox_reads` and one `inbox_audit` event; re-marking the same notice is
  a no-op. Notice bodies, inserted audit and read rows cannot be modified or
  deleted through ordinary SQLite UPDATE/DELETE because of database triggers.
- All storage is **internal only**. No email/SMS/cloud API, network,
  financial ledger operation, request submission/resubmission, notification
  transport, push service or Taraz posting exists in this module. Financial
  references are **not ingested or displayed**, even if a caller invents
  an unverified reference field.

Audit events record operator and recipient identifiers, event key, project,
payload hash and locally recorded time. This is an append-only local audit
within SQLite, **not** a cryptographically signed, independently tamper-proof
audit log. A filesystem administrator or compromised host may replace,
edit or delete the database outside this API.

## Recorded synthetic tests

Executed with Python 3.12, using `safe_test_runner.isolated_environment`
around a subprocess and per-test disposable `TemporaryDirectory` databases:

```powershell
py -3.12 -B -m unittest discover -s tests -p test_mtr_internal_notification_store.py -v
```

**Observed result:** 18/18 tests passed, exit 0, in 2.396 seconds.
Covered: policy-generated notices, duplicate same-payload restart replay,
conflicting payload with full rollback, recipient/tenant/project IDOR,
viewer access and revoked-field redaction, mark-read persistence,
UPDATE/DELETE denial on all three tables, malformed database/path denial,
failure to ingest unverified financial references or external channels,
8 racing threads and **4 real Windows child processes** producing one
insert and one insertion audit event across the same DB.

**Not tested/blocked:** real authenticated host identity, tenant/project ACL
enforcement upstream, genuine Taraz receipt or actor provenance, actual
event-key generator/trust, signature/replay protection, hostile filesystem
replacement or hard power loss, encrypted data at rest, audit retention,
physical LAN and GUI delivery, packaging, installation, release, operational
backup/readback/restore. A SQLite unit-test success does **not** complete E6.
No live profiles, finance data, existing source, OS services or credentials
were changed; no commit, push or deployment.
