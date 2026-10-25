# M03 / TR-03 · Indexed board visibility and synthetic performance evidence

**Date:** 2026-10-21  
**Workspace:** `D:\CoS-Test\madar-desk`  
**Status:** indexed view and bounded progressive lane helper implemented independently; focused tests **PASS**; **not yet connected to App.jsx or an installed EXE**.

## Scope and source bottleneck

The competitor/backlog report `COMPETITOR_WEAKNESSES_TO_MADAR_STRENGTHS_2026-10-21.md` identifies TR-03 / M03 as the large-board weakness: the current `src/App.jsx` (roughly lines 525–540 and 842–849) checks `workspaceBoards.some()` and `boards.find()` for each task and then filters or sorts again per rendered Kanban column. It ultimately renders **every** `<TaskCard />` for a long lane. This is an algorithmic and DOM workload risk, **not** a measured FPS regression.

This tranche adds **only**:

1. `src/board_performance.js`: a pure indexed visibility/filter/group layer, plus bounded progressive **data paging**.
2. `tests/board_performance.test.cjs`: functional, security/ACL-scope, immutability, legacy, order, malformed input and 10k-card tests.
3. `scripts/benchmark_large_board.cjs`: generated-only Node measurement for 1k, 5k and 10k cards.
4. `M03_PERFORMANCE.md`: integration contract and measured evidence.

No edits were made to `App.jsx`, backend files, any existing test, user APPDATA, Git or releases.

## Public API and data/authorization contract

```js
import {createBoardPerformanceIndex} from './board_performance.js';

// state must come from Bridge/LAN after host-side role/project authorization
// and sensitive financial redaction. The IDs below MUST be host-visible.
const view = createBoardPerformanceIndex(state, {
  permittedProjectIds: state.projects.map(project => project.id),
});

// One workspace / project / board, no repeated O(boards) lookup per card:
const visible = view.selectActiveCards({
  workspaceId: activeWorkspaceId,
  projectId: selected === 'all' ? undefined : selected,
  boardId: activeBoard?.id,
  highOnly: filter === 'high',
  withReports: filter === 'with-reports',
  matchIds: optionalAuthorizedSearchIds, // Set, not a full-state query
  predicate: card => matchAdvanced(card, advanced, activeBoard?.id),
});

// Group once, rather than repeating whole-list scans on every board column.
const groups = view.groupActiveCards({
  workspaceId: activeWorkspaceId,
  boardId: activeBoard.id,
  projectId: selected,
  matchIds: optionalAuthorizedSearchIds,
});
const lane = groups.get(stage.id) || [];

// Optional unfiltered progressive *data* page (NOT virtual DOM rendering):
const first = view.getLanePage(activeBoard.id, stage.id, {
  offset: 0, limit: 60,
});
// first = {cards, total, nextOffset, hasMore}
// getOrderedLaneCards(boardId, listId) returns a new array in cardOrder order.
```

**Important:** pass `permittedProjectIds` explicitly from the authenticated, already redacted view. No bare call can default to access-all. The allowlist is defense in depth, **not a replacement** for LAN server ACL. Unknown/unauthorized project IDs, boards and task IDs produce no result even when guessed in filters or search-ID sets. Authorized cards are returned by **original object reference**; the index does not clone or edit cards. It never reads or exposes invoice/ledger/price fields as a separate search index. An authorized card can itself contain task costs, so the backend must still enforce the expected reader-level cost policy before sending it.

Creation costs roughly one scan of projects, workspaces, boards and tasks, with one sort per populated board lane; selection uses the smallest available indexed bucket (board, workspace, project, priority or status) and intersects all supplied constraints. All changes to permissions, card data, lists, board/workspace archived state, or host revision require a **new index**. Never reuse an old index after a state/permission change or after a stale-CAS conflict. No module-level cache and no index persistence.

