import React,{useEffect,useMemo,useState} from 'react';
import AccountingJalaliField from './accounting_jalali_field.jsx';
import {displayAccountingDate,formatAccountingJalali,
  parseAccountingJalali} from './accounting_jalali_dates.js';
import {parseAccountingBankCSV,parseAccountingBankAmount,accountingBankNetExact} from './accounting_bank_csv.js';

const numberOf=value=>{
  const normalized=String(value??'').trim()
    .replace(/[۰-۹]/g,x=>String(x.charCodeAt(0)-1776))
    .replace(/[٠-٩]/g,x=>String(x.charCodeAt(0)-1632))
    .replace(/[٬,\s]/g,'');
  if(!/^(0|[1-9][0-9]*)$/.test(normalized))throw Error('عدد باید صحیح، نامنفی و بدون اعشار باشد.');
  const n=BigInt(normalized);
  if(n>BigInt(Number.MAX_SAFE_INTEGER))throw Error('عدد خارج از محدوده دقیق حسابداری است.');
  return Number(n);
};
const signedNumber=value=>parseAccountingBankAmount(value);
const money=(n,unit)=>typeof n==='number'?n.toLocaleString('fa-IR')+' '+unit:'—';
const opt=(rows,label,selected='')=><><option value="">{label}</option>
  {rows.map(r=><option key={r.id} value={r.id}>{r.name||r.id} ({r.id})</option>)}</>;
const asList=collection=>Object.values(collection||{}).sort((a,b)=>a.id.localeCompare(b.id,'en',{numeric:true}));
const sendCommand=(execute,type,fields,message)=>execute(id=>({command:{
  type,eventId:id,...fields,
}}),message||'عملیات با شناسه جدید در دفتر مستقل ثبت شد.');

function InlineForm({title,children,onSubmit,canManage,disabled=false}){
  const [error,setError]=useState('');
  if(!canManage)return null;
  return <section className="sac-panel sac-operational-form">
    <h3>{title}</h3>
    <form className="sac-grid" onSubmit={async e=>{
      e.preventDefault();if(disabled)return;
      setError('');
      try{await onSubmit();}catch(err){setError(err?.message||'ورودی عملیات معتبر نیست.');}
    }}>
      {children}
      {error&&<p role="alert" className="sac-alert error">{error}</p>}
      <div className="sac-form-actions"><button type="submit" disabled={disabled}>ثبت با سابقه حسابداری</button></div>
    </form>
  </section>;
}
function Input({label,value,onChange,required=true,kind='text',options=null}){
  return <label className="sac-field"><span>{label}</span>
    {options?<select required={required} value={value} onChange={e=>onChange(e.target.value)}>
      {options}</select>:<input dir={kind==='number'?'ltr':undefined}
        inputMode={kind==='number'?'numeric':undefined}
        required={required} value={value} onChange={e=>onChange(e.target.value)}/>}
  </label>;
}
function SolarDate({label,value,onChange,limit}){
  return <label className="sac-field"><span>{label}</span>
    <AccountingJalaliField value={value} onChange={onChange} max={limit}/>
  </label>;
}
function Err({children}){return <p className="sac-audit-notice">{children}</p>;}
function Table({cols,rows,empty='رکوردی ثبت نشده است.'}){
  const [search,setSearch]=useState(''),[shown,setShown]=useState(100);
  const filtered=search?rows.filter(r=>r.search.toLocaleLowerCase('fa-IR')
    .includes(search.toLocaleLowerCase('fa-IR'))):rows;
  return <div className="sac-table-container">
    <div className="sac-table-tools">
      <input type="search" placeholder="جست‌وجو در فهرست"
        aria-label="جست‌وجو در فهرست" value={search}
        onChange={e=>{setSearch(e.target.value);setShown(100);}}/>
      <span>{Math.min(shown,filtered.length).toLocaleString('fa-IR')} از {
        filtered.length.toLocaleString('fa-IR')} ردیف</span>
    </div>
    <div className="sac-table-wrap"><table>
      <thead><tr>{cols.map((col,i)=><th key={i}>{col}</th>)}</tr></thead>
      <tbody>{filtered.slice(0,shown).map(r=><tr key={r.id}>{r.cells.map((cell,i)=>
        <td key={i}>{cell}</td>)}</tr>)}</tbody>
    </table></div>
    {!filtered.length&&<p>{empty}</p>}
    {shown<filtered.length&&<div className="sac-table-pagination">
      <button type="button" onClick={()=>setShown(v=>v+100)}>نمایش ۱۰۰ مورد بعدی</button>
      <button type="button" onClick={()=>setShown(Number.MAX_SAFE_INTEGER)}>نمایش همه</button></div>}
  </div>;
}

