# MTR phase execution status — evidence ledger, 2026-11-09

> This is not a claim that phases E0-E7 have completed or that a new version has shipped. The work described here is uncommitted in isolated worktrees, and all I/O/tests used disposable synthetic data. Official accounting truth stays solely in Taraz.

## Source baselines and locations

- Madar isolated worktree: `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107` at HEAD `32bd8ffe5ebbb0f4cd5c011c59323ed32f8647ac`, dirty with historical user-approved work and this pilot. Never clean/reset others' edits.
- Taraz original checkout: `D:\CoS-Test\000- Taraz\taraz-accounting-desktop` at HEAD `653089bb99747ab1c909cfdb113d2d12bc36e47a`, not modified for this E2 pilot.
- Taraz E2 detached worktree: `D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109`, same base HEAD. Modified only `taraz_integration.py` and `tests/test_taraz_integration.py`.
- No commit, push, installer, live LAN service change, financial posting, production backup/restore, cloud AI request or user profile modification.

## Phase-to-code/evidence matrix

| Phase | Source implemented or inspected | What is proven / explicitly open |
|---|---|---|
| E0 contracts | `mtr_finance_workflow_contract.py`, tests and integrated design docs | Pure request/amendment/replay decisions and synthetic tests exist; no approved production contract or comprehensive E0 acceptance |
| E1 order/CRM/AI | existing `madar_ai_draft.py`, AI user dashboard in `src/features.jsx`, `lan.py`, `native_app.py`; new `madar_ai_provider_policy.py` and tests | Admin-controlled local AI grant in synthetic host/browser; **pure** deny-by-default online BYOK provider policy tested (no actual provider API or secret vault). Real Ollama `qwen3:4b` listed but synthetic inference returned `model_unavailable` after 12s on 2026-11-09. CRM and full orders not complete |
| E2 request and receipt | Madar `taraz_exchange.py`, `taraz_review_status.py`, `mtr_e2_send_journal.py`, task UI manual prepare/queue and retry, Taraz isolated `taraz_integration.py`, cross-repo smoke | Explicit same-ID resend with stable first-send journal before file publication; cooperating per-ID OS lock and payload conflict checks; Taraz crash-resilient **metadata-only** review decision/receipt; synthetic cross-repo round trip passes. Still NOT authenticated, NOT true LAN transport or official financial receipt; one-active-intent limit and no multi-device acceptance |
| E3 deficiency loop | new `mtr_deficiency_workflow.py`, tests and separate pilot contract | Pure synthetic finance-reviewer referral, assigned correction, manual-only re-submission intent; no authenticated Taraz deficiency service, persisted audit or live routing verified |
| E4 customer matching | New `radar_party_match_preview.py` and tests | Pure same-org ACL-gated, explainable 4-field candidate preview with human-review flags; no authoritative Taraz party API, no decision audit or operational UI |
| E5 amendments | E0 pure amendment contract + new `mtr_amendment_review_preview.py` and tests | Pure independent amendments, warnings, field conflict/rejection/stale baselines; no operational state, atomic version submit, trusted Taraz rejection or linked financial review |
| E6 shared view/notifications | new `mtr_internal_notification_policy.py` and tests | Pure internal-only recipient plan and amendment summary, scoped redaction; no verified live delivery, authentic Taraz document link or atomic dedup |
| E7 acceptance | `docs/modernization/MTR_E7_ACCEPTANCE_GATES_20261109.md` + `tests/test_mtr_acceptance_matrix.py` | 32 AC + 8 G explicitly mapped and OPEN; Windows EXE, 2-device LAN, power loss, release/rollback acceptance not verified |

## Commands / results observed

