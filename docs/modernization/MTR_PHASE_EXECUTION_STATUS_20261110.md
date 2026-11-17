# Madar / Taraz / Radar E0–E7 | scoped execution status | 2026-11-10

**Verdict: substantial isolated source implementation and regression evidence; NOT E0–E7 accepted and NOT approved for deployment.** No verified official Taraz ledger posting, official remote catalog authority, live installation or second physical Windows client is included.

## Worktrees and boundaries

- Madar: `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107`, inspected HEAD `32bd8ff`, dirty shared isolated worktree.
- Taraz: `D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109`, inspected detached HEAD `653089b`, dirty shared isolated worktree.
- No commit, push, deploy, installation, production service, real user/finance ledger, network/Windows Firewall/DHCP, printers or file shares changed. Test HTTPS connections were bounded synthetic loopback with disposable fixtures, not an office-LAN acceptance test.

## Final focused test evidence observed in this continuation

| Area | Command/scope | Direct result | Caution |
|---|---|---|---|
| Madar E0–E7 source | `py -3.12 -B -m unittest -q` over 31 selected named Python modules, with temporary `MTR_TARAZ_SOURCE` pointing at detached Taraz | **498/498 OK, exit 0, 128.962s** | Focused modules only, not full legacy suite or installed UX |
| Taraz local catalog | `tests.test_taraz_mtr_catalog_read` | **25/25 OK, exit 0** | Local synthetic authoritative projection only; not official remote parties |
| Taraz signed peer registry | `tests.test_taraz_mtr_peer_registry` after actor-role fix | **12/12 OK, exit 0** | Synthetic SQLite signing/queries only |
| E1 React | `node --test tests/ai_usage_admin_host_boundary.test.cjs tests/ai_usage_admin.test.cjs` | **39/39 PASS, exit 0** | Three tests characterize residual visual/consent trust limits |
| E1 host/store/HTTP | `tests.test_madar_ai_usage_host_adapter`, `tests.test_madar_ai_usage_store`, `tests.test_madar_ai_usage_lan_http_pilot` | **57/57 OK, exit 0** | Included within the broader 498 suite; do not add |
| E2/E4 detailed regression | Host-peer, outbox, dispatch, recovery policy, local catalog, synthetic link preview and matrix | **119/119 OK, exit 0** | Also overlaps the broader 498 suite |
| E7 traceability | `tests.test_mtr_acceptance_matrix` plus explicit row scan | **4/4 OK; 40 total rows, 40 OPEN** | Structure only, no acceptance closure |

Counts are different slices, several **overlap**; do not sum or derive a completion percentage.

## Phase-by-phase source disposition

| Phase | Observed/source implementation | Still required to accept |
|---|---|---|
| E0 | Separated Madar request/intents from official Taraz ledger; legacy standalone finance routes intentionally retired, pure workflow contracts tested | Reconcile all old suite tests with approved split; prove no harmful secondary regressions |
| E1 | CRM/policy/quota/CAS/one-time consent pilots; optional host HTTPS; unmounted React panel now requires host grant scope echo | Host-selected text preflight, genuine command/gesture provenance, real local model draft success, approved provider vault and installed UX; no cloud dispatch |
| E2 | Pinned synthetic two-hop HTTPS, HMAC, immutable outbox/one-shot gate; fixed cross-role peer query; shared host locks released before TLS; **same-actor relogin query-first** added through host-checked read-only store/gate API; Taraz local catalog projection | Official Taraz identity+catalog API, official receipt/ledger idempotency, signed metadata recovery journal, query capacity/TLS-handshake hardening, two-PC/backup/restore and physical fault injection |
| E3 | Durable deficiency store/host policy with independent verified-finance boundary and manual unsent resend intent | Independently authenticated real Taraz receipt, user-facing lifecycle and acceptance |
| E4 | Local Taraz scoped catalog, human candidate review, audit; pure wrong-link impact preview and **unsent** selective correction intent for chosen open records | Official party-link transactions, authoritative affected-document enumeration, transactional selective changes, real before/after audit and rollback |
| E5 | Independent amendment history, CAS/conflict warnings, human approvals, unsent manual intent | Actual official financial state sync, authorization, installed reconciliation/send workflow |
| E6 | Host-scoped durable **internal-only** notices and optional HTTPS pilot | Installed notification UX/readback, operational retention and security validation; no external channels enabled |
| E7 | 32 acceptance AC and eight go-live G rows retained; unit test checks traceability | **All 40 remain OPEN** pending end-to-end authoritative, physical and release evidence |

