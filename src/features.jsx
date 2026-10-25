import React,{useEffect,useState} from 'react';
import {Check, Cloud, Download, Layers3, LockKeyhole, Moon, Plus, Settings2, ShieldCheck, Sun, Trash2, Users, Wallet, X, ArrowUp, ArrowDown, RefreshCw, Archive, RotateCcw} from 'lucide-react';
import {Avatar, AvatarIconPicker, RoleBadge, DEFAULT_AVATAR_COLOR} from './members.jsx';
import {PrioritySettings} from './priorities.jsx';

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
 const updateStage=(id,fields)=>onChange(s=>({...s,stages:s.stages.map(stage=>stage.id===id?{...stage,...fields}:stage)}));
 const addStage=()=>{if(!name.trim()||stages.length>=40)return;const newStage={id:'stage_'+Date.now()+'_'+Math.random().toString(36).slice(2,7),label:name.trim(),subtitle:'مرحله سفارشی',color:'#6386cb'};onChange(s=>({...s,stages:[...s.stages,newStage]}));setName('');};
 const deleteStage=id=>{
   if(stages.length<=1||stages.find(stage=>stage.id===id)?.archived===true)return;
   const fallback=stages.find(stage=>stage.id!==id&&stage.archived!==true)?.id;
   if(!fallback)return;
   onChange(s=>({...s,stages:s.stages.filter(stage=>stage.id!==id),tasks:s.tasks.map(t=>
     (t.listId||t.status)===id
       ?{...t,...(t.boardId?{listId:fallback}:{}),status:fallback}
       :t)}));
 };
 const moveStage=(id,d)=>{const index=stages.findIndex(s=>s.id===id),next=index+d;if(next<0||next>=stages.length)return;const a=[...stages];[a[index],a[next]]=[a[next],a[index]];onChange(s=>({...s,stages:a}));};
 const updateDefault=checked=>onChange(s=>({...s,settings:{...s.settings,costDefault:checked},projects:s.projects.map(p=>({...p,costEnabled:checked}))}));
 const updateTheme=theme=>onChange(s=>({...s,settings:{...s.settings,theme}}));
 return <div className="overlay" onMouseDown={onClose}><section className="dialog settings-modal" onMouseDown={e=>e.stopPropagation()} role="dialog" aria-modal="true"><div className="dialog-head"><h2><Settings2 size={18}/> تنظیمات مدار</h2><button className="icon-btn" onClick={onClose} aria-label="بستن"><X size={19}/></button></div>
   <div className="dialog-body settings-content">
     <div className="setting-block"><h3><Moon size={17}/> ظاهر برنامه</h3><p>حالت نمایش در تمام صفحات برنامه اعمال می‌شود.</p><div className="theme-picks"><button className={settings.theme!=='dark'?'selected':''} disabled={!canManage} onClick={()=>updateTheme('light')}><Sun size={19}/> روشن {settings.theme!=='dark'&&<Check size={16}/>}</button><button className={settings.theme==='dark'?'selected':''} disabled={!canManage} onClick={()=>updateTheme('dark')}><Moon size={19}/> تاریک {settings.theme==='dark'&&<Check size={16}/>}</button></div></div>
     <div className="setting-block"><h3><Layers3 size={17}/> تقویم و نمایش تاریخ</h3><p>انتخاب تقویم فقط روی این کامپیوتر ذخیره می‌شود؛ تاریخ واقعی کارها در همه سیستم‌ها یکسان می‌ماند.</p><div className="theme-picks"><button className={calendar==='jalali'?'selected':''} onClick={()=>onCalendarChange('jalali')}>شمسی {calendar==='jalali'&&<Check size={16}/>}</button><button className={calendar==='gregorian'?'selected':''} onClick={()=>onCalendarChange('gregorian')}>میلادی {calendar==='gregorian'&&<Check size={16}/>}</button></div></div>
     <div className="setting-block"><h3><Wallet size={17}/> مدیریت هزینه‌ها</h3><label className="setting-toggle"><input type="checkbox" checked={!!settings.costDefault} disabled={!canManage} onChange={e=>updateDefault(e.target.checked)}/><span><strong>فعال‌کردن فیلد هزینه برای همه پروژه‌ها</strong><small>هم برای پروژه‌های فعلی اعمال می‌شود و هم پیش‌فرض پروژه‌های جدید خواهد بود؛ مبالغ قبلی پاک نمی‌شوند.</small></span></label></div>
     <PrioritySettings settings={settings} usedIds={priorityUsedIds||data.tasks.map(t=>t.priority)} canManage={canManage} onChange={priorityDefinitions=>onChange(s=>({...s,settings:{...s.settings,priorityDefinitions}}))}/>
     <div className="setting-block"><h3><Layers3 size={17}/> ستون‌ها و مراحل برد</h3><p>ستون‌ها را روی برد بکشید و جابه‌جا کنید یا از فلش‌های زیر استفاده کنید. رنگ هر ستون مستقل است.</p>
       <div className="stage-manager">{stages.map((stage,i)=><div className="stage-manage-row" key={stage.id}>
         <span className="stage-color" style={{background:stage.color}}/>
         <input className="stage-color-picker" type="color" aria-label={'رنگ ستون '+stage.label} title={'رنگ ستون '+stage.label} value={/^#[0-9a-f]{6}$/i.test(stage.color)?stage.color:'#64748b'} disabled={!canManage} onChange={e=>updateStage(stage.id,{color:e.target.value})}/>
         {editing===stage.id?<div className="stage-edit-fields"><input aria-label="نام ستون" maxLength={100} value={label} onChange={e=>setLabel(e.target.value)}/><input aria-label="توضیح ستون" value={subtitle} onChange={e=>setSubtitle(e.target.value)}/></div>:<span className="stage-manage-label"><strong>{stage.label}</strong><small>{stage.archived===true?'بایگانی‌شده · ':''}{stage.subtitle}</small></span>}
         {canManage&&<div className="stage-manage-actions">
           {editing===stage.id?<button onClick={()=>{if(label.trim())updateStage(stage.id,{label:label.trim(),subtitle:subtitle.trim()});setEditing('');}} title="ذخیره"><Check size={16}/></button>:<button onClick={()=>{setEditing(stage.id);setLabel(stage.label);setSubtitle(stage.subtitle||'');}} title="ویرایش">ویرایش</button>}
           <button onClick={()=>moveStage(stage.id,-1)} disabled={i===0} title="انتقال به راست"><ArrowUp size={15}/></button>
           <button onClick={()=>moveStage(stage.id,1)} disabled={i===stages.length-1} title="انتقال به چپ"><ArrowDown size={15}/></button>
           {boardId&&(stage.archived===true?
             <button type="button" onClick={()=>onRestoreList?.(stage.id)} title="بازیابی ستون بدون تغییر کارت‌ها" aria-label={'بازیابی ستون '+stage.label}><RotateCcw size={16}/></button>:
             <button type="button" disabled={stages.filter(item=>item.archived!==true).length<=1} onClick={()=>onArchiveList?.(stage.id)} title="بایگانی ستون بدون حذف کارت‌ها" aria-label={'بایگانی ستون '+stage.label}><Archive size={16}/></button>)}
           <button onClick={()=>{if(window.confirm('این ستون حذف شود و کارهای آن منتقل شوند؟'))deleteStage(stage.id);}} disabled={stages.length===1||stage.archived===true||stages.filter(item=>item.archived!==true).length<=1} title="حذف"><Trash2 size={15}/></button>
         </div>}
       </div>)}</div>
       {canManage&&<div className="stage-new"><input value={name} maxLength={100} onChange={e=>setName(e.target.value)} onKeyDown={e=>e.key==='Enter'&&addStage()} placeholder="نام ستون جدید..."/><button className="btn primary" disabled={!name.trim()} onClick={addStage}><Plus size={15}/> افزودن ستون</button></div>}
     </div>
     <p className="setting-foot">فونت داخلی برنامه: وزیرمتن · تنظیمات برای داده‌های ذخیره‌شده اعمال می‌شوند.</p>
   </div>
 </section></div>;
}

