# P0 Madar ↔ Taraz finance: current-source synthetic cross-app QA

**Date:** 2026-11-10

**Disposition:** **SYNTHETIC SOURCE-ONLY QA PASSED** for the bounded paths
below. **Operational finance pairing, authenticated installed runtime,
official Taraz receipt, release and deployment remain NO_GO.**

## Ownership and live source boundaries

- Changed only **NEW**
  `scripts/qa_mtr_finance_crosssource_synthetic_20261110.py`,
  `tests/test_mtr_finance_crosssource_synthetic_20261110.py`, and this document.
- **Madar root:** `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107`
  (HEAD seen `32bd8ff`, pre-existing multi-agent dirty state).
- **Taraz root:** `D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109`
  (HEAD seen `653089b`, pre-existing dirty state).
- Existing `lan.py`, `taraz_exchange.py`,
  `mtr_finance_authenticated_origin.py`,
  `mtr_peer_envelope.py`, `mtr_taraz_finance_witness_verifier.py`,
  Taraz company/identity/registry/review/accounting/finance issuer modules,
  their fixtures and source tests were **read only**. The script checks
  mandatory current-source files exist, refuses links, and includes per-run
  SHA-256 source-file hashes in the resulting JSON. These hashes describe
  source snapshots, not a trusted installed version.

## Exact synthetic stages and evidence

1. Create private disposable `LanService`, with an **actual** current
   `account_for(token)` session backed by `make_account`, an owner-scoped
   synthetic admin and a saved task with one exact 2 × 750 RIAL expense.
   No live server or external identity is contacted.
2. Use the **current** `taraz_exchange.queue_saved_task(..., request_id=...)`,
   which calls `_publish_proposal`. Read the **actual persisted raw UTF-8
   bytes** from the temporary pending file. This deliberately preserves
   insertion-order JSON instead of replacing it with the separately
   canonicalized HMAC-envelope bytes. Check positive `amountRial = "1500"`
   and SHA-256 of that exact file.
3. `HostAuthenticatedFinanceOrigin.prepare_manual` and
   `sign_original_manual` prove the current saved task, account lineage,
   session, company, source digest and invoice/journal IDs. The signer
   issues the v2 HMAC request. `sign_query_manual` produces one original-bound
   challenge; a second query from the same origin is denied.
4. Current `TarazPeerRegistry.intake` records one original, and a repeated
   **same-wire** delivery after a simulated lost acknowledgment is idempotent.
   `query_receipt` returns a separately direction-key-signed metadata receipt;
   repeated same-query lookup is byte-identical and SQLite still contains
   **exactly one original and one query**. The test injects
   `verified_transport_peer=True` only for this synthetic local exercise.
   That flag does **not** prove an authenticated network, TLS peer or service.
5. Register an isolated Taraz company with `StandaloneCompanyRegistry`,
   real `LocalCompanyIdentity` **admin and editor** synthetic sessions.
   Actual `TarazAPI.tarazIntegrationReview`, using the editor's current
   authenticated session, moves the proposal and creates source-bound
   intent + nonfinancial review files with the **original source digest**.
   Review has `financialEventCreated=False`.
6. Independently logged-in **Taraz company admin** calls the real
   `AccountingDesktopAPI.standaloneAccountingCommand` for
   `party.register`, `invoice.create`, `invoice.approve`,
   `invoice.issue` with monotonically checked revision. It persists
   **one actual invoice.issue event, revision 4**, to **only the test company's
   disposable SQLite**, not a real accounting file. An independent SQL
   read verifies the persisted state/digest, event and revision.
7. Actual Taraz `ManualExternalActorLinks.authorize_manual` approves the
   77-character external Madar lineage ID using that company's **real
   synthetic admin session**. It binds the current HMAC original/challenge
   and company/request IDs, one time.
