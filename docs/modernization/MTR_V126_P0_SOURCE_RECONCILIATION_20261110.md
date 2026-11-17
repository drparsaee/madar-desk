# Madar ↔ Taraz P0: isolated v1.0.26 source reconciliation

**Date:** 2026-11-10
**Result:** Concrete **source-only / QA-only partial port**. **NO_GO** for upgrade,
installation, publication, signed release, authenticated Taraz financial posting,
or production connection acceptance.

## Origin, branch and scope

- **New, detached Git worktree:** `D:\CoS-Test\000- Madar\madar-mtr-v126-integration-20261110`.
- Exact locally inspected base: `785a419af482f998154464a41df7770c9c9c87d4`
  (`feat/madar-v126-p1p2-github-20261107`); worktree was initially clean.
  No cherry-picks or merges were attempted, so no branch conflict occurred.
- Source material was read from the separate concurrently dirty P2/MTR worktree
  `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107`.
  That shared worktree and installed programs/profiles were **not changed**.
- `package.json`, both package-lock root version entries,
  `madar_update.CURRENT_VERSION` and `scripts/build_p1p2_v126_qa.py`
  remain **1.0.26** with the original P1/P2 builder route. No version was
  fabricated. The prior observed installed baseline is also 1.0.26, so this
  worktree is **not an eligible strictly newer upgrade**. The next release
  would need a separately reviewed, correctly sourced version **greater than**
  the independently re-read installed version, then new complete packaging and
  rollback evidence.

## Exact source and test changes

| Type | Path(s) | Source, reason and boundary |
|---|---|---|
| Added unchanged current-source modules | `mtr_e2_send_journal.py`, `taraz_review_status.py`, `mtr_taraz_installed_peer.py`, `mtr_taraz_peer_identity.py` | Durable manually reserved same-ID metadata requests; scoped local observations; SHA-pinned same-user Taraz manual-open probe; pure peer-attestation **schema/verifier only**. The verifier is **not wired to an authorized live Taraz issuer**. |
| Reconciled existing MTR module | `taraz_exchange.py` | Ported only the dedicated metadata exchange implementation: explicit request ID, bounded readback, exclusive hard-link publication, cooperative request locks, conflicting/uncertain retry hard-stop, no ledger write. This intentionally changes the old one-shot `Bridge.tarazIntegrationQueue(taskId)` contract. |
| Surgically edited v1.0.26 native entrypoint | `native_app.py` | Kept all non-MTR `Bridge` methods identical to the v1.0.26 Git AST. Added manual `OpenLocal`, durable `Prepare`, guarded same-ID `Queue`, scoped consent-gated `History`, exact JS bridge exports; retained old status response plus `localPeer`. For client actor scoping **tightened** HTTPS fingerprint requirements and removed endpoint-only fallback. |
| Surgically edited v1.0.26 frontend | `src/App.jsx` | Retained v1.0.26 Web/PWA, Gantt, notifications and automatic verified-update caching. Added desktop-only mock failures, explicit Prepare → Queue, scoped history button and local-uncertainty labels, same-ID retry, manual peer opener. UI never calls the finance ledger. |
| Updated existing synthetic tests | `tests/test_taraz_exchange.py`, `tests/general_ui_preferences.test.cjs` | Assert new deliberate failure of unprepared native one-shot queue and exact manual Prepare → Queue consent order, preserving baseline finance-separation and P2 checks. |
| Added focused synthetic/source tests | `tests/test_mtr_e2_send_journal.py`, `tests/test_taraz_review_status.py`, `tests/test_taraz_manual_retry.py`, `tests/test_taraz_manual_retry_faults.py`, `tests/test_mtr_taraz_installed_peer_20261110.py`, `tests/test_mtr_taraz_peer_identity_20261110.py`, `tests/test_mtr_taraz_connection_contract_20261110.py`, `tests/test_mtr_v126_port_parity_20261110.py` | Explicit same-ID replay, corruption, cross-process filesystem contention, source-bound local receipt uncertainty, role/project/offline denial, exact v1.0.26 source preservation and strict client HTTPS fingerprint guard. |
| Test scope deliberately excluded | `tests/test_taraz_review_status.py::test_ai_native_opt_in_acl_and_preview_only` | **One explicit skip**, because the AI drafting feature and its `aiDraftSuggest` native method are outside this P0 metadata-only port. It was not counted as a pass. |

