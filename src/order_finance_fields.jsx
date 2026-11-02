import React,{useEffect,useState} from 'react';
import './order_finance_fields.css';

const secureSource=()=>{
  const uuid=globalThis.crypto?.randomUUID?.();
  if(!uuid)throw Error('شناسه امن برای قلم تجاری قابل تولید نیست.');
  return 'expense.'+uuid;
};
const parseInteger=(input,{allowNull=false,zero=false,max=1000000000000000}={})=>{
  if(allowNull&&input.trim()==='')return null;
  if(!/^(0|[1-9][0-9]*)$/.test(input.trim()))throw Error('عدد صحیح نامعتبر است.');
  const n=Number(input);
  if(!Number.isSafeInteger(n)||n>(max)||(!zero&&n<=0))throw Error('مبلغ یا تعداد خارج از محدوده است.');
  return n;
};

export function OrderSaleFields({task,api,onUpdate,onPrepare,canEdit,canManage}){
  const [parties,setParties]=useState([]);
  const [notice,setNotice]=useState('');
  const [quote,setQuote]=useState(null);
  const [quoteError,setQuoteError]=useState('');
  useEffect(()=>{
    if(!canManage)return;
    let active=true;
    api.standaloneAccountingRead().then(output=>{
      if(active)setParties(Object.values(output?.view?.parties||{}).filter(
        p=>p.kind==='customer'||p.kind==='both'));
    }).catch(err=>{if(active)setNotice(err.message);});
    return()=>{active=false;};
  },[api,canManage]);
  useEffect(()=>{
    let live=true;
    setQuote(null);setQuoteError('');
    const quantity=task.saleQuantity??1,unitPrice=task.saleUnitPrice??0;
    if(!canManage||unitPrice===0)return()=>{live=false;};
    if(typeof api?.standaloneAccountingQuote!=='function'){
      setQuoteError('محاسبه مبلغ در میزبان حسابداری فعال نیست.');
      return()=>{live=false;};
    }
    api.standaloneAccountingQuote({quantity,unitPrice,currency:task.saleCurrency||'TOMAN'})
      .then(result=>{
        if(!live)return;
        if(result?.status!=='quote-only'||typeof result.amount!=='string'||
           !/^[0-9]+$/.test(result.amount))throw Error('پاسخ محاسبه معتبر نیست.');
        setQuote(result);
      }).catch(error=>{if(live)setQuoteError(error?.message||'محاسبه رد شد.');});
    return()=>{live=false;};
  },[api,canManage,task.saleQuantity,task.saleUnitPrice,task.saleCurrency]);
  if(!canManage)return null;
  // A historical Toman amount is never silently reinterpreted as Rials.
  // Newly empty cards have no historical amount and may start in Rials.
  const legacySale=task.saleCurrency!=='RIAL'&&Number(task.saleUnitPrice||0)>0;
  return <div className="edit-section order-sale-fields"><h3>سفارش فروش / انتقال به حسابداری مستقل</h3>
    <div className="time-inputs">
      <label>نام سفارش‌دهنده (قابل نمایش به کارکنان)
        <input maxLength={300} value={task.orderCustomerName||''} disabled={!canEdit}
          onChange={e=>onUpdate({orderCustomerName:e.target.value})}/></label>
      <label>شناسه مشتری در حسابداری
        <select value={task.salePartyId||''} disabled={!canEdit}
          onChange={e=>{
            const party=parties.find(p=>p.id===e.target.value);
            onUpdate({salePartyId:e.target.value,...(party?{orderCustomerName:party.name}:{})});
          }}>
          <option value="">انتخاب مشتری ثبت‌شده</option>
          {parties.map(p=><option key={p.id} value={p.id}>{p.name} ({p.id})</option>)}
        </select></label>
      <label className="order-sale-fields__quantity">تعداد سفارش
        <input type="number" min="1" max="1000000" value={task.saleQuantity??1}
          disabled={!canEdit} onChange={e=>{
            const v=Number(e.target.value);
            if(Number.isSafeInteger(v)&&v>=1&&v<=1000000)onUpdate({saleQuantity:v});
          }}/></label>
      <label>{legacySale?'قیمت تاریخی (تومان، فقط خواندنی)':'قیمت واحد (ریال صحیح)'}
        <input inputMode="numeric" dir="ltr" value={String(task.saleUnitPrice??0)}
          disabled={!canEdit||legacySale} onChange={e=>{
            try{onUpdate({saleUnitPrice:parseInteger(e.target.value,{zero:true}),saleCurrency:'RIAL'});setNotice('');}
            catch(err){setNotice(err.message);}
          }}/></label>
    </div>
    {legacySale&&<small>مبلغ این سفارش تاریخی به تومان محفوظ است و در کارت به ریال تبدیل نمی‌شود.</small>}
    {!!quote&&<p role="status">جمع محاسبه‌شده توسط موتور حسابداری: <strong>
      {BigInt(quote.amount).toLocaleString('fa-IR')} {quote.currency==='RIAL'?'ریال':'تومان'}
      </strong> (پیش‌نمایش، هنوز فاکتوری صادر نشده است)</p>}
    {!!quoteError&&<p role="alert">{quoteError}</p>}
    <div className="form-footer">
      <button type="button" className="btn secondary" disabled={!task.salePartyId}
        onClick={()=>void onPrepare(task)}>ثبت فاکتور</button>
    </div>
    <small>صدور نهایی پس از بررسی و تأیید در حسابداری مستقل انجام می‌شود.</small>
    {!!notice&&<p role="alert">{notice}</p>}
  </div>;
}

