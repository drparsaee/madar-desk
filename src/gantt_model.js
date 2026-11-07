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
