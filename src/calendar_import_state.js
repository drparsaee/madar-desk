/** Convert user-approved ICS preview records into ordinary, zero-cost tasks. */
export function importCalendarEvents(state, projectId, events, createId, timestamp) {
  if (!state || !Array.isArray(state.tasks) || !Array.isArray(state.projects) ||
      !Array.isArray(events) || events.length > 1000 || typeof createId !== 'function' ||
      !state.projects.some(p=>p.id===projectId)) throw Error('پروژه یا فایل تقویم معتبر نیست.');
  const board=(state.boards||[]).find(b=>b.projectId===projectId&&!b.archived);
  if (!board?.stages?.length || !state.stages?.length) throw Error('برای ورود رویداد باید برد فعال با ستون معتبر وجود داشته باشد.');
  const stageId=board.stages[0].id;
  const status=state.stages.some(s=>s.id===stageId)?stageId:state.stages[0].id;
  const priority=state.settings?.priorityDefinitions?.[0]?.id||'medium';
  const known=new Set(state.tasks.map(t=>t.calendarSourceKey).filter(Boolean));
  const ids=new Set(state.tasks.map(t=>t.id));
  const created=[];
  for(const item of events){
    if (!item || typeof item.source_key!=='string' || !/^[0-9a-f]{64}$/.test(item.source_key) ||
        typeof item.title!=='string'||!item.title.trim()||item.title.length>300 ||
        typeof item.dueDate!=='string'||!/^\d{4}-\d\d-\d\d$/.test(item.dueDate) ||
        !Number.isFinite(Date.parse(item.dueDate+'T12:00:00Z')) ||
        new Date(item.dueDate+'T12:00:00Z').toISOString().slice(0,10)!==item.dueDate)
      throw Error('رویداد نامعتبر در فایل تقویم وجود دارد.');
    if(known.has(item.source_key))continue;
    const id=createId();
    if(typeof id!=='string'||!id||ids.has(id))throw Error('شناسه کارت تکراری است.');
    ids.add(id);known.add(item.source_key);
    created.push({id,projectId,boardId:board.id,listId:stageId,status,priority,
      title:item.title.trim(),description:'',dueDate:item.dueDate,
      calendarSourceKey:item.source_key,labels:[],checklist:[],reports:[],
      assignees:[],fileLinks:[],cost:0,costEnabled:false,
      createdAt:timestamp,updatedAt:timestamp});
  }
  return {...state,tasks:[...created,...state.tasks]};
}
