# E2 signed-query journal/host boundary QA (2026-11-10)

## Result and scope

**9/9 new synthetic host-boundary tests PASS (exit 0, 18.164s).**
Only the **new** `tests/test_mtr_e2_journal_host_boundary_20261110.py`
was authored for this follow-up. This QA document is new. No production,
transport, journal, dispatch, Taraz or prior test source was edited.

The test composes `HostToPeerIntegratedTests` as a disposable fixture
without inheriting its prior test methods. It uses separate temporary SQLite
databases and a bounded local-only TLS test peer loaded from the detached
Taraz worktree. No real accounts, services, production network,
real finance books, commit, push, install or deployment were touched.

```powershell
$env:MTR_TARAZ_SOURCE='D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109'
py -3.12 -B -m unittest -q tests.test_mtr_e2_journal_host_boundary_20261110
# Ran 9 tests in 18.164s; OK; exit 0
```

## Observed, not assumed

| Negative case | Observed bounded outcome |
| --- | --- |
| Same original actor, new login session | Signed query and journal work; dispatch permit cannot be rearmed |
| Same account promoted editor -> admin | Taraz refuses original editor's actor-role claim; no journal row or new dispatch |
| Unsigned fake peer JSON | Rejected before journal callback; no receipt and no new dispatch |
| Tampered signed peer bytes | HMAC/envelope verification denies; no journal row |
| Same query ID with second contradictory, separately signed answer | Journal rejects and retains first immutable received observation |
| Finance ACL revoked after actual loopback response, before persistence | Host rechecks live account, denies journal write; regrant confirms zero rows |
| Lock-order around blocking network and journal persistence | Other thread takes host/card locks during peer I/O; journal write runs with host/card locks, no observed deadlock |
| Two concurrent signed queries | Both terminate and write separate observations without rearming dispatch |
| Host journal capacity 1; second fresh query | Second query raises capacity error, first record remains; no UI success, send slot still consumed |

The signed contradictory response in this QA was made only with a **known
synthetic test key**. It models a compromised or malfunctioning peer and does
not imply a browser user can sign such evidence.

## Risk distinctions

- **No confirmed exploitable high-risk bypass** in these nine cases. These
  tests show local fail-closed behavior, not global absence of defects.
- **Observed diagnostic inconsistency (low/medium):** when Taraz refuses an
  editor-origin query re-signed under admin actor-role, the HTTPS client can
  raise `PeerPilotProtocolError("unexpected peer content type")` rather
  than the intended peer-denial exception, because
  `mtr_peer_https_pilot.py` validates Content-Type before HTTP error status.
  This does **not** create a receipt, store a journal row or enable retry, but
  confuses error classification and could weaken operational diagnosis.
  No change to the transport source was authorized in this task.
- **Observed availability limit:** when journal capacity is full, the peer
  can accept and persist a new **query ID** before the host callback rejects
  its local journal write. No second finance request is sent, but the signed
  peer registry consumes one additional query slot. Lifetime retention
  planning must coordinate the host's and peer's 10k limits.
- **Not verified:** threat model for attacker-held Python execution or
  filesystem/DDL access; tamper-evident external anchor; long-duration
  process/power loss; true simultaneous operational LAN clients; certificate
  lifecycle; formal whole-product ACL concurrency; or a real Taraz finance
  authority. The journal hashes are not a trusted external audit anchor.
- **Integration remains synthetic:** `MtrE2HostPeerPilot` is explicitly
  `synthetic_only` and currently unmounted operationally. No E7 release,
  official financial receipt, invoice, posting or auto-resend is validated.

### Test provenance

The first broad invocation unintentionally imported the existing fixture
TestCase class into the new module's namespace, causing **27 tests** to run
instead of the intended nine and two harness errors. The imported fixture
class was then referenced **through its module**, so it is no longer
discovered twice. A subsequent nine-test run had two harness expectations
to correct: current LAN role changes prohibit scoped admin and password
updates revoke sessions; HMAC timestamp checks require second precision,
and the peer 409 path raises protocol-error classification. The final
**9/9** run above is the verified result. None of the early harness errors
was treated as a production security finding.