- Madar `py -3.12 -B -m unittest -q tests.test_mtr_e2_cross_app tests.test_taraz_manual_retry_faults tests.test_taraz_manual_retry tests.test_taraz_exchange tests.test_taraz_review_status tests.test_taraz_link_status tests.test_mtr_finance_workflow_contract tests.test_ai_user_admin tests.test_madar_ai_draft tests.test_madar_ai_provider_policy tests.test_radar_party_match_preview` with `MTR_TARAZ_SOURCE` pointing at the isolated Taraz checkout: **109 tests OK**, exit 0, independently rerun. Includes cross-app send→review→readback→same-ID replay, corrupt-intent unknown, opposite-decision conflict, and OS lock fault cases.
- Taraz isolated: `py -3.12 -B -m unittest discover -s tests -p test_taraz_integration.py -q`: **20/20 OK**; `... -p test_taraz_link_status.py -q`: **8/8 OK**, independently rerun in detached Taraz worktree, exit 0. `git diff --check` passed with LF/CRLF warning (not an error).
- Madar fault-injection `tests.test_taraz_manual_retry_faults`: **8 cases** passed according to independent worker report; 31 related synthetic cases passed together. Real Windows OS hard-link exclusivity and two Python processes agreeing on same lock were exercised; not real Taraz EXE or physical two-PC testing.
- UI `node --test tests/general_ui_preferences.test.cjs tests/madar_lan_user_ui_runtime.test.cjs`: **5/5 OK**, exit 0, final rerun. Vite `node_modules/.bin/vite.cmd build`: final build passed, 1692 modules, nonblocking ~855KB main chunk warning. Both tracked `git diff --check` runs passed.
- Pre-existing `tests.test_lan` baseline still has **2 unrelated 404-vs-403 failures** for retired `/api/standalone-accounting/prepare` and `/quote` routes. Do NOT claim a full-green suite or release authorization.
- In this continuation: new local `mtr_e2_send_journal` and native/JS first-send preflight; independent fault review initially reproduced three dangerous native bypasses (missing JS wrapper, journal-less direct send and arbitrary request ID), which were fixed. Rerun `py -3.12 -B -m unittest -q tests.test_mtr_e2_send_journal_faults tests.test_mtr_e2_send_journal tests.test_taraz_manual_retry tests.test_taraz_exchange tests.test_taraz_review_status`: **50/50 OK**, exit 0, after fixes. Earlier 64 tests of adjacent journal+finance-contract suites also passed. The UI/Vite build passed after initial journal integration; the subsequent native/JS wrapper change needs a final stable build.
- E3 pure deficiency pilot: 37/37 tests passed (worker) and 27 previous contract tests passed; E5 pure amendment preview: 29 new tests and 27 prior contract tests passed; E6 pure internal notifications: 18/18 tests passed; E7 complete-trace matrix coverage: 4/4 tests passed. These were scoped synthetic tests, not operational E2E.
- A broad `py -3.12 -B tools/safe_test_runner.py` isolated profile run during other concurrent edits discovered **222** Python test modules (1 packaged EXE test excluded); ran **221**, **190 passed/31 failed**, reporting 2065 tests with 21 failures and 124 errors, 4 skipped and 2 expected failures; **SOURCE QA BLOCKED**, exit 1. This snapshot includes known legacy accounting and some concurrently edited tests, and MUST NOT be described as an independent stable baseline or a green full suite. A stable rerun/differential root-cause analysis remains necessary; do not re-enable retired financial endpoints merely to make outdated tests green.

## Release blockers and next integration gates

1. Authorized Taraz service and peer identity / signed receipt, organization/ACL mapping, actual network transport and verified query-before-replay. File observations are not trusted receipt or financial approval.
2. New device-local first-send ID journal exists, but needs an authoritative host-side reservation for multi-PC concurrency; a genuinely distinct manual resubmission, host identity changes, and cross-version coexistence of old/new Taraz still need acceptance tests.
3. E1: real online BYOK backend with protected Windows credential storage, explicit cloud consent+usage accounting+admin limits, and isolated model quality/availability tests; no cloud calls until consent/spend boundaries are implemented.
4. E3/E4/E5/E6 actual server-side workflows, finance review, official party matching/catalog and result auditing.
5. E7: genuine process power-loss/recovery tests, 2-PC Windows LAN/WebView2 GUI, full AC/G matrix, production backup-readback-rollback and separate deployment permission.

An isolated-worktree test pass must not be represented as LocalForge push, installed MadarHost state, official Taraz ledger integration or completion of E0–E7.

## Subsequent continuation: new host pilots and durable stores (source-only)

This section records observed evidence **after** the earlier 223-test focused
baseline. The original HEAD remains `32bd8ffe5ebbb0f4cd5c011c59323ed32f8647ac`;
the working tree is still dirty with other concurrent work. None of these
changes were merged/pushed/installed or tested against real user profiles.

