# ExecPlan | Safe, reproducible `npm test` for Madar modernization

## Purpose, user decision, scope
Owner requires continuous safe modernization checks but no access to actual customer profiles, installed software or live Parsian. Main source baseline 6f0da57ad40b59cc60a9db8347b391dd3ca2f995. Previous UI fix made npm test build the latest Vite output, but `npm test` still runs unittest discovery directly in the calling environment and Node browser tests without redirecting the complete Windows profile. This pilot makes the default test entry point an isolated launcher. Scope: package.json, a new standard-library-only tools/safe_test_runner.py, tests/test_safe_test_runner.py and this plan.

## Existing behavior / risks
`tools/modernization_python_suite.py` already isolates each Python module in distinct APPDATA/LOCALAPPDATA/TEMP/HOME/USERPROFILE directories, detects module-level failure and explicitly excludes packaged EXE launch. It normally writes its diagnostic report to a tracked file unless supplied --report. `npm test` currently bypasses it, invokes unittest on the actual ambient environment, then Vite build then node --test, which serves the local dist and may load state from ambient user profile. Existing browser tests use hard-coded read-only Chrome and Playwright paths; do not attempt installation or package download.

## Desired contract
1. Default `npm test` invokes a stdlib Python launcher that establishes a fresh temporary Windows user profile for all phases, scrubs inherited MADAR_* variables and per-profile storage paths. It must not read or write a real application data directory; existing test modules are responsible for synthetic fixtures.
2. Run existing per-module Python subprocess isolation (not the original raw unittest discovery), write report only inside the temporary QA root, and fail if any executed module fails or times out. The opt-in packaged-EXE test remains excluded and clearly reported.
3. Build current Vite output before any Node tests; preserve the serial Node test policy and explicit glob file selection. Abort and surface meaningful diagnostics on build or test failure; no released EXE is created.
4. Parse reported Python tests, skips, expected failures and Node tests, failures, skips; never mislabel skipped checks or a successful source run as deployed version acceptance.
5. Retain `npm run build`, `npm run dist:rc` and all release/financial commands untouched.

## Execution / progress
Baseline current source separate Python audit returned 168/168 modules, 1,612 tests, 2 skips, 2 expected failures and no unexpected failure after duplicate-ID correction; current source JS UI suite was 530/530 after build in previous turn. RED proof for ambient profile: `package.json` currently calls `python -m unittest discover` and raw `node --test`, with no environment sandbox.
Implemented `tools/safe_test_runner.py` as the standard `npm test` entry point. It uses the existing per-module Python test runner and disposable report root, then builds the current Vite bundle and runs all Node tests serially. A 5-test unit module asserts the environment scrub, subprocess path, Chrome compatibility exception and fail-closed Node result parsing.

The **first complete `npm test` attempt** returned Python **169/169 modules, 1,616 tests** and a successful build, but Node browser launches failed: this Windows Chrome version rejected Playwright's explicit temporary `--user-data-dir` whenever `USERPROFILE` was rewritten. Isolated browser tests confirmed a synthetic `HOME` works while a rewritten `USERPROFILE` does not. The launcher therefore retains only the original Windows `USERPROFILE`/drive identity **for the Node/Chrome phase**, while overriding its `APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`, `HOME`, `XDG_DATA_HOME` and Playwright browser profile. Python/accounting tests retain fully synthetic `USERPROFILE` and HOME. The tested Node phase uses fixture data and a fresh temporary Playwright profile, but this exception means Windows user identity is not wholly virtualized for the browser process.

Final full `npm test` exit code **0**: Python **169/169 modules, 1,617 tests** (2 skipped, 2 expected failures, 0 unexpected failures/errors/timeouts), Vite build PASS, Node/React/Playwright **530/530 tests passed, 0 skipped**. The opt-in packaged EXE test remained excluded. No installer, live company ledger, actual Parsian backup, production profile or signed release was exercised. Git commit/push remain separately verifiable.

## Explicit exclusions
User-tested physical PC acceptance, live accounting migration/Parsian data, installed exe/release signing and AV/SmartScreen are out of scope. Build writes disposable dist and public/fonts generated resources under source checkout, not customer profiles. No internet access is necessary or authorized.
