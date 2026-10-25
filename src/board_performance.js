/**
 * M03 read-only board/workspace visibility index for large Madar boards.
 *
 * The builder MUST be supplied project IDs from the authenticated, host-
 * redacted view. Never use task-supplied roles or cost fields for authorization.
 * All returned cards are identical references to permitted input cards. The
 * index does not project, clone, mutate or scan invoice/finance records.
 *
 * Rebuild on every authoritative immutable state/tasks/boards/workspaces
 * replacement. Do not reuse a cached index after a card/ACL/board edit.
 */

export const BOARD_INDEX_LIMITS = Object.freeze({
  tasks: 20_000, projects: 2_000, boards: 2_000, workspaces: 100,
  stages: 40, page: 300,
});

const LEGACY_WORKSPACE = 'workspace-legacy';
const MAX_ORDER = 1_000_000;
const EMPTY = Object.freeze([]);

function array(value, name, cap) {
  if (!Array.isArray(value) || value.length > cap)
    throw new TypeError(name + ' must be an array with at most ' + cap + ' items');
  return value;
}
function obj(value, name) {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new TypeError(name + ' must be an object');
  return value;
}
function textId(value, name) {
  // Historical project/task IDs may be empty, long and have control chars.
  // Do not normalize them or use separator-concatenated cache keys.
  if (typeof value !== 'string') throw new TypeError(name + ' must be a string');
  return value;
}
function flag(record, name, field) {
  if (Object.prototype.hasOwnProperty.call(record, field) &&
      typeof record[field] !== 'boolean')
    throw new TypeError(name + '.' + field + ' must be boolean');
}
function add(map, key, value) {
  const group = map.get(key);
  if (group) group.push(value);
  else map.set(key, [value]);
}
function ordered(cards) {
  // Identical cardOrder semantics to src/cardorder.js: explicit ascending,
  // stable ties by insertion; missing order comes last in insertion order.
  return cards.map((card, ordinal) => ({card, ordinal})).sort((a, b) => {
    const aOrder = Object.prototype.hasOwnProperty.call(a.card, 'cardOrder');
    const bOrder = Object.prototype.hasOwnProperty.call(b.card, 'cardOrder');
    if (aOrder !== bOrder) return aOrder ? -1 : 1;
    if (aOrder && a.card.cardOrder !== b.card.cardOrder)
      return a.card.cardOrder - b.card.cardOrder;
    return a.ordinal - b.ordinal;
  }).map(({card}) => card);
}
function parsePermission(ids) {
  const list = array(ids, 'permittedProjectIds', BOARD_INDEX_LIMITS.projects);
  const result = new Set();
  for (const id of list) {
    textId(id, 'permittedProjectIds item');
    result.add(id);
  }
  return result;
}
function selected(arrayMap, key) { return arrayMap.get(key) || EMPTY; }

/**
 * createBoardPerformanceIndex(state, {permittedProjectIds})
 *
 * The returned object has only readers, no full source state reference.
 * Authentication/finance redaction MUST occur on the host before this call.
 * A caller-supplied allowlist is defense in depth, not proof of identity.
 */
