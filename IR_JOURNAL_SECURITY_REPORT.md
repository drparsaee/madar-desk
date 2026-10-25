# RIAL V2 journal: synthetic security / concurrency report

Date: 2026-10-22. Scope: `ir_journal_v2.py`, `ir_journal_sqlite.py`, and the existing RIAL journal unittest suites. All writes made by these new tests used randomly named SQLite files in project-local `tests/madar-rial-security-stress-*` temporary directories, with cleanup. No live app state, Parsian, production database, existing TOMAN ledger, Git/release or running application was accessed by this worker.

## Reproducible validation

Command, run from `D:\CoS-Test\madar-desk`:

```powershell
python -m unittest discover -s tests -p 'test_ir_journal*.py' -q
```

Final observed result after the last test-name update: **61 tests / 61 PASS, 0 failures, 0 errors, process exit code 0, elapsed 16.336 s**, using **Python 3.12.10 on Windows**. This comprises **20 new security/stress tests** in `tests/test_ir_journal_security_stress.py` and **41 existing tests** in `test_ir_journal_sqlite.py` and `test_ir_journal_v2.py`. Final filesystem check found **0 leftover project-local stress temp directories**. The elapsed time measures this synthetic fixture on this machine, not an application performance guarantee.

The new tests include:

| Scenario | Test and observed result |
| --- | --- |
| Same-revision concurrency | 16 synchronized writer threads, exactly one successful SQLite `mutate`; 15 CAS conflicts; persisted one balanced journal |
| Multiwriter CAS retries | Five writers × seven unique postings: 35 committed journals, 35 distinct event IDs and sources, replay totals balanced, no missing writes |
| Simultaneous double-source attempts | Eight threads target the same source using different event IDs; only one committed, a subsequent distinct-ID attempt rejected |
| Pure vs SQL idempotency | Exact same-ID retry is a no-op; conflicting same-ID payload rejected; SQL `mutate` and `commit` reject same source/new event; direct pure-kernel post demonstrably accepts that duplicate |
| Tenant isolation | Cross-company lines, callbacks and state modifications rejected; six companies successfully store separate same-named events/sources |
| Fraud/malformed inputs | Invalid event/source/actor IDs, unverified source, invalid/future dates, unbalanced debit/credit, SQL quoted injection, and forged checksum/schema/currency rejected |
| Money boundaries | Float, NaN, Inf, bool, string, negative, zero and overflowing integer values rejected; cumulative posted sum overflow rolled back; 100-line event accepted and 102-line event rejected |
| Replay/append-only limits | Event deletion/reordering, currency reinterpretation and evidence removal rejected; event-count and chart-evidence bounds rejected; rehashed unbalanced historic event rejected |
| Transaction atomicity | Callback errors, malformed callback return and invalid state produce no persisted partial update; close Q1, reverse in Q2 and prevent further Q1 posting |
| File-writer threat reproduction | Writer with *direct raw SQLite write privileges* replaced an entire valid journal chain with a different, internally valid one and recomputed public hashes; subsequent `read` accepted it. See F-02. |

First authoring run produced five test errors: temporary SQLite helper connections remained open on Windows, and an attempted forged float checksum was incompatible with the canonical snapshot hash policy. The fixture was corrected to close connections and independently check both rejection layers. Following those corrections the broader journal suite passed. No implementation files were changed by this worker.

## Security findings and integration risks

### F-01 — Business-source uniqueness exists at the SQLite boundary, not in the pure kernel

**Reproduced, integration-critical.** `post_journal()` tracks event-ID idempotency but permits another journal with the same `(company_id, kind, project_id, source_id)` and a different event ID. `RIALJournalStorage._unique_business_sources()` rejects that candidate during `mutate` and `commit`. The new test `test_same_source_different_event_rejected_across_sql_mutate_and_commit` demonstrates both outcomes using the same event stream.

Reproduce with:

```powershell
python -m unittest discover -s tests -p 'test_ir_journal_security_stress.py' -k test_same_source_different_event_rejected_across_sql_mutate_and_commit -v
```

**Required host control:** every issued journal must go through the SQLite business-source uniqueness transaction. Any other future persistence adapter, direct pure-kernel caller, invoice or expense writer must enforce the same constraint within its own atomic transaction. The source key is scoped by kind/project; the host must normalize any business aliases representing the *same* commercial document before posting. This test does not establish whether existing invoice/task UI paths use this adapter.

### F-02 — DB-wide raw-write compromise can forge an internally valid history

**Reproduced, conditional on attacker having direct write control over the dedicated SQLite database.** Because the snapshot digest and event hash chain use unkeyed SHA-256, an attacker who bypasses the storage API and can overwrite `revision`, `payload` and `digest` together can reconstruct a different, self-consistent event chain. The reader accepts the reconstructed state; local hashes alone do not anchor authenticity to a protected prior value.

`test_direct_database_writer_can_replace_entire_valid_history` first commits a `2 RIAL` entry, builds a valid alternate `900 RIAL` entry from the same genesis state, directly replaces the synthetic row using raw SQLite, and asserts that `RIALJournalStorage.read()` returns the alternate. This is a **passing security-demonstration test of a real limitation**, not a claim that the attack was prevented.

Reproduce with:

```powershell
python -m unittest discover -s tests -p 'test_ir_journal_security_stress.py' -k test_direct_database_writer_can_replace_entire_valid_history -v
```

**Recommended control:** protect database file access, maintain independent append-only audit records and/or signed external periodic hash anchors/checkpoints that an attacker with ordinary SQLite write permissions cannot replace. Do not advertise the current checksums as cryptographic proof against an attacker who can rewrite the entire DB.

### F-03 — Authorization and dual-ledger atomicity are host responsibilities

**Not verified end-to-end.** The storage `mutate(company_id, expected_revision, operation)` API intentionally assumes the caller has authenticated the actor and verified the chart and business scopes. Unit tests can reject invalid scopes supplied to the pure kernel, but they cannot prove the host derives those scopes from trusted authorization data rather than the request body. The RIAL database is a dedicated separate journal; these tests do not establish a shared atomic transaction with existing TOMAN finance state, invoice issuance or the UI. A host must prevent double-posting and partial legacy/RIAL writes when integrating them.

**Required integration acceptance:** test role-permission denials through actual host handlers; authenticate source ownership; prove issue-invoice/task/expense produces at most one commercial posting across repeated IDs and concurrent requests; inject a fault between legacy and RIAL writes and verify rollback or a documented single-ledger issuance strategy; verify existing TOMAN history is preserved without reinterpretation. These cases remain open, not passed.

## Scope and limits

- Isolated SQLite connection tests verify API-level CAS and rollback for these synthetic workloads. They do **not** prove distributed, multi-process or system-crash durability, malicious process isolation, production throughput, real-host role enforcement, backup recovery, EXE UI behavior, or security of SQL/Parsian integrations.
- Concurrency coverage uses threads in one Python process. The 16-way single-revision race and 35 successful retrying postings are bounded stress examples, not an exhaustive contention model.
- Raw SQLite mutation was used only in local temporary fixtures as a hostile-file simulation. The proof does not grant the attacker database write privileges; it documents the consequence if such privileges are already held.
- The narrow suite and independent existing suites passing is evidence for their tested contracts only. It is **not** certification of the whole Madar application or a release gate.

Ownership: only `tests/test_ir_journal_security_stress.py` and `IR_JOURNAL_SECURITY_REPORT.md` were created/changed for this tranche. No implementation edits.
