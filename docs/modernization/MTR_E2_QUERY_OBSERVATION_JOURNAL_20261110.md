# E2 host signed-query observation journal (isolated implementation, 2026-11-10)

## Exact integration contract

The **new** `mtr_e2_query_observation_journal.py` exports:

```python
QueryObservationJournal(
    path: Path, *, outbox: HostRequestStore,
    gate: OneShotDispatchGate, max_records: int = 10_000,
)

journal.record(
    *, principal: TrustedPrincipal, request_id: str,
    expected_base_revision: int,
    original_wire: bytes, query_wire: bytes, peer_receipt_wire: bytes,
    sender_secret: bytes, peer_secret: bytes, now: datetime,
    sender_id: str, sender_key_id: str,
    peer_id: str, peer_key_id: str,
) -> dict

journal.observations(
    *, principal: TrustedPrincipal, request_id: str,
    expected_base_revision: int, limit: int = 100,
) -> tuple[dict, ...]
```

The trusted Madar host obtains **current** `TrustedPrincipal` from a live
`LanService` session, under its account/card authorization locks. Do not
deserialize that principal, `now`, the expected peer identities or HMAC keys
from the browser. Obtain the original signed request, signed query and signed
peer response **bytes from the trusted peer protocol** after the HTTPS reply;
record before returning the observation to the UI. A verification result with
only a digest or `verified=True` is insufficient. The current
`PeerLoopbackHttpsPilot.query_verified` returns just hashes and status; the
prime must wire its trusted raw-wire result without exposing keys or envelopes
to untrusted clients. No existing transport file was modified in this worker.

The journal independently calls `HostRequestStore.recovery_snapshot` and
`OneShotDispatchGate.recovery_status` for the original request, using the
current authorized actor/org/project grant and immutable original
request ID/base revision/payload digest. It then verifies the Madar original,
Madar lookup query and Taraz reply HMACs, including signer IDs, roles, key IDs,
tenant, original/query IDs, payload hashes, time and purpose. Host-account
revocation should be checked under a live host lock at the call boundary.

## Persistence and safety properties

- One SQLite file, schema v1, created only with an explicit pre-existing
  directory. It never opens the normal app database by default.
- Append-only query evidence with `UPDATE`/`DELETE` rejection triggers,
  unique query IDs across the whole DB, strict schema check, SQLite
  integrity check, contiguous sequence, SQLite AUTOINCREMENT high-water
  cross-check and SHA-256-linked row audit.
- Identical authenticated query ID and signed **payloads** are idempotent;
  equivalent newly signed envelopes do not replace the original signed
  envelope digest. Same ID with altered original request, sender or peer signer
  and key identity, query payload or peer payload/status fails with a conflict.
- Up to 10,000 lifetime query observations. On exhaustion, new queries fail
  closed. Nothing rotates, purges, reuses a query ID or grants a dispatch slot.
  Archival/rotation needs a separate owner-reviewed append-only strategy.
- Peer `received` is a signed **metadata claim**. `not_received` and
  `unknown` both produce local `lookupStatus="unknown"`. Every response
  explicitly reports `officialTarazReceipt=False`,
  `financialEventCreated=False`, `canAutoRetry=False`.
- Only hashes, request/query IDs, authorized actor/org/project/role/session
  metadata, observed state and host time are stored; no raw signed wires,
  HMAC secrets, financial amounts, transaction records or receipt IDs.
- The journal does **not** mutate the HostRequestStore receipt state or
  OneShotDispatchGate, and cannot send or resend a packet.

This is **DML-resistant**, not an external legal immutable audit. Someone with
filesystem/SQLite DDL authority can delete or rebuild the entire DB and forge
its unkeyed hash chain. A separate trusted hash anchor, audited backups,
permissions and restore strategy are needed for high-assurance retention.
There is no atomic cross-DB transaction between the outbox, gate, journal and
TLS. Signed metadata is never authoritative Taraz finance evidence.

## Verification

Run only synthetic temporary SQLite tests:

```powershell
py -3.12 -B -m unittest -v tests.test_mtr_e2_query_observation_journal
```

The test covers restart, concurrent writes, replay and contradictory IDs,
revoked actor/grant/session, wrong signatures/tenant, dispatch reservation,
capacity, DML immutability, hash/schema tampering and bounded reads. All test
database files live in `TemporaryDirectory`; no live profile, network,
real finance, commit, push or deployment is part of this slice.

**Observed isolated validation:** the dedicated command completed **16/16 OK,
exit 0**. A bounded wider regression that added existing envelope,
dispatch-gate and outbox tests completed **85/85 OK, exit 0**:

```powershell
py -3.12 -B -m unittest -q tests.test_mtr_e2_query_observation_journal tests.test_mtr_peer_envelope tests.test_mtr_e2_dispatch_gate tests.test_mtr_host_request_store
```

These results test the module API and synthetic neighboring contracts; they do
not demonstrate host/transport integration or production signing-key custody.
