/**
 * BD13: pure, board-local list archive / restore.
 *
 * Keep the stage in board.stages and ONLY change stage.archived. In particular,
 * never rewrite task.listId, task.status, task.archived, money, or global stages.
 *
 * A caller MUST pass {canManage:true}; this gate is UI defense-in-depth, not
 * a replacement for the authoritative LAN/admin ACL or whole-state CAS.
 */

function requireObject(value, name) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(name + ' must be an object');
  }
}

function requireStageId(value, name) {
  if (typeof value !== 'string' || !value.trim() || value.length > 100) {
    throw new TypeError(name + ' must be a nonempty stage/board ID up to 100 characters');
  }
}

function requirePermission(options) {
  requireObject(options, 'options');
  if (options.canManage !== true) {
    throw new Error('PERMISSION_DENIED: list archive/restore requires canManage');
  }
}

function selectedBoard(state, boardId, listId) {
  requireObject(state, 'state');
  requireStageId(boardId, 'boardId');
  requireStageId(listId, 'listId');
  if (!Array.isArray(state.boards) || !Array.isArray(state.projects) ||
      !Array.isArray(state.workspaces) || !Array.isArray(state.tasks)) {
    throw new TypeError('Expected normalized state boards/projects/workspaces/tasks arrays');
  }
  // Ambiguous IDs are never resolved to an arbitrary matching board.
  const matches = state.boards.filter(board => board?.id === boardId);
  if (matches.length !== 1) {
    throw new RangeError(matches.length ? 'Duplicate board ID' : 'Unknown board ID');
  }
  const board = matches[0];
  requireObject(board, 'board');
  if (board.archived === true) {
    throw new RangeError('Archived board must be restored before changing its lists');
  }
  if (typeof board.workspaceId !== 'string' ||
      !state.workspaces.some(workspace => workspace?.id === board.workspaceId)) {
    throw new RangeError('Board references an unknown workspace');
  }
  if (board.projectId != null &&
      (typeof board.projectId !== 'string' ||
       !state.projects.some(project => project?.id === board.projectId))) {
    throw new RangeError('Board references an unknown project');
  }
  // Project-less boards are supported in data_model.py; a project reference,
  // if present, must remain valid. Legacy project IDs may be empty strings.
  if (!Array.isArray(board.stages) || board.stages.length < 1 ||
      board.stages.length > 40) {
    throw new RangeError('Board must contain 1 to 40 retained stages');
  }
  const seen = new Set();
  for (const stage of board.stages) {
    requireObject(stage, 'board stage');
    requireStageId(stage.id, 'stage.id');
    if (seen.has(stage.id)) throw new RangeError('Duplicate stage ID');
    seen.add(stage.id);
    if ('archived' in stage && typeof stage.archived !== 'boolean') {
      throw new TypeError('stage.archived must be a boolean when present');
    }
  }
  const index = board.stages.findIndex(stage => stage.id === listId);
  if (index < 0) throw new RangeError('Unknown list ID for this board');
  return {board, index};
}

function updateStage(state, boardId, board, index, archived) {
  const stage = board.stages[index];
  const updatedStages = board.stages.map((item, i) =>
    i === index ? {...item, archived} : item);
  // Preserve all board extras, the exact stage order, all other board objects,
  // and the original project/task/finance collection references.
  return {...state, boards: state.boards.map(item =>
    item === board ? {...item, stages: updatedStages} : item)};
}

/**
 * Mark one board-local list as archived without moving/deleting its cards.
 * Already archived => original state by reference.
 * The last non-archived list may not be archived.
 */
export function archiveListState(state, boardId, listId, options = {}) {
  requirePermission(options);
  const {board, index} = selectedBoard(state, boardId, listId);
  if (board.stages[index].archived === true) return state;
  if (board.stages.filter(stage => stage.archived !== true).length <= 1) {
    throw new RangeError('Cannot archive the last active list');
  }
  return updateStage(state, boardId, board, index, true);
}

/**
 * Restore an existing archived list in place; cards and finance remain intact.
 * Already active (including legacy stage without archived) => original state.
 */
export function restoreListState(state, boardId, listId, options = {}) {
  requirePermission(options);
  const {board, index} = selectedBoard(state, boardId, listId);
  if (board.stages[index].archived !== true) return state;
  return updateStage(state, boardId, board, index, false);
}

/**
 * UI-only helper; never use its filtered output as replacement board.stages:
 * hidden archived stages must remain in the authoritative saved state.
 */
export function activeBoardLists(board) {
  requireObject(board, 'board');
  if (!Array.isArray(board.stages)) throw new TypeError('board.stages must be an array');
  return board.stages.filter(stage => stage?.archived !== true);
}