8. Two deliberately **independent disposable scenarios**, because their
   one-time external-actor link must never be reused:

   - `--mode binding`: Actual `ManualFinanceBindingAuthority` reads the
     posted invoice, registered query, exact reviewed source and current
     admin session, then returns
     `SIGNED_BINDING_TO_EXISTING_JOURNAL_OBSERVED_NOT_OFFICIAL`.
     A second binding is rejected, and no new journal entry is written.
   - `--mode witness`: Actual new
     `ManualTarazFinanceWitnessIssuer` receives a **separate, freshly
     generated synthetic finance-direction HMAC key**, private
     one-shot issuance SQLite, the authenticated company+admin context and
     already posted event. `DurableFinanceWitnessChallenges.register_manual`
     independently registers the same source-bound query. Current
     `TarazFinanceWitnessVerifier.inspect_and_consume` verifies the exact
     signed journal and accounting event bytes, ledger revision and ledger
     SHA-256; consumes the challenge durably. Both issuer and verifier reject
     replay. The verifier result remains
     `SIGNED_WITNESS_STRUCTURALLY_VERIFIED_OFFICIAL_ISSUER_UNAVAILABLE`.
     This is **synthetic structural/cryptographic evidence only**. In
     particular `realTarazIssuerAuthenticated=False`,
     `independentLiveLedgerReadbackVerified=False` and
     `officialFinanceReceiptVerified=False`.

Each result includes **sourceRawSha256**, **reviewedRawSha256** (must match),
**reviewMarkerSha256**, **signedOriginalWireSha256**,
**signedQueryWireSha256**, **signedPeerLookupSha256**,
**invoiceIssueEventSha256**, **ledgerStateSha256** and relevant
signed-finance-witness raw hashes. These are *per-run random synthetic
evidence* and are not stable releases or production pins.

## Reproduction and actual test scope

From the original Madar isolated source directory:

```powershell
python -B scripts/qa_mtr_finance_crosssource_synthetic_20261110.py --mode binding
python -B scripts/qa_mtr_finance_crosssource_synthetic_20261110.py --mode witness
python -B -m unittest tests.test_mtr_finance_crosssource_synthetic_20261110 -v
```

The focused suite recorded **6/6 passing** after fixing the test's own
SQLite connection-closure issue. It covers both actual-source paths,
matching raw source hashes and durable journal event, same-ID lost-ACK
replay, one-time challenge/issuer rejection, no official-status promotion,
nonempty temp-root refusal, missing-source fail-closed, invalid mode,
and blocked CLI output. Each scenario creates its *own* temporary company,
token, peer registry and ledger. This is not an operator login test.

## Explicit remaining blockers

- The script uses **synthetic sessions, a synthetic company, random
  self-provisioned test-only keys and an injected transport-trust boolean**.
  It does not authenticate an installed Madar/Taraz peer, perform TLS,
  verify credential provisioning or execute a service listener/GUI.
- The operator-facing finance issuer has **not been wired into the installed
  Taraz EXE or deployed service**. Prime reported that the currently
  examined QA bundle omitted its finance authority, external actor link,
  attestation and peer HTTP/registry modules. The source-level issuer and
  verifier tests do not change that deployment fact.
- Signing a synthetic journal witness does **not** establish external live
  accounting authority. The current verifier intentionally cannot promote
  its output to an official finance receipt, even after a successful HMAC,
  durable one-shot challenge, and matching journal event.
- Existing `1.0.23` source vs observed `1.0.26` installed mismatch and
  the separate `1.0.26` source-port worktree remain release blockers.
  Full Gated E7 compatibility, installer provenance, startup/recovery,
  trust key provisioning and real authorized two-PC QA remain unverified.
- No production ledger or user account was modified, no native process,
  network, installed binary, real profile, git commit, push, signing or
  release was involved in this synthetic tool.

**Final flags in both modes:** `officialFinanceReceiptVerified=false`,
`financialPostingReal=false`, `installed=false`,
`mayRelease=false`, `mayDeploy=false`, even when synthetic ledger and
witness structural evidence are positive.
