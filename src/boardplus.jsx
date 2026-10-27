import React,{useEffect,useMemo,useRef,useState} from 'react';
import {AlignLeft,AlignRight,Bold,Check,ChevronDown,ChevronUp,Filter,Italic,Link2,
 List,Save,Search,TextCursorInput,Trash2,Undo2,X} from 'lucide-react';
import {MarkdownPreview} from './markdown.jsx';

const colors=['#9a6714','#24845d','#7953b0','#b14f72','#3378ad','#aa5439','#676cbe','#54836a'];
export function labelColor(label){
 if(typeof label==='object')return label?.color||colors[0];
 const name=String(label||'');
 let hash=2166136261;
 for(const char of name){hash=Math.imul(hash^char.charCodeAt(0),16777619);}
 return colors[(hash>>>0)%colors.length];
}
export function labelText(label){return typeof label==='string'?label:String(label?.name||'');}
export function LabelChip({label,onClick}){
 const title=labelText(label),color=labelColor(label);
 return <span title={'برچسب: '+title} className={'colored-label '+(onClick?'editable-label':'')}
 style={{'--label-color':color}} onClick={onClick}>{title}</span>;
}

export function InlineChecklist({items=[],onToggle,canEdit=true,taskId,collapsed=false,onCollapse}){
 const done=items.filter(x=>x.done).length;
 if(!items.length)return null;
 return <div className="inline-checklist" onClick={e=>e.stopPropagation()}>
   <button className="checklist-toggle" onClick={onCollapse} type="button" aria-expanded={!collapsed} title={collapsed?'نمایش مراحل':'جمع‌کردن مراحل'}>
     <span><Check size={13}/> {done.toLocaleString('fa-IR')} / {items.length.toLocaleString('fa-IR')} مرحله</span>
     {collapsed?<ChevronDown size={16}/>:<ChevronUp size={16}/>}
   </button>
   {!collapsed&&<div className="inline-check-items">
     {items.slice(0,8).map(item=><label key={item.id} className={item.done?'completed':''} onClick={e=>e.stopPropagation()}>
       <input aria-label={'مرحله '+item.text} type="checkbox" checked={item.done} disabled={!canEdit} onChange={()=>onToggle?.(taskId,item.id)}/>
       <span>{item.text}</span>
     </label>)}
     {items.length>8&&<small title="جزئیات کارت برای بقیه مراحل">+ {items.length-8} مرحله دیگر در جزئیات کارت</small>}
   </div>}
 </div>;
}

