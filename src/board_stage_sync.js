/**
 * Legacy workspace-wide stage settings are still exposed for boards created
 * before list-specific management. A newly added global stage must be a real
 * list destination in every active board in that workspace. Never partially
 * publish the stage, rewrite card/status data, or exceed the 40-list cap.
 * Existing board-specific overrides, orders and archived lists stay put.
 */
export function propagateAddedWorkspaceStages(before, after, workspaceId) {
  if (!before || !after || before === after) return after;
  const previous = new Set((before.stages || []).map(stage => stage.id));
  const added = (after.stages || []).filter(stage => !previous.has(stage.id));
  const oldStages = new Map((before.stages || []).map(stage => [stage.id,stage]));
  const newStages = new Map((after.stages || []).map(stage => [stage.id,stage]));
  const changed = (after.stages || []).some(stage => {
    const old = oldStages.get(stage.id);
    return old && ['label','subtitle','color'].some(field => old[field] !== stage[field]);
  });
  if (!added.length && !changed) return after;
  const boards = after.boards || [];
  const writable = boards.filter(board => !board.archived && board.workspaceId === workspaceId);
  if (writable.some(board =>
    (board.stages || []).length + added.filter(stage =>
      !board.stages?.some(item => item.id === stage.id)).length > 40)) return before;
  return {
    ...after,
    boards: boards.map(board =>
      board.archived || board.workspaceId !== workspaceId ? board : {
        ...board,
        stages: [
          ...board.stages.map(stage => {
            const old=oldStages.get(stage.id), next=newStages.get(stage.id);
            if(!old || !next)return stage;
            const patch={};
            for(const field of ['label','subtitle','color']){
              if(old[field]!==next[field] && stage[field]===old[field])patch[field]=next[field];
            }
            return Object.keys(patch).length?{...stage,...patch}:stage;
          }),
          ...added.filter(stage => !board.stages.some(item => item.id === stage.id)),
        ],
      }),
  };
}

/** Choose an actual board containing a requested list, not just the first
 * board that happens to belong to a workspace. */
export function boardForColumn(boards, projectId, requestedListId, preferredBoardId) {
  const choices = (boards || []).filter(board =>
    !board.archived && board.projectId === projectId);
  const contains = board => board.stages?.some(stage =>
    stage.id === requestedListId && stage.archived !== true);
  return choices.find(board => board.id === preferredBoardId &&
    (!requestedListId || contains(board))) ||
    (requestedListId ? choices.find(contains) : null) || choices[0] || null;
}
