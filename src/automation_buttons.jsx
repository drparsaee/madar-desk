import React,{useCallback,useEffect,useRef,useState} from 'react';
import {
  Bell,Bookmark,Check,CheckCircle2,ChevronDown,Flag,Heart,Info,LayoutDashboard,
  LoaderCircle,MessageSquareText,MousePointerClick,PenLine,Play,Plus,RefreshCw,
  Rocket,Save,Search,Settings2,ShieldAlert,Star,Trash2,X,Zap,
} from 'lucide-react';
import './automation_buttons.css';

const ICONS=[
  {id:'zap',name:'جرقه',Icon:Zap},{id:'bell',name:'زنگ',Icon:Bell},
  {id:'message-square',name:'پیام',Icon:MessageSquareText},{id:'check-circle-2',name:'تأیید',Icon:CheckCircle2},
  {id:'flag',name:'پرچم',Icon:Flag},{id:'star',name:'ستاره',Icon:Star},
  {id:'rocket',name:'موشک',Icon:Rocket},{id:'bookmark',name:'نشانک',Icon:Bookmark},
  {id:'heart',name:'قلب',Icon:Heart},{id:'settings-2',name:'تنظیمات',Icon:Settings2},
  {id:'mouse-pointer-click',name:'کلیک',Icon:MousePointerClick},{id:'layout-dashboard',name:'برد',Icon:LayoutDashboard},
];
const ICON_MAP=Object.fromEntries(ICONS.map(item=>[item.id,item.Icon]));
const USERNAME=/^[A-Za-z0-9][A-Za-z0-9._-]{2,39}$/;
const SCOPE_NAMES={card:'کارت',board:'برد'};
const iconFor=id=>ICON_MAP[id]||Zap;
const emptyDraft=(scope,boardId)=>({title:'',icon:'zap',scope,boardId:boardId||'',enabled:true,closeAfterAction:false,actions:[]});
const errorText=e=>e?.message||String(e);

// The host, not this panel, enforces project permissions and the action allowlist.
export function validateAutomationButton(draft,{projectId,boardId,users=[]}){
  if(!projectId||typeof projectId!=='string')throw Error('پروژه‌ای برای ثبت دکمه انتخاب نشده است.');
  if(!boardId||typeof boardId!=='string')throw Error('برای ساخت دکمه، ابتدا یک برد انتخاب کنید.');
  if(!['card','board'].includes(draft.scope))throw Error('نوع دکمه معتبر نیست.');
  if(typeof draft.title!=='string'||!draft.title.trim())throw Error('نام دکمه را وارد کنید.');
  if(draft.title.trim().length>80)throw Error('نام دکمه نباید بیشتر از ۸۰ نویسه باشد.');
  if(!Object.hasOwn(ICON_MAP,draft.icon))throw Error('یک نماد معتبر انتخاب کنید.');
  if(!Array.isArray(draft.actions)||draft.actions.length===0)throw Error('حداقل یک عمل اضافه کنید.');
  if(draft.actions.length>5)throw Error('حداکثر پنج عمل برای هر دکمه مجاز است.');
  const members=new Set(users.filter(user=>USERNAME.test(user?.username||'')).map(user=>user.username));
  const actions=draft.actions.map((action,index)=>{
    const suffix=' (عمل '+(index+1)+')';
    if(!action||!['notify','comment'].includes(action.type))throw Error('این نوع عمل پشتیبانی نمی‌شود'+suffix);
    const text=action.type==='notify'?action.message:action.text;
    if(typeof text!=='string'||!text.trim()||/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(text))throw Error('متن عمل را وارد کنید'+suffix);
    const limit=action.type==='notify'?240:4000;
    if(text.trim().length>limit)throw Error('متن عمل از محدودیت مجاز بیشتر است'+suffix);
    if(action.type==='comment')return {type:'comment',text:text.trim()};
    const username=action.users?.[0];
    if(!Array.isArray(action.users)||action.users.length!==1||!USERNAME.test(username||'')||!members.has(username)){
      throw Error('عضو معتبر برای اعلان انتخاب کنید'+suffix);
    }
    return {type:'notify',users:[username],message:text.trim()};
  });
  return {
    ...(draft.id?{id:draft.id}:{}),projectId,boardId,scope:draft.scope,
    title:draft.title.trim(),icon:draft.icon,enabled:draft.enabled!==false,
    closeAfterAction:draft.scope==='card'&&draft.closeAfterAction===true,actions,
  };
}

