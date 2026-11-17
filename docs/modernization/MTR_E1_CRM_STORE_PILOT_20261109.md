# E1 Radar CRM SQLite store: isolated synthetic pilot

Date: 2026-11-09. Source baseline: Madar worktree HEAD `32bd8ff`. This is a **new standalone module and tests**, not a native, LAN, production, or official Taraz integration.

## Implemented contract

The new `radar_crm_store.py` exports `RadarCrmStore(database_path)`, `Principal`, `CrmError(code)`, and frozen read/write result types. The host supplies an authenticated fresh `Principal` with organization, granted projects, activity status, explicit capabilities and permitted tenant/project assignee IDs. The browser must never construct this capability itself.

The durable SQLite data model has composite organization/project/contact keys, a separately scoped follow-up table and an append-only events table. User actions create/update/soft-delete a CRM contact, append a human-reported interaction, schedule an internal follow-up due for a named assignee, and explicitly mark the follow-up completed. Every write supplies actor, event ID, an offset-aware timestamp, and (for existing contacts) an expected contact version. Audit events retain the actor, action, timestamp, prior/new values where relevant, request digest and resulting version. Existing audit events cannot be updated or deleted through SQL while the registered triggers remain in place. Records are soft-deleted; their history remains accessible to currently authorized staff.

The store uses `BEGIN IMMEDIATE` and a composite unique event key for atomic compare-and-swap/idempotent writes across connections or processes. A repeated identical event returns its original version and does not create new events. A reused event ID for different data is rejected. Queries require a current host-supplied capability and are bounded and limited to its organization and project. Contacts are visible only to the owner, current assignee or an explicitly privileged manager. Due reminders go only to the **currently authorized assignee**; changing the contact assignee does not silently forward an old reminder. All due dates are normalized to UTC before comparison.

No background scheduler, outbound contact, email, SMS, messaging, API call, accounting ledger, official Taraz customer record, matching or party link is present. Radar E4 party matching remains an independent pure module.

## Evidence

Commands run with Python 3.12 in the isolated worktree, using only unique synthetic temporary SQLite databases:

- `py -3.12 -B -m unittest -q tests.test_radar_crm_store`: **22 tests, OK**. Includes restart persistence, duplicate-event replay, changed-payload rejection, CAS conflict and rollback, real concurrent separate Windows process writers, scope isolation, removed access after reassignment, append-only audit, soft-delete history, human reminder scheduling/completion, UTC offset normalization and no socket use in the tested reminder path.
- `py -3.12 -B -m unittest -q tests.test_radar_party_match_preview`: **11 adjacent E4 tests, OK**. No E4 file was changed.
- `py -3.12 -B -m py_compile radar_crm_store.py tests/test_radar_crm_store.py`: exit 0.

These are synthetic tests of this source module only. A future MadarHost adapter must enforce fresh identity and project/assignee grants and OS-level database permissions, supply authoritative timestamps, handle backup/readback/recovery and test installed multi-user GUI and installed LAN behavior. These tests do not prove tamper-proof audit against privileged database administrators, cross-machine synchronization, encryption at rest, production migration or operational readiness.

## Release boundary

Only `radar_crm_store.py`, `tests/test_radar_crm_store.py`, and this document were created for this assignment. No edits to shared modules, no real customer/finance data, no commit, no push, no deployment.
