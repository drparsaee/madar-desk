import React,{useMemo,useRef,useState} from 'react';
import {CalendarRange,ChevronLeft,ChevronRight,GitBranch} from 'lucide-react';
import {analyzeCriticalPaths,barPosition,buildGanttRows,dayNumber,dayString,ganttAxis,inspectGanttDependencies,previewGanttShiftImpact,shiftPlan,validPlan} from './gantt_model.js';
import './gantt_view.css';

const CELL_WIDTH=44;
const ROW_HEIGHT=118;
const LABEL_WIDTH=276;
const humanDate=(date,calendar)=>new Date(date+'T12:00:00Z').toLocaleDateString(
  calendar==='gregorian'?'fa-IR-u-ca-gregory':'fa-IR-u-ca-persian',
  {year:'numeric',month:'short',day:'numeric',timeZone:'UTC'});
const axisLabel=(entry,scale,calendar)=>scale==='day'?
  humanDate(entry.key,calendar).replace(/\d{4}/g,'').trim():
  humanDate(entry.key,calendar);

/** Read-only by default. Mutations are delivered to the host's existing ACL-enforced save path. */
export function GanttView({tasks=[],calendar='jalali',canEdit=false,onUpdate=()=>{},onOpen=()=>{}}){
  const [scale,setScale]=useState('day'),[member,setMember]=useState(''),[query,setQuery]=useState('');
  const [error,setError]=useState(''),[priority,setPriority]=useState('');
  const [pendingShift,setPendingShift]=useState(null);
  const first=tasks.find(t=>dayNumber(t.plannedStart)!==null)?.plannedStart||
    new Date().toISOString().slice(0,10);
  const [anchor,setAnchor]=useState(first);
  const drag=useRef(null);
  const suppressBarClick=useRef(false);
  const shown=useMemo(()=>tasks.filter(t=>(!member||(t.assignees||[]).includes(member))&&
    (!priority||t.priority===priority)&&(!query||String(t.title||'').toLowerCase().includes(query.trim().toLowerCase()))),
    [tasks,member,priority,query]);
  const {rows,total,truncated}=useMemo(()=>buildGanttRows(shown),[shown]);
  const diagnostics=useMemo(()=>inspectGanttDependencies(rows),[rows]);
  const critical=useMemo(()=>analyzeCriticalPaths(shown),[shown]);
  const criticalById=useMemo(()=>{
    const indexed=new Map();
    for(const project of critical.projects) {
      if(project.status!=='ready')continue;
      const zero=new Set(project.criticalIds);
      for(const [id,slackDays] of project.slackDays)
        indexed.set(id,{critical:zero.has(id),slackDays});
    }
    return indexed;
  },[critical]);
  const shownById=useMemo(()=>new Map(shown.map(task=>[task.id,task])),[shown]);
  const impact=useMemo(()=>pendingShift?
    previewGanttShiftImpact(shown,pendingShift.cardId,pendingShift.days):null,[shown,pendingShift]);
  const staleImpact=Boolean(pendingShift&&impact?.status==='ready'&&
    (impact.source.from.plannedStart!==pendingShift.start||
     impact.source.from.plannedEnd!==pendingShift.end));
  const impactReason={
    unavailable_target:'این کارت دیگر در نمای فعلی قابل بررسی نیست.',
    outside_authorized_view:'همه پیش‌نیازها در نمای فعلی قابل مشاهده نیستند؛ پیش‌نمایش کامل ممکن نیست.',
    invalid_or_missing_plan:'تاریخ‌های برنامه یا شناسه فعالیت‌های این پروژه ناقص یا نامعتبر هستند.',
    invalid_dependencies:'وابستگی تکراری یا نامعتبر وجود دارد؛ ابتدا آن را اصلاح کنید.',
    existing_conflict:'تداخل زمانی از قبل وجود دارد؛ ابتدا تداخل‌های فعلی را اصلاح کنید.',
    dependency_cycle:'چرخه وابستگی وجود دارد؛ برنامه‌ریزی متوقف شد.',
    earlier_than_predecessor:'این جابه‌جایی فعالیت را پیش از پایان یکی از پیش‌نیازها قرار می‌دهد.',
    date_out_of_range:'تاریخ جدید خارج از بازه معتبر تقویم است.',
    too_many:'تعداد فعالیت‌های این پروژه از حد پیش‌نمایش فراتر رفته است.',
    invalid_request:'مقدار جابه‌جایی معتبر نیست.',
    invalid_project:'پروژه کارت مشخص نیست.'
  };
  const axis=useMemo(()=>ganttAxis(anchor,scale),[anchor,scale]);
  const bars=useMemo(()=>new Map(rows.map(t=>[t.id,barPosition(t,axis)])),[rows,axis]);
  const width=axis.length*CELL_WIDTH;
  const positions=useMemo(()=>new Map(rows.map((t,i)=>[t.id,i])),[rows]);
  const arrows=[];
  rows.forEach((task,i)=>{
    const bar=bars.get(task.id);
    if(!bar)return;
    for(const depId of task.dependencies||[]){
      const priorIndex=positions.get(depId),prior=bars.get(depId);
      if(priorIndex===undefined||!prior)continue;
      const x1=prior.right*CELL_WIDTH,x2=bar.left*CELL_WIDTH;
      const y1=priorIndex*ROW_HEIGHT+ROW_HEIGHT/2,y2=i*ROW_HEIGHT+ROW_HEIGHT/2;
      arrows.push({key:depId+'>'+task.id,
        d:'M'+x1+' '+y1+' H'+(x1+10)+' V'+y2+' H'+x2});
    }
  });
  const members=[...new Set(tasks.flatMap(t=>Array.isArray(t.assignees)?t.assignees:[]))].sort();
  const priorities=[...new Set(tasks.map(t=>t.priority).filter(Boolean))].sort();
  const change=(task,field,value)=>{
    const start=field==='plannedStart'?value:(task.plannedStart||'');
    const end=field==='plannedEnd'?value:(task.plannedEnd||'');
    if(!validPlan(start,end)){setError('شروع و پایان باید تاریخ معتبر داشته باشند و پایان قبل از شروع نباشد.');return;}
    setError('');
    onUpdate(task.id,{[field]:value});
  };
  const navigate=direction=>{
    const day=dayNumber(anchor)||dayNumber(first);
    if(scale==='month'){
      const date=new Date(day*86400000);
      setAnchor(new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+direction*3,1)).toISOString().slice(0,10));
    }else setAnchor(dayString(day+direction*(scale==='week'?28:14)));
  };
  const onDragStart=(event,task)=>{
    if(!canEdit||scale!=='day'||!barPosition(task,axis))return;
    suppressBarClick.current=false;
    drag.current={cardId:task.id,x:event.clientX};
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const onDragEnd=(event,task)=>{
    const current=drag.current;drag.current=null;
    if(!current||current.cardId!==task.id)return;
    suppressBarClick.current=Math.abs(event.clientX-current.x)>5;
    const steps=Math.round((event.clientX-current.x)/CELL_WIDTH);
    if(!steps)return;
    const next=shiftPlan(task,steps);
    if(!next||!validPlan(next.plannedStart,next.plannedEnd)){setError('تاریخ جدید معتبر نیست.');return;}
    setError('');
    setPendingShift({cardId:task.id,days:steps,start:task.plannedStart,end:task.plannedEnd});
  };
  const requestPreview=(task,days=1)=>{
    if(!canEdit)return;
    setError('');
    setPendingShift({cardId:task.id,days,start:task.plannedStart,end:task.plannedEnd});
  };
  const applyPreview=()=>{
    if(!canEdit||impact?.status!=='ready'||staleImpact||impact.affectedCount!==0)return;
    onUpdate(impact.source.id,impact.source.to);
    setPendingShift(null);
  };
  return <section className="gantt-root" aria-label="گانت و برنامه زمانی پروژه">
    <div className="gantt-toolbar">
      <div className="gantt-heading"><GitBranch size={18}/><strong>گانت پروژه</strong><small>{total.toLocaleString('fa-IR')} فعالیت</small></div>
      <label>مقیاس <select aria-label="مقیاس گانت" value={scale} onChange={e=>setScale(e.target.value)}>
        <option value="day">روز</option><option value="week">هفته</option><option value="month">ماه</option>
      </select></label>
      <div className="gantt-period"><button type="button" aria-label="بازه قبلی" onClick={()=>navigate(-1)}><ChevronRight size={16}/></button>
        <button type="button" onClick={()=>setAnchor(new Date().toISOString().slice(0,10))}>امروز</button>
        <button type="button" aria-label="بازه بعدی" onClick={()=>navigate(1)}><ChevronLeft size={16}/></button></div>
      <label>مسئول <select aria-label="فیلتر مسئول گانت" value={member} onChange={e=>setMember(e.target.value)}>
        <option value="">همه</option>{members.map(x=><option key={x} value={x}>{x}</option>)}
      </select></label>
      <label>اولویت <select aria-label="فیلتر اولویت گانت" value={priority} onChange={e=>setPriority(e.target.value)}>
        <option value="">همه</option>{priorities.map(x=><option key={x} value={x}>{x}</option>)}
      </select></label>
      <input aria-label="جستجو در گانت" value={query} onChange={e=>setQuery(e.target.value)} placeholder="جستجوی فعالیت..." />
    </div>
    <p className="gantt-hint"><CalendarRange size={14}/> تاریخ شروع و پایان از موعد تحویل و نفرساعت جدا هستند.
      {canEdit?' در مقیاس روز، کشیدن نوار ابتدا پیش‌نمایش تغییرات را نشان می‌دهد.':''}</p>
    <div className="gantt-schedule-health" role="status" aria-label="کنترل ارتباط و زمان‌بندی گانت">
      <strong>{diagnostics.overlaps?`${diagnostics.conflictingCards.toLocaleString('fa-IR')} کارت دارای تداخل زمانی با پیش‌نیاز`:'برای کارت‌های نمایش‌داده‌شده تداخل زمانی شناسایی نشد'}</strong>
      <span>{diagnostics.overlaps.toLocaleString('fa-IR')} ارتباط با شروع زودهنگام</span>
      {(diagnostics.unknownDates>0||diagnostics.outsideView>0)&&<small>
        {diagnostics.unknownDates>0?`${diagnostics.unknownDates.toLocaleString('fa-IR')} ارتباط به‌دلیل تاریخ ناقص بررسی نشد. `:''}
        {diagnostics.outsideView>0?`${diagnostics.outsideView.toLocaleString('fa-IR')} پیش‌نیاز در نمای فعلی قابل بررسی نیست. `:''}
        نبود تداخل در این نما به معنی تأیید کل پروژه نیست.
      </small>}
    </div>
    <section className="gantt-critical-summary" aria-label="تحلیل مسیر بحرانی">
      <strong>مسیر بحرانی نمای فعلی (CPM)</strong>
      <small>محاسبه فقط با کارت‌های قابل مشاهده در همین نما انجام می‌شود، نه لزوماً کل پروژه؛ بر پایه مدت تقویمی و پیش‌نیازها، بدون محاسبه تعطیلات، ظرفیت منابع یا فاصله‌های عمدی برنامه.</small>
      {critical.projects.map((project,index)=><div key={project.projectId||index} className="gantt-critical-project">
        {critical.projects.length>1&&<b>پروژه {Number(index+1).toLocaleString('fa-IR')}</b>}
        {project.status==='ready'?<>
          <span>طولانی‌ترین زنجیره: <b>{project.durationDays.toLocaleString('fa-IR')} روز</b></span>
          <span>فعالیت‌های با شناوری صفر: <b>{project.criticalIds.length.toLocaleString('fa-IR')}</b></span>
          <p className="gantt-critical-chain" aria-label="یک نمونه از مسیر بحرانی">
            {project.pathIds.slice(0,8).map((id,i)=><React.Fragment key={id}>
              {i>0&&<span aria-hidden="true"> ← </span>}
              <span>{shownById.get(id)?.title||'فعالیت بدون عنوان'}</span>
            </React.Fragment>)}
            {project.pathIds.length>8&&<span> و {Number(project.pathIds.length-8).toLocaleString('fa-IR')} فعالیت دیگر</span>}
          </p>
        </>:<p role="status">
          {project.status==='cycle'
            ?'چرخه پیش‌نیازی وجود دارد؛ محاسبه مسیر بحرانی این پروژه متوقف شد.'
            :'تحلیل کامل نیست: همه فعالیت‌ها و پیش‌نیازهای قابل مشاهده باید تاریخ معتبر داشته باشند.'}
        </p>}
      </div>)}
      {!critical.projects.length&&<p>فعالیت فعالی در نمای فعلی وجود ندارد.</p>}
    </section>
    {pendingShift&&<section className="gantt-impact-preview" aria-label="پیش‌نمایش اثر جابه‌جایی">
      <div className="gantt-impact-head">
        <strong>پیش‌نمایش جابه‌جایی: {shownById.get(pendingShift.cardId)?.title||'کارت انتخاب‌شده'}</strong>
        <button type="button" onClick={()=>setPendingShift(null)} aria-label="بستن پیش‌نمایش">بستن</button>
      </div>
      <p>محاسبه فقط بر اساس کارت‌های قابل مشاهده این نما است؛ هنوز هیچ تغییری ذخیره نشده است.</p>
      <div className="gantt-impact-controls">
        <button type="button" disabled={!canEdit||pendingShift.days<=-3660}
          onClick={()=>setPendingShift(current=>({...current,days:current.days<0?current.days-1:-1}))}>یک روز زودتر</button>
        <strong aria-live="polite">{Math.abs(pendingShift.days).toLocaleString('fa-IR')} روز {pendingShift.days<0?'زودتر':'دیرتر'}</strong>
        <button type="button" disabled={!canEdit||pendingShift.days>=3660}
          onClick={()=>setPendingShift(current=>({...current,days:current.days>0?current.days+1:1}))}>یک روز دیرتر</button>
      </div>
      {impact?.status==='ready'&&!staleImpact?<>
        <p role="status">
          تغییر کارت اصلی: {impact.source.from.plannedStart} تا {impact.source.from.plannedEnd}
          {' ← '}{impact.source.to.plannedStart} تا {impact.source.to.plannedEnd}
        </p>
        <p><strong>{impact.affectedCount.toLocaleString('fa-IR')} فعالیت وابسته</strong> برای حفظ ترتیب شروع و پایان نیاز به جابه‌جایی رو به جلو دارند.</p>
        {impact.successors.length>0&&<ol className="gantt-impact-list">
          {impact.successors.slice(0,8).map(item=><li key={item.id}>
            <strong>{item.title}</strong>
            <span>{item.from.plannedStart} تا {item.from.plannedEnd} {' ← '}
              {item.to.plannedStart} تا {item.to.plannedEnd}</span>
          </li>)}
          {impact.successors.length>8&&<li>{(impact.successors.length-8).toLocaleString('fa-IR')} فعالیت دیگر در این پیش‌نمایش</li>}
        </ol>}
        {impact.affectedCount>0?<p role="status">
          اعمال گروهی فعلاً غیرفعال است؛ برای جلوگیری از تغییر ناقص، ابتدا جابه‌جایی وابسته‌ها باید با ذخیره اتمیک و بررسی مجوزها پشتیبانی شود.
        </p>:<button type="button" className="gantt-impact-confirm" disabled={!canEdit}
          onClick={applyPreview}>تأیید جابه‌جایی فقط همین کارت</button>}
      </>:<p role="alert">{staleImpact?'برنامه کارت بعد از باز شدن پیش‌نمایش تغییر کرده است. پیش‌نمایش را دوباره باز کنید.':
        impactReason[impact?.reason]||'برای این تغییر، پیش‌نمایش قابل‌اعتماد در دسترس نیست.'}</p>}
    </section>}
    {error&&<p role="alert" className="gantt-error">{error}</p>}
    {truncated&&<p role="status" className="gantt-error">برای حفظ عملکرد، {rows.length.toLocaleString('fa-IR')} فعالیت نخست نشان داده می‌شود. از فیلتر استفاده کنید.</p>}
    <div className="gantt-scroll" tabIndex={0} aria-label="جدول زمانی قابل پیمایش">
      <div className="gantt-board" style={{width:LABEL_WIDTH+width}}>
        <div className="gantt-axis">
          <div className="gantt-axis-title" style={{width:LABEL_WIDTH}}>فعالیت و تاریخ برنامه</div>
          <div className="gantt-axis-cells" style={{width}}>
            {axis.map(cell=><div key={cell.key} className="gantt-axis-cell" style={{width:CELL_WIDTH}}>{axisLabel(cell,scale,calendar)}</div>)}
          </div>
        </div>
        <div className="gantt-content">
          {rows.map(task=>{
            const bar=bars.get(task.id),missing=dayNumber(task.plannedStart)===null||dayNumber(task.plannedEnd)===null;
            const schedule=diagnostics.byTask.get(task.id);
            const hasConflict=Boolean(schedule?.conflicts.length);
            const criticalInfo=criticalById.get(task.id);
            return <div key={task.id} className="gantt-row" style={{height:ROW_HEIGHT}}>
              <div className="gantt-task" style={{width:LABEL_WIDTH}}>
                <button className="gantt-task-title" type="button" title={task.title} onClick={()=>onOpen(task.id)}>{task.title||'بدون عنوان'}</button>
                <div className="gantt-dates">
                  <input type="date" aria-label={'شروع '+task.title} title="شروع برنامه" value={task.plannedStart||''}
                    disabled={!canEdit} onChange={e=>change(task,'plannedStart',e.target.value)}/>
                  <span>تا</span>
                  <input type="date" aria-label={'پایان '+task.title} title="پایان برنامه" value={task.plannedEnd||''}
                    disabled={!canEdit} min={task.plannedStart||undefined} onChange={e=>change(task,'plannedEnd',e.target.value)}/>
                </div>
                {hasConflict&&<div className="gantt-schedule-warning">
                  <span title={schedule.conflicts.map(c=>c.title+' · '+c.predecessorEnd).join('؛ ')}>
                    تداخل با {schedule.conflicts.length.toLocaleString('fa-IR')} پیش‌نیاز
                  </span>
                  {canEdit&&schedule.suggestion&&<button type="button" title="فقط تاریخ همین کارت تغییر می‌کند؛ کارت‌های وابسته خودکار جابه‌جا نمی‌شوند"
                    aria-label={'اصلاح تاریخ کارت '+task.title+' بر اساس پیش‌نیازها'}
                    onClick={()=>onUpdate(task.id,schedule.suggestion)}>اصلاح تاریخ</button>}
                </div>}
                {criticalInfo&&<span className="gantt-critical-chip">
                  {criticalInfo.critical?'بحرانی، شناوری صفر':`شناوری ${criticalInfo.slackDays.toLocaleString('fa-IR')} روز`}
                </span>}
                {canEdit&&!missing&&<button type="button" className="gantt-impact-trigger"
                  aria-label={'پیش‌نمایش جابه‌جایی کارت '+task.title}
                  onClick={()=>requestPreview(task)}>بررسی جابه‌جایی</button>}
              </div>
              <div className="gantt-track" style={{width,backgroundSize:CELL_WIDTH+'px 100%'}}>
                {bar&&<button type="button" className={'gantt-bar'+(task.completed||task.status==='done'?' is-done':'')+(hasConflict?' has-conflict':'')+(criticalInfo?.critical?' is-critical':'')}
                  style={{left:(bar.left*CELL_WIDTH)+'px',width:Math.max(5,bar.width*CELL_WIDTH)+'px'}}
                  title={task.title+' | '+task.plannedStart+' تا '+task.plannedEnd+(hasConflict?' | تداخل با پیش‌نیاز':'')+(criticalInfo?.critical?' | مسیر بحرانی':'')}
                  onPointerDown={e=>onDragStart(e,task)} onPointerUp={e=>onDragEnd(e,task)}
                  onPointerCancel={()=>{drag.current=null;}}
                  onKeyDown={()=>{suppressBarClick.current=false;}}
                  onClick={()=>{if(suppressBarClick.current){suppressBarClick.current=false;return;}onOpen(task.id);}} aria-label={'نوار '+task.title+(hasConflict?'، دارای تداخل با پیش‌نیاز':'')+(criticalInfo?.critical?'، در مسیر بحرانی':'')} />}
                {missing&&<span className="gantt-empty">تاریخ شروع/پایان تعیین نشده</span>}
                {!missing&&!bar&&<span className="gantt-empty">خارج از بازهٔ نمایش</span>}
              </div>
            </div>;
          })}
          {arrows.length>0&&<svg className="gantt-arrows" viewBox={'0 0 '+width+' '+(rows.length*ROW_HEIGHT)}
            width={width} height={rows.length*ROW_HEIGHT} aria-hidden="true">
            <defs><marker id="madar-gantt-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6" fill="none" stroke="currentColor"/></marker></defs>
            {arrows.map(a=><path key={a.key} d={a.d} fill="none" stroke="currentColor" strokeWidth="1.25" opacity="0.7" markerEnd="url(#madar-gantt-arrow)"/>)}
          </svg>}
        </div>
      </div>
    </div>
    {!rows.length&&<p className="gantt-empty-panel">فعالیتی با این فیلتر پیدا نشد.</p>}
  </section>;
}
