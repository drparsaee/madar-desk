# BD13: Archive and restore a board-local list

**Status (2026-10-21):** Pure API with focused tests, wired into current `src/App.jsx` and `src/features.jsx` source. **Not part of the previously built RC2 executable.** Interactive GUI and two-device acceptance remain unverified.

## New deliverables

- **src/listarchive.js**: immutable, no-I/O board-list archive/restore
- **tests/listarchive.test.cjs**: self-contained Node tests using synthetic state only
- **LIST_ARCHIVE_API.md**: integration and schema contract

No shared JS/Python files, release, Git, external data, or APPDATA were changed.

## Exports and example

~~~js
import {archiveListState, restoreListState, activeBoardLists}
  from './listarchive.js';

// Missing or false canManage is DENIED. It must be the literal boolean true.
const next = archiveListState(state, boardId, listId, {canManage: true});
const originalVisible = activeBoardLists(next.boards.find(b => b.id === boardId));
const restored = restoreListState(next, boardId, listId, {canManage: true});
~~~

**Signature:** archiveListState(state, boardId, listId, options = {}) and restoreListState(state, boardId, listId, options = {}). Each is pure and changes only a single stage's **archived** boolean in the target board's **stages** array, returning a *new* state and board when needed. Repeated archive/restore calls on already archived/active lists return the **same state object** by identity (idempotency). Neither function persists anything.

Third export **activeBoardLists(board)** returns a *new* array with only stages whose archived flag is not true. It is a **UI-only view**. **Never persist this filtered list as board.stages**, or cards referring to hidden stages would lose a valid reference.

### Data representation

~~~json
{
  "boards": [{
    "id": "board-a",
    "stages": [
      {"id": "inbox", "label": "ورودی"},
      {"id": "review", "label": "بازبینی", "archived": true},
      {"id": "done", "label": "تکمیل"}
    ]
  }],
  "tasks": [{"id": "card-1", "boardId": "board-a", "listId": "review"}]
}
~~~

This illustrative fragment is **not** a complete valid host state. The review stage remains in the board's persisted stage array, at its original index. Cards remain attached to the same stage. On restore, only the flag changes to **archived: false**. Legacy stages missing that flag count as active: there is no migration or mass default insertion.

All other stage properties (label, subtitle, color, custom/future fields), board properties, task fields and array ordering are retained. **state.stages (global legacy stages) is never modified.**

## Data protection and guards

1. **Administrator UI gate:** options.canManage must be *exactly true*. Missing/false/string/number values are rejected even for already-archived/active no-ops. This is **not a trusted security boundary**: the authoritative host must recheck admin permissions and expected revision before accepting any persisted board change. Existing lan.py write_state restricts editors from editing boards (lines 471–506).
2. **Last active list:** cannot archive the final stage whose archived flag is not true. One-list boards must retain that list; hidden archived stages do not count as active.
3. **Board-local identity:** board and stage IDs must exist on exactly the requested board; ambiguous duplicate IDs, invalid stages and wrong-board references are rejected. The board must itself be active, and its workspace and non-null project references must exist. Project-less boards are permitted, as are empty-string *legacy project IDs* when present in projects.
4. **Type safety:** existing stage.archived values must be booleans when present. Missing means active. The selected board retains 1–40 stage objects with unique IDs.
5. **Immutability:** all changes clone only state, boards array, target board, target stages array, and the single changed stage object. Other boards, original state, projects, finance and task arrays retain their original object references.
6. **No card mutations:** no deletion, relocation or archive-status changes; task.boardId, listId, status, archived, archivedByBoard and cardOrder remain untouched. Existing archived cards remain archived.
7. **No finance mutations:** project prices, task costs, checklist or named-checklist costs, invoice state, receipts, settings and arbitrary extension metadata remain intact.

## Host/Python compatibility

- **data_model.py:142–170** checks stage IDs/labels and count; does not reject additive stage metadata. **data_model.py:347–376** validates task.listId against the *full* board.stages list, which the module preserves.
- **data_model.py:414–485** retains board stage definitions through legacy normalization. **native_app.py** also retains additive extension fields.
- Currently Python does **not** explicitly validate stage.archived as boolean. JS validates it on the selected board. Before enabling the feature in production, Prime may elect to add optional strict bool validation in Python; do not silently strip unknown fields or replace archived stages.
- Global legacy stages are a different namespace and are intentionally untouched. For pure legacy states without board definitions, normalize/migrate through the existing host first.

## UI integration contract (implemented in source; interactive acceptance pending)

~~~jsx
// Example only. Keep the existing admin/host CAS checks.
const archive = (boardId, listId) => {
  if (!canManage) return;
  changeAdmin(current => archiveListState(
    current, boardId, listId, {canManage}));
};
const restore = (boardId, listId) => {
  if (!canManage) return;
  changeAdmin(current => restoreListState(
    current, boardId, listId, {canManage}));
};
const visibleStages = activeBoard
  ? activeBoardLists(activeBoard)
  : globalStages;
~~~

The source now imports `archiveListState`, `restoreListState`, and `activeBoardLists`. `SettingsPanel` exposes archive/restore controls for board-local stages, and the active board filters archived lists from visible lanes and new-card destinations. This was confirmed by source inspection and a successful build, not a completed interactive workflow test.

**Critical integration rules:**

- Show archived lists in a *separate restore section*, exclude them from normal Kanban lanes, add-card target choices, stage keyboard navigation and drag/drop destinations. Ensure cards still remain discoverable in their archived list and are not silently moved or unarchived.
- **Never persist only visibleStages**. Existing src/features.jsx:37–70 and the App board settings integration edit the stages array; preserve the archived entries when updating/reordering non-archived stages.
- An existing destructive **deleteStage** workflow remains separate. Adding BD13 does not silently replace deletion or fix its existing semantics.
- Persist the entire untouched-finance state with **the host's revision/CAS authorization**, handling conflicts by reloading latest state and reapplying the user's intent. Do not overwrite other clients' changes from a stale UI snapshot.
- Client-side canManage checks are only defense-in-depth. Host LAN should verify admin rights at save time, including after a role downgrade. Avoid applying operations while the board itself is archived.
- If a board is archived, restore that board first before attempting list operations.

## Tests

From the existing project checkout:

~~~powershell
node --test tests/listarchive.test.cjs
~~~

**Verified: 16/16 PASS, 0 failures**, ~225 ms. The synthetic suites cover per-board isolation, retained stage metadata/ordering, financial and nested checklist preservation, archived cards, admin-only gate, last-active-list refusal, idempotency, missing/corrupted project/workspace/board references, duplicate/invalid IDs, legacy empty project reference, JSON persistence roundtrip, and forty archive/restore cycles.

**Not tested:** installed EXE, native Python validator runtime, live LAN ACL or CAS, multi-process filesystem races or UI interaction. Those gates are owned by Prime. Do not claim Trello BD13 UI parity or an RC2 shipment based solely on this module.
