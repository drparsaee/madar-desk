import React, {useEffect, useRef, useState} from 'react';
import {CalendarRange, Eye, FileText, RefreshCw, ShieldCheck, Wallet, X} from 'lucide-react';
import {CalendarField,displayDate} from './productivity.jsx';
import './financeoverview.css';

const money=value=>Number(value||0).toLocaleString('fa-IR')+' تومان';
const eventId=()=>('ui-receipt-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
const localToday=()=>{const now=new Date();return [now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');};
const latin=value=>String(value??'').replace(/[۰-۹]/g,c=>String(c.charCodeAt(0)-1776)).replace(/[٠-٩]/g,c=>String(c.charCodeAt(0)-1632));
const amount=value=>{
  const digits=latin(value).replace(/[\s,،]/g,'');
  if(!/^(0|[1-9][0-9]*)$/.test(digits)||!Number.isSafeInteger(Number(digits)))return null;
  return Number(digits);
};

export function ProfitPeek({api,projectId=''}) {
  const [result,setResult]=useState(null),[error,setError]=useState('');
  useEffect(()=>{
    let live=true;
    setResult(null);setError('');
    Promise.resolve().then(()=>api.financeOverview(projectId,'','')).then(data=>{if(live)setResult(data);}).catch(e=>{if(live)setError(e.message||String(e));});
    return()=>{live=false;};
  },[api,projectId]);
  return <div className="private-profit" role="status">
    <ShieldCheck size={17}/>
    {error?<span>دریافت اطلاعات مالی: {error}</span>:!result?<span>در حال خواندن سود از سرور...</span>:<>
      <span>دریافتی: <strong>{money(result.receivedTotal)}</strong></span>
      <span>هزینه: <strong>{money(result.expenseTotal)}</strong></span>
      <span className={result.profit<0?'profit-negative':'profit-positive'}>سود / زیان: <strong>{money(result.profit)}</strong></span>
    </>}
  </div>;
}

export function FinanceOverview({api,projects,calendar='jalali',initialProjectId='',onClose,onOpenInvoices}) {
  const [projectId,setProjectId]=useState(initialProjectId);
  const [startDate,setStartDate]=useState('');
  const [endDate,setEndDate]=useState('');
  const [summary,setSummary]=useState(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [amountText,setAmountText]=useState('');
  const [receiptProject,setReceiptProject]=useState(initialProjectId||projects[0]?.id||'');
  const [receivedAt,setReceivedAt]=useState(localToday);
  const [description,setDescription]=useState('');
  const [reload,setReload]=useState(0);
  const [notice,setNotice]=useState('');
  const pendingReceipt=useRef(null);

  useEffect(()=>{
    let live=true;
    setBusy(true);setSummary(null);setError('');
    Promise.resolve().then(()=>{
      if(typeof api.financeOverview!=='function')throw Error('گزارش مالی فقط در نسخه ویندوز به‌روز در دسترس است.');
      return api.financeOverview(projectId,startDate,endDate);
    }).then(data=>{if(live)setSummary(data);}).catch(e=>{if(live)setError(e.message||String(e));}).finally(()=>{if(live)setBusy(false);});
    return()=>{live=false;};
  },[api,projectId,startDate,endDate,reload]);

  const saveReceipt=async e=>{
    e.preventDefault();
    const value=amount(amountText);
    if(!receiptProject||!value||!receivedAt){setError('پروژه، تاریخ و مبلغ دریافتی مثبت را وارد کنید.');return;}
    setBusy(true);setError('');setNotice('');
    try{
      // Preserve the date explicitly selected by the user across time zones.
      const receivedTimestamp=receivedAt+'T12:00:00Z';
      const normalizedDescription=description.trim();
      const fingerprint=JSON.stringify([receiptProject,value,receivedTimestamp,normalizedDescription]);
      if(pendingReceipt.current?.fingerprint!==fingerprint){
        pendingReceipt.current={fingerprint,eventId:eventId()};
      }
      await api.financeCommand({
        type:'project.receipt',eventId:pendingReceipt.current.eventId,projectId:receiptProject,
        amount:value,receivedAt:receivedTimestamp,
        description:normalizedDescription
      });
      pendingReceipt.current=null;
      setAmountText('');setDescription('');setNotice('مبلغ دریافتی ثبت شد.');setReload(i=>i+1);
    }catch(e){setError('ثبت دریافتی: '+(e.message||String(e))+'؛ برای تلاش مجدد همین اطلاعات را بدون تغییر ارسال کنید تا رکورد تکراری ایجاد نشود.');}
    finally{setBusy(false);}
  };
  const grouped=summary?.categories||[];
  const byProject=summary?.projects||[];
  const receipts=summary?.receipts||[];
  return <div className="finance-hub-backdrop" onMouseDown={onClose}>
    <section className="finance-hub" role="dialog" aria-modal="true" aria-label="مدیریت مالی" onMouseDown={e=>e.stopPropagation()}>
      <header className="finance-hub-head"><div><small><ShieldCheck size={14}/> دسترسی اختصاصی مدیر</small><h2><Wallet size={22}/> مدیریت مالی</h2></div><button type="button" onClick={onClose} aria-label="بستن"><X size={20}/></button></header>
      <div className="finance-hub-body">
        <div className="finance-hub-filters">
          <label>پروژه<select value={projectId} onChange={e=>setProjectId(e.target.value)}><option value="">تمام پروژه‌ها</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <CalendarField label="از تاریخ" calendar={calendar} value={startDate} onChange={setStartDate}/>
          <CalendarField label="تا تاریخ" calendar={calendar} value={endDate} onChange={setEndDate}/>
          <button type="button" disabled={busy} onClick={()=>setReload(i=>i+1)}><RefreshCw size={16}/> تازه‌سازی</button>
        </div>
        {error&&<p role="alert" className="finance-hub-error">{error}</p>}
        {notice&&<p role="status" className="finance-hub-notice">{notice}</p>}
        {busy&&!summary&&<p>در حال دریافت گزارش از میزبان...</p>}
        {summary&&<>
          <div className="finance-hub-cards">
            <article><small>مبلغ دریافتی ثبت‌شده</small><strong>{money(summary.receivedTotal)}</strong></article>
            <article><small>هزینه‌های ثبت‌شده</small><strong>{money(summary.expenseTotal)}</strong></article>
            <article className={summary.profit<0?'loss':'gain'}><small>سود / زیان محاسبه‌شده</small><strong>{money(summary.profit)}</strong></article>
          </div>
          <div className="finance-hub-sections">
            <section>
              <h3><CalendarRange size={18}/> هزینه به تفکیک دسته</h3>
              <div className="finance-hub-table"><div className="table-head"><span>دسته هزینه</span><span>تعداد</span><span>مبلغ</span></div>
                {grouped.map((category,i)=><div key={category.category+'-'+i}><span>{category.category}</span><span>{Number(category.count||0).toLocaleString('fa-IR')}</span><strong>{money(category.total)}</strong></div>)}
                {!grouped.length&&<p>در این بازه هزینه‌ای ثبت نشده است.</p>}
              </div>
            </section>
            <section>
              <h3><Wallet size={18}/> جمع پروژه‌ها</h3>
              <div className="finance-hub-projects">
                {byProject.map(p=><article key={p.projectId}><strong>{p.name}</strong><span>دریافتی: {money(p.receivedTotal)}</span><span>هزینه: {money(p.expenseTotal)}</span><b className={p.profit<0?'profit-negative':'profit-positive'}>سود / زیان: {money(p.profit)}</b>
                  {onOpenInvoices&&<button onClick={()=>onOpenInvoices(p.projectId)}><FileText size={15}/> قرارداد و فاکتور</button>}
                </article>)}
                {!byProject.length&&<p>پروژه‌ای در این گزارش وجود ندارد.</p>}
              </div>
            </section>
          </div>
        </>}
        <section className="finance-hub-receipt">
          <h3>ثبت مبلغ دریافتی واقعی</h3>
          <p>مبلغ قرارداد یا قیمت پروژه با وجه دریافت‌شده یکسان نیست. هر دریافت جداگانه ثبت می‌شود و در محاسبه سود لحاظ می‌شود.</p>
          <form onSubmit={saveReceipt}>
            <label>پروژه<select required value={receiptProject} onChange={e=>setReceiptProject(e.target.value)}>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
            <label>مبلغ به تومان<input required dir="ltr" inputMode="numeric" value={amountText} onChange={e=>setAmountText(e.target.value)} placeholder="2500000"/></label>
            <CalendarField label="تاریخ دریافت" calendar={calendar} value={receivedAt} onChange={setReceivedAt}/>
            <label>توضیح اختیاری<input maxLength={300} value={description} onChange={e=>setDescription(e.target.value)} placeholder="مثلاً قسط اول"/></label>
            <button type="submit" className="btn primary" disabled={busy||!projects.length}>ثبت دریافتی</button>
          </form>
          {!!receipts.length&&<div className="finance-hub-receipts">
            <h4>دریافت‌های ثبت‌شده در بازه انتخابی</h4>
            {receipts.slice().reverse().map(r=><div key={r.eventId}><span>{projects.find(p=>p.id===r.projectId)?.name||r.projectId} · {displayDate(r.receivedAt?.slice(0,10),calendar,true)} · {r.description||'بدون توضیح'}</span><strong>{money(r.amount)}</strong></div>)}
          </div>}
        </section>
        <p className="finance-hub-note">هزینه‌های فعلی از مبالغ ثبت‌شده روی کارت و مراحل محاسبه می‌شوند. فیلتر زمانی بر اساس تاریخ هزینه انتخاب‌شده است؛ برای داده‌های قدیمی فاقد تاریخ مستقل، تاریخ آخرین ویرایش کارت به کار می‌رود. این مبالغ سند بانکی پرداخت یا گزارش رسمی حسابداری محسوب نمی‌شوند. دریافت ثبت‌شده روی یک فاکتور را دوباره به‌عنوان دریافت مستقل وارد نکنید.</p>
      </div>
    </section>
  </div>;
}
