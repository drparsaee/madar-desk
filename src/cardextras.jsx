import React, {useState} from 'react';
import {ChevronDown, ChevronUp, ListChecks, Plus, Trash2, Clock3, Users, Ellipsis, Wallet} from 'lucide-react';
import {CalendarField} from './productivity.jsx';
import {AssigneeSelector} from './members.jsx';
import {CoverColorPicker} from './cover_color_picker.jsx';
import {StageExpenseFields} from './order_finance_fields.jsx';
import './cardextras.css';

const COLOR_RE = /^#[0-9a-fA-F]{6}$/;
const ID_RE = /^[a-zA-Z0-9_-]{1,100}$/;
const CUSTOM_TYPES = ['text', 'number', 'date', 'checkbox', 'select'];
const TYPE_TITLES = {text:'متن', number:'عدد', date:'تاریخ', checkbox:'تأیید', select:'انتخابی'};

function nonEmpty(input, max, label) {
  if (typeof input !== 'string' || !input.trim() || input.length > max) throw new Error(`${label}: مقدار نامعتبر است`);
  return input.trim();
}
function issueId() {
  const cryptoApi = typeof crypto === 'undefined' ? null : crypto;
  return cryptoApi?.randomUUID ? `c-${cryptoApi.randomUUID()}` : `c-${Date.now().toString(36)}${Math.random().toString(36).slice(2,12)}`;
}
function makeUniqueId(occupied, factory = issueId) {
  for (let i = 0; i < 10; i++) {
    const id = factory();
    if (typeof id === 'string' && ID_RE.test(id) && !occupied.has(id)) return id;
  }
  throw new Error('شناسه یکتا ساخته نشد');
}
function cloneGroup(group) {return {...group, items: (group.items || []).map(item => ({...item}))};}
function hasMoney(item) {return typeof item.cost === 'number' && item.cost > 0;}

/** Read a legacy card's flat checklist as its named compatibility group. */
export function cardChecklistGroups(task = {}) {
  if (Array.isArray(task.checklists) && task.checklists.length) {
    const groups = task.checklists.map(cloneGroup);
    // App's current flat editor writes checklist first. The host's migration
    // likewise treats it as authoritative. Reconcile immediately so a named
    // group edit cannot resurrect a stale paid step or undo a recent edit.
    const legacy = groups.find(group => group.id === 'checklist-legacy');
    if (legacy && Array.isArray(task.checklist)) {
      legacy.items = task.checklist.map((item,index) => ({...item,
        id:item.id || legacy.items[index]?.id || `item-compat-${index}`}));
    }
    return groups;
  }
  if (Array.isArray(task.checklists) && task.checklists.length === 0 && !(task.checklist || []).length) return [];
  if (!(task.checklist || []).length) return [];
  return [{id:'checklist-legacy',name:'چک‌لیست',items:task.checklist.map((item, index) =>
    ({...item, id:item.id || `item-compat-${index}`}))}];
}

/**
 * All edits return {checklists, checklist} as one atomic App task-update patch.
 * Legacy flat checklist mirrors ONLY checklist-legacy; named groups never add
 * hidden money to the old financial ledger and cannot delete charged steps.
 */
