# E7 current-source QA: bounded pre/post Python SHA-256 gate

**Worktree:** `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107`.
The E0–E7 source QA checker has new fingerprinting logic in
`tools/mtr_release_suite_scope.py` and synthetic regressions in
`tests/test_mtr_release_suite_scope.py`. No historical test, production
module, prior QA runner, build script or installed service was modified.

## Why this gate exists

The previously reported **236/236 current-source modules passing** occurred
in a shared dirty worktree. Another agent may change a module between the
first and last test, so a passing test-runner summary alone cannot attest
that a single source revision was tested.

The optional `--run-current` command now takes a bounded Python source
inventory **after selecting current test modules and before starting child
processes**, and repeats it **after all tests finish, before returning a
successful result**. It verifies the selected test-module inventory a
second time before execution and after the final fingerprint. The existing
`modernization_python_suite.execute_module` disposable per-module profile
runner is unchanged.

The source inventory includes every `*.py` file recursively under this
worktree, **including untracked, modified and retired historical test files**.
It is not based on `git ls-files` and does not ignore failed modules. Its
explicitly ignored folder names are only `.git`, `__pycache__`,
`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox`, `.nox`,
`.venv`, `venv`, and `node_modules`, at any depth. Their contents
are not part of the source fingerprint. A symlink/junction/reparse point in
the scanned tree, including an excluded directory itself, is rejected.

The scanner uses filesystem metadata and no-follow semantics where the OS
supports them, hashes file contents with SHA-256, and records a canonical
sorted `[relative_path, sha256]` list in the aggregate SHA-256 digest.
Each snapshot has explicit bounds: 12,000 Python files, 20,000 directories,
150,000 directory entries, 32 MiB per Python source and 512 MiB total.
Any bound, read, path-safety, changed-in-flight, or pre/post mismatch
causes `SCOPE_BLOCKED`, exit code **2**; no successful
`CURRENT_SCOPE_QA` result is published. The diagnostic reports bounded
counts/names of added, removed and content-changed files, not source
contents. An unchanged run returns the original current-scope result shape
plus `sourceSnapshotSha256`, `sourceSnapshotFiles`,
`sourceSnapshotBytes`, `sourceSnapshotMatchedPrePost: true`, and
`sourceSnapshotExcludedDirectories`.

The old historical report remains failed: **118 errors, 9 assertion
failures, 22 failing modules**. The 21 explicitly reviewed retired
accounting test modules and their original source SHA-256 pins are unchanged.
This snapshot gate neither rewrites that report nor grants release approval.

## Exact checks

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
py -3.12 -B -m unittest -q tests.test_mtr_release_suite_scope
```

Synthetic disposable fixture tests cover unchanged source identity and
fingerprint reporting; same-size edits; new and deleted Python modules;
symlink/reparse-path denial; source size/file/entry limits; a new test
appearing between selection and the initial snapshot; blocked CLI exit
status; and preservation of historical full-QA counters. No 236-module
source suite, network, build, installer or live profile is exercised.

The scanner was also invoked **read-only once** against the shared worktree
to verify it can traverse that source tree. This is a point-in-time
fingerprint, **not** evidence of stable source during a long QA run and
**not** a release pass. Its count and digest can change while other workers
edit the shared tree.

**Observed bounded verification on 2026-11-10:** the updated classifier
suite completed **21/21 PASS, exit 0**, with both edited Python files passing
`compile()` syntax checks. The historical classifier still exited
**1** and displayed the unchanged 118 errors / 9 failed assertions.
The single read-only worktree scan observed **545 `*.py` files**,
**6,677,225 bytes**, SHA-256 aggregate fingerprint
`b2e24d23e45edf62f3c0b05b7f1fd10bae8357cb6c42661fbb8761886d207a66`
at that instant. This fingerprint is not an accepted release baseline,
and no 236-module current-scope suite was executed under this assignment.

## Important remaining limits

- Two endpoint snapshots do **not** detect a source change that is reverted
  byte-for-byte between checkpoints, and cannot make the shared directory
  immutable or prevent symlink-race attacks by privileged filesystem actors.
- SHA-256 equality proves the measured content set matches at those
  checkpoints, not that every test ran against one immutable source version.
  A release-grade invariant requires an isolated frozen Git commit/worktree
  or verified read-only copy, and a clean rerun there.
- Non-Python files (JS/TS, assets, tests outside `*.py`, build config,
  dependencies) are not fingerprinted by this gate. They require their
  own artifact/build attestation.
- No claim of binary signing, WebView2 acceptance, LAN/HTTPS security,
  cross-application integration or packaged-release readiness follows from
  passing these synthetic source-snapshot unit tests.

## Follow-on: non-Python source consistency (same day)

The prime extended `capture_source_snapshot` beyond the original Python-only
gate to include these executable/metadata file suffixes in the same bounded,
recursive SHA-256 inventory: `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`,
`.css`, `.ps1`, `.iss`, `.html`, `.json`, `.yaml`, `.yml`, `.toml`, `.ini`.
The same explicit excluded cache/venv directories, file/byte bounds,
non-following link checks and mismatch refusal remain in force. A change in a
React source or PowerShell installer helper during a Python source-suite run
can now block its result, rather than being invisible to the Python-only
snapshot. No claim is made about binaries, images, fonts, other unlisted
extensions or installed dependencies.

Two **new red-then-green disposable negative tests** cover modification of a
`.jsx` component and addition of a `.ps1` updater during the run: both failed
before the extension and both passed after it. Full scope-classifier unit tests
now **23/23 PASS, exit 0** (`py -3.12 -B -m unittest -q
tests.test_mtr_release_suite_scope`). One *point-in-time only* updated source
snapshot observed **961 files / 12,086,580 bytes**, SHA-256
`a429c9f636974165cc537c463bf27d96bf1c9839bbc7b1613214744a60602d80`.
Concurrent edits elsewhere can change that fingerprint at any time. A fresh
current-scope run under this extended gate is still necessary, and the worktree
remains dirty/non-release-ready.