export function LiveCheques({view,canManage,disabled,execute,today,unit}){
  const [form,setForm]=useState({chequeId:'',direction:'receipt',documentId:'',
    bankAccountId:'1010',dueDate:today,amount:'',reference:''});
  const [reasons,setReasons]=useState({});
  const [endorsees,setEndorsees]=useState({});
  const change=(field,val)=>setForm(f=>({...f,[field]:val,
    ...(field==='direction'?{documentId:''}:{})}));
  const docs=asList(view[form.direction==='receipt'?'invoices':'bills']).filter(d=>
    d.status==='issued'&&d.allocated+(d.returnedAmount||0)<d.total);
  const liquid=asList(view.accounts).filter(a=>a.liquid);
  const cheques=asList(view.cheques);
  return <section>
    <h2>خزانه و چک عملیاتی</h2>
    <Err>ثبت و واگذاری چک وجه نقد ایجاد نمی‌کند؛ فقط پس از تأیید واقعی وصول در بانک،
      پرداخت یا دریافت مربوط در دفترکل ثبت می‌شود. چک‌های پارسیان بدون تطبیق وارد این بخش نمی‌شوند.</Err>
    <Table cols={['شناسه','جهت و طرف‌حساب','شماره بانک','سررسید شمسی','مبلغ','وضعیت','عملیات']}
      rows={cheques.map(ch=>{
        const reason=reasons[ch.id]||'';
        const act=(label,action,requireReason=false)=>canManage?<button type="button"
          disabled={disabled||(requireReason&&!reason.trim())}
          onClick={()=>void sendCommand(execute,'cheque.'+action,
            {chequeId:ch.id,...(action==='clear'?{postingDate:today}:{}),
              ...(requireReason?{reason:reason.trim()}:{}),
            },'وضعیت چک و در صورت وصول، سند حسابداری ثبت شد.')}>{label}</button>:null;
        return {id:ch.id,search:[ch.id,ch.reference,ch.status,ch.partyId].join(' '),cells:[
          ch.id, <>{ch.direction==='receipt'?'دریافتی':'پرداختی'} / {
            view.parties[ch.partyId]?.name||ch.partyId}</>,
          ch.reference,displayAccountingDate(ch.dueDate),money(ch.amount,unit),ch.status,
          <div className="sac-cheque-actions">
            {canManage&&['received','deposited','issued','endorsed','returned'].includes(ch.status)&&
              <input placeholder="دلیل برگشت، لغو یا واگذاری" value={reason}
                onChange={e=>setReasons(p=>({...p,[ch.id]:e.target.value}))}/>}
            {ch.status==='received'&&act('سپردن به بانک','deposit')}
            {ch.status==='received'&&canManage&&<>
              <select value={endorsees[ch.id]||''}
                onChange={e=>setEndorsees(p=>({...p,[ch.id]:e.target.value}))}>
                {opt(asList(view.parties).filter(p=>p.id!==ch.partyId),
                  'انتخاب ذی‌نفع واگذاری')}
              </select>
              <button type="button" disabled={disabled||!reason.trim()||!endorsees[ch.id]}
                onClick={()=>void sendCommand(execute,'cheque.endorse',{
                  chequeId:ch.id,endorseeId:endorsees[ch.id],
                  reason:reason.trim()})}>واگذاری با سابقه</button>
            </>}
            {ch.status==='deposited'&&act('تأیید وصول بانک','clear')}
            {ch.status==='issued'&&act('تأیید پاس‌شدن','clear')}
            {['received','deposited','issued','endorsed'].includes(ch.status)&&
              act('برگشت چک','return',true)}
            {['received','deposited','issued','endorsed','returned'].includes(ch.status)&&
              act('لغو قطعی تعهد چک','cancel',true)}
            {ch.status==='returned'&&canManage&&<button disabled={disabled}
              onClick={()=>void sendCommand(execute,'cheque.redeliver',{
                chequeId:ch.id,reason:'ثبت مجدد چک برگشتی با تأیید اپراتور'})}>ثبت مجدد در جریان</button>}
          </div>,
        ]};
      })}/>
    <InlineForm title="ثبت چک دریافتی یا پرداختی" canManage={canManage} disabled={disabled}
      onSubmit={async()=>{
        const ok=await sendCommand(execute,'cheque.register',{
          chequeId:form.chequeId,direction:form.direction,
          documentId:form.documentId,bankAccountId:form.bankAccountId,
          dueDate:form.dueDate,amount:numberOf(form.amount),
          reference:form.reference.trim()});
        if(ok)setForm(f=>({...f,chequeId:'',amount:'',reference:''}));
      }}>
      <Input label="شناسه چک" value={form.chequeId} onChange={v=>change('chequeId',v)}/>
      <Input label="نوع" value={form.direction} onChange={v=>change('direction',v)}
        options={<><option value="receipt">دریافتی</option><option value="payment">پرداختی</option></>}/>
      <Input label="فاکتور صادرشده" value={form.documentId}
        onChange={v=>change('documentId',v)}
        options={opt(docs.map(d=>({...d,name:d.id+' / '+(view.parties[d.partyId]?.name||'')})),
          'انتخاب فاکتور')}/>
      <Input label="حساب بانکی" value={form.bankAccountId}
        onChange={v=>change('bankAccountId',v)} options={opt(liquid,'انتخاب بانک')}/>
      <SolarDate label="تاریخ سررسید" value={form.dueDate} onChange={v=>change('dueDate',v)}/>
      <Input label={'مبلغ ('+unit+')'} kind="number" value={form.amount}
        onChange={v=>change('amount',v)}/>
      <Input label="شناسه/شماره روی چک" value={form.reference}
        onChange={v=>change('reference',v)}/>
    </InlineForm>
  </section>;
}

