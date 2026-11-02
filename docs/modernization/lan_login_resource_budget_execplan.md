# ExecPlan | Bound unauthenticated LAN login resource use

## Baseline and priority

Private LocalForge `main` and `origin/main` both at `45b143a51e9d1383c68e25df06a8718a7216a620` after fetch on 2026-11-02. Two unrelated untracked Trello research folders are not in scope. PROJECT_CONTEXT MD-O02 and DECISIONS MD-D06 require a host-side secure login boundary. This work changes only LAN login input limits, synthetic tests and this plan, not customer profiles, Parsian, installed EXEs or operational state.

## Red characterization

The ordinary `/api/login` POST parser accepts up to 16 MB before JSON parsing, and `authenticate` accepts arbitrary-length username/password strings before SHA-256/PBKDF2. `password_hash` also permits creating passwords that a bounded login would later reject. Synthetic tests must demonstrate an oversized declared login body is refused before reading, overlong direct credentials never enter PBKDF2, and new accounts cannot be created with an unloginable password. Existing short and normal-length credentials must remain compatible; ordinary valid/invalid account timing parity is preserved.

## Minimal repair

Limit `/api/login` declared JSON body to 64 KiB while retaining the larger upload allowance on other routes. Enforce a 4096-character upper bound on LAN passwords in both creation and authentication, and the already documented 40-character upper bound on usernames during login. Keep existing minimum password length, lockout counters, dummy KDF for well-formed unknown usernames, TLS, role/ACL and sessions unchanged. Previously created passwords above the new bound are not guaranteed compatible; this is an explicit security tradeoff, not a claim of zero behavior change.

## Gates and limits

Run RED against untouched source; then focused LAN, TLS and identity suites, the official isolated `npm test` Python/Node/Vite gate, syntax and `git diff --check`. Only on success commit and push the three scoped files to LocalForge main and read back the remote SHA. Synthetic loopback traffic and temporary files do not establish real two-PC, installed-EXE, physical crash or customer migration acceptance.

## Executed evidence (2026-11-02)

- RED on unchanged `lan.py`: the initial HTTP fixture declared a large body but sent none, resulting in a client timeout rather than a useful status assertion. The fixture was corrected to send a complete synthetic JSON body and stub out the password verifier. The repeatable RED run then exited **1** with **3/3 failing assertions**: oversized HTTP login reached the verifier, oversized direct credentials reached the verifier, and an oversized new password was accepted for hashing. No operational data was accessed.
- GREEN focused: `python -B -m unittest tests.test_lan_login_resource_limits tests.test_lan_unknown_account_kdf tests.test_lan_account_lockout tests.test_lan_security_framing_phase4 -q` exited **0**, **15 tests OK**. Ordinary unknown-account KDF parity and account/IP lockout tests remained green.
- GREEN official source QA: `npm test` exited **0**. Python: **184/184 executed modules**, **1,684 reported tests**, two skipped, two expected failures, zero unexpected failures/errors/timeouts. Vite build passed. Node: **540/540 passed**, zero skipped/failures. The packaged EXE test is excluded by the official runner.
- The limit applies to newly created passwords and all login attempts; a hypothetical previously stored password longer than 4096 characters requires an explicit recovery/reset path. No installed application or real account was inspected, so no claim about the presence of such an account is made.
