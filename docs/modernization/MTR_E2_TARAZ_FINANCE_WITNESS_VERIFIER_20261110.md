# P0 Taraz finance-journal witness verifier contract (2026-11-10)

**Scope: NEW, isolated-source verification prototype only. There is no actual authenticated Taraz finance-witness issuer. No production witness is accepted as official.**

Files added:

- `mtr_taraz_finance_witness_verifier.py`
- `tests/test_mtr_taraz_finance_witness_verifier_20261110.py`

The Taraz files `taraz_mtr_finance_binding_authority.py` and
`taraz_mtr_external_actor_link.py` were inspected read-only. Both expressly
report `officialFinanceReceiptVerified=false`. The Madar
`mtr_host_request_store.py` currently denies `record_query_result` and has
no durable, finance-specific one-use peer challenge/issuer transaction; its
recovery reads provide read-only metadata but no official receipt authority.
No existing Madar or Taraz source was modified.

## Typed, strict future witness interface

`FinanceWitnessTrust` must be explicitly provisioned by a trusted host
operator with an organization ID, Madar sender/key IDs and private Madar HMAC
key, plus a separate, dedicated Taraz finance issuer/key ID and independently
provisioned finance-direction HMAC key. There are no default keys, key lookup
from JSON, local-admin shortcuts, or `verified=True` flags. Key reuse across
Madar and Taraz directions is rejected. The keys cannot be pickled via the
typed config; repr redacts them.

`DurableFinanceWitnessChallenges` uses an explicit existing private
directory and a fixed SQLite filename,
`mtr-taraz-finance-witness-queries.sqlite3`. On explicit manual host action,
`register_manual` verifies the signed original
`finance_review_request` and signed `receipt_lookup` query using the
provisioned Madar HMAC key. It requires matching original/query HMAC
identities, organization, role, request ID, payload digest, source SHA-256,
project, immutable external actor lineage, company, invoice, event, journal,
and positive original RIAL amount. It records the exact immutable binding
hash, original/query wire hashes and challenge expiry; an original request
or query ID cannot be registered twice, including across process restarts.
The SQLite journal does not prune replay records automatically.

`TarazFinanceWitnessVerifier.inspect_and_consume` enforces an exact
canonical, bounded **proposed** wire format:

- Protocol `mtr-taraz-journal-witness`, version 1, algorithm HMAC-SHA256,
  purpose `invoice-issue-readback`, audience `madar.finance`.
- Organization and dedicated finance issuer/key; original request ID, original
  wire digest, original payload digest, exact Madar query/challenge ID and wire
  digest.
- Original Madar source digest (of **actual source file bytes**, without
  canonicalizing insertion-order JSON), task/project, immutable 77-character
  Madar actor, selected registered-company ID, invoice ID, issue event ID and
  journal ID.
- Currency exactly `RIAL`, canonical positive decimal `amountRial`,
  positive exact ledger revision and asserted full-ledger-state SHA-256.
- SHA-256 digests of the supplied canonical journal and accounting event;
  journal `sourceType=invoice.issue`, exact invoice/event IDs, matching
  `J:<event>`, nonreversal, posting date, nonnegative balanced debit/credit
  lines, and matching `invoice.issue` event/result and amount.
- UTC issued/expiry timestamps, bounded lifetime, not after the signed query
  expiry. Time overrides are accepted only within 5 seconds of actual current
  UTC. Witness HMAC uses a separate domain prefix from peer metadata.

After **all** signature and structural checks, SQLite consumes the matching
registered challenge under `BEGIN IMMEDIATE` with a single update to the
one-time state. Reopening the registry does not permit replay, and competing
threads cannot both consume. Invalid/wrong-key/stale proofs cannot consume a
valid challenge.

The returned `FinanceWitnessAssessment` is a frozen typed result, with
`signedFinanceWitnessCryptographyVerified=True` only for exact synthetic
cryptographic agreement. Even for this result:

```text
decision = SIGNED_WITNESS_STRUCTURALLY_VERIFIED_OFFICIAL_ISSUER_UNAVAILABLE
realTarazIssuerAuthenticated = false
independentLiveLedgerReadbackVerified = false
officialFinanceReceiptVerified = false
financialEventCreatedByVerifier = false
safeToRetryFinancialPosting = false
```

Without operator provisioned trust or without a durable challenge journal,
the result is respectively `BLOCKED_NO_OPERATOR_FINANCE_TRUST` or
`BLOCKED_NO_DURABLE_CHALLENGE`, with all official/financial flags false.

## Explicit production blockers

1. **No trusted issuer exists.** The Taraz source provides verified local
   *readback* of preexisting accounting state but no finance-witness signing
   authority independently tied to that ledger, its current authenticated
   registered-company operator, company ACL, immutable journal/event read and
   a verifiable private signing key/certificate. A synthetic keyed HMAC is
   therefore a contract test, not real Taraz trust.
2. **No independent live ledger proof on Madar.** The witness input contains
   signed bytes and their digests. Even if the HMAC agrees, Madar cannot know
   whether the event was truly persisted, subsequently reversed or came from
   an authoritative Taraz snapshot without a trusted issuer. Source
   `invoice.create.sourceType/sourceId` is caller controlled. A Taraz issuer
   must read and attest the journal in a consistent company/role-verified
   snapshot and own the finance signing key. The independent actor mapping
   currently issues only one-time *consent to inspect*, not official identity
   provenance.
3. **Challenge authority is separate.** The NEW SQLite challenge store is
   useful only for isolated synthetic replay verification. A production
   host must integrate issuance and consumption with its own durable outbox,
   signed-original state, authenticated `LanService.account_for` session
   and authorization epochs, and consume proof in the official receipt
   ingestion transaction. The current store deliberately refuses this
   promotion. Registering a challenge using an otherwise valid HMAC does not
   prove that the live host authorized it.
4. **Source byte-order mismatch remains outside worker scope.** The actual
   `taraz_exchange._publish_proposal` writes compact insertion-order JSON
   and SHA-256 should bind those exact persisted bytes. The previously
   added `mtr_finance_authenticated_origin._proposal_bytes` currently
   requires sorted canonical JSON and cannot accept the real exported file
   directly. This new verifier accepts the actual compact, insertion-order
   source and hashes original bytes, but the origin signer requires an
   independently authorized fix. Its prior files were not modified here.
5. **Current Taraz and Madar finance receipt UI/HostRequestStore APIs are not
   connected.** No receipt posting, acknowledgement, automatic retry,
   installed application or LAN server was invoked in this step.

## Synthetic verification

Run:
```powershell
python -m py_compile mtr_taraz_finance_witness_verifier.py tests/test_mtr_taraz_finance_witness_verifier_20261110.py
python -m unittest discover -s tests -p test_mtr_taraz_finance_witness_verifier_20261110.py -q
```

The tests use only random disposable in-test keys, an isolated
`TemporaryDirectory` SQLite challenge journal, read-only imports from
Madar peer-envelope signing primitives, and synthetic journal/event data
that follow the inspected Taraz `invoice.issue` shape. There is no test
of actual Taraz issuer keys, installed GUI, finance ledger, real profiles,
external network, service, signing or production publication.

**Observed verification:** `py_compile` succeeded. The dedicated
`unittest discover` suite passed **13/13 tests** on the isolated source
(exit 0, approximately 0.61 s). Source byte order, fail-closed trust,
tampering, event reversal, expiry, role/tenant/witness bindings, persistent
replay across restart, simultaneous consumers and linked/corrupt SQLite are
covered synthetically. No statement of operational acceptance follows from
these tests. SQLite replay protections are local to this journal: rollback of
the journal to an older disk snapshot is not independently detectable without
additional trusted persistence.