Index visibility requires a known permitted project, active board, active workspace and active board-local list. `task.deleted`, `task.archived` and `task.archivedByBoard` must not be true. A card on an archived list stays in raw state but is not shown. Project-less boards are supported if the actual card's project ID is permitted. A fully unmigrated boardless v1 state is supported using its global `status` and a logical `workspace-legacy` bucket; partial/orphan board references are not guessed. Exact historical string card/project IDs survive without coercion. The implementation rejects duplicate accessible card IDs and duplicate board/workspace/stage references as well as malformed boolean flags and cardOrder values, rather than arbitrarily choosing one.

The order contract matches `src/cardorder.js`: `cardOrder` integers 0..1,000,000 first, ascending; equal values stable by original insertion; legacy missing order last, stable. For the global unscoped view, group keys remain legacy `task.status`. For an active board, group keys are **board-local** `task.listId`. Query selection preserves source insertion order; grouped board lanes preserve cardOrder order. The index respects host-aligned limits of 20k tasks, 2k boards/projects, 100 workspaces, 40 stages per board and 300 cards per page.

## Safe Prime integration guidance

The **current `App.jsx` is unchanged** by this worker. Prime can integrate later as follows:

1. After loading the authenticated `data` and `projects`, memoize the index by the current immutable `tasks`, `boards`, `workspaces`, `projects` and granted-project scope. Do not preserve it through a role/project/ACL switch, task edit, LAN refresh or CAS conflict. The desktop Bridge and LAN remain the sole authority.
2. Replace repeated per-card board/workspace linear lookups in `filtered` with `view.selectActiveCards(...)`. Keep `filterTasks`'s full Persian query language via `searchplus.js`: run it **only over the index's already authorized candidates** and pass back a `Set` of matching IDs. This tranche does **not** replace advanced text search parsing or assert an indexed inverted-text search.
3. Build `groupActiveCards` **once per filtered view**. Use `groups.get(stage.id) || []` for each Kanban lane. `getOrderedLaneCards` and `getLanePage` are optimized for unfiltered lane access; **do not** replace filtered groups with an unfiltered page or inadvertently make hidden cards visible.
4. For a large active lane, render only a bounded initial slice and increment the rendered count as the user scrolls. `getLanePage` returns data windows (60 by default, maximum 300); this is **not actual UI virtualization**. Prime should implement scroll/keyboard/drag-and-drop/accessible focus behavior and preserve the **full lane** for keyboard anchor and drag order semantics. Never use a page subset as a replacement for authoritative tasks, or for counts, finance totals or saved state.
5. Guard filter callbacks and potentially stale search results. Only use `state.projects`/users/stages from the host-allowed snapshot when building a query; no finance/price aggregation in this module. Let `matchAdvanced` filter data after authorization; no full source-state search to obtain hidden IDs.

## Focused correctness tests

```powershell
node --test tests/board_performance.test.cjs
```

Focused result: **16/16 PASS**. A related regression run (`board_performance`, `cardorder`, `listarchive`, `cardtrash`) was **69/69 PASS**. Tests include frozen input and original reference identity, no data change, permission-filtered cross-board/workspace selection, archived list/workspace/board/card and Trash exclusion, stable cardOrder ties/legacy behavior compared with `cardorder.js`, project-less/boardless legacy states, malformed/duplicate identifiers, bounded page sizes, and 10k synthetic cards.

## Synthetic benchmark (not FPS)

Command:

```powershell
node --expose-gc scripts/benchmark_large_board.cjs
```

Environment on this run: **Node v26.8.1, Windows x64, GC exposed**. The script generates 24 boards in two workspaces across three synthetic projects, with **60%** of all cards on one board, plus minimal checklists, dummy costs, reports and archived/deleted flags. Two projects are permitted; each input size is measured with **nine** build/query/group/page samples. No real data, disk state, browser or animation is used. Values below are milliseconds (sample medians), not animation rates:

| Synthetic cards | Largest board | Index build | Workspace/project/high filter | Group one board | Slice 60 lane cards |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 600 | 1.302 | 0.057 | 0.197 | 0.010 |
| 5,000 | 3,000 | 3.781 | 0.242 | 0.889 | 0.005 |
| 10,000 | 6,000 | 6.904 | 0.438 | 1.864 | 0.004 |