## Known gaps not to conceal

1. Historical full-suite failed-only snapshot from 2026-11-09: **31 modules evaluated, 25 failed, 123 errors and 12 assertions**. Triage grouped first roots as 24 retired standalone-accounting expectations and one obsolete native titlebar fixture since independently rerun **7/7 PASS** by worker-15. No later full-suite clean run is claimed. Secondary defects are still possible.
2. Taraz is the only official financial source of truth. Synthetic `lookupStatus=received`, registry metadata receipt, unsigned/pseudonymous hints, local candidate selection, or a successful one-shot slot are **not** Taraz posting approval or official finance receipt.
3. Exactly-once for the official ledger across separate Madar outbox, dispatch SQLite, HTTPS and Taraz finance is **not proven**. Current send logic is at-most-one attempt and query-first; automatic resend remains disabled even when status is unknown.
4. New read-only recovery permits same currently authorized original actor to query across a changed session or deleted card, but role changes, removed original project, signed durable journal and recovery after real power/network faults lack independent acceptance.
5. E1 UI rejects mismatched/missing grantScope, but a forged injected command wrapper can spoof a consistent response, and a client-shaped cloud preverified hint does not prove selected-text provenance. There is no cloud model dispatcher or paid call in this pilot.

**Follow-on gates:** independently provisioned Taraz test authority/official API and credential contract, production-safe host identity and audit, real two-device Windows TLS acceptance with backups/readback/rollback, security and UX signoff, and refactoring the legacy full-suite expectations without re-enabling retired finance.

Supporting local source notes: `MTR_E2_HOST_PEER_PILOT_20261110.md`, `MTR_E2_SECURITY_REVIEW_20261110.md`, `MTR_E2_RELOGIN_AUTHORIZED_RECOVERY_20261110.md`, `MTR_E1_AI_GRANT_SCOPE_CONTRACT_20261110.md`, `MTR_E4_LINK_IMPACT_PILOT_20261110.md`, `MTR_E7_ACCEPTANCE_GATES_20261109.md`.

## 2026-11-10 continued source implementation and regression addendum

The earlier E2 journal/TLS/identity gaps above have **new source-level pilot work**; the old lines describe the original baseline, not this later addendum:

- Taraz loopback TLS handshake moved out of the single accept loop into semaphore-bounded workers. `tests.test_taraz_mtr_peer_http` **17/17 PASS**; Taraz peer registry, HTTPS and catalog together **58/58 PASS**, exit 0. Registry capacity remains **10,000 immutable query IDs**: warning/read-only archive now exist, but archive does not free capacity. Independently authenticated epoch rollover remains **OPEN**.
- Madar client and synthetic loopback listener now bound TLS admission/sender concurrency. `MtrE2HostPeerPilot.query_first` supports a private in-process `evidence_sink` delivering actual original/query/receipt signed wires to `QueryObservationJournal`: signed HMAC and original current host ACL are reverified before append-only, hash-linked SQLite metadata commit. Failure to journal or current host revocation fails closed and never re-arms the dispatch gate. Integrated E2 host-peer+journal test modules **33/33 PASS**, exit 0. This is NOT an official Taraz receipt or proof of multi-database atomicity.
- Test-peer `not_received` no longer yields a retry-eligible decision; it is `hold_unverified_nonreceipt` because no authenticated official Taraz nonreceipt is proven. Related envelope/cross-app/workflow suite **46/46 PASS**, exit 0.
- E2 actor identity is now host-private immutable random `accountLineage` mapped to a domain-separated opaque `principal_actor_id` instead of recyclable usernames. New LAN accounts mint once, password updates preserve, delete/recreate same username gets a distinct actor. Older account records lacking lineage fail closed; a separate **explicit ADMIN-only**, verified create-only backup, no-HTTP migration pilot was implemented and tested. Legacy username-owned historical outbox rows are **never remapped**. Combined lineage/migration/recovery suite **58/58 PASS**, exit 0, including genuine synthetic `LanService.delete_user` and recreation. Private account dict provenance still depends on trusted host code: direct constructed `TrustedPrincipal` F1 remains conditional in-process risk; there is no proven external HTTP exploit.
- Current separate Node AI/interface suite **49/49 PASS**, exit 0; three tests are documented observed trust/consent limitations, not security clearance. Vite source build succeeded (chunk-size warning only); it is not an installer, real LAN host, or production deployment.
- Broad disposable-profile Python source suite ran **249 modules** (one installer EXE module excluded): **227 module PASS, 22 module FAIL**, 2,529 tests reported, **118 errors, nine failures**, two skipped, two expected failures. Of 22 failing modules, 21 first-failure roots still invoke intentionally retired in-Madar finance/accounting APIs; the remaining E2 synthetic recovery fixture was corrected and independently rerun with 30/30 recovery/lineage and 58/58 combined success. There has **NOT** been a second complete 249-module rerun since those corrections. Detailed audit JSON at `D:\CoS-Test\MTR_E0_E7_fullqa_20261110_afterfix.json` (isolated machine, not a deliverable link).
- No real profile, financial ledger, hosted Taraz service, operational LAN configuration, or installed Madar desktop changed; no commit, push, deploy or signing. Madar HEAD `32bd8ff`, Taraz detached HEAD `653089b`, both dirty shared worktrees. `git diff --check` exit 0 on tracked edits; untracked new file paths must still be reviewed/committed separately under an authorized release procedure.

