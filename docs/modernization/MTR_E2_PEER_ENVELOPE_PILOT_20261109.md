# E2 isolated MTR v2 peer-envelope pilot (2026-11-09)

## Scope and ownership

Experimental **pure Python** request signing, independent verification, query-first lookup and signed lookup-response verification. Not integrated into existing Madar UI, MadarHost, Taraz, existing schema-1 file inbox, databases or any network. Two different fixed **test-only** 32-byte secrets exist exclusively in the test module and are passed explicitly to signing/verification calls. Production keys are **not** present, provisioned or stored.

Approved intent: Refine **6.4** (controlled request/status/authorized catalog read, official records only in Taraz), **6.5** (initial financial-review request sent by explicit authorized user), **6.9** (transport uncertainty is separate from finance review/approval/official posting), **6.10** (query receipt before considering recovery of the *same* previously authorized message). AC-05..AC-13 remain **OPEN** until authenticated cross-app service and E2E acceptance.

New source: \`mtr_peer_envelope.py\`. New tests: \`tests/test_mtr_peer_envelope.py\`. Independent audit \`MTR_E7_ACCEPTANCE_GATES_20261109.md\` is **unchanged**. No modifications to \`taraz_exchange.py\`, \`taraz_review_status.py\`, \`native_app.py\`, \`taraz_integration.py\`, Taraz worktrees or operational profiles.

## Protocol v2 wire contract

All messages are strictly **canonical UTF-8 JSON bytes** (Unicode retained, sorted keys, no padding or trailing whitespace, no duplicate/extra/missing keys; invalid/floating/non-finite numbers rejected). All fields below, including \`payload\`, are covered by HMAC-SHA256 with a version-specific domain prefix. MAC is a lowercase hex string. The payload gets its own lowercase SHA-256 digest of canonical JSON. HMAC comparison uses \`hmac.compare_digest\` on decoded digests.

| Field | Requirement |
|---|---|
| \`protocol\`, \`version\`, \`algorithm\` | Fixed \`mtr-peer\`, JSON integer \`2\`, \`HMAC-SHA256\`; never negotiates insecure algorithms |
| \`kind\` / \`purpose\` | \`request\`: \`finance_review_request\`, \`catalog_read_query\`, \`party_creation_proposal\`; \`query\`: \`receipt_lookup\`; \`receipt\`: \`receipt_lookup_result\` |
| \`organizationId\`, \`senderId\`, \`senderRole\`, \`actorRole\` | Explicit scope and role claims to compare with **trusted expected** tenant, peer identity and allowed actor roles |
| \`audience\` | \`taraz_peer\` for Madar-origin requests/queries; \`madar_sender\` for Taraz lookup responses |
| \`keyId\` | Named key slot; verifier must select expected key from independent trusted host configuration, never by blindly trusting this field |
| \`requestId\` | Exactly 32 lowercase hex characters; query uses a **new** ID distinct from original. A response carries the **query** ID |
| \`issuedUtc\`, \`expiresUtc\` | Exact UTC seconds, for example \`2026-11-09T15:00:00Z\`; lifetime strictly greater than zero and no more than 300 seconds; verification rejects expired and >30-second future-issued messages |
| \`payloadSha256\`, \`payload\`, \`mac\` | Tamper-bound digest, JSON object, independent HMAC; at most 16 KiB canonical payload and 32 KiB entire signed envelope; bounded nesting/count/types |

The \`request\` kind requires an explicit signed call with \`authorized is True\` and \`explicit_manual_action is True\`; those are **caller's trusted host assertions**, not proof obtained from a client-controlled boolean. The receipt-query payload contains precisely \`originalRequestId\`, \`originalPurpose\`, \`originalPayloadSha256\`; a query uses a fresh query ID. The signed peer lookup result copies those fields and adds \`queryRequestId\`, \`queryPayloadSha256\`, \`lookupStatus\`. Only \`received\`, \`not_received\` and \`unknown\` are recognized. No finance approval/posting/document fields are created.

## Independent public APIs and safe decision contract

| API | Result and safety limit |
|---|---|
| \`sign_request(...)\` | Signed request bytes. Requires explicit already-authorized manual action, scope, purpose, role, time and caller-injected request key. **No transmission.** |
| \`verify_request(...)\` | Verified scalar claims after MAC, canonical JSON, org/sender/keyId, approved actor roles, type, purpose, expiry and size checks. |
| \`sign_receipt_query(original_verified, ...)\` | Separate signed lookup request for exactly the original ID/payload hash. **Does not resend original.** |
| \`verify_receipt_query(...)\` | Verifies lookup request using the Madar-direction key, expected organization/sender/actor roles and recipient. |
| \`sign_peer_receipt(query_verified, ...)\` | Signs a **simulated** Taraz lookup claim with the distinct Taraz-direction test key. **Not a financial receipt.** |
| \`verify_peer_receipt(..., original=..., query=...)\` | Verifies using the independently selected Taraz-direction key and exact original/query/organization binding. |
| \`check_replay_binding(verified, previous=...)\` | Pure read of caller-supplied per-(org,kind,requestId) binding to (senderId,senderRole,actorRole,purpose,keyId,payloadSHA256): \`new\`, \`identical\`, or reject any identity/purpose/payload conflict. **No atomic insert or durable store.** |
| \`query_first_recovery_decision(...)\` | Pure string: missing query result / lost approval => hold, peer lookup unknown => hold, peer claims received => observe claim, peer claims not received => eligible for *identical previously authorized attempt*. **Never retries, posts, or claims a formal receipt.** |

The return \`eligible_for_identical_prior_authorized_attempt\` is **not an authorization to issue a network send by itself**. Integration must re-check trusted persisted original manual approval and original ID/payload, compare the complete reply against the verifier's authenticated Taraz peer identity, perform an atomic server-side idempotency check and handle a response becoming stale while the original is in flight. A verified HMAC only authenticates possession of the selected shared key; it does not prove the peer is an actual Taraz installation, a finance officer approved anything, the lookup is authoritative, or the financial ledger has no transaction. A symmetric MAC is not a third-party-verifiable signature.

### Evidence and validation limits

- Test command: \`python -B -m unittest -v tests.test_mtr_peer_envelope\`. **16 tests passed** in the isolated Madar worktree on 2026-11-09. Checks canonical and independent verification, wrong tenant/sender/key/role/purpose/algorithm/version, tampering, malformed/noncanonical/duplicate JSON, bounded payloads, expiry/clock, short-key rejection, two different injected test keys, query-to-original binding, peer lookup statuses, absent query hold, old approval mismatch, identical-request replay and conflicting reuse. These tests perform no file, network, service or ledger I/O.
- Scoped coexistence rerun: \`python -B -m unittest -v tests.test_mtr_peer_envelope tests.test_mtr_finance_workflow_contract tests.test_taraz_review_status\` => **49 tests passed**, exit 0. A different wider run that also included the **existing** \`tests.test_taraz_manual_retry\` had **59 tests, 1 error** in \`test_native_bridge_accepts_exact_manual_retry_id\` at line 135, due to \`taraz_exchange.py:_build_proposal\` line 231 while other workers were editing that shared source. No claim of a fully green suite; this worker did not change existing tests or production source.
- Protocol is intentionally **not** connected to existing local \`pending\` / \`reviewed\` metadata flow or operational Taraz code. No durable key management, TLS/mTLS, server organization ACL, user action audit, simultaneous host transaction/compare-and-set, real query-first delivery, finance receipt/document authority, real two-PC LAN, power-loss recovery or production installer has been exercised.
- The companion map check requires a **trusted externally persisted map** and host transaction locks. It cannot detect a concurrent duplicate before either independent process records the ID, and signed \`not_received\` from a test peer cannot guarantee financial idempotency.

**Release status:** E2 signed envelope **pilot only**. AC-05..13 and G-01..08 are still open, as in the independent E7 acceptance audit. No commit, push, deploy, credential persistence or real financial action.