const EMPTY_FILTER={priority:'all',member:'all',label:'all',status:'all',due:'all',attachments:false};
export function matchAdvanced(task,advanced,activeBoardId){
 if(!advanced)return true;
 if(advanced.priority&&advanced.priority!=='all'&&task.priority!==advanced.priority)return false;
 if(advanced.member&&advanced.member!=='all'&&!(task.assignees||[]).includes(advanced.member))return false;
 if(advanced.label&&advanced.label!=='all'&&!(task.labels||[]).some(label=>labelText(label)===advanced.label))return false;
 if(advanced.status&&advanced.status!=='all'&&
     (activeBoardId&&task.boardId===activeBoardId?(task.listId||task.status):task.status)!==advanced.status)return false;
 if(advanced.attachments&&!(task.fileLinks||[]).length&&!(task.attachments||[]).length)return false;
 if(advanced.due!=='all'){
   const day=(task.dueDate||'').slice(0,10);
   const today=localDateKey(new Date());
   if(advanced.due==='overdue'&&(!day||day>=today))return false;
   if(advanced.due==='today'&&day!==today)return false;
   if(advanced.due==='unset'&&day)return false;
 }
 return true;
}
export function localDateKey(date){
 const pad=value=>String(value).padStart(2,'0');
 return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`;
}
const storeKey='madar-saved-filters-v1';
export function AdvancedFilters({tasks=[],users=[],stages=[],priorities=[],value=EMPTY_FILTER,onChange}){
 const [open,setOpen]=useState(false);
 const [saved,setSaved]=useState([]);
 const [name,setName]=useState('');
 const labels=useMemo(()=>[...new Set(tasks.flatMap(t=>(t.labels||[]).map(labelText)))].sort(),[tasks]);
 useEffect(()=>{try{const result=JSON.parse(localStorage.getItem(storeKey)||'[]');if(Array.isArray(result))setSaved(result.slice(0,20));}catch{}},[]);
 const save=()=>{
   const valueName=name.trim().slice(0,60);if(!valueName)return;
   const next=[...saved.filter(x=>x.name!==valueName),{name:valueName,filter:value}].slice(-20);
   localStorage.setItem(storeKey,JSON.stringify(next));setSaved(next);setName('');
 };
 return <div className="advanced-filter">
   <button className={'filter-toggle '+(open?'selected':'')} onClick={()=>setOpen(v=>!v)} aria-expanded={open}><Filter size={16}/> فیلترهای پیشرفته</button>
   {open&&<section className="filter-popover">
     <div className="filter-header"><strong><Filter size={16}/> فیلتر و جست‌وجو</strong><button onClick={()=>setOpen(false)} aria-label="بستن"><X size={16}/></button></div>
     <div className="filter-grid">
       <label>اولویت<select value={value.priority} onChange={e=>onChange({...value,priority:e.target.value})}><option value="all">همه</option>{(priorities.length?priorities:[{id:'high',label:'بالا'},{id:'medium',label:'متوسط'},{id:'low',label:'کم'}]).map(p=><option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
       <label>مسئول<select value={value.member} onChange={e=>onChange({...value,member:e.target.value})}><option value="all">همه</option>{users.map(u=><option key={u.username} value={u.username}>{u.displayName||u.username}</option>)}</select></label>
       <label>برچسب<select value={value.label} onChange={e=>onChange({...value,label:e.target.value})}><option value="all">همه</option>{labels.map(l=><option key={l} value={l}>{l}</option>)}</select></label>
       <label>مرحله<select value={value.status} onChange={e=>onChange({...value,status:e.target.value})}><option value="all">همه</option>{stages.map(s=><option key={s.id} value={s.id}>{s.label}</option>)}</select></label>
       <label>سررسید<select value={value.due} onChange={e=>onChange({...value,due:e.target.value})}><option value="all">همه</option><option value="today">امروز</option><option value="overdue">عقب‌افتاده</option><option value="unset">بدون موعد</option></select></label>
       <label className="filter-check"><input type="checkbox" checked={value.attachments} onChange={e=>onChange({...value,attachments:e.target.checked})}/> دارای پیوست یا فایل</label>
     </div>
     <div className="filter-save"><input maxLength={60} placeholder="نام جست‌وجوی ذخیره‌شده" value={name} onChange={e=>setName(e.target.value)}/><button onClick={save} disabled={!name.trim()}><Save size={15}/> ذخیره</button></div>
     {!!saved.length&&<div className="saved-searches">{saved.map(item=><div key={item.name}><button onClick={()=>{onChange(item.filter);setOpen(false);}}>{item.name}</button><button title="حذف فیلتر" onClick={()=>{const next=saved.filter(s=>s.name!==item.name);setSaved(next);localStorage.setItem(storeKey,JSON.stringify(next));}}><Trash2 size={13}/></button></div>)}</div>}
     <button className="clear-filters" onClick={()=>onChange({...EMPTY_FILTER})}><Undo2 size={14}/> پاک‌کردن همه فیلترها</button>
   </section>}
 </div>;
}

export function RichDescription({value='',direction='auto',onChange,onDirection,disabled=false}){
 const area=useRef(null),[preview,setPreview]=useState(false);
 const wrap=(before,after=before)=>{
   const node=area.current;if(!node)return;
   const a=node.selectionStart,b=node.selectionEnd;
   const next=value.slice(0,a)+before+value.slice(a,b)+after+value.slice(b);
   onChange(next);
   requestAnimationFrame(()=>{node.focus();node.setSelectionRange(a+before.length,b+before.length);});
 };
 return <div className="rich-description">
   <div className="rich-toolbar">
     <button type="button" title="پررنگ" disabled={disabled} onClick={()=>wrap('**')}><Bold size={16}/></button>
     <button type="button" title="مورب" disabled={disabled} onClick={()=>wrap('*')}><Italic size={16}/></button>
     <button type="button" title="لیست" disabled={disabled} onClick={()=>wrap('- ','')}><List size={16}/></button>
     <button type="button" title="لینک" disabled={disabled} onClick={()=>wrap('[','](https://)')}><Link2 size={16}/></button>
     <span className="rich-separator"/>
     <button type="button" className={direction==='rtl'?'active':''} title="متن راست به چپ" disabled={disabled} onClick={()=>onDirection('rtl')}><AlignRight size={16}/></button>
     <button type="button" className={direction==='ltr'?'active':''} title="متن چپ به راست" disabled={disabled} onClick={()=>onDirection('ltr')}><AlignLeft size={16}/></button>
     <button type="button" className={direction==='auto'?'active':''} title="تشخیص جهت خودکار" disabled={disabled} onClick={()=>onDirection('auto')}><TextCursorInput size={16}/></button>
     <button type="button" className="rich-preview-btn" onClick={()=>setPreview(x=>!x)}>{preview?'ویرایش':'پیش‌نمایش متن'}</button>
   </div>
   {preview?<MarkdownPreview value={value} direction={direction}/>:
     <textarea ref={area} rows={Math.min(8,Math.max(3,value.split('\n').length+1))} placeholder="توضیحات کار؛ با نوار بالا متن را قالب‌بندی کنید." dir={direction} disabled={disabled} value={value} onChange={e=>onChange(e.target.value)}/>}
   <small className="rich-hint">برای ذخیره نوشته‌ها از Markdown ساده استفاده می‌شود؛ HTML اجرا نمی‌شود.</small>
 </div>;
}
