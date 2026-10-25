import React, {useEffect, useState} from 'react';
import {ReceiptText, RefreshCw, FilePlus2, ShieldCheck} from 'lucide-react';
import './financepanel.css';

const eventId=()=>('ui-finance-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
const textMoney=x=>Number(x||0).toLocaleString('fa-IR')+' تومان';

export function FinancePanel({project,tasks,api,onClose}){
  const [card,setCard]=useState(tasks[0]?.id||'');
  const [customer,setCustomer]=useState('');
  const [reference,setReference]=useState('');
  const [description,setDescription]=useState('');
  const [quantity,setQuantity]=useState('1');
  const [price,setPrice]=useState('');
  const [tax,setTax]=useState('0');
  const [discount,setDiscount]=useState('0');
  const [advance,setAdvance]=useState('0');
  const [auto,setAuto]=useState(true);
  const [invoices,setInvoices]=useState([]);
  const [status,setStatus]=useState(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const refresh=async()=>{setInvoices(await api.financeRead(project.id));setStatus(await api.financeStatus());};
  useEffect(()=>{refresh().catch(e=>setMessage('خواندن پرونده مالی: '+e.message));},[project.id]);
  const action=async payload=>{
    setBusy(true);setMessage('');
    try{const result=await api.financeCommand({eventId:eventId(),...payload});await refresh();setMessage('در پرونده مالی ثبت شد.');return result;}
    catch(e){setMessage(e.message||String(e));return null;}
    finally{setBusy(false);}
  };
  const isMoney=x=>/^(?:0|[1-9][0-9]*)$/.test(x)&&Number.isSafeInteger(Number(x));
  const saveContract=()=>{
    if(!card||!customer.trim()||!description.trim()||!Number.isSafeInteger(Number(quantity))||Number(quantity)<1||![price,tax,discount,advance].every(isMoney)){
      setMessage('نام مشتری، شرح، تعداد و مبالغ صحیح لازم است. مبلغ فروش را جدا از هزینه داخلی وارد کن.');return;
    }
    return action({type:'contract.set',cardId:card,sale:{
      customer:{name:customer.trim(),reference:reference.trim()},
      lines:[{id:'service',description:description.trim(),quantity:Number(quantity),unitPrice:Number(price)}],
      tax:Number(tax),discount:Number(discount),advance:Number(advance),autoInvoice:auto
    }});
  };
  return <div className="finance-backdrop" onMouseDown={onClose}>
    <section className="finance-dialog" role="dialog" aria-modal="true" aria-label="حسابداری و پیش‌فاکتور" onMouseDown={e=>e.stopPropagation()}>
      <header><strong><ReceiptText size={19}/> پرونده مالی: {project.name}</strong><button onClick={onClose} aria-label="بستن">×</button></header>
      <div className="finance-content">
        <p className="finance-info"><ShieldCheck size={17}/> مبالغ به تومان هستند. هزینه داخلی مبنای قیمت فروش نیست. پایان کارت فقط پیش‌نویس فاکتور ایجاد می‌کند؛ صدور شماره‌دار نیازمند تأیید مدیر است.</p>
        <div className="finance-form">
          <h3><FilePlus2 size={16}/> تعریف قرارداد فروش برای یک کارت</h3>
          <label>کارت<select value={card} onChange={e=>setCard(e.target.value)}>{tasks.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
          <label>مشتری<input value={customer} onChange={e=>setCustomer(e.target.value)} placeholder="نام واقعی مشتری"/></label>
          <label>شناسه مشتری (اختیاری)<input value={reference} onChange={e=>setReference(e.target.value)}/></label>
          <label>شرح خدمت<input value={description} onChange={e=>setDescription(e.target.value)}/></label>
          <div className="finance-form-cols">
            <label>تعداد<input type="number" min="1" step="1" value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>
            <label>قیمت واحد<input dir="ltr" type="number" min="0" step="1" value={price} onChange={e=>setPrice(e.target.value)}/></label>
            <label>تخفیف<input dir="ltr" type="number" min="0" step="1" value={discount} onChange={e=>setDiscount(e.target.value)}/></label>
            <label>مالیات (مبلغ صریح)<input dir="ltr" type="number" min="0" step="1" value={tax} onChange={e=>setTax(e.target.value)}/></label>
            <label>پیش‌پرداخت<input dir="ltr" type="number" min="0" step="1" value={advance} onChange={e=>setAdvance(e.target.value)}/></label>
          </div>
          <label className="finance-check"><input type="checkbox" checked={auto} onChange={e=>setAuto(e.target.checked)}/> ایجاد پیش‌نویس خودکار پس از تکمیل کارت</label>
          <button className="btn primary" disabled={busy} onClick={saveContract}>ثبت قرارداد و قیمت توافقی</button>
        </div>
        <div className="finance-list">
          <header><strong>فاکتورها و پیش‌نویس‌ها ({invoices.length})</strong><button disabled={busy} onClick={()=>refresh().catch(e=>setMessage(e.message))}><RefreshCw size={15}/> تازه‌سازی</button></header>
          {invoices.map(item=><div className="finance-invoice" key={item.id}>
            <div><strong>{item.sale.customer.name} | {item.status}</strong><small>کارت: {tasks.find(t=>t.id===item.cardId)?.title||item.cardId} | شماره: {item.number||'هنوز صادر نشده'}</small><span>{textMoney(item.sale.total)}</span></div>
            <div className="finance-actions">
              {item.status==='Draft'&&<button disabled={busy} onClick={()=>action({type:'invoice.review',invoiceId:item.id})}>ارسال برای بررسی</button>}
              {item.status==='Review'&&<button disabled={busy} onClick={()=>{if(window.confirm('این پیش‌نویس با شماره مالی جدید صادر شود؟'))action({type:'invoice.issue',invoiceId:item.id});}}>صدور با شماره</button>}
              {['Draft','Review','Issued'].includes(item.status)&&<button disabled={busy} onClick={()=>{const reason=window.prompt('دلیل ابطال');if(reason?.trim())action({type:'invoice.cancel',invoiceId:item.id,reason:reason.trim()});}}>ابطال</button>}
            </div>
          </div>)}
          {!invoices.length&&<p>هنوز فاکتوری ثبت نشده است. ابتدا قرارداد فروش را برای یک کارت تعریف کن و کارت را تکمیل کن.</p>}
        </div>
        {!!status?.pending&&<p className="finance-warning">رویداد مالی در انتظار پردازش: {status.pending} | {status.warning||'در صورت قطع برنامه دوباره پردازش خواهد شد.'}</p>}
        {message&&<p className="finance-message" role="status">{message}</p>}
      </div>
    </section>
  </div>;
}