export function editCardChecklists(task, command, idFactory = issueId) {
  if (!task || !command || typeof command !== 'object') throw new Error('دستور چک‌لیست نامعتبر است');
  const groups = cardChecklistGroups(task);
  const type = command.type;
  const groupIndex = groups.findIndex(group => group.id === command.groupId);
  const group = groups[groupIndex];
  if (type === 'add-group') {
    if (groups.length >= 30) throw new Error('حداکثر ۳۰ چک‌لیست مجاز است');
    groups.push({id:makeUniqueId(new Set(groups.map(g => g.id)), idFactory),
      name:nonEmpty(command.name,180,'نام چک‌لیست'),items:[]});
  } else {
    if (!group) throw new Error('چک‌لیست یافت نشد');
    if (type === 'rename-group') group.name = nonEmpty(command.name, 180, 'نام چک‌لیست');
    else if (type === 'remove-group') {
      if (group.items.some(item=>hasMoney(item)||(item.expenseItems||[]).length>0)) throw new Error('حذف چک‌لیست دارای هزینه ثبت‌شده مجاز نیست');
      groups.splice(groupIndex,1);
    } else if (type === 'add-item') {
      if (group.items.length >= 300) throw new Error('حداکثر ۳۰۰ مرحله در هر چک‌لیست مجاز است');
      group.items.push({id:makeUniqueId(new Set(group.items.map(i => i.id)),idFactory),
        text:nonEmpty(command.text,5000,'متن مرحله'),done:false,cost:0});
    } else {
      const index = group.items.findIndex(item => item.id === command.itemId);
      if (index < 0) throw new Error('مرحله یافت نشد');
      const item = group.items[index];
      if (type === 'rename-item') item.text = nonEmpty(command.text,5000,'متن مرحله');
      else if (type === 'set-expenses') {
        if(group.id==='checklist-legacy')throw new Error('هزینه مرحله اصلی باید از ویرایشگر اصلی ثبت شود');
        const expenses=command.expenseItems;
        if(!Array.isArray(expenses)||expenses.length>50||expenses.some(x=>
          !x||typeof x!=='object'||Array.isArray(x)||typeof x.id!=='string'||
          !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/.test(x.id)||
          typeof x.description!=='string'||!x.description.trim()||x.description.length>300||
          typeof x.partyId!=='string'||!x.partyId||
          !Number.isSafeInteger(x.quantity)||x.quantity<1||x.quantity>1000000||
          (x.unitPrice!==null&&(!Number.isSafeInteger(x.unitPrice)||x.unitPrice<=0))||
          !['RIAL','TOMAN'].includes(x.currency))||
          new Set(expenses.map(x=>x.id)).size!==expenses.length)throw new Error('اقلام هزینه نامعتبرند');
        const existingIds=new Set([
          ...(task.checklist||[]).flatMap(step=>(step.expenseItems||[]).map(x=>x.id)),
          ...groups.flatMap(g=>g.id===group.id?[]:g.items.flatMap(s=>(s.expenseItems||[]).map(x=>x.id)))
        ]);
        if(expenses.some(x=>existingIds.has(x.id)))throw new Error('شناسه هزینه تکراری است');
        item.expenseItems=expenses.map(x=>({...x}));
      }
      else if (type === 'patch-item') {
        const changes=command.changes||{};
        if(Object.keys(changes).some(key=>!['dueDate','assignees'].includes(key))) throw new Error('تنها موعد و مسئول قابل ویرایش است');
        if(Object.hasOwn(changes,'dueDate')) {
          if(typeof changes.dueDate!=='string'||(changes.dueDate&&!/^\d{4}-\d{2}-\d{2}$/.test(changes.dueDate)))throw new Error('تاریخ نامعتبر است');
          item.dueDate=changes.dueDate;
        }
        if(Object.hasOwn(changes,'assignees')) {
          if(!Array.isArray(changes.assignees)||changes.assignees.length>100||
              changes.assignees.some(v=>typeof v!=='string'||v.length>120)) throw new Error('فهرست مسئولان نامعتبر است');
          item.assignees=[...new Set(changes.assignees)];
        }
      }
      else if (type === 'toggle-item') item.done = !item.done;
      else if (type === 'remove-item') {
        if (hasMoney(item)||(item.expenseItems||[]).length) throw new Error('مرحله دارای هزینه ثبت‌شده قابل حذف نیست');
        group.items.splice(index, 1);
      } else if (type === 'move-item') {
        const target = index + (command.direction === 'up' ? -1 : command.direction === 'down' ? 1 : 0);
        if (target < 0 || target >= group.items.length || target === index) return {checklists:groups,checklist:task.checklist || []};
        [group.items[index],group.items[target]] = [group.items[target],group.items[index]];
      } else throw new Error('عملیات ناشناخته است');
    }
  }
  const legacy = groups.find(g => g.id === 'checklist-legacy');
  return {checklists:groups, checklist:legacy ? legacy.items.map(i => ({...i}))
    : type === 'remove-group' && command.groupId === 'checklist-legacy' ? [] : (task.checklist || [])};
}