Memory snapshots, **MiB from `process.memoryUsage()`**, after synthetic input preparation versus after 9 runs. These reflect the whole Node process and temporary/JIT/garbage-collection effects, **not the precise size of one index**:

| Cards | Heap before | Heap after | Reported delta | RSS before | RSS after |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 5.639 | 7.296 | +1.658 | 70.027 | 76.793 |
| 5,000 | 8.279 | 13.075 | +4.796 | 74.504 | 90.063 |
| 10,000 | 12.930 | 27.028 | +14.098 | 89.938 | 121.395 |

The script also logs individual-group maximum timings as JSON for inspection. CPU, OS background load and GC can materially alter numbers. The numbers are not a controlled comparison with Trello or with the prior App.jsx implementation.

**Acceptance still outstanding:** integrate into React, implement actual incremental or virtualized DOM rendering, conduct controlled 1k/5k/10k load tests on the *target Windows PC* with Chromium Performance/React Profiler (initial load, input-to-render latency, keyboard navigation, smooth scroll and memory), enforce role changes/physical multi-client tests, and run regression/EXE acceptance. **No FPS target is claimed achieved here.**

## M03 follow-up · bounded accessible progressive lane state

**New files:** `src/board_progressive.js` and `tests/board_progressive.test.cjs`. No existing UI/backend files, storage, APPDATA, Git or release were changed by this worker. This extends **data paging / render model**, not a ready-to-mount React component; Prime still owns `App.jsx` integration, real DOM scroll measurements and keyboard handlers.

### API / integration contract

```js
import {
  createProgressiveLaneState,
  captureProgressiveLaneScroll,
  advanceProgressiveLaneState,
  reconcileProgressiveLaneState,
  revealProgressiveLaneCard,
  progressiveLaneNeighbor,
  getProgressiveLaneView,
} from './board_progressive.js';

// From createBoardPerformanceIndex(state, {permittedProjectIds}) after
// host LAN ACL and finance redaction. Never pass unfiltered raw tasks.
const lane = permittedIndex.groupActiveCards({
  boardId: activeBoard.id, workspaceId: activeWorkspaceId,
  projectId: selected, matchIds: authorizedMatches,
}).get(stage.id) || [];

let pager = createProgressiveLaneState(lane, {
  pageSize: 48, maxRendered: 240,
});

// Before loading the next page, optionally capture actual DOM geometry:
// cardId = FIRST visible rendered card (not simply the first data item).
pager = captureProgressiveLaneScroll(lane, pager, {
  cardId: firstVisibleCardId,
  offsetPx: firstVisibleCardTopRelativeToLaneScrollViewport,
  scrollTopPx: laneScrollElement.scrollTop,
});
pager = advanceProgressiveLaneState(lane, pager, 'next');
// OR 'previous', to revisit the trimmed head of an already long lane.

// On any new authoritative data, filter or permission scope:
// FIRST regenerate the host-authorized lane, THEN reconcile the old pager.
pager = reconcileProgressiveLaneState(newPermittedLane, pager);

// Keyboard/search jump to a card, only if it is in the permitted lane:
pager = revealProgressiveLaneCard(newPermittedLane, pager, cardId);

// Across a page boundary, get neighbors from the COMPLETE permitted lane,
// never the sliced rendered list:
const nextCard = progressiveLaneNeighbor(newPermittedLane, cardId, +1);

const ui = getProgressiveLaneView(newPermittedLane, pager, {
  regionId: 'boardLaneDoing', // unique, stable, safe DOM id; use React useId
  laneLabel: stage.label,
});
// Render ui.entries ONLY (each {card,key,index,ariaPosInSet,ariaSetSize}).
// Use key, role="listitem", aria-posinset / aria-setsize for each card.
// Render region with id, role="list" and accessible label.
// Use actual HTML BUTTONs with ui.controls.previous / ui.controls.next
// aria-label and aria-controls; wire to advanceProgressiveLaneState.
// Put ui.liveStatus in a polite aria-live region after a page change.
// After React commit, execute ui.scrollRestore and ui.focusTarget ONCE,
// preferably in useLayoutEffect keyed to the pager transition.
```

