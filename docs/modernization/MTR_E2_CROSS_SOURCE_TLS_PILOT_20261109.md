# E2 two-source signed HTTPS metadata pilot, loopback only

**Status: synthetic source interoperability demonstrated, NOT operational E2,
NOT official Taraz financial integration, NOT released.**

## Implemented separately, without shared finance authority

- Madar `mtr_peer_https_pilot.py`: `PeerLoopbackHttpsPilot` pins a configured
  SHA-256 certificate digest **before sending any Authorization bearer**;
  only `127.0.0.1`, explicit test-only constructor flag and in-memory injected
  independent sender/peer HMAC keys plus a separate transport bearer. Uses
  strict time-bound canonical v2 `mtr_peer_envelope.py` and explicit manual
  dispatch assertion; no key persistence, service discovery, automatic retries,
  official financial writes or UI route.
- Detached Taraz `taraz_mtr_peer_registry.py`: durable SQLite metadata-only
  request/query registry, binding and conflict protection, separate directional
  signed lookup receipt `received` or `unknown`. No fake `not_received`.
- Detached Taraz `taraz_mtr_peer_http.py`: explicit opt-in HTTPS server bound
  to `127.0.0.1`, accepts only two POST routes, authenticates independent host
  transport bearer **before reading body**, then verifies request HMAC/tenant,
  actor role, TTL, key ID, sender and purpose. No actual Taraz ledger API.

## Direct synthetic evidence

In Madar isolated worktree, set `MTR_TARAZ_SOURCE` to the detached Taraz
source `D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109` and run:

```powershell
py -3.12 -B -m unittest -q tests.test_mtr_e2_two_source_https_pilot
py -3.12 -B -m unittest -q tests.test_mtr_peer_https_pilot
```

**Observed in this source continuation:** `test_mtr_peer_https_pilot` **8/8**
successful, and `test_mtr_e2_two_source_https_pilot` **5/5** successful,
including local real TLS packet exchange between both repository modules,
certificate pin / bearer denial, same-ID different-payload refusal and a
controlled fault in which the Taraz SQLite commit occurred over HTTPS but
Madar's in-process caller lost its acknowledgement. The latter did **not**
transmit again: the next action was a distinct signed query showing
`received`. This is a fault **injection after the successful response**, not
an electrical power-loss or physical LAN interruption test.

The fifth two-source test exercised **three separate durable SQLite stores**:
Madar `HostRequestStore` manual prepare/authorization, Madar
`OneShotDispatchGate` first-attempt reservation, and detached Taraz
`TarazPeerRegistry` metadata arrival over real TLS. It verified a single
reservation, a real signed lookup, a persisted `unknown_after_attempt`
state, and denial of a second dispatch even after reopening the host DBs.
The outbox and dispatch gate are **not cross-database atomic**; the test
therefore does not establish exactly-once network/ledger delivery.

## Later host-authenticated two-hop interoperability

`mtr_e2_host_peer_pilot.py` is a **separate synthetic-only Python integration**
of authenticated in-process `LanService.account_for`, the existing optional
TLS MadarHost request prepare/manual-intent API, the durable first-attempt
gate, a pinned local HTTPS client and the detached Taraz test registry.
`tests/test_mtr_e2_host_peer_pilot.py` includes a concrete two-hop scenario:
an authenticated test client posts prepare and manual-send **intent** to
MadarHost over HTTPS; MadarHost-side Python then reserves one dispatch slot
and transmits only bounded signed metadata to detached Taraz over another
HTTPS connection; the test reads each host and peer's differing statuses.

**Observed final targeted regression:** `py -3.12 -B -m unittest -q` on
`tests.test_mtr_e2_host_peer_pilot`, `tests.test_mtr_e2_two_source_https_pilot`,
`tests.test_mtr_peer_https_pilot`, `tests.test_mtr_e2_dispatch_gate`,
`tests.test_mtr_host_request_store`, `tests.test_mtr_lan_finance_adapter`,
`tests.test_madar_ai_usage_lan_http_pilot`,
`tests.test_madar_ai_usage_host_adapter`, `tests.test_madar_ai_usage_store`,
`tests.test_mtr_acceptance_matrix`: **146 tests, OK, exit 0** (with
`MTR_TARAZ_SOURCE` pointing to the explicitly detached test source).
Earlier directly scoped host-peer test: **11 tests, OK**. The one-shot
simulation also exercises an acknowledgement lost *after* the test Taraz
registry committed the request and verifies that a reopened gate denies
another initial dispatch; only a new signed query recovers arrival.

