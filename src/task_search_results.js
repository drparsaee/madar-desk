import {filterTasks} from './searchplus.js';

function validFlag(record, field) {
  if (record[field] !== undefined && typeof record[field] !== 'boolean')
    throw new TypeError('Invalid ' + field + ' flag');
}

/** Stable sort of result DTOs. Dates newest first; card order within its list. */
export function sortTaskSearchResults(results, sortBy = 'date') {
  if (!['date', 'cardOrder'].includes(sortBy))
    throw new RangeError('sortBy must be date or cardOrder');
  if (!Array.isArray(results)) throw new TypeError('results must be an array');
  const collator = new Intl.Collator('fa');
  const locationCompare = (a,b) =>
    collator.compare(a.projectName || '', b.projectName || '') ||
    collator.compare(a.boardName || '', b.boardName || '') ||
    collator.compare(a.listName || '', b.listName || '');
  const cardOrder = (a,b) =>
    a.cardOrder == null ? (b.cardOrder == null ? 0 : 1) :
    b.cardOrder == null ? -1 : a.cardOrder - b.cardOrder;
  const dateNumber = item => item.date && Number.isFinite(Date.parse(item.date))
    ? Date.parse(item.date) : -Infinity;
  return results.map((item, index) => ({item, index})).sort((a,b) => {
    const cmp = sortBy === 'cardOrder'
      ? locationCompare(a.item,b.item) || cardOrder(a.item,b.item)
      : (dateNumber(b.item) - dateNumber(a.item)) ||
        locationCompare(a.item,b.item) || cardOrder(a.item,b.item);
    return cmp || a.index - b.index;
  }).map(({item}) => item);
}

/**
 * Cross-status task search, for an already authenticated/redacted host snapshot.
 *
 * The explicit permittedProjectIds MUST come from the trusted host grants.
 * Do not derive it from state.projects or any property of an individual task.
 * No finance/attachment fields or raw task references are returned.
 *
 * searchTaskLocations(state, {query, permittedProjectIds, workspaceId?,
 *   projectId?, users?, sortBy?: 'date' | 'cardOrder'})
 *
 * An omitted workspaceId searches every accessible workspace, including
 * archived ones. A supplied workspaceId narrows the search even for trash.
 * An empty query intentionally returns [] (never dumps the whole task store).
 */
