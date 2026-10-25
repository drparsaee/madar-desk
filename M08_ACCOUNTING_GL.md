# M-08 Independent Double-Entry GL Kernel

**Status (2026-10-21): isolated pure kernel + synthetic unit tests only.**

Implementation: `accounting_gl.py`. Tests: `tests/test_accounting_gl.py`.
No existing `finance.py`, `app_storage.py`, `native_app.py`, React UI,
database schema, real APPDATA, accounts, network, release or Git state was
changed. This implementation is **not installed in the live finance domain**.

## Existing architecture reviewed read-only

- `finance.py`: integer whole-toman amounts; existing operational finance
  `ledger` records events for invoices/contracts/payments but are not themselves
  debit-credit GL postings. The existing finance state currently also has
  **optional** `accounting`/`accountingSources` extension paths.
- `accounting_core.py` and `accounting_service.py`: separate, already existing
  accounting implementation and optional finance-domain orchestration. Their
  current behavior and production readiness are **not certified by this worker**.
- `app_storage.py`: validated four/five-domain snapshots, revision-based CAS
  commits, and checksummed storage. No new GL domain or native database table was
  attached. This M-08 kernel is independent of that persistence mechanism.

This task adds a small, generic GL event-sourcing kernel to evaluate separately,
without claiming it replaces or is compatible with the existing
`accounting_core.py` schema. An integration decision must select a single
authoritative GL engine; **never dual-post into both**.

## Data and accounting invariants

Versioned source snapshot:

```json
{
  "schemaVersion": 1,
  "currency": "TOMAN",
  "events": []
}
```

Only three append-only commands are accepted, with exact property names:
`account.create`, `journal.post`, `journal.reverse`.

Accounts are added once with an immutable ID, name and classification:
`asset`, `liability`, `equity`, `revenue`, `expense`.
Debit is the normal side for assets/expenses, credit for the others.
Account rename/delete, posted journal edit/delete and arbitrary command
extensions are rejected.

The journal requirements are:

- At least two, at most 200 distinct account lines. Every line has exact
  `accountId`, `debit` and `credit` fields; exactly one side must be positive.
- All values are **Python integers**, in whole tomans. Floats, booleans,
  fractional amounts, negative amounts, text amounts, NaN/Infinity and values
  over `10^15` are rejected. Journal totals must balance and not exceed
  `10^15` on either side. There is no implicit tax/rounding/FX logic.
- The journal ID must be unique, account IDs must already exist and the
  posting date must be a real `YYYY-MM-DD` date no later than the host-provided
  trusted timestamp's date.
- A reversal creates **another** full journal with swapped debit/credit lines,
  preserving the original entry. Only a normal posted journal can be reversed,
  once, with an explicit reason; the reversal date may not precede original
  posting. A reversal of a reversal is rejected.
- `trial_balance` calculates debit/credit turnovers, debit/credit net balance,
  normal balance by account kind, and totals, with optional `through_date`
  filter. Its debit and credit columns must balance.
- The event chain contains `seq`, actor, explicit timezone-aware `at`,
  `command`, deterministic actor+command fingerprint, result, `prevHash` and
  `hash`. Every read/command fully replays the log, rechecks hashes, accounting
  rules, unique event IDs, and matching computed results.
- The event ID is the idempotency key. Identical retries from the same actor
  return the original result with `changed: false`, even with a different
  `now` timestamp. Reuse with a different command or actor fails closed.
  Previously successful retries still require a currently authenticated admin.

Limits: 10,000 events in memory, up to 200 lines per journal, and 12,000,000
JSON bytes for source/output. No background writes, no timestamps from machine
clock, no filesystem operations and no network side effects.

### What this kernel does NOT guarantee

An in-process SHA-256 chain can identify accidental corruption or modification
that has not been fully rehashed. It is **not a signature** and cannot prevent
a privileged attacker from rewriting an entire chain or truncating its tail.
The host must pin the last hash to trusted revision history and use
authenticated, atomic, revision-checked persistence and backups.

