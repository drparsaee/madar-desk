import React,{useMemo} from 'react';
import {Activity,ArrowUpLeft,CalendarDays,CheckCheck,ClipboardCheck,
  FolderKanban,LayoutDashboard,Layers3,TrendingUp} from 'lucide-react';
import './vitrea_overview.css';

const MONTHS=8;
const faNumber=value=>Number(value||0).toLocaleString('fa-IR');
const validDate=value=>{
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}(?:T|$)/.test(value))return null;
  const iso=value.slice(0,10);
  const timestamp=Date.parse(iso+'T00:00:00Z');
  return Number.isFinite(timestamp)&&new Date(timestamp).toISOString().slice(0,10)===iso?iso:null;
};
const monthId=date=>date.getFullYear()+'-'+String(date.getMonth()+1).padStart(2,'0');

/** A truthful activity series, not a revenue or finance projection. */
export function monthlyTaskActivity(tasks,now=new Date(),months=MONTHS){
  const rows=Array.from({length:months},(_,i)=>{
    const date=new Date(now.getFullYear(),now.getMonth()-(months-1-i),1);
    // Aggregation uses Gregorian YYYY-MM; label the same calendar explicitly.
    return {id:monthId(date),label:new Intl.DateTimeFormat('fa-IR-u-ca-gregory',{month:'short'}).format(date),count:0};
  });
  const byMonth=new Map(rows.map(row=>[row.id,row]));
  for(const task of Array.isArray(tasks)?tasks:[]){
    const iso=validDate(task?.createdAt);
    if(iso){const row=byMonth.get(iso.slice(0,7));if(row)row.count++;}
  }
  return rows;
}

export function overviewTaskSummary(tasks,projects,stages,now=new Date()){
  const visible=(Array.isArray(tasks)?tasks:[]).filter(task=>task&&task.deleted!==true&&task.archived!==true);
  const stageList=Array.isArray(stages)?stages:[];
  const stageOf=task=>stageList.find(stage=>stage.id===(task.listId||task.status))
    ||stageList.find(stage=>stage.id===task.status);
  const isCompleted=task=>task.status==='done'||
    /(?:تمام|تکمیل|انجام[‌ ]?شد)/.test(stageOf(task)?.label||'');
  const isReview=task=>task.status==='review'||/بررسی|تأیید/.test(stageOf(task)?.label||'');
  const completed=visible.filter(isCompleted).length;
  const reviews=visible.filter(task=>!isCompleted(task)&&isReview(task));
  const today=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),
    String(now.getDate()).padStart(2,'0')].join('-');
  const due=visible.filter(task=>!isCompleted(task)&&validDate(task.dueDate)===today);
  const newest=[...visible].sort((a,b)=>String(b.updatedAt||b.createdAt||'')
    .localeCompare(String(a.updatedAt||a.createdAt||'')));
  const projectRows=(Array.isArray(projects)?projects:[]).map(project=>{
    const cards=visible.filter(task=>task.projectId===project.id);
    const done=cards.filter(isCompleted).length;
    return {project,count:cards.length,done};
  });
  const laneRows=stageList.filter(stage=>stage.archived!==true).map(stage=>({
    stage,count:visible.filter(task=>(task.listId||task.status)===stage.id).length
  }));
  return {total:visible.length,completed,reviewCount:reviews.length,
    active:visible.length-completed,projects:projectRows,lanes:laneRows,
    reviews:reviews.slice(0,4),due:due.slice(0,4),recent:newest.slice(0,5)};
}

function TaskAction({task,onOpen,secondary}){
  return <button type="button" className="vitrea-overview-task" onClick={()=>onOpen?.(task.id)}>
    <span className="vitrea-overview-task__dot" aria-hidden="true"/>
    <span className="vitrea-overview-task__content"><strong>{task.title||'کار بدون عنوان'}</strong>
      <small>{secondary||task.description||'مشاهده و ویرایش کار'}</small></span>
    <ArrowUpLeft size={15} aria-hidden="true"/>
  </button>;
}

