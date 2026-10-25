# CD05 P0 · Reversible card trash (source-integrated contract)

**Status, 2026-10-21:** pure helpers wired into `src/App.jsx`; host validators accept only strict optional boolean `task.deleted`. Isolated Bridge/LAN/SSR contracts passed. An **experimental RC5 EXE** was built and passed basic 9/9 GUI smoke; this is **not** interaction-level Trash acceptance, two-PC LAN evidence, or a stable/full-parity release. Permanent deletion, garbage collection, retention timers and invoice cancellation remain **out of scope**.

## Why this exists

The previous `src/App.jsx` used `tasks.filter(t=>t.id!==id)`, physically dropping the card. Prime replaced that handler with `softDeleteCardState`, added `restoreTrashedCard`, and renders an inline Trash modal. This worker did not edit the existing handler or shared code.

## Public functions

In new `src/cardtrash.js`:

```js
import {softDeleteCardState, restoreDeletedCardState} from './cardtrash.js';

// Manager: explicit strict boolean; the LAN host must still authenticate them.
const trashed = softDeleteCardState(state, cardId, {canManage: true});
const recovered = restoreDeletedCardState(trashed, cardId, {canManage: true});

// Editor: grant must be explicit and scoped to the card's exact project ID.
const editorState = softDeleteCardState(state, cardId, {
  canEdit: true,
  grantedProjectIds: ['authorized-project'],
});
```

- `softDeleteCardState(state, cardId, options)` marks only the matching task with `deleted: true`.
- `restoreDeletedCardState(state, cardId, options)` marks only the matching task with `deleted: false`.
- A card already in the target state returns the original root **by reference** (after permission and reference checks).
- Changing one task creates a new root and a new `tasks` array; it clones only that task's top level. Every other card and every nested checklist, attachment, project, finance, audit, comment, automation, template, board and workspace collection is reused untouched. Deep-frozen input is supported.
- The marker is **independent** from `task.archived` / `task.archivedByBoard`. Restoring an already archived card does not unarchive that card or its board/list.
- An originally absent `deleted` property is considered active. Restoring from trash writes explicit `deleted: false`, so reversibility is semantic, not exact byte-for-byte equality with the original missing property. Other card fields remain equal.
- The helper produces no timestamps, random IDs, finance mutations or other side effects. It does not mutate `state.__localRevision`, `state.__remoteRevision` or `state.__offline`. JSON serialization keeps the boolean marker and all related data.

The helper does **not** physically move cards into another board/list and never drops `task.listId`, `task.status`, `task.cardOrder`, costs, named/flat checklists, assignees, metadata, invoice references, report IDs, attachment references or project prices. The UI can present `task.deleted === true` in a Trash view and exclude those cards from active kanban and ordinary search. A separately archived board/list can remain hidden even after a card is restored from trash.

## Security and reference rules

Pure helper options are *defense-in-depth flags*, **not authentication**. Missing options, a viewer, `canManage: 'true'`, `canEdit: 'true'`, or a bare `canEdit: true` without explicit grants are denied. Strict `canManage === true` allows manager actions; strict `canEdit === true` requires `grantedProjectIds` array containing the exact card `projectId`. The authoritative LAN service **must** recheck role and project grants and refuse replay of foreign project data. A card's own `canManage` or assignees never grant edit permission.

Actions fail closed for:

- missing or ambiguous card/project/board/workspace references and duplicate board list IDs;
- partial `boardId`/`listId` links, unknown board-local list, mismatched board/project assignment;
- archived board or archived workspace for **both** trash and restoration;
- non-boolean optional `task.deleted`, `task.archived`, `task.archivedByBoard`, `board.archived`, `workspace.archived` or stage `archived`;
- invalid IDs or oversized arrays (maximum cards 20,000, projects 2,000, boards 2,000, workspaces 100, lists per board 40).

Board-local **archived lists are allowed**: the list remains a valid retained destination and the card is never moved out of it. Legacy cards with only project ID + global `status` (no `boardId` and no `listId`) work without inventing references. Project-less boards (`board.projectId == null`) are supported, and legacy *empty project IDs* are matched exactly if present. A malformed partial board/list reference must be migrated first.

## Integration contract, implemented parts and remaining gates

1. **Host schema, integrated and focused-tested:** both Python validators now require strict boolean `task.deleted` when present; missing legacy flag is accepted. JSON and SQLite save/reopen tests retain card ID, list, status, costs, project price, actual finance draft invoice and uploaded attachment bytes.
2. **UI, integrated and source/SSR-tested:** the destructive `deleteTask` filter was replaced with the pure transition, a sidebar Trash view and inline restore control were added, and deleted cards are filtered from ordinary Kanban, reporting, planner, suggestions and card editor. Restore is disabled for viewers and archived boards/workspaces. The exact inline Trash JSX is compiled from `App.jsx` and rendered with React server-side in the test harness. These are code/SSR contracts, not interactive browser tests.
3. **CAS and persistence:** the pure function is an isolated state transform, not a persistence operation. Submit its result through existing `Bridge.getStateForUi() / saveState()` with unchanged `__localRevision`, or through LAN `read_state/write_state` using its caller's **original expected revision**. Never read the latest revision just to stamp a stale snapshot or bypass `CONFLICT`. A rejected edit must keep the pending local snapshot safe for manual reload/merge/export. Do not mutate the finance, collab, attachment or automation stores as a side effect of trash/restore.
4. **Finance and attachments:** separate host domains contain issued invoice/payment/audit references and attachment binaries. Preserve those records by keeping the same task ID, not by copying or deleting them. A card's soft deletion does not cancel an invoice, reverse a payment, void costs, or remove an attachment. Finance/attachment APIs must still enforce authenticated ACLs for trashed cards. No physical purge implementation is included.
5. **Remaining acceptance gates:** real browser click/keyboard flows, true multi-process/physical LAN race, installer/EXE smoke, comprehensive cross-module/full suite verification and explicit release acceptance. The current RC3 EXE must not be assumed to include this source change.

## Verified scope

Run in `D:\CoS-Test\madar-desk`:

```powershell
node --test tests/cardtrash.test.cjs
node --test tests/cardtrash_ui_contract.test.cjs
py -3.12 -m unittest tests.test_card_trash_contract -v
```

Verified: 18/18 pure JS tests, 11/11 App JSX static/SSR tests, 10/10 Python Bridge/LAN/validators contract tests. Total **39/39 PASS** in focused runs. The Python fixtures use unique disposable roots with patched `APPDATA`, `LOCALAPPDATA` and `native_app.datadir`; attachment content and finance invoice are real fixture records in temporary storage, not user data. **No real APPDATA, Git, release or Trello reverse engineering were used.**
