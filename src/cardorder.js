/**
 * Pure card ordering for normalized Madar version-1 state.
 * Public API:
 *   getOrderedLaneCards(tasks, boardId, listId)
 *   normalizeCardOrders(state, {boardId?, listId?} = {})
 *   moveCardInState(state, {cardId,toListId,toBoardId?,anchorCardId?,placement?})
 *   prepareCardOrderCAS(state, expectedRevision, move)
 *
 * Optional task.cardOrder is an integer 0..1_000_000 per (boardId,listId).
 * Missing order: explicit values sort first, then legacy cards by original
 * insertion index. No I/O, timestamps, mutation or finance projection.
 */
export const MAX_CARD_ORDER = 1_000_000;
const MAX_TASKS = 20_000; // current native_app.py cap
const MAX_ID_LENGTH = 1_024; // strict mutation-only safety bound

function validId(value, max = 100) {
  return typeof value === 'string' && value.trim().length > 0 &&
    value.length <= max && !/[\u0000-\u001f\u007f]/u.test(value);
}
function assertId(value, name, max = 100) {
  if (!validId(value, max)) throw new TypeError(name + ' must be a nonempty valid ID');
}
function assertObject(value, name) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(name + ' must be an object');
  }
}
function assertOrder(task) {
  if ('cardOrder' in task && (!Number.isSafeInteger(task.cardOrder) ||
    task.cardOrder < 0 || task.cardOrder > MAX_CARD_ORDER)) {
    throw new RangeError('Invalid cardOrder for card ' + task.id);
  }
}
function assertTasks(tasks, {forMutation = false} = {}) {
  if (!Array.isArray(tasks) || tasks.length > MAX_TASKS) {
    throw new TypeError('tasks must be an array of at most ' + MAX_TASKS + ' cards');
  }
  const seen = new Set();
  for (const task of tasks) {
    assertObject(task, 'task');
    // The Python host accepts unique legacy task IDs that are empty, very
    // long, or contain control characters. Reading must not hide or crash on
    // such persisted cards, while ALL write paths remain deliberately strict.
    if (typeof task.id !== 'string') throw new TypeError('task.id must be a string');
    if (forMutation) assertId(task.id, 'task.id', MAX_ID_LENGTH);
    if (seen.has(task.id)) throw new RangeError('Duplicate card id: ' + task.id);
    seen.add(task.id);
    assertOrder(task);
  }
  return tasks;
}
function assertState(state) {
  assertObject(state, 'state');
  assertTasks(state.tasks, {forMutation: true});
  if (!Array.isArray(state.boards)) throw new TypeError('state.boards must be an array');
  if (!Array.isArray(state.stages)) throw new TypeError('state.stages must be an array');
  const boards = new Map();
  for (const board of state.boards) {
    assertObject(board, 'board');
    assertId(board.id, 'board.id');
    if (boards.has(board.id)) throw new RangeError('Duplicate board id: ' + board.id);
    if (!Array.isArray(board.stages)) throw new TypeError('board.stages must be an array');
    const stages = new Set();
    for (const stage of board.stages) {
      assertObject(stage, 'board stage');
      assertId(stage.id, 'board stage.id');
      if (stages.has(stage.id)) throw new RangeError('Duplicate stage: ' + stage.id);
      stages.add(stage.id);
    }
    boards.set(board.id, stages);
  }
  return boards;
}
function validateLane(boards, boardId, listId) {
  assertId(boardId, 'boardId');
  assertId(listId, 'listId');
  if (!boards.has(boardId) || !boards.get(boardId).has(listId)) {
    throw new RangeError('Unknown board/list: ' + boardId + '/' + listId);
  }
}
function laneKey(boardId, listId) {
  return JSON.stringify([boardId, listId]); // collision-free for arbitrary IDs
}
function isInLane(card, boardId, listId) {
  return card.boardId === boardId && card.listId === listId && card.archived !== true;
}
function orderLane(lane) {
  // Stable explicit original index even on older JS sort implementations.
  return lane.map((card, index) => ({card, index})).sort((a, b) => {
    const aSet = Object.prototype.hasOwnProperty.call(a.card, 'cardOrder');
    const bSet = Object.prototype.hasOwnProperty.call(b.card, 'cardOrder');
    if (aSet !== bSet) return aSet ? -1 : 1;
    if (aSet && a.card.cardOrder !== b.card.cardOrder) {
      return a.card.cardOrder - b.card.cardOrder;
    }
    return a.index - b.index;
  }).map(({card}) => card);
}
function laneCards(tasks, boardId, listId) {
  return orderLane(tasks.filter(card => isInLane(card, boardId, listId)));
}
function patchDense(patches, lane) {
  if (lane.length - 1 > MAX_CARD_ORDER) {
    throw new RangeError('Too many cards to assign bounded cardOrder values');
  }
  lane.forEach((card, position) => {
    const prior = patches.get(card.id) || {};
    patches.set(card.id, {...prior, cardOrder: position});
  });
}
function applyPatches(state, patches) {
  let changed = false;
  const tasks = state.tasks.map(task => {
    const update = patches.get(task.id);
    if (!update) return task;
    const keys = Object.keys(update);
    if (keys.every(key => Object.prototype.hasOwnProperty.call(task, key) &&
        Object.is(task[key], update[key]))) return task;
    changed = true;
    return {...task, ...update}; // finance/cost/assignees/comments stay intact
  });
  return changed ? {...state, tasks} : state;
}