export function VitreaOverview({tasks=[],projects=[],stages=[],onOpenTask,onSelectProject}){
  const summary=useMemo(()=>overviewTaskSummary(tasks,projects,stages),[tasks,projects,stages]);
  const months=useMemo(()=>monthlyTaskActivity(tasks),[tasks]);
  const chartMax=Math.max(1,...months.map(row=>row.count));
  const stageMax=Math.max(1,...summary.lanes.map(row=>row.count));
  return <section className="vitrea-overview" dir="rtl" aria-label="نمای کلی فضای کار">
    <div className="vitrea-overview-kpis">
      <div className="vitrea-overview-kpi"><span className="vitrea-overview-kpi__icon"><LayoutDashboard size={19}/></span>
        <span><strong>{faNumber(summary.total)}</strong><small>کل کارهای این نما</small></span></div>
      <div className="vitrea-overview-kpi"><span className="vitrea-overview-kpi__icon"><Activity size={19}/></span>
        <span><strong>{faNumber(summary.active)}</strong><small>کارهای تکمیل‌نشده</small></span></div>
      <div className="vitrea-overview-kpi"><span className="vitrea-overview-kpi__icon"><CheckCheck size={19}/></span>
        <span><strong>{faNumber(summary.completed)}</strong><small>کارهای انجام‌شده</small></span></div>
    </div>

    <div className="vitrea-overview-grid">
      <article className="vitrea-overview-panel vitrea-overview-panel--wide">
        <div className="vitrea-overview-panel__heading"><div><span>روند فعالیت</span><small>تعداد کارهای ثبت‌شده در ۸ ماه اخیر</small></div>
          <span className="vitrea-overview-panel__icon"><TrendingUp size={18}/></span></div>
        <div className="vitrea-overview-chart-title"><strong>{faNumber(months.reduce((sum,row)=>sum+row.count,0))}</strong>
          <small>کار ثبت‌شده در بازهٔ نمودار</small></div>
        <div className="vitrea-overview-month-chart" role="img"
          aria-label={'آمار کارهای ساخته‌شده در ماه‌های اخیر: '+months.map(row=>row.id+': '+row.count).join('، ')}>
          {months.map(row=><div key={row.id} className="vitrea-overview-month-chart__month">
            <div className="vitrea-overview-month-chart__track">
              <span style={{height:Math.max(row.count?4:0,row.count/chartMax*100)+'%'}}/>
            </div><small>{row.label}</small></div>)}
        </div>
        {!months.some(row=>row.count>0)&&<p className="vitrea-overview-muted">هنوز کاری با تاریخ ایجاد معتبر در این بازه ثبت نشده است.</p>}
      </article>

      <article className="vitrea-overview-panel vitrea-overview-panel--stages">
        <div className="vitrea-overview-panel__heading"><div><span>مراحل کار</span><small>توزیع واقعی کارت‌ها در مراحل فعال</small></div>
          <Layers3 size={18}/></div>
        <div className="vitrea-overview-stage-list">
          {summary.lanes.map(({stage,count})=><div className="vitrea-overview-stage" key={stage.id}>
            <div><span>{stage.label}</span><strong>{faNumber(count)}</strong></div>
            <div className="vitrea-overview-stage__track"><span style={{width:(count/stageMax*100)+'%',background:stage.color||'#82b5f8'}}/></div>
          </div>)}
          {!summary.lanes.length&&<p className="vitrea-overview-muted">مرحلهٔ فعالی وجود ندارد.</p>}
        </div>
      </article>
    </div>

    <article className="vitrea-overview-panel vitrea-overview-projects">
      <div className="vitrea-overview-panel__heading"><div><span>پروژه‌های من</span><small>وضعیت زندهٔ کارت‌ها در پروژه‌های این فضای کاری</small></div>
        <FolderKanban size={18}/></div>
      <div className="vitrea-overview-project-grid">
        {summary.projects.slice(0,8).map(({project,count,done},index)=><button
          type="button" key={project.id} className={'vitrea-overview-project tone-'+index%6}
          onClick={()=>onSelectProject?.(project.id)}>
            <span className="vitrea-overview-project__top"><span className="vitrea-overview-project__symbol"><FolderKanban size={17}/></span>
              <ArrowUpLeft size={17}/></span>
            <strong>{project.name}</strong><small>{faNumber(count)} کارت</small>
            <span className="vitrea-overview-project__bottom"><b>{faNumber(done)} تکمیل‌شده</b>
              <span>{count?faNumber(Math.round(done/count*100)):'۰'}٪</span></span>
            <span className="vitrea-overview-project__track"><span style={{width:(count?done/count*100:0)+'%'}}/></span>
          </button>)}
        {!summary.projects.length&&<p className="vitrea-overview-muted">هنوز پروژه‌ای در این فضای کاری وجود ندارد.</p>}
      </div>
    </article>

    <div className="vitrea-overview-grid vitrea-overview-grid--three">
      <article className="vitrea-overview-panel">
        <div className="vitrea-overview-panel__heading"><div><span>منتظر بررسی</span><small>{faNumber(summary.reviewCount)} کار نیازمند توجه</small></div>
          <ClipboardCheck size={18}/></div>
        <div className="vitrea-overview-task-list">{summary.reviews.map(task=><TaskAction key={task.id} task={task} onOpen={onOpenTask}/>)}
          {!summary.reviews.length&&<p className="vitrea-overview-muted">کاری در انتظار بررسی نیست.</p>}</div>
      </article>
      <article className="vitrea-overview-panel">
        <div className="vitrea-overview-panel__heading"><div><span>امروز</span><small>کارهای دارای سررسید امروز</small></div>
          <CalendarDays size={18}/></div>
        <div className="vitrea-overview-task-list">{summary.due.map(task=><TaskAction key={task.id} task={task} onOpen={onOpenTask}/>)}
          {!summary.due.length&&<p className="vitrea-overview-muted">کاری با سررسید امروز وجود ندارد.</p>}</div>
      </article>
      <article className="vitrea-overview-panel">
        <div className="vitrea-overview-panel__heading"><div><span>آخرین کارها</span><small>مرتب‌شده بر اساس زمان ثبت یا ویرایش</small></div>
          <Activity size={18}/></div>
        <div className="vitrea-overview-task-list">{summary.recent.map(task=><TaskAction key={task.id} task={task} onOpen={onOpenTask}/>)}
          {!summary.recent.length&&<p className="vitrea-overview-muted">هنوز کار فعالی وجود ندارد.</p>}</div>
      </article>
    </div>
  </section>;
}