### Explicitly excluded implementation

No source was copied from `mtr_finance_authenticated_origin.py`,
`mtr_lan_finance_adapter.py`, `mtr_peer_envelope.py`, host-provenance/actor-lineage
migration, E2 dispatch/recovery database/HTTPS components, E3–E6 adapter or
notice modules, AI drafting, or the Taraz application. No Taraz account,
authenticated host, cryptographic challenge/response, trusted provisioning,
official receipt, third-party finance API, ledger posting, or signed
acknowledgement has been integrated. Copying those pieces without their
current-LanService/role/peer trust roots would produce a false security claim.

The integrating prime separately reports inspecting the latest Taraz QA binary:
its bundled native metadata-review bridge is present, while
`taraz_mtr_finance_binding_authority`, `external_actor_link`,
`attestation_issuer` and the peer HTTP/registry modules are absent from its
PyInstaller PYZ inventory. **This is a finding reported by prime**, not a
separate binary inspection performed in this worktree. It means a matching
financial authority/issuer is not mounted at runtime even if all of this
isolated Madar metadata-port unit testing passes. The Taraz QA build remains
nonrelease and cannot serve as evidence of operational finance pairing.

**Read-only host/E2 module dependency inventory:**

| Unported current-source module | Direct dependency or integration reason |
|---|---|
| `mtr_host_request_store.py` | Own private SQLite host request store and `TrustedPrincipal` contracts; requires real account/project policy wiring |
| `mtr_e2_dispatch_gate.py` | Depends on `mtr_host_request_store`; one-shot dispatch state needs host-authenticated issuance and recovery |
| `mtr_account_lineage.py`, `mtr_host_principal_provenance.py` | Host-private lineage and provenance seal; issuer depends on the actual LAN account registry and trusted session |
| `mtr_e2_query_observation_journal.py`, `mtr_e2_host_peer_pilot.py` | Cross-source signed observation journal, provenance-bound dispatch, and host/peer integration; pilot depends on store, gate and host authority |
| `mtr_peer_envelope.py`, `mtr_finance_authenticated_origin.py` | Authenticated HMAC wire formats and original signer; finance signer explicitly requires live `LanService`, `principal_actor_id` and current saved task/expense |
| `mtr_lan_finance_adapter.py` | Host financing access adapter; depends on private request store and account lineage, neither integrated with this v1.0.26 LAN host |

The inventory was derived from source import/class declarations only; it
does **not** prove these separate pilot modules interoperable or safe to copy.
No speculative host implementation or static identity credentials were added.

The P1/P2 source files `src/startup_update.mjs`, `src/gantt_model.js`,
`src/gantt_view.jsx`, `src/teamplus.jsx`, `server/gantt_shift_guard.cjs`,
`server/index.cjs`, `lan.py`, both v1.0.26 builder/QA upgrade scripts and
their version metadata were **not edited**. The source-lineage test compares
their line-ending-normalized byte hashes to the exact committed v1.0.26 blobs.
All other Python `Bridge` method ASTs remain equal to that base.

## Actual verification in this detached worktree

1. **74 Python unittest cases, exit 0, 73 executed/pass and one explicit
   unrelated AI skip.** Command:
   `python -B -m unittest tests.test_mtr_v126_port_parity_20261110 tests.test_mtr_taraz_connection_contract_20261110 tests.test_taraz_exchange tests.test_mtr_e2_send_journal tests.test_taraz_review_status tests.test_taraz_manual_retry tests.test_taraz_manual_retry_faults tests.test_mtr_taraz_installed_peer_20261110 tests.test_mtr_taraz_peer_identity_20261110 -q`.
   Includes six direct detached-source Taraz metadata review/deny/replay tests
   (operating only on `TemporaryDirectory` and in-memory fake bridge states),
   four exact-baseline source-preservation checks, and a new unpinned/HTTP
   client actor-scope negative test. No official Taraz ledger/auth claims.
