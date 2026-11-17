# E0–E7 Madar QA: historical full suite vs reviewed current architecture

**Scope and truth:** source-level classifier for detached Madar worktree only.
Historical evidence: `D:\CoS-Test\MTR_E0_E7_fullqa_20261110_afterfix.json`,
report SHA-256:
`974fc07d9380780eb85ba26763f9ba21557b49b9fc53db31523cf2a507821d53`.
The report was generated 2026-11-10 05:29:02 UTC, Python 3.12.10, with
disposable profiles and per-module process isolation.

**Historical full suite is NOT GREEN.** The original result must remain:

| Historical measure | Exact report |
|---|---:|
| Modules discovered / executed | 250 / 249 |
| Modules passed / failed | 227 / 22 |
| Unexpected test errors | **118** |
| Failed assertions | **9** |
| Test cases reported | 2,529 |
| Explicit existing packaged-EXE exclusion | `test_packaged_madar_host_exe.py` |

The source-level review identifies **21 failing test modules that still
exercise retired in-Madar finance/accounting APIs** (including mixed
task-finance integration suites). They contribute **117 errors and 9 failed
assertions**, but they are **not deleted, changed, marked passing or omitted
from the historical full report**. They should eventually be replaced with
equivalent tests of the optional authenticated Taraz integration, and any
non-financial features within mixed modules need replacement coverage.

The explicitly reviewed retired test modules (SHA-256 of each current source
is pinned in `tools/mtr_release_suite_scope.py`) are:

1. `test_accounting_bridge.py`
2. `test_authenticated_intake_cas.py`
3. `test_card_trash_contract.py`
4. `test_finance_bridge.py`
5. `test_finance_overview.py`
6. `test_finance_reference_bridge.py`
7. `test_list_archive_contract.py`
8. `test_new_http_endpoints.py`
9. `test_purchase_host_adversarial.py`
10. `test_purchase_intake.py`
11. `test_release_lan.py`
12. `test_release_persistence.py`
13. `test_rial_host_read_bridge.py`
14. `test_rial_host_security_invariants.py`
15. `test_rial_purchase_host_integration.py`
16. `test_sqlite_export_bridge.py`
17. `test_standalone_accounting_end_to_end.py`
18. `test_standalone_accounting_host.py`
19. `test_standalone_task_prepare.py`
20. `test_unified_bridge.py`
21. `test_user_acceptance_workflows.py`

The **remaining historical failed module is current architecture**:
`test_mtr_e2_recovery_security_20261110.py`, **1 error, 0 failed assertions**.
Its historical diagnostic reports
`AttributeError: 'MtrE2HostPeerPilot' object has no attribute '_journal'`.
This is not a retired failure. Current code may have changed after the
historical report; a fresh disposable-profile rerun is necessary.

## CLI: explicit, fail-closed gates

From the detached Madar worktree:

```powershell
# Read-only historical classification. EXPECT exit code 1 for the real report.
$env:PYTHONDONTWRITEBYTECODE = '1'
py -3.12 -B tools/mtr_release_suite_scope.py

# New classifier unit contracts (no real network or accounts).
py -3.12 -B -m unittest -q tests.test_mtr_release_suite_scope
```

Historical classification verifies aggregate counters against all 249 module
rows, every reviewed module's present source SHA-256 and its retired-finance
source markers, and the explicit original packaged-EXE exclusion. Any
unreviewed failed module, unexpected exemption, changed reviewed source,
missing test, or inconsistent summary **blocks** the process. A newly
discovered current test is included, not silently excluded. The original
full-suite failure count is *always* displayed as historical evidence.

To re-run only the single previously failed current E2 module, under the
existing `tools/modernization_python_suite.py` per-child disposable profile
and the `safe_test_runner.isolated_environment` parent scrub:

```powershell
py -3.12 -B tools/mtr_release_suite_scope.py --run-current `
  --known-failures-only `
  --approve-retired-sha256 b2d4ff6e9f7afcbf337d23bd65c5b674eaaf87a07c9a6e5ec0df296c753babb9 `
  --workers 1
```

The approval argument must match the exact SHA-256 of the 21-name reviewed
mapping (including source hashes). No new name is excluded because it sounds
like accounting. This targeted run checks **only the E2 recovery module**,
which uses synthetic in-process mock peers and no network. It is not a
current-suite pass or release authorization even if all tests pass.

To run the entire current-architecture source suite in a separately
authorized environment, omit `--known-failures-only` and keep the explicit
retired-set approval digest. This discovers every `tests/test_*.py`,
subtracts exactly the 21 reviewed source-pinned retired modules and the
historically explicit packaged-EXE test, and executes the rest, including
newly added modules, via the existing disposable-profile child runner.
**This full current-scope run was not carried out under the present
no-network authorization** because many existing source test modules start
synthetic loopback HTTP listeners. It needs separate network-test authorization.
The full-suite historical result must remain visible even if the narrower
current run is green. A clean current-scope run is necessary but not
sufficient for release readiness: packaging, independent Taraz E2/E4
integration, migration recovery, real ACL and deployment gates remain.

## 2026-11-10 execution evidence

- Source classifier's **11/11 unit tests PASS**, Exit Code **0**.
- Actual historical classifier: **Exit Code 1**, accurately reports 118
  original errors, 9 assertions, 21 retired failing modules and one current
  E2 historical failure, with no hidden tests.
- Targeted fresh `test_mtr_e2_recovery_security_20261110.py` via approved
  disposable child-runner: **15/15 tests PASS**, Exit Code **0**,
  0 errors/0 assertions. This resolves only the observed *rerun result*
  for that module; the historical file itself is unchanged.
- No actual full current-scope run or new full source-wide run was performed.
  In particular, nothing here claims an E0–E7 release-ready artifact.

Only new classifier, tests and this documentation were created. No historical
test, production source, original runner, source JSON report, user profile,
installed service, network endpoint, commit, push or deployment was modified.
