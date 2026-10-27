/**
 * Delete one settings stage without moving cards between boards.
 *
 * With boardId, board.stages is authoritative. SettingsPanel also receives a
 * board-scoped projection whose `stages` aliases board.stages; preserve that
 * projection for its existing onChange adapter. Global deletion never alters
 * a board card's listId and refuses to remove a status still used by a board.
 */
export function deleteSettingsStage(state, stageId, {boardId = null, canManage = false} = {}) {
  if (!canManage || !state || typeof stageId !== 'string' || !stageId ||
      !Array.isArray(state.stages) || !Array.isArray(state.tasks)) return state;

  const matchingBoards = boardId == null ? [] : state.boards?.filter(item => item?.id === boardId);
  if (boardId != null && matchingBoards?.length !== 1) return state;
  const board = matchingBoards[0] || null;
  if (boardId != null && (!board || board.archived === true)) return state;
  const stages = board ? board.stages : state.stages;
  if (!Array.isArray(stages) || stages.length < 2) return state;
  if (stages.some(stage => !stage || typeof stage.id !== 'string' || !stage.id) ||
      new Set(stages.map(stage => stage.id)).size !== stages.length) return state;
  const selected = stages.find(stage => stage?.id === stageId);
  if (!selected || selected.archived === true ||
      stages.filter(stage => stage?.archived !== true).length <= 1) return state;

  const fallback = stages.find(stage => stage?.id !== stageId && stage?.archived !== true);
  if (!fallback) return state;

  // Every board card's status must point to an existing global stage, even if
  // its board's listId uses a different ID. Refuse ambiguous global deletion.
  if (!board && state.tasks.some(task => task?.boardId && task.status === stageId)) return state;

  const remaining = stages.filter(stage => stage?.id !== stageId);
  const changedTasks = state.tasks.map(task => {
    if (!task || (board ? task.boardId !== boardId : !!task.boardId)) return task;
    if (board) {
      if (task.listId !== stageId && !(task.listId == null && task.status === stageId)) return task;
      return {...task, listId: fallback.id};
    }
    if (task.status !== stageId && task.listId !== stageId) return task;
    return {...task,
      ...(task.status === stageId ? {status: fallback.id} : {}),
      ...(task.listId === stageId ? {listId: fallback.id} : {})};
  });
  const tasks = changedTasks.some((task, i) => task !== state.tasks[i]) ? changedTasks : state.tasks;

  if (!board) return {...state, stages: remaining, tasks};
  return {...state, tasks,
    boards: state.boards.map(item => item === board ? {...board, stages: remaining} : item),
    // In SettingsPanel's board projection this is the displayed stage list;
    // in the persisted model state.stages belongs to global stages instead.
    ...(state.stages === board.stages ? {stages: remaining} : {})};
}
