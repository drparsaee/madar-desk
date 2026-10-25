# Madar Desk: standalone legacy accounting storage

**Delivered:** 2026-10-22. **Status:** independently functioning pure-core adapter + SQLite storage, synthetic-test validated. **Currency:** integer **TOMAN** only. This is **not RIAL V2**, not a migration, and not an adapter to the task manager.

## New files only

- `standalone_accounting.py`: the independent storage service
- `tests/test_standalone_accounting.py`: self-contained synthetic acceptance, adversarial and race tests
- `STANDALONE_ACCOUNTING_STORAGE.md`: this contract and handoff

No modifications to `accounting_core.py`, `native_app.py`, `lan.py`, `app_storage.py`, task-manager UI, unified finance, migration files, production APPDATA, Parsian, release, Git or live SQL.

## Public Python contract

```python
from standalone_accounting import StandaloneAccountingStore

# Caller intentionally chooses a separate private/local SQLite path.
store = StandaloneAccountingStore(r"D:\some-isolated-folder\standalone.sqlite3")

# The host has authenticated this principal and owns the account index.
trusted_accounts = {"accountant": {"username": "accountant", "role": "admin"}}

snapshot = store.read(actor="accountant", accounts=trusted_accounts)
# {'revision': 0, 'view': accounting_core.accounting_view(...)}

response = store.command(
    {"type": "party.register", "eventId": "register-001",
     "partyId": "supplier-001", "name": "Supplier", "kind": "vendor"},
    actor="accountant", accounts=trusted_accounts,
    expected_revision=snapshot["revision"],
    now="2026-10-22T13:00:00Z",
)
# {'revision': 1, 'result': {'partyId': 'supplier-001'},
#  'view': accounting_core.accounting_view(...)}
```

There are only three public operations: constructor, `read` and `command`. The service **never** asks the caller for task/project identifiers, a unified finance bundle, a RIAL company mapping, a client-side role flag, a proof token or an APPDATA location. No implicit migrations, imports, scheduled synchronization, backups, activation or live account registration are performed.

The independent SQLite schema has **one application table**, `standalone_accounting`, and SQLite `user_version=1`. `revision=0` is a virtual pristine accounting state with no row. First accepted new accounting event creates revision 1. Every subsequent accepted new event replaces the singleton state with a **full event-history snapshot**, increasing revision by exactly one. Event history within that snapshot is immutable through the API. A deliberate audit trail of *earlier snapshot revisions* is NOT implemented; the durable audit is the full event-sourced history and its hash chain. A new audit-revisions schema would require a separately authorized change.

## Transaction, replay and concurrency semantics

1. Every `command` starts **one SQLite `BEGIN IMMEDIATE` transaction**, reads and checks the current revision, stored SHA-256 checksum, canonical JSON and **full event-history replay** through `accounting_core.validate_accounting_state`. It then calls **`accounting_core.apply_accounting_command`**, reruns full validation on the returned state, and returns a role-authorized `accounting_core.accounting_view`.
2. New authorized event: canonical JSON is stored with a SHA-256 digest using one insert/update inside the **same** SQL transaction, with integer CAS. WAL and `synchronous=FULL` are enabled. Any exception rolls back all changes.
3. Exact replay (same **eventId**, authenticated **actor** and exact **command payload**) returns its saved original `result`, currently authorized view and **unchanged revision**. The timestamp `now` must still be valid. A reused ID with another payload or actor is refused. A demoted/revoked actor cannot replay an operation outside their current permissions.
4. **Strict CAS even for replay:** `expected_revision` must equal the current revision *before* checking event ID; a stale request receives `AccountingRevisionConflict`. Caller must refresh via `read` and retry the **same** event to recover from an uncertain successful write. This is deterministic and documented, rather than silently allowing stale writers.
5. Two independently instantiated stores at the same path serialize through SQLite; when both submit different events with the same expected revision, one commits and the other gets a revision conflict. Errors after a SQL insert/update but before `COMMIT` are rolled back, including on a nonempty history.