export function createBoardPerformanceIndex(state, {permittedProjectIds} = {}) {
  obj(state, 'state');
  const grants = parsePermission(permittedProjectIds);
  const tasks = array(state.tasks, 'tasks', BOARD_INDEX_LIMITS.tasks);
  const boards = array(state.boards ?? [], 'boards', BOARD_INDEX_LIMITS.boards);
  const workspaces = array(state.workspaces ?? [], 'workspaces', BOARD_INDEX_LIMITS.workspaces);
  const globalStages = array(state.stages ?? [], 'stages', BOARD_INDEX_LIMITS.stages);
  const allowedProjects = new Set();
  for (const project of array(state.projects, 'projects', BOARD_INDEX_LIMITS.projects)) {
    obj(project, 'project');
    const id = textId(project.id, 'project.id');
    if (grants.has(id)) {
      if (allowedProjects.has(id)) throw new RangeError('Duplicate permitted project ID');
      allowedProjects.add(id);
    }
  }

  const workspaceById = new Map();
  for (const workspace of workspaces) {
    obj(workspace, 'workspace');
    const id = textId(workspace.id, 'workspace.id');
    if (workspaceById.has(id)) throw new RangeError('Duplicate workspace ID');
    flag(workspace, 'workspace', 'archived');
    workspaceById.set(id, workspace);
  }

  const boardById = new Map();
  const activeBoards = new Map();
  for (const board of boards) {
    obj(board, 'board');
    const id = textId(board.id, 'board.id');
    if (boardById.has(id)) throw new RangeError('Duplicate board ID');
    boardById.set(id, board);
    flag(board, 'board', 'archived');
    const workspace = workspaceById.get(board.workspaceId);
    if (!workspace || workspace.archived === true || board.archived === true)
      continue;
    if (board.projectId != null && !allowedProjects.has(board.projectId))
      continue;
    const stageIds = new Set();
    const liveStageIds = new Set();
    const stages = array(board.stages, 'board.stages', BOARD_INDEX_LIMITS.stages);
    for (const stage of stages) {
      obj(stage, 'stage');
      const stageId = textId(stage.id, 'stage.id');
      if (stageIds.has(stageId)) throw new RangeError('Duplicate stage ID');
      flag(stage, 'stage', 'archived');
      stageIds.add(stageId);
      if (stage.archived !== true) liveStageIds.add(stageId);
    }
    activeBoards.set(id, {workspaceId: board.workspaceId,
                          projectId: board.projectId, liveStageIds});
  }

  const byBoard = new Map();
  const byWorkspace = new Map();
  const byProject = new Map();
  const byStatus = new Map();
  const byPriority = new Map();
  const byBoardLane = new Map(); // board ID -> (list ID -> ordered refs)
  const globalStageIds = new Set(globalStages.map(stage => stage?.id));
  const legacyOnly = boards.length === 0;
  const all = [];
  const usedTaskIds = new Set();

  for (const task of tasks) {
    obj(task, 'task');
    textId(task.id, 'task.id');
    if (!allowedProjects.has(task.projectId)) continue; // no leaked refs
    if (usedTaskIds.has(task.id)) throw new RangeError('Duplicate accessible card ID');
    usedTaskIds.add(task.id);
    for (const field of ['archived', 'deleted', 'archivedByBoard'])
      flag(task, 'task', field);
    if (task.archived === true || task.deleted === true ||
        task.archivedByBoard === true) continue;
    if (Object.prototype.hasOwnProperty.call(task, 'cardOrder') &&
        (!Number.isSafeInteger(task.cardOrder) || task.cardOrder < 0 ||
         task.cardOrder > MAX_ORDER))
      throw new RangeError('Invalid cardOrder');

    let workspaceId = LEGACY_WORKSPACE;
    if (task.boardId != null || task.listId != null) {
      if (task.boardId == null || task.listId == null) continue;
      const board = activeBoards.get(task.boardId);
      if (!board || !board.liveStageIds.has(task.listId) ||
          (board.projectId != null && board.projectId !== task.projectId))
        continue;
      workspaceId = board.workspaceId;
      if (!byBoardLane.has(task.boardId)) byBoardLane.set(task.boardId, new Map());
      add(byBoardLane.get(task.boardId), task.listId, task);
      add(byBoard, task.boardId, task);
    } else {
      // The unmigrated v1 view has no board. Once ANY boards exist, detached
      // cards are not silently attached to a guessed board or workspace.
      if (!legacyOnly || !globalStageIds.has(task.status)) continue;
    }
    all.push(task);
    add(byWorkspace, workspaceId, task);
    add(byProject, task.projectId, task);
    add(byStatus, task.status, task);
    add(byPriority, task.priority, task);
  }
  for (const lanes of byBoardLane.values())
    for (const [id, group] of lanes) lanes.set(id, ordered(group));

  function base(options = {}) {
    obj(options, 'options');
    // A query may only narrow original permissions; it cannot authorize a
    // foreign project, even if a caller knows its card/board identifiers.
    if (options.projectId !== undefined) {
      textId(options.projectId, 'projectId');
      if (!allowedProjects.has(options.projectId)) return EMPTY;
    }
    if (options.boardId !== undefined) {
      textId(options.boardId, 'boardId');
      return selected(byBoard, options.boardId);
    }
    if (options.workspaceId !== undefined) {
      textId(options.workspaceId, 'workspaceId');
      return selected(byWorkspace, options.workspaceId);
    }
    if (options.projectId !== undefined) return selected(byProject, options.projectId);
    if (options.priority !== undefined) return selected(byPriority, options.priority);
    if (options.status !== undefined) return selected(byStatus, options.status);
    return all;
  }
  function passes(card, options, matchIds) {
    if (options.projectId !== undefined && card.projectId !== options.projectId) return false;
    if (options.workspaceId !== undefined) {
      const board = activeBoards.get(card.boardId);
      if ((board?.workspaceId || LEGACY_WORKSPACE) !== options.workspaceId) return false;
    }
    if (options.boardId !== undefined && card.boardId !== options.boardId) return false;
    if (options.listId !== undefined &&
        (options.boardId === undefined
          ? card.status !== options.listId : card.listId !== options.listId)) return false;
    if (options.status !== undefined && card.status !== options.status) return false;
    if (options.priority !== undefined && card.priority !== options.priority) return false;
    if (options.highOnly && card.priority !== 'high') return false;
    if (options.withReports && (!Array.isArray(card.reports) || !card.reports.length)) return false;
    if (matchIds && !matchIds.has(card.id)) return false;
    return !options.predicate || options.predicate(card) === true;
  }
  function checkOptions(options) {
    obj(options, 'options');
    if (options.predicate !== undefined && typeof options.predicate !== 'function')
      throw new TypeError('predicate must be a function');
    if (options.matchIds !== undefined &&
        !(options.matchIds instanceof Set))
      throw new TypeError('matchIds must be a Set');
    for (const key of ['highOnly', 'withReports'])
      if (options[key] !== undefined && typeof options[key] !== 'boolean')
        throw new TypeError(key + ' must be boolean');
    for (const key of ['boardId', 'workspaceId', 'projectId', 'listId','status','priority'])
      if (options[key] !== undefined) textId(options[key], key);
  }

  /**
   * Scans the smallest applicable bucket. Output order is original task order.
   * Callers can supply matchIds from host-safe searchplus.filterTasks on the
   * index's authorized candidates, NEVER on the full unredacted task list.
   */
  function select(options = {}) {
    checkOptions(options);
    return base(options).filter(card => passes(card, options, options.matchIds));
  }
  function lane(boardId, listId) {
    textId(boardId, 'boardId'); textId(listId, 'listId');
    return selected(byBoardLane.get(boardId) || new Map(), listId).slice();
  }
  function group(options = {}) {
    checkOptions(options);
    const source = select(options);
    const result = new Map();
    // Stable order follows cardOrder semantics, unlike repeat scanning one
    // full filtered list per stage in App.jsx. Complexity O(n + Σ k log k).
    for (const card of source) add(result,
      options.boardId === undefined ? card.status : card.listId, card);
    if (options.boardId !== undefined) {
      const ranks = byBoardLane.get(options.boardId) || new Map();
      for (const [listId, cards] of result) {
        const rank = new Map(selected(ranks, listId).map((card,i) => [card, i]));
        cards.sort((a,b) => rank.get(a) - rank.get(b));
      }
    }
    return result;
  }

  /** Progressive rendering slice: NEVER treat it as permission enforcement.
   * It exposes total/nextOffset, so DOM cards can grow in bounded batches.
   * Actual virtualization and scroll/keyboard focus remain Prime's work. */
  function lanePage(boardId, listId, {offset = 0, limit = 60} = {}) {
    if (!Number.isSafeInteger(offset) || offset < 0)
      throw new RangeError('offset must be a nonnegative integer');
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > BOARD_INDEX_LIMITS.page)
      throw new RangeError('limit must be an integer between 1 and 300');
    textId(boardId, 'boardId'); textId(listId, 'listId');
    const cards = selected(byBoardLane.get(boardId) || new Map(), listId);
    const end = Math.min(offset + limit, cards.length);
    return {cards: cards.slice(offset,end), total: cards.length,
            nextOffset: end < cards.length ? end : null,
            hasMore: end < cards.length};
  }
  return Object.freeze({
    visibleCount: all.length,
    selectActiveCards: select,
    groupActiveCards: group,
    getOrderedLaneCards: lane,
    getLanePage: lanePage,
  });
}
