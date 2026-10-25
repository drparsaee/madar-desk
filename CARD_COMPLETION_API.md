# Madar Desk: workspace and card completion contracts

## Scope and persistence

The extension works with existing version-1 JSON state. `data_model.normalize_plus()`
and `data_model.validate_plus()` remain the authoritative additive schema. `native_app.py`
and `lan.py` were not modified. Existing task costs, flat checklists, project pricing,
board membership, and finance ledgers are not rewritten by these APIs.

Existing host-side `native_app.is_valid(state)` delegates to `validate_plus()` and
therefore checks the additional `cover` schema. Covers are **solid color only**:

```json
{"cover":{"type":"color","color":"#5672CA","size":"strip"}}
```

`cover: null` or omitted is also valid. Only `strip` or `full` sizes and strict
`#RRGGBB` colors are accepted. URLs, `data:` URI values, images, arbitrary CSS,
gradients, SVG and HTML are not a supported cover format. React renders strings
as escaped text and uses validated colors as `backgroundColor`, without unsafe
HTML insertion. Existing unknown properties are preserved by normalization;
**unknown properties are not automatically validated or authorized**.

## Python workspace operations (pure functions)

```python
from data_model import (
    create_workspace, rename_workspace, set_workspace_archived,
    move_board_workspace, delete_empty_workspace,
)

new_state = create_workspace(state, "ws-20261021-1", "تیم تولید")
new_state = rename_workspace(new_state, "ws-20261021-1", "اجرای سفارش")
new_state = move_board_workspace(new_state, "board-id", "ws-20261021-1")
new_state = set_workspace_archived(new_state, "ws-20261021-1", True)
new_state = set_workspace_archived(new_state, "ws-20261021-1", False)
# Deletion requires an empty workspace with no board references.
new_state = delete_empty_workspace(new_state, "ws-20261021-1")
```

Each operation normalizes/clones/validates before returning, never mutating the
argument. The caller supplies a unique stable ID at creation, normally generated
in the application. `delete_empty_workspace` refuses any referenced workspace
and never cascades board/card removal. Moving a board changes only its
`workspaceId`. Archiving the last active workspace is rejected. Host write
operations must continue to apply existing authorization and transaction/CAS
checks. These functions **do not add a LAN endpoint or authorization gate**.

## React: import and exact `App.jsx` integration recipe

The following is for Prime to integrate; `App.jsx` is outside this worker's edits.

```jsx
import {
  CardChecklists, CardCover, CardCustomFields, BoardFieldEditor,
  editCardChecklists, normalizeCover, editCardFieldValues, editBoardFields,
} from './cardextras.jsx';
```

Inside the existing `TaskEditor`, its `update` function currently sends a
partial task patch through `onUpdate(task.id, patch)` and checks `canEdit`.
Keep that authorization check in the host and editor. Mount:

```jsx
const activeBoard = boards.find(b => b.id === task.boardId);
<CardCover task={task} disabled={!canEdit} onChange={update}/>
<CardChecklists task={task} disabled={!canEdit} hideLegacy={true} onChange={update}/>
{activeBoard && <CardCustomFields
  task={task} board={activeBoard} calendar={calendar}
  disabled={!canEdit} onChange={update}/>}
```

`hideLegacy={true}` keeps the existing flat legacy checklist editor visible and
suppresses its duplicate named group. New-group creation remains available.
With `hideLegacy={false}` the legacy named group is also displayed and editable.
`CardChecklists.onChange` sends **both** `{checklists, checklist}` in the same
patch, so the current Windows editor's legacy flat checklist mirror stays
consistent. In the editor, either replace the old flat checklist section with
`CardChecklists`, or ensure all old flat-checklist edits also mirror the
`checklist-legacy` group. `cardChecklistGroups()` also treats the current flat
list as authoritative when compiling an edit, matching the current host
normalizer and preventing a stale named copy from undoing financial edits.
An alternative for the old editor is to call
`editCardChecklists(task, command)` in its change handlers.

For board field definitions, mount a separate admin-only board settings section:

```jsx
{canManage && activeBoard && <BoardFieldEditor
  board={activeBoard} tasks={tasks} templates={data.templates || []}
  onChange={updatedBoard => changeAdmin(state => ({
    ...state,
    boards: state.boards.map(board => board.id === updatedBoard.id ? updatedBoard : board)
  }))}/>}
```

The editor allows adding `text`, `number`, `date`, `checkbox` or `select`
definitions, renaming definitions, and removing unused definitions. Removing a
definition referenced by any task or template is refused. The command helper
`editBoardFields(board, tasks, templates, command, idFactory?)` is independently
testable. `CardCustomFields` edits per-card `customFieldValues` with typed
input; date display follows `calendar` (Jalali/Gregorian), while persisted dates
remain Gregorian `YYYY-MM-DD` as required by the model.

`CardCover.onChange` sends `{cover: null}` or `{cover:{type:'color',color,size}}`.
The cover display may be added to the board's task card using the same validated
`normalizeCover(task.cover)` and an inline `backgroundColor` style.

### Checklist commands

```js
editCardChecklists(task, {type:'add-group',name:'کنترل کیفیت'});
editCardChecklists(task, {type:'rename-group',groupId:'qa',name:'QC'});
editCardChecklists(task, {type:'remove-group',groupId:'qa'});
editCardChecklists(task, {type:'add-item',groupId:'qa',text:'بررسی برش'});
editCardChecklists(task, {type:'rename-item',groupId:'qa',itemId:'step',text:'کنترل رنگ'});
editCardChecklists(task, {type:'toggle-item',groupId:'qa',itemId:'step'});
editCardChecklists(task, {type:'move-item',groupId:'qa',itemId:'step',direction:'up'});
editCardChecklists(task, {type:'remove-item',groupId:'qa',itemId:'step'});
```

The factory argument is optional. Added items initialize with `cost:0` and
`done:false`. Edits preserve existing item cost, cost category and cost date.
Deleting charged items or groups is intentionally blocked to prevent silent
loss of recorded financial context. If a business workflow must retire a paid
step, it needs a separate auditable financial action. Only `checklist-legacy`
is synchronized back to the flat `task.checklist`; additional groups are not
silently added to the existing expense summation. Financial overview currently
uses the flat legacy checklist as its recognized cost source, so this UI does
not claim separate named-group costs enter profit calculations.

## Tests and integration boundaries

```powershell
python -m unittest discover -s tests -p test_card_completion.py -v
node --test tests/cardextras.test.cjs
```

`tests/test_card_completion.py` checks workspace immutability, references,
cost preservation, color-only cover schema, native `is_valid` acceptance and
normalization idempotence. `tests/cardextras.test.cjs` checks checklist
operations, cost guards, custom fields, board definitions, cover validation and
server-side escaped rendering. Neither modifies real APPDATA. The new JS
test should be added to `package.json`'s `npm test` script by Prime.

Not covered here: live UI click flows, authorization policy on a new workspace
endpoint, financial posting for additional named groups, release packaging and
multiclient synchronization. These require Prime integration and targeted
host tests before a production release.
