import React,{useEffect,useState} from 'react';
import {Check, Cloud, Download, Layers3, LockKeyhole, Moon, Plus, Settings2, ShieldCheck, Sun, Trash2, Users, Wallet, X, ArrowUp, ArrowDown, RefreshCw, RotateCcw} from 'lucide-react';
import {Avatar, AvatarIconPicker, RoleBadge, DEFAULT_AVATAR_COLOR} from './members.jsx';
import {PrioritySettings} from './priorities.jsx';
import {INTERFACE_FEATURE_TIERS, INTERFACE_MODE_OPTIONS} from './interface_mode.js';
import {deleteSettingsStage} from './stage_delete_safe.js';
import './settings_density.css';

export const DEFAULT_STAGES=[
 {id:'inbox',label:'صندوق ورودی',subtitle:'ایده‌ها و کارهای جدید',color:'#9ca3af'},
 {id:'planned',label:'برنامه‌ریزی',subtitle:'آماده شروع',color:'#6785d8'},
 {id:'active',label:'در حال انجام',subtitle:'در جریان کار',color:'#c89141'},
 {id:'review',label:'در انتظار بررسی',subtitle:'نیاز به تصمیم',color:'#a37be1'},
 {id:'done',label:'تکمیل‌شده',subtitle:'کارهای تمام‌شده',color:'#3ca789'}
];
const toLatin=v=>String(v??'').replace(/[۰-۹]/g,ch=>String(ch.charCodeAt(0)-1776)).replace(/[٠-٩]/g,ch=>String(ch.charCodeAt(0)-1632));
export const parseMoney=s=>Math.max(0,Math.min(1e15,Number(toLatin(s).replace(/[^0-9]/g,''))||0));
export const money=v=>Number(v||0).toLocaleString('en-US',{maximumFractionDigits:0});
export const costTotal=tasks=>tasks.reduce((acc,t)=>acc+(t.cost||0)+t.checklist.reduce((s,c)=>s+(c.cost||0),0),0);
export const cardCostEnabled=(task,project)=>task.costEnabled===null||task.costEnabled===undefined?!!project?.costEnabled:task.costEnabled===true;
export const validLanFingerprint=value=>/^(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{2}(?::[a-fA-F0-9]{2}){31})$/.test(String(value||'').trim());
export const normalizeLanFingerprint=value=>String(value||'').trim().replace(/:/g,'');
export function MoneyField({value,onChange,disabled=false,placeholder='0',label='مبلغ به تومان'}){
 return <div className="money-input"><input dir="ltr" inputMode="numeric" aria-label={label} disabled={disabled} placeholder={placeholder} value={money(value)} onChange={e=>onChange(parseMoney(e.target.value))}/><span>تومان</span></div>;
}
export function FinanceSummary({project,tasks,onChange,canManage=true,compact=false}){
 if(!project?.costEnabled)return null;
 const related=tasks.filter(t=>t.projectId===project.id);
 const cost=costTotal(related.filter(t=>cardCostEnabled(t,project))),price=project.price||0,profit=price-cost;
 return <div className={'finance-summary '+(compact?'compact':'')}>
   <div className="finance-head"><span><Wallet size={18}/> حساب پروژه</span><span>{related.length.toLocaleString('fa-IR')} کار</span></div>
   <div className="finance-grid">
     <div><small>قیمت پروژه</small>{onChange?<MoneyField disabled={!canManage} value={price} label="قیمت پروژه" onChange={onChange}/>:<strong>{money(price)} <em>تومان</em></strong>}</div>
     <div><small>جمع هزینه کارها و مراحل</small><strong>{money(cost)} <em>تومان</em></strong></div>
     <div className={profit<0?'loss':'profit'}><small>{profit>=0?'سود پیش‌بینی‌شده':'زیان پیش‌بینی‌شده'}</small><strong>{profit<0?'−':''}{money(Math.abs(profit))} <em>تومان</em></strong></div>
   </div>
 </div>;
}