export function searchTaskLocations(state, options = {}) {
  if (!state || typeof state !== 'object' || Array.isArray(state)) {
    throw new TypeError('state must be an object');
  }
  const {query = '', permittedProjectIds, workspaceId, projectId,
    users = [], sortBy = 'date'} = options;
  if (!Array.isArray(permittedProjectIds) ||
      permittedProjectIds.length > 2000 ||
      permittedProjectIds.some(id => typeof id !== 'string')) {
    throw new TypeError('Explicit permittedProjectIds array is required');
  }
  if (typeof query !== 'string') throw new TypeError('query must be a string');
  if (workspaceId !== undefined && typeof workspaceId !== 'string')
    throw new TypeError('workspaceId must be a string');
  if (projectId !== undefined && typeof projectId !== 'string')
    throw new TypeError('projectId must be a string');
  if (!['date', 'cardOrder'].includes(sortBy))
    throw new RangeError('sortBy must be date or cardOrder');
  if (!Array.isArray(users)) throw new TypeError('users must be an array');
  if (query.trim().length === 0) return [];
  const {tasks, projects, boards = [], workspaces = [], stages = []} = state;
  if (!Array.isArray(tasks) || tasks.length > 20000 ||
      !Array.isArray(projects) || projects.length > 2000 ||
      !Array.isArray(boards) || boards.length > 2000 ||
      !Array.isArray(workspaces) || workspaces.length > 100 ||
      !Array.isArray(stages) || stages.length > 40) {
    throw new TypeError('Invalid or oversized task search state');
  }
  const grants = new Set(permittedProjectIds);
  const projectById = new Map();
  for (const project of projects) {
    if (!project || typeof project.id !== 'string') throw new TypeError('Invalid project');
    if (!grants.has(project.id)) continue;
    if (projectById.has(project.id)) throw new RangeError('Duplicate authorized project');
    projectById.set(project.id, project);
  }
  if (projectId !== undefined && !projectById.has(projectId)) return [];
  if (!projectById.size) return [];

  const workspaceById = new Map();
  for (const workspace of workspaces) {
    if (!workspace || typeof workspace.id !== 'string') throw new TypeError('Invalid workspace');
    if (workspaceById.has(workspace.id)) throw new RangeError('Duplicate workspace');
    validFlag(workspace, 'archived');
    workspaceById.set(workspace.id, workspace);
  }
  const boardById = new Map();
  for (const board of boards) {
    if (!board || typeof board.id !== 'string') throw new TypeError('Invalid board');
    if (boardById.has(board.id)) throw new RangeError('Duplicate board');
    validFlag(board, 'archived');
    boardById.set(board.id, board);
  }
  const globalStages = new Map(stages.map(stage => [stage?.id, stage]));
  const seenIds = new Set();
  const candidates = [];
  for (const task of tasks) {
    if (!task || typeof task !== 'object' || !projectById.has(task.projectId) ||
        (projectId !== undefined && task.projectId !== projectId)) continue;
    if (typeof task.id !== 'string') throw new TypeError('Invalid authorized task id');
    if (seenIds.has(task.id)) throw new RangeError('Duplicate authorized task id');
    seenIds.add(task.id);
    for (const flag of ['deleted', 'archived', 'archivedByBoard']) {
      if (task[flag] !== undefined && typeof task[flag] !== 'boolean')
        throw new TypeError('Invalid task.' + flag);
    }
    if (Object.hasOwn(task, 'cardOrder') &&
        (!Number.isSafeInteger(task.cardOrder) || task.cardOrder < 0 || task.cardOrder > 1000000))
      throw new RangeError('Invalid cardOrder');
    let board = null, workspace = null, stage = null;
    if (task.boardId != null || task.listId != null) {
      if (typeof task.boardId !== 'string' || typeof task.listId !== 'string') continue;
      board = boardById.get(task.boardId);
      if (!board || (board.projectId != null && board.projectId !== task.projectId))
        continue; // Never disclose cards through an unrelated or broken board.
      workspace = workspaceById.get(board.workspaceId);
      if (!workspace || !Array.isArray(board.stages)) continue;
      stage = board.stages.find(item => item?.id === task.listId);
      if (!stage) continue;
      validFlag(stage, 'archived');
    } else {
      // Legacy v1 boardless state. Never fabricate a workspace/board.
      if (boards.length || !globalStages.has(task.status)) continue;
      stage = globalStages.get(task.status);
      if (!stage || typeof stage !== 'object') continue;
      validFlag(stage, 'archived');
    }
    if (workspaceId !== undefined &&
        (workspace?.id || 'workspace-legacy') !== workspaceId) continue;
    candidates.push({task, board, workspace, stage});
  }

  // Only authorized candidates and their authorized project names enter the
  // preexisting rich/Persian search. It never indexes finance fields.
  const byStage = new Map();
  for (const candidate of candidates) {
    if (!byStage.has(candidate.stage)) byStage.set(candidate.stage, []);
    byStage.get(candidate.stage).push(candidate.task);
  }
  const matchIds = new Set();
  const safeProjects = [...projectById.values()];
  for (const [stage, stageTasks] of byStage) {
    for (const task of filterTasks(stageTasks, {
      query, projects: safeProjects, users, stages: [stage]
    })) matchIds.add(task.id);
  }
  const results = candidates.filter(item => matchIds.has(item.task.id)).map(({task, board, workspace, stage}) => {
    const archiveScope = task.archivedByBoard === true || board?.archived === true ? 'board' :
      workspace?.archived === true ? 'workspace' :
      stage?.archived === true ? 'list' : task.archived === true ? 'card' : null;
    const status = task.deleted === true ? 'trash' :
      archiveScope ? 'archived' : 'active';
    const date = [task.updatedAt, task.createdAt].find(value =>
      typeof value === 'string' && Number.isFinite(Date.parse(value))) || '';
    const labels = Array.isArray(task.labels) ? task.labels.map(label => {
      const name = typeof label === 'string' ? label : label?.name || label?.label;
      const color = typeof label === 'object' && label !== null &&
        /^#[a-fA-F0-9]{3,8}$/.test(label.color || '') ? label.color : null;
      return {name: String(name || ''), color};
    }).filter(label => label.name) : [];
    return {
      id: task.id, title: String(task.title || ''), projectId: task.projectId,
      projectName: String(projectById.get(task.projectId)?.name || ''),
      boardId: board?.id ?? null, boardName: String(board?.name || ''),
      workspaceId: workspace?.id ?? null, workspaceName: String(workspace?.name || ''),
      listId: board ? task.listId : task.status,
      listName: String(stage?.label || stage?.name || task.listId || task.status || ''),
      status, archiveScope, labels, date, cardOrder: Number.isSafeInteger(task.cardOrder) &&
        task.cardOrder >= 0 && task.cardOrder <= 1000000 ? task.cardOrder : null,
    };
  });
  return sortTaskSearchResults(results, sortBy);
}
