import React,{useEffect,useMemo,useRef,useState} from 'react';
import {FilePlus2,ReceiptText,RefreshCcw,ShieldCheck,X} from 'lucide-react';
import './accounting_panel.css';

const newEvent=()=>('accounting-ui-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
const MAX_TOMAN=10**15;
const MAX_QTY=100000;
const ID_PATTERN=/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/;
export const parseAccountingAmount=value=>{
  if(typeof value!=='string'&&typeof value!=='number')return null;
  const ascii=String(value).trim()
    .replace(/[۰-۹]/g,c=>String(c.charCodeAt(0)-1776))
    .replace(/[٠-٩]/g,c=>String(c.charCodeAt(0)-1632))
    .replace(/٬/g,',');
  if(!/^(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)$/.test(ascii))return null;
  const number=Number(ascii.replace(/,/g,''));
  return Number.isSafeInteger(number)&&number<=MAX_TOMAN?number:null;
};
const integer=parseAccountingAmount;
const money=value=>Number.isSafeInteger(value)&&value>=0?value.toLocaleString('fa-IR')+' تومان':'نامشخص';
const text=value=>typeof value==='string'?value.trim():'';
const localToday=()=>{
  const d=new Date();
  return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
};
export const validPostingDate=(day,today=localToday())=>{
  if(typeof day!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(day)||day>today)return false;
  const parts=day.split('-').map(Number);
  const utc=new Date(Date.UTC(parts[0],parts[1]-1,parts[2]));
  return utc.getUTCFullYear()===parts[0]&&utc.getUTCMonth()===parts[1]-1&&utc.getUTCDate()===parts[2];
};
export const validateSaleInput=({quantity,unitPrice,discount,tax,advance,description})=>{
  const numbers=[quantity,unitPrice,discount,tax,advance].map(integer);
  const [count,unit,deduction,taxValue,advanceValue]=numbers;
  if(!text(description)||text(description).length>300)return {error:'شرح فروش (حداکثر ۳۰۰ نویسه) الزامی است.'};
  if(numbers.some(n=>n===null)||!count||count>MAX_QTY||!unit)
    return {error:'تعداد باید بین ۱ تا ۱۰۰٬۰۰۰ و قیمت واحد باید مثبت باشد؛ مبالغ را به تومان وارد کنید.'};
  const subtotal=BigInt(count)*BigInt(unit);
  if(subtotal>BigInt(MAX_TOMAN)||BigInt(deduction)>subtotal)
    return {error:'جمع فروش از سقف مجاز بیشتر است یا تخفیف از مبلغ فروش تجاوز می‌کند.'};
  const total=subtotal-BigInt(deduction)+BigInt(taxValue);
  if(total<=0n||total>BigInt(MAX_TOMAN)||BigInt(advanceValue)>total)
    return {error:'مبلغ نهایی باید مثبت و در محدوده مجاز باشد؛ پیش‌دریافت نمی‌تواند از مبلغ نهایی بیشتر باشد.'};
  return {error:'',values:{count,unit,discountValue:deduction,taxValue,advanceValue,total:Number(total)}};
};
export const activeExpenseSources=(expenseSources,cardId,basis)=>{
  if(!Array.isArray(expenseSources)||!cardId||!['actual','estimated'].includes(basis))return [];
  return expenseSources.filter(s=>s&&s.cardId===cardId&&typeof s.sourceId==='string'&&s.sourceId&&
    Number.isSafeInteger(s[basis])&&s[basis]>0&&s[basis]<=MAX_TOMAN)
    .map(s=>({id:s.sourceId,label:text(s.description)||s.sourceId,
      estimated:s.estimated,actual:s.actual,amount:s[basis]}));
};
export const outstandingDocuments=(documents,projectId)=>{
  if(!Array.isArray(documents)||!projectId)return [];
  return documents.filter(d=>d&&d.projectId===projectId&&d.status==='Issued'&&
    ['sales','purchase'].includes(d.kind)&&ID_PATTERN.test(d.id||'')&&
    ID_PATTERN.test(d.party?.id||'')&&Number.isSafeInteger(d.total)&&
    Number.isSafeInteger(d.allocated)&&d.total>0&&d.allocated>=0&&d.total>d.allocated);
};
export const validateSettlement=(target,amount,postingDate,today=localToday())=>{
  if(!target)return {error:'ابتدا یک فاکتور صادرشده با مانده مثبت را انتخاب کنید.'};
  const value=integer(amount);
  if(!value||value>target.total-target.allocated)return {error:'مبلغ تسویه باید مثبت و حداکثر برابر مانده همان فاکتور باشد.'};
  if(!validPostingDate(postingDate,today)||postingDate<target.postingDate)
    return {error:'تاریخ تسویه باید معتبر، غیرآینده و برابر یا پس از تاریخ صدور سند باشد.'};
  return {error:'',amount:value};
};

/** Project-accounting UI. Data mutation is always through authoritative host APIs.
 * Caller must keep this panel admin-only and the server MUST check ACL again.
 */
export function AccountingPanel({api,projects=[],tasks=[],canManage=false,onClose=()=>{},initialProjectId=''}) {
  const [projectId,setProjectId]=useState(initialProjectId||projects[0]?.id||'');
  const [kind,setKind]=useState('sales');
  const [cardId,setCardId]=useState('');
  const [partyName,setPartyName]=useState('');
  const [partyId,setPartyId]=useState('');
  const [reference,setReference]=useState('');
  const [description,setDescription]=useState('');
  const [quantity,setQuantity]=useState('1');
  const [unitPrice,setUnitPrice]=useState('');
  const [discount,setDiscount]=useState('0');
  const [tax,setTax]=useState('0');
  const [advance,setAdvance]=useState('0');
  const [sourceId,setSourceId]=useState('direct');
  const [basis,setBasis]=useState('actual');
  const [approveEstimate,setApproveEstimate]=useState(false);
  const [paymentFor,setPaymentFor]=useState('');
  const [paymentAmount,setPaymentAmount]=useState('');
  const [liquidAccount,setLiquidAccount]=useState('1010');
  const [postingDate,setPostingDate]=useState(()=>new Date().toISOString().slice(0,10));
  const [fundingAmount,setFundingAmount]=useState('');
  const [fundingNote,setFundingNote]=useState('');
  const [data,setData]=useState({documents:[],balances:[]});
  const [loadedProjectId,setLoadedProjectId]=useState('');
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [refresh,setRefresh]=useState(0);
  const pending=useRef(null);
  const inFlight=useRef(false);
  const panelRef=useRef(null);
  const closeRef=useRef(null);
  const previousFocus=useRef(null);
  const latestOnClose=useRef(onClose);
  latestOnClose.current=onClose;
  const projectTasks=useMemo(()=>tasks.filter(t=>t.projectId===projectId&&t.deleted!==true),[tasks,projectId]);
  const selected=projectTasks.find(t=>t.id===cardId)||projectTasks[0];
  const readReady=loadedProjectId===projectId&&!loading;
  const expenseSources=useMemo(()=>readReady?activeExpenseSources(data?.expenseSources,selected?.id,basis):[],
    [readReady,data,selected?.id,basis]);
  const selectedSource=expenseSources.find(s=>s.id===sourceId);
  const issuedDocuments=useMemo(()=>readReady?outstandingDocuments(data?.documents,projectId):[],
    [readReady,data,projectId]);
  const paymentTarget=issuedDocuments.find(d=>d.id===paymentFor);
  const salesValidation=validateSaleInput({quantity,unitPrice,discount,tax,advance,description});
  const settlementValidation=validateSettlement(paymentTarget,paymentAmount,postingDate);
  const hasSelectedCost=!!selectedSource&&selectedSource.amount>0;
  const handleClose=()=>{if(!busy&&!inFlight.current)onClose();};

  useEffect(()=>{
    previousFocus.current=typeof document!=='undefined'?document.activeElement:null;
    closeRef.current?.focus();
    const onKeyDown=event=>{
      if(event.key==='Escape'){event.preventDefault();if(!inFlight.current)latestOnClose.current();return;}
      if(event.key!=='Tab'||!panelRef.current)return;
      const elements=[...panelRef.current.querySelectorAll(
        'button:not([disabled]),[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
      )].filter(element=>element.getClientRects().length>0);
      if(!elements.length)return;
      const first=elements[0],last=elements[elements.length-1];
      if(!panelRef.current.contains(document.activeElement)){event.preventDefault();first.focus();}
      else if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    };
    if(typeof document!=='undefined')document.addEventListener('keydown',onKeyDown);
    return()=>{
      if(typeof document!=='undefined')document.removeEventListener('keydown',onKeyDown);
      previousFocus.current?.focus?.();
    };
  },[]);

  useEffect(()=>{
    let live=true;
    if(!canManage||!projectId){setLoadedProjectId('');setLoading(false);return()=>{};}
    setLoading(true);
    setLoadedProjectId('');
    setError('');
    Promise.resolve().then(()=>{
      if(typeof api.accountingRead!=='function')throw Error('هسته حسابداری در نسخه اجرایی فعلی متصل نیست.');
      return api.accountingRead(projectId);
    }).then(value=>{
      if(!live)return;
      if(!value||!Array.isArray(value.documents)||!Array.isArray(value.balances)||
         !Array.isArray(value.expenseSources))throw Error('پاسخ حسابداری ناقص است؛ عملیات متوقف شد.');
      setData(value);
      setLoadedProjectId(projectId);
    }).catch(e=>{if(live){setLoadedProjectId('');setError(e.message||String(e));}})
      .finally(()=>{if(live)setLoading(false);});
    return()=>{live=false;};
  },[api,canManage,projectId,refresh]);

  const action=async command=>{
    if(inFlight.current)return false;
    if(!canManage||!readReady||typeof api.accountingCommand!=='function'){
      setError('اطلاعات به‌روز حسابداری یا مجوز میزبان در دسترس نیست.');return false;
    }
    const identity=JSON.stringify(command);
    if(pending.current?.identity!==identity)pending.current={identity,eventId:newEvent()};
    inFlight.current=true;
    setBusy(true);setError('');setNotice('');
    try{
      const id=pending.current.eventId;
      const recordId=command.type==='receipt.record'?{receiptId:id}:
                     command.type==='payment.record'?{paymentId:id}:{};
      await api.accountingCommand({...command,...recordId,eventId:id});
      pending.current=null;
      setLoadedProjectId('');
      setNotice('دستور در میزبان ثبت شد؛ برای مشاهده مانده جدید، داده‌ها دوباره دریافت می‌شوند.');
      setRefresh(n=>n+1);
      return true;
    }catch(e){
      setError((e.message||String(e))+'؛ برای تلاش مجدد همان اطلاعات را حفظ کنید تا سند تکراری ساخته نشود.');
      return false;
    }finally{inFlight.current=false;setBusy(false);}
  };
  const create=event=>{
    event.preventDefault();
    if(!readReady||!selected||!partyName.trim()||!projectId||
       !ID_PATTERN.test(text(partyId))||text(partyName).length>200){
      setError('پروژه و تسک معتبر، نام طرف حساب و شناسه انگلیسی (۱ تا ۹۶ نویسه) الزامی است.');return;
    }
    if(reference.length>100||/[\x00-\x1f\x7f]/.test(reference)){
      setError('شناسه مرجع حداکثر ۱۰۰ نویسه و بدون نویسه کنترلی باشد.');return;
    }
    const party={id:text(partyId),name:text(partyName),reference:text(reference),
                 kind:kind==='sales'?'customer':'supplier'};
    if(kind==='sales'){
      if(salesValidation.error){setError(salesValidation.error);return;}
      const {count,unit,discountValue,taxValue,advanceValue}=salesValidation.values;
      action({type:'draft.sales.fromTask',projectId,cardId:selected.id,party,
              lines:[{id:'service',description:text(description),quantity:count,unitPrice:unit}],
              discount:discountValue,tax:taxValue,advance:advanceValue});
    }else{
      if(basis==='estimated'&&!approveEstimate){setError('برای استفاده از هزینه برآوردی، تأیید صریح لازم است.');return;}
      if(!hasSelectedCost){setError('یک منبع هزینه معتبر با مبلغ مثبت انتخاب کنید؛ ابتدا هزینه را در تسک ثبت و تازه‌سازی کنید.');return;}
      const sourceId=selectedSource.id;
      action({type:'draft.purchase.fromCosts',projectId,party,basis,
              approveEstimate:approveEstimate,
              selections:[{cardId:selected.id,sourceId}]});
    }
  };
  const settle=event=>{
    event.preventDefault();
    if(!readReady||settlementValidation.error){
      setError(!readReady?'ابتدا اطلاعات تازه حسابداری را دریافت کنید.':settlementValidation.error);return;
    }
    const paid=settlementValidation.amount;
    const sales=paymentTarget.kind==='sales';
    const summary=[sales?'دریافت واقعی از مشتری':'پرداخت واقعی به تأمین‌کننده',
      paymentTarget.party?.name||paymentTarget.party?.id,
      paymentTarget.number||paymentTarget.id,money(paid)].join(' | ');
    if(!window.confirm(summary+'\nاطلاعات با سند بانکی یا صندوق مطابقت دارد و ثبت شود؟'))return;
    action({type:sales?'receipt.record':'payment.record',
            partyId:paymentTarget.party.id,accountId:liquidAccount,postingDate,
            allocations:[sales?{invoiceId:paymentTarget.id,amount:paid}:
                        {billId:paymentTarget.id,amount:paid}]}).then(ok=>{
                          if(ok){setPaymentFor('');setPaymentAmount('');}
                        });
  };
  const fund=event=>{
    event.preventDefault();
    const value=integer(fundingAmount);
    if(!value||!readReady){setError('مبلغ مثبت ورود وجه و اطلاعات به‌روز حسابداری الزامی‌اند.');return;}
    if(!fundingNote.trim()){setError('منبع واقعی تأمین وجه را بنویسید.');return;}
    if(!validPostingDate(postingDate)){setError('تاریخ معتبر و غیرآینده انتخاب کنید.');return;}
    if(fundingNote.trim().length>1000){setError('شرح منبع وجه حداکثر ۱۰۰۰ نویسه باشد.');return;}
    if(!window.confirm('آیا این مبلغ واقعاً وارد صندوق یا بانک شده است؟ این کار یک سند حسابداری ایجاد می‌کند.'))return;
    action({type:'funds.deposit',accountId:liquidAccount,amount:value,
            postingDate,note:fundingNote.trim()}).then(ok=>{
              if(ok){setFundingAmount('');setFundingNote('');}
            });
  };

  if(!canManage)return <section role="alert">مشاهده و ثبت حسابداری فقط برای مدیر مالی مجاز است.</section>;
  return <div className="accounting-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget)handleClose();}}>
    <section ref={panelRef} className="accounting-panel" role="dialog" aria-modal="true" aria-labelledby="accounting-title" aria-describedby="accounting-guidance" onMouseDown={event=>event.stopPropagation()} dir="rtl">
      <header className="accounting-header">
        <h2 id="accounting-title"><ReceiptText size={20} aria-hidden="true"/> حسابداری مدار</h2>
        <button ref={closeRef} type="button" onClick={handleClose} disabled={busy} aria-label="بستن حسابداری"><X size={20} aria-hidden="true"/></button>
      </header>
      <p id="accounting-guidance" className="accounting-caution"><ShieldCheck size={16} aria-hidden="true"/> فاکتور فروش از مبلغی که برای این فاکتور وارد می‌کنید و فاکتور خرید از هزینه معتبر تسک ساخته می‌شود. پیش‌نویس، سند قطعی یا رسید پرداخت نیست؛ صدور و ثبت وجه نیاز به تأیید جداگانه دارد.</p>
      {loading&&<p className="accounting-loading" role="status">در حال دریافت اطلاعات این پروژه…</p>}
      {!loading&&!readReady&&<p className="accounting-error" role="alert">اطلاعات حسابداری این پروژه هنوز آماده نیست. برای تلاش مجدد، «تازه‌سازی» را بزنید.</p>}
      <div className="accounting-layout">
        <form onSubmit={create} className="accounting-form" aria-label="فرم پیش‌نویس فاکتور">
          <h3><FilePlus2 size={17}/> ایجاد پیش‌نویس</h3>
          <label>پروژه<select required value={projectId} onChange={e=>{setProjectId(e.target.value);setCardId('');setSourceId('');setPaymentFor('');setPaymentAmount('');setError('');setNotice('');}}>{projects.map(p=><option value={p.id} key={p.id}>{p.name}</option>)}</select></label>
          <label>نوع فاکتور<select value={kind} onChange={e=>{setKind(e.target.value);setError('');setSourceId('');}}><option value="sales">فروش به شخص</option><option value="purchase">خرید از تأمین‌کننده</option></select></label>
          <label>تسک<select required value={selected?.id||''} onChange={e=>{setCardId(e.target.value);setSourceId('');setError('');}} disabled={!projectTasks.length}><option value="" disabled>یک تسک انتخاب کنید</option>{projectTasks.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
          <label>{kind==='sales'?'نام شخص / مشتری':'نام تأمین‌کننده'}<input required maxLength={200} autoComplete="off" value={partyName} onChange={e=>setPartyName(e.target.value)}/></label>
          <label>شناسه طرف حساب<input required maxLength={96} dir="ltr" autoComplete="off" aria-invalid={!!partyId&&!ID_PATTERN.test(text(partyId))} value={partyId} onChange={e=>setPartyId(e.target.value)} placeholder="customer-01"/></label>
          <label>کد یا شناسه مرجع (اختیاری)<input maxLength={100} value={reference} onChange={e=>setReference(e.target.value)}/></label>
          {kind==='sales'?<>
            <label>شرح فروش<input required maxLength={300} value={description} onChange={e=>setDescription(e.target.value)}/></label>
            <div className="accounting-numbers">
              <label>تعداد<input type="text" inputMode="numeric" dir="ltr" required value={quantity} aria-invalid={integer(quantity)===null||integer(quantity)<1||integer(quantity)>MAX_QTY} onChange={e=>setQuantity(e.target.value)}/></label>
              <label>قیمت واحد (تومان)<input type="text" inputMode="numeric" dir="ltr" required value={unitPrice} aria-invalid={integer(unitPrice)===null||integer(unitPrice)<1} onChange={e=>setUnitPrice(e.target.value)}/></label>
              <label>تخفیف<input type="text" inputMode="numeric" dir="ltr" value={discount} aria-invalid={integer(discount)===null} onChange={e=>setDiscount(e.target.value)}/></label>
              <label>مالیات، مبلغ صریح<input type="text" inputMode="numeric" dir="ltr" value={tax} aria-invalid={integer(tax)===null} onChange={e=>setTax(e.target.value)}/></label>
              <label>پیش‌دریافت اعلامی<input type="text" inputMode="numeric" dir="ltr" value={advance} aria-invalid={integer(advance)===null} onChange={e=>setAdvance(e.target.value)}/></label>
            </div>
            <p className="accounting-help">مبالغ صحیح به تومان و بدون اعشار هستند؛ رقم فارسی و جداکننده هزارگان پذیرفته می‌شود. پیش‌دریافت این فاکتور، رسید بانکی یا تسویه ثبت‌شده نیست.</p>
            {description&&unitPrice&&salesValidation.error&&<p className="accounting-field-error" role="status">{salesValidation.error}</p>}
            {!salesValidation.error&&<p className="accounting-summary" role="status">جمع فاکتور: {money(salesValidation.values.total)}</p>}
          </>:<>
            <label>مبنای مبلغ<select value={basis} onChange={e=>{setBasis(e.target.value);setSourceId('');setApproveEstimate(false);}}><option value="actual">هزینه واقعی ثبت‌شده</option><option value="estimated">هزینه برآوردی با تأیید</option></select></label>
            <label>هزینه انتخابی<select required value={selectedSource?.id||''} onChange={e=>setSourceId(e.target.value)} disabled={!expenseSources.length||!readReady}><option value="">منبع هزینه را انتخاب کنید</option>{expenseSources.map(s=><option key={s.id} value={s.id}>{s.label} | برآورد {money(s.estimated)} | واقعی {money(s.actual)}</option>)}</select></label>
            {readReady&&!expenseSources.length&&<p className="accounting-field-error" role="status">برای این تسک در مبنای انتخابی، هزینه مثبت قابل صدور پیدا نشد. ابتدا آن را در تسک ثبت کنید.</p>}
            {selectedSource&&<p className="accounting-summary" role="status">مبلغ منبع انتخابی: {money(selectedSource.amount)}. این مبلغ هنوز پرداخت نشده است.</p>}
            {basis==='estimated'&&<label className="accounting-confirm"><input type="checkbox" checked={approveEstimate} onChange={e=>setApproveEstimate(e.target.checked)}/> تأیید می‌کنم این مبلغ صرفاً برآورد بوده و باید قبل از صدور نهایی کنترل شود.</label>}
          </>}
          <button className="btn primary" type="submit" disabled={busy||!readReady||!selected||(kind==='purchase'&&!hasSelectedCost)||(kind==='sales'&&!!salesValidation.error)}>ثبت پیش‌نویس بدون صدور قطعی</button>
        </form>
        <section className="accounting-list">
          <header><h3>فاکتورها و طرف‌حساب‌ها</h3><button type="button" onClick={()=>setRefresh(n=>n+1)} disabled={busy||loading}><RefreshCcw size={15} aria-hidden="true"/> تازه‌سازی</button></header>
          {readReady&&(data?.balances||[]).map(b=><article key={b.partyId} className="accounting-balance"><strong>{b.name||b.partyId}</strong><span>طلب از مشتری: {money(b.receivable)}</span><span>بدهی به تأمین‌کننده: {money(b.payable)}</span></article>)}
          {readReady&&(data?.documents||[]).filter(d=>d.projectId===projectId).map(d=><article key={d.id} className="accounting-document">
            <strong>{d.kind==='purchase'?'خرید':'فروش'} | {d.party?.name||d.partyId||'بدون نام'} | {d.status}</strong>
            <span>{money(d.total)} | شماره {d.number||'صادر نشده'}</span>
            {Number.isSafeInteger(d.total)&&Number.isSafeInteger(d.allocated)&&<span>مانده فاکتور: {money(Math.max(0,d.total-d.allocated))}</span>}
            {d.status==='Draft'&&<button type="button" disabled={busy} onClick={()=>action({type:'document.review',projectId:d.projectId,documentId:d.id})}>تأیید برای بررسی</button>}
            {d.status==='Review'&&<button type="button" disabled={busy} onClick={()=>{
              if(!validPostingDate(postingDate)){setError('تاریخ صدور معتبر و غیرآینده انتخاب کنید.');return;}
              if(window.confirm('سند حسابداری قطعی و شماره‌گذاری شود؟'))action({type:'document.issue',projectId:d.projectId,documentId:d.id,postingDate});
            }}>صدور قطعی</button>}
            {['Draft','Review'].includes(d.status)&&<button type="button" disabled={busy} onClick={()=>{const reason=window.prompt('دلیل ابطال پیش‌نویس');if(reason?.trim())action({type:'document.cancel',projectId:d.projectId,documentId:d.id,reason:reason.trim()});}}>ابطال پیش‌نویس</button>}
          </article>)}
          {readReady&&!(data?.documents||[]).some(d=>d.projectId===projectId)&&<p>هنوز سندی در این پروژه ثبت نشده است.</p>}
          <p className="accounting-caution">مانده طرف‌حساب و تراز حساب‌ها در سطح کل دفتر حسابداری است؛ ممکن است شامل پروژه‌های دیگر نیز باشد.</p>
          <form className="accounting-form accounting-subform" aria-label="ثبت دریافت یا پرداخت واقعی" onSubmit={settle}>
            <h3>ثبت دریافت از مشتری / پرداخت به تأمین‌کننده</h3>
            <p className="accounting-help">برای جلوگیری از ثبت دریافت یا پرداخت روی سند اشتباه، انتخاب فاکتور باید صریح باشد. ثبت این فرم مستقل از صدور فاکتور است.</p>
            <label>فاکتور صادرشده دارای مانده<select required value={paymentTarget?.id||''} onChange={e=>{setPaymentFor(e.target.value);setPaymentAmount('');}} disabled={!issuedDocuments.length||busy}><option value="">فاکتور موردنظر را انتخاب کنید</option>{issuedDocuments.map(d=><option key={d.id} value={d.id}>{d.kind==='sales'?'دریافت از مشتری':'پرداخت به تأمین‌کننده'} · {d.number||d.id} · {d.party?.name} · {money(d.total-d.allocated)}</option>)}</select></label>
            {readReady&&!issuedDocuments.length&&<p className="accounting-help">فاکتور صادرشده با مانده مثبت برای این پروژه وجود ندارد.</p>}
            {paymentTarget&&<p className="accounting-summary" role="status">{paymentTarget.kind==='sales'?'دریافت از مشتری':'پرداخت به تأمین‌کننده'}: {paymentTarget.party?.name} | مانده {money(paymentTarget.total-paymentTarget.allocated)}</p>}
            <label>مبلغ واقعی تسویه (تومان)<input type="text" inputMode="numeric" dir="ltr" required aria-invalid={paymentAmount!==''&&!!settlementValidation.error} value={paymentAmount} onChange={e=>setPaymentAmount(e.target.value)}/></label>
            <label>صندوق / بانک<select value={liquidAccount} onChange={e=>setLiquidAccount(e.target.value)}><option value="1010">بانک</option><option value="1000">صندوق</option></select></label>
            <label>تاریخ ثبت و صدور<input type="date" required max={localToday()} value={postingDate} aria-invalid={!validPostingDate(postingDate)} onChange={e=>setPostingDate(e.target.value)}/></label>
            {paymentAmount&&settlementValidation.error&&<p role="status" className="accounting-field-error">{settlementValidation.error}</p>}
            <button type="submit" className="btn primary" disabled={busy||!readReady||!!settlementValidation.error}>{paymentTarget?.kind==='purchase'?'ثبت پرداخت واقعی':'ثبت دریافت واقعی'}</button>
          </form>
          <form className="accounting-form accounting-subform" aria-label="ورود وجه واقعی" onSubmit={fund}>
            <h3>ثبت ورود واقعی وجه سرمایه اولیه</h3>
            <p>برای پرداخت خرید، صندوق یا بانک باید موجودی ثبت‌شده کافی داشته باشد. این بخش جایگزین بررسی حساب بانکی نیست.</p>
            <label>وجه واقعی (تومان)<input type="text" inputMode="numeric" dir="ltr" required value={fundingAmount} aria-invalid={fundingAmount!==''&&!integer(fundingAmount)} onChange={e=>setFundingAmount(e.target.value)}/></label>
            <label>شرح منبع وجه<input required maxLength={1000} value={fundingNote} onChange={e=>setFundingNote(e.target.value)} placeholder="مثلاً واریز شخص مالک"/></label>
            <button type="submit" disabled={busy||!readReady||!integer(fundingAmount)||!fundingNote.trim()||!validPostingDate(postingDate)}>ثبت سرمایه واقعی پس از تأیید</button>
          </form>
        </section>
      </div>
      <div className="accounting-feedback" aria-live="polite">
        {error&&<p role="alert" className="accounting-error">{error}</p>}
        {notice&&<p role="status" className="accounting-notice">{notice}</p>}
      </div>
    </section>
  </div>;
}
