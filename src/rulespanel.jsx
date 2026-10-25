import React, {useEffect,useState} from 'react';
import {Zap,Plus,Trash2,RefreshCw,X} from 'lucide-react';
import './rulespanel.css';

const eventId=()=>('rule-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
const triggers={
 card_created:'ساخت کارت جدید',card_moved:'انتقال کارت',label_changed:'تغییر برچسب',
 checklist_completed:'تکمیل چک‌لیست',custom_field_changed:'تغییر فیلد سفارشی',
 due_soon:'نزدیک‌شدن به موعد'
};

export function RulesPanel({api,project,users,onClose}){
 const [rules,setRules]=useState([]);
 const [trigger,setTrigger]=useState('card_moved');
 const [kind,setKind]=useState('notify');
 const [message,setMessage]=useState('');
 const [target,setTarget]=useState('');const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const load=async()=>{setRules(await api.collabRead('rules',project.id));};
 useEffect(()=>{load().catch(e=>setError(e.message));},[project.id]);
 const send=async command=>{
   setBusy(true);setError('');
   try{await api.collabCommand({eventId:eventId(),...command});await load();}
   catch(e){setError(e.message||String(e));}
   finally{setBusy(false);}
 };
 const add=()=>{
   if(!message.trim()||kind==='notify'&&!target){setError('پیام و گیرنده لازم‌اند.');return;}
   const actions=kind==='notify'?[{type:'notify',users:[target],message:message.trim()}]:
                  [{type:'comment',text:message.trim()}];
   send({type:'rule.upsert',rule:{id:eventId(),projectId:project.id,
         trigger,conditions:[],actions,enabled:true}});
 };
 return <div className="rule-backdrop" onMouseDown={onClose}><section className="rule-dialog" role="dialog" aria-modal="true" aria-label="مدیریت قوانین خودکار" onMouseDown={e=>e.stopPropagation()}>
  <header><strong><Zap size={17}/> قوانین خودکار: {project.name}</strong><button onClick={onClose} aria-label="بستن"><X size={18}/></button></header>
  <div className="rule-body">
   <p>قانون‌ها روی سرور اجرا می‌شوند و فقط دو عمل امن دارند: اعلان برای عضو و ثبت نظر. اجرای کد یا فرمان سیستم مجاز نیست.</p>
   <label>رویداد<select value={trigger} onChange={e=>setTrigger(e.target.value)}>{Object.entries(triggers).map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label>
   <label>عمل<select value={kind} onChange={e=>setKind(e.target.value)}><option value="notify">ارسال اعلان</option><option value="comment">ثبت نظر خودکار</option></select></label>
   {kind==='notify'&&<label>دریافت‌کننده<select value={target} onChange={e=>setTarget(e.target.value)}><option value="">انتخاب عضو</option>{users.map(user=><option value={user.username} key={user.username}>{user.displayName||user.username}</option>)}</select></label>}
   <label>متن<input value={message} maxLength={kind==='notify'?240:4000} onChange={e=>setMessage(e.target.value)} placeholder="متن رویداد، بدون اجرای کد"/></label>
   <button className="btn primary" disabled={busy} onClick={add}><Plus size={16}/> افزودن قانون</button>
   <button className="btn secondary" disabled={busy} onClick={async()=>{setBusy(true);try{const result=await api.runDueScheduler();setError('اجرای زمان‌بند: '+result.events+' کارت بررسی شد، '+result.new+' رویداد تازه ثبت شد.');}catch(e){setError(e.message);}finally{setBusy(false);}}}>اجرای بررسی موعدها اکنون</button>
   <div className="rule-list"><div className="rule-list-head"><strong>قانون‌های پروژه ({rules.length})</strong><button disabled={busy} onClick={()=>load().catch(e=>setError(e.message))}><RefreshCw size={15}/> تازه‌سازی</button></div>
    {rules.map(rule=><div key={rule.id}><span><b>{triggers[rule.trigger]||rule.trigger}</b> · {rule.actions.map(a=>a.message||a.text).join(' | ')}</span><button disabled={busy} title="حذف قانون" onClick={()=>{if(window.confirm('این قانون حذف شود؟'))send({type:'rule.delete',ruleId:rule.id});}}><Trash2 size={15}/></button></div>)}
    {!rules.length&&<p>قانونی برای این پروژه ثبت نشده است.</p>}
   </div>
   {error&&<p role="alert" className="rule-error">{error}</p>}
  </div>
 </section></div>;
}