| Phase | Additional source in Madar isolated worktree | Validation and remaining blocker |
|---|---|---|
| E1 | New `radar_crm_store.py`, `radar_host_adapter.py`, `tests/test_radar_crm_store.py`, `tests/test_radar_host_adapter.py` and `tests/test_radar_lan_http_pilot.py`. Source `lan.py` now has explicit TLS-only opt-in `mount_radar_crm_pilot()` and POST `/api/radar/v1/command`; disabled by default | 48 combined CRM host/store/E4 tests passed per worker report; **5/5** real synthetic HTTPS loopback route tests independently passed. User-reported CRM timestamps, no operational account/user GUI consent and no installed-host acceptance |
| E2 Madar host | New `mtr_host_request_store.py`, `mtr_lan_finance_adapter.py` and tests; `lan.py` opt-in TLS-only `/api/mtr/v2/prepare`, `/manual-send`, `/status` with original authenticated LAN bearer, current saved task and server-derived org/project/revision. Records only an **UNSENT** manual intent. | Store worker independently reports 34/34 new tests. Combined `tests.test_mtr_lan_finance_adapter tests.test_mtr_host_request_store tests.test_integration_api_v1`: **53/53 OK**. New pinned HTTPS pilot **8 tests** included. No actual transport, peer identity provisioning, authenticated Taraz receipt or official ledger idempotency |
| E2 Taraz isolated peer | In detached Taraz source new `taraz_mtr_peer_registry.py` and tests: bounded canonical v2 signed envelope verification, directional HMAC, durable metadata request/query registry, nonreceipt stays `unknown`. In Madar `tests/test_mtr_e2_signed_peer_registry_cross_app.py` cross-imports the actual two modules | **39/39** Taraz peer+legacy integration tests passed, and **3/3** Madar↔Taraz source-to-source synthetic signing/intake/query/verify passed with explicit `MTR_TARAZ_SOURCE`. A `verified_transport_peer` host assertion is NOT real TLS/identity; no socket was opened for interop, no finance receipt or ledger event created |
| E3 | New `mtr_deficiency_store.py`, existing `mtr_deficiency_workflow.py`, tests and docs | Worker reports **65/65** combined new + pure tests; durable metadata-only assignment/correction/manual resubmission intent with CAS/audit. Official Taraz deficiency receipt authentication absent |
| E4 | Existing `radar_party_match_preview.py` remains pure; new E4 human-review persistence is a separate pending worker activity | No official Taraz party read-only API, peer-attested candidate list or production link/update permitted |
| E5 | New `mtr_amendment_store.py`, tests/doc, independent amend state, two separate human acknowledgments, revision CAS, backed-up SQLite and immutable audit | Worker reports **29 new + 29 preview + 27 contract = 85/85 passed**; unsent manual intent only, no authoritative rejection source or live host integration |
| E6 | New `mtr_internal_notification_store.py`, `mtr_lan_notification_adapter.py`, tests/doc. `lan.py` adds default-off pinned HTTPS POST `/api/mtr-notices/v1/command` for host event-key publish/list/mark-read only | Worker reports **56/56** combined E6 store/adapter/policy tests; prime independently observed **4/4** real local synthetic TLS HTTP tests pass. Installed user registry does not yet manage opt-in `internalNotificationsEnabled` nor independently authenticated event journal. No external delivery or official financial status claim |
| E7 | Existing AC-01..AC-32 and G-01..G-08 mapping stays OPEN | No packaged EXE/two-PC/power-loss acceptance, protected production credential provisioning, real backup/rollback or release authorization |

### Regression qualification

- A broader **62-case** synthetic TLS/integration run reported **3 failing
  assertions** only in `tests.test_integration_http_security` where the
  test expected HTTP 403 but explicitly retired `/api/finance`,
  `/api/finance-status`, `/api/finance-overview` returned 404. **Do not restore
  forbidden finance endpoints to turn this test green.** The other tests in
  this run passed. These failures have not yet been reconciled with the
  approved deprecation contract.
- The older full-suite run already reported 31 failing Python modules; it is
  still **SOURCE QA BLOCKED**. New focused passes do not override that verdict.
- All new network tests use loopback TLS with the repository's **test-only**
  certificate and `TemporaryDirectory` state, never the installed hosts.
- `docs/modernization/MTR_E2_LAN_HOST_PILOT_20261109.md`,
  `docs/modernization/MTR_E1_E6_HTTPS_MOUNTS_PILOT_20261109.md` and detached
  Taraz `docs/MTR_E2_TARAZ_PEER_REGISTRY_PILOT_20261109.md` state trust and
  operational limitations in detail.
