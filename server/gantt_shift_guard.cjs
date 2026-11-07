'use strict';

// Host-side pure preflight for an eventual atomic batch Gantt endpoint.
// The caller MUST use the full current host snapshot, trusted ACL and revision
// inside the same locked/transactional commit. This module never persists data.
const DAY=86400000;
class GanttShiftError extends Error {
  constructor(code){super(code);this.name='GanttShiftError';this.code=code;}
}
const deny=code=>{throw new GanttShiftError(code);};
const own=(v,key)=>Object.prototype.hasOwnProperty.call(v,key);
const dayNumber=value=>{
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
  const [year,month,day]=value.split('-').map(Number);
  if(year<1)return null;
  const date=new Date(0);
  date.setUTCFullYear(year,month-1,day);
  return date.getUTCFullYear()===year&&date.getUTCMonth()===month-1&&
    date.getUTCDate()===day?Math.floor(date.getTime()/DAY):null;
};
const shifted=(task,days)=>{
  const start=dayNumber(task.plannedStart),end=dayNumber(task.plannedEnd);
  if(start===null||end===null||end<start)deny('missing_plan');
  const to={plannedStart:new Date((start+days)*DAY).toISOString().slice(0,10),
    plannedEnd:new Date((end+days)*DAY).toISOString().slice(0,10)};
  if(dayNumber(to.plannedStart)===null||dayNumber(to.plannedEnd)===null)
    deny('date_range');
  return to;
};

function prepareGanttShift(state,request,{role,projects,actualRevision}={}) {
  if(!state||!Array.isArray(state.tasks)||!request||
     typeof request!=='object'||Array.isArray(request)||
     Object.keys(request).sort().join(',')!=='days,expectedRevision,taskId'||
     typeof request.taskId!=='string'||!request.taskId||
     !Number.isSafeInteger(request.days)||request.days===0||
     Math.abs(request.days)>3660||
     typeof request.expectedRevision!=='string'||!request.expectedRevision)
    deny('invalid_request');
  if(role!=='admin'&&role!=='editor')deny('forbidden');
  if(typeof actualRevision!=='string'||!actualRevision)deny('invalid_state');
  if(request.expectedRevision!==actualRevision)deny('stale_revision');
  if(projects!==null&&!Array.isArray(projects))deny('forbidden');
  const ids=new Map();
  for(const task of state.tasks) {
    if(!task||typeof task.id!=='string'||!task.id||ids.has(task.id))
      deny('invalid_state');
    ids.set(task.id,task);
  }
  const source=ids.get(request.taskId);
  if(!source||source.deleted||source.archived)deny('unavailable_target');
  const pid=source.projectId;
  if(typeof pid!=='string'||!pid)deny('invalid_state');
  if(projects!==null&&!projects.includes(pid))deny('forbidden');
  const group=state.tasks.filter(t=>t.projectId===pid&&!t.deleted&&!t.archived);
  if(group.length>20000)deny('too_many');
  const byId=new Map(group.map(t=>[t.id,t]));
  const children=new Map(group.map(t=>[t.id,[]]));
  const indegree=new Map(group.map(t=>[t.id,0]));
  const bounds=new Map();
  let existingConflict=false;
  for(const task of group) {
    const a=dayNumber(task.plannedStart),b=dayNumber(task.plannedEnd);
    if(a===null||b===null||b<a)deny('missing_plan');
    if(own(task,'dependencies')&&!Array.isArray(task.dependencies))
      deny('invalid_dependency');
    bounds.set(task.id,{start:a,end:b});
  }
  for(const task of group) {
    const a=bounds.get(task.id).start;
    const used=new Set();
    for(const dep of task.dependencies||[]) {
      if(typeof dep!=='string'||used.has(dep)||dep===task.id)
        deny('invalid_dependency');
      used.add(dep);
      const parent=byId.get(dep);
      if(!parent)deny('outside_project');
      if(a<=bounds.get(parent.id).end)existingConflict=true;
      children.get(dep).push(task.id);
      indegree.set(task.id,indegree.get(task.id)+1);
    }
  }
  const queue=[...indegree.keys()].filter(id=>indegree.get(id)===0).sort();
  const order=[];
  for(let i=0;i<queue.length;i++){
    const id=queue[i];order.push(id);
    for(const child of children.get(id)) {
      indegree.set(child,indegree.get(child)-1);
      if(indegree.get(child)===0)queue.push(child);
    }
  }
  if(order.length!==group.length)deny('dependency_cycle');
  if(existingConflict)deny('existing_conflict');
  const proposals=new Map([[source.id,shifted(source,request.days)]]);
  for(const id of order) {
    if(id===source.id)continue;
    const task=byId.get(id);
    if(!(task.dependencies||[]).some(parent=>proposals.has(parent)))continue;
    let required=dayNumber(task.plannedStart);
    for(const dep of task.dependencies||[]) {
      const parent=byId.get(dep),after=proposals.get(dep);
      required=Math.max(required,dayNumber(after?.plannedEnd||parent.plannedEnd)+1);
    }
    const offset=required-dayNumber(task.plannedStart);
    if(offset>0)proposals.set(id,shifted(task,offset));
    if(proposals.size>500)deny('too_many');
  }
  const sourceStart=dayNumber(proposals.get(source.id).plannedStart);
  for(const id of source.dependencies||[]) {
    if(sourceStart<=dayNumber(byId.get(id).plannedEnd))
      deny('earlier_than_predecessor');
  }
  // A hidden/outside-project/archived dependent cannot silently be left behind.
  for(const task of state.tasks) {
    if(byId.has(task.id))continue;
    const deps=task.dependencies||[];
    if(!Array.isArray(deps))deny('invalid_dependency');
    if(deps.some(dep=>proposals.has(dep)))deny('outside_project');
  }
  const updates=[...proposals].map(([id,to])=>({id,...to}));
  const nextState={...state,tasks:state.tasks.map(t=>
    proposals.has(t.id)?{...t,...proposals.get(t.id)}:t)};
  return {nextState,updates,changedCount:updates.length,scope:'full_host'};
}
module.exports={GanttShiftError,prepareGanttShift};