export function LiveInventory({view,canManage,canAdmin=canManage,disabled,execute,today,unit}){
  const [warehouse,setWarehouse]=useState({warehouseId:'',name:''});
  const [reverseReason,setReverseReason]=useState({});
  const [form,setForm]=useState({type:'inventory.receive',warehouseId:'',itemId:'',
    quantity:'',postingDate:today,billId:'',invoiceId:'',unitCost:'',toWarehouseId:'',reason:''});
  const ch=(key,val)=>setForm(p=>({...p,[key]:val}));
  const warehouses=asList(view.warehouses),goods=asList(view.items).filter(a=>a.kind==='goods');
  const stock=warehouses.flatMap(w=>Object.entries(view.stock?.[w.id]||{}).map(([itemId,b])=>
    ({id:w.id+':'+itemId,warehouseId:w.id,itemId,qty:b.quantity,value:b.value})));
  const movements=asList(view.stockMovements);
  return <section>
    <h2>انبار، کاردکس و بهای تمام‌شده FIFO</h2>
    <Err>رسید خرید فقط به فاکتور خرید صادرشده و کالای دارای رهگیری موجودی متصل می‌شود.
      موجودی افتتاحیه با تأیید سرمایه ثبت می‌شود. حواله فروش بهای تمام‌شده را در دفترکل ثبت می‌کند.</Err>
    <Table cols={['انبار','کالا','تعداد موجود','ارزش موجودی']}
      rows={stock.map(s=>({id:s.id,search:s.id+' '+view.items[s.itemId]?.name,cells:[
        view.warehouses[s.warehouseId]?.name||s.warehouseId,
        view.items[s.itemId]?.name||s.itemId,
        s.qty.toLocaleString('fa-IR'),money(s.value,unit)]}))}/>
    <h3>کاردکس عملیات ثبت‌شده</h3>
    <Table cols={['شناسه','عملیات','انبار','کالا','تعداد','ارزش','تاریخ','برگشت']}
      rows={movements.map(m=>({id:m.id,search:m.id+' '+m.type+' '+m.itemId,cells:[
        m.id,m.type,view.warehouses[m.warehouseId]?.name||m.warehouseId,
        view.items[m.itemId]?.name||m.itemId,m.quantity.toLocaleString('fa-IR'),
        money(m.value,unit),displayAccountingDate(m.postingDate),
        m.reversed?'برگشت‌شده':m.type==='inventory.reverse'?'اصلاحیه':
          canManage?<div className="sac-cheque-actions">
            <input placeholder="علت برگشت کاردکس" value={reverseReason[m.id]||''}
              onChange={e=>setReverseReason(p=>({...p,[m.id]:e.target.value}))}/>
            <button disabled={disabled||!(reverseReason[m.id]||'').trim()}
              onClick={()=>void sendCommand(execute,'inventory.reverse',{
                movementId:m.id,postingDate:today,reason:reverseReason[m.id].trim()})}>
              برگشت ایمن</button></div>:null,
      ]}))}/>
    <InlineForm title="تعریف انبار" canManage={canManage} disabled={disabled}
      onSubmit={async()=>{
        const ok=await sendCommand(execute,'warehouse.create',warehouse);
        if(ok)setWarehouse({warehouseId:'',name:''});
      }}>
      <Input label="کد انبار" value={warehouse.warehouseId}
        onChange={v=>setWarehouse(s=>({...s,warehouseId:v}))}/>
      <Input label="نام انبار" value={warehouse.name}
        onChange={v=>setWarehouse(s=>({...s,name:v}))}/>
    </InlineForm>
    {canManage&&goods.some(x=>!x.stockTracked)&&<section className="sac-panel">
      <h3>فعال‌کردن کنترل موجودی برای کالا</h3>
      {goods.filter(x=>!x.stockTracked).map(g=><button key={g.id}
        type="button" disabled={disabled} onClick={()=>void sendCommand(execute,
          'item.stock.enable',{itemId:g.id})}>فعال‌سازی {g.name}</button>)}
    </section>}
    <InlineForm title="ثبت رسید، حواله، انتقال و اصلاح موجودی" canManage={canManage}
      disabled={disabled} onSubmit={async()=>{
        const fields={warehouseId:form.warehouseId,itemId:form.itemId,
          quantity:numberOf(form.quantity),postingDate:form.postingDate};
        if(form.type==='inventory.receive')fields.billId=form.billId;
        if(form.type==='inventory.issue')fields.invoiceId=form.invoiceId;
        if(form.type==='inventory.opening'){
          if(!canAdmin)throw Error('ثبت موجودی افتتاحیه تنها برای مدیر مجاز است.');
          fields.unitCost=numberOf(form.unitCost);
        }
        if(form.type==='inventory.transfer')fields.toWarehouseId=form.toWarehouseId;
        if(['inventory.opening','inventory.transfer','inventory.adjust'].includes(form.type))
          fields.reason=form.reason.trim();
        const ok=await sendCommand(execute,form.type,fields);
        if(ok)setForm(s=>({...s,quantity:'',reason:''}));
      }}>
      <Input label="نوع عملیات" value={form.type} onChange={v=>ch('type',v)} options={<>
        {canAdmin&&<option value="inventory.opening">موجودی افتتاحیه با سرمایه</option>}
        <option value="inventory.receive">رسید خرید دارای فاکتور</option>
        <option value="inventory.issue">حواله فروش و ثبت بهای تمام‌شده</option>
        <option value="inventory.transfer">انتقال به انبار دیگر</option>
        <option value="inventory.adjust">کسری انبارگردانی</option>
      </>}/>
      <Input label="انبار مبدأ" value={form.warehouseId} onChange={v=>ch('warehouseId',v)}
        options={opt(warehouses,'انتخاب انبار')}/>
      <Input label="کالای دارای رهگیری" value={form.itemId} onChange={v=>ch('itemId',v)}
        options={opt(goods.filter(g=>g.stockTracked),'انتخاب کالا')}/>
      <Input label="تعداد صحیح در واحد پایه" kind="number" value={form.quantity}
        onChange={v=>ch('quantity',v)}/>
      <SolarDate label="تاریخ ثبت" value={form.postingDate}
        onChange={v=>ch('postingDate',v)} limit={today}/>
      {form.type==='inventory.receive'&&<Input label="فاکتور خرید قطعی"
        value={form.billId} onChange={v=>ch('billId',v)}
        options={opt(asList(view.bills).filter(d=>d.status==='issued'),'انتخاب خرید')}/>}
      {form.type==='inventory.issue'&&<Input label="فاکتور فروش قطعی"
        value={form.invoiceId} onChange={v=>ch('invoiceId',v)}
        options={opt(asList(view.invoices).filter(d=>d.status==='issued'),'انتخاب فروش')}/>}
      {form.type==='inventory.opening'&&<Input label={'بهای تمام‌شده هر واحد ('+unit+')'}
        kind="number" value={form.unitCost} onChange={v=>ch('unitCost',v)}/>}
      {form.type==='inventory.transfer'&&<Input label="انبار مقصد"
        value={form.toWarehouseId} onChange={v=>ch('toWarehouseId',v)}
        options={opt(warehouses.filter(w=>w.id!==form.warehouseId),'انتخاب انبار مقصد')}/>}
      {['inventory.opening','inventory.adjust','inventory.transfer'].includes(form.type)&&
        <Input label="دلیل مستند" value={form.reason} onChange={v=>ch('reason',v)}/>}
    </InlineForm>
  </section>;
}

