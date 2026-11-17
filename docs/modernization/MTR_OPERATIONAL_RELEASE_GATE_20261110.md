# Madar ↔ Taraz P0: read-only operational release veto gate (2026-11-10)

**Scope:** one new verifier, one new synthetic test module, this note. The
verifier never signs, installs, migrates, opens real profiles, runs services,
posts ledger entries or changes any deployment. It is a **veto/check** for an
independently reviewed future release, not an approval or a source of evidence.

## Current observed result

Command (read-only):

```powershell
py -3.12 -B tools/mtr_operational_release_gate_20261110.py
```

Expected **NO_GO / exit 2** for the current isolated source and QA-only bundle.
There are **two explicit policies**:

- Default `--policy production-signed`: validates Windows Authenticode and
  requires nine independent proof domains, including signing.
- Owner-authorized **signing-deferred**
  `--policy owner-controlled-unsigned-qa`: checks eight independent domains
  (all except binary signing) and records actual `NotSigned` without making
  signature absence its own blocker. This mode **never means signed release,
  permission to install, or production acceptance**. It does NOT waive source,
  version, peer, crash, backup/restore, official financial receipt or rollback
  evidence. Any generated `QA_EVIDENCE_ACCEPTABLE_NOT_INSTALLABLE` label is
  explicitly nonproduction. Both policies have `mayInstall=false` and
  `mayDeploy=false` regardless of other results.

The second policy reflects the owner's earlier instruction to defer signing
for the Madar QA stage; it does not silently reverse that decision or claim
unsigned production distribution is safe. Current candidate is **NO_GO in
both policies** for independent reasons beyond signing.
The immutable QA-only EXE is
`D:\CoS-Test\MTR-MADAR-TARAZ-QA-BUNDLE-20261110\run-20261110-144128-10416-207ce8ba\exe-dist\Madar-Taraz-Connection-QA-20261110-NONRELEASE.exe`,
SHA-256 `11a9726f976bd633c6eb120b939e1d7aab63c6ca99a3e3b5a5cc57bd967ed4f9`.

The inspector verifies the 6,501-entry input inventory and SHA-256 tree,
all snapshot file bytes, selected live source identity, Vite asset hashes,
PyInstaller embedded assets and embedded provenance, exact EXE SHA, and
package/lock/updater version consistency. This demonstrates **QA provenance**,
not a release-grade build from a clean commit.

**Actual blockers:** source is concurrently dirty; bundle and manifest
explicitly say **QA_ONLY_NON_RELEASE**; source/build version is **1.0.23**
versus the previously observed installed **1.0.26** baseline; Windows
Authenticode on this QA EXE returned **NotSigned** (only a mandatory blocker
in the signed-production policy); no production trusted
independent attester public keys are provisioned; no authoritative,
fresh, source-bound nine-domain operational proof set is provided. The
E7 acceptance matrix documents all 32 AC + eight G gates **OPEN**. Running a
source/test synthetic scenario is not formal financial-transaction acceptance.

## Independent proof requirements

A separately reviewed future candidate requires a NEW immutable release
binary and independently pinned source/build identity. The proof convention is
an **external** directory with `proofs.json`, one `<kind>.json` signed
detail per domain and exact accompanying SHA-256-bound witness files. Nine
independently pinned RSA-2048+ public keys (different keys and roles) must be
provisioned in the reviewed verifier source **separately from the proofs**:

| Domain | Required external evidence |
|---|---|
| source | Clean exact committed source, complete source inventory |
| build | Cumulative immutable release, complete reproducible build provenance, signed offline WebView2 prerequisite |
| tests | Entire Python and JavaScript suite, zero missed/failing tests, all 40 AC/G scenarios |
| peer | Authenticated mutual TLS, independently pinned Taraz service identity and host-side authorization on two real clients |
| crash | Power-loss fault injection, query-first restart and ledger-side idempotency |
| backup | Full-scope snapshot and independently verified readback/restore/reconciliation |
| finance | **Authoritative Taraz-signed** receipt, official document identifier and ledger readback; local `.review.json` is never sufficient |
| rollback | Upgrade trial on disposable profiles and independent restoration of all retained data |
| signing | Valid Windows Authenticode signer chain/publisher thumbprint plus offline runtime signature and install package |

Every proof must have exact schema, correct independent issuer role, one
release/run/source identity, unexpired strict UTC timestamps, signed JSON
contents, SHA-256-bound witness files, and all required scenario checks TRUE.
The QA-only deferred-signing mode uses eight distinct independently signed
proofs without `signing`; signing still needs a separate release approval
before any future signed production distribution.
Missing, duplicate, extra, forged, stale or cross-run proofs are rejected.
No `--trust-on-first-use`, `--allow-unsigned`, injected certificate or
local fake receipt can elevate evidence; default trusted-key map remains
**empty**, so the production CLI **cannot authorize a release**.
Test-injected keys are permitted only in isolated Python unit fixtures.

## Gates *not* closed by this implementation

The gate does **not** create the nine witnesses, approve signing keys,
authenticate an official Taraz ledger, run backup/restore/power-loss tests,
or test an installer. A future signed release must be audited again against
its own exact binary and source, then pass separate owner acceptance.
`decision=GO` in a hypothetical verified artifact would still be a
read-only assessment; the tool's `mayInstall` and `mayDeploy` remain FALSE.
Installation, rollback staging and explicit approval are controlled solely by
the prime/owner release procedure.
