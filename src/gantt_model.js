// Pure, host-agnostic read model. Planning dates are calendar days, not work minutes.
const DAY=86400000;
const utcStamp=(year,month,day)=>{
  const date=new Date(0);
  date.setUTCFullYear(year,month,day);
  return date.getTime();
};
export function dayNumber(value) {
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
  const [y,m,d]=value.split('-').map(Number);
  if(y<1)return null;
  const stamp=utcStamp(y,m-1,d),date=new Date(stamp);
  return date.getUTCFullYear()===y&&date.getUTCMonth()===m-1&&date.getUTCDate()===d
    ?Math.floor(stamp/DAY):null;
}
export const dayString=number=>new Date(number*DAY).toISOString().slice(0,10);
export function validPlan(start='',end='') {
  const a=start===''?null:dayNumber(start),b=end===''?null:dayNumber(end);
  return (a!==null||start==='')&&(b!==null||end==='')&&
    (a===null||b===null||a<=b);
}
/** Reject invalid partial date edits before they reach autosave or offline sync.
 * Unrelated card edits do not retroactively rewrite legacy planning fields.
 */
export function validPlanningPatch(task,patch) {
  if(!patch||typeof patch!=='object')return false;
  if(!Object.hasOwn(patch,'plannedStart')&&!Object.hasOwn(patch,'plannedEnd'))return true;
  const start=Object.hasOwn(patch,'plannedStart')?patch.plannedStart:(task?.plannedStart||'');
  const end=Object.hasOwn(patch,'plannedEnd')?patch.plannedEnd:(task?.plannedEnd||'');
  return typeof start==='string'&&typeof end==='string'&&validPlan(start,end);
}
export function shiftPlan(task,days) {
  const a=dayNumber(task.plannedStart),b=dayNumber(task.plannedEnd);
  if(a===null||b===null||!Number.isSafeInteger(days))return null;
  const plannedStart=dayString(a+days),plannedEnd=dayString(b+days);
  return dayNumber(plannedStart)===null||dayNumber(plannedEnd)===null
    ?null:{plannedStart,plannedEnd};
}

/** P2 schedule diagnostics for only the cards the current reader can see.
 * A predecessor hidden by ACL/filtering is UNKNOWN, never assumed completed.
 * Suggested shifts preserve duration and affect one card only; no cascade.
 */
export function inspectGanttDependencies(tasks=[]) {
  if(!Array.isArray(tasks))throw Error('Invalid Gantt card collection');
  const active=tasks.filter(t=>t&&!t.deleted&&!t.archived);
  const byId=new Map(active.map(t=>[t.id,t]));
  const byTask=new Map();
  let overlaps=0,unknownDates=0,outsideView=0;
  for(const task of active){
    const start=dayNumber(task.plannedStart),end=dayNumber(task.plannedEnd);
    const conflicts=[];
    let incomplete=0,hidden=0,latestPredecessorEnd=null;
    const dependencies=Array.isArray(task.dependencies)?new Set(task.dependencies):new Set();
    for(const dependencyId of dependencies){
      const predecessor=byId.get(dependencyId);
      // The full task set is already ACL-filtered by its caller. Never look up
      // missing predecessors in unfiltered host data or display their IDs.
      if(!predecessor||predecessor.projectId!==task.projectId||dependencyId===task.id){
        outsideView++;hidden++;continue;
      }
      const priorEnd=dayNumber(predecessor.plannedEnd);
      if(start===null||end===null||start>end||priorEnd===null||
          !validPlan(predecessor.plannedStart||'',predecessor.plannedEnd||'')){
        unknownDates++;incomplete++;continue;
      }
      latestPredecessorEnd=Math.max(latestPredecessorEnd??priorEnd,priorEnd);
      if(start<=priorEnd){
        overlaps++;
        conflicts.push({predecessorId:dependencyId,title:String(predecessor.title||'بدون عنوان'),
          predecessorEnd:predecessor.plannedEnd});
      }
    }
    // When any predecessor is hidden or undated, offering a one-card repair
    // would incorrectly imply that all dependencies have been checked.
    const days=latestPredecessorEnd===null||start===null?0:latestPredecessorEnd+1-start;
    const suggestion=conflicts.length&&hidden===0&&incomplete===0&&days>0
      ?shiftPlan(task,days):null;
    byTask.set(task.id,{conflicts,hidden,incomplete,suggestion});
  }
  return {overlaps,conflictingCards:[...byTask.values()].filter(x=>x.conflicts.length).length,
    unknownDates,outsideView,byTask};
}

/** A deterministic CPM-style read model for the *already-authorized* view.
 * Task duration is the inclusive count of calendar days between planning dates.
 * Intentional calendar gaps, holidays, costs and resource constraints are NOT
 * inferred. A hidden/undated predecessor invalidates its entire project result.
 * This never performs a write or silently edits a dependent card.
 */
