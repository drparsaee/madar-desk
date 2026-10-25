# Madar Desk 1.0 RC1: evidence-based verification (2026-10-21)

**Status: release candidate, NOT a certified/stable v1.0 release.** This record
distinguishes implemented code from a physical deployment acceptance. It does
not imply that real user profiles, Google accounts, or two physical computers
have been tested. All new integration suites use disposable test roots.

## Artifact and reproducible build

- Source workspace: `D:\CoS-Test\madar-desk`.
- RC package name/version: `Madar-Desk-v1.0-rc1.exe` / `1.0.0-rc.1`.
- Build command: `npm run dist:rc` (Vite then PyInstaller onefile/windowed).
- Built executable: `release/Madar-Desk-v1.0-rc1.exe`, **13,763,139 bytes**.
- SHA-256 measured after rebuilt post-security-fix artifact:
  `05B87B883C4CDA6EE9900DBCB1CC3818D738847066AF749A54DBD0BE827BC6F6`.
- Previously released `release/Madar-Desk-v0.6-custom-preview.exe` was not
  replaced. This is NOT a code-signing or antivirus result.

## Executed checks

| Verification | Observed result | Evidence in workspace |
|---|---:|---|
| `npm run build` (final React/Vite bundle) | PASS, 1,619 modules | `.qa-v1-rc1-finalbuild.log`, package build output |
| `npm test` after all new modules and final host changes | **442 Python + 76 Node = 518 PASS, 0 FAIL** | `.qa-v1-rc1-shipping-alltests.log` |
| `py -3.12 scripts/release_qa.py` in isolated APPDATA | **16 PASS** | `.qa-v1-rc1-releaseqa.log` |
| `py -3.12 scripts/release_qa.py --full` with separate disposable `APPDATA` and `LOCALAPPDATA`, final source | **442 Python + 76 Node PASS**, exit 0 | `.qa-v1-rc1-shipping-isolated-final.log` |
| Real mounted HTTPS integration security (one localhost host) | **11 PASS** | `tests/test_integration_http_security.py`, `SECURITY_API_MOUNT_REVIEW.md` |
| Mounted HTTPS API read, CAS PATCH & replay | **2 PASS** | `tests/test_release_integration_http.py` |
| Opt-in automation engine with host SQLite, receipts and restart | **3 PASS** | `tests/test_release_automation_host.py` |
| Five-domain offline recovery + file attachments and tamper cases | **4 PASS**, worker report | `tests/test_automation_full_recovery.py`, `AUTOMATION_RECOVERY_VERIFICATION.md` |
| Final rebuilt EXE Windows GUI smoke | **9/9 PASS**, exit 0 | `v1-gui-smoke-t6080f7d/diagnostics.json`, `GUI_SMOKE_V1.md` |
| GUI smoke harness fixture regression | **13/13 PASS** | `tests/test_gui_smoke_harness.py` |
| MCP bounded stdio (legacy JSON-RPC subset, HTTPS backing) | **9/9 PASS**, worker report | `tests/test_mcp_stdio_v1.py`, `MCP_STDIO_V1.md` |
| Portable RC installer sandbox copy & hash test | **1/1 PASS** | `tests/test_release_portable_install.py` |
| Safe portable installer/updater with rollback (disposable dirs) | **17/17 PASS**, worker report | `tests/test_portable_installer.py`, `PORTABLE_INSTALL_V1.md` |
| Signed webhook outbox library | **16/16 PASS**, worker report | `tests/test_webhook_outbox_v1.py`, `WEBHOOK_OUTBOX_V1.md` |
| Source archive generation and ZIP CRC integrity | PASS, 180 entries, expected modules present | `release/Madar-Desk-v1.0-rc1-source.zip` |

The first full npm run while another agent was still editing a new security
test failed the chunked-body acceptance. An explicit `Transfer-Encoding`
rejection was implemented in `lan.py`; the regression and subsequent **complete
518-test run** passed. No claim is made about further live proxy behavior.

## Scope delivered, with boundaries

