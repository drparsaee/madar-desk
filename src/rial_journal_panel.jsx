import React,{useEffect,useRef,useState} from 'react';
import './rial_journal_panel.css';

// V2 boundary: amounts arrive as canonical decimal RIAL strings. Never convert
// the existing numeric TOMAN accounting snapshot or call accountingCommand.
export const RIAL_V2_SCHEMA='IR-JOURNAL-V2.1';
export const MAX_RIAL_V2=9007199254740991n;
const ID=/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/;
const KINDS=new Set(['task','card','checklist','independent']);
const PERSIAN='۰۱۲۳۴۵۶۷۸۹';
const validId=value=>typeof value==='string'&&ID.test(value);

export function parseCanonicalRial(value){
  if(typeof value!=='string'||value.length>16||!/^(?:0|[1-9][0-9]*)$/.test(value))return null;
  const amount=BigInt(value);
  return amount<=MAX_RIAL_V2?amount:null;
}

export function formatExactRial(value){
  const rial=parseCanonicalRial(value);
  if(rial===null)return 'مبلغ ریالی نامعتبر';
  return rial.toString().replace(/\B(?=(\d{3})+(?!\d))/g,',')
    .replace(/[0-9]/g,digit=>PERSIAN[Number(digit)])+' ریال';
}

const validDate=value=>{
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const [year,month,day]=value.split('-').map(Number);
  const parsed=new Date(Date.UTC(year,month-1,day));
  return parsed.getUTCFullYear()===year&&parsed.getUTCMonth()===month-1&&parsed.getUTCDate()===day;
};

export function validateRialLines(lines){
  if(!Array.isArray(lines)||lines.length<2||lines.length>100)return {error:'هر سند باید بین ۲ تا ۱۰۰ ردیف داشته باشد.'};
  let debits=0n,credits=0n;
  for(const line of lines){
    if(!line||!validId(line.accountCode)||
      (line.costCenterCode!=null&&!validId(line.costCenterCode)))
      return {error:'کد حساب یا مرکز هزینه یکی از ردیف‌ها نامعتبر است.'};
    const debit=parseCanonicalRial(line.debitRial);
    const credit=parseCanonicalRial(line.creditRial);
    if(debit===null||credit===null||(debit>0n)===(credit>0n))
      return {error:'ردیف سند باید دقیقاً یک بدهکار یا بستانکار ریالی مثبت داشته باشد.'};
    debits+=debit;credits+=credit;
    if(debits>MAX_RIAL_V2||credits>MAX_RIAL_V2)
      return {error:'گردش سند از سقف دقیق ریالی بیشتر است.'};
  }
  if(debits===0n||debits!==credits)return {error:'سند در مقیاس ریال تراز نیست.'};
  return {error:'',totalRial:debits.toString()};
}

function validateScope(data,{companyId,fiscalPeriodId}){
  if(!data||typeof data!=='object'||Array.isArray(data)||
    data.schema!==RIAL_V2_SCHEMA||data.currency!=='RIAL'||
    data.companyId!==companyId||data.fiscalPeriodId!==fiscalPeriodId)
    return 'نسخه، واحد ریال، شرکت یا دوره مالی پاسخ میزبان V2 تطابق ندارد.';
  return '';
}

export function validateRialJournalSnapshot(data,scope){
  const scopeError=validateScope(data,scope);
  if(scopeError)return {error:scopeError};
  if(typeof data.revision!=='string'||!/^[a-fA-F0-9]{64}$/.test(data.revision)||
    !Array.isArray(data.journals)||data.journals.length>500)
    return {error:'نسخه دفترکل یا تعداد اسناد پاسخ معتبر نیست؛ حداکثر ۵۰۰ سند در هر پاسخ پذیرفته می‌شود.'};
  const unique=new Set();
  for(const journal of data.journals){
    if(!journal||!validId(journal.eventId)||unique.has(journal.eventId)||
      journal.companyId!==scope.companyId||journal.fiscalPeriodId!==scope.fiscalPeriodId||
      !validDate(journal.postingDate)||!journal.source||
      !KINDS.has(journal.source.kind)||!validId(journal.source.sourceId)||
      (journal.reversalOf!=null&&journal.reversalOf!==''&&!validId(journal.reversalOf)))
      return {error:'شناسه، منبع یا محدوده یکی از اسناد V2 نامعتبر است.'};
    unique.add(journal.eventId);
    const check=validateRialLines(journal.lines);
    if(check.error)return {error:'سند '+journal.eventId+': '+check.error};
  }
  return {error:'',journals:data.journals,revision:data.revision};
}

