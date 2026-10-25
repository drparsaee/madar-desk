# Madar Desk 1.0: verification of full recovery with automation journal

## Test scope

The new integration suite is `tests/test_automation_full_recovery.py`. It uses
the **real** `full_recovery.create_full_backup` and
`full_recovery.restore_full_backup`, rather than mocking the archive or
restore implementation. Every path is created under `TemporaryDirectory`.
No APPDATA paths, live Madar release, live server, LAN process, subprocess,
or existing user backup are accessed by the new suite.

Only these **new** files belong to this verification worker:

- `tests/test_automation_full_recovery.py`
- `AUTOMATION_RECOVERY_VERIFICATION.md`

No production code was changed.

## Reproducible scenario

The test builds an actual `UnifiedAppStorage` at a disposable path with a
four-domain revision followed by an **explicitly activated five-domain**
revision. The activated revision holds all five domains:

1. `tasks`: a real, normalized task/project model, with a distinctive card
   title that must survive restore.
2. `collab`: an authorized automation rule and one applied automated comment.
3. `finance`: a valid financial state.
4. `completion_outbox`: a non-empty, valid completion event.
5. `automation`: **three audit entries**, one durable completion receipt and
   one pending event job created by `automation_v1.enqueue_events` and
   `automation_v1.run_batch(limit=1)`.

The source root also contains the real `unified-active.json` marker and an
`AttachmentStore` with a UTF-8 text attachment whose SHA-256 blob and metadata
are validated. The test creates a full ZIP backup with `offline=True`, then
performs another **valid five-domain database commit** (different journal,
collaboration state, card title and outbox) and uploads a second attachment.
It restores the first ZIP over that newer, still-valid state and asserts:

- Entire restored `UnifiedSnapshot` (including revision, SHA-256 and bundle)
  is identical to the pre-backup snapshot, with both historical revisions.
- Automation receipts, audit and pending jobs match **exactly**, not merely
  record counts. No task, finance, collaboration or outbox fields are lost.
- The original attachment is readable with exactly identical content bytes;
  later attachment metadata does not leak into the recovered snapshot.
- The pre-restore directory retains the later database and later attachment;
  a pre-restore ZIP is also written as a rollback artifact.
- `integrity_check()` succeeds after reopening SQLite and no recovery journal
  remains pending.

### Damaged archive rejection tests

Each rejected restore must preserve the original, valid five-domain database
and attachment bytes, leave no pending restore journal, and avoid publishing
a pre-restore rollback ZIP (because verification rejects before the swap):

| Attack on the ZIP copy | Expected result |
|---|---|
| Remove `data/madar-unified.sqlite3` | Reject before swap |
| Alter archived SQLite bytes without updating ZIP manifest | Reject checksum |
| Remove a referenced attachment blob | Reject missing member |
| Add a `data/../` traversal member | Reject unsafe path |
| Alter blob bytes and **update outer ZIP manifest checksum** | Reject inner attachment integrity |
| Embed invalid automation audit outcome, **recompute SQLite revision SHA-256 and outer ZIP manifest** | Reject semantic validation of five-domain journal |

An additional test confirms `offline=True` is mandatory for both APIs.

## Commands and verified results

Run using a regular Python test runner from the Madar Desk project root:

```powershell
python -m unittest discover -s tests -p test_automation_full_recovery.py -v
python -m unittest discover -s tests -p test_full_recovery.py -v
python -m unittest discover -s tests -p test_automation_storage.py -v
python -m py_compile tests/test_automation_full_recovery.py
```

**Initial focused run:** `test_automation_full_recovery.py` = **4 PASS,
0 FAIL, 0 ERROR** (`exit code 0`, 2.034 s on the test workstation).

**Regression and verification run:**

| Test command | PASS | FAIL | ERROR | Exit code |
|---|---:|---:|---:|---:|
| `test_automation_full_recovery.py` | 4 | 0 | 0 | 0 |
| `test_full_recovery.py` (existing) | 11 | 0 | 0 | 0 |
| `test_automation_storage.py` (existing) | 12 | 0 | 0 | 0 |
| `py_compile` for the new test | successful | 0 | 0 | 0 |

**Total:** 27 passed tests, no failures or errors. The existing recovery
suite uses its own synthetic subprocess fault-injection case; the **new**
five-domain verification suite does not launch any subprocess or application.

## Boundaries and residual risks

This verifies the production *offline full archive and restore API* on an
activated five-domain SQLite database and actual attachment storage. It does
not exercise a real production installation, the native app UI, a live LAN
session, or an actively running writer. `offline=True` is an **assertion by
the caller**; no OS-level process lock is acquired by this API. The operator
must stop all writers before taking a full backup or restoring one.

The integrated data is backed up using SQLite's online backup API and the
attachment manifest/blob checks. This suite checks backup correctness,
restoration and malicious/corrupt archives, but does not claim every possible
fault injection or power-loss condition is covered. Real-world recovery
should retain the produced pre-restore ZIP and previous root until verification
and must not automatically overwrite newer data without operator approval.

**Storage compatibility note:** The current five-domain validator accepts old
four-domain snapshots, but a released older four-domain-only executable may
not read a database whose head contains the fifth `automation` domain.
Production activation/downgrade remains Prime's responsibility.