export function BankReconciliation({view,canManage,disabled,execute,today,unit}){
  const [form,setForm]=useState({statementId:'',accountId:'1010',
    date:today,amount:'',reference:''});
  const [reasons,setReasons]=useState({});
  const [matches,setMatches]=useState({});
  const [importRows,setImportRows]=useState([]);
  const [importError,setImportError]=useState('');
  const [importAcknowledged,setImportAcknowledged]=useState(false);
  const ch=(key,val)=>setForm(p=>({...p,[key]:val}));
  const statements=asList(view.bankStatements);
  const liquid=asList(view.accounts).filter(a=>a.liquid);
  const journalOptions=asList(Object.fromEntries(view.journals.filter(j=>
    !j.reversalOf&&!view.reversed?.[j.id]).map(j=>[j.id,{...j,name:j.id+' / '+j.date}])));
  const remaining=statements.filter(r=>!r.journalId);
  return <section>
    <h2>مغایرت‌گیری بانک</h2>
    <Err>ردیف‌های صورتحساب بانک فقط سند شاهد هستند. ثبت صورت‌حساب به‌تنهایی
      هیچ وجه یا سند مالی ایجاد نمی‌کند. «تطبیق» فقط وقتی مبلغ حساب بانکی در سند دقیقاً
      با مبلغ مثبت/منفی ردیف برابر باشد مجاز است.</Err>
    <div className="sac-metrics">
      <div className="sac-metric"><span>جمع اقلام صورت‌حساب</span><strong>{statements.length.toLocaleString('fa-IR')}</strong></div>
      <div className="sac-metric"><span>تطبیق‌نشده</span><strong>{remaining.length.toLocaleString('fa-IR')}</strong></div>
      <div className="sac-metric"><span>خالص مانده اقلام تطبیق‌نشده</span><strong>{
        money(remaining.reduce((n,r)=>n+r.amount,0),unit)}</strong></div>
    </div>
    <Table cols={['شناسه','بانک','شماره رسید/مرجع','تاریخ','مبلغ','سند تطبیق','اقدامات']}
      rows={statements.map(r=>({id:r.id,search:r.id+' '+r.reference+' '+r.journalId,
        cells:[r.id,view.accounts[r.accountId]?.name||r.accountId,r.reference,
          displayAccountingDate(r.date),
          <span className={r.amount>0?'sac-money-debit':'sac-money-credit'}>
            {money(r.amount,unit)}</span>,r.journalId||'تطبیق‌نشده',
          canManage?<div className="sac-cheque-actions">
            <input placeholder="علت تصمیم تطبیق" value={reasons[r.id]||''}
              onChange={e=>setReasons(p=>({...p,[r.id]:e.target.value}))}/>
            {!r.journalId&&<select value={matches[r.id]||''}
              onChange={e=>setMatches(p=>({...p,[r.id]:e.target.value}))}>
              {opt(journalOptions,'سند دفترکل')}</select>}
            <button type="button" disabled={disabled||!(reasons[r.id]||'').trim()||
              (!r.journalId&&!matches[r.id])}
              onClick={()=>void sendCommand(execute,
                r.journalId?'bank.statement.unmatch':'bank.statement.match',{
                  statementId:r.id,reason:reasons[r.id].trim(),
                  ...(r.journalId?{}:{journalId:matches[r.id]})})}>
              {r.journalId?'بازکردن مغایرت':'تطبیق با سند'}</button>
          </div>:null,
        ]}))}/>
    <InlineForm title="ثبت ردیف صورتحساب بانکی" canManage={canManage}
      disabled={disabled} onSubmit={async()=>{
        const ok=await sendCommand(execute,'bank.statement.add',{
          statementId:form.statementId,accountId:form.accountId,
          date:form.date,amount:signedNumber(form.amount),
          reference:form.reference.trim()});
        if(ok)setForm(s=>({...s,statementId:'',amount:'',reference:''}));
      }}>
      <Input label="شناسه رکورد بانک" value={form.statementId}
        onChange={v=>ch('statementId',v)}/>
      <Input label="حساب بانکی" value={form.accountId} onChange={v=>ch('accountId',v)}
        options={opt(liquid,'انتخاب حساب')}/>
      <SolarDate label="تاریخ تراکنش" value={form.date} onChange={v=>ch('date',v)}/>
      <Input label={'مبلغ علامت‌دار ('+unit+') / منفی برای برداشت'} value={form.amount}
        onChange={v=>ch('amount',v)}/>
      <Input label="شناسه مرجع بانک" value={form.reference}
        onChange={v=>ch('reference',v)}/>
    </InlineForm>
    {canManage&&<section className="sac-panel">
      <h3>ورود دسته‌ای صورتحساب بانک از CSV آفلاین</h3>
      <p>فرمت دقیق پنج ستون با جداکننده نقطه‌ویرگول:
        <code dir="ltr">statementId;accountId;date;amount;reference</code>.
        تاریخ‌ها به‌شکل شمسی ۱۴۰۵/۰۸/۰۲ یا ISO، مبلغ صحیح علامت‌دار و حداکثر ۵۰۰ ردیف در هر فایل.
        فایل فقط در حافظه همین رایانه خوانده می‌شود و ثبت نهایی یک تراکنش اتمیک است.</p>
      <input type="file" accept=".csv,text/csv" aria-label="فایل CSV بانک"
        onChange={async e=>{
          setImportRows([]);setImportAcknowledged(false);setImportError('');
          const file=e.target.files?.[0];if(!file)return;
          try{
            if(file.size>1024*1024)throw Error('فایل CSV بیش از ۱ مگابایت است.');
            const value=await file.text();
            setImportRows(parseAccountingBankCSV(value,{
              accounts:view.accounts,existing:view.bankStatements,today}));
          }catch(err){setImportError(err.message||'خواندن فایل معتبر نبود.');}
        }}/>
      {importError&&<p role="alert" className="sac-alert error">{importError}</p>}
      {!!importRows.length&&<>
        <p>{importRows.length.toLocaleString('fa-IR')} ردیف،
          خالص {accountingBankNetExact(importRows).toLocaleString('fa-IR')+' '+unit}
          {' '}برای ثبت آماده است.</p>
        <label><input type="checkbox" checked={importAcknowledged}
          onChange={e=>setImportAcknowledged(e.target.checked)}/>
          تأیید می‌کنم شناسه بانک، صورت‌حساب اصلی و مبالغ را بررسی کرده‌ام.</label>
        <button type="button" disabled={disabled||!importAcknowledged}
          onClick={async()=>{
            if(await sendCommand(execute,'bank.statement.batch',{rows:importRows},
              'تمام ردیف‌های CSV در یک تراکنش ثبت شدند.')){
              setImportRows([]);setImportAcknowledged(false);
            }
          }}>ثبت اتمیک همه ردیف‌ها</button>
      </>}
    </section>}
  </section>;
}

