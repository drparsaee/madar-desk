/**
 * CD05: reversible, in-memory card trash. NOT wired to the current UI/RC3.
 *
 * task.deleted is a dedicated soft-delete marker, independent from
 * task.archived and task.archivedByBoard. No other card/domain key changes.
 *
 * This is a UI defense-in-depth gate, NOT the trusted LAN ACL or storage CAS:
 * managers provide {canManage:true}; editors provide {canEdit:true,
 * grantedProjectIds:['project-id']}, obtained from authenticated host grants.
 * Passing options does not authenticate a user.
 */

export const MAX_TRASH_CARDS = 20_000;
const MAX_PROJECTS = 2_000;
const MAX_BOARDS = 2_000;
const MAX_WORKSPACES = 100;
const MAX_BOARD_LISTS = 40;

function object(value, field) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(field + ' must be an object');
  }
  return value;
}

function array(value, field, limit) {
  if (!Array.isArray(value) || value.length > limit) {
    throw new RangeError(field + ' must be an array of at most ' + limit + ' items');
  }
  return value;
}

function identifier(value, field, limit = 100) {
  if (typeof value !== 'string' || !value.trim() || value.length > limit ||
      /[\x00-\x1f\x7f]/.test(value)) {
    throw new TypeError(field + ' must be a valid nonempty identifier');
  }
  return value;
}

function legacyProjectId(value) {
  // data_model.py permits empty historical project identifiers. They can be
  // referenced only by exact match; no new ID or project is synthesized.
  if (typeof value !== 'string' || value.length > 2048 ||
      /[\x00-\x1f\x7f]/.test(value)) {
    throw new TypeError('task.projectId must be a string project ID');
  }
  return value;
}

function unique(items, id, field) {
  const matches = items.filter(item => item?.id === id);
  if (matches.length !== 1) {
    throw new RangeError(matches.length ? 'Duplicate ' + field + ' reference' :
      'Unknown ' + field + ' reference');
  }
  return object(matches[0], field);
}

function optionalBoolean(record, field, label) {
  if (Object.hasOwn(record, field) && typeof record[field] !== 'boolean') {
    throw new TypeError(label + '.' + field + ' must be a boolean when present');
  }
}

function requireGrant(options, projectId) {
  object(options, 'options');
  if (options.canManage === true) return;
  if (options.canEdit !== true) {
    throw new Error('PERMISSION_DENIED: card trash/restore requires manage or edit grant');
  }
  const ids = array(options.grantedProjectIds, 'grantedProjectIds', MAX_PROJECTS);
  const allowed = new Set();
  for (const id of ids) {
    if (typeof id !== 'string' || id.length > 100 ||
        /[\x00-\x1f\x7f]/.test(id)) {
      throw new TypeError('grantedProjectIds contains an invalid project ID');
    }
    allowed.add(id);
  }
  if (!allowed.has(projectId)) {
    throw new Error('PERMISSION_DENIED: no card edit grant for this project');
  }
}

export function selectedCard(state, cardId, options) {
  object(state, 'state');
  // Legacy task IDs can be longer than newer board IDs. Do not rewrite them.
  identifier(cardId, 'cardId', 2048);
  const tasks = array(state.tasks, 'tasks', MAX_TRASH_CARDS);
  const projects = array(state.projects, 'projects', MAX_PROJECTS);
  const task = unique(tasks, cardId, 'card');
  legacyProjectId(task.projectId);
  unique(projects, task.projectId, 'project');
  requireGrant(options, task.projectId);
  optionalBoolean(task, 'deleted', 'task');
  optionalBoolean(task, 'archived', 'task');
  optionalBoolean(task, 'archivedByBoard', 'task');

  // An unmigrated v1 task has projectId + global status and no board/list.
  // Never infer or invent links, and refuse only partial board references.
  if (task.boardId == null && task.listId == null) {
    if (typeof task.status !== 'string' || !task.status.trim()) {
      throw new RangeError('Legacy card must retain a valid status');
    }
    if (state.stages !== undefined) {
      const stages = array(state.stages, 'stages', MAX_BOARD_LISTS);
      if (!stages.some(stage => stage?.id === task.status)) {
        throw new RangeError('Legacy card status is not in global stages');
      }
    }
    // An unreferenced legacy task does not become part of a guessed board.
    return task;
  }
  if (task.boardId == null || task.listId == null) {
    throw new RangeError('Card has an incomplete board/list reference');
  }

  identifier(task.boardId, 'task.boardId');
  identifier(task.listId, 'task.listId');
  const boards = array(state.boards, 'boards', MAX_BOARDS);
  const workspaces = array(state.workspaces, 'workspaces', MAX_WORKSPACES);
  const board = unique(boards, task.boardId, 'board');
  optionalBoolean(board, 'archived', 'board');
  if (board.archived === true) {
    throw new RangeError('Archived board must be restored before changing its cards');
  }
  if (board.projectId != null && board.projectId !== task.projectId) {
    throw new RangeError('Card project does not match its board project');
  }
  identifier(board.workspaceId, 'board.workspaceId');
  const workspace = unique(workspaces, board.workspaceId, 'workspace');
  optionalBoolean(workspace, 'archived', 'workspace');
  if (workspace.archived === true) {
    throw new RangeError('Archived workspace must be restored before changing its cards');
  }
  const stages = array(board.stages, 'board.stages', MAX_BOARD_LISTS);
  if (!stages.length) throw new RangeError('Board must retain at least one list');
  const listIds = new Set();
  for (const stage of stages) {
    object(stage, 'board stage');
    identifier(stage.id, 'stage.id');
    if (listIds.has(stage.id)) throw new RangeError('Duplicate board list ID');
    listIds.add(stage.id);
    optionalBoolean(stage, 'archived', 'stage');
  }
  if (!listIds.has(task.listId)) {
    throw new RangeError('Card listId is not present in its board');
  }
  // An archived LIST is intentionally allowed. Restored cards remain in their
  // original hidden list until BD13 restores it; references never move.
  return task;
}

function toggle(state, cardId, options, deleted) {
  const task = selectedCard(state, cardId, options);
  if ((task.deleted === true) === deleted) return state;
  return {
    ...state,
    tasks: state.tasks.map(item => item === task ? {...item, deleted} : item),
  };
}

/** Move a card to trash without destroying any task or related financial data. */
export function softDeleteCardState(state, cardId, options = {}) {
  return toggle(state, cardId, options, true);
}

/** Restore a trashed card in its exact original board/list/status/order. */
export function restoreDeletedCardState(state, cardId, options = {}) {
  return toggle(state, cardId, options, false);
}
