# Evaluation: `ekmungai/python-accounting` as a Madar accounting engine

**Date:** 2026-10-21  
**Disposition:** **Not suitable as a drop-in replacement.** A limited, isolated reference implementation or separately designed adapter could be investigated after the money and persistence contracts are fixed.  
**Evaluation boundary:** Windows, Python 3.12, throwaway venv, an in-memory SQLite database, and synthetic entries only. No Madar production data or host integration was used.

## Evidence and reproducibility

| Evidence | Observed outcome |
|---|---|
| Package | `python-accounting==2.0.0` wheel downloaded from the package index into `.scratch-python-accounting-eval/` and installed in its own `.venv` on Windows Python **3.12.10**. `pip check`: `No broken requirements found.` |
| Dependencies actually installed | `SQLAlchemy==2.1.6`, `mysqlclient==2.3.0`, `psycopg2==2.9.13`, `python-dateutil==2.9.0.post0`, `six==1.17.0`, `typing_extensions==4.16.0`. These were confined to the disposable venv. |
| License | **MIT License**, copyright (c) 2024 Edward Mungai. Verified in downloaded wheel at `python_accounting-2.0.0.dist-info/licenses/LICENSE` and separately published upstream at [LICENSE](https://github.com/ekmungai/python-accounting/blob/main/LICENSE). The MIT notice must accompany copies/substantial portions. This does **not** constitute a review of every dependency's license. |
| Published metadata | [Upstream pyproject.toml](https://github.com/ekmungai/python-accounting/blob/main/pyproject.toml) lists `requires-python >=3.11` and four direct dependencies (including mandatory MySQL and PostgreSQL drivers). [README](https://github.com/ekmungai/python-accounting) documents `Base.metadata.create_all`, `get_session`, `Entity`, `Currency`, accounts, line items, `CashSale.post(session)`, and reporting APIs. |
| Reproducible test | `.scratch-python-accounting-eval/probe_sqlite.py` uses official public API with `create_engine('sqlite+pysqlite:///:memory:')`; it creates and drops all synthetic state in process memory and writes `.scratch-python-accounting-eval/probe_result.json`. Results below are actual run results, not a claim about the Madar application. |

## Pass / fail / inconclusive

| Check | Result | Direct evidence and interpretation |
|---|---|---|
| Windows Python 3.12 install | **PASS** | `python-accounting 2.0.0` and runtime dependencies installed in a private venv; `pip check` reported no broken dependencies. Installation does not establish deployment or PyInstaller compatibility. |
| SQLite schema creation | **PASS** | `Base.metadata.create_all(engine)` created **14** tables: `account`, `assignment`, `balance`, `category`, `currency`, `entity`, `ledger`, `line_item`, `recyclable`, `recycled`, `reporting_period`, `tax`, `transaction`, `user`. |
| Simple double entry | **PASS** | Synthetic `CashSale` with `LineItem(amount=Decimal('123.0000'))` posted exactly two `Ledger` rows: one `DEBIT 123.0000` and one `CREDIT 123.0000`. No manual balancing adjustment was needed. |
| Stated numeric-scale maximum example | **PASS, narrow case** | `999999999.9999` survived line-item and both ledger readbacks exactly; both sides matched, and `is_secure()` returned `True`. This is one example within nominal `DECIMAL(13,4)` capacity, **not** a general proof of exactness. |
| Exact large integer rial | **FAIL for Madar's unguarded integer-money requirement** | Synthetic input `9007199254740993` (`2**53 + 1`) returned **`9007199254740992.0000`** from both `LineItem` and `Ledger`. `is_secure()` returned `False` for this transaction. No validation error rejected the amount. **Qualification:** this deliberately exceeds the model's nominal `DECIMAL(13,4)` range (9 integer digits, 4 fractional digits); the test demonstrates failure to guard a value a rial-domain API may receive, not a violation of a documented guarantee for oversized values. Actual Madar money ceilings must be specified and enforced independently. |
| SQLite FK enforcement in default connection | **FAIL as an integrity gate** | `PRAGMA foreign_keys` returned **`0`** despite declared table foreign keys. An integrator must explicitly enable and test FK enforcement for every SQLite connection. |
| Ledger tampering indicator | **PASS, narrow case** | After changing one synthetic `ledger.amount` by direct SQL, a fresh session's `is_secure()` identified the mismatch. This is not proof of tamper resistance against someone able to rewrite data and all hashes. |
| Financial reports, tax, purchases, aging, multiple entities/currencies, reversals, concurrent transactions, migration | **INCONCLUSIVE** | APIs/models or documentation exist for some features; these paths were **not exercised** in this evaluation. Neither IFRS/GAAP compliance nor correctness of Iranian accounting/tax behavior is independently verified. |
| Persistent local SQLite, offline packaging, startup migration, backup/restore, crash recovery | **INCONCLUSIVE** | The test used in-memory SQLite only, no native installer, production schema, or file-based DB. |

### Reproducing and locating the monetary precision failure

The actual `LineItem.amount`, `Ledger.amount`, and `Transaction.main_account_amount` SQLAlchemy fields are `DECIMAL(precision=13, scale=4)`. The following minimal, read-only inspection of the installed package demonstrates the **conversion boundary before SQLite persists the number**:

```python
from decimal import Decimal
from sqlalchemy import create_engine
from python_accounting.models import LineItem

engine = create_engine("sqlite+pysqlite:///:memory:")
column_type = LineItem.__table__.c.amount.type
binder = column_type.dialect_impl(engine.dialect).bind_processor(engine.dialect)
bound = binder(Decimal("9007199254740993"))
print(str(column_type), engine.dialect.supports_native_decimal)
print(type(bound).__name__, repr(bound))
# DECIMAL(13, 4) False
# float 9007199254740992.0
```

**Verified mechanism:** The installed SQLAlchemy SQLite dialect has `supports_native_decimal=False`, and its bind processor converts the exact input to an already-rounded Python `float`. The SQLite column is declared `DECIMAL(13,4)` with **NUMERIC affinity**, *not* a `REAL` affinity declaration. SQLite can nevertheless store individual values as `INTEGER` or `REAL`. On the actual synthetic posted rows, `SELECT typeof(amount), quote(amount) FROM line_item WHERE id=:id` returned `('integer', '123')`, `('real', '999999999.9999')` and **`('integer', '9007199254740992')`** respectively. Thus the large amount was rounded before storage, and SQLite persisted that changed integer. The full synthetic double-entry path and the exact SQL inspection are in `probe_sqlite.py` and `probe_result.json`.

This particular failure is **outside nominal `DECIMAL(13,4)` range**; it cannot establish failure for all supported values or other SQL dialects. For a strict **canonical integer RIAL** contract, however, allowing a large unvalidated number to change silently is an unacceptable integration condition, and this SQLite schema/adapter has not demonstrated the needed range or enforced integer-only amounts.

To rerun the installed-wheel test from the Madar project root on a machine with Python 3.12 and network access for dependencies:

```powershell
python -m venv .scratch-python-accounting-eval\.venv
.\.scratch-python-accounting-eval\.venv\Scripts\python.exe -m pip install .\.scratch-python-accounting-eval\python_accounting-2.0.0-py3-none-any.whl
.\.scratch-python-accounting-eval\.venv\Scripts\python.exe .scratch-python-accounting-eval\probe_sqlite.py
```

## Compatibility with current Madar design

| Dimension | Current Madar source inspected (read-only) | `python-accounting` v2.0.0 | Replacement effect |
|---|---|---|---|
| Persistence and transactions | `accounting_core.py` (snapshot read 2026-10-21) uses a versioned JSON **event list** and deterministic pure projections. `accounting_service.py` says the host atomically persists the entire finance snapshot via existing SQLite CAS / JSON semantics. | SQLAlchemy relational models and `AccountingSession`; e.g. `Ledger._post_simple` calls `session.commit()` when posting. | Requires redesign of transactional boundary, migration, replay, idempotency and host atomicity. Cannot safely swap imports. |
| Money | Existing `accounting_core.py` currently validates exact integer **TOMAN** values (`MAX_TOMAN = 10**15`, snapshot). The planned financial-domain policy calls for canonical integer **RIAL**, explicit TOMAN display/entry and migration source-unit verification. | Decimal fields (`DECIMAL(13,4)`), currency codes stored as `String(3)`; test exhibited silent loss for an oversized exact integer. | RIAL conversion, bounds, no-float arithmetic and non-truncating TOMAN display require an explicit money adapter and probably model/schema changes. Existing TOMAN events cannot be presumed already migrated. |
| User/task linkage | `accounting_service.py` consumes task-based sales and purchase drafts and keeps document/source fingerprints in `accountingSources`. | Generic accounting transactions, invoices, bills, assignments, reports. | Mapping tasks and expense sources to identified parties/documents, immutable amount snapshot, duplicate prevention and approval paths is application work. |
| Audit and document lifecycle | Event-source validation and journal reversal are implemented in current Madar code paths; authorization comes from trusted host accounts. | Has transaction posting, hash checks and ORM session isolation; `Transaction.is_posted` and validation protect normal model edits. | Verify durability, reversal semantics, period closure, auth, recovery, event provenance and tampering policies before considering a replacement. |
| Storage footprint | Host uses its existing finance snapshot/persistence contract. | 14 SQL tables plus MySQL/PostgreSQL Python drivers even for SQLite-only install. | Packaging and migrations become more complex; requiring a MySQL/Postgres **driver** does not mean a server was started or required during the synthetic SQLite run. |

The upstream's financial reporting taxonomy, configurable account categories, multi-entity model and account aging APIs might still inform Madar's reporting design. Their advertised existence is **not** a verified compatibility result. The current Madar accounting engine already implements basic journal balancing; a replacement should provide demonstrable benefits after evaluating the impact of changing storage and money rules.

## Conditions for reconsideration

1. **Publish and test the exact RIAL money policy first.** Require Python `int` at every host boundary; reject bool, floats, fractional rials, out-of-range values and unknown legacy units. All calculations, snapshots and persisted journal amounts must round-trip exactly, including a stated maximum. If an upstream adapter is pursued, investigate storing integer rials in SQLite `INTEGER` (with explicit signed-64-bit bounds) or canonical decimal strings with checked arithmetic instead of the current `DECIMAL(13,4)` mappings.
2. **Build a genuinely isolated trial adapter** that maps Madar approved documents and event IDs to upstream entities and entries. Preserve source fingerprint/idempotency and existing atomic commit semantics. Audit upstream internal `commit()` calls to avoid an invoice being issued on one side while the host snapshot write fails.
3. **Enforce database invariants.** Turn SQLite FK checking on per connection; add authoritative balancing and immutable-posting checks, tests for rejection of invalid direct SQL mutations, multi-company isolation, and crash rollback. Verify hash checks against realistic threat models, not solely the one successful tamper probe.
4. **Run wider adversarial acceptance tests** for invoice → debtor, expense → creditor/purchase bill, collections/payments, duplicate submissions, posted-document freeze, reverse-and-repost, multi-period close, concurrent writers, backups, and strict precision at boundary values. Test Windows executable packaging and offline startup separately.
5. **Decide replacement based on measured value.** Until these gates pass, retain the current Madar event engine and consider `python-accounting` only as a source of open-source accounting patterns or a standalone experimental reference. This decision is an engineering recommendation based on the narrowly scoped evidence above, not a production certification of either implementation.

## Containment and limitations

Only `.scratch-python-accounting-eval/` and this new evaluation document were created/edited for this task. No Madar source, finance records, package scripts, system Python installation, Git, APPDATA, native application, SQL service, or release was modified. After tests, **the scratch venv (~40.7 MB) and pip cache (~6.7 MB) were removed**; the isolated script, captured JSON results, upstream wheel and unpacked MIT license/code remain under scratch for auditing. Dependencies must be reinstalled to rerun the script. Source observations are dated snapshots because other Madar workers may change code concurrently. This evaluation does not inspect proprietary code, real business data or actual users.
