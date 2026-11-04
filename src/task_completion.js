/** The user's explicit completion toggle takes precedence over legacy lanes.
 * Moving to a "done" lane is not necessary (and may trigger finance bridges).
 */
export function taskIsCompleted(task){
  if(typeof task?.completed==='boolean')return task.completed;
  return task?.status==='done';
}
