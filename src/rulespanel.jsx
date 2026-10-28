import React,{useCallback,useEffect,useRef,useState} from 'react';
import {
  Zap,Plus,Trash2,RefreshCw,X,ChevronLeft,ChevronRight,Check,
  CalendarClock,Clock3,MousePointerClick,LayoutDashboard,GitBranch,
  Bell,MessageSquareText,ArrowLeftRight,Tags,CalendarDays,
  ListChecks,FileText,SlidersHorizontal,Info,Play,ShieldCheck,
} from 'lucide-react';
import {TRIGGER_GROUPS,TRIGGER_INFO,ACTION_INFO,buildAutomationRule,describeRule} from './automation_wizard_logic.js';
import './rulespanel.css';

const eventId=()=>('rule-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
const nav=[
  {id:'rules',label:'قوانین',icon:GitBranch},
  {id:'scheduled',label:'زمان‌بندی‌شده',icon:Clock3},
  {id:'due',label:'موعد کارت',icon:CalendarClock},
  {id:'card-buttons',label:'دکمه‌های کارت',icon:MousePointerClick},
  {id:'board-buttons',label:'دکمه‌های برد',icon:LayoutDashboard},
];
const groupIcons={move:ArrowLeftRight,changes:Tags,dates:CalendarDays,checklists:ListChecks,content:FileText,fields:SlidersHorizontal};
const dueTabs=[
  {id:'basic',label:'Basic',subtitle:'پایه'},
  {id:'dates',label:'Dates',subtitle:'تاریخ‌ها'},
  {id:'checklist',label:'Checklist',subtitle:'چک‌لیست'},
  {id:'content',label:'Content',subtitle:'محتوا'},
  {id:'fields',label:'Fields',subtitle:'فیلدها'},
];
const missing={
  scheduled:{title:'زمان‌بندی‌شده',description:'قانون‌های تکراری روزانه، هفتگی و ماهانه هنوز امکان ساخت و ذخیره در میزبان مدار ندارند.',examples:['هر روز در ساعت مشخص','هر هفته در روزهای انتخابی','اول هر ماه']},
  'card-buttons':{title:'دکمه‌های کارت',description:'اجرای عمل با دکمه اختصاصی روی کارت هنوز در موتور اتومیشن پشتیبانی نمی‌شود.',examples:['ایجاد دکمه روی کارت','اجرای دستور با یک کلیک']},
  'board-buttons':{title:'دکمه‌های برد',description:'دکمه‌های خودکار برد و اجرای گروهی روی کارت‌ها هنوز پشتیبانی نمی‌شوند.',examples:['دکمه سراسری روی برد','اجرای عمل روی چند کارت']},
};

function WizardSteps({step}){
  return <ol className="rule-steps" aria-label="مراحل ساخت قانون">
    {['انتخاب رویداد','انتخاب عمل','مرور و ذخیره'].map((label,index)=><li key={label} className={step===index+1?'active':step>index+1?'done':''} aria-current={step===index+1?'step':undefined}>
      <span className="rule-step-number">{step>index+1?<Check size={14}/>:index+1}</span><span>{label}</span>
    </li>)}
  </ol>;
}

export function RulesPanel({api,project,users=[],listOptions=[],priorityOptions=[],onManageButtons,onClose,initialListId='',initialTrigger='card_moved'}){
  const [rules,setRules]=useState([]);
  const [loading,setLoading]=useState(true);
  const [section,setSection]=useState('rules');
  const [step,setStep]=useState(0);
  const [category,setCategory]=useState('move');
  const [trigger,setTrigger]=useState('card_moved');
  const [actionType,setActionType]=useState('notify');
  const [recipient,setRecipient]=useState('');
  const [message,setMessage]=useState('');
  const [limitToList,setLimitToList]=useState(Boolean(initialListId));
  const [dueDay,setDueDay]=useState('');
  const [dueListId,setDueListId]=useState('');
  const [duePriority,setDuePriority]=useState('');
  const [dueAdvancedOpen,setDueAdvancedOpen]=useState(false);
  const [dueTab,setDueTab]=useState('basic');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const closeRef=useRef(null);
  const dialogRef=useRef(null);
  const dueAdvancedRef=useRef(null);
  const members=users.filter(u=>u&&/^[A-Za-z0-9][A-Za-z0-9._-]{2,39}$/.test(u.username||''));

  const load=useCallback(async()=>{
    const items=await api.collabRead('rules',project.id);
    if(!Array.isArray(items))throw Error('پاسخ فهرست قوانین معتبر نیست.');
    setRules(items);
  },[api,project.id]);

  useEffect(()=>{
    let active=true;
    setLoading(true);setError('');
    api.collabRead('rules',project.id)
      .then(items=>{if(!active)return;if(!Array.isArray(items))throw Error('پاسخ فهرست قوانین معتبر نیست.');setRules(items);})
      .catch(e=>{if(active){setRules([]);setError(e?.message||String(e));}})
      .finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[api,project.id]);

  useEffect(()=>{closeRef.current?.focus();},[]);

  useEffect(()=>{
    const onKeyDown=e=>{
      if(e.key==='Escape'){e.stopPropagation();if(dueAdvancedOpen)setDueAdvancedOpen(false);else onClose();return;}
      if(e.key!=='Tab'||!dialogRef.current)return;
      const focusable=Array.from(dialogRef.current.querySelectorAll(
        'button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[href],[tabindex]:not([tabindex="-1"])'
      )).filter(element=>element.getClientRects().length>0);
      if(!focusable.length)return;
      const first=focusable[0],last=focusable[focusable.length-1];
      if(e.shiftKey&&(document.activeElement===first||!dialogRef.current.contains(document.activeElement))){
        e.preventDefault();last.focus();
      }else if(!e.shiftKey&&(document.activeElement===last||!dialogRef.current.contains(document.activeElement))){
        e.preventDefault();first.focus();
      }
    };
    window.addEventListener('keydown',onKeyDown);
    return()=>window.removeEventListener('keydown',onKeyDown);
  },[onClose,dueAdvancedOpen]);

  useEffect(()=>{
    if(!dueAdvancedOpen)return;
    const onPointerDown=e=>{
      if(dueAdvancedRef.current&&!dueAdvancedRef.current.contains(e.target))setDueAdvancedOpen(false);
    };
    document.addEventListener('pointerdown',onPointerDown);
    return()=>document.removeEventListener('pointerdown',onPointerDown);
  },[dueAdvancedOpen]);

  function chooseSection(next){
    if((next==='card-buttons'||next==='board-buttons')&&typeof onManageButtons==='function'){
      onManageButtons(next==='card-buttons'?'card':'board');return;
    }
    setSection(next);setStep(0);setDueAdvancedOpen(false);setError('');setNotice('');
  }
  function startWizard(from=section){
    const next=from==='due'?'due':'rules';
    const selected=next==='due'?'due_soon':Object.hasOwn(TRIGGER_INFO,initialTrigger)?initialTrigger:'card_moved';
    const currentGroup=TRIGGER_GROUPS.find(g=>g.triggers.includes(selected));
    setSection(next);setStep(1);setCategory(currentGroup?.id||'move');setTrigger(selected);
    setActionType('notify');setRecipient('');setMessage('');
    setLimitToList(Boolean(initialListId)&&['card_moved','card_created'].includes(selected));
    setDueDay('');setDueListId('');setDuePriority('');setDueAdvancedOpen(false);setDueTab('basic');setError('');setNotice('');
  }
  function chooseGroup(group){
    setCategory(group.id);
    if(group.triggers.length)chooseTrigger(group.triggers[0]);
  }
  function chooseTrigger(selected){
    setTrigger(selected);setError('');
    if(!['card_moved','card_created'].includes(selected))setLimitToList(false);
    if(selected!=='due_soon'){
      setDueDay('');setDueListId('');setDuePriority('');setDueAdvancedOpen(false);setDueTab('basic');
    }
  }
  function preview(){
    return buildAutomationRule({id:'rule-preview',projectId:project.id,trigger,
      actionType,recipient,message,limitToList,listId:initialListId,dueDay,dueListId,duePriority});
  }
  function nextStep(){
    setError('');
    if(step===1){
      if(!TRIGGER_GROUPS.find(g=>g.id===category)?.triggers.includes(trigger)){
        setError('یکی از رویدادهای پشتیبانی‌شده را انتخاب کنید.');return;
      }
      setDueAdvancedOpen(false);setStep(2);return;
    }
    try{preview();setStep(3);}catch(e){setError(e.message);}
  }
  async function save(){
    let rule;
    try{rule=buildAutomationRule({id:eventId(),projectId:project.id,trigger,
      actionType,recipient,message,limitToList,listId:initialListId,dueDay,dueListId,duePriority});}
    catch(e){setError(e.message);return;}
    setBusy(true);setError('');setNotice('');
    try{
      await api.collabCommand({type:'rule.upsert',eventId:eventId(),rule});
      setStep(0);setNotice('قانون در پروژه ثبت شد.');
      try{await load();}catch(e){setError('قانون ثبت شد اما تازه‌سازی فهرست ناموفق بود: '+(e?.message||String(e)));}
    }catch(e){setError(e?.message||String(e));}
    finally{setBusy(false);}
  }
  async function removeRule(rule){
    if(!window.confirm('این قانون حذف شود؟'))return;
    setBusy(true);setError('');setNotice('');
    try{
      await api.collabCommand({type:'rule.delete',eventId:eventId(),ruleId:rule.id});
      setRules(items=>items.filter(item=>item.id!==rule.id));
      setNotice('قانون حذف شد.');
      try{await load();}catch(e){setError('قانون حذف شد اما تازه‌سازی فهرست ناموفق بود: '+(e?.message||String(e)));}
    }catch(e){setError(e?.message||String(e));}
    finally{setBusy(false);}
  }
  async function runDueNow(){
    setBusy(true);setError('');setNotice('');
    try{
      const result=await api.runDueScheduler();
      setNotice('بررسی موعدها انجام شد: '+result.events+' رویداد بررسی و '+result.new+' مورد اعمال شد.');
    }catch(e){setError(e?.message||String(e));}
    finally{setBusy(false);}
  }
  const visibleRules=section==='due'?rules.filter(r=>r.trigger==='due_soon'):rules;
  const currentGroup=TRIGGER_GROUPS.find(g=>g.id===category);
  const listConditionPossible=Boolean(initialListId)&&['card_moved','card_created'].includes(trigger);
  const currentInfo=TRIGGER_INFO[trigger];
  const selectedMember=members.find(u=>u.username===recipient);
  const validOptions=source=>Array.isArray(source)?source.filter(option=>option&&typeof option.id==='string'&&option.id.length>0&&option.id.length<=100):[];
  const dueLists=validOptions(listOptions);
  const duePriorities=validOptions(priorityOptions);
  const displayOption=(options,id)=>options.find(option=>option.id===id)?.label||options.find(option=>option.id===id)?.name||id;
  const dueFilterCount=Number(dueDay!=='')+Number(Boolean(dueListId))+Number(Boolean(duePriority));
  const previewRule=step===3?(()=>{try{return preview();}catch{return null;}})():null;
  const summary=previewRule?describeRule(previewRule):null;

  return <div className="rule-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}>
    <section className="rule-dialog" role="dialog" aria-modal="true" aria-label={'اتوماسیون پروژه '+project.name} dir="rtl" ref={dialogRef}>
      <header className="rule-head">
        <div className="rule-title"><span className="rule-title-icon"><Zap size={20}/></span><div><strong>اتوماسیون مدار</strong><small>{project.name}</small></div></div>
        <button type="button" className="rule-icon-button" aria-label="بستن پنجره اتوماسیون" onClick={onClose} ref={closeRef}><X size={19}/></button>
      </header>
      <div className="rule-layout">
        <nav className="rule-sidebar" aria-label="بخش‌های اتوماسیون">
          <span className="rule-sidebar-label">اتوماسیون</span>
          {nav.map(item=><button type="button" key={item.id} className={'rule-nav-button'+(section===item.id?' active':'')} aria-current={section===item.id?'page':undefined} onClick={()=>chooseSection(item.id)}>
            <item.icon size={18}/><span>{item.label}</span>{section===item.id&&<ChevronLeft size={16} className="rule-nav-chevron"/>}
          </button>)}
          <div className="rule-sidebar-foot"><ShieldCheck size={17}/><span>اجرای قوانین با مجوز میزبان</span></div>
        </nav>
        <div className="rule-workspace">
          {step>0?<div className="rule-wizard">
            <div className="rule-section-title"><div><span className="rule-kicker">ساخت قانون جدید</span><h2>{step===1?'وقتی این اتفاق افتاد…':step===2?'این کار را انجام بده…':'قانون را مرور کن'}</h2><p>{step===1?'رویدادی را انتخاب کن که شروع‌کننده قانون باشد.':step===2?'قانون بعد از رویداد انتخاب‌شده چه کاری انجام دهد؟':'پیش از ذخیره، رویداد و عمل را بررسی کن.'}</p></div><button type="button" className="rule-text-button" onClick={()=>{setStep(0);setError('');}} disabled={busy}>انصراف</button></div>
            <WizardSteps step={step}/>
            {step===1&&<>
              {section!=='due'&&<div className="rule-group-grid" role="group" aria-label="دسته رویدادها">{TRIGGER_GROUPS.map(group=>{
                const Icon=groupIcons[group.id];return <button type="button" key={group.id} className={'rule-group'+(category===group.id?' active':'')+(group.triggers.length?'':' unavailable')} aria-pressed={category===group.id} onClick={()=>chooseGroup(group)}>
                  <Icon size={19}/><strong>{group.label}</strong>{!group.triggers.length&&<small>به‌زودی</small>}
                </button>;})}</div>}
              <div className="rule-options" role="group" aria-label="رویدادهای موجود">
                <h3>{section==='due'?'رویداد موعد':currentGroup?.label}</h3>
                {(section==='due'?['due_soon']:currentGroup?.triggers||[]).map(key=><button type="button" key={key} className={'rule-option'+(trigger===key?' selected':'')} onClick={()=>chooseTrigger(key)} aria-pressed={trigger===key}>
                  <span className="rule-radio" aria-hidden="true"/><span><strong>{TRIGGER_INFO[key].label}</strong><small>{TRIGGER_INFO[key].description}</small></span>
                </button>)}
                {section!=='due'&&!currentGroup?.triggers.length&&<p className="rule-unsupported"><Info size={17}/>{currentGroup?.hint}</p>}
              </div>
              {listConditionPossible&&<label className="rule-condition"><input type="checkbox" checked={limitToList} onChange={e=>setLimitToList(e.target.checked)}/> <span><strong>فقط برای فهرست انتخاب‌شده</strong><small>قانون فقط وقتی اجرا می‌شود که مقصد انتقال یا محل ساخت کارت همین فهرست باشد.</small></span></label>}
              {trigger==='due_soon'&&<div className="rule-due-advanced" ref={dueAdvancedRef}>
                <div className="rule-due-toolbar">
                  <div><strong>شرط‌های رویداد موعد</strong><small>در بازهٔ امروز تا هفت روز آینده؛ شرط‌های اضافه را در Advanced انتخاب کنید.</small></div>
                  <button type="button" className={'rule-advanced-trigger'+(dueAdvancedOpen?' active':'')} aria-expanded={dueAdvancedOpen} aria-controls={dueAdvancedOpen?'rule-due-advanced-popover':undefined} onClick={()=>{setDueAdvancedOpen(open=>!open);setDueTab('basic');}}>
                    <SlidersHorizontal size={16}/>Advanced{dueFilterCount>0&&<span className="rule-advanced-count">{dueFilterCount}</span>}
                  </button>
                </div>
                {dueFilterCount>0&&<div className="rule-filter-chips" aria-label="شرط‌های فعال">
                  {dueDay!==''&&<span>{Number(dueDay)===0?'روز موعد':dueDay+' روز مانده'}<button type="button" aria-label="حذف شرط روز موعد" onClick={()=>setDueDay('')}><X size={13}/></button></span>}
                  {dueListId&&<span>فهرست: {displayOption(dueLists,dueListId)}<button type="button" aria-label="حذف شرط فهرست" onClick={()=>setDueListId('')}><X size={13}/></button></span>}
                  {duePriority&&<span>اولویت: {displayOption(duePriorities,duePriority)}<button type="button" aria-label="حذف شرط اولویت" onClick={()=>setDuePriority('')}><X size={13}/></button></span>}
                </div>}
                {dueAdvancedOpen&&<div id="rule-due-advanced-popover" className="rule-advanced-popover" role="region" aria-label="شرط‌های پیشرفته موعد">
                  <div className="rule-advanced-head"><div><strong>Advanced conditions</strong><small>شرط‌ها تنها روی اطلاعات منتشرشده توسط موتور موعد اعمال می‌شوند.</small></div><button type="button" className="rule-icon-button" aria-label="بستن شرط‌های پیشرفته" onClick={()=>setDueAdvancedOpen(false)}><X size={17}/></button></div>
                  <div className="rule-advanced-tabs" role="tablist" aria-label="دسته‌های شرط پیشرفته">
                    {dueTabs.map(tab=><button key={tab.id} id={'rule-tab-'+tab.id} type="button" role="tab" aria-selected={dueTab===tab.id} aria-controls="rule-due-tabpanel" className={dueTab===tab.id?'active':''} onClick={()=>setDueTab(tab.id)}><strong>{tab.label}</strong><small>{tab.subtitle}</small></button>)}
                  </div>
                  <div className="rule-advanced-body" id="rule-due-tabpanel" role="tabpanel" aria-labelledby={'rule-tab-'+dueTab}>
                    {dueTab==='basic'&&<>
                      <h3>فهرست کارت</h3><p>فقط کارت‌هایی که هنگام بررسی موعد در فهرست انتخاب‌شده هستند.</p>
                      {dueLists.length?<label className="rule-advanced-field">فهرست موردنظر<select aria-label="فهرست کارت در موعد" value={dueListId} onChange={e=>setDueListId(e.target.value)}><option value="">تمام فهرست‌ها</option>{dueLists.map(option=><option key={option.id} value={option.id}>{option.label||option.name||option.id}</option>)}</select></label>
                        :<p className="rule-advanced-unavailable"><Info size={17}/>فهرست‌های برد برای انتخاب در دسترس نیستند.</p>}
                      <p className="rule-advanced-unavailable"><Info size={17}/>فیلتر عضو و برچسب برای رویداد موعد هنوز پشتیبانی نمی‌شود.</p>
                    </>}
                    {dueTab==='dates'&&<>
                      <h3>فاصله تا موعد</h3><p>یک روز مشخص را انتخاب کنید یا قانون را برای تمام بازهٔ صفر تا هفت روز نگه دارید.</p>
                      <label className="rule-advanced-field">روز مانده به موعد<select aria-label="روز مانده به موعد" value={dueDay} onChange={e=>setDueDay(e.target.value)}><option value="">تمام بازهٔ ۰ تا ۷ روز</option>{Array.from({length:8},(_,i)=><option key={i} value={i}>{i===0?'روز موعد':i+' روز مانده'}</option>)}</select></label>
                    </>}
                    {dueTab==='fields'&&<>
                      <h3>اولویت کارت</h3><p>مقدار اولویت فعلی کارت هنگام بررسی موعد با شرط مقایسه می‌شود.</p>
                      {duePriorities.length?<label className="rule-advanced-field">اولویت موردنظر<select aria-label="اولویت کارت در موعد" value={duePriority} onChange={e=>setDuePriority(e.target.value)}><option value="">تمام اولویت‌ها</option>{duePriorities.map(option=><option key={option.id} value={option.id}>{option.label||option.name||option.id}</option>)}</select></label>
                        :<p className="rule-advanced-unavailable"><Info size={17}/>اولویت‌های پروژه برای انتخاب در دسترس نیستند.</p>}
                      <p className="rule-advanced-unavailable"><Info size={17}/>فیلترهای سفارشی دیگر در رویداد موعد دادهٔ قابل اتکا ندارند.</p>
                    </>}
                    {dueTab==='checklist'&&<p className="rule-advanced-unavailable"><Info size={18}/>فیلتر چک‌لیست در رویداد موعد پشتیبانی نمی‌شود؛ موتور موعد شناسه یا وضعیت چک‌لیست را ارسال نمی‌کند.</p>}
                    {dueTab==='content'&&<p className="rule-advanced-unavailable"><Info size={18}/>فیلتر عنوان، متن، پیوست و محتوای کارت برای رویداد موعد در دسترس نیست.</p>}
                  </div>
                  <div className="rule-advanced-footer"><small>{dueFilterCount?dueFilterCount+' شرط فعال':'بدون شرط اضافه'}</small><button type="button" className="rule-primary-button" onClick={()=>setDueAdvancedOpen(false)}>انجام شد</button></div>
                </div>}
              </div>}
            </>}
            {step===2&&<>
              <div className="rule-choice-grid" role="group" aria-label="نوع عمل">
                {Object.entries(ACTION_INFO).map(([key,info])=>{
                  const Icon=key==='notify'?Bell:MessageSquareText;return <button type="button" key={key} aria-pressed={actionType===key} className={'rule-action'+(actionType===key?' selected':'')} onClick={()=>{setActionType(key);setError('');}}>
                    <Icon size={20}/><strong>{info.label}</strong><small>{info.description}</small>
                  </button>;})}
              </div>
              <div className="rule-fields">
                {actionType==='notify'&&<label>اعلان برای کدام عضو؟
                  <select value={recipient} onChange={e=>{setRecipient(e.target.value);setError('');}}>
                    <option value="">انتخاب عضو</option>{members.map(user=><option key={user.username} value={user.username}>{user.displayName||user.username}</option>)}
                  </select>{!members.length&&<small>عضو معتبری در فهرست پروژه موجود نیست. می‌توانید «ثبت نظر خودکار» را انتخاب کنید.</small>}
                </label>}
                <label>متن {actionType==='notify'?'اعلان':'نظر'}
                  <textarea rows={4} value={message} maxLength={actionType==='notify'?240:4000} onChange={e=>{setMessage(e.target.value);setError('');}} placeholder={actionType==='notify'?'متن اعلان را بنویسید':'متن نظری که روی کارت ثبت می‌شود'}/>
                  <small className="rule-count" dir="ltr">{message.length} / {actionType==='notify'?240:4000}</small>
                </label>
              </div>
            </>}
            {step===3&&summary&&<div className="rule-review">
              <div className="rule-review-row"><span className="rule-review-symbol"><Zap size={18}/></span><div><small>وقتی</small><strong>{summary.trigger}</strong>{summary.destination&&<span>{trigger==='due_soon'?'فهرست: '+displayOption(dueLists,summary.destination):'فقط فهرست انتخاب‌شده'}</span>}{summary.dueDay!==undefined&&<span>{summary.dueDay===0?'روز موعد':'دقیقاً '+summary.dueDay+' روز پیش از موعد'}</span>}{summary.duePriority&&<span>اولویت: {displayOption(duePriorities,summary.duePriority)}</span>}</div></div>
              <div className="rule-review-link" aria-hidden="true"/>
              <div className="rule-review-row"><span className="rule-review-symbol"><Check size={18}/></span><div><small>آنگاه</small><strong>{summary.action}</strong>{selectedMember&&actionType==='notify'&&<span>گیرنده: {selectedMember.displayName||selectedMember.username}</span>}<p>{summary.message}</p></div></div>
              <p className="rule-review-note"><ShieldCheck size={17}/>قانون بعد از ذخیره فعال است. برای رویدادهای موجود در پروژه اجرا می‌شود و دسترسی آن در میزبان بررسی خواهد شد.</p>
            </div>}
            {error&&<p role="alert" className="rule-error">{error}</p>}
            <div className="rule-wizard-footer">
              <button type="button" className="rule-outline-button" disabled={busy} onClick={()=>{if(step===1){setStep(0);}else{setStep(step-1);}setError('');}}><ChevronRight size={17}/>{step===1?'بازگشت به قوانین':'مرحله قبل'}</button>
              {step<3?<button type="button" className="rule-primary-button" disabled={busy||step===1&&!(section==='due'||currentGroup?.triggers.includes(trigger))} onClick={nextStep}>ادامه <ChevronLeft size={17}/></button>
                :<button type="button" className="rule-primary-button" disabled={busy||!summary} onClick={save}><Check size={17}/>{busy?'در حال ذخیره…':'ذخیره و فعال‌سازی'}</button>}
            </div>
          </div>:missing[section]?<div className="rule-unavailable-panel"><div className="rule-unavailable-illustration"><Clock3 size={29}/></div><span className="rule-kicker">در حال توسعه</span><h2>{missing[section].title}</h2><p>{missing[section].description}</p><div className="rule-placeholder-items">{missing[section].examples.map(example=><span key={example}><Info size={15}/>{example}</span>)}</div><button type="button" className="rule-outline-button" onClick={()=>chooseSection('rules')}><ChevronRight size={16}/> بازگشت به قوانین</button></div>
          :<div className="rule-overview">
            <div className="rule-section-title"><div><span className="rule-kicker">{section==='due'?'اتوماسیون موعدها':'قوانین خودکار'}</span><h2>{section==='due'?'رویدادهای تاریخ سررسید':'قوانین پروژه'}</h2><p>{section==='due'?'وقتی موعد کارت در فاصلهٔ صفر تا ۷ روز قرار بگیرد، قانون هنگام بررسی موعدها اجرا می‌شود.':'رویداد را مشخص کن، عمل را انتخاب کن و پس از مرور قانون را ذخیره کن.'}</p></div><button type="button" className="rule-primary-button" onClick={()=>startWizard()}><Plus size={17}/>{section==='due'?'قانون موعد جدید':'ساخت قانون'}</button></div>
            <div className="rule-metrics"><div><span>قوانین این بخش</span><strong>{visibleRules.length}</strong></div><div><span>قوانین فعال</span><strong>{visibleRules.filter(r=>r.enabled).length}</strong></div></div>
            {section==='due'&&<div className="rule-due-scheduler"><div><CalendarClock size={19}/><span><strong>بررسی موعدهای امروز</strong><small>اجرای دستی موتور موعدها برای کارت‌های باز</small></span></div><button type="button" className="rule-outline-button" disabled={busy} onClick={runDueNow}><Play size={15}/> اجرای بررسی</button></div>}
            <div className="rule-list"><div className="rule-list-head"><strong>قانون‌های ثبت‌شده</strong><button type="button" className="rule-icon-button" aria-label="تازه‌سازی قوانین" title="تازه‌سازی قوانین" disabled={busy||loading} onClick={()=>{setError('');load().catch(e=>setError(e?.message||String(e)));}}><RefreshCw size={17}/></button></div>
              {loading?<p className="rule-empty">در حال دریافت قوانین…</p>:visibleRules.map(rule=>{
                const info=describeRule(rule);return <div className="rule-list-row" key={rule.id}><div className="rule-list-visual"><Zap size={16}/></div><div className="rule-list-detail"><strong>{info.trigger}</strong><span>{info.action} · {info.message}</span>{info.destination&&<small>{rule.trigger==='due_soon'?'فهرست: '+displayOption(dueLists,info.destination):'محدود به فهرست مقصد'}</small>}{info.dueDay!==undefined&&<small>{info.dueDay} روز مانده تا موعد</small>}{info.duePriority&&<small>اولویت: {displayOption(duePriorities,info.duePriority)}</small>}</div><span className={'rule-status'+(rule.enabled?' enabled':'')}>{rule.enabled?'فعال':'غیرفعال'}</span><button type="button" className="rule-icon-button rule-delete" aria-label={'حذف قانون '+info.trigger} title="حذف قانون" disabled={busy} onClick={()=>removeRule(rule)}><Trash2 size={17}/></button></div>;
              })}
              {!loading&&!visibleRules.length&&<div className="rule-empty"><GitBranch size={24}/><strong>هنوز قانونی ثبت نشده</strong><span>قانون اول را با سه گام ساده بسازید.</span></div>}
            </div>
            {notice&&<p role="status" className="rule-notice">{notice}</p>}
            {error&&<p role="alert" className="rule-error">{error}</p>}
          </div>}
        </div>
      </div>
    </section>
  </div>;
}