/** Reject arbitrary CSS, URLs, gradient or image settings before style use. */
export function normalizeCover(cover) {
  if (cover == null) return null;
  if (!cover || typeof cover !== 'object' || Array.isArray(cover) ||
      Object.keys(cover).sort().join(',') !== 'color,size,type' ||
      cover.type !== 'color' || typeof cover.color !== 'string' || !COLOR_RE.test(cover.color) ||
      !['strip','full'].includes(cover.size)) throw new Error('کاور باید فقط یک رنگ HEX معتبر داشته باشد');
  return {type:'color', color:cover.color.toUpperCase(), size:cover.size};
}
/** White/near-black foreground selection for full-card solid color covers. */
export function coverTextColor(hex){
  if(typeof hex!=='string'||!COLOR_RE.test(hex))return '#152238';
  const [r,g,b]=[1,3,5].map(i=>{
    const channel=parseInt(hex.slice(i,i+2),16)/255;
    return channel<=.04045?channel/12.92:Math.pow((channel+.055)/1.055,2.4);
  });
  const lum=.2126*r+.7152*g+.0722*b;
  const dark='#142236';
  const linear=channel=>{
    const value=channel/255;
    return value<=.04045?value/12.92:Math.pow((value+.055)/1.055,2.4);
  };
  const darkLum=.2126*linear(0x14)+.7152*linear(0x22)+.0722*linear(0x36);
  // WCAG AA normal text: avoid unreadable white on mid-grey covers.
  // The dark accent is retained when it passes; black is the safe fallback.
  if(1.05/(lum+.05)>=4.5)return '#FFFFFF';
  return (lum+.05)/(darkLum+.05)>=4.5?dark:'#000000';
}

export function editCardFieldValues(task, field, value) {
  if (!field || typeof field.id !== 'string' || !field.id.trim() || field.id.length > 100)
    throw new Error('شناسه فیلد نامعتبر است');
  if (value !== null && value !== undefined) {
    if (field.type === 'text') {if (typeof value !== 'string' || value.length > 5000) throw new Error('متن نامعتبر است');}
    else if (field.type === 'number') {if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('عدد نامعتبر است');}
    else if (field.type === 'checkbox') {if (typeof value !== 'boolean') throw new Error('گزینه تأیید نامعتبر است');}
    else if (field.type === 'date') {
      if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || Number(value.slice(0,4)) < 1 || !Number.isFinite(Date.parse(value)) ||
        new Date(value).toISOString().slice(0,10) !== value) throw new Error('تاریخ باید میلادی معتبر YYYY-MM-DD باشد');
    } else if (field.type === 'select') {
      if (!field.options?.some(option => option.id === value)) throw new Error('گزینه تعریف نشده است');
    } else throw new Error('نوع فیلد نامعتبر است');
  }
  return {customFieldValues:{...(task?.customFieldValues || {}),[field.id]:value ?? null}};
}