export function analyzeCriticalPaths(tasks=[],limit=20000) {
  if(!Array.isArray(tasks))throw Error('Invalid Gantt card collection');
  const projects=new Map();
  for(const item of tasks) {
    if(!item||item.deleted||item.archived)continue;
    const projectId=typeof item.projectId==='string'?item.projectId:'';
    if(!projects.has(projectId))projects.set(projectId,[]);
    projects.get(projectId).push(item);
  }
  const outcomes=[];
  for(const [projectId,cards] of projects) {
    const result={projectId,status:'ready',reason:'',taskCount:cards.length,
      durationDays:null,criticalIds:[],pathIds:[],slackDays:new Map()};
    const abort=reason=>{result.status='partial';result.reason=reason;outcomes.push(result);};
    if(!projectId||cards.length>limit) {
      abort(!projectId?'invalid_project':'too_many');continue;
    }
    const byId=new Map();
    let invalid='';
    for(const card of cards) {
      if(typeof card.id!=='string'||!card.id||byId.has(card.id)) {
        invalid='duplicate_or_invalid_id';break;
      }
      const start=dayNumber(card.plannedStart),end=dayNumber(card.plannedEnd);
      if(start===null||end===null||end<start) {
        invalid='missing_or_invalid_dates';break;
      }
      if(card.dependencies!==undefined&&!Array.isArray(card.dependencies)) {
        invalid='invalid_dependencies';break;
      }
      byId.set(card.id,{card,duration:end-start+1});
    }
    if(invalid){abort(invalid);continue;}
    const inDegree=new Map(),successors=new Map();
    for(const id of byId.keys()){inDegree.set(id,0);successors.set(id,[]);}
    for(const [id,{card}] of byId) {
      const seen=new Set();
      for(const predecessorId of card.dependencies||[]) {
        if(typeof predecessorId!=='string'||seen.has(predecessorId)||
           predecessorId===id){invalid='invalid_dependencies';break;}
        seen.add(predecessorId);
        if(!byId.has(predecessorId)){invalid='outside_authorized_view';break;}
        successors.get(predecessorId).push(id);
        inDegree.set(id,inDegree.get(id)+1);
      }
      if(invalid)break;
    }
    if(invalid){abort(invalid);continue;}
    const queue=[...byId.keys()].filter(id=>!inDegree.get(id)).sort();
    const order=[],earliestStart=new Map(),longestParent=new Map();
    for(const id of byId.keys())earliestStart.set(id,0);
    for(let cursor=0;cursor<queue.length;cursor++) {
      const id=queue[cursor];
      order.push(id);
      const finish=earliestStart.get(id)+byId.get(id).duration;
      for(const next of successors.get(id)) {
        const current=earliestStart.get(next);
        if(finish>current||(finish===current&&
            (longestParent.get(next)===undefined||id<longestParent.get(next)))) {
          earliestStart.set(next,finish);
          longestParent.set(next,id);
        }
        inDegree.set(next,inDegree.get(next)-1);
        if(inDegree.get(next)===0)queue.push(next);
      }
    }
    if(order.length!==cards.length) {
      result.status='cycle';result.reason='dependency_cycle';
      outcomes.push(result);continue;
    }
    const durationDays=Math.max(0,...order.map(id=>
      earliestStart.get(id)+byId.get(id).duration));
    const latestFinish=new Map();
    for(let i=order.length-1;i>=0;i--) {
      const id=order[i],next=successors.get(id);
      latestFinish.set(id,next.length?Math.min(...next.map(successor=>
        latestFinish.get(successor)-byId.get(successor).duration)):durationDays);
      result.slackDays.set(id,latestFinish.get(id)-byId.get(id).duration-earliestStart.get(id));
    }
    result.durationDays=durationDays;
    result.criticalIds=order.filter(id=>result.slackDays.get(id)===0);
    const last=order.filter(id=>earliestStart.get(id)+byId.get(id).duration===durationDays)
      .sort()[0];
    const reversed=[];
    for(let cursor=last;cursor!==undefined;cursor=longestParent.get(cursor))
      reversed.push(cursor);
    result.pathIds=reversed.reverse();
    outcomes.push(result);
  }
  outcomes.sort((a,b)=>a.projectId.localeCompare(b.projectId));
  return {projects:outcomes,complete:outcomes.length>0&&outcomes.every(p=>p.status==='ready')};
}
export function ganttAxis(anchor,scale='day') {
  const day=dayNumber(anchor)??dayNumber(new Date().toISOString().slice(0,10));
  if(scale==='month'){
    const base=new Date(day*DAY);
    const start=new Date(utcStamp(base.getUTCFullYear(),base.getUTCMonth()-3,1));
    return Array.from({length:18},(_,i)=>{
      const a=Math.floor(utcStamp(start.getUTCFullYear(),start.getUTCMonth()+i,1)/DAY);
      const b=Math.floor(utcStamp(start.getUTCFullYear(),start.getUTCMonth()+i+1,1)/DAY);
      return {start:a,end:b,key:dayString(a)};
    });
  }
  const step=scale==='week'?7:1;
  // Shift by calendar days, not local milliseconds; timezone and DST do not affect storage.
  const start=day-(scale==='week'?((new Date(day*DAY).getUTCDay()+1)%7)+42:14);
  return Array.from({length:scale==='week'?24:42},(_,i)=>({
    start:start+i*step,end:start+(i+1)*step,key:dayString(start+i*step)
  }));
}
export function buildGanttRows(tasks,limit=350){
  const active=tasks.filter(t=>t&&!t.deleted&&!t.archived);
  const sorted=active.slice().sort((a,b)=>
    Number(dayNumber(a.plannedStart)===null)-Number(dayNumber(b.plannedStart)===null)||
    (a.plannedStart||'').localeCompare(b.plannedStart||'')||
    String(a.title||'').localeCompare(String(b.title||'')));
  return {rows:sorted.slice(0,limit),total:sorted.length,truncated:sorted.length>limit};
}
export function barPosition(task,axis){
  const start=dayNumber(task.plannedStart),end=dayNumber(task.plannedEnd);
  if(start===null||end===null||start>end||!axis.length)return null;
  const base=axis[0].start,last=axis[axis.length-1].end;
  if(end<base||start>=last)return null;
  const toCell=day=>{
    if(day<=base)return 0;
    if(day>=last)return axis.length;
    const index=axis.findIndex(c=>day>=c.start&&day<c.end);
    return index+(day-axis[index].start)/(axis[index].end-axis[index].start);
  };
  const left=toCell(start),right=toCell(end+1);
  return {left,right,width:right-left,clipped:start<base||end>=last};
}
