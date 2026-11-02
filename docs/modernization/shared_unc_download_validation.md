# Shared UNC download validation (2026-11-02)

- Baseline: `aa99f21067d3c87aec392c05e933c905dbac1e36`; JS rejected synthetic UNC with a space in the Share name (`\\\\FILESERVER\\Scan Drive\\sample\\مهر\\English.zip`), while native validator accepted it.
- Before fix: `node --test tests/productivity.test.cjs` => 5 passed, 1 failed (Share space assertion).
- After fix: `node --test tests/productivity.test.cjs` => 6 passed, 0 failed; `python -B -m unittest discover -s tests -p test_native.py -v` => 23 passed, 0 failed.
- `python -B tools/safe_test_runner.py` => exit 0. Python reported 177/177 modules passed, 1,658 tests reported, 2 skipped, 2 expected failures, 0 unexpected failures/errors. Vite `npm run build` passed. Serial Node reported 530/530 passed, 0 skipped/failures. This uses disposable profiles and excludes packaged EXE.
- Windows KnownFolder read-only smoke: `windows_downloads_directory()` returned an absolute existing path on this QA Windows machine (path deliberately not logged).
- `git diff --check`: passed, no whitespace errors. Git emitted Windows LF/CRLF conversion warnings in normal diff operations.
- Final test fixtures use synthetic network paths; after replacing the original host-specific sample with `FILESERVER`, the focused tests were rerun. The full safe suite above ran against the same assertions before this fixture-only anonymization.
- Commit/push: to be verified separately against private LocalForge refs; source suite success alone does not establish either step.
- Live SMB path permission, actual downloaded file contents on two PCs and newly built/installed EXE: not verified. No live user or Parsian state was changed.
