# RESOLVED IN SOURCE QA | Composite accounting restore crash publication

## Synthetic evidence and impact

Independent audit on `main` baseline `8da0f1ee`: `standalone_accounting_restore.py` publishes the restored SQLite file with `os.link()` before publishing optional template and identity companions. A forced subprocess termination immediately after SQLite publication leaves a visible restored ledger with no `local-users.json`; retry then hits the no-clobber destination guard. This is an unresolved crash-consistency defect, not a release acceptance result.

The read-only audit worker reported a deterministic RED run, exit 1, one expected assertion failure. The first integrated source QA also discovered the audit while it was in `tests/` and failed on that one module. The isolated synthetic reproduction is preserved as `docs/modernization/audits/restore_crash_publication_red.py` and intentionally not included in the green regression suite until a repair is implemented. It uses temporary synthetic accounting data and identity records, not user or Parsian data.

## Repair and observed source validation (2026-11-02)

`standalone_accounting_restore.py` now stages validated members inside a destination-side transaction directory protected by a process lock, with a ready record of exact source/destination and SHA-256 checksums. It publishes the optional template and identity companions before exposing SQLite. After an abrupt exit, the same explicit restore can resume only after validating the stage and verifying any existing output is the *same hard-link inode*; unrelated files block publication and are never overwritten. Normal exceptions revoke only owned hard links. Legacy one-file restores retain strict no-clobber behavior.

`tests/test_restore_crash_publication.py` exercises termination before the first link, after each member, resumed completion and second-run no-clobber, foreign destination preservation, changed backup rejection, ordinary failure rollback, and legacy one-file restoration. The historical `docs/modernization/audits/restore_crash_publication_red.py` reproducer was rerun after repair and passes. Adjacent source tests: 69/69 PASS. The official isolated `npm test` exit 0 reports 172/172 Python modules (1,641 tests, 2 skips and 2 expected failures, zero unexpected failures/errors), Vite build PASS, and Node 530/530 PASS.

The original independent RED observation on `8da0f1ee` remains an archived baseline. Physical power-loss durability, damaged transaction manual recovery, installed-EXE acceptance and real-user migration are separate unverified gates. Full design, parity and validation scope: `restore_crash_publication_execplan.md`, `_overview.md`, `_design.md`, `_validation.md`.
