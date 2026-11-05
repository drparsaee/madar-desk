import React,{useEffect,useId,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {CalendarDays, Clock3, Copy, ExternalLink, FileText, FolderOpen, Link2, Plus, Search, Trash2, X, BarChart3,HelpCircle,Download} from 'lucide-react';
import {MiniCalendar} from './mini_calendar.jsx';

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
export function CalendarField({value,onChange,calendar='jalali',disabled=false,label='تاریخ',popupOnClick=false}){
 const [text,setText]=useState('');
 const [error,setError]=useState(false);
 const [pickerOpen,setPickerOpen]=useState(false);
 const [popupStyle,setPopupStyle]=useState({top:0,left:0,visibility:'hidden'});
 const popupId=useId();
 const container=useRef(null);
 const popup=useRef(null);
 const trigger=useRef(null);
 const focusPicker=useRef(false);
 useEffect(()=>{setText(value?calendar==='jalali'?jalaliDigits(new Date(value+'T12:00:00Z')):value.replace(/-/g,'/'):'');setError(false);},[value,calendar]);
 useEffect(()=>{
   if(!pickerOpen)return;
   const outside=event=>{
     if(!container.current?.contains(event.target)&&!popup.current?.contains(event.target))setPickerOpen(false);
   };
   const escape=event=>{
     if(event.key==='Escape'){
       event.preventDefault();event.stopPropagation();setPickerOpen(false);trigger.current?.focus();
     }
   };
   document.addEventListener('pointerdown',outside,true);
   document.addEventListener('keydown',escape,true);
   return()=>{document.removeEventListener('pointerdown',outside,true);document.removeEventListener('keydown',escape,true);};
 },[pickerOpen]);
 useLayoutEffect(()=>{
   if(!pickerOpen||disabled||!container.current||!popup.current)return;
   const anchor=container.current;
   const menu=popup.current;
   const place=()=>{
     const viewport=window.visualViewport;
     const leftEdge=(viewport?.offsetLeft||0)+8;
     const topEdge=(viewport?.offsetTop||0)+8;
     // visualViewport measurements can briefly lag window.innerHeight during
     // Playwright/OS window resizing. Never position beyond the *smaller*
     // viewport or the portaled calendar can become unreachable on mobile.
     const rightEdge=Math.min(window.innerWidth-8,
       leftEdge+Math.min(viewport?.width||window.innerWidth,window.innerWidth)-16);
     const bottomEdge=Math.min(window.innerHeight-8,
       topEdge+Math.min(viewport?.height||window.innerHeight,window.innerHeight)-16);
     const width=Math.max(0,Math.min(280,rightEdge-leftEdge));
     const height=Math.max(0,bottomEdge-topEdge);
     menu.style.width=width+'px';
     menu.style.maxHeight=height+'px';
     const rect=anchor.getBoundingClientRect();
     const menuHeight=menu.getBoundingClientRect().height;
     const below=bottomEdge-rect.bottom-5;
     const above=rect.top-topEdge-5;
     const openAbove=below<menuHeight&&above>below;
     const desiredTop=openAbove?rect.top-menuHeight-5:rect.bottom+5;
     const top=Math.max(topEdge,Math.min(desiredTop,bottomEdge-menuHeight));
     const left=Math.max(leftEdge,Math.min(rect.right-width,rightEdge-width));
     setPopupStyle(previous=>previous.top===top&&previous.left===left&&
       previous.width===width&&previous.maxHeight===height&&previous.visibility==='visible'?previous:
       {top,left,width,maxHeight:height,visibility:'visible'});
   };
   place();
   if(focusPicker.current){
     menu.querySelector('.madar-mini-calendar__selected, .madar-mini-calendar__today, .madar-mini-calendar__days button')?.focus();
     focusPicker.current=false;
   }
   // Capture scrolling on nested drawers and panels, not just the page.
   window.addEventListener('scroll',place,true);
   let resizeFrame=0;
   const resize=()=>{place();cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(place);};
   window.addEventListener('resize',resize);
   window.visualViewport?.addEventListener('resize',resize);
   window.visualViewport?.addEventListener('scroll',place);
   const resizeObserver=typeof ResizeObserver==='function'?new ResizeObserver(place):null;
   resizeObserver?.observe(anchor);
   resizeObserver?.observe(menu);
   return()=>{
     window.removeEventListener('scroll',place,true);
     cancelAnimationFrame(resizeFrame);
     window.removeEventListener('resize',resize);
     window.visualViewport?.removeEventListener('resize',resize);
     window.visualViewport?.removeEventListener('scroll',place);
     resizeObserver?.disconnect();
   };
 },[pickerOpen,disabled,calendar]);
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
 return <div ref={container} className="calendar-field" onKeyDown={event=>{
   if(event.key==='Escape'&&pickerOpen){event.preventDefault();event.stopPropagation();setPickerOpen(false);}
 }}><label>{label} <small>{calendar==='jalali'?'شمسی':'میلادی'}</small></label>
 <div className="calendar-field__input-wrap">
 <input dir="ltr" disabled={disabled} aria-label={label} placeholder={calendar==='jalali'?'1405/07/28':'2026/10/20'}
 value={text} onClick={()=>{if(!disabled&&popupOnClick){focusPicker.current=false;setPickerOpen(true);}}}
 onChange={e=>{setText(e.target.value);setError(false);}} onKeyDown={e=>e.key==='Enter'&&save()} onBlur={save}/>
 <button ref={trigger} type="button" className="calendar-field__open" disabled={disabled}
   title={'بازکردن تقویم '+label} aria-label={'انتخاب تاریخ '+label} aria-expanded={pickerOpen} aria-controls={popupId}
   onClick={()=>{focusPicker.current=true;setPickerOpen(open=>!open);}}><CalendarDays size={16}/></button>
 </div>
 {pickerOpen&&!disabled&&createPortal(<MiniCalendar id={popupId} popupRef={popup} popupStyle={popupStyle}
   value={value} calendar={calendar} onSelect={date=>{onChange(date);setError(false);}}
   onClose={()=>{setPickerOpen(false);trigger.current?.focus();}}/>,document.body)}
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
 const [showEditor,setShowEditor]=useState(false);
 const open=async p=>{setMessage('');try{await api.openSharedFile(p);}catch(e){setMessage('بازکردن فایل ممکن نشد: '+e.message);}};
 const download=async p=>{setMessage('');try{const result=await api.downloadSharedFile(p);setMessage('فایل در پوشه دانلودهای این سیستم ذخیره شد: '+result.name);}catch(e){setMessage('دانلود فایل ممکن نشد: '+e.message);}};
 const choose=async()=>{setMessage('');try{const file=await api.chooseSharedFile();if(!file.canceled){setPath(file.path);setName(file.name);}}catch(e){setMessage('انتخاب فایل ممکن نشد: '+e.message);}};
 const add=()=>{if(!pathValid(path)){setMessage('مسیر معتبر نمونه: \\\\OFFICE-PC\\Projects\\file.pdf');return;}
   if(!name.trim()){setMessage('عنوان فایل را وارد کنید.');return;}
   onChange([...links,{id:id(),name:name.trim().slice(0,180),path:path.replace(/\//g,'\\')}]);setName('');setPath('');setMessage('');setShowEditor(false);
 };
 if(compact)return <div className="shared-links shared-links--compact">
   <div className="shared-links__heading"><strong><Link2 size={15}/> لینک‌های فایل اشتراکی ({links.length})</strong>
     {canEdit&&<button type="button" onClick={()=>setShowEditor(v=>!v)} aria-expanded={showEditor}><Plus size={14}/> لینک اشتراکی</button>}
     <details className="shared-links__help"><summary title="راهنمای فایل شبکه" aria-label="راهنمای لینک اشتراکی"><HelpCircle size={15}/></summary><p>مسیر شبکه باید با Windows File Sharing در دسترس باشد. فایل روی میزبان شبکه می‌ماند؛ برای دریافت روی نام فایل بزنید. مدار نسخهٔ دیگری از فایل شبکه آپلود نمی‌کند.</p></details>
   </div>
   {links.map(item=><div className="shared-item" key={item.id}>
     <FileText size={15}/><button type="button" className="shared-open" onClick={()=>download(item.path)} title={item.path} aria-label={'دانلود '+item.name}><strong dir="auto">{item.name}</strong></button>
     <button type="button" onClick={()=>download(item.path)} title="دانلود از شبکه" aria-label={'دانلود فایل '+item.name}><Download size={15}/></button>
     <button type="button" onClick={()=>open(item.path)} title="نمایش در File Explorer" aria-label={'بازکردن '+item.name}><FolderOpen size={15}/></button>
     {canEdit&&<button type="button" title="حذف لینک" aria-label={'حذف لینک '+item.name} onClick={()=>onChange(links.filter(x=>x.id!==item.id))}><X size={15}/></button>}
   </div>)}
   {canEdit&&showEditor&&<div className="shared-links__editor">
     <button type="button" onClick={choose}><FolderOpen size={14}/> انتخاب فایل از شبکه</button>
     <input aria-label="عنوان فایل" maxLength={180} placeholder="نام فایل" value={name} onChange={e=>setName(e.target.value)}/>
     <input dir="ltr" aria-label="مسیر اشتراک ویندوز" placeholder="\\\\SERVER\\Share\\file.pdf" value={path} onChange={e=>setPath(e.target.value)}/>
     <button type="button" disabled={!name.trim()||!path.trim()} onClick={add}>ثبت لینک</button>
   </div>}
   {!!message&&<p className="field-error" role="alert">{message}</p>}
 </div>;
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
 <small className="shared-note">برای استفاده روی سیستم‌های دیگر، پوشه باید با Windows File Sharing به اشتراک گذاشته شده باشد و حساب ویندوز آن سیستم مجوز دسترسی داشته باشد. دانلود روی همان کامپیوتر در پوشه Downloads ذخیره می‌شود؛ فایل‌ها در مدار آپلود نمی‌شوند.</small>
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