export function StageExpenseFields({task,step,parties,onUpdate,onPrepare,canEdit,
    existingJobs={},accountReady=false}){
  const [draft,setDraft]=useState({partyId:'',description:'',quantity:'1',
    currency:'RIAL',unitPrice:''});
  const [error,setError]=useState('');
  const expenses=step.expenseItems||[];
  const save=updated=>onUpdate({checklist:task.checklist.map(s=>
    s.id===step.id?{...s,expenseItems:updated}:s)});
  const vendorList=parties.filter(p=>p.kind==='vendor'||p.kind==='both');
  return <div className="order-expense-list">
    {expenses.map(exp=><div key={exp.id} className="order-expense-item">
      <strong>{exp.description}</strong>
      <span>{vendorList.find(p=>p.id===exp.partyId)?.name||exp.partyId}</span>
      <span>{exp.quantity} × {exp.unitPrice===null?'در انتظار قیمت':
        (exp.currency==='TOMAN'?rialView(exp.unitPrice):String(exp.unitPrice))+' ریال'}</span>
      {existingJobs[exp.id]?<small>ثبت‌شده در حسابداری: {existingJobs[exp.id].status}</small>:
        <button type="button" disabled={!accountReady}
          onClick={()=>void onPrepare(task,exp)}>ارسال کار به حسابداری</button>}
      {!existingJobs[exp.id]&&<button type="button" disabled={!canEdit||!accountReady}
        onClick={()=>save(expenses.filter(x=>x.id!==exp.id))}>حذف قلم</button>}
    </div>)}
    {canEdit&&accountReady&&<div className="order-expense-item">
      <input aria-label={'شرح هزینه '+step.text} maxLength={300}
        placeholder="شرح قلم، مثل پیک" value={draft.description}
        onChange={e=>setDraft(p=>({...p,description:e.target.value}))}/>
      <select aria-label={'تأمین‌کننده '+step.text} value={draft.partyId}
        onChange={e=>setDraft(p=>({...p,partyId:e.target.value}))}>
        <option value="">انتخاب تأمین‌کننده</option>
        {vendorList.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <input aria-label={'تعداد '+step.text} dir="ltr" inputMode="numeric"
        placeholder="تعداد" value={draft.quantity}
        onChange={e=>setDraft(p=>({...p,quantity:e.target.value}))}/>
      <input aria-label={'قیمت واحد '+step.text} dir="ltr" inputMode="numeric"
        placeholder="قیمت نامشخص" value={draft.unitPrice}
        onChange={e=>setDraft(p=>({...p,unitPrice:e.target.value}))}/>
      <span>ریال</span>
      <button type="button" onClick={()=>{
        try{
          if(!draft.description.trim()||!draft.partyId||expenses.length>=50)
            throw Error('شرح، تأمین‌کننده و ظرفیت مرحله را بررسی کنید.');
          const quantity=parseInteger(draft.quantity,{max:1000000});
          const unitPrice=parseInteger(draft.unitPrice,{allowNull:true});
          save([...expenses,{id:secureSource(),partyId:draft.partyId,
            description:draft.description.trim(),quantity,unitPrice,currency:'RIAL'}]);
          setDraft({partyId:'',description:'',quantity:'1',currency:'RIAL',unitPrice:''});
          setError('');
        }catch(err){setError(err.message);}
      }}>افزودن هزینه مستقل</button>
    </div>}
    {!accountReady&&<small role="alert">پیش از ایجاد یا حذف اقلام مالی، اتصال امن حسابداری و فهرست طرف‌حساب‌ها باید دریافت شود.</small>}
    {!!error&&<small role="alert">{error}</small>}
  </div>;
}
