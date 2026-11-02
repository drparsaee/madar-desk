import React,{useEffect,useMemo,useState} from 'react';
import {CalendarDays, Clock3, Copy, ExternalLink, FileText, FolderOpen, Link2, Plus, Search, Trash2, X, BarChart3} from 'lucide-react';

export const durationText=v=>{
 const minutes=Number(v)||0;
 if(!minutes)return 'ثبت نشده';
 const hours=Math.floor(minutes/60),remainder=minutes%60;
 return hours?hours.toLocaleString('fa-IR')+' ساعت'+(remainder?' و '+remainder.toLocaleString('fa-IR')+' دقیقه':''):minutes.toLocaleString('fa-IR')+' دقیقه';
};
export const toLatin=v=>String(v??'').replace(/[۰-۹]/g,x=>String(x.charCodeAt(0)-1776)).replace(/[٠-٩]/g,x=>String(x.charCodeAt(0)-1632));
const jalaliParts=new Intl.DateTimeFormat('en-US-u-ca-persian',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'UTC'});
export const jalaliDigits=date=>{
 const found=jalaliParts.formatToParts(date).reduce((o,p)=>({...o,[p.type]:p.value}),{});
 return [found.year,found.month,found.day].join('/');
};
const ISO=/^\d{4}-\d{2}-\d{2}$/;
export function displayDate(value,calendar='jalali',full=false){
 if(!value)return '';
 const d=new Date(ISO.test(value)?value+'T12:00:00':value);
 if(Number.isNaN(d.getTime()))return value;
 return new Intl.DateTimeFormat(calendar==='jalali'?'fa-IR-u-ca-persian':'fa-IR-u-ca-gregory',{
   year:full?'numeric':undefined,month:full?'2-digit':'short',day:'numeric'
 }).format(d);
}
export function fromJalali(input){
 const m=/^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$/.exec(toLatin(input).trim());
 if(!m)return null;
 const [year,month,day]=m.slice(1).map(Number);
 if(year<1250||year>1600||month<1||month>12||day<1||day>31)return null;
 const start=Date.UTC(year+621,2,18);
 for(let i=0;i<375;i++){
   const candidate=new Date(start+i*86400000);
   const candidateParts=jalaliDigits(candidate).split('/').map(Number);
   if(candidateParts[0]===year&&candidateParts[1]===month&&candidateParts[2]===day)return candidate.toISOString().slice(0,10);
 }
 return null;
}
export function CalendarField({value,onChange,calendar='jalali',disabled=false,label='تاریخ'}){
 const [text,setText]=useState('');
 const [error,setError]=useState(false);
 useEffect(()=>{setText(value?calendar==='jalali'?jalaliDigits(new Date(value+'T12:00:00Z')):value.replace(/-/g,'/'):'');setError(false);},[value,calendar]);
 const save=()=>{
   if(!text.trim()){onChange('');setError(false);return;}
   const iso=calendar==='jalali'?fromJalali(text):(/^(\d{4})[/-](\d\d?)[/-](\d\d?)$/.test(toLatin(text))?(()=>{
     const parts=toLatin(text).split(/[/-]/).map(Number);
     const y=parts[0],m=parts[1],d=parts[2];
     const check=new Date(Date.UTC(y,m-1,d));
     return check.getUTCFullYear()===y&&check.getUTCMonth()===m-1&&check.getUTCDate()===d?[
       y,String(m).padStart(2,'0'),String(d).padStart(2,'0')].join('-'):null;
   })():null);
   if(iso){onChange(iso);setError(false);}else setError(true);
 };
 return <div className="calendar-field"><label>{label} <small>{calendar==='jalali'?'شمسی':'میلادی'}</small></label>
 <input dir="ltr" disabled={disabled} aria-label={label} placeholder={calendar==='jalali'?'1405/07/28':'2026/10/20'}
 value={text} onChange={e=>{setText(e.target.value);setError(false);}} onKeyDown={e=>e.key==='Enter'&&save()} onBlur={save}/>
 {error&&<small className="field-error">تاریخ معتبر نیست؛ مانند {calendar==='jalali'?'1405/07/28':'2026/10/20'} وارد کنید.</small>}
 </div>;
}
export function searchText(task,project){
 return [task.title,task.description,task.status,task.dueDate,project?.name,
   ...(task.labels||[]),...(task.checklist||[]).map(s=>s.text),
   ...(task.reports||[]).map(s=>s.summary+' '+s.agent),
   ...(task.fileLinks||[]).map(s=>s.name+' '+s.path)].join(' ').toLocaleLowerCase('fa').replace(/[يى]/g,'ی').replace(/ك/g,'ک');
}
const stopWords=new Set('در و به با را از برای که یک این آن روی کار پروژه تکمیل نسخه انجام کردن جدید طرح طراحی مرحله های است'.split(' '));
const words=input=>new Set(String(input||'').toLocaleLowerCase('fa').replace(/[يى]/g,'ی').replace(/ك/g,'ک')
 .replace(/[^\p{L}\p{N}]+/gu,' ').split(/\s+/).filter(w=>w.length>1&&!stopWords.has(w)));