/** Edit board-level field definitions without invalidating task/template references. */
export function editBoardFields(board, tasks = [], templates = [], command, idFactory = issueId) {
  if (!board || !Array.isArray(board.customFields)) throw new Error('برد معتبر نیست');
  const fields = board.customFields.map(field => ({...field,options:field.options?.map(o => ({...o})) || []}));
  if (command.type === 'add') {
    if (fields.length >= 50) throw new Error('حداکثر ۵۰ فیلد سفارشی مجاز است');
    if (!CUSTOM_TYPES.includes(command.fieldType)) throw new Error('نوع فیلد نامعتبر است');
    const name = nonEmpty(command.name,100,'نام فیلد');
    const rawOptions = command.fieldType === 'select' ? (command.options || []) : [];
    if (!Array.isArray(rawOptions) || rawOptions.length > 100 || (command.fieldType === 'select' && !rawOptions.length))
      throw new Error('گزینه‌های فیلد انتخابی نامعتبرند');
    const choices = [], used = new Set();
    for (const text of rawOptions) {
      const label = nonEmpty(text,100,'گزینه');
      if (choices.some(o => o.label === label)) throw new Error('گزینه تکراری است');
      const id = makeUniqueId(used,idFactory); used.add(id); choices.push({id,label});
    }
    fields.push({id:makeUniqueId(new Set(fields.map(f => f.id)),idFactory), name,
      type:command.fieldType, options:choices});
  } else if (command.type === 'rename') {
    const field = fields.find(f => f.id === command.fieldId);
    if (!field) throw new Error('فیلد پیدا نشد');
    field.name = nonEmpty(command.name,100,'نام فیلد');
  } else if (command.type === 'remove') {
    const index = fields.findIndex(f => f.id === command.fieldId);
    if (index < 0) throw new Error('فیلد پیدا نشد');
    const used = [...tasks.filter(t => t.boardId === board.id), ...templates.filter(t => t.boardId === board.id)]
      .some(entry => Object.prototype.hasOwnProperty.call(entry.customFieldValues || {},command.fieldId));
    if (used) throw new Error('فیلد در یک کارت یا قالب استفاده شده است');
    fields.splice(index,1);
  } else throw new Error('عملیات فیلد ناشناخته است');
  return {...board, customFields:fields};
}

function ActionError({message}) {return message ? <p className="cardextras-error" role="alert">{message}</p> : null;}

function ChecklistRow({task,group,item,onEdit,disabled,users=[],calendar='jalali',projectId='',canManage=false,accountView=null,onOpenPurchase}) {
  const [editing,setEditing] = useState(false);
  const [menu,setMenu]=useState('');
  const [draft,setDraft] = useState(item.text);
  const commit = () => {if (!draft.trim()) return;onEdit({type:'rename-item',groupId:group.id,itemId:item.id,text:draft});setEditing(false);};
  const edit=changes=>onEdit({type:'patch-item',groupId:group.id,itemId:item.id,changes});
  return <li className="cardextras-checkitem cardextras-checkitem--compact" onKeyDown={event=>{if(event.key==='Escape'&&menu){event.stopPropagation();setMenu('');}}}>
   <div className="cardextras-checkitem__line">
    <input type="checkbox" aria-label={'انجام '+item.text} checked={Boolean(item.done)} disabled={disabled}
      onChange={() => onEdit({type:'toggle-item',groupId:group.id,itemId:item.id})}/>
    {editing ? <input className="cardextras-grow" value={draft} maxLength={5000} aria-label="ویرایش متن مرحله"
      onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();commit();}if(e.key==='Escape')setEditing(false);}}/>
      : <button type="button" className={item.done?'cardextras-complete cardextras-grow cardextras-checkitem__title':'cardextras-grow cardextras-checkitem__title'} disabled={disabled} onClick={()=>{setDraft(item.text);setEditing(true);}}>{item.text}</button>}
    {editing&&<button type="button" disabled={disabled||!draft.trim()} onClick={commit}>ذخیره</button>}
    <div className="cardextras-checkitem__actions">
      <button type="button" aria-label={'زمان '+item.text} aria-expanded={menu==='date'} onClick={()=>setMenu(v=>v==='date'?'':'date')}><Clock3 size={15}/></button>
      <button type="button" aria-label={'مسئول '+item.text} aria-expanded={menu==='members'} onClick={()=>setMenu(v=>v==='members'?'':'members')}><Users size={15}/></button>
      {canManage&&<button type="button" aria-label={'هزینه '+item.text} aria-expanded={menu==='cost'} onClick={()=>setMenu(v=>v==='cost'?'':'cost')}><Wallet size={15}/>{(item.expenseItems||[]).length>0&&<span className="cardextras-checkitem__expense-count">{item.expenseItems.length}</span>}</button>}
      <button type="button" aria-label={'بیشتر '+item.text} aria-expanded={menu==='more'} onClick={()=>setMenu(v=>v==='more'?'':'more')}><Ellipsis size={15}/></button>
    </div>
   </div>
   {menu&&<div className="cardextras-checkitem__menu" role="group" aria-label={'گزینه‌های '+item.text}>
     {menu==='date'&&<CalendarField value={item.dueDate||''} calendar={calendar} disabled={disabled} label="موعد مرحله" onChange={dueDate=>edit({dueDate})} popupOnClick/>}
     {menu==='members'&&<AssigneeSelector users={users} projectId={projectId} value={item.assignees||[]} disabled={disabled} onChange={assignees=>edit({assignees})}/>}
     {menu==='cost'&&canManage&&<StageExpenseFields task={task} step={item}
       parties={Object.values(accountView?.parties||{})} existingJobs={accountView?.contractorJobs||{}}
       accountReady={Boolean(accountView)} canEdit={!disabled} onPrepare={onOpenPurchase}
       onExpenseItemsChange={expenseItems=>onEdit({type:'set-expenses',groupId:group.id,itemId:item.id,expenseItems})}/>}
     {menu==='more'&&<div className="cardextras-checkitem__more">
    <button type="button" disabled={disabled} title="یک مرحله بالاتر" aria-label={'بالا بردن '+item.text}
      onClick={()=>onEdit({type:'move-item',groupId:group.id,itemId:item.id,direction:'up'})}><ChevronUp size={14}/></button>
    <button type="button" disabled={disabled} title="یک مرحله پایین‌تر" aria-label={'پایین بردن '+item.text}
      onClick={()=>onEdit({type:'move-item',groupId:group.id,itemId:item.id,direction:'down'})}><ChevronDown size={14}/></button>
    <button type="button" disabled={disabled||item.cost>0||(item.expenseItems||[]).length>0} title={item.cost>0?'ابتدا هزینه ثبت‌شده را از بخش مالی مدیریت کنید':'حذف مرحله'}
      aria-label={'حذف '+item.text} onClick={()=>onEdit({type:'remove-item',groupId:group.id,itemId:item.id})}><Trash2 size={15}/></button>
     </div>}
   </div>}
  </li>;
}