**Task/card UI:** cover, named checklists, custom fields, Planner, reports and
CSV, Trello JSON import, ICS file preview/export, paid legacy checklist removal
guard, long server-specific Planner namespace. Public CSV/API projections omit
finance. Planner uses account-scoped plaintext localStorage and reminders only
while the app is running; Trello/ICS imports are bounded subsets, not perfect
roundtrips.

**Network:** Existing LAN HTTP/HTTPS plus opt-in versioned integration REST
routes mounted on the *same HTTPS* LAN listener. Keys are issued locally to
administrator via trusted desktop bridge, held hashed in server RAM, expire,
and can be revoked. Role/project scope checked at request time. No public
internet listener, durable API tokens, OAuth calendar sync or signed outgoing
webhook delivery is asserted here.

**Automation:** Existing rules UI and due scheduler; new opt-in 5-domain SQLite
journal engine with queued/due execution, bounded retry, receipts and audit.
Activation first saves a SQLite backup, then commits the fifth automation
domain with a CAS revision. **An old 0.6 binary cannot open an activated
five-domain database**, so downgrading needs a planned restore of the backup.

**Recovery:** Explicit OFFLINE backup/restore/recover maintenance CLI, pre-open
crash-journal refusal and backup-first rollback. Archive has manifest/integrity
checks but is **unencrypted**, potentially including LAN password hashes,
financial records, and attachment binaries; never upload this complete ZIP to
Google Drive by default. The writer process guard is best-effort, not a formal
guarantee against arbitrary uncooperative writers.

**Executable GUI screenshot:** Final isolated EXE rendered the seeded board
with five columns and four task cards. A screenshot was captured at 1484×921;
structural PNG integrity and complete image scanlines checked separately, and
the image was visually inspected for obvious missing layout/blank render. The
native screenshot callback still reports `done:false`, although the complete
image exists; the strict QA harness records this discrepancy as a **warning**
not as a proven native callback success. The harness opened and terminated
only its own Windows Job process, leaving real Windows profiles untouched.

**MCP:** Separate opt-in stdio subprocess offers a read-only three-tool legacy
MCP subset, backed by trusted-certificate-pinned HTTPS integration API.
Limited to clients able to negotiate the supported protocol versions; no
assertion of compatibility with all modern MCP clients or live external apps.

**Webhook:** Signed, bounded HMAC outbox library offers idempotent enqueue,
delivery receipts, retries, dead letter audit, and callable ACL/secret/transport
injection without persisting secrets. This is **not live webhook sending**:
no validated outgoing TLS transport, host persistence/registration or UI is
wired. See `WEBHOOK_OUTBOX_V1.md` for the exact tested boundary.

**Portable installer:** A separate, explicitly invoked `scripts/Install-MadarDesk.ps1`
checks local PE structure, SHA-256, locked target and protected profile paths,
stages same-directory updates and keeps a rollback backup. Tests intentionally
install into disposable directories only. This is NOT an MSI, signing or an
automatic background updater; an optional independently trusted source SHA-256
should be supplied to the command. See its dedicated documentation.

## Release acceptance gates not yet established

- True two-physical-Windows-machine encrypted LAN interoperability under
  drop/reconnect, concurrent edits and firewall conditions.
- OAuth connections and live interoperability with Google/Outlook calendars;
  only offline `.ics` interchange is implemented and tested.
- Multi-hour GUI walkthrough, end-user workflow acceptance and performance
  load testing with realistic datasets; the successful single-page EXE smoke
  does not cover these.
- Code signing, MSI/MSIX distribution and automatic background updater
  infrastructure. An opt-in portable installer script is available and tested
  only against temporary destinations.
- End-to-end live signed webhooks, external MCP client compatibility (if a
  bounded connector exists, refer to its dedicated test report), and plugin
  marketplace. Do not infer functionality from a roadmap entry alone.
- Cloud Drive sync verified on physical external accounts; full backup ZIP must
  not be substituted into the old task-only Google Drive backup workflow.

**Decision:** Keep as RC until outstanding physical and external acceptance
tests are evidenced. Do not overwrite an existing data root as a smoke test.