**Important distinction:** the HTTP `/api/mtr/v2/manual-send` operation
records an **UNSENT intent**; the separately invoked test coordinator is
not mounted as an HTTP send endpoint. The received peer registry state is
not an official finance receipt or posted ledger state. These tests do not
close G-03 or any E7 acceptance gate.

The test-only PEM pair is taken from detached Taraz's publicly known
`tests/test_taraz_mtr_peer_http.py`. It is **not** a production key or a
valid secret. The registry and listener exist only for the test's
`TemporaryDirectory`; neither installed app is started or configured.

## Severe remaining risks and release gates

1. This client deliberately accepts only a *caller assertion* that durable
   human authorization exists. A separate **atomic host-side dispatch gate**
   must prove the actual saved card, actor/session, authorization, receipt
   history and one-shot attempt before calling it. A stale boolean must never
   count as evidence. Without that gate, repeat calls can send the same
   signed metadata twice, even though the test registry deduplicates.
2. One loopback test bearer and public test certificate is NOT real identity
   provisioning, mutual service authentication, key rotation or secure
   organizational trust. Real LAN listeners and credential vaults remain absent.
3. The response `received` means **metadata arrival only** in a detached test
   registry; neither an accepted financial review nor official approval,
   posting, invoice, ledger idempotency, party identity or document reference.
4. Host SQLite, Taraz registry SQLite and any future ledger are NOT one
   atomic transaction. Query-before-retry cannot by itself guarantee true
   exactly-once official financial posting. The authoritative Taraz finance
   service must enforce the actual idempotent financial transaction.
5. Physical host service and clients, stale session recovery, installed EXEs,
   protected key storage and rotation, real isolated backup/restore/readback,
   rollback and AC/G installed acceptance are not done. No merge, push or
   deployment authorization was given by this pilot.

Every G-01..08 and AC-01..32 gate remains OPEN pending the exact installed
and official-system evidence.

## Later two-TLS-hop, actual MadarHost session roundtrip

An independent, explicit **test-only** coordinator was added as
`mtr_e2_host_peer_pilot.py`, with tests in
`tests/test_mtr_e2_host_peer_pilot.py`. It ties together an actual synthetic
MadarHost `account_for` authenticated session, current saved project/card,
`MtrLanFinanceAdapter` persisted manual authorization,
`HostRequestStore.request_snapshot`, `OneShotDispatchGate` durable first-attempt
reservation, and `PeerLoopbackHttpsPilot` to the detached Taraz test listener.

The single targeted case
`test_real_two_https_hops_manual_client_host_then_test_taraz` was observed
**PASS (1/1), exit 0**. The test **actually sends packets over TWO TLS
connections** on `127.0.0.1`: synthetic client -> explicitly mounted
MadarHost finance-metadata endpoint, and MadarHost coordinator -> isolated
Taraz metadata-only peer. The signed receipt lookup and second-attempt denial
also passed in this case. It does not exercise an installed Windows client,
real LAN device, production authorization, or official financial receipt.

In a related synthetic test, a saved card title changed after the first
dispatch. The old immutable request remained available for signed
**read-only query-first recovery**, while any new submission was rejected
on stale current-card revision. **1/1 targeted test passed.**

The coordinator is NOT registered as an HTTP route for the user or browser;
no production peer configuration exists. Its Python `synthetic_only=True`
is an API-level safety assertion, not evidence that a live service is safe.
It currently holds host locks while contacting a localhost test peer and
relies on two independent host SQLite databases; this is unsuitable for
production availability/atomicity until redesigned and independently tested.
