# E4 detached Taraz local catalog -> Radar candidate review pilot

**Status: synthetic cross-repository local read and manual decision; E4/G gates OPEN.**

`mtr_e4_local_catalog_pilot.py` is an isolated, **unmounted** Python adapter.
With explicit `MTR_TARAZ_SOURCE` pointing at detached Taraz code, it loads
`TarazCatalogRead` which actually reads a synthetic company-specific
`StandaloneAccountingStore` under a valid `LocalCompanyIdentity` session.
The adapter enforces that the reviewer organization/project and permitted
candidate IDs/fields correspond to the host-injected catalog scope. It
collects **all** authorized party pages before calling
`PartyReviewStore.open_pending`, rejects a candidate set larger than 64
rather than showing an incomplete shortlist, and saves a versioned audit.

Only the safe Taraz catalog fields `id/name` are passed to the Radar matching
preview. Other comparison fields (`official_id`, `phone`, `address`) are
`not_authorized`, not guessed. `name` matches are heuristic and never
verify identity. A duplicate name creates **multiple distinct candidate
rows**. The human must explicitly select a candidate or reject all.

Before a human decision, the same authorized local catalog is reread and its
revision/candidate list/preview digest compared with the saved snapshot;
changed local book or temporary-customer data blocks the decision. Even a
recorded selection leaves `officialPartyLinked=False`,
`officialTarazPartyCreated=False`, `networkUsed=False` and no mutation to
Taraz accounting. No linked party record or financial document is written.

## Reproducible evidence

```powershell
$env:MTR_TARAZ_SOURCE='D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109'
py -3.12 -B -m unittest -v tests.test_mtr_e4_local_catalog_pilot
Remove-Item Env:MTR_TARAZ_SOURCE
```

**Observed: 7/7 passed, exit 0**, with independent synthetic Taraz registry,
identity and accounting book (three artificial parties including a hidden
row) in `TemporaryDirectory`, plus a durable Radar human-review SQLite DB.
The suite verified complete duplicate-name candidate retention, human
selection without financial mutation, source revision and temporary-customer
staleness denial, session logout/revocation, reviewer row/org/project ACL
denial, and source observation expiry. The Taraz catalog reader's own
**25 tests passed** in detached Taraz worktree according to the worker's
separate tool report, not a second independent rerun by prime.

## Unresolved boundary

- `LocalCompanyIdentity` authenticates a local synthetic company's session.
  It is **not** remote Taraz peer/transport authentication, authoritative
  official tax identity, certified provenance or a legal party verification.
- `HostPrincipal`, `HostCatalogScope` and the temporary Radar customer are
  **injected trust assertions**. The host must derive each from actual
  authenticated users, current scoped CRM data and official Taraz grants.
- No production session vault, company mapping, trusted remote company API,
  revocation across hosts, installed LAN route, party-link transaction,
  rollback or two-Windows-machine E7 acceptance exists in this adapter.
- Source-side 64-party bound deliberately fails closed for larger catalogs;
  real server-side filtered/search pagination and authorization are needed.
- The code is excluded from default application startup and never uses
  actual user profiles, cloud services, or real company ledgers.
