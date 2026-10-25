/**
 * Madar v1 additive workspace transitions. No I/O and no changes to task,
 * project, board projectId, finance, attachment, checklist or template data.
 * Mirrors data_model.py:32,339-357,504-558 without Python dependencies.
 * The canManage gate is client defense only; host ACL stays authoritative.
 */
export const LEGACY_WORKSPACE_ID = 'workspace-legacy';
export const MAX_WORKSPACES = 100;

function requireManager(canManage) {
  if (canManage !== true) throw new Error('مدیریت فضاهای کاری فقط برای مدیر مجاز است');
}

function validId(id, field) {
  if (typeof id !== 'string' || !id.trim() || id.length > 100 ||
      [...id].some(c => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127))
    throw new Error(field + ': شناسه معتبر نیست');
  return id;
}

function validName(name) {
  if (typeof name !== 'string' || !name.trim() || name.length > 180 ||
      [...name].some(c => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127))
    throw new Error('نام فضای کاری باید بین ۱ تا ۱۸۰ نویسه و بدون نویسه کنترلی باشد');
  return name.trim();
}

const legacyWorkspace = () => ({
  id: LEGACY_WORKSPACE_ID, name: 'فضای کاری من', archived: false,
});

function requireArray(value, label) {
  if (!Array.isArray(value)) throw new Error(label + ': آرایه معتبر نیست');
  return value;
}

/** Synthesize legacy default only when workspaces and boards are both absent. */
export function workspaceShell(state) {
  if (!state || typeof state !== 'object' || Array.isArray(state))
    throw new Error('اطلاعات برنامه معتبر نیست');
  const boards = requireArray(state.boards ?? [], 'boards');
  const workspaces = requireArray(state.workspaces ?? [], 'workspaces');
  if (!workspaces.length && boards.length)
    throw new Error('بردهای قدیمی بدون Workspace معتبرند؛ ابتدا مهاجرت میزبان لازم است');
  return {
    ...state,
    boards,
    workspaces: workspaces.length ? workspaces : [legacyWorkspace()],
  };
}

/** Before/after validation of workspace and board references, without repair. */
export function validateWorkspaceLinks(state) {
  const current = workspaceShell(state);
  const {workspaces, boards} = current;
  if (workspaces.length > MAX_WORKSPACES) throw new Error('حداکثر ۱۰۰ فضای کاری مجاز است');
  const workspaceIds = new Set();
  let active = 0;
  for (const w of workspaces) {
    if (!w || typeof w !== 'object' || Array.isArray(w)) throw new Error('فضای کاری نامعتبر');
    validId(w.id, 'workspace.id');
    validName(w.name);
    if (w.archived !== undefined && typeof w.archived !== 'boolean')
      throw new Error('وضعیت بایگانی Workspace نامعتبر است');
    if (workspaceIds.has(w.id)) throw new Error('شناسه Workspace تکراری است');
    workspaceIds.add(w.id);
    if (!w.archived) active += 1;
  }
  if (!active) throw new Error('حداقل یک فضای کاری فعال لازم است');
  const projects = requireArray(current.projects ?? [], 'projects');
  const projectIds = new Set(projects.map(p => p?.id));
  const boardIds = new Set();
  const boardsById = new Map();
  for (const board of boards) {
    if (!board || typeof board !== 'object' || Array.isArray(board))
      throw new Error('برد نامعتبر است');
    validId(board.id, 'board.id');
    if (boardIds.has(board.id)) throw new Error('شناسه برد تکراری است');
    boardIds.add(board.id);
    boardsById.set(board.id, board);
    if (!workspaceIds.has(board.workspaceId))
      throw new Error('برد به Workspace ناشناخته اشاره دارد');
    if (board.projectId != null && !projectIds.has(board.projectId))
      throw new Error('برد به پروژه ناشناخته اشاره دارد');
  }
  const tasks = requireArray(current.tasks ?? [], 'tasks');
  for (const card of tasks) {
    if (!card || typeof card !== 'object' || Array.isArray(card))
      throw new Error('کارت نامعتبر است');
    if (projects.length && !projectIds.has(card.projectId))
      throw new Error('پروژه کارت پیدا نشد');
    const board = card.boardId != null ? boardsById.get(card.boardId) : null;
    if (card.boardId != null && !board)
      throw new Error('برد کارت پیدا نشد');
    if (board && board.projectId != null && board.projectId !== card.projectId)
      throw new Error('پروژه کارت با پروژه برد مغایرت دارد');
    if (card.listId != null && card.boardId == null)
      throw new Error('مرحله کارت بدون برد معتبر نیست');
    if (card.listId != null && (!Array.isArray(board.stages) ||
        !board.stages.some(s => s?.id === card.listId)))
      throw new Error('مرحله کارت در برد مربوط موجود نیست');
  }
  for (const template of requireArray(current.templates ?? [], 'templates')) {
    if (!template || !boardIds.has(template.boardId))
      throw new Error('قالب به برد ناشناخته اشاره دارد');
  }
  return current;
}