**Bounds:** max source lane **20,000**, default page **48**, maximum page **100**, default render cap **240**, absolute render cap **300**. Appending the next page trims the oldest rendered items if at the cap; loading a previous page trims from the far end. Global counts, positions and keyboard neighbors **always** refer to the complete permitted/filtered lane. Rendering hundreds rather than thousands of cards is a DOM *budget*, not proof of 60 FPS or a virtualization claim.

**ARIA contract:** item.index is the original **zero-based index in the complete filtered lane**, `ariaPosInSet` is its **one-based** position, `ariaSetSize` is the complete permitted lane length. The widget supplies explicit text, `aria-controls` and `type="button"` for previous/next load actions plus a localized Persian polite-live status string. Parent must render them as actual keyboard-usable buttons, not on-hover divs. `focusTarget.cardId` is the first newly added card when paging, or the requested card on a jump; use DOM refs keyed by the *unchanged card ID*. `preventScroll:true` means the parent may restore an anchor before separately using `scrollIntoView` for a keyboard focus destination when necessary. Stable React keys must use card.id, not the current page-relative index.

**Scroll contract:** `captureProgressiveLaneScroll` only accepts an ID already rendered in the **current permitted window**, plus measured card-top offset and scrollTop; no hidden or foreign ID can be captured. `getProgressiveLaneView().scrollRestore` gives `{cardId,offsetPx,fallbackScrollTopPx,strategy}`: after DOM commit, locate the anchor DOM element again and adjust scrollTop by the difference in the card's viewport-relative top (or use the fallback if still valid). On inserts/reorders a reconcile preserves the anchor's *ID*, prior page-relative index and pixel offset if it remains authorized. On deletion/revocation it selects a safe currently permitted fallback and sets `anchorLost:true`; old IDs and measurements are discarded. Bounded trimming can necessarily evict an old anchor; UI must respect the explicit lost-anchor signal rather than promising perfect scroll continuity.

**Security/lifecycle:** all functions consume **already host-scoped, filtered arrays**. The helper performs no authorization and cannot resurrect records: changes in grants, filters, board/list/archive, trash, CAS revision or workspace MUST create a fresh authorized lane and call reconcile; for a wholly different board/user, **reset** with createProgressiveLaneState instead of retaining a previous user's cursor. Old pagers contain only ID/offset/position metadata, not card cost or invoice payloads. Reconciliation clears a forbidden anchor/focus ID; on an empty authorized lane the view is empty. The helper never changes source task objects, finance data, list IDs or saved state.

**Remaining implementation:** Prime must wire per-(board,list,filter/scope) state in `App.jsx`, preserve existing drag-drop and full-lane keyboard navigation, capture actual scroll geometry, handle post-commit focus/scroll once per action, and test page-back/forward in a live Chromium environment. Consider a per-lane `useRef` map keyed by board + list plus authenticated scope, with state reset on permission changes. Avoid auto-load on every scroll event; an explicit load-more control is the accessible fallback. The module currently performs full-lane ID validation on each action for deterministic fail-closed behavior; it is not a zero-cost per-frame scroll handler.

### Focused validation

```powershell
node --test tests/board_progressive.test.cjs
node --test tests/board_progressive.test.cjs tests/board_performance.test.cjs tests/cardorder.test.cjs tests/listarchive.test.cjs tests/cardtrash.test.cjs
```

Verified on 2026-10-21: **19/19** dedicated progressive tests PASS and **88/88** combined M03 + cardorder + listarchive + cardtrash tests PASS (Node v26.8.1 Windows x64). The progressive tests include repeated bounded 10k paging, exact absolute indexes, ARIA SSR list and buttons, next/previous slicing, anchor retention/loss, filtered-lane insertion/deletion, permission-scope revocation, legacy weird IDs, out-of-window keyboard neighbors, malformed/oversized state, and 200 transitions preserving identical cost/checklist/invoice references. **No FPS or layout measurement is asserted.**