**E7 remains OPEN (all 40 gates).** Official finance API/receipts, authority and idempotency; physical two-PC TLS testing; true backup/readback/rollback; incomplete cloud-consent provenance; independent security review; and safe release packaging/acceptance are still needed. Passing synthetic tests do not authorize production posting or publication.

## Follow-up verification after mandatory E2 principal provenance wiring (2026-11-10)

**This addendum supersedes older pre-wiring assertions only where specifically evidenced; it does not erase historical failures or certify installation.** The F1 host provenance issuer is now wired into the live-object *synthetic* outbox recovery and dispatch-gate recovery entrypoints, using separate one-use HMAC audiences. Journal read/write and signed `query_first` require current host authentication under account/project locks. Plain constructed `TrustedPrincipal` does not authorize recovery. The integrating agent reported **148/148 PASS** in synthetic E2/host/journal negative and positive tests (including forgery, stolen seal, replay and revocation). No external process/OS compromise resistance or production hosted principal attestation was proven.

Changes directly exercised in this continuation also include rejecting invalid private project grant shapes, deleted saved projects and unreadable host saved state *before finance-intent prepare*. The corresponding LAN finance-pilot tests failed before the guard and then passed **11/11**, exit 0. The synthetic peer client now distinguishes bounded pinned-peer JSON HTTP 409 denial from HTTP 503 uncertainty before enforcing success-envelope content type; fresh negative tests and entire peer pilot **13/13 PASS**, exit 0. Neither path enables automatic retry or generates an official financial receipt.

### Reconciled full and current-source suites

| Run | Verified result | Interpretation |
|---|---|---|
| Full Python source `tools/modernization_python_suite.py --workers 4 --timeout 150` | **257 modules executed; 235 pass / 22 fail; 2,627 tests reported; 129 errors, nine failed assertions; zero timeouts; exit 1** | Saved `D:\CoS-Test\MTR_E0_E7_fullqa_20261110_postprovenance.json`. Excludes only historical packaged-EXE test. This is a real failing snapshot and must remain visible. |
| Failure source mapping | **21/22 failing modules** match the reviewed SHA-256-pinned retired *in-Madar* accounting contract files; the remaining `test_mtr_e2_recovery_policy_pilot.py` had 12 fixture setup errors | Test fixture's in-memory host state lacked the now-required current project registry; fixed in its synthetic `FakeBridge` without weakening production checks. Independently rerun **12/12 PASS**, exit 0. The full snapshot is not rewritten or claimed to pass retroactively. |
| Separate current-architecture source QA `tools/mtr_release_suite_scope.py --run-current --approve-retired-sha256 b2d4ff6e9f7afcbf337d23bd65c5b674eaaf87a07c9a6e5ec0df296c753babb9 --workers 4 --timeout 150` | **236/236 modules PASS, 2,435 tests reported, zero errors/assertions/timeouts, eight skipped, exit 0** | Saved `D:\CoS-Test\MTR_E0_E7_current_scope_20261110_postprovenance.jsonl`; SHA-256 `871c8ad04232f05e1c185ee840a001470a2dc1da3fccad70362972ad7c6415d9`. Exact 21 reviewed legacy modules plus packaged EXE excluded; eight newly added test modules are explicitly listed in JSONL. A current-source pass is not an installed-app acceptance or full-suite pass. |

