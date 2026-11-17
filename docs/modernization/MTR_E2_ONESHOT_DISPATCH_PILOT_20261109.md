# E2 host-side one-shot dispatch gate: synthetic, in-process pilot

**Decision:** First physical-send attempt requires a durable reservation before
network activity. Never infer nonreceipt from timeout, process termination,
missing HTTP response or a stale client status. Once reserved, the first slot
is consumed, including when the process crashes *before* transmission.

**Baseline and ownership:** isolated shared Madar worktree `32bd8ff`; only
NEW `mtr_e2_dispatch_gate.py`, `tests/test_mtr_e2_dispatch_gate.py`, and this
document. No changes to existing LAN, `HostRequestStore`, Taraz peer/client,
workers, UI, real data or installed service. No commit, push or deploy.

## Existing contract and integration

`mtr_host_request_store.HostRequestStore.manual_send` persists the explicit
`MANUAL_SEND_AUTHORIZED` **intent**, not a peer send. Its scoped
`request_snapshot(principal,request_id,expected_base_revision)` returns the
host-validated org/project, stable request ID, actor/session-bound request,
SHA-256 of prepared metadata, base revision, `sendKey` and outbox observation.

`OneShotDispatchGate(path: Path, outbox: HostRequestStore)` uses an explicitly
selected absolute SQLite database path independent of the outbox. Callers must
hold an authenticated host-derived `TrustedPrincipal`, must supply the actual
server-authoritative current revision, and must not deserialize principal or
`current_server_revision` from browser-supplied claims. The gate delegates
actor/session/org/project/read ACL validation to `HostRequestStore` at each
operation, and additionally requires the `mtr.manual_send` permission and an
admin/editor/finance_submitter role before any reservation or transition.

API:

1. `reserve_once(principal, request_id, expected_payload_sha256,
   expected_base_revision, current_server_revision, send_key)` performs
   `BEGIN IMMEDIATE`, re-reads the source outbox, checks
   `MANUAL_SEND_AUTHORIZED`, `receiptState=unknown`, exact SHA/revision/key,
   and inserts one globally unique (within this SQLite authority) `request_id`
   row bound to org, project, actor, session, payload SHA, base revision and
   stable send key. Both request and send key are UNIQUE across this gate DB.
   After an immutable audit insert and committed transaction, only the very
   first successful call returns `firstAttemptGranted=True`. Another call,
   including the same principal/send key, **raises** `DispatchGateConflict`;
   there is no idempotent resend of the grant. The response's
   `reservationConsumed=True` and `mayDispatch=False` reflect the **persisted
   state after consuming** the one-shot permit. The host integration must
   consume the transient first-call result exactly once and never cache or
   expose it as a reusable client dispatch capability.
2. `status(principal,request_id,expected_base_revision)` is read-only and
   returns current in-scope state without revealing another session. As soon
   as any reservation exists, `reservationConsumed=True`, `mayDispatch=False`
   and `mustQueryFirst=True` until authoritative receipt observation.
3. `mark_unknown_after_attempt(...,expected_version)` uses compare-and-swap to
   record an externally reported uncertain attempt outcome. This state does
   **not** itself certify any network packet was transmitted. It never grants
   retry authority.
4. `observe_received(...,expected_version)` reads the existing authenticated
   HostRequestStore snapshot under the gate writer transaction and advances
   to `observed_received` only if that source has already recorded
   `receiptState=received` with a correlated receipt ID. Repeated same-version
   observation is read-only. `HostRequestStore` already validates its own
   recorded observation; this gate still cannot independently authenticate
   any Taraz peer or receipt.
5. `audit_events(...)` exposes the current authorized request's local history.
   `backup_to(absolute_new_path)` creates and verifies a **non-overwriting**
   SQLite backup. The copied database has `first_permits_enabled=0` so even a
   pre-reservation backup reopened as a gate is **query-only** and cannot
   silently issue a first permit after an offline restore. The original gate
   remains enabled. There is no automatic backup or restore job.

## Persistence invariants