Read uses a SQLite read transaction for one consistent snapshot, verifies digest and full replay, then applies core's read ACL. Results are detached new dicts. The original accounting core is the sole authority for named customers/vendors, posting dates, journal balancing, AR/AP reconciliation, document approvals, settlements, period close, role permissions, event-id fingerprint and hash chain.

**Bounds:** strict canonical UTF-8 JSON; JSON duplicate keys/nonfinite constants disallowed; snapshot at most **15,000,000 bytes**; at most **20,000 accounting events**. Exceeding bounds rejects the write without changing the SQLite revision. SQLite itself has normal file-system limits. These conservative app limits should be reviewed before large deployments; each command rereplays the entire bounded event chain, so large historical ledgers may need audited optimization.

**Errors:** `AccountingRevisionConflict` means stale expected revision; `AccountingIntegrityError` means stored digest, format or accounting replay failed; `StandaloneAccountingError` means unsupported SQLite layout/version. Original `ValueError` and `PermissionError` from `accounting_core` remain fail-closed. The caller is responsible for presenting these errors and retrying only when appropriate.

## Coverage and observed validation

Command:

```powershell
python -m unittest discover -s tests -p test_standalone_accounting.py -v
```

**15 tests PASS; 0 FAIL (1.122 seconds, exit 0)** on the target Windows Python runtime. Coverage:

- Empty revision 0, detached TOMAN view, no task-manager/unified database tables.
- Issue approved customer invoice, record partial receipt; persist and reopen with exact balances.
- Issue supplier purchase bill and partially pay with bank funding; correct payable, paid and outstanding amounts.
- New chart account, stockless item creation/update, bank transfer, manual double-entry, journal reversal and fiscal period close.
- Current actor permissions (admin/editor/viewer/financeView), tampered actor/proof/role/company in command, wrong timestamp and invalid money.
- Exact idempotent replay without revision bump; conflicting event payload/actor and stale-revision replay denied.
- Concurrent independent SQLite store instances: exactly one CAS winner.
- Simulated crash **after INSERT/UPDATE but before COMMIT**, empty and nonempty history; no partially committed revision.
- Corrupted checksum, altered immutable event, and tampering with recomputed external snapshot SHA-256 all detected by strict replay on both read and command.
- Explicit JSON/event-size bounds and refusal to implicitly initialize in a foreign occupied SQLite database.

All tests use `tempfile.TemporaryDirectory` and dispose of the SQLite connections. The controlled failure injection is **not** an actual power-cut test. No production datastore was read or written.

## Security / integration boundary and operational cautions

- **Trusted host required.** Caller must derive `actor`, `accounts` and `now` from authenticated server/session or local privileged host context. A client may submit a *business command* but cannot choose these keyword arguments. The standalone service cannot independently authenticate a caller, and arbitrary Python executing inside the privileged host could supply false trusted arguments. This is **not a cryptographic authorization guarantee**.
- Both the state SHA-256 and accounting core event-chain hashes are **unkeyed integrity checks**, not digital signatures. Someone who can directly rewrite this separate SQLite file with sufficient operating-system privilege can also recompute hashes and attempt to forge a replay-valid history. Enforce OS ACLs, separate privileged service, and external immutable backups/audit logs if the threat model includes local process/file compromise.
- **TOMAN only.** `accounting_core.empty_accounting_state` fixes `currency='TOMAN'`. Money is exact integer TOMAN in this independent legacy ledger; there is no automatic RIAL ×10 conversion, fiscal company mapping, RIAL V2 journal, invoice-to-task bridge or unified CAS with other modules.
- This service does not provide backups, user authentication, multi-tenant partitioning, historical snapshot restore, migrations or GUI/LAN endpoints. Integration into the main application would be a **separate, explicitly reviewed phase**; an independent accounting instance and a task-manager invoice must not be implicitly claimed to share financial state.