export function InstalmentPlans({view,canManage,disabled,execute,today,unit}){
  const [form,setForm]=useState({planId:'',direction:'receipt',
    documentId:'',schedule:''});
  const [reasons,setReasons]=useState({});
  const ch=(key,val)=>setForm(s=>({...s,[key]:val,
    ...(key==='direction'?{documentId:''}:{})}));
  const rows=asList(view.installmentPlans);
  const documents=asList(view[form.direction==='receipt'?'invoices':'bills'])
    .filter(d=>d.status==='issued'&&d.allocated+(d.returnedAmount||0)<d.total);
  return <section>
    <h2>دفتر اقساط و سررسید مطالبات و بدهی‌ها</h2>
    <Err>برنامه اقساط صرفاً سررسید پرداخت‌ها را مشخص می‌کند؛ بدهکاری جدید ایجاد
      نمی‌کند. دریافت واقعی با همان عملیات دریافت/پرداخت استاندارد ثبت می‌شود.</Err>
    <Table cols={['شناسه','فاکتور','باقی‌مانده','موعدهای باقیمانده','وضعیت','عملیات']}
      rows={rows.map(plan=>{
        const doc=view[plan.direction==='receipt'?'invoices':'bills'][plan.documentId];
        const already=Math.max(0,(doc?.allocated||0)-plan.initialAllocated);
        let paid=already;
        const parts=plan.schedule.map(s=>{
          const allocated=Math.min(s.amount,paid);paid-=allocated;
          return {...s,remaining:s.amount-allocated};
        });
        const outstanding=parts.reduce((s,x)=>s+x.remaining,0);
        const due=parts.filter(x=>x.remaining>0).map(x=>
          displayAccountingDate(x.dueDate)+(x.dueDate<today?' (سررسید گذشته)':'')+
          ' / '+money(x.remaining,unit));
        return {id:plan.id,search:plan.id+' '+plan.documentId,
          cells:[plan.id,plan.documentId,money(outstanding,unit),
            <ul>{due.map((x,i)=><li key={i}>{x}</li>)}</ul>,
            plan.active?'فعال':'لغوشده',
            plan.active&&canManage?<div className="sac-cheque-actions">
              <input value={reasons[plan.id]||''} placeholder="علت فسخ برنامه"
                onChange={e=>setReasons(p=>({...p,[plan.id]:e.target.value}))}/>
              <button disabled={disabled||!(reasons[plan.id]||'').trim()}
                onClick={()=>void sendCommand(execute,'installments.cancel',{
                  planId:plan.id,reason:reasons[plan.id].trim()})}>لغو برنامه</button>
            </div>:null]};
      })}/>
    <InlineForm title="ایجاد برنامه اقساط" canManage={canManage} disabled={disabled}
      onSubmit={async()=>{
        const schedule=form.schedule.split(/\r?\n/).filter(x=>x.trim()).map(s=>{
          const [solar,value,...extra]=s.split(';').map(x=>x.trim());
          const dueDate=parseAccountingJalali(solar)||
            (/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(solar)?solar:null);
          if(extra.length||!dueDate||!value)
            throw Error('هر قسط یک تاریخ شمسی معتبر و مبلغ لازم دارد.');
          return {dueDate,amount:numberOf(value)};
        });
        const ok=await sendCommand(execute,'installments.create',{
          planId:form.planId,direction:form.direction,documentId:form.documentId,
          schedule});
        if(ok)setForm(s=>({...s,planId:'',schedule:''}));
      }}>
      <Input label="کد برنامه" value={form.planId} onChange={v=>ch('planId',v)}/>
      <Input label="نوع" value={form.direction} onChange={v=>ch('direction',v)}
        options={<><option value="receipt">دریافت از مشتری</option><option value="payment">پرداخت به تأمین‌کننده</option></>}/>
      <Input label="فاکتور صادرشده" value={form.documentId}
        onChange={v=>ch('documentId',v)} options={opt(documents,'انتخاب فاکتور')}/>
      <label className="sac-field"><span>اقساط (هر سطر: تاریخ شمسی؛ مبلغ صحیح)</span>
        <textarea required rows={4} dir="ltr"
          placeholder={'۱۴۰۵/۰۸/۱۰;500000\n۱۴۰۵/۰۹/۱۰;500000'}
          value={form.schedule} onChange={e=>ch('schedule',e.target.value)}/>
        <small>مجموع مبالغ باید دقیقاً برابر ماندهٔ تسویه‌نشده سند باشد.</small>
      </label>
    </InlineForm>
  </section>;
}

