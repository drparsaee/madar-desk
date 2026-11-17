# E4 wrong-party-link impact and selective correction intent (2026-11-10)

**Scope: pure, synthetic-only, nonmutating pilot for approved Refine 6.15/6.16. Not a production link-correction API.**

## Added sources

- `mtr_e4_link_correction_pilot.py`
- `tests/test_mtr_e4_link_correction_pilot.py`

## Behavior

- Given a synthetic, host-supplied complete snapshot of orders linked to an existing customer/party and a reviewer principal, it builds an authorized, field-minimal **before/after impact preview**. It refuses incomplete counts, duplicate IDs, cross-org/project/customer/party rows, old and new party equality, expired snapshots, missing order/document visibility, inactive reviewer and absent project/capability grants.
- Exposes each affected order's ID, state, proposed party, finance request reference and document IDs **only when supplied as explicitly host-authorized**. It does not expose document bodies, ledger amounts, prices, bank data or private customer detail.
- A separate explicit human selection may produce an **UNSENT_SELECTION_INTENT** for a subset of open/draft orders with **no** linked finance request and **no** linked document. Submitted, posted, closed or finance-linked orders cannot be selected in this pilot. CAS-style revision/digest checks and a canonical preview digest reject stale or tampered displays. No bulk auto-selection.
- Never writes an order, changes a customer or party link, changes a financial request, mutates a Taraz document or sends a network request. It has no storage or LAN route, no official finance review and no signable receipt.

## Evidence

Command, in isolated Madar worktree:

```powershell
py -3.12 -B -m unittest -v tests.test_mtr_e4_link_correction_pilot
```

**12/12 tests OK, exit 0, 2026-11-10.** Cases include five dependent records, two explicitly selected, no changes, missing ACL/doc grants, stale/future source, cross-tenant, duplicate, revoked reviewer, forged preview and no production mode. All fixtures are in-memory Python objects, not user profiles or Taraz financial books.

## Critical non-acceptance limits

1. `HostImpactSnapshot` and `HostPrincipal` are **assertions supplied by a caller**. This module does not independently authenticate an actual Madar host session, discover authoritative linked orders/documents, validate a remote Taraz ledger or prove the caller supplied every dependency. `allHostSuppliedDependenciesVisible` describes internal consistency of the synthetic input, not external completeness.
2. Digest/CAS here detects changed preview content and a caller-supplied revision mismatch. It is not a signed server receipt or transactional check against current live cards/ledger. Any future live adapter must read source and ACL from a trusted host inside its own lock/transaction, then revalidate immediately before applying a selected change.
3. Selection only produces an **unsent intent**. No actual selective card correction, immutable before/after audit, official link mutation, review UI or rollback is implemented. Formal AC-18 and AC-19 remain OPEN.
4. No remote credentials, real documents, real profile, installed client, two-PC network or production environment were accessed or modified. No commit, push or deploy.