function ActionEditor({action,index,members,onChange,onRemove,disabled}){
  const isNotify=action.type==='notify';
  const Icon=isNotify?Bell:MessageSquareText;
  const message=isNotify?action.message:action.text;
  const maxLength=isNotify?240:4000;
  return <article className="ab-action-card">
    <div className="ab-action-heading"><span className="ab-action-symbol"><Icon size={18}/></span>
      <strong>{index+1}. {isNotify?'اعلان به عضو':'ثبت نظر روی کارت'}</strong>
      <button type="button" className="ab-icon-button" aria-label={'حذف عمل '+(index+1)} onClick={onRemove} disabled={disabled}><Trash2 size={16}/></button>
    </div>
    {isNotify&&<label className="ab-field">عضو دریافت‌کننده
      <select required value={action.users?.[0]||''} disabled={disabled} onChange={e=>onChange({...action,users:e.target.value?[e.target.value]:[]})}>
        <option value="">انتخاب عضو</option>
        {members.map(member=><option key={member.username} value={member.username}>{member.displayName||member.username}</option>)}
      </select>
      {!members.length&&<small>عضو معتبر موجود نیست. برای ذخیره، یک عمل «ثبت نظر» انتخاب کنید.</small>}
    </label>}
    <label className="ab-field">متن {isNotify?'اعلان':'نظر'}
      <textarea required rows={3} maxLength={maxLength} disabled={disabled} value={message||''}
        onChange={e=>onChange(isNotify?{...action,message:e.target.value}:{...action,text:e.target.value})}
        placeholder={isNotify?'پیامی که برای عضو ارسال می‌شود':'متنی که روی کارت ثبت می‌شود'}/>
      <small className="ab-character-count" dir="ltr">{(message||'').length} / {maxLength}</small>
    </label>
  </article>;
}

/**
 * Embed as <AutomationButtonsPanel api={api} project={project} boardId={board.id} users={users} />.
 * Set modal={true} and onClose for a standalone dialog. Provide cardId and onCloseCard
 * when card execution is offered. canManage/canRun are UI affordances, never ACL checks.
 */