This first-phase kernel does not provide approved invoice posting workflows,
tax rules, account hierarchy, period locking/closing, liquidity overdraft
policy, historical balance carry-forward, row-level project grants, financial
statement certification, or a reconciliation engine. A balanced journal is
mathematically valid but could still be a **wrong business transaction**.
Administrative authorization is intentionally strict; any non-admin actor
is refused, regardless of the actor's `financeEdit` flag. Users must be
authenticated by the host before invoking this library, and the authoritative
accounts collection cannot be supplied by an untrusted client.

## Contract for Prime: pure functions

```python
from accounting_gl import (
    empty_gl_state, validate_gl_state, apply_gl_command,
    trial_balance, gl_view,
)

# In-memory detached snapshot; NO persisted finance changes:
state = empty_gl_state()
accounts = {"root": {"username": "root", "role": "admin"}}
now = "2026-10-21T16:00:00+03:30"  # trusted host-generated timestamp

# Add accounts explicitly; create separately with unique eventIds:
out = apply_gl_command(
    state,
    {"type": "account.create", "eventId": "acct-1",
     "accountId": "1000", "name": "Cash", "kind": "asset"},
    actor="root", accounts=accounts, now=now)
state = out["state"]      # out["changed"] == True

out = apply_gl_command(
    state,
    {"type": "account.create", "eventId": "acct-2",
     "accountId": "3000", "name": "Owner equity", "kind": "equity"},
    actor="root", accounts=accounts, now=now)
state = out["state"]

out = apply_gl_command(
    state,
    {"type": "journal.post", "eventId": "source:owner-funding:001",
     "journalId": "J-001", "postingDate": "2026-10-21",
     "description": "Owner funding approved",
     "lines": [
         {"accountId": "1000", "debit": 1000, "credit": 0},
         {"accountId": "3000", "debit": 0, "credit": 1000},
     ]},
    actor="root", accounts=accounts, now=now)
state = out["state"]

validate_gl_state(state)
balance = trial_balance(state, actor="root", accounts=accounts)
view = gl_view(state, actor="root", accounts=accounts)
```

`apply_gl_command` returns `{state, changed, result}` as a fresh Python dict.
Both input state and command are preserved on success and failure.
`validate_gl_state` returns `True` or raises `ValueError` on inconsistency.
`gl_view` and `trial_balance` return detached read projections after ACL
check and replay. This contract deliberately does not accept an existing
`finance.py` ledger, native database connection, SQLite path or file handle.

### Host integration requirements (not executed)

1. Decide which existing GL engine is authoritative: this kernel or the
   `accounting_core.py` extension. Their event schemas differ; use a reviewed
   migration/adapter if consolidating. Never write duplicate journals.
2. Authenticate `actor`, enforce current admin permissions, and obtain the
   entire authoritative snapshot and trusted `now` from the host. A caller
   must not claim arbitrary roles or invent a stamp.
3. Apply the command against a detached complete GL state; validate its result.
   Atomically CAS-commit the GL snapshot together with the corresponding
   operational finance/task state and source event mapping if the business
   action requires it. Reject stale revisions. Ensure idempotency across crash
   retries **at the storage boundary**.
4. For financial transactions such as invoice issue, task-generated sale,
   purchase bill or payment, require separate explicit business approval,
   source authorization, and one unique business-source-to-GL-event mapping.
   This kernel **does not derive** journal lines from tasks, sale prices or
   expense drafts.
5. Keep full backups/recovery and the trusted last-event hash in the same
   durable revision transaction. Test actual two-process CAS and crash restore
   before claiming production readiness.

## Validation

```powershell
py -3.12 -m unittest discover -s tests -p test_accounting_gl.py -v
```

The suite uses only synthetic Python objects. It exercises five account
classes, invoice-like AR/AP postings, turnover and balances, time-filtered
trial balance, one-time reversal, replay under a changed host timestamp,
event ID collisions, current administrator ACL, strict schema and JSON types,
overflow/negative/float controls, tamper/replay checks and non-mutation on
errors. It does **not** test real invoices, actual finance database integration,
workstation UI, LAN, APPDATA, real users or double-entry certified statements.