function ChecklistGroup({task,group,disabled,onEdit,users,calendar,projectId,canManage,accountView,onOpenPurchase}) {
  const [newItem,setNewItem] = useState('');
  const [rename,setRename] = useState(false);
  const [name,setName] = useState(group.name);
  const [expanded,setExpanded] = useState(true);
  const completed=group.items.filter(item=>item.done).length;
  const add = () => {if(newItem.trim()){onEdit({type:'add-item',groupId:group.id,text:newItem});setNewItem('');}};
  const saveName = () => {if(name.trim()){onEdit({type:'rename-group',groupId:group.id,name});setRename(false);}};
  return <section className="cardextras-group" aria-label={'چک‌لیست '+group.name}>
    <div className="cardextras-grouphead">
      <button type="button" onClick={()=>setExpanded(value=>!value)} aria-expanded={expanded} aria-label={'نمایش '+group.name}>
        {expanded?<ChevronUp size={16}/>:<ChevronDown size={16}/>}</button>
      {rename ? <input className="cardextras-grow" value={name} maxLength={180} aria-label="نام چک‌لیست"
        onChange={e=>setName(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();saveName();}}}/>
        : <strong className="cardextras-grow">{group.name}</strong>}
      <span className="cardextras-progress">{completed.toLocaleString('fa-IR')} / {group.items.length.toLocaleString('fa-IR')}</span>
      {rename ? <button type="button" disabled={disabled||!name.trim()} onClick={saveName}>ذخیره</button>
        : <button type="button" disabled={disabled} onClick={()=>{setName(group.name);setRename(true);}}>تغییر نام</button>}
      <button type="button" disabled={disabled||group.items.some(item=>item.cost>0||(item.expenseItems||[]).length>0)} title="حذف چک‌لیست بدون هزینه"
        aria-label={'حذف چک‌لیست '+group.name} onClick={()=>onEdit({type:'remove-group',groupId:group.id})}><Trash2 size={15}/></button>
    </div>
    {expanded && <>
      <div className="cardextras-track"><span style={{width:`${group.items.length?completed/group.items.length*100:0}%`}}/></div>
      <ul className="cardextras-items">{group.items.map(item=><ChecklistRow key={item.id} task={task} group={group} item={item}
        disabled={disabled} onEdit={onEdit} users={users} calendar={calendar} projectId={projectId}
        canManage={canManage} accountView={accountView} onOpenPurchase={onOpenPurchase}/>)}</ul>
      {!disabled&& <div className="cardextras-addrow"><input aria-label={'مرحله جدید '+group.name} placeholder="مرحله جدید..."
        value={newItem} maxLength={5000} onChange={e=>setNewItem(e.target.value)}
        onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();add();}}}/>
        <button type="button" disabled={!newItem.trim()||group.items.length>=300} onClick={add}><Plus size={15}/> افزودن</button></div>}
    </>}
  </section>;
}

