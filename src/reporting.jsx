import React,{useMemo,useState} from 'react';
import {ArrowDownToLine,BarChart3,CalendarDays,FileSpreadsheet,LayoutList,X} from 'lucide-react';
import {displayDate} from './productivity.jsx';
import {dateKey,reportRows,summarizeRows,taskReportCsv,timelineBuckets} from './reporting.js';
import './reporting.css';

const duration=minutes=>{const value=Math.max(0,Math.round(minutes));return value>=60?`${Math.floor(value/60)} ساعت و ${value%60} دقیقه`:`${value} دقیقه`;};
const download=(text,name)=>{
  const blob=new Blob([text],{type:'text/csv;charset=utf-8'});
  const address=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=address;a.download=name;a.click();
  setTimeout(()=>URL.revokeObjectURL(address),1000);
};
export function ReportingPanel({tasks=[],projects=[],boards=[],stages=[],calendar='jalali',onOpenTask,onClose}){
  const [projectId,setProjectId]=useState(''),[boardId,setBoardId]=useState(''),[member,setMember]=useState('');
  const [start,setStart]=useState(''),[end,setEnd]=useState('');
  const [mode,setMode]=useState('table'),[priority,setPriority]=useState('all');
  const rows=useMemo(()=>reportRows(tasks,projects,stages,{boards,projectId,boardId,member,start,end,priority}),
    [tasks,projects,boards,stages,projectId,boardId,member,start,end,priority]);
  const stats=useMemo(()=>summarizeRows(rows),[rows]);
  const timeline=useMemo(()=>timelineBuckets(rows),[rows]);
  const badRange=!!(dateKey(start)&&dateKey(end)&&start>end);
  return <div className="reporting-backdrop" onMouseDown={onClose}>
    <section role="dialog" aria-modal="true" aria-label="داشبورد و گزارش عملکرد" className="reporting-panel" onMouseDown={e=>e.stopPropagation()}>
      <header><div><small>گزارش غیرمالی وظایف</small><h2><BarChart3 size={21}/> داشبورد و گزارش عملکرد</h2></div><button type="button" onClick={onClose} aria-label="بستن"><X size={19}/></button></header>
      <div className="reporting-content">
        <div className="reporting-filter">
          <label>پروژه<select value={projectId} onChange={e=>setProjectId(e.target.value)}><option value="">تمام پروژه‌های قابل‌مشاهده</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <label>برد<select aria-label="فیلتر برد گزارش" value={boardId} onChange={e=>setBoardId(e.target.value)}><option value="">همهٔ بردها</option>{boards.filter(b=>!b.archived&&(!projectId||b.projectId===projectId)).map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          <label>مسئول<select aria-label="فیلتر مسئول گزارش" value={member} onChange={e=>setMember(e.target.value)}><option value="">همهٔ مسئولان</option>{[...new Set(tasks.flatMap(t=>t.assignees||[]))].sort().map(name=><option value={name} key={name}>{name}</option>)}</select></label>
          <label>شروع تاریخ میلادی<input aria-label="شروع بازه گزارش" type="date" value={start} max={end||undefined} onChange={e=>setStart(e.target.value)}/></label>
          <label>پایان تاریخ میلادی<input aria-label="پایان بازه گزارش" type="date" value={end} min={start||undefined} onChange={e=>setEnd(e.target.value)}/></label>
          <label>اولویت<select value={priority} onChange={e=>setPriority(e.target.value)}><option value="all">همه</option>{[...new Set(tasks.map(t=>t.priority))].filter(Boolean).map(p=><option key={p} value={p}>{p}</option>)}</select></label>
        </div>
        {badRange&&<p role="alert">شروع بازه نباید بعد از پایان آن باشد.</p>}
        <div className="reporting-stats">
          <article><small>کل کارها</small><strong>{stats.tasks.toLocaleString('fa-IR')}</strong></article>
          <article><small>کارهای عقب‌افتاده</small><strong>{stats.overdue.toLocaleString('fa-IR')}</strong></article>
          <article><small>زمان برآوردی</small><strong>{duration(stats.estimatedMinutes)}</strong></article>
          <article><small>زمان واقعی</small><strong>{duration(stats.actualMinutes)}</strong></article>
        </div>
        <div className="reporting-tools"><div>
          <button className={mode==='table'?'selected':''} onClick={()=>setMode('table')}><LayoutList size={15}/> جدول</button>
          <button className={mode==='timeline'?'selected':''} onClick={()=>setMode('timeline')}><CalendarDays size={15}/> خط زمانی موعدها</button>
        </div><button disabled={badRange||!rows.length} onClick={()=>download(taskReportCsv(rows),'madar-task-report-'+new Date().toISOString().slice(0,10)+'.csv')}><FileSpreadsheet size={16}/> دریافت CSV <ArrowDownToLine size={14}/></button></div>
        {mode==='table'?<div className="reporting-table"><table><thead><tr><th>کار</th><th>پروژه</th><th>برد</th><th>مرحله</th><th>اولویت</th><th>سررسید</th><th>پیشرفت</th><th>زمان واقعی</th></tr></thead><tbody>{rows.map(t=><tr key={t.id}><td><button onClick={()=>{onOpenTask?.(t.id);onClose();}}>{t.title}</button></td><td>{t.project}</td><td>{t.board}</td><td>{t.status}</td><td>{t.priority}</td><td>{displayDate(t.dueDate,calendar,true)||'بدون موعد'}</td><td>{t.progress.toLocaleString('fa-IR')}٪</td><td>{duration(t.actualMinutes)}</td></tr>)}</tbody></table>{!rows.length&&<p>کاری در این بازه پیدا نشد.</p>}</div>:
        <div className="reporting-timeline">{timeline.map(({day,items})=><div key={day}><strong>{displayDate(day,calendar,true)}</strong>{items.map(item=><button key={item.id} onClick={()=>{onOpenTask?.(item.id);onClose();}}>{item.title} · {item.project}</button>)}</div>)}{!timeline.length&&<p>کار دارای موعدی در این بازه وجود ندارد.</p>}</div>}
        <div className="reporting-projects"><h3>حجم کار به تفکیک پروژه</h3>{stats.byProject.map(project=><div key={project.id}><span>{project.name} ({project.count.toLocaleString('fa-IR')})</span><strong>{duration(project.actual)} واقعی / {duration(project.estimate)} برآورد</strong></div>)}</div>
        <p className="reporting-footnote">گزارش فقط کارت‌های قابل‌مشاهده کاربر را شامل می‌شود. مقادیر مالی، قرارداد، دریافتی و سود در CSV درج نمی‌شوند. تحلیل بر مبنای داده‌های ثبت‌شده است.</p>
      </div>
    </section>
  </div>;
}
