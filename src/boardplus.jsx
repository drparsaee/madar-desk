import React,{useEffect,useMemo,useRef,useState} from 'react';
import {AlignLeft,AlignRight,Bold,Check,ChevronDown,ChevronUp,Filter,Italic,Link2,
 List,Save,Search,TextCursorInput,Trash2,Undo2,X} from 'lucide-react';
import {MarkdownPreview} from './markdown.jsx';
import {FILTER_LIMITS,matchFilterTree,validateFilterTree} from './advanced_filter_engine.js';
import {taskIsCompleted} from './task_completion.js';

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
 if(typeof advanced!=='object'||Array.isArray(advanced)||
     (advanced.due!==undefined&&!['all','today','overdue','unset'].includes(advanced.due))||
     (advanced.attachments!==undefined&&typeof advanced.attachments!=='boolean'))return false;
 if(advanced.priority&&advanced.priority!=='all'&&task.priority!==advanced.priority)return false;
 if(advanced.member&&advanced.member!=='all'&&!(task.assignees||[]).includes(advanced.member))return false;
 if(advanced.label&&advanced.label!=='all'&&!(task.labels||[]).some(label=>labelText(label)===advanced.label))return false;
 if(advanced.status&&advanced.status!=='all'&&
     (activeBoardId&&task.boardId===activeBoardId?(task.listId||task.status):task.status)!==advanced.status)return false;
 if(advanced.attachments&&!(task.fileLinks||[]).length&&!(task.attachments||[]).length)return false;
 if(advanced.due!=='all'){
   const day=(task.dueDate||'').slice(0,10);
   const today=localDateKey(new Date());
   // A card completed in place is not overdue even if its board lane did
   // not change. Moving it to the legacy 'done' lane can post finance events.
   if(advanced.due==='overdue'&&
       (!day||day>=today||taskIsCompleted(task)))return false;
   if(advanced.due==='today'&&day!==today)return false;
   if(advanced.due==='unset'&&day)return false;
 }
 return matchFilterTree(task,advanced.rules,activeBoardId);
}
export function localDateKey(date){
 const pad=value=>String(value).padStart(2,'0');
 return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`;
}
// Never reuse the legacy unscoped key. Its contents cannot be attributed to
// an authenticated user or board, so importing it would expose another
// user's saved searches. Leave that key untouched for explicit recovery.
export function savedFilterStorageKey(identity,scopeId){
 if(typeof identity!=='string'||!identity.trim()||
    typeof scopeId!=='string'||!scopeId.trim()||
    identity.length>1024||scopeId.length>512)return '';
 try{
   // Never truncate a caller identity: users with long shared host prefixes
   // could otherwise collide and read each other's saved filter metadata.
   return 'madar-saved-filters-v2:'+
     encodeURIComponent(identity)+':'+encodeURIComponent(scopeId);
 }catch{return '';}
}
const FILTER_FIELD_LABELS={priority:'اولویت',member:'مسئول',label:'برچسب',status:'مرحله',due:'سررسید',attachments:'پیوست',title:'عنوان کارت'};
const FILTER_DUE_OPTIONS=[{value:'today',label:'امروز'},{value:'overdue',label:'عقب‌افتاده'},{value:'unset',label:'بدون موعد'}];
const FILTER_ATTACHMENT_OPTIONS=[{value:'yes',label:'دارد'},{value:'no',label:'ندارد'}];
const asOptions=items=>items.map(item=>typeof item==='string'?{value:item,label:item}:item);
function defaultRule(options){return {field:'priority',comparison:'is',value:options.priority[0]?.value||'high'};}
function replaceRuleAtPath(root,path,replace){
 if(!path.length)return replace(root);
 const [first,...rest]=path;
 return {...root,children:root.children.map((child,i)=>i===first?replaceRuleAtPath(child,rest,replace):child)};
}
function RuleEditor({node,path,depth,options,nodes,onChangeRoot,onRemove}){
 const update=fn=>onChangeRoot(root=>replaceRuleAtPath(root,path,fn));
 if(!Object.prototype.hasOwnProperty.call(node,'op')){
   const choices=options[node.field]||[];
   const isTitle=node.field==='title';
   const changeField=field=>{
     const next=options[field]||[];
     update(()=>({field,comparison:field==='title'?'contains':'is',value:field==='title'?'عنوان':(next[0]?.value||'unknown')}));
   };
   return <div className="filter-rule">
     <label>فیلد<select aria-label="فیلد شرط" value={node.field} onChange={e=>changeField(e.target.value)}>{Object.entries(FILTER_FIELD_LABELS).map(([field,label])=><option key={field} value={field}>{label}</option>)}</select></label>
     <label>مقایسه<select aria-label="مقایسه شرط" value={node.comparison} onChange={e=>update(old=>({...old,comparison:e.target.value}))}>{(isTitle?[['contains','شامل'],['notContains','شامل نباشد']]:[['is','برابر'],['isNot','برابر نباشد']]).map(([v,label])=><option key={v} value={v}>{label}</option>)}</select></label>
     <label className="filter-rule-value">مقدار{isTitle?<input aria-label="عبارت عنوان" maxLength={FILTER_LIMITS.text} value={node.value} onChange={e=>update(old=>({...old,value:e.target.value}))}/>:choices.length?<select aria-label="مقدار شرط" value={node.value} onChange={e=>update(old=>({...old,value:e.target.value}))}>{!choices.some(option=>option.value===node.value)&&<option value={node.value}>{node.value}</option>}{choices.map(item=><option key={item.value} value={item.value}>{item.label}</option>)}</select>:<input aria-label="مقدار شرط" maxLength={FILTER_LIMITS.text} value={node.value} onChange={e=>update(old=>({...old,value:e.target.value}))}/>}</label>
     <button className="filter-rule-remove" type="button" aria-label="حذف شرط" title="حذف شرط" onClick={onRemove}><Trash2 size={15}/></button>
   </div>;
 }
 const canAdd=nodes<FILTER_LIMITS.nodes&&node.children.length<FILTER_LIMITS.children;
 return <div className={'filter-rule-group '+(depth?'nested':'')}>
   <div className="filter-rule-group-header">
     <label>ترکیب شرط‌ها <select aria-label="نوع ترکیب شرط‌ها" value={node.op} onChange={e=>update(old=>({...old,op:e.target.value}))}><option value="and">همه (AND)</option><option value="or">یکی (OR)</option></select></label>
     {depth>0&&<button type="button" aria-label="حذف گروه" title="حذف گروه" onClick={onRemove}><Trash2 size={15}/></button>}
   </div>
   {node.children.map((child,i)=><RuleEditor key={i} node={child} path={[...path,i]} depth={depth+1} options={options} nodes={nodes} onChangeRoot={onChangeRoot} onRemove={()=>node.children.length===1&&depth>0?onRemove():update(group=>({...group,children:group.children.filter((_,index)=>index!==i)}))}/>)}
   <div className="filter-rule-actions">
     <button type="button" disabled={!canAdd} onClick={()=>update(group=>({...group,children:[...group.children,defaultRule(options)]}))}>+ شرط</button>
     <button type="button" disabled={!canAdd||nodes+2>FILTER_LIMITS.nodes||depth>=FILTER_LIMITS.depth-1} onClick={()=>update(group=>({...group,children:[...group.children,{op:'and',children:[defaultRule(options)]}]}))}>+ گروه</button>
   </div>
 </div>;
}
export function AdvancedFilters({tasks=[],users=[],stages=[],priorities=[],value=EMPTY_FILTER,onChange,
 identity='solo:local',scopeId='workspace:default'}){
 const [open,setOpen]=useState(false);
 const [saved,setSaved]=useState([]);
 const [name,setName]=useState('');
 const [saveError,setSaveError]=useState('');
 const storeKey=useMemo(()=>savedFilterStorageKey(identity,scopeId),[identity,scopeId]);
 const active=value||EMPTY_FILTER;
 const tree=active.rules??{op:'and',children:[]};
 const treeValidation=validateFilterTree(tree);
 const editableTree=validateFilterTree(tree,{allowEmptyText:true});
 const labels=useMemo(()=>[...new Set(tasks.flatMap(t=>(t.labels||[]).map(labelText)))].sort(),[tasks]);
 const ruleOptions={
   priority:asOptions((priorities.length?priorities:[{id:'high',label:'بالا'},{id:'medium',label:'متوسط'},{id:'low',label:'کم'}]).map(p=>({value:p.id,label:p.label}))),
   member:users.map(u=>({value:u.username,label:u.displayName||u.username})),
   label:asOptions(labels),status:stages.map(s=>({value:s.id,label:s.label})),
   due:FILTER_DUE_OPTIONS,attachments:FILTER_ATTACHMENT_OPTIONS
 };
 const changeRules=change=>{
   if(!editableTree.valid)return;
   const next=change(tree);
   onChange({...active,rules:next.children.length?next:null});
 };
 useEffect(()=>{
   setSaved([]);setSaveError('');
   if(!storeKey)return;
   try{
     const result=JSON.parse(localStorage.getItem(storeKey)||'[]');
     if(Array.isArray(result))setSaved(result.slice(0,20));
   }catch{}
 },[storeKey]);
 const save=()=>{
   const valueName=name.trim().slice(0,60);
   if(!valueName||!treeValidation.valid||!storeKey)return;
   const next=[...saved.filter(x=>x.name!==valueName),{name:valueName,filter:active}].slice(-20);
   try{
     localStorage.setItem(storeKey,JSON.stringify(next));
     setSaved(next);setName('');setSaveError('');
   }catch{setSaveError('ذخیره فیلتر در این دستگاه ممکن نیست. فضای ذخیره‌سازی را بررسی کنید.');}
 };
 const removeSaved=valueName=>{
   if(!storeKey)return;
   const next=saved.filter(item=>item.name!==valueName);
   try{localStorage.setItem(storeKey,JSON.stringify(next));setSaved(next);setSaveError('');}
   catch{setSaveError('حذف فیلتر ذخیره نشد. فضای ذخیره‌سازی را بررسی کنید.');}
 };
 return <div className="advanced-filter">
   <button className={'filter-toggle '+(open?'selected':'')} onClick={()=>setOpen(v=>!v)} aria-expanded={open}><Filter size={16}/> فیلترهای پیشرفته</button>
   {open&&<section className="filter-popover">
     <div className="filter-header"><strong><Filter size={16}/> فیلتر و جست‌وجو</strong><button onClick={()=>setOpen(false)} aria-label="بستن"><X size={16}/></button></div>
     <div className="filter-grid">
       <label>اولویت<select value={active.priority||'all'} onChange={e=>onChange({...active,priority:e.target.value})}><option value="all">همه</option>{ruleOptions.priority.map(p=><option key={p.value} value={p.value}>{p.label}</option>)}</select></label>
       <label>مسئول<select value={active.member||'all'} onChange={e=>onChange({...active,member:e.target.value})}><option value="all">همه</option>{users.map(u=><option key={u.username} value={u.username}>{u.displayName||u.username}</option>)}</select></label>
       <label>برچسب<select value={active.label||'all'} onChange={e=>onChange({...active,label:e.target.value})}><option value="all">همه</option>{labels.map(l=><option key={l} value={l}>{l}</option>)}</select></label>
       <label>مرحله<select value={active.status||'all'} onChange={e=>onChange({...active,status:e.target.value})}><option value="all">همه</option>{stages.map(s=><option key={s.id} value={s.id}>{s.label}</option>)}</select></label>
       <label>سررسید<select value={active.due||'all'} onChange={e=>onChange({...active,due:e.target.value})}><option value="all">همه</option><option value="today">امروز</option><option value="overdue">عقب‌افتاده</option><option value="unset">بدون موعد</option></select></label>
       <label className="filter-check"><input type="checkbox" checked={!!active.attachments} onChange={e=>onChange({...active,attachments:e.target.checked})}/> دارای پیوست یا فایل</label>
     </div>
     <details className="filter-rule-builder"><summary>شرط‌های ترکیبی (AND / OR) {treeValidation.valid&&treeValidation.nodes>1?`(${treeValidation.nodes-1})`:''}</summary>
       {!treeValidation.valid&&<p className="filter-rule-error" role="alert">{treeValidation.error} فیلتر نامعتبر نتیجه‌ای نمایش نمی‌دهد.</p>}
       {editableTree.valid?<RuleEditor node={tree} path={[]} depth={0} options={ruleOptions} nodes={editableTree.nodes} onChangeRoot={changeRules}/>:
         <button type="button" className="filter-rule-reset" onClick={()=>onChange({...active,rules:null})}>حذف شرط‌های نامعتبر</button>}
       <small>فیلترهای معمولی و شرط‌های ترکیبی هم‌زمان اعمال می‌شوند. حداکثر {FILTER_LIMITS.nodes} بخش و {FILTER_LIMITS.depth} سطح تو در تو.</small>
     </details>
     <div className="filter-save"><input maxLength={60} placeholder="نام جست‌وجوی ذخیره‌شده" value={name} onChange={e=>setName(e.target.value)}/><button onClick={save} disabled={!storeKey||!name.trim()||!treeValidation.valid}><Save size={15}/> ذخیره</button></div>
     {saveError&&<small role="alert" className="filter-rule-error">{saveError}</small>}
     {!!saved.length&&<div className="saved-searches">{saved.map(item=><div key={item.name}><button onClick={()=>{onChange(item.filter);setOpen(false);}}>{item.name}</button><button title="حذف فیلتر" aria-label={'حذف فیلتر '+item.name} onClick={()=>removeSaved(item.name)}><Trash2 size={13}/></button></div>)}</div>}
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
