import React,{useMemo,useRef,useState} from 'react';
import {CalendarRange,ChevronLeft,ChevronRight,GitBranch} from 'lucide-react';
import {barPosition,buildGanttRows,dayNumber,dayString,ganttAxis,shiftPlan,validPlan} from './gantt_model.js';
import './gantt_view.css';

const CELL_WIDTH=44;
const ROW_HEIGHT=72;
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
  const first=tasks.find(t=>dayNumber(t.plannedStart)!==null)?.plannedStart||
    new Date().toISOString().slice(0,10);
  const [anchor,setAnchor]=useState(first);
  const drag=useRef(null);
  const suppressBarClick=useRef(false);
  const shown=useMemo(()=>tasks.filter(t=>(!member||(t.assignees||[]).includes(member))&&
    (!priority||t.priority===priority)&&(!query||String(t.title||'').toLowerCase().includes(query.trim().toLowerCase()))),
    [tasks,member,priority,query]);
  const {rows,total,truncated}=useMemo(()=>buildGanttRows(shown),[shown]);
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
    setError('');onUpdate(task.id,next);
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
      {canEdit?' در مقیاس روز می‌توان نوار فعالیت را جابه‌جا کرد.':''}</p>
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
              </div>
              <div className="gantt-track" style={{width,backgroundSize:CELL_WIDTH+'px 100%'}}>
                {bar&&<button type="button" className={'gantt-bar'+(task.completed||task.status==='done'?' is-done':'')}
                  style={{left:(bar.left*CELL_WIDTH)+'px',width:Math.max(5,bar.width*CELL_WIDTH)+'px'}}
                  title={task.title+' | '+task.plannedStart+' تا '+task.plannedEnd}
                  onPointerDown={e=>onDragStart(e,task)} onPointerUp={e=>onDragEnd(e,task)}
                  onPointerCancel={()=>{drag.current=null;}}
                  onKeyDown={()=>{suppressBarClick.current=false;}}
                  onClick={()=>{if(suppressBarClick.current){suppressBarClick.current=false;return;}onOpen(task.id);}} aria-label={'نوار '+task.title} />}
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
