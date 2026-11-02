# Accounting restore validation matrix

- Baseline: reproduce process exit immediately after SQLite hard link; ensure failure before patch.
- Publication: terminate after each optional companion hard link and after final SQLite hard link; verify SQLite absent until all companions exist; retry identical source, check byte-identical companions and ledger.
- Recovery: interruption before publication, repeated retry, mismatched source, corrupt staging and foreign destination file; never delete foreign content.
- Exception: injected hard-link failure and directory-sync failure roll back only owned destination paths, including racing replacements.
- Legacy: explicit SQLite-only manual restore retains no-clobber and revision equality.
- Concurrency: exactly one of two competing restores publishes.
- Broader gate: focused Python suites, then `npm test` (synthetic profile Python, build, JS tests), diff review, LocalForge push verification if green.
