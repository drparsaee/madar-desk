// Task analytics deliberately exclude confidential finance and server-only fields.
export const dateKey=value=>{
  if(typeof value!=='string')return '';
  const match=/^(\d{4})-(\d\d)-(\d\d)/.exec(value);
  if(!match)return '';
  const year=Number(match[1]),month=Number(match[2]),day=Number(match[3]);
  const date=new Date(Date.UTC(year,month-1,day));
  return date.getUTCFullYear()===year&&date.getUTCMonth()===month-1&&date.getUTCDate()===day?match[0]:'';
};
const safeText=value=>String(value??'').slice(0,10000);
export const reportRows=(tasks=[],projects=[],stages=[],options={})=>{
  const projectName=new Map(projects.map(p=>[p.id,p.name]));
  const stageName=new Map(stages.map(s=>[s.id,s.label]));
  const start=dateKey(options.start||''),end=dateKey(options.end||'');
  return tasks.filter(t=>!t.archived).filter(t=>{
    if(options.projectId&&t.projectId!==options.projectId)return false;
    if(options.priority&&options.priority!=='all'&&t.priority!==options.priority)return false;
    const when=dateKey(t.dueDate||t.createdAt);
    if(start&&(!when||when<start))return false;
    if(end&&(!when||when>end))return false;
    return true;
  }).map(t=>{
    const count=(t.checklist||[]).length;
    const done=(t.checklist||[]).filter(item=>item.done).length;
    return {id:safeText(t.id),title:safeText(t.title),project:safeText(projectName.get(t.projectId)||'نامشخص'),
      status:safeText(stageName.get(t.listId)||stageName.get(t.status)||t.status),
      completed:t.status==='done',
      priority:safeText(t.priority),createdAt:dateKey(t.createdAt),dueDate:dateKey(t.dueDate),
      estimatedMinutes:Math.max(0,Number(t.estimatedMinutes)||0),actualMinutes:Math.max(0,Number(t.actualMinutes)||0),
      checklistCount:count,completedSteps:done,progress:count?Math.round(done/count*100):0,
      assignees:(Array.isArray(t.assignees)?t.assignees:[]).map(safeText).join('، '),
      labels:(Array.isArray(t.labels)?t.labels:[]).map(safeText).join('، ')};
  });
};
export const summarizeRows=rows=>{
  const result={tasks:rows.length,done:0,overdue:0,estimatedMinutes:0,actualMinutes:0,completedSteps:0,totalSteps:0,byProject:[]};
  const groups=new Map(),today=dateKey(new Date().toISOString());
  for(const row of rows){
    if(row.completed)result.done++;
    if(row.dueDate&&row.dueDate<today&&!row.completed)result.overdue++;
    result.estimatedMinutes+=row.estimatedMinutes;
    result.actualMinutes+=row.actualMinutes;
    result.completedSteps+=row.completedSteps;
    result.totalSteps+=row.checklistCount;
    const group=groups.get(row.project)||{name:row.project,count:0,estimate:0,actual:0};
    group.count++;group.estimate+=row.estimatedMinutes;group.actual+=row.actualMinutes;
    groups.set(row.project,group);
  }
  result.byProject=[...groups.values()].sort((a,b)=>b.count-a.count||a.name.localeCompare(b.name));
  return result;
};
const csvCell=value=>{
  let text=safeText(value);
  // Spreadsheet formula injection applies even to quoted CSV cells.
  if(/^[\s\u0000-\u001f]*[=+\-@\t\r\n]/u.test(text))text="'"+text;
  return '"'+text.replace(/"/g,'""')+'"';
};
export const taskReportCsv=rows=>{
  const names=['عنوان','پروژه','مرحله','اولویت','تاریخ ایجاد','سررسید','برآورد دقیقه','واقعی دقیقه','درصد مراحل','مسئولان','برچسب‌ها'];
  const keys=['title','project','status','priority','createdAt','dueDate','estimatedMinutes','actualMinutes','progress','assignees','labels'];
  return '\ufeff'+[names,...rows.map(row=>keys.map(k=>row[k]))].map(values=>values.map(csvCell).join(',')).join('\r\n')+'\r\n';
};
export const timelineBuckets=rows=>Object.entries(rows.filter(x=>x.dueDate).reduce((all,row)=>{
  (all[row.dueDate]??=[]).push(row);return all;
},{})).sort(([a],[b])=>a.localeCompare(b)).map(([day,items])=>({day,items}));
