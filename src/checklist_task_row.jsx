import React,{useState} from 'react';
import {Check,Clock3,Users,Wallet,Ellipsis,Trash2,HelpCircle} from 'lucide-react';
import {CalendarField,displayDate} from './productivity.jsx';
import {AssigneeSelector,AssignedMembers} from './members.jsx';
import {MoneyField,money} from './features.jsx';
import {StageExpenseFields} from './order_finance_fields.jsx';
import {removeUnpaidLegacyStep} from './checklistguard.js';
import './checklist_task_row.css';

const todayISO=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};

export function ChecklistTaskRow({task,step,users,calendar,canEdit,canManage,priceEnabled,
    accountView,onUpdate,onOpenPurchase}){
  const [menu,setMenu]=useState('');
  const [editing,setEditing]=useState(false);
  const [text,setText]=useState(step.text);
  const parties=Object.values(accountView?.parties||{});
  const vendors=parties.filter(p=>p.kind==='vendor'||p.kind==='both');
  const accountReady=Boolean(accountView);
  const assigned=Array.isArray(step.assignees)?step.assignees:[];
  const patch=changes=>{if(!canEdit)return;onUpdate({checklist:task.checklist.map(item=>item.id===step.id?{...item,...changes}:item)});};
  const finish=()=>{if(text.trim()&&text.trim()!==step.text)patch({text:text.trim()});else setText(step.text);setEditing(false);};
  const open=key=>setMenu(previous=>previous===key?'':key);
  const safeDelete=()=>{const result=removeUnpaidLegacyStep(task,step.id);if(result)onUpdate(result);};
  const paid=Number(step.cost||0)!==0||(step.expenseItems||[]).length>0;
  const canDelete=canEdit&&canManage&&!paid;
  return <div className="task-compact-step task-checklist-item" data-step-id={step.id}
    onKeyDown={event=>{if(event.key==='Escape'&&menu){event.stopPropagation();setMenu('');}}}>
    <div className="step-row task-checklist-item__row">
      <button type="button" className={'step-check '+(step.done?'checked':'')} disabled={!canEdit}
        aria-label={'تغییر وضعیت '+step.text} aria-pressed={Boolean(step.done)}
        onClick={()=>patch({done:!step.done})}>{step.done&&<Check size={14}/>}</button>
      {editing?<input className="task-checklist-item__title-input" aria-label={'ویرایش '+step.text}
          value={text} maxLength={5000} autoFocus onChange={e=>setText(e.target.value)} onBlur={finish}
          onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();finish();}if(e.key==='Escape'){e.stopPropagation();setText(step.text);setEditing(false);}}}/>
        :<button type="button" className={'task-checklist-item__title '+(step.done?'completed':'')}
          disabled={!canEdit} title="ویرایش عنوان" onClick={()=>{setText(step.text);setEditing(true);}}>{step.text}</button>}
      <div className="task-checklist-item__actions" role="group" aria-label={'گزینه‌های '+step.text}>
        {assigned.length>0&&<span className="task-checklist-item__avatars"><AssignedMembers assignees={assigned} users={users}/></span>}
        <button type="button" title="زمان انجام" aria-label={'زمان '+step.text} aria-expanded={menu==='date'}
          onClick={()=>open('date')}><Clock3 size={16}/>{step.dueDate&&<span className="task-checklist-item__dot"/>}</button>
        <button type="button" title="مسئول مرحله" aria-label={'مسئول '+step.text} aria-expanded={menu==='members'}
          onClick={()=>open('members')}><Users size={16}/></button>
        {canManage&&<button type="button" title="هزینه و طرف حساب" aria-label={'هزینه '+step.text}
          aria-expanded={menu==='cost'} onClick={()=>open('cost')}><Wallet size={16}/>{paid&&<span className="task-checklist-item__dot"/>}</button>}
        <button type="button" title="گزینه‌های بیشتر" aria-label={'بیشتر '+step.text} aria-expanded={menu==='more'}
          onClick={()=>open('more')}><Ellipsis size={17}/></button>
      </div>
    </div>
    {menu&&<div className="task-checklist-item__panel" role="group" aria-label={'ویرایش '+step.text}>
      {menu==='date'&&<>
        <CalendarField value={step.dueDate||''} calendar={calendar} disabled={!canEdit}
          label="موعد این مرحله" popupOnClick onChange={dueDate=>patch({dueDate})}/>
        {step.dueDate&&<small>{displayDate(step.dueDate,calendar,true)}</small>}
        {step.dueDate&&canEdit&&<button type="button" onClick={()=>patch({dueDate:''})}>حذف موعد</button>}
      </>}
      {menu==='members'&&<AssigneeSelector value={assigned} users={users} projectId={task.projectId}
        disabled={!canEdit} onChange={assignees=>patch({assignees})}/>}
      {menu==='cost'&&<div className="task-checklist-item__cost">
        {priceEnabled&&<div className="task-checklist-item__fields">
          <label>مبلغ هزینه (تومان)<MoneyField value={step.cost||0} disabled={!canEdit}
            label={'هزینه مرحله '+step.text} onChange={cost=>patch({cost,costDate:step.costDate||(cost?todayISO():'')})}/></label>
          <label>طرف حساب<select aria-label={'طرف حساب '+step.text} disabled={!canEdit||!accountReady}
              value={step.costPartyId||''} onChange={e=>patch({costPartyId:e.target.value})}>
              <option value="">انتخاب طرف حساب</option>
              {vendors.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
            </select></label>
          <label>دسته هزینه<input aria-label={'دسته هزینه مرحله '+step.text} maxLength={80}
              disabled={!canEdit} value={step.costCategory||''} onChange={e=>patch({costCategory:e.target.value})}/></label>
          <CalendarField value={step.costDate||''} calendar={calendar} disabled={!canEdit}
            label="تاریخ هزینه" onChange={costDate=>patch({costDate})}/>
        </div>}
        {!priceEnabled&&<small>هزینه مستقیم این کارت فعال نیست. ثبت هزینه مستقل از مسیر حسابداری امکان‌پذیر است.</small>}
        <details className="task-checklist-item__independent"><summary>هزینه مستقل و ارسال به حسابداری ({(step.expenseItems||[]).length})</summary>
          <StageExpenseFields task={task} step={step} parties={parties}
            existingJobs={accountView?.contractorJobs||{}} accountReady={accountReady}
            canEdit={canEdit} onUpdate={onUpdate} onPrepare={onOpenPurchase}/>
        </details>
        <details className="task-help"><summary title="تفاوت دو نوع هزینه" aria-label="راهنمای هزینه"><HelpCircle size={15}/></summary>
          <p>مبلغ مستقیم در گزارش هزینهٔ قدیمی کارت منظور می‌شود؛ انتخاب طرف حساب اینجا فقط اطلاعات همان مرحله است. برای ثبت عملیاتی نزد طرف حساب و ارسال به حسابداری، از «هزینه مستقل» استفاده کنید.</p>
        </details>
      </div>}
      {menu==='more'&&<div className="task-checklist-item__more">
        <button type="button" disabled={!canEdit} onClick={()=>{setText(step.text);setEditing(true);setMenu('');}}>ویرایش عنوان</button>
        <button type="button" disabled={!canDelete} title={paid?'مرحلهٔ دارای هزینه قابل حذف نیست':'حذف مرحله'}
          onClick={safeDelete}><Trash2 size={14}/> حذف مرحله</button>
        {paid&&<small>برای محافظت از سوابق مالی، مرحلهٔ دارای هزینه حذف نمی‌شود.</small>}
      </div>}
    </div>}
  </div>;
}