export function PayrollAndTax({view,canManage,canSetTax=canManage,disabled,execute,today,unit}){
  const [pay,setPay]=useState({payrollId:'',employeeId:'',
    period:parseAccountingJalali(formatAccountingJalali(today,{digits:'ascii'}).slice(0,7)+'/01')||today,
    gross:'',withholding:'0',reason:''});
  const [rule,setRule]=useState({ruleId:'',name:'',rateBasisPoints:'',
    effectiveFrom:today,reason:''});
  const [bank,setBank]=useState('1010');
  const [statementDate,setStatementDate]=useState(today);
  const ch=(key,val)=>setPay(p=>({...p,[key]:val}));
  const rules=asList(view.taxRules);
  return <section>
    <h2>حقوق و دستمزد، بدهی کارکنان و سیاست مالیات</h2>
    <Err>این ماژول ثبت حسابداری ناخالص حقوق، کسورات صریح و پرداخت خالص را انجام می‌دهد.
      محاسبات بیمه، عیدی، سنوات، نرخ‌های مالیات و گزارش‌های رسمی ایران خودکار/تأییدشده نیست.
      سیاست‌های مالیات این قسمت صرفاً نرخ‌هایی هستند که حسابدار با سند تعیین می‌کند.</Err>
    <Table cols={['شناسه','کارمند','ماه','ناخالص','کسورات','خالص','وضعیت','پرداخت']}
      rows={asList(view.payroll).map(p=>({id:p.id,search:p.id+' '+p.employeeId,
        cells:[p.id,p.employeeId,p.period,money(p.gross,unit),money(p.withholding,unit),
          money(p.net,unit),p.status,
          p.status==='accrued'&&canManage?<div className="sac-cheque-actions">
            <select value={bank} onChange={e=>setBank(e.target.value)}>
              {opt(asList(view.accounts).filter(a=>a.liquid),'حساب پرداخت')}</select>
            <AccountingJalaliField max={today} value={statementDate}
              onChange={setStatementDate}/>
            <button disabled={disabled} onClick={()=>void sendCommand(execute,'payroll.pay',{
              payrollId:p.id,accountId:bank,postingDate:statementDate})}>پرداخت خالص حقوق</button>
          </div>:
          p.status==='paid'&&p.withholding>0&&!p.remittanceJournalId&&canManage?
            <button type="button" disabled={disabled}
              onClick={()=>void sendCommand(execute,'payroll.remit',{
                payrollId:p.id,accountId:bank,postingDate:statementDate})}>
              پرداخت کسورات به ذی‌نفع</button>:null,
        ]}))}/>
    <InlineForm title="ثبت سند حقوق و کسورات" canManage={canManage} disabled={disabled}
      onSubmit={async()=>{
        const ok=await sendCommand(execute,'payroll.accrue',{
          payrollId:pay.payrollId,employeeId:pay.employeeId,
          period:pay.period,gross:numberOf(pay.gross),
          withholding:numberOf(pay.withholding),reason:pay.reason.trim()});
        if(ok)setPay(p=>({...p,payrollId:'',gross:'',withholding:'0',reason:''}));
      }}>
      <Input label="شناسه لیست حقوق" value={pay.payrollId} onChange={v=>ch('payrollId',v)}/>
      <Input label="شناسه کارمند" value={pay.employeeId} onChange={v=>ch('employeeId',v)}/>
      <SolarDate label="اول ماه حقوق" value={pay.period} onChange={v=>ch('period',v)}
        limit={today}/>
      <Input label={'ناخالص ('+unit+')'} value={pay.gross} kind="number"
        onChange={v=>ch('gross',v)}/>
      <Input label={'کسورات صریح ('+unit+')'} value={pay.withholding} kind="number"
        onChange={v=>ch('withholding',v)}/>
      <Input label="دلیل ثبت و تأیید حقوق" value={pay.reason}
        onChange={v=>ch('reason',v)}/>
    </InlineForm>
    <h3>قواعد مالیاتی تعریف‌شده توسط حسابدار</h3>
    <Table cols={['کد','عنوان','نرخ درصدی','تاریخ اجرای شمسی','سوابق']}
      rows={rules.map(r=>({id:r.id,search:r.id+' '+r.name,cells:[
        r.id,r.name,(r.rateBasisPoints/100).toLocaleString('fa-IR')+'٪',
        displayAccountingDate(r.effectiveFrom),r.history.length.toLocaleString('fa-IR'),
      ]}))}/>
    <InlineForm title="ثبت / بازنگری سیاست مالیات" canManage={canSetTax} disabled={disabled}
      onSubmit={async()=>{
        const ok=await sendCommand(execute,'tax.rule.set',{
          ruleId:rule.ruleId,name:rule.name,
          rateBasisPoints:numberOf(rule.rateBasisPoints),
          effectiveFrom:rule.effectiveFrom,reason:rule.reason.trim()});
        if(ok)setRule(x=>({...x,ruleId:'',rateBasisPoints:'',reason:''}));
      }}>
      <Input label="شناسه قانون داخلی" value={rule.ruleId}
        onChange={v=>setRule(x=>({...x,ruleId:v}))}/>
      <Input label="عنوان" value={rule.name}
        onChange={v=>setRule(x=>({...x,name:v}))}/>
      <Input label="نرخ برحسب یک‌ده‌هزار (۶۰۰ = ۶٪)"
        kind="number" value={rule.rateBasisPoints}
        onChange={v=>setRule(x=>({...x,rateBasisPoints:v}))}/>
      <SolarDate label="تاریخ اجرا" value={rule.effectiveFrom}
        onChange={v=>setRule(x=>({...x,effectiveFrom:v}))}/>
      <Input label="مبنای تصمیم و علت تغییر" value={rule.reason}
        onChange={v=>setRule(x=>({...x,reason:v}))}/>
    </InlineForm>
  </section>;
}