export function AutomationButtonsPanel({
  api,project,projectId:explicitProjectId,boardId,users=[],scope:requestedScope,initialScope='card',
  cardId,cardOptions=[],onCloseCard,onClose,onSaved,onChanged,modal,canManage=true,canRun=true,
}){
  const isModal=modal??Boolean(onClose);
  const projectId=explicitProjectId||project?.id||'';
  const firstScope=(requestedScope||initialScope)==='board'?'board':'card';
  const [scope,setScope]=useState(firstScope);
  const [selectedCardId,setSelectedCardId]=useState(cardId||'');
  const [buttons,setButtons]=useState([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [runningId,setRunningId]=useState('');
  const [view,setView]=useState('list');
  const [draft,setDraft]=useState(()=>emptyDraft(firstScope,boardId));
  const [iconPicker,setIconPicker]=useState(false);
  const [iconQuery,setIconQuery]=useState('');
  const [actionPicker,setActionPicker]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const dialogRef=useRef(null);
  const titleRef=useRef(null);
  const listSupported=typeof api?.automationButtonsList==='function';
  const saveSupported=typeof api?.automationButtonsSave==='function';
  const deleteSupported=typeof api?.automationButtonsDelete==='function';
  const runSupported=typeof api?.automationButtonRun==='function';
  const validMembers=users.filter(user=>USERNAME.test(user?.username||''));
  const availableCards=cardOptions.filter(item=>item&&typeof item.id==='string'&&item.id);
  const targetCardId=cardId||selectedCardId;

  useEffect(()=>setScope((requestedScope||initialScope)==='board'?'board':'card'),[requestedScope,initialScope]);
  useEffect(()=>setSelectedCardId(cardId||''),[cardId,boardId]);

  const reload=useCallback(async()=>{
    if(!listSupported)throw Error('میزبان فعلی از فهرست دکمه‌های اتوماسیون پشتیبانی نمی‌کند.');
    if(!projectId||!boardId)throw Error('ابتدا پروژه و برد را انتخاب کنید.');
    const items=await api.automationButtonsList({projectId,boardId});
    if(!Array.isArray(items))throw Error('پاسخ فهرست دکمه‌ها از میزبان معتبر نیست.');
    setButtons(items);
    return items;
  },[api,listSupported,projectId,boardId]);

  useEffect(()=>{
    let current=true;
    setLoading(true);setError('');setButtons([]);
    if(!listSupported||!projectId||!boardId){
      setError(!listSupported?'میزبان فعلی قابلیت دکمه‌های اتوماسیون را ارائه نمی‌کند.':'برای بارگذاری دکمه‌ها، پروژه و برد را انتخاب کنید.');
      setLoading(false);return;
    }
    api.automationButtonsList({projectId,boardId})
      .then(items=>{if(!current)return;if(!Array.isArray(items))throw Error('پاسخ فهرست دکمه‌ها معتبر نیست.');setButtons(items);})
      .catch(e=>{if(current)setError(errorText(e));})
      .finally(()=>{if(current)setLoading(false);});
    return()=>{current=false;};
  },[api,listSupported,projectId,boardId]);

  useEffect(()=>{
    if(view==='edit')titleRef.current?.focus();
  },[view]);
  useEffect(()=>{
    if(!isModal||typeof document==='undefined')return;
    const previous=document.activeElement;
    dialogRef.current?.querySelector('button')?.focus();
    const keydown=e=>{
      if(e.key==='Escape'){
        if(iconPicker){setIconPicker(false);return;}
        if(actionPicker){setActionPicker(false);return;}
        if(view==='edit'&&!busy){setView('list');return;}
        if(onClose&&!busy){e.preventDefault();onClose();}return;
      }
      if(e.key!=='Tab'||!dialogRef.current)return;
      const focusable=Array.from(dialogRef.current.querySelectorAll('button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])'))
        .filter(node=>node.getClientRects().length>0);
      if(!focusable.length)return;
      const first=focusable[0],last=focusable[focusable.length-1];
      if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
      else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
    };
    document.addEventListener('keydown',keydown);
    return()=>{document.removeEventListener('keydown',keydown);if(previous?.isConnected)previous.focus();};
  },[isModal,onClose,view,busy,iconPicker,actionPicker]);

  function startNew(){
    setDraft(emptyDraft(scope,boardId));setView('edit');setError('');setNotice('');
    setIconPicker(false);setActionPicker(false);
  }
  function startEdit(button){
    setScope(button.scope==='board'?'board':'card');
    setDraft({...emptyDraft(button.scope,boardId),...button,
      boardId,actions:Array.isArray(button.actions)?button.actions.map(action=>({...action,users:action.users?.slice()})):[]});
    setView('edit');setError('');setNotice('');setActionPicker(false);
  }
  function changeDraft(changes){setDraft(current=>({...current,...changes}));setError('');}
  function addAction(type){
    if(!['notify','comment'].includes(type))return;
    changeDraft({actions:[...draft.actions,type==='notify'?{type:'notify',users:[],message:''}:{type:'comment',text:''}]});
    setActionPicker(false);
  }
  function changeAction(index,action){changeDraft({actions:draft.actions.map((old,i)=>i===index?action:old)});}
  function removeAction(index){changeDraft({actions:draft.actions.filter((_,i)=>i!==index)});}

  async function save(event){
    event?.preventDefault?.();
    let payload;
    try{payload=validateAutomationButton(draft,{projectId,boardId,users:validMembers});}
    catch(e){setError(errorText(e));return;}
    if(!saveSupported){setError('میزبان فعلی ذخیره دکمه را پشتیبانی نمی‌کند.');return;}
    setBusy(true);setError('');setNotice('');
    try{
      const response=await api.automationButtonsSave(payload);
      if(!response||typeof response!=='object'||!response.id)throw Error('میزبان ذخیره را با شناسه دکمه تأیید نکرد.');
      const items=await reload();
      const stored=items.find(item=>item.id===response.id);
      if(!stored)throw Error('ذخیره اعلام شد اما دکمه در فهرست میزبان پیدا نشد. فهرست را تازه‌سازی کنید.');
      if(stored.enabled!==payload.enabled||stored.scope!==payload.scope||stored.closeAfterAction!==payload.closeAfterAction||
        stored.title!==payload.title||stored.icon!==payload.icon||stored.projectId!==projectId||stored.boardId!==boardId||
        JSON.stringify(stored.actions)!==JSON.stringify(payload.actions)){
        throw Error('میزبان همهٔ تنظیمات یا عمل‌های دکمه را مطابق درخواست نگه نداشت؛ ذخیره کامل تأیید نشده است.');
      }
      setView('list');setNotice('دکمه در برد ذخیره شد.');onSaved?.(stored);onChanged?.(stored);
    }catch(e){setError(errorText(e));}
    finally{setBusy(false);}
  }

  async function remove(button){
    if(!deleteSupported){setError('میزبان فعلی حذف دکمه را پشتیبانی نمی‌کند.');return;}
    if(typeof window!=='undefined'&&!window.confirm('دکمه «'+button.title+'» حذف شود؟'))return;
    setBusy(true);setError('');setNotice('');
    try{
      const response=await api.automationButtonsDelete(button.id);
      if(response?.buttonId!==button.id)throw Error('میزبان حذف دکمه را تأیید نکرد.');
      const items=await reload();
      if(items.some(item=>item.id===button.id))throw Error('دکمه هنوز در فهرست میزبان قرار دارد. حذف تأیید نشده است.');
      setNotice('دکمه حذف شد.');
    }
    catch(e){setError(errorText(e));}
    finally{setBusy(false);}
  }

  function runBlockReason(button){
    if(!runSupported)return 'اجرای دکمه در این نسخه از میزبان پشتیبانی نمی‌شود.';
    if(button.enabled===false)return 'این دکمه غیرفعال است.';
    if(!targetCardId)return 'برای اجرای دکمه، ابتدا کارت مقصد را انتخاب کنید.';
    return '';
  }
  async function run(button){
    const blocked=runBlockReason(button);
    if(blocked){setError(blocked);return;}
    setRunningId(button.id);setError('');setNotice('');
    try{
      const result=await api.automationButtonRun({buttonId:button.id,cardId:targetCardId});
      if(result?.ok===false||result?.error)throw Error(result.error||'اجرای دکمه در میزبان ناموفق بود.');
      if(result?.buttonId!==button.id||result?.cardId!==targetCardId)throw Error('میزبان اجرای دکمه روی کارت انتخاب‌شده را تأیید نکرد.');
      setNotice('اجرای دکمه توسط میزبان انجام شد.');
      if(button.scope==='card'&&button.closeAfterAction===true)onCloseCard?.();
    }catch(e){setError(errorText(e));}
    finally{setRunningId('');}
  }

  const filtered=buttons.filter(button=>button.scope===scope);
  const canCreate=canManage&&saveSupported&&listSupported&&!!projectId&&!!boardId;
  const activeIcon=iconFor(draft.icon);
  const pickedIcon=React.createElement(activeIcon,{size:22,'aria-hidden':true});
  const options=ICONS.filter(icon=>(icon.name+' '+icon.id).toLowerCase().includes(iconQuery.toLowerCase().trim()));
  const workspace=<section className="ab-panel" dir="rtl" ref={dialogRef} role={isModal?'dialog':'region'} aria-modal={isModal?'true':undefined} aria-label="دکمه‌های اتوماسیون مدار">
    <header className="ab-header">
      <span className="ab-header-icon"><MousePointerClick size={21}/></span>
      <div><h2>دکمه‌های اتوماسیون</h2><p>{project?.name||'مدیریت دکمه‌های کارت و برد'}</p></div>
      {isModal&&onClose&&<button type="button" className="ab-icon-button ab-close" aria-label="بستن دکمه‌های اتوماسیون" disabled={busy||!!runningId} onClick={onClose}><X size={20}/></button>}
    </header>
    <div className="ab-body">
      {view==='list'?<>
        <div className="ab-tabs" role="group" aria-label="نوع دکمه">
          <button type="button" className={scope==='card'?'selected':''} aria-pressed={scope==='card'} onClick={()=>{setScope('card');setError('');setNotice('');}}><MousePointerClick size={16}/>دکمه‌های کارت</button>
          <button type="button" className={scope==='board'?'selected':''} aria-pressed={scope==='board'} onClick={()=>{setScope('board');setError('');setNotice('');}}><LayoutDashboard size={16}/>دکمه‌های برد</button>
        </div>
        <div className="ab-list-heading"><div><h3>دکمه‌های {SCOPE_NAMES[scope]}</h3><p>با یک کلیک، عمل‌های تعریف‌شده را اجرا کنید.</p></div>
          <div className="ab-list-tools"><button type="button" className="ab-icon-button" aria-label="تازه‌سازی دکمه‌ها" disabled={busy||loading||!listSupported} onClick={async()=>{setError('');setNotice('');setLoading(true);try{await reload();}catch(e){setError(errorText(e));}finally{setLoading(false);}}}><RefreshCw size={17}/></button>
            {canManage&&<button type="button" className="ab-primary" disabled={!canCreate||busy} onClick={startNew}><Plus size={16}/> ساخت دکمه</button>}</div>
        </div>
        {!cardId&&canRun&&<label className="ab-card-target">کارت مقصد اجرای دکمه
          <select value={selectedCardId} onChange={e=>{setSelectedCardId(e.target.value);setError('');}} aria-label="کارت مقصد اجرای دکمه">
            <option value="">انتخاب کارت</option>
            {availableCards.map(item=><option key={item.id} value={item.id}>{item.title||item.name||item.id}</option>)}
          </select>
          <small>{availableCards.length?'هر بار تنها روی کارت انتخاب‌شده اجرا می‌شود.':'برای اجرای دکمه، کارت مقصد باید از نمای برد یا کارت در اختیار پنل قرار گیرد.'}</small>
        </label>}
        {!listSupported&&<p className="ab-unsupported"><ShieldAlert size={18}/> میزبان این قابلیت را ارائه نمی‌کند؛ برای استفاده، نسخهٔ دارای API دکمه‌ها لازم است.</p>}
        {loading?<p className="ab-empty"><LoaderCircle size={19} className="ab-spinning"/>در حال دریافت دکمه‌ها…</p>:<div className="ab-button-list">
          {filtered.map(button=>{
            const Icon=iconFor(button.icon);
            const blocked=runBlockReason(button);
            return <article className="ab-list-row" key={button.id}>
              <span className="ab-list-symbol"><Icon size={19}/></span>
              <div className="ab-list-copy"><strong>{button.title}</strong><small>{button.actions?.length||0} عمل · {button.enabled===false?'غیرفعال':'فعال'}{button.scope==='card'&&button.closeAfterAction?' · بستن کارت پس از اجرا':''}</small></div>
              {canRun&&<button type="button" className="ab-quiet" disabled={!!runningId||busy||!!blocked} title={blocked||'اجرای دکمه'} aria-label={'اجرای '+button.title} onClick={()=>run(button)}><Play size={15}/> اجرا</button>}
              {canManage&&<><button type="button" className="ab-icon-button" aria-label={'ویرایش '+button.title} disabled={busy||!!runningId||!saveSupported} onClick={()=>startEdit(button)}><PenLine size={17}/></button>
                <button type="button" className="ab-icon-button ab-delete" aria-label={'حذف '+button.title} disabled={busy||!!runningId||!deleteSupported} onClick={()=>remove(button)}><Trash2 size={17}/></button></>}
              {canRun&&blocked&&<small className="ab-execution-hint">{blocked}</small>}
            </article>;
          })}
          {!filtered.length&&<div className="ab-empty"><MousePointerClick size={29}/><strong>هنوز دکمه‌ای برای {SCOPE_NAMES[scope]} وجود ندارد.</strong><span>نام و نماد را انتخاب کنید، سپس عمل‌ها را اضافه کنید.</span></div>}
        </div>}
      </>:<form className="ab-form" noValidate onSubmit={save}>
        <div className="ab-form-heading"><div><h3>{draft.id?'ویرایش دکمه':'ساخت دکمه جدید'}</h3><p>نام و نماد دکمه را مشخص کنید و عمل‌ها را به ترتیب اضافه کنید.</p></div><span className="ab-scope-pill">{draft.scope==='card'?<MousePointerClick size={16}/>:<LayoutDashboard size={16}/>}دکمه {SCOPE_NAMES[draft.scope]}</span></div>
        <div className="ab-identity">
          <label className="ab-field ab-title-field">نام دکمه
            <input ref={titleRef} required type="text" maxLength={80} value={draft.title} disabled={busy} onChange={e=>changeDraft({title:e.target.value})} placeholder="مثلاً اعلان به مسئول کارت"/>
          </label>
          <div className="ab-icon-field"><span className="ab-field-label">نماد دکمه</span>
            <button type="button" className="ab-icon-picker-trigger" aria-label="انتخاب نماد دکمه" aria-expanded={iconPicker} disabled={busy} onClick={()=>setIconPicker(open=>!open)}>{pickedIcon}<ChevronDown size={17}/></button>
          </div>
        </div>
        {iconPicker&&<div className="ab-icon-popover" aria-label="انتخاب نماد">
          <label className="ab-icon-search"><Search size={16}/><input type="search" value={iconQuery} onChange={e=>setIconQuery(e.target.value)} placeholder="جست‌وجوی نماد" aria-label="جست‌وجوی نماد"/></label>
          <div className="ab-icon-grid" role="group" aria-label="نمادهای موجود">{options.map(item=><button type="button" key={item.id} title={item.name} aria-label={'نماد '+item.name} aria-pressed={draft.icon===item.id} className={draft.icon===item.id?'selected':''} onClick={()=>{changeDraft({icon:item.id});setIconPicker(false);setIconQuery('');}}><item.Icon size={21}/></button>)}</div>
          {!options.length&&<p className="ab-help">نمادی با این نام پیدا نشد.</p>}
        </div>}
        <label className="ab-checkbox"><input type="checkbox" disabled={busy} checked={draft.enabled!==false} onChange={e=>changeDraft({enabled:e.target.checked})}/><span><strong>دکمه فعال باشد</strong><small>دکمهٔ غیرفعال اجرا نمی‌شود.</small></span></label>
        {draft.scope==='card'&&<label className="ab-checkbox"><input type="checkbox" disabled={busy} checked={!!draft.closeAfterAction} onChange={e=>changeDraft({closeAfterAction:e.target.checked})}/><span><strong>پس از اجرای موفق، کارت بسته شود</strong><small>در نمای کارت و پس از تأیید موفقیت میزبان اجرا می‌شود.</small></span></label>}
        <section className="ab-actions" aria-label="عمل‌های دکمه"><div className="ab-actions-heading"><h4>عمل‌ها <span>{draft.actions.length}</span></h4><p>ترتیب نمایش، ترتیب اجرای درخواست‌ها به میزبان است.</p></div>
          {draft.actions.map((action,index)=><ActionEditor key={index} action={action} index={index} members={validMembers} disabled={busy}
            onChange={newAction=>changeAction(index,newAction)} onRemove={()=>removeAction(index)}/>)}
          {!draft.actions.length&&<div className="ab-action-empty"><Info size={17}/>هنوز عملی اضافه نشده است.</div>}
          <button type="button" className="ab-add-action" disabled={busy||draft.actions.length>=5} aria-expanded={actionPicker} onClick={()=>setActionPicker(value=>!value)}><Plus size={17}/> افزودن عمل <ChevronDown size={15}/></button>
          {actionPicker&&<div className="ab-action-options" role="group" aria-label="نوع عمل جدید">
            <button type="button" onClick={()=>addAction('notify')} disabled={busy}><Bell size={20}/><span><strong>اعلان به عضو</strong><small>پیام برای یک عضو انتخاب‌شده</small></span></button>
            <button type="button" onClick={()=>addAction('comment')} disabled={busy}><MessageSquareText size={20}/><span><strong>ثبت نظر</strong><small>ثبت نظر روی کارت مشخص</small></span></button>
          </div>}
          {draft.scope==='board'&&draft.actions.some(a=>a.type==='comment')&&<p className="ab-help"><Info size={16}/> اجرای ثبت نظر از برد نیازمند انتخاب کارت مقصد است. اجرای گروهی پشتیبانی نمی‌شود.</p>}
        </section>
        <footer className="ab-form-footer"><button type="button" className="ab-secondary" disabled={busy} onClick={()=>{setView('list');setError('');setActionPicker(false);}}>انصراف</button>
          <button type="submit" className="ab-primary" disabled={busy||!saveSupported}>{busy?<LoaderCircle size={17} className="ab-spinning"/>:<Save size={17}/>} {busy?'در حال ذخیره…':'ذخیره دکمه'}</button></footer>
      </form>}
      {notice&&<p className="ab-notice" role="status"><Check size={17}/>{notice}</p>}
      {error&&<p className="ab-error" role="alert"><ShieldAlert size={17}/>{error}</p>}
      <p className="ab-host-note"><Info size={15}/>دکمه‌ها با مجوز میزبان اجرا می‌شوند. نگهداری فعلی دکمه‌ها در میزبان مستقل است و پوشش پشتیبان یکپارچه هنوز تأیید نشده است.</p>
    </div>
  </section>;
  if(!isModal)return workspace;
  return <div className="ab-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&onClose&&!busy&&!runningId)onClose();}}>{workspace}</div>;
}

/** Compact entry point for cards and board toolbars. Actual execution lives in the panel. */
export function AutomationButtonsLauncher({onClick,scope='card',disabled=false}){
  const isBoard=scope==='board';
  return <button type="button" className="ab-launcher" disabled={disabled} onClick={onClick}>
    {isBoard?<LayoutDashboard size={17}/>:<MousePointerClick size={17}/>}
    {isBoard?'دکمه‌های برد':'دکمه‌های کارت'}
  </button>;
}

/** Render stored buttons in a card editor or board toolbar, without an authoring modal. */
export function AutomationButtonStrip({api,projectId,boardId,scope='card',cardId,onRan,onCloseCard,canRun=true}){
  const [buttons,setButtons]=useState([]);
  const [loading,setLoading]=useState(true);
  const [running,setRunning]=useState('');
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  useEffect(()=>{
    let current=true;
    setError('');setNotice('');setButtons([]);setLoading(true);
    if(!projectId||!boardId||typeof api?.automationButtonsList!=='function'){
      setError('دکمه‌های اتوماسیون در این میزبان یا برد در دسترس نیستند.');
      setLoading(false);return;
    }
    api.automationButtonsList({projectId,boardId}).then(items=>{
      if(!current)return;
      if(!Array.isArray(items))throw Error('پاسخ میزبان برای دکمه‌ها معتبر نیست.');
      setButtons(items.filter(button=>button.scope===scope&&button.enabled!==false));
    }).catch(e=>{if(current)setError(errorText(e));})
      .finally(()=>{if(current)setLoading(false);});
    return()=>{current=false;};
  },[api,projectId,boardId,scope]);
  async function run(button){
    if(!canRun)return;
    if(!cardId){setError('برای اجرا، کارت مقصد را انتخاب کنید.');return;}
    if(typeof api?.automationButtonRun!=='function'){
      setError('اجرای دکمه در میزبان فعلی پشتیبانی نمی‌شود.');return;
    }
    setRunning(button.id);setError('');setNotice('');
    try{
      const result=await api.automationButtonRun({buttonId:button.id,cardId});
      if(result?.ok===false||result?.error)throw Error(result.error||'اجرای دکمه ناموفق بود.');
      if(result?.buttonId!==button.id||result?.cardId!==cardId)throw Error('میزبان اجرای دکمه روی کارت انتخاب‌شده را تأیید نکرد.');
      setNotice('دکمه «'+button.title+'» اجرا شد.');
      onRan?.(button,result);
      if(scope==='card'&&button.closeAfterAction===true)onCloseCard?.();
    }catch(e){setError(errorText(e));}
    finally{setRunning('');}
  }
  return <div className="ab-strip" dir="rtl" role="group" aria-label={'دکمه‌های اتوماسیون '+SCOPE_NAMES[scope]}>
    {!loading&&buttons.map(button=>{
      const Icon=iconFor(button.icon);
      return <button type="button" key={button.id} className="ab-strip-button" disabled={!canRun||!!running||!cardId||typeof api?.automationButtonRun!=='function'}
        title={!cardId?'کارت مقصد مشخص نشده است':button.title} onClick={()=>run(button)}>
        {running===button.id?<LoaderCircle size={15} className="ab-spinning"/>:<Icon size={15}/>} {button.title}
      </button>;
    })}
    {!loading&&!cardId&&buttons.length>0&&<span className="ab-strip-error">برای اجرا باید کارت مقصد انتخاب شود.</span>}
    {notice&&<span className="ab-strip-status" role="status">{notice}</span>}
    {error&&<span className="ab-strip-error" role="alert">{error}</span>}
  </div>;
}
