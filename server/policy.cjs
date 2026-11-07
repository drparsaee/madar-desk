'use strict';

const {canonical} = require('./storage.cjs');
class ValidationError extends Error {
  constructor(message, status=422, code='invalid_state') {
    super(message); this.status=status; this.code=code;
  }
}
const bad=(message)=>{throw new ValidationError(message);};
const own=(v,k)=>Object.prototype.hasOwnProperty.call(v,k);
const object=(v,where)=>{if(!v || typeof v!=='object'||Array.isArray(v))bad(where+' must be an object.');return v;};
const keys=(v,allowed,where)=>{
  object(v,where);
  for(const key of Object.keys(v))if(!allowed.includes(key))bad(where+' contains unsupported field: '+key.slice(0,50));
};
const text=(v,where,max=500,empty=true)=>{
  if(typeof v!=='string'||v.length>max||(!empty&&!v.trim())||
     /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(v)||
     /<\/?[a-z][^>]*>/i.test(v)||
     /(?:javascript:|data:|file:|\\\\|[a-z]:[\\/])/i.test(v))
    bad(where+' contains unsafe or invalid text.');
  return v;
};
const id=(v,where)=>{text(v,where,128,false);if(!/^[\w.:-]+$/.test(v))bad(where+' contains an invalid identifier.');return v;};
const str=(v,k,where,max=500)=>{if(own(v,k))text(v[k],where+'.'+k,max);};
const bool=(v,k,where)=>{if(own(v,k)&&typeof v[k]!=='boolean')bad(where+'.'+k+' must be boolean.');};
const number=(v,k,where)=>{if(own(v,k)&&(!Number.isSafeInteger(v[k])||v[k]<0||v[k]>5256000))bad(where+'.'+k+' must be a nonnegative integer.');};
const planDate=(value,where)=>{
  if(value==='')return;
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))bad(where+' must be an ISO calendar date.');
  const [year,month,day]=value.split('-').map(Number);
  if(year<1)bad(where+' is not a valid calendar date.');
  const date=new Date(0);
  date.setUTCFullYear(year,month-1,day);
  if(date.getUTCFullYear()!==year||date.getUTCMonth()!==month-1||date.getUTCDate()!==day)
    bad(where+' is not a valid calendar date.');
};
const arr=(v,where,max)=>{if(!Array.isArray(v)||v.length>max)bad(where+' has invalid size.');return v;};
const unique=(rows,where)=>{
  const seen=new Set();
  for(const row of rows){if(seen.has(row.id))bad(where+' has duplicate IDs.');seen.add(row.id);}
};
function labels(rows,where){
  arr(rows,where,200);
  for(const [i,item] of rows.entries()) {
    keys(item,['id','name','color'],where+'['+i+']');
    id(item.id,where+'.id');text(item.name,where+'.name',100,false);
    text(item.color,where+'.color',30,false);
    if(!/^#[0-9a-fA-F]{6}$/.test(item.color))bad(where+' has invalid color.');
  }
  unique(rows,where);
}
function stage(row,where) {
  keys(row,['id','label','subtitle','color','archived'],where);
  id(row.id,where+'.id');text(row.label,where+'.label',180,false);
  str(row,'subtitle',where,300);str(row,'color',where,30);
  bool(row,'archived',where);
}
function checkItem(row,where) {
  keys(row,['id','text','done','title','completedAt'],where);
  id(row.id,where+'.id');
  str(row,'text',where,10000);str(row,'title',where,10000);
  str(row,'completedAt',where,60);bool(row,'done',where);
}
function task(row,where) {
  keys(row,['id','projectId','boardId','listId','status','title','description','priority',
    'completed','dueDate','labels','labelIds','labelColors','checklist','checklists','archived',
    'deleted','cardOrder','estimatedMinutes','actualMinutes','createdAt','updatedAt',
    'assignees','reports','dependencies','watchers','plannedStart','startedAt','completedAt',
    'position','archivedByBoard','calendarSourceKey','source','cover','customFieldValues','plannedEnd'],where);
  for(const required of ['id','projectId','boardId','title','checklist','labels'])if(!own(row,required))bad(where+' missing '+required);
  id(row.id,where+'.id');id(row.projectId,where+'.projectId');id(row.boardId,where+'.boardId');
  for(const field of ['listId','status','priority'])if(own(row,field))id(row[field],where+'.'+field);
  text(row.title,where+'.title',300);
  for(const [field,max] of Object.entries({description:10000,dueDate:60,createdAt:60,
    updatedAt:60,plannedStart:60,startedAt:60,completedAt:60,calendarSourceKey:128,source:128}))
    str(row,field,where,max);
  for(const field of ['completed','archived','deleted','archivedByBoard'])bool(row,field,where);
  for(const field of ['plannedStart','plannedEnd'])if(own(row,field))planDate(row[field],where+'.'+field);
  if(row.plannedStart&&row.plannedEnd&&row.plannedStart>row.plannedEnd)
    bad(where+' has plannedEnd before plannedStart.');
  for(const field of ['cardOrder','estimatedMinutes','actualMinutes','position'])number(row,field,where);
  arr(row.labels,where+'.labels',200).forEach((label,i)=>text(label,where+'.labels['+i+']',100,false));
  for(const field of ['labelIds','assignees','dependencies','watchers']){
    if(own(row,field))arr(row[field],where+'.'+field,200).forEach((value,i)=>id(value,where+'.'+field+'['+i+']'));
  }
  if(own(row,'labelColors')){
    object(row.labelColors,where+'.labelColors');
    if(Object.keys(row.labelColors).length>200)bad(where+' has too many label colors.');
    for(const [name,color] of Object.entries(row.labelColors)){
      text(name,where+'.labelColors',100,false);
      if(typeof color!=='string'||!/^#[a-fA-F0-9]{6}$/.test(color))bad(where+' has invalid label color.');
    }
  }
  if(own(row,'cover')&&row.cover!==null){
    keys(row.cover,['type','color','size'],where+'.cover');
    if(row.cover.type!=='color'||typeof row.cover.color!=='string'||
       !/^#[0-9a-fA-F]{6}$/.test(row.cover.color)||
       !['strip','full'].includes(row.cover.size))
      bad(where+' has an unsupported cover.');
  }
  if(own(row,'customFieldValues')&&Object.keys(object(row.customFieldValues,
    where+'.customFieldValues')).length)
    bad(where+' contains unverified custom fields.');
  arr(row.checklist,where+'.checklist',300).forEach((item,i)=>checkItem(item,where+'.checklist['+i+']'));
  unique(row.checklist,where+'.checklist');
  if(own(row,'checklists')){
    arr(row.checklists,where+'.checklists',30).forEach((group,i)=>{
      const at=where+'.checklists['+i+']';
      keys(group,['id','name','items'],at);id(group.id,at+'.id');text(group.name,at+'.name',180,false);
      arr(group.items,at+'.items',300).forEach((item,j)=>checkItem(item,at+'.items['+j+']'));
      unique(group.items,at+'.items');
    });
    unique(row.checklists,where+'.checklists');
  }
  if(own(row,'reports')){
    arr(row.reports,where+'.reports',200).forEach((report,i)=>{
      const at=where+'.reports['+i+']';
      keys(report,['id','agent','summary','createdAt'],at);
      id(report.id,at+'.id');text(report.agent,at+'.agent',160,false);
      text(report.summary,at+'.summary',2000,false);
      str(report,'createdAt',at,60);
    });
    unique(row.reports,where+'.reports');
  }
}
function validateSnapshot(state) {
  keys(state,['version','workspaces','boards','projects','tasks','stages','settings'],'state');
  if(state.version!==1)bad('Unsupported state version.');
  for(const [name,max] of Object.entries({workspaces:200,boards:1000,projects:1000,tasks:20000,stages:200}))
    arr(state[name],'state.'+name,max);
  state.workspaces.forEach((item,i)=>{
    const w='workspaces['+i+']';keys(item,['id','name','archived'],w);
    id(item.id,w+'.id');text(item.name,w+'.name',180,false);bool(item,'archived',w);
  });
  state.projects.forEach((item,i)=>{
    const w='projects['+i+']';keys(item,['id','name','color','archived'],w);
    id(item.id,w+'.id');text(item.name,w+'.name',180);str(item,'color',w,30);bool(item,'archived',w);
  });
  state.stages.forEach((item,i)=>stage(item,'stages['+i+']'));
  state.boards.forEach((item,i)=>{
    const w='boards['+i+']';
    keys(item,['id','workspaceId','projectId','name','color','archived','stages','labelDefinitions','customFields'],w);
    id(item.id,w+'.id');id(item.workspaceId,w+'.workspaceId');
    if(item.projectId!==null)id(item.projectId,w+'.projectId');
    text(item.name,w+'.name',180,false);str(item,'color',w,30);bool(item,'archived',w);
    arr(item.stages,w+'.stages',200).forEach((entry,j)=>stage(entry,w+'.stages['+j+']'));
    unique(item.stages,w+'.stages');
    if(own(item,'labelDefinitions'))labels(item.labelDefinitions,w+'.labelDefinitions');
    if(own(item,'customFields'))arr(item.customFields,w+'.customFields',0);
  });
  state.tasks.forEach((item,i)=>task(item,'tasks['+i+']'));
  for(const name of ['workspaces','projects','boards','tasks','stages'])unique(state[name],name);
  keys(state.settings,['theme','themeForAllUsers','googleClientId','priorityDefinitions',
    'labelLibrary'],'settings');
  if(own(state.settings,'theme'))text(state.settings.theme,'settings.theme',30);
  bool(state.settings,'themeForAllUsers','settings');
  // Client seed may send an empty OAuth public ID; never store a nonempty credential/config ID.
  if(own(state.settings,'googleClientId')&&state.settings.googleClientId!=='')bad('External integration settings are local-only.');
  if(own(state.settings,'labelLibrary'))labels(state.settings.labelLibrary,'settings.labelLibrary');
  if(own(state.settings,'priorityDefinitions')){
    arr(state.settings.priorityDefinitions,'settings.priorityDefinitions',30).forEach((item,i)=>{
      const w='settings.priorityDefinitions['+i+']';
      keys(item,['id','label','color','effect'],w);id(item.id,w+'.id');
      text(item.label,w+'.label',100,false);str(item,'color',w,30);str(item,'effect',w,30);
    });
    unique(state.settings.priorityDefinitions,'settings.priorityDefinitions');
  }
  const projects=new Set(state.projects.map(x=>x.id));
  const workspaces=new Set(state.workspaces.map(x=>x.id));
  const boards=new Map(state.boards.map(x=>[x.id,x]));
  const tasks=new Map(state.tasks.map(x=>[x.id,x]));
  const successors=new Map(state.tasks.map(x=>[x.id,[]]));
  const indegree=new Map(state.tasks.map(x=>[x.id,0]));
  for(const board of state.boards){
    if(!workspaces.has(board.workspaceId)||board.projectId!==null&&!projects.has(board.projectId))
      bad('Board references missing workspace/project.');
  }
  for(const entry of state.tasks){
    const board=boards.get(entry.boardId);
    if(!projects.has(entry.projectId)||!board||board.projectId!==entry.projectId)
      bad('Task references missing or mismatched project/board.');
    if(entry.listId && !board.stages.some(x=>x.id===entry.listId) &&
       !state.stages.some(x=>x.id===entry.listId))
      bad('Task references missing list.');
    const seen=new Set();
    if((entry.dependencies||[]).length>128)bad('Task has too many dependencies.');
    for(const dependency of entry.dependencies||[]){
      const predecessor=tasks.get(dependency);
      if(dependency===entry.id||seen.has(dependency)||!predecessor||
        predecessor.projectId!==entry.projectId||predecessor.deleted===true||
        entry.deleted===true)bad('Task has invalid dependency.');
      seen.add(dependency);
      successors.get(dependency).push(entry.id);
      indegree.set(entry.id,indegree.get(entry.id)+1);
    }
  }
  const queue=[...indegree].filter(([,degree])=>degree===0).map(([id])=>id);
  let processed=0;
  for(let i=0;i<queue.length;i++){
    processed++;
    for(const next of successors.get(queue[i])){
      const degree=indegree.get(next)-1;
      indegree.set(next,degree);
      if(degree===0)queue.push(next);
    }
  }
  if(processed!==state.tasks.length)bad('Task dependency cycle detected.');
  if(Buffer.byteLength(JSON.stringify(state),'utf8')>16*1024*1024)
    throw new ValidationError('Workspace is too large.',413,'payload_too_large');
  return state;
}
function projectFor(taskRow,allowed) {return allowed===null || allowed.has(taskRow.projectId);}
function projectScope(user) {
  return user.project_ids_json===null ? null : new Set(JSON.parse(user.project_ids_json));
}
function projectSnapshot(state,user) {
  const allowed=projectScope(user);
  if(allowed===null)return state;
  const projects=state.projects.filter(p=>allowed.has(p.id));
  const boards=state.boards.filter(b=>allowed.has(b.projectId));
  const wids=new Set(boards.map(b=>b.workspaceId));
  const visibleTasks=state.tasks.filter(t=>projectFor(t,allowed));
  const visibleIds=new Set(visibleTasks.map(t=>t.id));
  return {...state,projects,boards,workspaces:state.workspaces.filter(w=>wids.has(w.id)),
    tasks:visibleTasks.map(t=>t.dependencies
      ?{...t,dependencies:t.dependencies.filter(id=>visibleIds.has(id))}:t)};
}
function mergeEditor(current,incoming,user) {
  const scoped=projectSnapshot(current,user);
  for(const name of ['workspaces','boards','projects','stages','settings'])
    if(canonical(scoped[name])!==canonical(incoming[name]))
      throw new ValidationError('Editor cannot modify workspace structure.',403,'insufficient_permissions');
  const grant=projectScope(user);
  const old=new Map(current.tasks.map(t=>[t.id,t]));
  const visibleIds=new Set(scoped.tasks.map(t=>t.id));
  for(const taskRow of incoming.tasks){
    const previous=old.get(taskRow.id);
    if(!projectFor(taskRow,grant) || previous && (
      !projectFor(previous,grant) || previous.projectId!==taskRow.projectId))
      throw new ValidationError('Task project is outside the editor grant.',403,'insufficient_permissions');
  }
  const incomingById=new Map(incoming.tasks.map(t=>[t.id,t]));
  const mergedTasks=current.tasks.flatMap(t=>{
    if(!projectFor(t,grant))return [t];
    const replacement=incomingById.get(t.id);
    if(!replacement)return [];
    // Out-of-scope dependency IDs were hidden from the editor's GET response.
    // Carry those existing references forward while applying visible changes.
    const hidden=(t.dependencies||[]).filter(id=>!visibleIds.has(id));
    return [hidden.length?{...replacement,
      dependencies:[...new Set([...(replacement.dependencies||[]),...hidden])]}:replacement];
  });
  for(const row of incoming.tasks)if(!old.has(row.id))mergedTasks.push(row);
  const merged={...current,tasks:mergedTasks};
  // Never turn an omitted out-of-scope task into a deletion.
  validateSnapshot(merged);
  return merged;
}
module.exports={ValidationError,validateSnapshot,projectSnapshot,mergeEditor};