function update(state, canManage, transform) {
  requireManager(canManage);
  const current = validateWorkspaceLinks(state);
  const changed = transform(current);
  validateWorkspaceLinks(changed);
  return changed;
}

export function generateWorkspaceId(state, makeId) {
  const current = validateWorkspaceLinks(state);
  const seen = new Set(current.workspaces.map(w => w.id));
  const generate = makeId || (() => {
    if (typeof globalThis.crypto?.randomUUID === 'function')
      return 'workspace-' + globalThis.crypto.randomUUID();
    // ID is not a credential; collisions are still rejected.
    return 'workspace-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
  });
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const id = generate();
    if (typeof id === 'string' && /^workspace-[A-Za-z0-9_-]{1,90}$/.test(id) &&
        !seen.has(id)) return id;
  }
  throw new Error('شناسه یکتای Workspace ایجاد نشد');
}

export function createWorkspaceState(state, id, name, {canManage = false} = {}) {
  return update(state, canManage, current => {
    if (current.workspaces.length >= MAX_WORKSPACES)
      throw new Error('حداکثر تعداد Workspace تکمیل شده است');
    if (typeof id !== 'string' || !/^workspace-[A-Za-z0-9_-]{1,90}$/.test(id))
      throw new Error('شناسه Workspace جدید نامعتبر است');
    if (current.workspaces.some(w => w.id === id))
      throw new Error('شناسه Workspace از قبل وجود دارد');
    return {...current, workspaces: [
      ...current.workspaces, {id, name:validName(name), archived:false},
    ]};
  });
}

export function renameWorkspaceState(state, id, name, {canManage = false} = {}) {
  return update(state, canManage, current => {
    validId(id, 'workspace.id');
    if (!current.workspaces.some(w => w.id === id)) throw new Error('Workspace پیدا نشد');
    const label = validName(name);
    return {...current, workspaces: current.workspaces.map(w => w.id === id ? {...w, name:label} : w)};
  });
}

export function archiveWorkspaceState(state, id, {canManage = false} = {}) {
  return update(state, canManage, current => {
    validId(id, 'workspace.id');
    const workspace = current.workspaces.find(w => w.id === id);
    if (!workspace) throw new Error('Workspace پیدا نشد');
    if (id === LEGACY_WORKSPACE_ID)
      throw new Error('فضای کاری پیش‌فرض قدیمی قابل بایگانی نیست');
    if (workspace.archived) throw new Error('Workspace قبلاً بایگانی شده است');
    if (current.workspaces.filter(w => !w.archived).length < 2)
      throw new Error('آخرین Workspace فعال قابل بایگانی نیست');
    return {...current, workspaces: current.workspaces.map(w =>
      w.id === id ? {...w, archived:true} : w)};
  });
}

export function restoreWorkspaceState(state, id, {canManage = false} = {}) {
  return update(state, canManage, current => {
    validId(id, 'workspace.id');
    const workspace = current.workspaces.find(w => w.id === id);
    if (!workspace) throw new Error('Workspace پیدا نشد');
    if (!workspace.archived) throw new Error('Workspace فعال است');
    return {...current, workspaces: current.workspaces.map(w =>
      w.id === id ? {...w, archived:false} : w)};
  });
}

/** Move only board.workspaceId; preserve tasks, projects and all financial fields. */
export function moveBoardWorkspaceState(state, boardId, destinationId, {canManage = false} = {}) {
  return update(state, canManage, current => {
    validId(boardId, 'board.id');
    validId(destinationId, 'workspace.id');
    const destination = current.workspaces.find(w => w.id === destinationId);
    if (!destination || destination.archived)
      throw new Error('Workspace مقصد باید فعال و موجود باشد');
    const board = current.boards.find(b => b.id === boardId);
    if (!board) throw new Error('برد پیدا نشد');
    if (board.workspaceId === destinationId) return current;
    return {...current, boards: current.boards.map(b => b.id === boardId ?
      {...b, workspaceId:destinationId} : b)};
  });
}

export function selectWorkspaceId(state, id) {
  const current = validateWorkspaceLinks(state);
  validId(id, 'workspace.id');
  if (!current.workspaces.some(w => w.id === id && !w.archived))
    throw new Error('Workspace انتخاب‌شده فعال یا موجود نیست');
  return id;
}

export function activeWorkspaceId(state, desiredId) {
  const current = validateWorkspaceLinks(state);
  const selected = current.workspaces.find(w => w.id === desiredId && !w.archived);
  return selected?.id || current.workspaces.find(w => !w.archived).id;
}