export function SettingsPanel({data,onChange,onClose,calendar='jalali',onCalendarChange,canManage=true,priorityUsedIds,boardId=null,onArchiveList,onRestoreList}){
 const [name,setName]=useState('');
 const [editing,setEditing]=useState('');
 const [label,setLabel]=useState('');
 const [subtitle,setSubtitle]=useState('');
 const stages=data.stages||DEFAULT_STAGES;
 const settings=data.settings||{};
 const usedByBoard=id=>!boardId&&data.tasks.some(task=>task.boardId&&task.status===id);
 const updateStage=(id,fields)=>onChange(s=>({...s,stages:s.stages.map(stage=>stage.id===id?{...stage,...fields}:stage)}));
 const addStage=()=>{if(!name.trim()||stages.length>=40)return;const newStage={id:'stage_'+Date.now()+'_'+Math.random().toString(36).slice(2,7),label:name.trim(),subtitle:'مرحله سفارشی',color:'#6386cb'};onChange(s=>({...s,stages:[...s.stages,newStage]}));setName('');};
 const deleteStage=id=>{
   if(!canManage || !stages.some(stage=>stage.id===id&&stage.archived!==true) ||
      stages.filter(stage=>stage.archived!==true).length<=1)return;
   onChange(s=>deleteSettingsStage(s,id,{boardId,canManage}));
   if(editing===id)setEditing('');
 };
 const moveStage=(id,d)=>{const index=stages.findIndex(s=>s.id===id),next=index+d;if(next<0||next>=stages.length)return;const a=[...stages];[a[index],a[next]]=[a[next],a[index]];onChange(s=>({...s,stages:a}));};
 const updateDefault=checked=>onChange(s=>({...s,settings:{...s.settings,costDefault:checked},projects:s.projects.map(p=>({...p,costEnabled:checked}))}));
 const updateTheme=theme=>onChange(s=>({...s,settings:{...s.settings,theme}}));
 return <div className="overlay" onMouseDown={onClose}><section className="dialog settings-modal settings-density" dir="rtl" onMouseDown={e=>e.stopPropagation()} role="dialog" aria-modal="true" aria-label="تنظیمات مدار"><div className="dialog-head"><h2><Settings2 size={18}/> تنظیمات مدار</h2><button className="icon-btn" onClick={onClose} aria-label="بستن"><X size={19}/></button></div>
   <div className="dialog-body settings-content">
     <div className="settings-density__quick-grid" aria-label="تنظیمات پرکاربرد">
     <div className="setting-block"><h3><Moon size={17}/> ظاهر برنامه</h3><p>حالت نمایش در تمام صفحات برنامه اعمال می‌شود.</p><div className="theme-picks"><button className={settings.theme!=='dark'?'selected':''} disabled={!canManage} onClick={()=>updateTheme('light')}><Sun size={19}/> روشن {settings.theme!=='dark'&&<Check size={16}/>}</button><button className={settings.theme==='dark'?'selected':''} disabled={!canManage} onClick={()=>updateTheme('dark')}><Moon size={19}/> تاریک {settings.theme==='dark'&&<Check size={16}/>}</button></div></div>
     <div className="setting-block"><h3><Layers3 size={17}/> تقویم و نمایش تاریخ</h3><p>انتخاب تقویم فقط روی این کامپیوتر ذخیره می‌شود؛ تاریخ واقعی کارها در همه سیستم‌ها یکسان می‌ماند.</p><div className="theme-picks"><button className={calendar==='jalali'?'selected':''} onClick={()=>onCalendarChange('jalali')}>شمسی {calendar==='jalali'&&<Check size={16}/>}</button><button className={calendar==='gregorian'?'selected':''} onClick={()=>onCalendarChange('gregorian')}>میلادی {calendar==='gregorian'&&<Check size={16}/>}</button></div></div>
     <div className="setting-block"><h3><Wallet size={17}/> مدیریت هزینه‌ها</h3><label className="setting-toggle"><input type="checkbox" checked={!!settings.costDefault} disabled={!canManage} onChange={e=>updateDefault(e.target.checked)}/><span><strong>فعال‌کردن فیلد هزینه برای همه پروژه‌ها</strong><small>هم برای پروژه‌های فعلی اعمال می‌شود و هم پیش‌فرض پروژه‌های جدید خواهد بود؛ مبالغ قبلی پاک نمی‌شوند.</small></span></label></div>
     </div>
     <details className="settings-density__disclosure"><summary><span><Layers3 size={17}/> تنظیم اولویت‌های کارت</span><small>نام، رنگ، جلوه و اولویت‌های سفارشی</small></summary>
     <PrioritySettings settings={settings} usedIds={priorityUsedIds||data.tasks.map(t=>t.priority)} canManage={canManage} onChange={priorityDefinitions=>onChange(s=>({...s,settings:{...s.settings,priorityDefinitions}}))}/>
     </details>
     {boardId?<details className="settings-density__disclosure"><summary><span><Layers3 size={17}/> مدیریت بازیابی ستون‌های بایگانی‌شده</span><small>{stages.filter(stage=>stage.archived===true).length.toLocaleString('fa-IR')} ستون بایگانی‌شده</small></summary>
       <div className="setting-block"><p>ویرایش، جابه‌جایی و بایگانی هر ستون از منوی همان ستون روی برد انجام می‌شود.</p>
         {stages.some(stage=>stage.archived===true)?<div className="stage-manager">{stages.filter(stage=>stage.archived===true).map(stage=><div className="stage-manage-row stage-manage-row--archived" key={stage.id} style={{gridTemplateColumns:'12px minmax(0,1fr) max-content'}}>
           <span className="stage-color" style={{background:stage.color}}/>
           <span className="stage-manage-label"><strong>{stage.label}</strong><small>بایگانی‌شده · {stage.subtitle}</small></span>
           {canManage&&<div className="stage-manage-actions"><button type="button" onClick={()=>onRestoreList?.(stage.id)} title="بازیابی ستون بدون تغییر کارت‌ها" aria-label={'بازیابی ستون '+stage.label}><RotateCcw size={16}/></button></div>}
         </div>)}</div>:<p>ستون بایگانی‌شده‌ای برای بازیابی وجود ندارد.</p>}
       </div>
     </details>:<details className="settings-density__disclosure"><summary><span><Layers3 size={17}/> مدیریت ستون‌ها و مراحل برد</span><small>{stages.length.toLocaleString('fa-IR')} مرحله عمومی، ترتیب و رنگ</small></summary>
     <div className="setting-block"><h3><Layers3 size={17}/> مراحل عمومی</h3><p>ترتیب مراحل عمومی با فلش‌ها تغییر می‌کند. مدیریت ستون‌های هر برد از منوی همان ستون انجام می‌شود.</p>
       <div className="stage-manager">{stages.map((stage,i)=><div className="stage-manage-row" key={stage.id}>
         <span className="stage-color" style={{background:stage.color}}/>
         <input className="stage-color-picker" type="color" aria-label={'رنگ ستون '+stage.label} title={'رنگ ستون '+stage.label} value={/^#[0-9a-f]{6}$/i.test(stage.color)?stage.color:'#64748b'} disabled={!canManage} onChange={e=>updateStage(stage.id,{color:e.target.value})}/>
         {editing===stage.id?<div className="stage-edit-fields"><input aria-label="نام ستون" maxLength={100} value={label} onChange={e=>setLabel(e.target.value)}/><input aria-label="توضیح ستون" value={subtitle} onChange={e=>setSubtitle(e.target.value)}/></div>:<span className="stage-manage-label"><strong>{stage.label}</strong><small>{stage.archived===true?'بایگانی‌شده · ':''}{stage.subtitle}</small></span>}
         {canManage&&<div className="stage-manage-actions" role="group" aria-label={'عملیات ستون '+stage.label}>
           {editing===stage.id?<button onClick={()=>{if(label.trim())updateStage(stage.id,{label:label.trim(),subtitle:subtitle.trim()});setEditing('');}} title="ذخیره" aria-label={'ذخیره ستون '+stage.label}><Check size={16}/></button>:<button onClick={()=>{setEditing(stage.id);setLabel(stage.label);setSubtitle(stage.subtitle||'');}} title="ویرایش" aria-label={'ویرایش ستون '+stage.label}>ویرایش</button>}
           <button onClick={()=>moveStage(stage.id,-1)} disabled={i===0} title="انتقال به مرحله قبل" aria-label={'انتقال ستون '+stage.label+' به مرحله قبل'}><ArrowUp size={15}/></button>
           <button onClick={()=>moveStage(stage.id,1)} disabled={i===stages.length-1} title="انتقال به مرحله بعد" aria-label={'انتقال ستون '+stage.label+' به مرحله بعد'}><ArrowDown size={15}/></button>
           <button onClick={()=>{if(window.confirm('این مرحله حذف شود و کارهای قدیمی آن منتقل شوند؟'))deleteStage(stage.id);}} disabled={stages.length===1||stage.archived===true||stages.filter(item=>item.archived!==true).length<=1||usedByBoard(stage.id)} title={usedByBoard(stage.id)?'مرحله در وضعیت کارت‌های بردهای دیگر استفاده شده است':'حذف'} aria-label={'حذف ستون '+stage.label}><Trash2 size={15}/></button>
         </div>}
       </div>)}</div>
       {canManage&&<div className="stage-new"><input value={name} maxLength={100} aria-label="نام ستون جدید" onChange={e=>setName(e.target.value)} onKeyDown={e=>e.key==='Enter'&&addStage()} placeholder="نام ستون جدید..."/><button className="btn primary" disabled={!name.trim()} onClick={addStage}><Plus size={15}/> افزودن ستون</button></div>}
     </div>
     </details>}
     <p className="setting-foot">فونت داخلی برنامه: وزیرمتن · تنظیمات برای داده‌های ذخیره‌شده اعمال می‌شوند.</p>
   </div>
 </section></div>;
}

// A display template controls UI visibility only. The LAN host's admin/editor/viewer
// authorization remains independent and is never inferred from a custom title.
export const LAN_BUILTIN_DISPLAY_ROLES=Object.freeze([
 {id:'superadmin',label:'مدیرکل',displayMode:'finance',isBuiltin:true},
 {id:'senior',label:'مدیر ارشد',displayMode:'operations',isBuiltin:true},
 {id:'middle',label:'مدیر میانی',displayMode:'operations',isBuiltin:true},
 {id:'unit',label:'مدیر واحد',displayMode:'operations',isBuiltin:true},
 {id:'employee',label:'کارمند',displayMode:'basic',isBuiltin:true},
]);
const LAN_BUILTIN_ROLE_IDS=new Set(LAN_BUILTIN_DISPLAY_ROLES.map(item=>item.id));
const LAN_MODE_ORDER={basic:0,operations:1,finance:2};
const LAN_FEATURE_LABELS={
 workspaceSwitch:'انتخاب فضای کاری',projects:'پروژه‌ها',boards:'بردها',cards:'کارت‌ها',
 createTask:'ساخت کار',createProject:'ساخت پروژه',createBoard:'ساخت برد',
 assignees:'اعضای کار',dueDate:'سررسید',reminder:'یادآوری',priority:'اولویت',
 search:'جست‌وجو',quickFilters:'فیلتر سریع',taskTrash:'سطل زباله کارها',
 projectFiles:'فایل‌های پروژه',cardChecklist:'چک‌لیست',cardAttachments:'پیوست کارت',
 boardView:'نمای برد',listView:'نمای فهرست',syncStatus:'وضعیت همگام‌سازی',
 backupRestore:'پشتیبان و بازیابی',networkStatus:'شبکه',settings:'تنظیمات',
 profile:'پروفایل',notifications:'اعلان‌ها',workspaceManagement:'مدیریت فضای کاری',
 boardAdministration:'مدیریت برد',projectAdministration:'مدیریت پروژه',
 advancedFilters:'فیلترهای پیشرفته',activity:'فعالیت‌ها',reporting:'گزارش‌ها',
 planner:'برنامه‌ریز',timeDashboard:'داشبورد زمان',timelineView:'نمای زمان‌بندی',
 taskTime:'زمان کار',cardComments:'نظرهای کارت',customFields:'فیلدهای سفارشی',
 boardFieldEditor:'ویرایش فیلدهای برد',automationRules:'قوانین خودکار',
 trelloImport:'ورود از ترلو',calendarInterop:'اتصال تقویم',
 secureApiKeys:'کلید API',lanUserManagement:'مدیریت کاربران',
 financeHub:'مدیریت مالی',projectFinance:'هزینه پروژه',profitPeek:'سود پروژه',
 taskCostControls:'هزینه کار',checklistCostControls:'هزینه مراحل',
 projectPricing:'قیمت پروژه',aiAgent:'دستیار هوشمند (در صورت فعال‌سازی)',
};
export const lanDefaultDisplayRoleForUser=(user)=>user?.displayRole||
 (user?.role==='admin'?'superadmin':user?.role==='viewer'?'employee':'middle');
export const lanCanAssignDisplayRole=(roles,id,technicalRole)=>
 Array.isArray(roles)&&roles.some(template=>template.id===id)&&
 (id==='superadmin')===(technicalRole==='admin');
const lanRoleLabel=(roles,id)=>roles.find(item=>item.id===id)?.label||
 LAN_BUILTIN_DISPLAY_ROLES.find(item=>item.id===id)?.label||id;
const lanRoleFeatures=mode=>Object.keys(INTERFACE_FEATURE_TIERS).filter(key=>
 LAN_MODE_ORDER[INTERFACE_FEATURE_TIERS[key]]<=LAN_MODE_ORDER[mode]);
export function lanDisplayRolePayload({id,label,displayMode,features,limited}){
 const available=lanRoleFeatures(displayMode);
 return {id,label:label.trim(),displayMode,
   features:limited?available.filter(key=>features.includes(key)):available};
}
export const lanAvailableUserFeatures=(role,mode)=>
 (Array.isArray(role?.features)?role.features:lanRoleFeatures(role?.displayMode||'basic'))
   .filter(key=>Object.prototype.hasOwnProperty.call(INTERFACE_FEATURE_TIERS,key)&&
     LAN_MODE_ORDER[INTERFACE_FEATURE_TIERS[key]]<=LAN_MODE_ORDER[mode]);

export function LanPanel({api,projects,onClose,status,onRefresh,onConnected}){
 const editorRef=React.useRef(null);
 const [view,setView]=useState('connection');
 const [mode,setMode]=useState(status?.mode||'solo');
 const [username,setUsername]=useState('');
 const [password,setPassword]=useState('');
 const [url,setUrl]=useState(status?.url||'http://192.168.1.10:48370');
 const [port,setPort]=useState(String(status?.port||48370));
 const [secureHost,setSecureHost]=useState(false);
 const [certfile,setCertfile]=useState('');
 const [keyfile,setKeyfile]=useState('');
 const [fingerprint,setFingerprint]=useState('');
 const [users,setUsers]=useState([]);
 const [displayRoles,setDisplayRoles]=useState(LAN_BUILTIN_DISPLAY_ROLES);
 const [displayRole,setDisplayRole]=useState('employee');
 const [customUserDisplay,setCustomUserDisplay]=useState(false);
 const [userDisplayMode,setUserDisplayMode]=useState('basic');
 const [userDisplayFeatures,setUserDisplayFeatures]=useState([]);
 const [editingDisplayRole,setEditingDisplayRole]=useState('');
 const [displayRoleTitle,setDisplayRoleTitle]=useState('');
 const [displayRoleMode,setDisplayRoleMode]=useState('basic');
 const [limitRoleFeatures,setLimitRoleFeatures]=useState(false);
 const [selectedRoleFeatures,setSelectedRoleFeatures]=useState([]);
 const [name,setName]=useState('');
 const [userPassword,setUserPassword]=useState('');
 const [userDisplayName,setUserDisplayName]=useState('');
 const [userIcon,setUserIcon]=useState('user');
 const [userColor,setUserColor]=useState(DEFAULT_AVATAR_COLOR);
 const [userPhoto,setUserPhoto]=useState('');
 const [editingUsername,setEditingUsername]=useState('');
 const [role,setRole]=useState('viewer');
 const [scope,setScope]=useState('all');
 const [selectedProjects,setSelectedProjects]=useState([]);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const run=async action=>{setBusy(true);setError('');setNotice('');try{await action();await onRefresh();}catch(e){setError(e.message||String(e));}finally{setBusy(false);}};
 const refreshDisplayRoles=async()=>{
   const result=await api.lanDisplayRoles();
   if(!Array.isArray(result))throw Error('پاسخ نقش‌های نمایشی معتبر نیست.');
   setDisplayRoles(result);
   return result;
 };
 const loadUsers=()=>run(async()=>{const results=await Promise.all([api.lanUsers(),api.lanDisplayRoles()]);
   if(!Array.isArray(results[0])||!Array.isArray(results[1]))throw Error('پاسخ کاربران یا قالب‌های نمایش معتبر نیست.');
   setUsers(results[0]);setDisplayRoles(results[1]);setView('users');
 });
 const httpsTarget=/^https:\/\//i.test(url.trim());
 const validPin=validLanFingerprint(fingerprint);
 const handleHost=()=>run(async()=>{
   const s=await api.lanHost(username,password,parseInt(port,10),secureHost?certfile.trim():'',secureHost?keyfile.trim():'');
   setMode(s.mode);setNotice(secureHost?'میزبان HTTPS راه‌اندازی شد. اثرانگشت SHA-256 را از پنل میزبان به کلاینت‌ها بده.':'میزبان HTTP قدیمی راه‌اندازی شد؛ ارتباط رمزگذاری نمی‌شود.');
 });
 const handleJoin=()=>run(async()=>{
   const s=await api.lanJoin(url.trim(),username,password,httpsTarget?normalizeLanFingerprint(fingerprint):'');
   setMode(s.mode);await onConnected();setNotice(httpsTarget?'با بررسی اثرانگشت گواهی به سرور HTTPS متصل شدی.':'به میزبان HTTP قدیمی متصل شدی؛ ارتباط رمزگذاری نمی‌شود.');
 });
 const handleLeave=()=>run(async()=>{const s=await api.lanLeave();setMode(s.mode);await onConnected();setNotice('به حالت شخصی برگشتی.');});
 const resetUserForm=()=>{setEditingUsername('');setName('');setUserPassword('');setUserDisplayName('');setUserIcon('user');setUserColor(DEFAULT_AVATAR_COLOR);setUserPhoto('');setRole('viewer');setDisplayRole('employee');setCustomUserDisplay(false);setUserDisplayMode('basic');setUserDisplayFeatures([]);setScope('all');setSelectedProjects([]);};
 const editUser=u=>{
   const id=lanDefaultDisplayRoleForUser(u);
   const template=displayRoles.find(item=>item.id===id);
   const chosenMode=u.displayMode||template?.displayMode||'basic';
   const available=lanAvailableUserFeatures(template,chosenMode);
   const chosenFeatures=Array.isArray(u.displayFeatures)?available.filter(key=>u.displayFeatures.includes(key)):available;
   setEditingUsername(u.username);setName(u.username);setRole(u.role);setDisplayRole(id);
   setUserDisplayMode(chosenMode);setUserDisplayFeatures(chosenFeatures);
   setCustomUserDisplay(chosenMode!==template?.displayMode||chosenFeatures.length!==available.length);
   setScope(u.projects===null?'all':'selected');setSelectedProjects(u.projects||[]);setUserPassword('');
   setUserDisplayName(u.displayName||'');setUserIcon(u.avatarIcon||'user');setUserColor(u.avatarColor||DEFAULT_AVATAR_COLOR);setUserPhoto(u.avatarPhoto||'');
   editorRef.current?.focus();editorRef.current?.scrollIntoView?.({block:'nearest'});
 };
 const changeDisplayRole=id=>{
   setDisplayRole(id);setCustomUserDisplay(false);
   const template=displayRoles.find(item=>item.id===id);
   setUserDisplayMode(template?.displayMode||'basic');
   setUserDisplayFeatures(lanAvailableUserFeatures(template,template?.displayMode||'basic'));
 };
 const activeTemplate=displayRoles.find(item=>item.id===displayRole);
 const activeMode=customUserDisplay?userDisplayMode:activeTemplate?.displayMode||'basic';
 const userFeatureKeys=lanAvailableUserFeatures(activeTemplate,activeMode);
 const invalidDisplayRole=!lanCanAssignDisplayRole(displayRoles,displayRole,role);
 const saveUser=()=>run(async()=>{if(invalidDisplayRole)throw Error('قالب مدیرکل فقط با مجوز فنی مدیر میزبان مجاز است؛ مجوز مدیر نیز به انتخاب قالب مدیرکل نیاز دارد.');
   await api.lanSaveUser({username:name.trim(),password:userPassword,role,displayRole,
     displayMode:customUserDisplay?activeMode:null,
     displayFeatures:customUserDisplay?userFeatureKeys.filter(key=>userDisplayFeatures.includes(key)):null,
     projects:role==='admin'||scope==='all'?null:selectedProjects,displayName:userDisplayName,
     avatarIcon:userIcon,avatarColor:userColor,avatarPhoto:userPhoto});
   setUsers(await api.lanUsers());resetUserForm();setNotice('حساب، قالب نمایش و مجوز فنی ذخیره شد.');});
 const resetPassword=()=>run(async()=>{await api.lanResetPassword(name,userPassword);setUserPassword('');setNotice('رمز قبلی باطل و رمز جدید فعال شد؛ نشست‌های قبلی نیز لغو شدند.');});
 const deleteUser=u=>run(async()=>{await api.lanDeleteUser(u);setUsers(await api.lanUsers());setNotice('حساب حذف شد.');});
 const resetDisplayRoleForm=()=>{setEditingDisplayRole('');setDisplayRoleTitle('');setDisplayRoleMode('basic');setLimitRoleFeatures(false);setSelectedRoleFeatures([]);};
 const editRoleTemplate=template=>{
   if(template.isBuiltin||LAN_BUILTIN_ROLE_IDS.has(template.id))return;
   setEditingDisplayRole(template.id);setDisplayRoleTitle(template.label);setDisplayRoleMode(template.displayMode);
   setLimitRoleFeatures(Array.isArray(template.features));
   setSelectedRoleFeatures(Array.isArray(template.features)?template.features:lanRoleFeatures(template.displayMode));
 };
 const saveRoleTemplate=()=>run(async()=>{
   const title=displayRoleTitle.trim();
   if(!title)throw Error('عنوان قالب نمایش را وارد کن.');
   if(editingDisplayRole&&LAN_BUILTIN_ROLE_IDS.has(editingDisplayRole))throw Error('قالب‌های پیش‌فرض قابل ویرایش نیستند.');
   const payload=lanDisplayRolePayload({id:editingDisplayRole||'custom_'+Date.now().toString(36),
     label:title,displayMode:displayRoleMode,features:selectedRoleFeatures,limited:limitRoleFeatures});
   await api.lanSaveDisplayRole(payload);
   await refreshDisplayRoles();resetDisplayRoleForm();setNotice('قالب نمایش ذخیره شد.');
 });
 const deleteRoleTemplate=template=>run(async()=>{
   if(template.isBuiltin||LAN_BUILTIN_ROLE_IDS.has(template.id))throw Error('قالب‌های پیش‌فرض قابل حذف نیستند.');
   if(users.some(u=>lanDefaultDisplayRoleForUser(u)===template.id))throw Error('ابتدا نقش نمایشی کاربران وابسته را تغییر بده.');
   await api.lanDeleteDisplayRole(template.id);await refreshDisplayRoles();
   if(editingDisplayRole===template.id)resetDisplayRoleForm();
   if(displayRole===template.id)changeDisplayRole('employee');
   setNotice('قالب نمایشی حذف شد.');
 });
 const featureKeys=lanRoleFeatures(displayRoleMode);
 const canManage=status?.user?.role==='admin'&&(status?.mode==='server'||status?.mode==='client');
 return <div className="overlay" onMouseDown={onClose}><section className="dialog lan-modal lan-density" dir="rtl" onMouseDown={e=>e.stopPropagation()} role="dialog" aria-modal="true" aria-label="شبکه محلی و کاربران"><div className="dialog-head"><h2><Users size={19}/> شبکه محلی و کاربران</h2><button className="icon-btn" onClick={onClose} aria-label="بستن"><X size={19}/></button></div><div className="dialog-body">
  <div className="lan-heading"><span className={'connection-dot '+(status?.mode!=='solo'?'online':'')}/><strong>{status?.mode==='server'?'میزبان شبکه فعال':status?.mode==='client'?'متصل به سرور':'حالت شخصی و آفلاین'}</strong></div>
  <details className="lan-density__help"><summary><ShieldCheck size={15}/> راهنمای اتصال امن و اثر انگشت گواهی</summary><p className="lan-help">برای اتصال امن، میزبان را با گواهی و کلید PEM راه‌اندازی کن، نشانی HTTPS را به کلاینت بده و اثرانگشت کامل SHA-256 را مستقیماً از میزبان دریافت و در کلاینت وارد کن. HTTP قدیمی فقط برای شبکه مورداعتماد است و رمزگذاری ندارد.</p></details>
  {status?.error&&<p className="lan-error">{status.error}</p>}
  {status?.mode==='solo'?<div className="lan-modes">
    <div className="setting-block"><h3><Cloud size={17}/> فعال‌کردن سرور محلی</h3>
      <div className="setting-grid"><label>نام مدیر<input value={username} onChange={e=>setUsername(e.target.value)} placeholder="admin"/></label><label>رمز مدیر (حداقل ۱۰ نویسه)<input type="password" value={password} onChange={e=>setPassword(e.target.value)}/></label><label>پورت<input dir="ltr" value={port} onChange={e=>setPort(e.target.value)}/></label></div>
      <label className="lan-tls-toggle"><input type="checkbox" checked={secureHost} onChange={e=>setSecureHost(e.target.checked)}/> HTTPS با گواهی و کلید PEM</label>
      {secureHost?<div className="lan-tls-fields"><label>مسیر گواهی PEM روی میزبان<input dir="ltr" autoComplete="off" value={certfile} onChange={e=>setCertfile(e.target.value)} placeholder="C:\\certs\\server.crt"/></label><label>مسیر کلید خصوصی PEM روی میزبان<input dir="ltr" autoComplete="off" value={keyfile} onChange={e=>setKeyfile(e.target.value)} placeholder="C:\\certs\\server.key"/></label><small>گواهی و کلید باید روی رایانه میزبان وجود داشته باشند؛ کلید خصوصی را به کلاینت‌ها نده.</small></div>:<p className="lan-warning">حالت HTTP قدیمی: رمز عبور و اطلاعات شبکه رمزگذاری نمی‌شوند.</p>}
      <button disabled={busy||!username.trim()||password.length<10||(secureHost&&(!certfile.trim()||!keyfile.trim()))} className="btn primary" onClick={handleHost}>راه‌اندازی میزبان {secureHost?'HTTPS':'HTTP قدیمی'}</button>
    </div>
    <div className="setting-block"><h3><Users size={17}/> اتصال به سرور دیگر</h3>
      <label>نشانی سرور<input dir="ltr" value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://192.168.1.10:48370"/></label>
      {httpsTarget?<div className="lan-tls-fields"><label>اثر انگشت کامل SHA-256 گواهی سرور<input dir="ltr" autoComplete="off" spellCheck={false} value={fingerprint} onChange={e=>setFingerprint(e.target.value)} placeholder="۶۴ رقم هگز از رایانه میزبان"/></label><small>این مقدار را از میزبان از مسیر قابل‌اعتماد دریافت کن. اتصال HTTPS بدون pin معتبر انجام نمی‌شود.</small></div>:<p className="lan-warning">نشانی HTTP قدیمی است و ارتباط رمزگذاری ندارد. برای اتصال امن نشانی HTTPS و اثرانگشت سرور را وارد کن.</p>}
      <div className="setting-grid"><label>نام کاربری<input value={username} onChange={e=>setUsername(e.target.value)}/></label><label>رمز<input type="password" value={password} onChange={e=>setPassword(e.target.value)}/></label></div>
      <button disabled={busy||!username.trim()||!password||!(url.trim().startsWith('http://')||httpsTarget)||(httpsTarget&&!validPin)} className="btn secondary" onClick={handleJoin}>اتصال و دریافت کارها</button>
    </div>
  </div>:
   <><div className="lan-connected"><span>{status?.mode==='server'?('پورت میزبان: '+status.port):('نشانی: '+status?.url)}</span><span>سطح دسترسی: <RoleBadge role={status?.user?.role}/></span><span>{status?.transport==='https'?'اتصال HTTPS':'اتصال HTTP قدیمی (بدون رمزگذاری)'}</span>{status?.mode==='server'&&status?.fingerprint&&<span>اثر انگشت SHA-256 گواهی میزبان: <code dir="ltr">{status.fingerprint}</code></span>}</div><div className="lan-actions"><button className="btn secondary" onClick={onConnected}><RefreshCw size={16}/> تازه‌سازی اطلاعات</button>{canManage&&<button className="btn primary" aria-label="تعریف کاربر و تعیین سطح دسترسی" onClick={loadUsers}><Plus size={16}/> تعریف کاربر</button>}<button className="btn secondary" disabled={busy} onClick={handleLeave}>خروج از شبکه</button></div></>}
  {view==='users'&&canManage&&<div className="users-manager">
    <div className="account-create-heading"><Users size={18}/> تعریف کاربر و تعیین سطح دسترسی</div>
    <p className="lan-help">مدیر قالب نمایش هر حساب را تعیین می‌کند. قالب فقط امکانات قابل مشاهده را مشخص می‌کند؛ مجوز فنی و دسترسی به داده‌ها جداگانه در میزبان کنترل می‌شود.</p>
    <div className="lan-density__workspace">
    <aside className="lan-density__directory" aria-label="حساب‌ها و قالب‌های موجود">
    <h3>کاربران شبکه</h3>
    <div className="users-list">{users.map(u=><div className="user-row" key={u.username}>
      <Avatar user={u} size={36}/>
      <span><strong>{u.displayName||u.username}</strong><small dir="ltr">@{u.username}</small>
        <small>قالب نمایش: {lanRoleLabel(displayRoles,lanDefaultDisplayRoleForUser(u))}</small>
        <span>مجوز فنی: <RoleBadge role={u.role}/></span>
        <small>{u.projects===null?'تمام پروژه‌ها':u.projects.length?u.projects.length+' پروژه مجاز':'بدون پروژه مجاز'}</small>
      </span>
      <button type="button" className="btn secondary" onClick={()=>editUser(u)}>ویرایش</button>
      <button type="button" aria-label={'حذف کاربر '+u.username} disabled={busy||u.username===status?.user?.username}
        onClick={()=>{if(window.confirm('این کاربر حذف شود؟'))deleteUser(u.username)}}><Trash2 size={15}/></button>
    </div>)}</div>
    <details className="setting-block lan-display-roles">
      <summary><ShieldCheck size={16}/> قالب‌های نقش و سطح نمایش <small>{displayRoles.length.toLocaleString('fa-IR')} قالب</small></summary>
      <p className="lan-help">قالب‌های اصلی مدیرکل، مدیر ارشد، مدیر میانی، مدیر واحد و کارمند آماده‌اند. می‌توانی برای بخش‌های دیگر قالب اختصاصی بسازی. این قالب‌ها به‌تنهایی دسترسی امنیتی ایجاد نمی‌کنند.</p>
      <div className="users-list">{displayRoles.map(template=>{
        const assigned=users.filter(u=>lanDefaultDisplayRoleForUser(u)===template.id).length;
        const builtin=template.isBuiltin||LAN_BUILTIN_ROLE_IDS.has(template.id);
        const modeLabel=INTERFACE_MODE_OPTIONS.find(mode=>mode.id===template.displayMode)?.label||template.displayMode;
        return <div className="user-row" key={template.id}>
          <span><strong>{template.label}</strong><small>{modeLabel} · {assigned.toLocaleString('fa-IR')} کاربر · {builtin?'پیش‌فرض':'سفارشی'}</small></span>
          {!builtin&&<><button className="btn secondary" type="button" disabled={busy} onClick={()=>editRoleTemplate(template)}>ویرایش</button>
            <button type="button" disabled={busy||!!assigned} aria-label={'حذف قالب '+template.label}
              title={assigned?'ابتدا کاربران این قالب را به نقش دیگری منتقل کن.':'حذف قالب سفارشی'}
              onClick={()=>{if(window.confirm('قالب نمایشی «'+template.label+'» حذف شود؟'))deleteRoleTemplate(template);}}><Trash2 size={15}/></button></>}
        </div>;
      })}</div>
      <div className="account-create-heading"><Plus size={17}/>{editingDisplayRole?'ویرایش قالب سفارشی':'افزودن قالب سفارشی'}</div>
      <div className="setting-grid">
        <label>عنوان نقش<input maxLength={60} value={displayRoleTitle} onChange={e=>setDisplayRoleTitle(e.target.value)} placeholder="مثلاً مسئول تدارکات"/></label>
        <label>حالت پایه نمایش<select value={displayRoleMode} onChange={e=>setDisplayRoleMode(e.target.value)}>
          {INTERFACE_MODE_OPTIONS.map(option=><option value={option.id} key={option.id}>{option.label}</option>)}
        </select></label>
      </div>
      <label className="setting-toggle"><input type="checkbox" checked={limitRoleFeatures}
        onChange={e=>{setLimitRoleFeatures(e.target.checked);if(e.target.checked&&!selectedRoleFeatures.length)setSelectedRoleFeatures(featureKeys);}}/>
        <span><strong>انتخاب امکانات قابل نمایش این نقش</strong><small>وقتی خاموش است همه امکانات حالت پایه نمایش داده می‌شوند، در محدوده مجوز فنی کاربر.</small></span>
      </label>
      {limitRoleFeatures&&<details className="lan-role-features" open><summary>امکانات مجاز ({selectedRoleFeatures.filter(key=>featureKeys.includes(key)).length.toLocaleString('fa-IR')} مورد)</summary>
        <div className="scope-list" role="group" aria-label="امکانات قابل نمایش نقش سفارشی">
          {featureKeys.map(key=><label key={key}><input type="checkbox" checked={selectedRoleFeatures.includes(key)}
            onChange={e=>setSelectedRoleFeatures(keys=>e.target.checked?[...keys,key]:keys.filter(item=>item!==key))}/>
            {LAN_FEATURE_LABELS[key]||key}</label>)}
        </div>
      </details>}
      <div className="lan-actions"><button className="btn primary" type="button" disabled={busy||!displayRoleTitle.trim()}
        onClick={saveRoleTemplate}>{editingDisplayRole?'ذخیره قالب':'ایجاد قالب'}</button>
        {editingDisplayRole&&<button className="btn secondary" type="button" onClick={resetDisplayRoleForm}>انصراف از ویرایش</button>}
      </div>
    </details>
    </aside>
    <section className="lan-density__editor" aria-label="فرم مدیریت حساب" tabIndex={-1} ref={editorRef}>
    <div className="account-create-heading"><Plus size={17}/>{editingUsername?'ویرایش حساب '+editingUsername:'ساخت حساب جدید'}</div>
    <h4>مشخصات حساب</h4>
    <div className="setting-grid lan-density__identity">
      <label>نام کاربری انگلیسی<input autoComplete="off" maxLength={40} disabled={!!editingUsername}
        value={name} onChange={e=>setName(e.target.value)}/></label>
      <label>رمز {editingUsername?'(خالی = بدون تغییر)':'(حداقل ۱۰ نویسه)'}
        <input type="password" autoComplete="new-password" value={userPassword} onChange={e=>setUserPassword(e.target.value)}/></label>
      <label>نام نمایشی<input maxLength={80} value={userDisplayName} onChange={e=>setUserDisplayName(e.target.value)}
        placeholder="مثلاً مسئول تولید"/></label>
    </div>
    <h4>نقش و دسترسی</h4>
    <div className="setting-grid lan-density__access">
      <label>قالب نقش و امکانات قابل نمایش
        <select value={displayRole} onChange={e=>changeDisplayRole(e.target.value)}>
          {!displayRoles.some(item=>item.id===displayRole)&&<option value={displayRole}>نقش ناشناخته ({displayRole})</option>}
          {displayRoles.map(template=><option key={template.id} value={template.id}>{template.label}</option>)}
        </select>
      </label>
      <label>مجوز فنی (مستقل از قالب نمایش)
        <select value={role} onChange={e=>{setRole(e.target.value);if(e.target.value==='admin')setScope('all');}}>
          <option value="viewer">مشاهده‌گر: فقط خواندن</option>
          <option value="editor">ویرایشگر: انجام و تغییر کارها</option>
          <option value="admin">مدیر میزبان: مدیریت همه بخش‌ها و کاربران</option>
        </select>
      </label>
      {role!=='admin'&&<label>دسترسی به پروژه‌ها
        <select value={scope} onChange={e=>setScope(e.target.value)}>
          <option value="all">تمام پروژه‌ها</option>
          <option value="selected">فقط پروژه‌های انتخابی</option>
        </select>
      </label>}
    </div>
    <p className="account-role-help">{editingUsername?'تغییر قالب نمایش هنگام ویرایش، مجوز فنی قبلی را خودکار عوض نمی‌کند.':'حساب جدید با مجوز فنی «مشاهده‌گر» شروع می‌شود؛ انتخاب قالب نمایشی هیچ مجوزی را تغییر نمی‌دهد.'} {role==='admin'
      ?'مدیر به تمام پروژه‌ها و مدیریت حساب‌ها دسترسی دارد.'
      :role==='editor'
        ?'ویرایشگر می‌تواند کارهای پروژه‌های مجاز را ثبت و ویرایش کند، اما اجازه مدیریت کاربران را ندارد.'
        :'مشاهده‌گر فقط اطلاعات پروژه‌های مجاز را می‌بیند و حق تغییر ندارد.'}</p>
    {invalidDisplayRole&&<p className="lan-error" role="alert">قالب معتبر انتخاب کن. قالب «مدیرکل» فقط با مجوز فنی «مدیر میزبان» سازگار است و این مجوز نیز به قالب «مدیرکل» نیاز دارد. هر دو را جداگانه انتخاب کن.</p>}
    {activeTemplate&&<div className="setting-block lan-user-display-options">
      <label className="setting-toggle"><input type="checkbox" checked={customUserDisplay} onChange={e=>{
        setCustomUserDisplay(e.target.checked);
        if(e.target.checked&&!userDisplayFeatures.length){
          setUserDisplayMode(activeTemplate.displayMode);
          setUserDisplayFeatures(lanAvailableUserFeatures(activeTemplate,activeTemplate.displayMode));
        }
      }}/><span><strong>شخصی‌سازی امکانات این کاربر</strong>
        <small>تنظیم مستقل هر حساب، در محدوده قالب انتخابی؛ با خاموش‌کردن، تنظیمات پیش‌فرض قالب اعمال می‌شود.</small>
      </span></label>
      {customUserDisplay&&<>
        <label>حالت نمایش این حساب
          <select value={activeMode} onChange={e=>setUserDisplayMode(e.target.value)}>
            {INTERFACE_MODE_OPTIONS.filter(item=>LAN_MODE_ORDER[item.id]<=LAN_MODE_ORDER[activeTemplate.displayMode])
              .map(item=><option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </label>
        <details className="lan-role-features"><summary>امکانات قابل مشاهده ({userFeatureKeys.filter(key=>userDisplayFeatures.includes(key)).length.toLocaleString('fa-IR')} از {userFeatureKeys.length.toLocaleString('fa-IR')})</summary>
          <div className="scope-list" role="group" aria-label="امکانات قابل نمایش این کاربر">
            {userFeatureKeys.map(key=><label key={key}><input type="checkbox"
              checked={userDisplayFeatures.includes(key)}
              onChange={e=>setUserDisplayFeatures(keys=>e.target.checked?[...keys,key]:keys.filter(item=>item!==key))}/>
              {LAN_FEATURE_LABELS[key]||key}</label>)}
          </div>
        </details>
      </>}
    </div>}
    {role!=='admin'&&scope==='selected'&&<div className="scope-list" role="group" aria-label="پروژه‌های مجاز">
      {projects.map(p=><label key={p.id}><input type="checkbox" checked={selectedProjects.includes(p.id)}
        onChange={e=>setSelectedProjects(v=>e.target.checked?[...v,p.id]:v.filter(id=>id!==p.id))}/>{p.name}</label>)}
      {!selectedProjects.length&&<small>هیچ پروژه‌ای انتخاب نشده است؛ این حساب فقط به پروفایل خودش دسترسی خواهد داشت.</small>}
    </div>}
    <details className="lan-density__optional"><summary><Users size={15}/> آواتار و نماد کاربر <small>شخصی‌سازی اختیاری</small></summary>
    <div className="account-avatar-controls">
      <span>نماد انتخابی حوزه فعالیت کاربر</span>
      <div className="account-avatar-preview"><Avatar size={43} user={{username:name,displayName:userDisplayName,
        role,avatarIcon:userIcon,avatarColor:userColor,avatarPhoto:userPhoto}}/>
        <span>نماد نشان‌دهنده انتخاب کاربر است، نه تشخیص خودکار ویژگی‌های شخصیتی.</span></div>
      <AvatarIconPicker value={userIcon} onChange={key=>{setUserIcon(key);setUserPhoto('');}}/>
      <label className="member-color-field">رنگ آواتار
        <input aria-label="رنگ آواتار کاربر" type="color" value={userColor} onChange={e=>setUserColor(e.target.value)}/></label>
    </div>
    </details>
    <div className="lan-actions lan-density__actions"><button type="button" className="btn primary"
      disabled={busy||invalidDisplayRole||!name.trim()||(!editingUsername&&userPassword.length<10)}
      onClick={saveUser}>{editingUsername?'ذخیره تغییرات کاربر':'ایجاد حساب کاربر'}</button>
      {editingUsername&&<button type="button" className="btn secondary" onClick={resetUserForm}>حساب جدید</button>}
      {editingUsername&&<button type="button" className="btn secondary"
        disabled={busy||userPassword.length<10} onClick={resetPassword}>بازنشانی رمز</button>}
    </div>
    <p className="lan-help">مجوز فنی روی میزبان اعمال می‌شود و قالب نمایشی جای آن را نمی‌گیرد. رمز قبلی هنگام بازنشانی باطل می‌شود.</p>
    </section>
    </div>
  </div>}
  {!!notice&&<div className="inline-message">{notice}</div>}{!!error&&<div className="lan-error" role="alert">{error}</div>}
 </div></section></div>;
}
