# Madar Desk | Python suite phase 3 characterization

Date: 2026-11-01. Worktree: `D:\CoS-Test\madar-codex-modernization-phase2-20261101`.
Branch: `modernization/phase2-20261101`; HEAD observed before the audit: `60beedd589903949269464176416ae6bebf78fb7`.

## Execution and boundaries

Command (Python 3.12.10):

```powershell
python tools/modernization_python_suite.py --workers 6 --timeout 75
```

The runner used **one Python child process per module**, with a different disposable `APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`, `HOME`, and `USERPROFILE` for every module. Each test module has an explicit 75-second timeout. It never called an installed application or read real Parsian data. Per-module stderr and counts are in `full_python_phase3_results.json`; local home and repository paths are redacted from diagnostics. The child process roots were deleted at completion.

`pytest` was not installed for Python 3.12, so this audit used the repository's stdlib `unittest` tests. The opt-in `test_packaged_madar_host_exe.py` was excluded deliberately because it can launch a built executable; packaged executable acceptance remains untested. UI/browser/Node tests, installed software, real LAN devices, operational databases, and real-user migrations are outside this Python audit.

| Measurement | Observed |
| --- | ---: |
| Python test modules discovered | 168 |
| Executed / excluded | 167 / 1 |
| Passed / failed modules | 136 / 31 |
| Timed-out modules | 0 |
| Tests reported by unittest | 1,595 |
| Skipped / expected failures | 2 / 2 |
| Unexpected unittest errors | 106 |
| Unexpected assertion failures | 3 |
| Elapsed suite wall time | 93.25 seconds |

The original report counter briefly included `expected failures=2` as ordinary failures because of a parsing regex. The parser was corrected and the existing stderr was **recounted without rerunning the tests**. There are three unexpected assertion failures, not five.

## Failure classification

**Probable common fixture drift: 29 failing modules.** Production `native_app.Bridge.__init__()` now creates `empty_initial_state()` on a new profile (`native_app.py:485-486`), whereas older integration tests implicitly assume `initial_state()` with `p-sample`, example cards and boards (`native_app.py:328-370`). This is consistent with the owner's decision not to seed customer profiles with test cards. The failure shapes include `Card not found`, `Project not found`, `StopIteration` searching the sample board, `IndexError` on sample tasks, and HTTP 400 when attempting to grant access to a nonexistent sample project. These are **diagnostic explanations**, not proof that all 29 modules would pass after fixture repair.

Representative verified traces:

- `test_attachment_bridge.py`: `attachmentUpload('example-2', ...)` raises `AttachmentError: Card not found`; setting `projects=['p-sample']` for a LAN editor raises `ValueError: یک پروژه در محدوده دسترسی وجود ندارد.` The test `setUp()` constructs `Bridge()` without creating a sample state.
- `test_automation_buttons.py`: `setUp()` selects a board where `projectId == 'p-sample'`, raising `StopIteration` on the empty fresh profile.
- `test_madar_host_service.py`: the synthetic newly provisioned HTTPS host returns zero tasks, but the test asserts it must return four at line 139 (`AssertionError: 0 != 4`). A fresh host should not silently gain sample tasks.
- `test_release_lan.py` and `test_new_http_endpoints.py`: HTTP 400 during fixture setup when granting permissions; these appear consistent with nonexistent project grants, pending targeted confirmation after fixture repair.

**Unresolved behavior or test expectation: `test_bridge_offline.py`.** `test_client_does_not_discard_overlapping_edit` expected a `RuntimeError('CONFLICT')` after concurrent offline/local and host edits, but no error was raised. It explicitly constructs the synthetic sample with `initial_state()` and is **not explained by the default empty profile**. The test's disconnected/reconnect state and the actual `OfflineStore.reconcile` path need a focused reproducible check before altering runtime behavior. This is a potential data-conflict regression; release is blocked pending resolution.

**Output-format-only assertion: `test_portable_installer.py`.** `test_fresh_portable_install_creates_only_exe` verified the exact installed EXE bytes and the source bytes, then failed because the PowerShell auto-formatted table printed only `0e` of the SHA column instead of the first eight expected hex characters. The recorded example has a very long worktree path, which narrows PowerShell's table columns. This is a fragile stdout assertion, not evidence of an incorrect installed byte stream. The rest of the module's tests passed. Retain the binary comparison and use explicit machine-readable hash output if this display assertion must remain.

## Minimal safe follow-up

1. Add one **test-only** helper that saves `normalize_state(initial_state())` into each *test's own disposable* `tasks.json` before calling `Bridge()` or provisioning the synthetic LAN host. Use it only in test classes whose assertions explicitly refer to `p-sample` or `example-*`. Do not change the production `empty_initial_state()` behavior. Fix the main fixture consumers and rerun their modules before expanding to the rest of the 29.
2. For HTTP integration tests, explicitly create sample projects before assigning their IDs to editor/viewer accounts. Distinguish permission rejections from missing fixture scope; do not loosen production ACL.
3. Independently investigate the overlapping-offline-edit test. Check whether `_network_available`, reconnect cooldown and `OfflineStore.reconcile` run with the host revision supplied by the test, and prove either conflict preservation or a legitimate changed contract.
4. Replace the installer table-width-dependent assertion with a stable structured output contract or remove the redundant formatted-string check while retaining the verified byte/hash checks.
5. Re-run the isolated Python suite after fixture repairs and after concurrent worker edits settle; then run separate packaged-EXE acceptance only in a deliberately isolated release environment.

## Confidence limits

The suite was launched from a clean worktree at HEAD `60beedd`; during its 93-second execution, other modernization workers began changing some tests and source files. Therefore its result is an **observed run**, not a guarantee that every test ran against an immutable single revision. The per-module diagnostics retain only the final 10,000 characters, so some multiple-error modules have truncated intermediate tracebacks. No fixture test files, runtime source, installed programs, customer databases, or real user profiles were modified by this worker. No full-suite PASS, real-world migration or deployment is claimed.
