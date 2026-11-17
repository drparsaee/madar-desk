# E2 re-login recovery: independent source/security QA (2026-11-10)

**Verdict:** current re-login path has meaningful positive/negative protection
in synthetic tests, but two important **in-process identity-trust findings**
remain. A passing test suite here must not be interpreted as security approval
or release readiness.

**Scope:** shared Madar worktree
`D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107`,
HEAD `32bd8ffe5ebbb0f4cd5c011c59323ed32f8647ac`. The four existing
`mtr_host_request_store.py`, `mtr_e2_dispatch_gate.py`,
`mtr_lan_finance_adapter.py`, `mtr_e2_host_peer_pilot.py` and neighboring tests
were **read-only**; only NEW
`tests/test_mtr_e2_recovery_security_20261110.py` and this NEW note were
authored. No listener, actual peer, live profile, real ledger, existing code
edits, commit, push or deployment.

## Verified current implementation

- `MtrLanFinanceAdapter._recovery_principal` at
  `mtr_lan_finance_adapter.py:87-133` asks current `service.account_for(token)`,
  enforces admin/editor and editor `financeEdit`, reads currently saved project
  registry, intersects current project grants, hashes the *current* bearer
  token into session ID, and grants **only `mtr.read`**. It does not derive a
  principal from request/browser JSON. The ordinary prepare/send path remains
  separate.
- `HostRequestStore.recovery_snapshot` at
  `mtr_host_request_store.py:707-739` validates the current principal's
  authenticated/active/session-valid flags, read role/capability, **original
  organization and project**, **same original username**, original revision
  and prior `MANUAL_SEND_AUTHORIZED` state; it reads validated canonical
  metadata without opening a send slot.
- `OneShotDispatchGate.recovery_status` at
  `mtr_e2_dispatch_gate.py:434-461` compares the recovered original outbox
  org/project/actor/**original session**/SHA/revision/send key against the
  durable reserved row and validates reservation audit. `reserve_once`
  remains original-session-bound and a consumed slot cannot be granted twice.
- `MtrE2HostPeerPilot.query_first` at
  `mtr_e2_host_peer_pilot.py:156-193` uses those two readers and immutable
  original task identity, without requiring a currently existing card. This
  read-only metadata query does not call a send/replay operation. **The test
  substitutes an in-memory peer** and a synthetic signed-envelope return;
  no real HMAC, TLS, Taraz peer or official receipt is verified here.

## Findings (severity conditional on trust boundary)

### F1: Principal forging possible for an in-process caller (HIGH if untrusted code reaches store/gate)

**Observed:** `TrustedPrincipal` is an ordinary constructible dataclass
(`mtr_host_request_store.py:172-200`). The standalone public Python methods
`recovery_snapshot` and `recovery_status` accept a freshly constructed
principal with `authenticated=True`, `session_valid=True`, `role='admin'`,
an arbitrary new `session_id`, the right username/org/project and `mtr.read`.
The synthetic test directly constructed this principal **without calling
`service.account_for`**, and successfully read the original session identifier,
raw send key and historical payload/title. The one-shot gate still returned
`mayDispatch=False`.

**Scope of certainty:** an in-process call that controls those fields bypasses
**host authentication provenance**. This does **not** prove that HTTP,
pywebview, a low-privilege desktop user or another process can construct or
submit such a principal to these internal methods. No route exposing this
recovery API was found in the inspected `MtrLanFinanceAdapter.handle`
(`_ROUTES` remains prepare/manual-send/status). Actual exploitability requires
reviewing all composition roots and third-party in-process callers.

**Minimum remediation:** enforce an unforgeable host-internal principal
provenance boundary (or a narrowly scoped trusted host callback) before these
read methods are callable by plugins/adapters, and never publish direct store
access to untrusted JS, HTTP, extensions or workers. Keep the existing
project/actor/revision/gate checks; **do not** remove them to make a test pass.
Avoid returning raw original session ID or send key outside a genuinely
host-private comparison layer.

### F2: Username reuse cannot distinguish a replaced account (HIGH conditional identity-reuse risk)

**Observed in a synthetic authorization model:** deleting/revoking original
Alice's tokens and registering a *different* account under username `alice`
with a new valid session, an allowed role and the original project grant
allowed `recovery_snapshot` and `recovery_status` to return the old request.
The outbox records only `actor_id` based on `account['username']`; no immutable
account incarnation/UUID is required in the recovery check. Real `LanService`
code stores username in session mappings (`lan.py:657-672`) and permits user
upsert by username (`lan.py:798-850`), and has a deletion path at `986-1089`.

**Scope of certainty:** the equality-only identifier problem and acceptance
on the actual recovery APIs are demonstrated; **the real LAN delete ->
recreate -> login workflow was not exercised**. Do not call this a verified
network exploit. Revocation of project membership or role **does** stop
recovery as long as the resulting currently authenticated identity is checked
and the original project is revoked.

**Minimum remediation:** use a persistent, immutable non-reused host account
ID to bind *new* outbox and gate records. For legacy rows without this ID,
fail closed on deleted/recreated users or require explicit host-controlled
account-lineage reconciliation with audit. Preserve historical IDs and never
map a replaced username to old finance intent merely because the text matches.

## Negative checks that passed

The synthetic tests confirmed denial for: different actor or organization,
revoked/invalid session via host, removed project grant or saved original
project, revoked role/finance capability, principal boolean/permission/role/
project tampering, unknown request, wrong original revision, missing dispatch
reservation and PREPARED-only request. Direct original-session mutation/send
API access did **not** rearm the consumed slot after re-login. A card title,
project or list move and even deletion do **not** erase the historical request
when original project authority remains. A mismatched/corrupt outbox digest,
dispatch reservation send key and immutable audit history were rejected.

The tests' DB tampering intentionally modified **only isolated synthetic
SQLite databases**. For the gate corruption cases, the test explicitly
dropped a trigger **in its own fixture** to mimic hostile on-disk damage; no
existing host database or trigger was modified. The coordinator test mocked
peer lookup so **no network I/O** was performed.

## Exact test evidence and constraints

Windows PowerShell wrapper assigned a fresh temporary directory to
`APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`, `HOME`, `USERPROFILE`, set
`PYTHONDONTWRITEBYTECODE=1`, restored previous environment values and removed
only that disposable directory afterward. It executed:

```powershell
py -3.12 -B -m unittest discover -s tests -p test_mtr_e2_recovery_security_20261110.py -v
```

**Observed: 15 tests, 15 passed, 0 errors/failures, process exit 0.** Two
of those *passing* tests are deliberately written to **demonstrate security
gaps** (forged in-process principal and replaced username). Green does not
mean they were denied. The test host/peer stubs and all data were synthetic,
and no actual LAN login, peer query or deployment was tested. The exact
files/paths and counts above, not broader release readiness, are the
bounded conclusion.