2. **21/21 Node tests passed**, exit 0, for
   `tests/startup_update.test.cjs`, `tests/gantt_model.test.cjs` and
   `tests/general_ui_preferences.test.cjs`. Because this new detached tree
   intentionally has no installed `node_modules`, the test process loaded
   existing `esbuild` **read-only** through `NODE_PATH` pointing at the
   separately present v1.0.26 worktree's packages. No npm installation.
3. **React JSX syntax parsing passed** using read-only
   `esbuild.transformSync` for the entire edited `src/App.jsx`. This checks
   syntax, **not** runtime rendering or browser interaction.
4. **`git diff --check` passed**; `HEAD` remains
   `785a419af482f998154464a41df7770c9c9c87d4`, detached.

### Important failing or unrun tests

- An attempted combined P2 Node run failed 3 modules initially because the new
  worktree has **no local `node_modules/esbuild`**. Supplying read-only
  `NODE_PATH` subsequently allowed the entire targeted 21-test Gantt,
  updater and consent scope to pass.
- The P2 notification browser test still could not resolve React, React DOM
  and Lucide during an isolated `esbuild.buildSync` in this dependency-free
  detached worktree. Its two static tests passed; browser interaction was
  **not verified**. No new dependency installation or Chrome process was
  used to work around this limitation.
- `tests.test_js_bridge_surface` failed its **one historical assertion**:
  it expects `financeRead`, `financeStatus` and `financeCommand` to be
  exported in the browser bridge, although the exact **original v1.0.26**
  `native_app.JS_BRIDGE` does not export those retired finance methods.
  The test itself and those legacy backend contracts were **not changed**.
  This old static assertion is not a proof of a new MTR regression or of full
  baseline QA success. It remains a documented incomplete legacy-suite gate.
- No full Python/Node suite, real installed GUI, real two-PC TLS host,
  power-loss experiment, finance side effect, or final installer test was run.
  Historical E7 release/acceptance gates remain open.

## Remaining P0 security, product and release blockers

1. Local `pending`, `reviewed` and `*.review.json` files are **unauthenticated
   observations**. A visible state label or `peerVerified:false` must never be
   promoted to official receipt, source-confirmed accounting, or positive
   delivery. `mtr_taraz_peer_identity.py` is a pure contract and needs a
   *separately authenticated* Taraz issuer, provisioned trust and durable
   one-time challenge validation before real peer status may change to true.
2. Current actor identity in the port still relies on the desktop's
   `remote_user` projection; HTTPS/fingerprint checking narrows the risk but
   **does not prove current host authorization**, account lineage, role,
   persisted tasks or session revocation. The host private account authority
   and integration challenge remain unimplemented here.
3. A prepared request and its local file publication are not an atomic
   cross-process financial protocol. Unknown outcomes stop automatic resend;
   official Taraz idempotency, crash recovery, re-login, two-PC TLS, authorized
   saved-project access and post-restart receipts need independent tests.
4. The updated UI is **not an installed v1.0.26 program**. Local source tests
   cannot certify a new package or preserve every installed UX behavior.
   Existing embedded build/update manifest, no-downgrade and release evidence
   are separate mandatory gates.
5. **Same-version 1.0.26 cannot upgrade installed 1.0.26.** Reconcile the
   port with the exact latest approved v1.0.26/P1/P2 source; independently
   verify actual installed baseline. After full review create a *new*
   greater-than-installed candidate and aligned package/lock/updater/builder
   + independently pinned source/QA metadata, complete tests, signing
   acceptance, backup/restore and explicit owner installation approval.

**Disposition:** source-only P0 metadata port and scoped tests completed,
uncommitted in this newly detached worktree. **NO_GO for installation,
financial posting, publication or production integration**. No live app,
account, service, installed EXE, actual user profile or accounting ledger
was opened, modified, or used as test input.