export function FiscalYearClose({view,canManage,disabled,execute,today}){
  const solarYear=Number(formatAccountingJalali(today,{digits:'ascii'}).slice(0,4));
  const defaultStart=parseAccountingJalali((solarYear-1)+'/01/01')||today.slice(0,4)+'-01-01';
  const defaultEnd=parseAccountingJalali((solarYear-1)+'/12/30')||
    parseAccountingJalali((solarYear-1)+'/12/29')||today;
  const [startDate,setStartDate]=useState(()=>{
    if(!view.closedThrough)return defaultStart;
    const d=new Date(view.closedThrough+'T00:00:00Z');
    d.setUTCDate(d.getUTCDate()+1);return d.toISOString().slice(0,10);
  });
  const [throughDate,setThroughDate]=useState(defaultEnd);
  const [periodId,setPeriodId]=useState('');
  const [reason,setReason]=useState('');
  return <section>
    <h3>اختتامیه سال مالی و انتقال خودکار مانده به دوره بعد</h3>
    <Err>آغاز و پایان دوره با تاریخ شمسی انتخاب می‌شود. بازه باید پیوسته
      و فاقد سند قدیمی بیرون از دوره باشد. درآمد و هزینه با سند متوازن بسته
      می‌شوند و مانده دارایی/بدهی بدون سند تکراری به دوره بعد انتقال می‌یابد.</Err>
    <Table cols={['شناسه دوره','شروع شمسی','پایان شمسی','رویداد','سند اختتامیه','دلیل']}
      rows={(view.fiscalYears||[]).map(row=>({id:row.eventId,search:row.eventId,
        cells:[row.periodId||'—',displayAccountingDate(row.startDate),
          displayAccountingDate(row.throughDate),
          row.eventId,row.journalId||'بدون گردش',row.reason]}))}/>
    <InlineForm title="ثبت اختتامیه و قفل سال" canManage={canManage} disabled={disabled}
      onSubmit={async()=>{
        if(!globalThis.confirm?.('بستن قطعی سال و صفرکردن مانده حساب‌های درآمد/هزینه انجام شود؟'))return;
        const success=await sendCommand(execute,'fiscal.year.close',{
          startDate,throughDate,...(periodId.trim()?{periodId:periodId.trim()}:{}),
          reason:reason.trim()},
          'سند اختتامیه ثبت و سال مالی قفل شد.');
        if(success)setReason('');
      }}>
      <Input label="شناسه دوره مالی (اختیاری)" required={false} value={periodId}
        onChange={setPeriodId}/>
      <SolarDate label="اولین روز دوره مالی" value={startDate}
        onChange={setStartDate} limit={today}/>
      <SolarDate label="آخرین روز سال مالی" value={throughDate} onChange={setThroughDate}
        limit={today}/>
      <Input label="علت و مرجع تصویب اختتامیه" value={reason} onChange={setReason}/>
    </InlineForm>
  </section>;
}

