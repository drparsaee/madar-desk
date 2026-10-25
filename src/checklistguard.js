/** Remove only a cost-free legacy step, keeping its named checklist mirror aligned. */
export function removeUnpaidLegacyStep(task, itemId) {
  if (!task || !Array.isArray(task.checklist) || typeof itemId !== 'string') return null;
  const matching = task.checklist.filter(item => item?.id === itemId);
  // Duplicate identifiers or a nonzero/unparseable cost make deletion unsafe.
  if (matching.length !== 1 || !Number.isFinite(Number(matching[0].cost ?? 0)) ||
      Number(matching[0].cost ?? 0) !== 0 ||
      (Array.isArray(matching[0].expenseItems) && matching[0].expenseItems.length > 0)) return null;
  const checklist = task.checklist.filter(item => item?.id !== itemId);
  const changes = {checklist};
  if (Array.isArray(task.checklists)) {
    changes.checklists = task.checklists.map(group => group?.id === 'checklist-legacy'
      ? {...group, items: checklist.map(item => ({...item}))}
      : group);
  }
  return changes;
}
