# P0 modernization follow-ups (read-only worker findings)

These are **worker-reported synthetic reproductions**, not independently
reproduced or repaired by the integrating agent in the host-junction change.
Treat each as an unverified lead until a fresh red/green test is executed on
the then-current LocalForge `main`. No real profiles, finance data, or EXEs
were used by the reporting workers.

## MD-O02 | LAN login lockout reset by a different valid account

- Baseline reported: `6606ed6`; `lan.py` `LanService.authenticate`, around
  lines 405-419, increments `self.failed[ip]` for bad credentials but removes
  the whole IP counter on **any** successful login.
- Worker-reported synthetic in-memory sequence: five invalid `admin` attempts
  from one IP, one valid `viewer` login from the same IP, then further invalid
  `admin` attempts. The valid viewer login cleared the shared failure counter.
- Next bounded ExecPlan: characterize legitimate user login and lockout,
  reproduce interleaved-account bypass with a new test, preserve per-account
  lockout even if another account authenticates, then run LAN/ACL and full safe
  suites. Keep host permissions and credentials unchanged.

## MD-O15 | Automatic backup identity companion omitted during restore

- Baseline reported: `6606ed6`; `standalone_accounting_auto_backup.py` writes
  a SQLite backup and optional `.users.json` companion, while
  `standalone_accounting_restore.py` accepts a missing identity companion as
  a legacy SQLite-only backup.
- Worker-reported disposable reproduction: produce an automatic backup with
  a synthetic admin registry, omit `.users.json` in a partial transfer, then
  restore. Restore accepted the ledger without a user registry, making the
  protected desktop book inaccessible through normal company login.
- Next bounded ExecPlan: add a versioned, last-published completion manifest
  with expected companion names/digests; reject missing/mismatched declared
  companions before publishing restore; preserve explicit legacy one-file
  manual backups. Test interruption and rollback with synthetic files only.

Neither item is a release approval or a claim of full migration coverage.