export function LanPanel({api,projects,onClose,status,onRefresh,onConnected}){
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
 const [name,setName]=useState('');
 const [userPassword,setUserPassword]=useState('');
 const [userDisplayName,setUserDisplayName]=useState('');
 const [userIcon,setUserIcon]=useState('user');
 const [userColor,setUserColor]=useState(DEFAULT_AVATAR_COLOR);
 const [userPhoto,setUserPhoto]=useState('');
 const [editingUsername,setEditingUsername]=useState('');
 const [role,setRole]=useState('editor');
 const [scope,setScope]=useState('all');
 const [selectedProjects,setSelectedProjects]=useState([]);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const run=async action=>{setBusy(true);setError('');setNotice('');try{await action();await onRefresh();}catch(e){setError(e.message||String(e));}finally{setBusy(false);}};
 const loadUsers=()=>run(async()=>{setUsers(await api.lanUsers());setView('users');});
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
 const resetUserForm=()=>{setEditingUsername('');setName('');setUserPassword('');setUserDisplayName('');setUserIcon('user');setUserColor(DEFAULT_AVATAR_COLOR);setUserPhoto('');setRole('editor');setScope('all');setSelectedProjects([]);};
 const editUser=u=>{setEditingUsername(u.username);setName(u.username);setRole(u.role);setScope(u.projects===null?'all':'selected');setSelectedProjects(u.projects||[]);setUserPassword('');setUserDisplayName(u.displayName||'');setUserIcon(u.avatarIcon||'user');setUserColor(u.avatarColor||DEFAULT_AVATAR_COLOR);setUserPhoto(u.avatarPhoto||'');};
 const saveUser=()=>run(async()=>{await api.lanSaveUser({username:name.trim(),password:userPassword,role,projects:role==='admin'||scope==='all'?null:selectedProjects,displayName:userDisplayName,avatarIcon:userIcon,avatarColor:userColor,avatarPhoto:userPhoto});setUsers(await api.lanUsers());resetUserForm();setNotice('حساب، پروفایل و دسترسی ذخیره شد.');});
 const resetPassword=()=>run(async()=>{await api.lanResetPassword(name,userPassword);setUserPassword('');setNotice('رمز قبلی باطل و رمز جدید فعال شد؛ نشست‌های قبلی نیز لغو شدند.');});
 const deleteUser=u=>run(async()=>{await api.lanDeleteUser(u);setUsers(await api.lanUsers());setNotice('حساب حذف شد.');});
 const canManage=status?.user?.role==='admin'&&(status?.mode==='server'||status?.mode==='client');
 return <div className="overlay" onMouseDown={onClose}><section className="dialog lan-modal" onMouseDown={e=>e.stopPropagation()} role="dialog" aria-modal="true"><div className="dialog-head"><h2><Users size={19}/> شبکه محلی و کاربران</h2><button className="icon-btn" onClick={onClose} aria-label="بستن"><X size={19}/></button></div><div className="dialog-body">
  <div className="lan-heading"><span className={'connection-dot '+(status?.mode!=='solo'?'online':'')}/><strong>{status?.mode==='server'?'میزبان شبکه فعال':status?.mode==='client'?'متصل به سرور':'حالت شخصی و آفلاین'}</strong></div>
  <p className="lan-help">برای اتصال امن، میزبان را با گواهی و کلید PEM راه‌اندازی کن، نشانی HTTPS را به کلاینت بده و اثرانگشت کامل SHA-256 را مستقیماً از میزبان دریافت و در کلاینت وارد کن. HTTP قدیمی فقط برای شبکه مورداعتماد است و رمزگذاری ندارد.</p>
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
    <p className="lan-help">فقط مدیر می‌تواند حساب جدید بسازد، نقش‌ها را تغییر دهد یا پروژه‌های مجاز را مشخص کند. هر کاربر نماد حوزه فعالیتش را خودش هم می‌تواند از بخش پروفایل تغییر دهد.</p>
    <h3>کاربران شبکه</h3>
    <div className="users-list">{users.map(u=><div className="user-row" key={u.username}>
      <Avatar user={u} size={36}/>
      <span><strong>{u.displayName||u.username}</strong><small dir="ltr">@{u.username}</small>
        <RoleBadge role={u.role}/>
        <small>{u.projects===null?'تمام پروژه‌ها':u.projects.length?u.projects.length+' پروژه مجاز':'بدون پروژه مجاز'}</small>
      </span>
      <button type="button" className="btn secondary" onClick={()=>editUser(u)}>ویرایش</button>
      <button type="button" aria-label={'حذف کاربر '+u.username} disabled={busy||u.username===status?.user?.username}
        onClick={()=>{if(window.confirm('این کاربر حذف شود؟'))deleteUser(u.username)}}><Trash2 size={15}/></button>
    </div>)}</div>
    <div className="account-create-heading"><Plus size={17}/>{editingUsername?'ویرایش حساب '+editingUsername:'ساخت حساب جدید'}</div>
    <div className="setting-grid">
      <label>نام کاربری انگلیسی<input autoComplete="off" maxLength={40} disabled={!!editingUsername}
        value={name} onChange={e=>setName(e.target.value)}/></label>
      <label>رمز {editingUsername?'(خالی = بدون تغییر)':'(حداقل ۱۰ نویسه)'}
        <input type="password" autoComplete="new-password" value={userPassword} onChange={e=>setUserPassword(e.target.value)}/></label>
      <label>نام نمایشی<input maxLength={80} value={userDisplayName} onChange={e=>setUserDisplayName(e.target.value)}
        placeholder="مثلاً مسئول تولید"/></label>
      <label>نقش و سطح دسترسی
        <select value={role} onChange={e=>{setRole(e.target.value);if(e.target.value==='admin')setScope('all');}}>
          <option value="viewer">مشاهده‌گر: فقط خواندن</option>
          <option value="editor">ویرایشگر: انجام و تغییر کارها</option>
          <option value="admin">مدیر: مدیریت همه بخش‌ها و کاربران</option>
        </select>
      </label>
      {role!=='admin'&&<label>دسترسی به پروژه‌ها
        <select value={scope} onChange={e=>setScope(e.target.value)}>
          <option value="all">تمام پروژه‌ها</option>
          <option value="selected">فقط پروژه‌های انتخابی</option>
        </select>
      </label>}
    </div>
    <p className="account-role-help">{role==='admin'
      ?'مدیر به تمام پروژه‌ها و مدیریت حساب‌ها دسترسی دارد.'
      :role==='editor'
        ?'ویرایشگر می‌تواند کارهای پروژه‌های مجاز را ثبت و ویرایش کند، اما اجازه مدیریت کاربران را ندارد.'
        :'مشاهده‌گر فقط اطلاعات پروژه‌های مجاز را می‌بیند و حق تغییر ندارد.'}</p>
    {role!=='admin'&&scope==='selected'&&<div className="scope-list" role="group" aria-label="پروژه‌های مجاز">
      {projects.map(p=><label key={p.id}><input type="checkbox" checked={selectedProjects.includes(p.id)}
        onChange={e=>setSelectedProjects(v=>e.target.checked?[...v,p.id]:v.filter(id=>id!==p.id))}/>{p.name}</label>)}
      {!selectedProjects.length&&<small>هیچ پروژه‌ای انتخاب نشده است؛ این حساب فقط به پروفایل خودش دسترسی خواهد داشت.</small>}
    </div>}
    <div className="account-avatar-controls">
      <span>نماد انتخابی حوزه فعالیت کاربر</span>
      <div className="account-avatar-preview"><Avatar size={43} user={{username:name,displayName:userDisplayName,
        role,avatarIcon:userIcon,avatarColor:userColor,avatarPhoto:userPhoto}}/>
        <span>نماد نشان‌دهنده انتخاب کاربر است، نه تشخیص خودکار ویژگی‌های شخصیتی.</span></div>
      <AvatarIconPicker value={userIcon} onChange={key=>{setUserIcon(key);setUserPhoto('');}}/>
      <label className="member-color-field">رنگ آواتار
        <input aria-label="رنگ آواتار کاربر" type="color" value={userColor} onChange={e=>setUserColor(e.target.value)}/></label>
    </div>
    <div className="lan-actions"><button type="button" className="btn primary"
      disabled={busy||!name.trim()||(!editingUsername&&userPassword.length<10)}
      onClick={saveUser}>{editingUsername?'ذخیره تغییرات کاربر':'ایجاد حساب کاربر'}</button>
      {editingUsername&&<button type="button" className="btn secondary" onClick={resetUserForm}>حساب جدید</button>}
      {editingUsername&&<button type="button" className="btn secondary"
        disabled={busy||userPassword.length<10} onClick={resetPassword}>بازنشانی رمز</button>}
    </div>
    <p className="lan-help">تغییر نقش و محدوده فقط با مجوز مدیر انجام می‌شود. رمز قبلی هنگام بازنشانی باطل می‌شود.</p>
  </div>}
  {!!notice&&<div className="inline-message">{notice}</div>}{!!error&&<div className="lan-error" role="alert">{error}</div>}
 </div></section></div>;
}