The current-scope source runner's reviewed retirement classifier itself had **11/11** tests; the package preflight and classifier combined **15/15**. Other separate scoped runs: **302/302** Madar E1–E6 Python, **105/105** additional E0/E1/E4/E6 Python, **39/39** AI UI Node and **58/58** Taraz synthetic peer/HTTPS/catalog. These figures overlap the larger suites and **must not be summed**. The Taraz 10,000-query immutable-registry epoch staging added **12/12** source tests and readback/archive evidence; activation remains deliberately BLOCKED since query-ID replay across archived epochs is not yet rejected by the live registry/protocol.

### Repeatable E7 package decision

`py -3.12 -B tools/mtr_release_readiness.py` returned **`NO_GO`, exit 2 (expected)**. Its **14/14** combined static/preflight tests passed, but actual builder safety gates fail: 221 modified/untracked paths at observed HEAD `32bd8ff`, absent full offline WebView2 prerequisite, and **40/40 acceptance AC/G rows OPEN**. `dist/` exists but has no current build provenance; Authenticode, WebView2 offline identity, installed packaging toolchain, two-PC installation, signed official Taraz finance authority, backup/readback/restore and rollback remain unverified. See `MTR_E7_PACKAGE_PREFLIGHT_20261110.md` and the machine-readable CLI output. No build, setup run, operational service/network modification, financial posting, signing, commit, push or deployment took place.

## Later 2026-11-10 source-locked QA and security-boundary evidence

**Prime-reported current-source QA snapshot (separate from the older 236-module run):** **241/241 selected Python modules PASS; zero failed modules and zero timeouts.** The pre-run and post-run SHA-256 source snapshot both equal `16d46796b0086ff40735d3a06a4499a410bb1ec4d7eef23c8c99c102ca624509` over **966 files / 12,167,149 bytes**. The matching hashes attest to the scoped source snapshot remaining unchanged during that run; they do not authenticate Taraz or establish release acceptance. These are results supplied by the integrating prime, **not a QA rerun performed while editing this ledger**.

**Coverage limitation requiring follow-up:** four modules in that 241-module tally executed **zero tests** because `MTR_TARAZ_SOURCE` was not set for cross-source imports: `test_mtr_e2_host_peer_pilot.py`, `test_mtr_e2_signed_peer_registry_cross_app.py`, `test_mtr_e2_two_source_https_pilot.py`, and `test_mtr_e4_local_catalog_pilot.py`. Their runner-level pass/zero-test status is **not** evidence that their behavioral tests passed. Prime will rerun them with the explicit isolated Taraz source; do not count these four as exercised acceptance coverage until such evidence exists.

Additional **source/synthetic-only** updates reported for this continuation:

- **E2 official receipt:** the in-process `verified_by_adapter=True`/constructible-principal authority flaw has been closed fail-closed pending an official Taraz verifier. Historical self-asserted `received`/`not_received` observations and old gate confirmations are quarantined in operational projections; stored audit/SQLite integrity is retained, and neither automatic resend nor ledger receipt is authorized. See `MTR_E2_RECEIPT_AUTHORITY_BOUNDARY_20261110.md`.
- **E2 restart recovery:** read-only ambiguous account-lineage migration restart inspector has **21 synthetic tests** reported; operator classification is inspection only, without automated restore, identity rewrite or real-account migration.
- **E5 official rejection:** `record_rejection` now denies unauthenticated purported Taraz rejections even when a caller constructs a `TrustedPrincipal` and sets `verified_by_adapter=True`. Historical stored `REJECTED` rows retain their raw SQLite/audit evidence but are projected as `REJECTION_UNVERIFIED`, with unverified related/audit labels and conservative draft review. See `MTR_E5_REJECTION_AUTHORITY_20261110.md`.
- **E6 internal notice UI:** App/Bridge opt-in inbox wiring has **11 Python + 17 Node synthetic/source tests** reported; this is not installed desktop notice UX or operational readback acceptance.
- **E7 upgrade helpers:** **13 isolated PowerShell helper integration tests** reported with disposable paths and fixtures; these do not attest to a production installer, actual client upgrade, rollback or signature.

