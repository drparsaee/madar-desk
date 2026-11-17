# MTR connection-first roadmap, 2026-11-10

## Owner reprioritization

- **Today, P0:** connect Madar to Taraz. Keep both applications separate; Taraz is the only source of official financial truth. Prioritize a real, operator-visible handoff and its acceptance evidence over expanding Radar.
- **Next, P1:** authenticated official finance/catalog authority, task-to-request-to-review-to-status-to-invoice workflow, anti-duplicate behavior, security, recovery, and installed two-device checks. No automatic financial posting or unsafe resend.
- **Next, P2:** Taraz novice assistant: contextual Persian onboarding, natural-language help to create a *draft*, show missing fields, explain accounting terms and validation errors, offer walkthroughs and require permission plus explicit user confirmation before any consequential action. AI may never invent receipts, bypass roles, silently alter ledger or block manual work.
- **Later, P3:** Radar CRM architecture, customer intelligence and network/marketplace, deferred until the core Madar–Taraz vertical slice is proven usable. Its novice AI assistant follows the same optional, explainable and non-autonomous rules.

## Dependency graph without fabricated dates

`Madar saved card + explicit manual consent -> bounded handoff -> Taraz authenticated manual inbox -> reliable review/status -> official Taraz finance authority -> full-cycle acceptance -> reliable install/restore -> Taraz guided AI -> Radar and its guided AI`

Some UI and tests may proceed in parallel, but **official write / receipt authority is a blocking dependency** for actual accounting workflow. No percentage based on selected Python tests is an operational completion score.

## Observed current boundary

- Madar `native_app.py` + `taraz_exchange.py`: manual task metadata proposals to the current Windows user's `LOCALAPPDATA/Madar-Taraz-Bridge`. `src/App.jsx` exposes task send and status with consent. No official posting.
- Taraz `taraz_desktop.py` + `taraz_integration.py`: manual listing/review/rejection from the **same Windows user/machine** bridge; settings and floating inbox UI exist in source; review is not approval/ledger posting.
- `mtr_e2_host_peer_pilot.py` and Taraz signed peer modules are bounded **synthetic** network pilots. Their existence does not establish an installed LAN endpoint or authenticated official Taraz receipt.
- `tests/test_mtr_madar_taraz_local_crosssource_20261110.py` exercises source-to-source local roundtrips in a `TemporaryDirectory` against the explicitly named detached Taraz checkout. It is **not** a test of the installed apps, a second PC, real accounts, or financial ledger.

## Gates before calling today's connection operational

1. Independently verify actual installed Madar and Taraz versions expose the matching handoff APIs/UI and the intended same-user environment, or deliver a separately authenticated LAN connector if apps are on different machines.
2. Use a clearly authorized nonfinancial test task; verify it arrives in Taraz and status returns to Madar, without modifying personal or official accounting data.
3. Verify genuine identity/permissions, rejection, offline/unknown status, tamper recovery and explicit manual-only behavior on installed apps.
4. Separately validate official Taraz finance contracts, official receipts, backup/readback/restore, two-machine network operation, security and release acceptance before allowing ledger operations.

## Status vocabulary

`SOURCE_PROVEN` requires direct source inspection; `SYNTHETIC_VERIFIED` requires exact completed tests; `INSTALLED_VERIFIED` requires real installed-app test; `OFFICIAL_FINANCE_VERIFIED` requires independently authenticated Taraz accounting evidence. No transition between these states can be inferred from a passing unit suite.