export function validateRialInvoicePreview(data,scope,invoice){
  const scopeError=validateScope(data,scope);
  if(scopeError)return {error:scopeError};
  if(!validId(invoice.invoiceId)||!['sales','purchase'].includes(invoice.invoiceKind)||
    data.previewOnly!==true||data.invoiceId!==invoice.invoiceId||
    data.invoiceKind!==invoice.invoiceKind||!validDate(data.postingDate))
    return {error:'پاسخ صدور آزمایشی معتبر نیست یا میزبان حالت فقط پیش‌نمایش را تأیید نکرد.'};
  const amount=parseCanonicalRial(data.totalRial);
  if(amount===null||amount===0n)return {error:'مبلغ فاکتور در پاسخ میزبان نامعتبر است.'};
  const lines=validateRialLines(data.lines);
  if(lines.error)return {error:'پیش‌نمایش ثبت دوبل نامعتبر است: '+lines.error};
  return {error:'',preview:data};
}

const scopeKey=(companyId,fiscalPeriodId)=>companyId+'\u001f'+fiscalPeriodId;
const sourceLabel=source=>({task:'تسک',card:'کارت',checklist:'چک‌لیست',independent:'سند مستقل'})[source.kind]+' · '+source.sourceId;

function JournalRows({lines}){
  return <div className="rjv-table-scroll"><table>
    <thead><tr><th scope="col">کد حساب</th><th scope="col">بدهکار (ریال)</th><th scope="col">بستانکار (ریال)</th><th scope="col">مرکز هزینه</th></tr></thead>
    <tbody>{lines.map((line,index)=><tr key={index}>
      <th scope="row" dir="ltr">{line.accountCode}</th>
      <td dir="ltr">{formatExactRial(line.debitRial)}</td>
      <td dir="ltr">{formatExactRial(line.creditRial)}</td>
      <td>{line.costCenterCode||'—'}</td>
    </tr>)}</tbody>
  </table></div>;
}

/**
 * Standalone V2 read UI. The host supplies trusted company/period identity,
 * grants and two new dedicated, authenticated read-only methods:
 *   api.rialJournalRead({companyId,fiscalPeriodId}) -> V2 snapshot DTO
 *   api.rialInvoiceIssuePreview({companyId,fiscalPeriodId,
 *     invoiceId,invoiceKind,previewOnly:true}) -> V2 preview DTO.
 * No UI method can create, issue, reverse or post a financial document.
 */
