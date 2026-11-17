# MTR E6 LAN host notice adapter: isolated in-process pilot

**Scope:** Three new files only, shared dirty worktree based on `32bd8ff`.
No existing LAN/React/Taraz sources were edited, and no service, real user
profile, real finance database, LAN listener or installed application was touched.
No commit, push or deployment.

## API and trust boundary

`mtr_lan_notification_adapter.MtrLanNotificationAdapter(
service, store, *, org_id, trusted_event_source)` takes an existing
`InternalNotificationStore`, host-owned organization ID and a **host-installed**
callable `trusted_event_source(event_key)`. That callable must obtain a durable,
authenticated `TrustedHostNoticeEvent` from a host journal. A frozen Python
dataclass is **not** evidence of event integrity, source authentication, or
an actual Taraz receipt. This pilot does not provide a trusted event journal.

In-process methods:

- `publish(token, event_key)`: resolves the event from the host callback using
  the caller's key only as a selector. It never accepts client event details,
  recipient lists, actor/role claims, organization IDs, plan dictionaries or
  finance references. Under the existing `service.lock` then
  `service.bridge._lock`, it calls `service.account_for(token)` and verifies
  that account against the current `service.users` registry. It takes projects,
  card/task assignment and current card contents from `bridge.getState()`,
  checks the saved-card SHA-256 against the trusted event snapshot, rejects a
  stale event or unrelated editor, and checks the event actor is a current
  editor/admin of the project. It constructs the policy input and store's
  authenticated `HostPrincipal`/`HostRecipientGrant` internally. The real
  `plan_internal_notifications` policy and SQLite `publish_plan` validate and
  persist only internal notices. Atomic replay protection is enforced by the
  store's per-recipient UNIQUE event key and payload comparison; the policy's
  preliminary dedup set is deliberately empty to allow conflict detection.
- `list_notifications(token, *, project_id=None, limit=100)`:
  reauthenticates the session, rechecks current project grants, enabled inbox,
  role and private-field ACL; the store returns current user's records only.
  Unverified financial approval/posting statuses are masked on display.
- `mark_read(token, notice_id)`: reauthenticates and uses the existing store's
  scoped, append-only read acknowledgement. Another user's ID is rejected.

Recipient selection is server-derived: same project, explicitly enabled in
the trusted user registry (`internalNotificationsEnabled is True`) and either
admin or currently assigned to the saved task. `internalNotificationFields`
may further **reduce** the user's role ceiling, never widen it. Default
role ceilings: admin gets status, actor, amendment ID and deficiency summary;
editor gets status, actor and amendment ID; viewer gets status only. Unknown
account, malformed grants, stale projects, unsupported role or malformed
per-user field caps fail closed. The adapter refuses finance approval,
rejection and official posting status transitions because no independent
Taraz provenance is available. No receipt or document ID is produced.

**Current wiring limitation:** `LanService` supports `account_for` and a host
user registry but does **not** currently expose this new event journal or
management/persistence flow for `internalNotificationsEnabled` and
`internalNotificationFields`. With the flag absent there are zero recipients
and inbox reads are forbidden. The integration is not mounted as a LAN route;
no new endpoint, email, SMS, external network traffic, finance operation,
resubmission or reminder was introduced.

## Evidence, 2026-11-09

Executed from the isolated Windows worktree, Python 3.12 with disposable
`TemporaryDirectory` SQLite files and synthetic test host/state. One test
constructs a real `LanService` without starting a listener, authenticates a
synthetic owner, uses its actual `account_for` and then revokes that session.

```powershell
py -3.12 -B -m unittest discover -s tests -p test_mtr_lan_notification_adapter.py -v
py -3.12 -B -m unittest discover -s tests -p test_mtr_internal_notification_store.py -v
py -3.12 -B -m unittest discover -s tests -p test_mtr_internal_notification_policy.py -v
```

Observed in the run: **20 + 18 + 18 = 56 tests, all passed**, each command
exit code **0**. Adapter cases cover host authentication, real synthetic
`LanService.account_for`, spoofed/expired sessions, source field injection,
actor and project scope, assignment and hash revision, per-user sensitive
field redaction including revocation, enabled flag, cross-user read ACK,
changed-payload conflicts, replay after SQLite restart, concurrent writers,
deficiency-only handling and refusal to claim official finance status.

## Release limitations

The trusted event provider's authenticity, journal append-only history,
status/revision provenance and correlation between financial request ID and
the saved task remain upstream responsibilities. The task hash proves only
agreement with the current saved task bytes; it cannot prove a historical
status transition or an official Taraz acknowledgment. This adapter assumes
one organization configured for the host, since `LanService.users` has no
per-user tenant membership contract. After publication, an otherwise still
project-authorized recipient may retain access to their historical inbox
even if removed from a task; new publications use current assignment. SQLite
dedup is per recipient, not a global immutable audience snapshot, so adding
new authorized recipients to a previously published event remains possible.
Host-level event recipient/audience versioning and retention policy are
required to close that release gate. Real TLS, multi-host deployment,
encrypted persistence, installer integration, physical delivery and recovery
from power loss were not tested by this adapter suite.