/**
 * Read-only sorting accepts host-valid legacy IDs (including "" and >1024
 * chars); duplicates and non-string IDs still fail closed. It never rewrites
 * task objects, even if one of their IDs cannot safely be used for drag/drop.
 * Mutating APIs below retain their strict ID checks.
 */
export function getOrderedLaneCards(tasks, boardId, listId) {
  assertTasks(tasks);
  assertId(boardId, 'boardId');
  assertId(listId, 'listId');
  return laneCards(tasks, boardId, listId);
}

/**
 * Fill dense order for all active lanes, a board, or a specific board/list.
 * Returns input by identity when already normalized. Archived cards stay
 * unchanged until restored and normalized/moved.
 */
export function normalizeCardOrders(state, {boardId, listId} = {}) {
  const boards = assertState(state);
  if (listId !== undefined && boardId === undefined) {
    throw new TypeError('listId requires boardId');
  }
  if (boardId !== undefined) {
    assertId(boardId, 'boardId');
    if (!boards.has(boardId)) throw new RangeError('Unknown boardId');
    if (listId !== undefined) validateLane(boards, boardId, listId);
  }
  const lanes = new Map();
  for (const task of state.tasks) {
    if (task.archived === true || !validId(task.boardId) || !validId(task.listId)) continue;
    if (boardId !== undefined && task.boardId !== boardId) continue;
    if (listId !== undefined && task.listId !== listId) continue;
    validateLane(boards, task.boardId, task.listId);
    const key = laneKey(task.boardId, task.listId);
    if (!lanes.has(key)) lanes.set(key, []);
    lanes.get(key).push(task);
  }
  const patches = new Map();
  for (const lane of lanes.values()) patchDense(patches, orderLane(lane));
  return applyPatches(state, patches);
}

function fallbackStatus(state, listId) {
  // Match boardops.js' legacy status pairing.
  const globalStages = state.stages;
  if (globalStages.some(stage => stage?.id === listId)) return listId;
  if (globalStages.some(stage => stage?.id === 'inbox')) return 'inbox';
  const first = globalStages[0]?.id;
  if (!validId(first)) throw new RangeError('No legacy stage for target list');
  return first;
}

/**
 * Reposition one active card in its board, including cross-list placement.
 * placement = before/after (require anchorCardId) or start/end (no anchor).
 * Cross-BOARD moves intentionally refuse; those require explicit migration
 * of board-specific labels and custom fields, not just card ordering.
 * Only source/destination lanes are renumbered.
 */
export function moveCardInState(state, {
  cardId, toBoardId, toListId, anchorCardId = null, placement = 'end'
} = {}) {
  const boards = assertState(state);
  assertId(cardId, 'cardId', MAX_ID_LENGTH);
  assertId(toListId, 'toListId');
  if (!['before', 'after', 'start', 'end'].includes(placement)) {
    throw new RangeError('placement must be before/after/start/end');
  }
  if (['before', 'after'].includes(placement)) {
    assertId(anchorCardId, 'anchorCardId', MAX_ID_LENGTH);
  } else if (anchorCardId !== null && anchorCardId !== undefined) {
    throw new TypeError('anchorCardId is only permitted for before/after');
  }
  const moving = state.tasks.find(card => card.id === cardId);
  if (!moving || moving.archived === true) throw new RangeError('Unknown or archived cardId');
  const boardId = toBoardId === undefined ? moving.boardId : toBoardId;
  validateLane(boards, moving.boardId, moving.listId);
  validateLane(boards, boardId, toListId);
  if (boardId !== moving.boardId) {
    throw new RangeError('Cross-board moves require a separate metadata migration');
  }
  const source = laneCards(state.tasks, moving.boardId, moving.listId)
    .filter(card => card.id !== moving.id);
  const sameLane = moving.listId === toListId;
  const target = sameLane ? source.slice() : laneCards(state.tasks, boardId, toListId);
  let index;
  if (placement === 'start') index = 0;
  else if (placement === 'end') index = target.length;
  else {
    if (anchorCardId === moving.id && sameLane) return state;
    const anchorIndex = target.findIndex(card => card.id === anchorCardId);
    if (anchorIndex < 0) throw new RangeError('anchorCardId must be an active target-list card');
    index = anchorIndex + (placement === 'after' ? 1 : 0);
  }
  target.splice(index, 0, moving);
  const patches = new Map();
  patchDense(patches, target);
  if (!sameLane) {
    patchDense(patches, source);
    const prior = patches.get(moving.id) || {};
    patches.set(moving.id, {...prior, boardId, listId: toListId,
      status: fallbackStatus(state, toListId)});
  }
  return applyPatches(state, patches);
}

/**
 * Prepare a whole-state optimistic concurrency save; this does NOT persist.
 * Prime must use expectedRevision in the existing authoritative LAN/Bridge
 * CAS path, and on conflict reload/reapply instead of overwriting newer data.
 */
export function prepareCardOrderCAS(state, expectedRevision, move) {
  if (typeof expectedRevision !== 'string' ||
      !/^[0-9a-f]{64}$/i.test(expectedRevision)) {
    throw new TypeError('expectedRevision must be the host SHA-256 revision');
  }
  return {nextState: moveCardInState(state, move), expectedRevision};
}