export function RialJournalPanel({
  api,companyId='',fiscalPeriodId='',canView=false,canPreview=false,onExit,
}){
  const [reading,setReading]=useState({key:'',status:'idle',message:'',data:null});
  const [invoiceKind,setInvoiceKind]=useState('sales');
  const [invoiceId,setInvoiceId]=useState('');
  const [preview,setPreview]=useState({key:'',status:'idle',message:'',data:null});
  const [refreshIndex,setRefreshIndex]=useState(0);
  const generation=useRef(0);
  const key=scopeKey(companyId,fiscalPeriodId);
  const identified=validId(companyId)&&validId(fiscalPeriodId);
  const hasRead=typeof api?.rialJournalRead==='function';
  const hasPreview=typeof api?.rialInvoiceIssuePreview==='function';
  const scope={companyId,fiscalPeriodId};
  const visibleRead=canView&&identified&&hasRead&&reading.key===key&&reading.status==='ready'?reading.data:null;
  const inputKey=key+'\u001f'+(visibleRead?.revision||'')+'\u001f'+invoiceKind+'\u001f'+invoiceId;
  const visiblePreview=canPreview&&hasPreview&&visibleRead&&preview.key===inputKey&&preview.status==='ready'?preview.data:null;
  const canRequestPreview=canView&&canPreview&&identified&&hasRead&&hasPreview&&!!visibleRead;

  useEffect(()=>{
    generation.current+=1;
    let cancelled=false;
    if(!canView||!identified||!hasRead){
      setReading({key,status:'blocked',message:'',data:null});
      return ()=>{cancelled=true;};
    }
    setReading({key,status:'loading',message:'',data:null});
    Promise.resolve().then(()=>api.rialJournalRead({companyId,fiscalPeriodId})).then(data=>{
      if(cancelled)return;
      const checked=validateRialJournalSnapshot(data,{companyId,fiscalPeriodId});
      setReading({key,status:checked.error?'error':'ready',message:checked.error||'',data:checked.error?null:checked});
    }).catch(error=>{
      if(!cancelled)setReading({key,status:'error',message:'خواندن امن دفترکل V2 ناموفق بود. وضعیت اتصال یا مجوز را در میزبان بررسی کنید.',data:null});
    });
    return ()=>{cancelled=true;};
  },[api?.rialJournalRead,companyId,fiscalPeriodId,canView,identified,hasRead,key,refreshIndex]);

  useEffect(()=>{
    generation.current+=1;
    setPreview({key:'',status:'idle',message:'',data:null});
  },[canPreview,hasPreview]);

  const updateKind=next=>{generation.current+=1;setInvoiceKind(next);setPreview({key:'',status:'idle',message:'',data:null});};
  const updateInvoice=next=>{generation.current+=1;setInvoiceId(next);setPreview({key:'',status:'idle',message:'',data:null});};
  const refresh=()=>{generation.current+=1;setPreview({key:'',status:'idle',message:'',data:null});setRefreshIndex(i=>i+1);};
  async function requestPreview(event){
    event.preventDefault();
    if(!canRequestPreview||!validId(invoiceId))return;
    const id=++generation.current;
    setPreview({key:inputKey,status:'loading',message:'',data:null});
    try{
      const result=await api.rialInvoiceIssuePreview({
        companyId,fiscalPeriodId,invoiceId,invoiceKind,previewOnly:true,
      });
      if(id!==generation.current)return;
      const checked=validateRialInvoicePreview(result,scope,{invoiceId,invoiceKind});
      setPreview({key:inputKey,status:checked.error?'error':'ready',
        message:checked.error||'',data:checked.error?null:checked.preview});
    }catch(error){
      if(id===generation.current)setPreview({key:inputKey,status:'error',
        message:'دریافت پیش‌نمایش V2 ناموفق بود. وضعیت فاکتور و مجوز را در میزبان بررسی کنید.',data:null});
    }
  }

  if(!canView)return <section className="rjv-root" dir="rtl"><p role="alert">مجوز مشاهده دفتر روزنامه ریالی برای شما صادر نشده است.</p></section>;

  return <section className="rjv-root" dir="rtl" aria-label="دفتر روزنامه ریالی V2">
    <header className="rjv-header">
      <div><p className="rjv-overline">Madar Desk · IR-JOURNAL-V2.1</p><h2>دفتر روزنامه ریالی</h2>
        <p>همه مبالغ این بخش فقط ریال صحیح هستند. حسابداری قدیمی مدار بر مبنای تومان باقی است.</p></div>
      {typeof onExit==='function'&&<button type="button" onClick={onExit}>بازگشت</button>}
    </header>
    {(!identified||!hasRead||!hasPreview)&&<p className="rjv-alert" role="alert">
      اتصال کامل و معتبر به میزبان حسابداری ریالی V2 برقرار نیست.
      { !identified?' شناسه معتبر شرکت و دوره مالی ارسال نشده است.':''}
      { !hasRead?' endpoint خواندن دفترکل V2 موجود نیست.':''}
      { !hasPreview?' endpoint پیش‌نمایش صدور V2 موجود نیست.':''}
      {' '}داده‌های تومانی قدیمی نباید به عنوان سند ریالی تعبیر شوند و امکان صدور فاکتور وجود ندارد.
    </p>}
    <div className="rjv-meta"><span>شرکت: <b dir="ltr">{identified?companyId:'تعریف‌نشده'}</b></span>
      <span>دوره مالی: <b dir="ltr">{identified?fiscalPeriodId:'تعریف‌نشده'}</b></span>
      <span>واحد ثابت: <strong>RIAL · ریال</strong></span></div>
    <div className="rjv-grid">
      <section className="rjv-card" aria-label="اسناد ثبت شده ریالی">
        <div className="rjv-card-heading"><h3>اسناد ثبت‌شده</h3>
          <button type="button" onClick={refresh} disabled={!identified||!hasRead||reading.status==='loading'}>تازه‌سازی اسناد</button></div>
        {reading.key===key&&reading.status==='loading'&&<p role="status">در حال خواندن اسناد V2...</p>}
        {reading.key===key&&reading.status==='error'&&<p role="alert">{reading.message}</p>}
        {visibleRead&&<><p className="rjv-caption">نسخه دفترکل: <code dir="ltr">{visibleRead.revision}</code></p>
          {visibleRead.journals.length===0?<p>سندی در دوره انتخاب‌شده ثبت نشده است.</p>:
            <div className="rjv-journals">{visibleRead.journals.map(journal=>
              <details key={journal.eventId} className="rjv-journal">
                <summary><strong dir="ltr">{journal.eventId}</strong><span>{journal.postingDate}</span>
                  <span>{sourceLabel(journal.source)}</span><b>{formatExactRial(validateRialLines(journal.lines).totalRial)}</b></summary>
                {journal.reversalOf&&<p>برگشت سند: {journal.reversalOf}</p>}
                <JournalRows lines={journal.lines}/>
              </details>)}</div>}
        </>}
        {!visibleRead&&reading.status==='idle'&&<p role="status">در انتظار اتصال دفترکل V2...</p>}
      </section>
      <section className="rjv-card" aria-label="پیش نمایش صدور فاکتور">
        <h3>پیش‌نمایش صدور فاکتور</h3>
        <p>برای فاکتور موجود، محاسبات پیش از صدور از میزبان V2 خوانده می‌شود. این صفحه هیچ فاکتوری صادر یا ثبت نمی‌کند.</p>
        {!canPreview&&<p role="alert">مجوز دریافت پیش‌نمایش صدور فاکتور ارائه نشده است.</p>}
        <form className="rjv-form" onSubmit={requestPreview}>
          <label>نوع فاکتور<select value={invoiceKind} onChange={event=>updateKind(event.target.value)}
            disabled={!canRequestPreview}><option value="sales">فروش</option><option value="purchase">خرید</option></select></label>
          <label>شناسه فاکتور<input value={invoiceId} dir="ltr" maxLength={96}
            onChange={event=>updateInvoice(event.target.value)}
            disabled={!canRequestPreview} placeholder="invoice-001"/></label>
          <button type="submit" disabled={!canRequestPreview||!validId(invoiceId)||preview.status==='loading'}>
            فقط محاسبه پیش‌نمایش
          </button>
        </form>
        {preview.key===inputKey&&preview.status==='loading'&&<p role="status">در حال محاسبه پیش‌نمایش...</p>}
        {preview.key===inputKey&&preview.status==='error'&&<p role="alert">{preview.message}</p>}
        {visiblePreview&&<div className="rjv-preview" role="status">
          <strong>پیش‌نمایش فقط خواندنی؛ هیچ سندی صادر نشده است.</strong>
          <p>فاکتور: <b dir="ltr">{visiblePreview.invoiceId}</b> | تاریخ سند: {visiblePreview.postingDate}</p>
          <p>جمع فاکتور: <b>{formatExactRial(visiblePreview.totalRial)}</b></p>
          <JournalRows lines={visiblePreview.lines}/>
        </div>}
      </section>
    </div>
  </section>;
}

export default RialJournalPanel;
