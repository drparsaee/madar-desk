# MD-O15 validation

Only disposable tests ran; no real user files, Parsian data, installed EXEs or production APPDATA were used.

- Baseline neighboring backup/identity/restore `unittest`: 52 tests PASS.
- RED reproduction: 4 new scenarios failed/errored before the manifest change as expected.
- GREEN adjacent regression: 58 tests PASS, including omitted/tampered/undeclared companion, interrupted final publication, retained prior copy, and previously supported one-file manual restore.
- Complete isolated Python rerun: 170/170 modules passed, 1630 tests reported, 2 skipped, 2 expected failures, no unexpected failure/error.
- Full official `npm test` rerun: Python 170/170 modules, build PASS, Node 530/530 tests passed, no Node skipped/failures. The initial integrated safe run had one unexpected Python error and did not reach Node; its temporary diagnostic was automatically deleted. The successful reruns do not identify that first transient error.
- Still outside scope: installed EXE validation, real-user restore, crash/power-loss fault injection across the filesystem durability boundary, and physical LAN devices.
