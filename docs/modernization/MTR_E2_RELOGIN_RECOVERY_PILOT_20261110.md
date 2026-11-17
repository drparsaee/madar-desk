# E2 re-login recovery: fail-closed pilot and host-store API blocker

**Historical worker-scope status: BLOCKED for positive re-login recovery in the original APIs.** The later same-day integrated read-only store/gate extension has since demonstrated same-actor relogin in a synthetic peer test; see `MTR_E2_RELOGIN_AUTHORIZED_RECOVERY_20261110.md`. This document below preserves the earlier worker's limits and evidence and must not be mistaken for current coordinator capability. Date: 2026-11-10. Shared
Madar worktree baseline `32bd8ffe5ebbb0f4cd5c011c59323ed32f8647ac`.
Owner permits **only new** `mtr_e2_recovery_policy_pilot.py`, its new test and
this document. This is a design/local policy test, **not** a mounted route,
an operational peer query or a production recovery implementation.

## Verified source boundary

* `mtr_lan_finance_adapter.py:52-85` derives user, organization, current
  project grants and session ID from the **currently authenticated host
  token**. Session ID is `sha256(token)`; a legitimate re-login changes it.
* `mtr_host_request_store.py:468-473` requires **both original actor ID and
  original session ID**, in addition to current organization/project/role/
  capability. `request_snapshot` (`686-705`) calls this check. It has no
  reviewed current-session-recovery read method.
* `mtr_e2_dispatch_gate.py:250-288,412-432` requires the same outbox snapshot
  and compares durable original `org_id`, `project_id`, `actor_id`,
  `session_id`, `payload_sha256`, `base_revision` and `send_key` to the
  caller's principal and outbox snapshot. Its `status` rejects new sessions.
* `mtr_e2_host_peer_pilot.py:152-184` still invokes those session-bound
  readers and optionally a peer query. The new policy makes **no call** to
  this transport/peer class. Current `query_first` also requires the current
  task to remain in its original project, despite already ignoring changed
  titles and revisions.

**Consequence:** No existing authorized public store/gate API can return the
original request metadata to the same actor **after re-login**. Reconstructing
`TrustedPrincipal` with the *old* session ID would forge session authority;
opening either private SQLite DB directly would bypass checked ACL and
corruption validation. Both would defeat the HIGH-security finding. Therefore
the positive re-login requirement **cannot safely be fulfilled in this file
ownership scope**. Do not claim the targeted behavior is implemented.

## Scoped implementation in the permitted new module

`MtrE2RecoveryPolicyPilot.inspect_existing(...)` only accepts the host-owned
`MtrLanFinanceAdapter` and `OneShotDispatchGate` sharing the **same actual
HostRequestStore object**. It authenticates an active token via
`_principal_and_task` under `service.lock` and `bridge._lock`, then asks the
original, ACL-enforcing `request_snapshot` and `gate.status`. It verifies the
original request, project, actor/session indirectly through existing APIs,
base revision, payload SHA and send key against the persisted gate/outbox.
After inspecting the original authorized reservation, it returns **only local
metadata**: original project and revision, payload digest, *hash of* the send
key, gate state, query-first decision and explicit `mayDispatch=False`,
`canAutoRetry=False`, `canResend=False`, `transportCalled=False` flags.
No raw payload/title, financial values or original session identifier are
returned. No HMAC signing, network traffic, peer query, receipt mutation,
reserve/retry operation, route, fake original principal or direct private DB
read exists in the new module.

The original session can still read after a title change or board/list move
**within** the original project: the stored original `baseRevision` is used
for the query, not the changed card hash. Relogin, project reassignment,
revocation, changed source/gate evidence, missing reservation, wrong actor or
wrong organization are all denied. For re-login, denial is **by design until
the missing host-store capability is reviewed**; it is not a workaround.

## Minimal next implementation gate for the owning store/host agents

1. Add a **host-only, read-only** `recovery_snapshot` API at the outbox boundary.
   It must authenticate the **current** host session; look up the immutable
   `request_id`; verify stored original actor == current actor, original org
   == current org, the **original project** is still in current grants, live
   role/capabilities remain authorized, and row/payload/audit corruption
   checks succeed. Do not accept actor, org, original session, grant booleans
   or preverified evidence from client JSON. Return bounded original metadata
   including original session **internally only**, never a resend token.
2. Add an independently authorized **read-only** gate recovery status path
   with the same current host authentication; strictly compare the outbox and
   gate's *original* `request_id/org_id/project_id/actor_id/session_id/
   base_revision/payload_sha256/send_key` and state/audit history. This must
   never issue a `firstAttemptGranted` permit or call `reserve_once`.
3. The host should serialize current-grant and original-project validation
   with other host authorization transitions; use the saved **original
   project ID**, not the card's currently mutable title or project. A moved
   card does not change historical request authority; revoked original grant
   denies recovery. A mismatch/corruption between separate SQLite databases
   fails closed. The cross-DB transaction/backup-epoch gap remains unresolved
   until independently reviewed recovery/coordination semantics exist.
4. Expose **query only** (if separately owner-authorized) using the immutable
   original request and a verified signed-peer query protocol. Receipt
   `unknown` and `not_received` do **not** authorize a second dispatch;
   never enable automatic resend. Keep finance ledger, transport credentials,
   and operational service access out of this policy pilot.

This is a contract for other owners, **not** permission for this worker to
modify their files or to mount a route.

## Synthetic verification

Command (PowerShell wrapper sets `APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`,
`HOME`, `USERPROFILE` to a unique disposable temp root and sets
`PYTHONDONTWRITEBYTECODE=1`; the variables and root are cleaned afterwards):

```powershell
py -3.12 -B -m unittest discover -s tests -p test_mtr_e2_recovery_policy_pilot.py -v
```

Observed **12 tests, 12 passed, 0 failures/errors, exit 0**. Tests cover
original-session query-only access, no second dispatch grant, stable historical
metadata after title/list/board changes, same-actor re-login **denial** and
direct proof both public store/gate APIs deny it, revoked session/project/
role/finance grant, wrong actor/org, cross-project move, expected revision/
SHA/send key mismatch, missing gate reservation, mismatched outbox/gate, and
synthetic persisted outbox payload tampering. The test-only tampering opens
**only its own disposable SQLite fixture**; the production module never does.

An intermediate run exposed a **test-only** Windows file handle leak because
`sqlite3.Connection` context management does not close the file; the test
fixture now uses `contextlib.closing`, and the stated 12/12 result is from
the rerun after correction. No production files were modified.

The **adjacent unchanged** modules were also run in the same kind of fresh
disposable environment:

```powershell
py -3.12 -B -m unittest discover -s tests -p test_mtr_e2_dispatch_gate.py -q
py -3.12 -B -m unittest discover -s tests -p test_mtr_host_request_store.py -q
```

Observed **19/19** and **34/34** respectively, each exit 0; **65/65 total**
across three separately executed test modules. This is limited regression
evidence, not a full-suite or live integration test.

## Limitations

The synthetic host emulates `account_for()` and current project grants and
does not start a LAN service or contact Taraz. Passing tests prove only this
local negative/read-only policy, not positive re-login recovery, live host
authentication, cross-process atomicity, signed query correctness, actual
backup recovery or production release. **High severity relogin recovery gap
remains BLOCKED pending reviewed store/gate host-only read APIs.**
