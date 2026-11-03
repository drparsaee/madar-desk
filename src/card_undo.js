// Card-only, in-memory history. No persistent snapshots, finance commands or LAN writes.
export const MAX_CARD_UNDO = 40;
const EDITABLE_FIELDS = new Set([
  'title', 'description', 'priority', 'dueDate', 'completed',
  'textDirection', 'labels', 'labelColors', 'cover'
]);

export const emptyCardHistory = scope => ({scope, undo: [], redo: []});

export function isUndoableCardPatch(fields) {
  return fields && typeof fields === 'object' && !Array.isArray(fields) &&
    Object.keys(fields).length > 0 && Object.keys(fields).every(key => EDITABLE_FIELDS.has(key));
}

const clone = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
const equivalent = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function cardSignature(card) {
  if (!card) return null;
  const {updatedAt, ...stable} = card;
  return JSON.stringify(stable);
}

function validCard(card, state) {
  if (!card || card.deleted === true || card.archived === true || card.archivedByBoard === true) return false;
  const board = (state.boards || []).find(item => item.id === card.boardId);
  if (!board || board.archived === true || board.projectId !== card.projectId) return false;
  const list = board.stages?.find(item => item.id === card.listId);
  return !!list && list.archived !== true;
}

/** Record only an actual, single-card nonfinancial edit. Untrusted mutations are never replayed. */
export function recordCardEdit(history, beforeState, afterState, cardId, fields, scope, actionId) {
  if (!isUndoableCardPatch(fields) || !scope || !actionId) return emptyCardHistory(scope);
  const before = beforeState?.tasks?.find(card => card.id === cardId);
  const after = afterState?.tasks?.find(card => card.id === cardId);
  if (!validCard(before, beforeState) || !validCard(after, afterState) ||
      before.boardId !== after.boardId || before.projectId !== after.projectId ||
      before.listId !== after.listId || !equivalent(beforeState.boards, afterState.boards) ||
      beforeState.tasks.length !== afterState.tasks.length ||
      beforeState.tasks.some((card, i) => card.id !== afterState.tasks[i]?.id ||
        (card.id !== cardId && cardSignature(card) !== cardSignature(afterState.tasks[i])))) {
    return emptyCardHistory(scope);
  }
  const keys = Object.keys(fields);
  const otherFields = card => Object.fromEntries(Object.entries(card)
    .filter(([key]) => key !== 'updatedAt' && !keys.includes(key)));
  if (!equivalent(otherFields(before), otherFields(after))) return emptyCardHistory(scope);
  const beforeFields = Object.fromEntries(keys.map(key => [key, before[key]]));
  const afterFields = Object.fromEntries(keys.map(key => [key, after[key]]));
  if (equivalent(beforeFields, afterFields)) return history?.scope === scope ? history : emptyCardHistory(scope);
  const base = history?.scope === scope ? history : emptyCardHistory(scope);
  // React may invoke functional state updaters twice in development StrictMode.
  if ([...base.undo, ...base.redo].some(entry => entry.actionId === actionId)) return base;
  const entry = {actionId, cardId, boardId: before.boardId, projectId: before.projectId,
    keys, before: clone(before), after: clone(after)};
  return {scope, undo: [...base.undo, entry].slice(-MAX_CARD_UNDO), redo: []};
}

export function cardHistoryAvailability(history, state, direction, scope, enabled) {
  if (!enabled || !scope || history?.scope !== scope) return false;
  const entry = history?.[direction]?.at(-1);
  if (!entry) return false;
  const card = state?.tasks?.find(item => item.id === entry.cardId);
  const expected = direction === 'undo' ? entry.after : entry.before;
  return validCard(card, state) && card.boardId === entry.boardId &&
    card.projectId === entry.projectId && cardSignature(card) === cardSignature(expected);
}

/** Conditional reversal: only the listed harmless keys change, all financial fields survive. */
export function applyCardHistory(history, state, direction, scope, enabled, timestamp) {
  if (!cardHistoryAvailability(history, state, direction, scope, enabled) ||
      !['undo', 'redo'].includes(direction)) return {applied: false, state, history};
  const from = history[direction];
  const entry = from.at(-1);
  const saved = direction === 'undo' ? entry.before : entry.after;
  const card = state.tasks.find(item => item.id === entry.cardId);
  const restored = {...card, updatedAt: timestamp};
  for (const key of entry.keys) {
    if (Object.prototype.hasOwnProperty.call(saved, key)) restored[key] = clone(saved[key]);
    else delete restored[key];
  }
  const nextState = {...state, tasks: state.tasks.map(item => item.id === entry.cardId ? restored : item)};
  const destination = direction === 'undo' ? 'redo' : 'undo';
  return {applied: true, state: nextState, history: {
    scope, [direction]: from.slice(0, -1),
    [destination]: [...history[destination], entry].slice(-MAX_CARD_UNDO)
  }};
}