export function similarTasks(title,tasks,exclude=''){
 const tokens=words(title);
 if(tokens.size<1)return [];
 return tasks.filter(t=>t.id!==exclude).map(t=>{
   const compare=words(t.title);
   const overlap=[...tokens].filter(w=>compare.has(w)).length;
   const union=new Set([...tokens,...compare]).size;
   const score=union?overlap/union:0;
   return {task:t,score};
 }).filter(x=>x.score>=0.25).sort((a,b)=>b.score-a.score).slice(0,4);
}
const id=()=>Date.now().toString(36)+Math.random().toString(36).slice(2);
export const pathValid=path=>{
 if(typeof path!=='string'||path.length>2048)return false;
 const normalized=path.replace(/\//g,'\\');
 if(!normalized.startsWith('\\\\')||normalized.startsWith('\\\\?\\')||normalized.startsWith('\\\\.\\'))return false;
 const parts=normalized.slice(2).split('\\');
 return parts.length>=3&&parts.slice(0,3).every(Boolean)&&
   !parts.some(part=>part==='.'||part==='..')&&
   !/[<>:"|?*\x00-\x1f]/.test(normalized.slice(2))&&!normalized.endsWith('\\');
};

export function SharedLinks({links=[],onChange,api,canEdit=true,compact=false}){
 const [name,setName]=useState(''),[path,setPath]=useState(''),[message,setMessage]=useState('');
 const open=async p=>{setMessage('');try{await api.openSharedFile(p);}catch(e){setMessage('بازکردن فایل ممکن نشد: '+e.message);}};
 const download=async p=>{setMessage('');try{const result=await api.downloadSharedFile(p);setMessage('فایل در پوشه دانلودهای این سیستم ذخیره شد: '+result.name);}catch(e){setMessage('دانلود فایل ممکن نشد: '+e.message);}};
 const choose=async()=>{setMessage('');try{const file=await api.chooseSharedFile();if(!file.canceled){setPath(file.path);setName(file.name);}}catch(e){setMessage('انتخاب فایل ممکن نشد: '+e.message);}};
 const add=()=>{if(!pathValid(path)){setMessage('مسیر معتبر نمونه: \\\\OFFICE-PC\\Projects\\file.pdf');return;}
   if(!name.trim()){setMessage('عنوان فایل را وارد کنید.');return;}
   onChange([...links,{id:id(),name:name.trim().slice(0,180),path:path.replace(/\//g,'\\')}]);setName('');setPath('');setMessage('');
 };
 return <div className="shared-links">
 {links.map(item=><div className="shared-item" key={item.id}><FileText size={16}/>
   <button className="shared-open" onClick={()=>download(item.path)} title={'دانلود فایل: '+item.path}><strong>{item.name}</strong><small dir="ltr">{item.path}</small></button>
   <button title="دانلود روی این سیستم" onClick={()=>download(item.path)}>دانلود</button>
   <button title="نمایش در File Explorer" onClick={()=>open(item.path)}><FolderOpen size={16}/></button>
   {canEdit&&<button title="حذف لینک" onClick={()=>onChange(links.filter(x=>x.id!==item.id))}><X size={15}/></button>}
 </div>)}
 {!links.length&&<p className="shared-empty">هنوز لینک فایل اشتراکی ثبت نشده است.</p>}
 {canEdit&&<button type="button" className="btn secondary" onClick={choose}><FolderOpen size={15}/> انتخاب فایل از شبکه</button>}
 {canEdit&&<div className="shared-create"><input aria-label="عنوان فایل" placeholder="نام فایل یا پوشه" value={name} onChange={e=>setName(e.target.value)}/><input dir="ltr" aria-label="مسیر اشتراک ویندوز" placeholder="\\Server\Share\Folder\File.pdf" value={path} onChange={e=>setPath(e.target.value)}/><button className="btn secondary" onClick={add}><Plus size={15}/> ثبت لینک</button></div>}
 {!!message&&<div className="field-error">{message}</div>}
 <small className="shared-note">برای استفاده روی سیستم‌های دیگر، پوشه باید با Windows File Sharing به اشتراک گذاشته شده باشد و حساب ویندوز آن سیستم مجوز دسترسی داشته باشد. فایل‌ها در مدار آپلود نمی‌شوند.</small>
 </div>;
}
export function TimeDashboard({tasks,projects,onOpen,calendar='jalali'}){
 const total=tasks.reduce((s,t)=>s+(t.estimatedMinutes||0),0);
 const actual=tasks.reduce((s,t)=>s+(t.actualMinutes||0),0);
 const missing=tasks.filter(t=>!t.estimatedMinutes).length;
 const byProject=projects.map(p=>({project:p,...(()=>{const selected=tasks.filter(t=>t.projectId===p.id);return {estimated:selected.reduce((s,t)=>s+(t.estimatedMinutes||0),0),actual:selected.reduce((s,t)=>s+(t.actualMinutes||0),0),count:selected.length};})()})).filter(x=>x.count);
 const maximum=Math.max(1,...byProject.map(x=>Math.max(x.estimated,x.actual)));
 return <section className="time-dashboard">
 <div className="time-heading"><div><h2><BarChart3 size={20}/> داشبورد برآورد زمان</h2><p>مجموع زمان‌های ثبت‌شده؛ زمان‌های خالی در جمع صفر لحاظ می‌شوند، نه یک تخمین ساختگی.</p></div></div>
 <div className="time-stat-grid"><div><small>زمان برآوردی</small><strong>{durationText(total)}</strong></div><div><small>زمان واقعی ثبت‌شده</small><strong>{durationText(actual)}</strong></div><div><small>بدون برآورد</small><strong>{missing.toLocaleString('fa-IR')} کار</strong></div></div>
 <h3>برآورد زمان به تفکیک پروژه</h3>
 <div className="time-chart">{byProject.map(p=><div className="time-chart-row" key={p.project.id}><div className="time-chart-title"><span>{p.project.name}</span><b>{durationText(p.estimated)}</b></div><div className="time-chart-tracks"><div className="time-chart-estimate" style={{width:(p.estimated/maximum*100)+'%'}}/><div className="time-chart-actual" style={{width:(p.actual/maximum*100)+'%'}}/></div></div>)}{!byProject.length&&<p>هنوز پروژه‌ای با کار ثبت نشده است.</p>}</div>
 <div className="chart-legend"><span><i className="legend-estimate"/>برآورد</span><span><i className="legend-actual"/>واقعی ثبت‌شده</span></div>
 <h3>کارها و تخمین انجام</h3>
 <div className="time-list">{[...tasks].sort((a,b)=>(b.estimatedMinutes||0)-(a.estimatedMinutes||0)).map(t=><button key={t.id} onClick={()=>onOpen(t.id)}><span>{t.title}<small>{displayDate(t.dueDate||t.createdAt,calendar,true)}</small></span><strong>{durationText(t.estimatedMinutes)}</strong><small>واقعی: {durationText(t.actualMinutes)}</small></button>)}</div>
 </section>;
}