These counts describe distinct and potentially overlapping source-level slices and **must not be summed**. The historical full Python QA failure remains on record; a selected current-source run does **not** turn that historical full execution green. **All 32 AC and eight G gates (40/40) remain OPEN. E7 decision: NO_GO.** Official Taraz finance and catalog authority, real two-PC TLS/client trials, installed-app checks, independent security/recovery acceptance, backup/readback/restore and release identity remain unverified. No real Taraz, physical LAN, installation, production financial data, commit, push or release is certified by this addendum.

## Superseding v3 cross-source, source-locked QA addendum (2026-11-10)

**Verified v3 report:** `D:\CoS-Test\MTR_E0_E7_current_scope_20261110_crosssource_sourceguard_v3.jsonl` records **exit 0; 240/240 selected current-SOURCE Python modules PASS; zero module failures/timeouts; 2,551 unittest cases, including one individually skipped test**. Every selected module reported at least one actual case; **zero modules had zero, all-skipped or unreported tests**. This replaces the preceding v2/241-module result as the latest scoped source-QA evidence; the earlier snapshot remains above as historical evidence, not as the current outcome.

Both bounded source snapshots matched **before and after the v3 execution**:

| Source snapshot | Files | Bytes | SHA-256 (same pre/post run) |
|---|---:|---:|---|
| Madar current source | 966 | 12,176,327 | `d40a96317a791bbe8f03a413a26b350359a7fb8b1d6828a3d0eaa0eaf6231941` |
| Detached Taraz source | 115 | Not recorded in this addendum | `95d48e64bf7c05ed7aea3b3cfe60bab1ffa684d0e6a9fab6e9d6f345840d33b1` |

The hashes establish **run-time source invariance for the captured v3 file sets only**. Subsequent documentation changes, including this addendum, change the working source tree and are **not covered by those earlier SHA-256 values**. They are not current post-edit source fingerprints or signatures of official Taraz authority.

The earlier v2 gap involving zero-test cross-source modules has been addressed **for this selected-source run** with the explicit pinned detached Taraz `--taraz-source` argument:

| Exercised cross-source module | Tests in v3 |
|---|---:|
| `test_mtr_e2_cross_app.py` | 2 |
| `test_mtr_e2_host_peer_pilot.py` | 18 |
| `test_mtr_e2_signed_peer_registry_cross_app.py` | 3 |
| `test_mtr_e2_two_source_https_pilot.py` | 5 |
| `test_mtr_e4_local_catalog_pilot.py` | 7 |
| **Total interop cases already included in 2,551** | **35** |

**Runner correction and explicit scope:** v2 was **BLOCKED** by one release-only installer module with **one skipped test out of one**. v3 refuses any zero-test, all-skipped or unreported module and requires a pinned Taraz `--taraz-source`. The current-source selector **explicitly excludes two RELEASE-ONLY modules**: `test_packaged_madar_host_exe.py` and `test_release_portable_install.py`; the latter exclusion is SHA-256 pinned to `000f3c35292401ca7029c6ab232e02e00d7bf43efd3bf9c1ec26debea8274f56`. Neither module's installation/release behavior has been proven by this scoped QA. This is **not** a passing full historical Python suite or E7 installer gate.

Additional scoped checks after the runner changes: **41/41 Python** tests covering source guard, readiness and acceptance matrix; **56/56 E1/E6 Node** tests. These counts overlap their source/feature contexts and are not additive to the 2,551 v3 unittest cases.

The read-only E7 preflight verdict remains **`NO_GO` (expected exit 2)** and **all 40/40 AC/G acceptance gates remain OPEN**. Historical full-suite failures remain recorded unchanged. This run demonstrates synthetic/local source tests and guarded cross-source interoperability only. It does **not** authenticate official Taraz finance receipts/ledger writes, certify actual two-PC LAN, verify installed packages or signatures, or demonstrate backup, restore and operational rollback. No deployment authorization follows from this report.
