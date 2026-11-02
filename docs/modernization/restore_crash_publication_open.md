# OPEN | Composite accounting restore is not crash-atomic

## Synthetic evidence and impact

Independent audit on `main` baseline `8da0f1ee`: `standalone_accounting_restore.py` publishes the restored SQLite file with `os.link()` before publishing optional template and identity companions. A forced subprocess termination immediately after SQLite publication leaves a visible restored ledger with no `local-users.json`; retry then hits the no-clobber destination guard. This is an unresolved crash-consistency defect, not a release acceptance result.

The read-only audit worker reported a deterministic RED run, exit 1, one expected assertion failure. The first integrated source QA also discovered the audit while it was in `tests/` and failed on that one module. The isolated synthetic reproduction is preserved as `docs/modernization/audits/restore_crash_publication_red.py` and intentionally not included in the green regression suite until a repair is implemented. It uses temporary synthetic accounting data and identity records, not user or Parsian data.

## Next bounded ExecPlan

Preserve the no-clobber contract and legacy manual restore. Reproduce interrupted publication after *each* member using subprocess termination and synthetic temporary directories. Design a crash-safe publication protocol in which no incomplete ledger is visible as a completed restore and recovery cannot delete unrelated files. A simple reorder of hardlinks is not sufficient if orphan companions then block retry. Implement durable completion/recovery semantics with ownership checks, and test ordinary exceptions, hard process termination, rollback, idempotent retry and legacy restore. Only then move this red characterization into the default suite and run complete safe QA. Physical power-loss durability and installed-EXE acceptance remain separate gates.