export function CardChecklists({task,onChange,disabled=false,hideLegacy=false,users=[],calendar='jalali',canManage=false,accountView=null,onOpenPurchase}) {
  const [name,setName] = useState('');
  const [error,setError] = useState('');
  const groups=cardChecklistGroups(task);
  const visibleGroups=hideLegacy?groups.filter(group=>group.id!=='checklist-legacy'):groups;
  const update=command=>{try{onChange(editCardChecklists(task,command));setError('');}
    catch(e){setError(e.message||String(e));}};
  const add=()=>{if(name.trim()){update({type:'add-group',name});setName('');}};
  return <div className="cardextras" dir="rtl">
    <h3><ListChecks size={17}/> چک‌لیست‌های کارت</h3>
    {visibleGroups.map(group=><ChecklistGroup key={group.id} task={task} group={group} disabled={disabled} onEdit={update} users={users} calendar={calendar} projectId={task.projectId} canManage={canManage} accountView={accountView} onOpenPurchase={onOpenPurchase}/>)}
    {!visibleGroups.length&&<p className="cardextras-muted">هنوز چک‌لیست دیگری ثبت نشده است.</p>}
    {!disabled&&<div className="cardextras-addrow"><input aria-label="نام چک‌لیست جدید" value={name} maxLength={180}
      placeholder="نام چک‌لیست جدید" onChange={e=>setName(e.target.value)}
      onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();add();}}}/>
      <button type="button" onClick={add} disabled={!name.trim()||groups.length>=30}><Plus size={15}/> چک‌لیست جدید</button></div>}
    <ActionError message={error}/>
  </div>;
}

export function CardCover({task,onChange,disabled=false}) {
  const [error,setError] = useState('');
  let cover = null;
  try {cover=normalizeCover(task?.cover);} catch { /* corrupt old cover is never painted */ }
  const change=value=>{try{onChange({cover:normalizeCover(value)});setError('');}catch(e){setError(e.message||String(e));}};
  const size=cover?.size||'strip', color=cover?.color||'#5672CA';
  return <div className="cardextras card-cover-editor" dir="rtl">
    <div className="card-cover-editor__header"><h3>کاور کارت</h3>
      {cover&&<button type="button" disabled={disabled} onClick={()=>change(null)}>حذف کاور</button>}
    </div>
    <div className="card-cover-editor__modes" role="group" aria-label="شیوه نمایش کاور">
      <button type="button" disabled={disabled} aria-pressed={size==='strip'}
        onClick={()=>change({type:'color',color,size:'strip'})}>نوار بالای کارت</button>
      <button type="button" disabled={disabled} aria-pressed={size==='full'}
        onClick={()=>change({type:'color',color,size:'full'})}>رنگ تمام کارت</button>
    </div>
    <div className={'card-cover-editor__preview card-cover-editor__preview--'+size}
      style={{'--cover-preview-color':color,'--cover-preview-contrast':coverTextColor(color)}}
      role="img" aria-label={'نمایش کاور '+(size==='full'?'تمام کارت':'نواری')+' با رنگ '+color}>
      {size==='strip'&&<span className="card-cover-editor__preview-band"/>}
      <span className="card-cover-editor__preview-title">{task?.title||'عنوان کارت'}</span>
      <span className="card-cover-editor__preview-line"/>
      <span className="card-cover-editor__preview-line short"/>
    </div>
    <CoverColorPicker value={color} disabled={disabled}
      onChange={next=>change({type:'color',color:next,size})}/>
    <ActionError message={error}/>
  </div>;
}

