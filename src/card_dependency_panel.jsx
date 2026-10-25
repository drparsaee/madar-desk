import React,{useMemo,useState} from 'react';
import {addCardDependency,removeCardDependency,cardBlockingStatus} from './card_dependencies.js';

/** Optional M06 task editor UI: authorized same-project task list only.
 * Backend validates every persisted dependency and remains the source of truth.
 */
export function CardDependencyPanel({task,allTasks,canEdit=false,onChange=()=>{}}){
  const [selected,setSelected]=useState('');
  const [error,setError]=useState('');
  const tasks=Array.isArray(allTasks)?allTasks:[];
  const byId=useMemo(()=>new Map(tasks.map(card=>[card.id,card])),[tasks]);
  const current=Array.isArray(task?.dependencies)?task.dependencies:[];
  const candidates=tasks.filter(card=>card.projectId===task.projectId&&card.id!==task.id&&
    card.deleted!==true&&card.archived!==true&&!current.includes(card.id));
  let status;
  try{status=cardBlockingStatus(tasks,task.id);}
  catch(e){status={blocked:false,blockingIds:[],invalid:e.message};}
  const apply=(predecessorId,add)=>{
    if(!canEdit||status.invalid)return;
    try{
      const updated=add
        ?addCardDependency({tasks},task.id,predecessorId,{canEdit:true,grantedProjectIds:[task.projectId]})
        :removeCardDependency({tasks},task.id,predecessorId,{canEdit:true,grantedProjectIds:[task.projectId]});
      const edited=updated.tasks.find(card=>card.id===task.id);
      onChange(edited.dependencies||[]);
      setError('');setSelected('');
    }catch(e){setError(e.message);}
  };
  return <section className="edit-section" aria-label="پیش‌نیازهای کارت" dir="rtl">
    <h3>پیش‌نیازها و موانع انجام</h3>
    {status.invalid&&<p role="alert" className="warning">ساختار پیش‌نیاز نامعتبر است: {status.invalid}</p>}
    {!status.invalid&&<p role="status" className={status.blocked?'warning':''}>
      {status.blocked?`${status.blockingIds.length.toLocaleString('fa-IR')} کار پیش‌نیاز هنوز کامل نشده است.`:'پیش‌نیاز ناتمام وجود ندارد.'}
    </p>}
    <ul>{current.map(id=><li key={id}>
      <span>{byId.get(id)?.title||'پیش‌نیاز ناموجود'} {status.blockingIds.includes(id)?' · مانع انجام':' · تکمیل‌شده'}</span>
      {canEdit&&!status.invalid&&<button type="button" aria-label={'حذف پیش‌نیاز '+(byId.get(id)?.title||id)} onClick={()=>apply(id,false)}>حذف ارتباط</button>}
    </li>)}</ul>
    {!current.length&&<small>این کارت پیش‌نیازی ندارد.</small>}
    {canEdit&&!status.invalid&&<div className="inline-create">
      <select aria-label="کارت پیش‌نیاز جدید" value={selected} onChange={e=>setSelected(e.target.value)}>
        <option value="">انتخاب پیش‌نیاز از همین پروژه</option>
        {candidates.map(card=><option key={card.id} value={card.id}>{card.title||card.id}</option>)}
      </select>
      <button type="button" disabled={!selected} onClick={()=>apply(selected,true)}>افزودن پیش‌نیاز</button>
    </div>}
    {error&&<p className="warning" role="alert">تغییر پیش‌نیاز انجام نشد: {error}</p>}
    <small>وابستگی فقط ترتیب منطقی کارها را مشخص می‌کند و موعد، مبلغ یا وضعیت را خودکار تغییر نمی‌دهد.</small>
  </section>;
}