export function CompanyProfile({view,canManage,disabled,execute}){
  const company=view.companyProfile||null;
  const empty={legalName:'',address:'',phone:'',nationalId:'',
    economicCode:'',postalCode:'',reason:''};
  const [form,setForm]=useState(empty);
  useEffect(()=>setForm({...empty,...company,reason:''}),[
    company?.history?.length,
  ]);
  const ch=(key,value)=>setForm(x=>({...x,[key]:value}));
  return <section>
    <h2>مشخصات واحد اقتصادی و سربرگ اسناد</h2>
    <Err>اطلاعات این بخش در چاپ فاکتور استفاده می‌شود. ثبت آن به معنای
      اعتبارسنجی دولتی یا ثبت خودکار در سامانه مؤدیان نیست. هر ویرایش علت دارد.</Err>
    {company&&<section className="sac-panel">
      <h3>{company.legalName}</h3>
      <p>شناسه ملی: {company.nationalId||'ثبت نشده'} | شناسه اقتصادی: {
        company.economicCode||'ثبت نشده'} | کد پستی: {company.postalCode||'ثبت نشده'}</p>
      <p>نشانی: {company.address||'ثبت نشده'} | تلفن: {company.phone||'ثبت نشده'}</p>
      <p>تعداد ویرایش‌های دارای سابقه: {
        company.history.length.toLocaleString('fa-IR')}</p>
    </section>}
    <InlineForm title={company?'ویرایش سربرگ شرکت':'ثبت مشخصات شرکت'}
      canManage={canManage} disabled={disabled}
      onSubmit={async()=>{
        const result=await sendCommand(execute,'company.profile.set',{
          legalName:form.legalName,address:form.address,phone:form.phone,
          nationalId:form.nationalId,economicCode:form.economicCode,
          postalCode:form.postalCode,reason:form.reason.trim()});
        if(result)setForm(x=>({...x,reason:''}));
      }}>
      {[
        ['legalName','عنوان رسمی/تجاری',true],
        ['nationalId','شناسه ملی/ثبت',false],
        ['economicCode','شناسه اقتصادی',false],
        ['postalCode','کدپستی',false],
        ['phone','شماره تماس',false],
        ['address','نشانی',false],
        ['reason','دلیل ثبت/تغییر',true],
      ].map(([key,label,required])=><Input key={key} label={label}
        value={form[key]||''} required={required} onChange={v=>ch(key,v)}/>)}
    </InlineForm>
  </section>;
}
