# MTR E4 party-match preview — isolated, non-authoritative pilot

**Scope:** Refine 6.11–6.14 / proposed acceptance AC-14–AC-17. Source
baseline: Madar isolated worktree at `32bd8ff`. **Prototype only**:
no Taraz backend read, party registration, link, customer mutation, financial
posting, API call, UI integration, audit event write, or deployment.

## Function and contract

`radar_party_match_preview.preview_party_matches(temporary_customer, candidates, *, scope)`
is a pure Python function with no filesystem, network, clock, or database use.
The supplied candidate list is **already authorized and server-scoped**; the
function is not a substitute for server-side authentication, organization
isolation, row/field ACL, or a real read contract with authoritative Taraz.
These decisions remain backend blockers.

- `scope`: `organization_id` (nonblank exact identifier),
  `server_scoped=True`, `party_read_authorized=True`,
  `finance_review_authorized=True`, and explicit `visible_fields`
  (a subset of `official_id`, `name`, `phone`, `address`).
- `temporary_customer`: `customer_id`, `organization_id`, and optional
  `official_id`, `name`, `phone`, `address`,
  `official_id_source_verified`.
- Every element of `candidates`: `party_id`, `organization_id`,
  `read_authorized=True`, and the optional comparison fields above.
- Missing/false/unknown scope or reviewer permission, mismatched organization
  or unauthorized candidate rejects the **entire batch**. Unauthorized field
  values are neither compared nor reflected in the preview. Candidate IDs
  must be distinct to avoid an ambiguous decision target. Callers must not
  manufacture or accept ACL flags from untrusted clients.

The result includes every supplied authorized candidate **in input order**,
including rows with no visible matching fields and rows with conflicting
IDs; it never silently drops a row or applies a numerical threshold, score,
probability, sorting, or fuzzy rank. Each allowed field shows original
temporary/candidate values plus `missing_*`, `different`, or
`equal_after_heuristic_normalization`. Name/address may include shared
words, clearly identified as a **heuristic** rather than identity evidence.
Undisclosed fields show only `not_authorized`.

For text, the heuristic uses Unicode NFC, Arabic/Persian Yeh/Kaf formatting
variants, whitespace/ZWNJ handling, and conservative digit conversion.
Phone comparisons only ignore separators; `+98` is **not** guessed equal to
`0` and leading zeroes are kept. Official IDs retain leading zeroes and are
**not** checked against a national registry, validated for issuance, or
inferred. `official_id_source_verified=True` is merely a claim in the
upstream supplied record, never verification by this engine. Disagreement
between two such claimed-verified IDs is prominently reported as a conflict
even when names agree.

The return explicitly requires human financial review and states that no
official-ID verification, auto-link, or auto-creation occurred. It cannot
approve or record a decision. Refine 6.14 separately requires an authorized
financial actor's decision outcome, relevant reference, actor identity and
timestamp in an audited history; free-text explanation is optional. That
decision/audit backend is **not implemented here**. A request to create a
new official party remains a proposal until authorized action in Taraz.

## Synthetic validation

Run from the worktree using an **isolated parent environment** and Python 3.12:

```powershell
$python = @'
import subprocess, sys, tempfile
from pathlib import Path
from tools.safe_test_runner import isolated_environment
with tempfile.TemporaryDirectory(prefix="madar-radar-e4-") as temporary:
    env = isolated_environment(Path(temporary) / "profile")
    command = [sys.executable, "-B", "-m", "unittest", "discover",
               "-s", "tests", "-p", "test_radar_party_match_preview.py", "-v"]
    result = subprocess.run(command, env=env, cwd=Path.cwd(), check=False)
    raise SystemExit(result.returncode)
'@
$python | py -3.12 -B -
```

**Observed scoped result:** 11 tests passed, 0 errors, 0 failures (exit 0).
Coverage includes all visible candidates, conflict between source-claimed
verified IDs, missing fields, Persian/phone formatting, field ACL masking,
organization isolation and unknown ACL rejection, no mutation/network
invocation, no guessed IDs, and no human decision performed.

**Untested / blocked:** real Taraz read API and provenance, genuine identity
verification, authentication/ACL at production server boundary, tenant-row
access proofs, actual finance-review/audit workflow, concurrent decisions,
real users, installation and production release. E4 completion requires
E1/E2/E3 integrations and the authoritative read contract, not this pilot.