export function CardCustomFields({task,board,onChange,disabled=false,calendar='jalali'}) {
  const [error,setError] = useState('');
  const fields=board?.customFields||[];
  const values=task?.customFieldValues||{};
  const write=(field,value)=>{try{onChange(editCardFieldValues(task,field,value));setError('');}
    catch(e){setError(e.message||String(e));}};
  return <div className="cardextras" dir="rtl">
    <h3>فیلدهای سفارشی</h3>
    {fields.map(field=><div className="cardextras-field" key={field.id}>
      {field.type==='checkbox'?<label><input type="checkbox" disabled={disabled} checked={values[field.id]===true}
        onChange={e=>write(field,e.target.checked)}/>{field.name}</label>:
      field.type==='date'?<CalendarField label={field.name} calendar={calendar} disabled={disabled}
        value={values[field.id]||''} onChange={value=>write(field,value||null)}/>:
      field.type==='select'?<label>{field.name}<select disabled={disabled} value={values[field.id]||''}
        onChange={e=>write(field,e.target.value||null)}><option value="">انتخاب نشده</option>
        {(field.options||[]).map(option=><option key={option.id} value={option.id}>{option.label}</option>)}</select></label>:
      field.type==='number'?<label>{field.name}<input type="number" disabled={disabled} step="any"
        value={values[field.id]??''} onChange={e=>write(field,e.target.value===''?null:Number(e.target.value))}/></label>:
      <label>{field.name}<input type="text" disabled={disabled} maxLength={5000} value={values[field.id]||''}
        onChange={e=>write(field,e.target.value)}/></label>}
    </div>)}
    {!fields.length&&<p className="cardextras-muted">فیلد سفارشی برای این برد تعریف نشده است.</p>}
    <ActionError message={error}/>
  </div>;
}

export function BoardFieldEditor({board,tasks=[],templates=[],onChange,disabled=false}) {
  const [name,setName] = useState('');
  const [type,setType] = useState('text');
  const [options,setOptions] = useState('');
  const [error,setError] = useState('');
  const apply=command=>{try{onChange(editBoardFields(board,tasks,templates,command));setError('');}
    catch(e){setError(e.message||String(e));}};
  const create=()=>{apply({type:'add',name,fieldType:type,options:type==='select'?
    options.split(/[،,\n]/).map(v=>v.trim()).filter(Boolean):[]});};
  return <div className="cardextras" dir="rtl"><h3>تعریف فیلدهای برد</h3>
    {(board?.customFields||[]).map(field=><div className="cardextras-fieldrow" key={field.id}>
      <span className="cardextras-grow">{field.name} ({TYPE_TITLES[field.type]||field.type})</span>
      <button type="button" disabled={disabled} onClick={()=>{
        const label=typeof window!=='undefined'?window.prompt('نام تازه فیلد',field.name):null;
        if(label!==null)apply({type:'rename',fieldId:field.id,name:label});}}>تغییر نام</button>
      <button type="button" disabled={disabled} onClick={()=>apply({type:'remove',fieldId:field.id})}
        aria-label={'حذف فیلد '+field.name}><Trash2 size={15}/></button>
    </div>)}
    {!disabled&&<div className="cardextras-addrow">
      <input aria-label="نام فیلد جدید" maxLength={100} value={name} onChange={e=>setName(e.target.value)}/>
      <select aria-label="نوع فیلد جدید" value={type} onChange={e=>setType(e.target.value)}>
        {CUSTOM_TYPES.map(key=><option value={key} key={key}>{TYPE_TITLES[key]}</option>)}</select>
      {type==='select'&&<input aria-label="گزینه‌های انتخابی" placeholder="گزینه‌ها با ویرگول جدا شوند"
        value={options} onChange={e=>setOptions(e.target.value)}/>}
      <button type="button" disabled={!name.trim()||(board?.customFields||[]).length>=50} onClick={create}>
        <Plus size={15}/> افزودن فیلد</button>
    </div>}
    <ActionError message={error}/>
  </div>;
}