SQLite uses `BEGIN IMMEDIATE`, `synchronous=FULL`, `foreign_keys=ON`, bounded
schema with `user_version=1`, `quick_check`, and SQL constraints. Audit is
append-only by explicit UPDATE/DELETE rejection triggers. Reservation deletion
is forbidden and a transition trigger prevents altering principal/project,
SHA, revision, stable key or downgrading state. The application checks a
complete audit version chain on reads. Valid transitions are:

```text
no record -> reserved_before_network (v1, first slot consumed)
reserved_before_network -> unknown_after_attempt (v2)
reserved_before_network -> observed_received (v2, observed via outbox)
unknown_after_attempt -> observed_received (v3, observed via outbox)
```

No path from any reserved state issues another first grant. A confirmed
`not_received` outbox query does **not** automatically enable another send.
No network, SMS, email, token, credential, finance database, Taraz call,
official ledger entry, real receipt or financial document is created.

## Observed synthetic evidence, 2026-11-09

Windows Python 3.12 from this isolated worktree, per-test
`TemporaryDirectory` host outbox and dispatch SQLite, disposable environment
paths (`APPDATA`, `LOCALAPPDATA`, `USERPROFILE`, `HOME`, `TEMP`, `TMP`).

```powershell
py -3.12 -B -m unittest discover -s tests -p test_mtr_e2_dispatch_gate.py -v
py -3.12 -B -m unittest discover -s tests -p test_mtr_host_request_store.py -v
git diff --check
```

Observed: **19/19 new gate tests passed**, **34/34 existing HostRequestStore
tests passed**, three commands exit **0**. New tests include one-shot replay,
lost response before network, uncertain outcome after restart, stale SHA/key/
revision, role/session/tenant/project ACL, global request identity collision
across two source databases, SQL audit immutability, transaction rollback on
audit fault, corruption/schema denial, outbox positive/negative observation,
read-only backup and restart, 12 racing threads and 4 independently spawned
Windows processes. Exactly one of each concurrent group obtained the first
reservation; no secondary dispatch grant was returned in those tests.

Earlier local run initially had 15 setup errors due to using exact `Path`
type equality on Windows; changed to `isinstance(Path)` and repeated tests.
Later one assertion expected a conflict on a query-only backup, whereas the
new restriction correctly raised `PermissionError`; this assertion was
corrected and final evidence above is the clean rerun. No full product suite,
live peer test, power-loss simulation or physical LAN delivery was run.

## Trust limitations and release gates

1. **Cross-database atomicity:** `HostRequestStore` and this gate commit to
   separate SQLite files; the read of `request_snapshot` inside the gate's
   `BEGIN IMMEDIATE` does **not** create an atomic transaction with the outbox
   or remote network. Outbox revocation, receipt observation or source changes
   could race between validation and reservation. Host integration needs a
   consistent synchronized origin and version check around this step.
2. **Physical dispatch enforcement:** This module does not and cannot prove
   that a caller used a returned first permit just once. The external trusted
   host must atomically consume the result in its sole dispatch path, deny all
   bypass routes and query the peer on every uncertainty. There is no actual
   Taraz connection, and no integration or transport enforcement yet.
3. **Global scope and recovery:** Unique IDs are global only for actors sharing
   the same gate database. Separate hosts/gates, arbitrary raw file rollback,
   filesystem administrator tampering and a restored outbox not aligned with
   the dispatch gate remain unprotected. Copies made by this API are
   query-only, but external raw snapshots cannot be distinguished reliably.
   Operational recovery must fail closed until both stores are reconciled
   against authoritative peer query results. Independent backup/restore and
   power-loss validation are still required.
4. **Receipt provenance:** `observed_received` trusts the outbox's previously
   attested `record_query_result`. Neither a boolean verification flag nor a
   received state proves cryptographic origin. Real peer authentication,
   signature/correlation and independently verified financial receipts remain
   prerequisites to production acceptance.

**Verified boundary:** synthetic host-side reservation and local SQLite
transition tests only. No real user, finance, peer, host install, release,
commit or push was touched.
