import React,{useEffect,useMemo,useRef,useState} from 'react';
import {ArrowRight,BookOpen,Building2,ChartNoAxesCombined,FileText,Package,RefreshCw,ShieldAlert,Wallet} from 'lucide-react';
import {MONEY_UNITS,parseMoneyInput,formatLegacyMoney,formatLegacyEntry,convertTypedMoney} from './ir_money_display.js';
import {inspectBackupFileLocally} from './parsian_local_backup_preflight.js';
import AccountingJalaliField from './accounting_jalali_field.jsx';
import {displayAccountingDate} from './accounting_jalali_dates.js';
import './accounting_workspace.css';

const TABS=[
  ['overview','داشبورد'],['sales','فروش و فاکتورها'],['purchases','خرید و خدمات دریافتی'],
  ['manual','فاکتور مستقل'],['items','کالا و خدمات'],
  ['parties','اشخاص و طرف‌حساب‌ها'],['accounts','حساب‌ها و دفترکل'],
  ['payments','دریافت و پرداخت'],['reports','گزارش‌ها'],['migration','مهاجرت و پشتیبان']
];
const ID_RE=/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/;
const MAX_TOMAN=10**15;
const todayLocal=()=>{const d=new Date();return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');};
export const parseWholeToman=(s,{allowZero=false}={})=>{
  if(typeof s!=='string'&&typeof s!=='number')return null;
  const value=String(s).trim().replace(/[۰-۹]/g,c=>String(c.charCodeAt(0)-1776))
    .replace(/[٠-٩]/g,c=>String(c.charCodeAt(0)-1632)).replace(/٬/g,',');
  if(!/^(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)$/.test(value))return null;
  const n=Number(value.replace(/,/g,''));
  return Number.isSafeInteger(n)&&n<=MAX_TOMAN&&(allowZero||n>0)?n:null;
};
const integer=parseWholeToman;
export const validAccountingDate=(date,today=todayLocal())=>{
  if(typeof date!=='string'||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(date)||date>today)return false;
  const [y,m,d]=date.split('-').map(Number),day=new Date(Date.UTC(y,m-1,d));
  return day.getUTCFullYear()===y&&day.getUTCMonth()===m-1&&day.getUTCDate()===d;
};
export const outstandingAccountingDocuments=(documents,kind,projectId='')=>{
  const targetKind=kind==='receipt'?'sales':kind==='payment'?'purchase':null;
  if(!Array.isArray(documents)||!targetKind)return [];
  return documents.filter(d=>d&&d.kind===targetKind&&d.status==='Issued'&&
    (!projectId||d.projectId===projectId)&&ID_RE.test(d.id||'')&&
    ID_RE.test(d.party?.id||'')&&Number.isSafeInteger(d.total)&&
    Number.isSafeInteger(d.allocated)&&d.total>0&&d.allocated>=0&&d.allocated<d.total);
};
export const buildSettlementCommand=({kind,document,amount,accountId,postingDate,eventId,today=todayLocal()})=>{
  if(!['receipt','payment'].includes(kind))return {error:'نوع تسویه معتبر نیست.'};
  if(!document||!outstandingAccountingDocuments([document],kind,document.projectId).length)
    return {error:'فاکتور صادرشده با مانده مثبت را صریحاً انتخاب کنید.'};
  const paid=integer(amount);
  if(paid===null||paid>document.total-document.allocated)return {error:'مبلغ باید صحیح، مثبت و حداکثر برابر مانده فاکتور باشد.'};
  if(!['1010','1000'].includes(accountId))return {error:'حساب نقد یا بانک معتبر نیست.'};
  if(!validAccountingDate(postingDate,today)||!validAccountingDate(document.postingDate,today)||postingDate<document.postingDate)
    return {error:'تاریخ تسویه باید معتبر و بین تاریخ صدور فاکتور و امروز باشد.'};
  if(!ID_RE.test(eventId||''))return {error:'شناسه عملیات معتبر نیست.'};
  const sales=kind==='receipt';
  return {error:'',command:{type:sales?'receipt.record':'payment.record',eventId,
    [sales?'receiptId':'paymentId']:eventId,partyId:document.party.id,
    accountId,postingDate,allocations:[{[sales?'invoiceId':'billId']:document.id,amount:paid}]}};
};
export const buildItemCreateCommand=({itemId,sku,name,kind,unit,eventId})=>{
  if(!ID_RE.test(itemId||'')||!ID_RE.test(eventId||'')||!['goods','service'].includes(kind)||
     !sku?.trim()||sku.trim().length>64||!name?.trim()||name.trim().length>200||
     !unit?.trim()||unit.trim().length>40)
    return {error:'شناسه، کد کالا، نام، نوع و واحد معتبر الزامی است.'};
  return {error:'',command:{type:'item.create',eventId,itemId,sku:sku.trim(),
    name:name.trim(),kind,unit:unit.trim()}};
};
export const buildStandaloneDocumentCommand=({kind,projectId,partyId,documentDate,
  description,quantity,unitPrice,discount='0',tax='0',itemId='',note='',eventId,
  items={},today=todayLocal()})=>{
  if(!['sales','purchase'].includes(kind)||!ID_RE.test(projectId||'')||
     !ID_RE.test(partyId||'')||!ID_RE.test(eventId||''))
    return {error:'نوع سند، پروژه و شناسه طرف‌حساب معتبر لازم است.'};
  if(!validAccountingDate(documentDate,today))return {error:'تاریخ فاکتور معتبر و غیرآینده باشد.'};
  if(typeof description!=='string'||!description.trim()||description.trim().length>200||
     typeof note!=='string'||note.length>1000)
    return {error:'شرح ردیف باید معتبر و یادداشت حداکثر هزار نویسه باشد.'};
  if(itemId&&(!ID_RE.test(itemId)||!items?.[itemId]||items[itemId].active!==true))
    return {error:'شناسه کالای انتخابی معتبر و فعال نیست.'};
  const qty=integer(quantity),price=integer(unitPrice),deduction=integer(discount,{allowZero:true}),
    taxValue=integer(tax,{allowZero:true});
  if(qty===null||qty>1000000||price===null||deduction===null||taxValue===null)
    return {error:'تعداد ۱ تا یک میلیون و تمام مبلغ‌ها باید عدد صحیح معتبر باشند.'};
  const subtotal=BigInt(qty)*BigInt(price);
  if(subtotal>BigInt(MAX_TOMAN)||BigInt(deduction)>subtotal)return {error:'مبلغ ردیف یا تخفیف از سقف مجاز بیشتر است.'};
  const total=subtotal-BigInt(deduction)+BigInt(taxValue);
  if(total<=0n||total>BigInt(MAX_TOMAN))return {error:'جمع نهایی باید مثبت و در محدوده مجاز باشد.'};
  return {error:'',total:Number(total),command:{type:'document.create',eventId,
    documentId:eventId,projectId,kind,partyId,documentDate,
    lines:[{description:description.trim(),quantity:qty,unitPrice:price,
      ...(itemId?{itemId}:{})}],discount:deduction,tax:taxValue,
    ...(note.trim()?{note:note.trim()}:{})}};
};
const nextEvent=prefix=>prefix+'-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
const normalizeSnapshot=v=>({
  documents:Array.isArray(v?.documents)?v.documents:[],
  purchaseIntakes:Array.isArray(v?.purchaseIntakes)?v.purchaseIntakes:[],
  balances:Array.isArray(v?.balances)?v.balances:[],
  accounts:v?.trialBalance&&typeof v.trialBalance==='object'?v.trialBalance:{},
  journals:Array.isArray(v?.journals)?v.journals:[],
  receipts:v?.receipts&&typeof v.receipts==='object'?v.receipts:{},
  payments:v?.payments&&typeof v.payments==='object'?v.payments:{},
  items:v?.items&&typeof v.items==='object'&&!Array.isArray(v.items)?v.items:{},
  parties:v?.parties&&typeof v.parties==='object'&&!Array.isArray(v.parties)?v.parties:{},
  reports:v?.reports&&typeof v.reports==='object'?v.reports:null,
  scope:v?.partyBalancesScope||'all-projects',
  closedThrough:v?.closedThrough||null
});

function Pane({children,title,description}){
  return <section className="accw-pane"><div className="accw-pane-head"><h2>{title}</h2>{description&&<p>{description}</p>}</div>{children}</section>;
}
function Empty({children}){return <p className="accw-empty">{children}</p>;}
function Status({status,onRetry}){return <div className="accw-status" role={status.error?'alert':'status'} aria-live="polite">
  {status.loading?'در حال دریافت اطلاعات از دفترکل...':status.error||status.message||'اطلاعات از پایگاه حسابداری دریافت شد.'}
  {status.error&&<button type="button" onClick={onRetry}>تلاش مجدد</button>}
</div>;}

/** Full-screen route, never an overlay on a task board. All mutations go to
 * the already-admin-gated host accountingCommand and finance CAS. */
export function AccountingWorkspace({api,projects=[],tasks=[],canManage=false,onExit=()=>{},initialSource=null}){
  // Display/entry unit only. The existing accountingCommand interface is TOMAN.
  const [moneyUnit,setMoneyUnit]=useState('TOMAN');
  const [parsianProbe,setParsianProbe]=useState({status:'idle',message:''});
  const [tab,setTab]=useState(['receipt','payment'].includes(initialSource?.kind)?'payments':
    initialSource?.kind==='manual'?'manual':initialSource?.kind==='items'?'items':
    initialSource?.kind==='purchase'?'purchases':initialSource?.kind==='sales'?'sales':'overview');
  const [projectId,setProjectId]=useState(initialSource?.projectId||'');
  const [snapshot,setSnapshot]=useState(normalizeSnapshot(null));
  const [status,setStatus]=useState({loading:true,error:'',message:''});
  const [refreshIndex,setRefreshIndex]=useState(0);
  const [loadedScope,setLoadedScope]=useState(null);
  const [settlementKind,setSettlementKind]=useState(initialSource?.kind==='payment'?'payment':'receipt');
  const [settlementDocumentId,setSettlementDocumentId]=useState(initialSource?.documentId||'');
  const [settlementAmount,setSettlementAmount]=useState('');
  const [settlementAccount,setSettlementAccount]=useState('1010');
  const [settlementDate,setSettlementDate]=useState(todayLocal);
  const [fundAmount,setFundAmount]=useState('');
  const [fundNote,setFundNote]=useState('');
  const [fundAccount,setFundAccount]=useState('1010');
  const [fundDate,setFundDate]=useState(todayLocal);
  const [itemId,setItemId]=useState('');
  const [itemSku,setItemSku]=useState('');
  const [itemName,setItemName]=useState('');
  const [itemKind,setItemKind]=useState('service');
  const [itemUnit,setItemUnit]=useState('عدد');
  const [manualKind,setManualKind]=useState('sales');
  const [manualProject,setManualProject]=useState(initialSource?.projectId||'');
  const [manualParty,setManualParty]=useState('');
  const [manualItem,setManualItem]=useState('');
  const [manualDescription,setManualDescription]=useState('');
  const [manualQuantity,setManualQuantity]=useState('1');
  const [manualUnitPrice,setManualUnitPrice]=useState('');
  const [manualDiscount,setManualDiscount]=useState('0');
  const [manualTax,setManualTax]=useState('0');
  const [manualNote,setManualNote]=useState('');
  const [manualDate,setManualDate]=useState(todayLocal);
  const [reportAccountId,setReportAccountId]=useState('');
  const [taskId,setTaskId]=useState(initialSource?.cardId||'');
  const [quantity,setQuantity]=useState(String(initialSource?.quantity||1));
  const [unitPrice,setUnitPrice]=useState(String(initialSource?.unitPrice||''));
  const [supplierId,setSupplierId]=useState('');
  const [supplierName,setSupplierName]=useState('');
  const [customerId,setCustomerId]=useState('');
  const [customerName,setCustomerName]=useState('');
  const [newPartyKind,setNewPartyKind]=useState('customer');
  const [newPartyId,setNewPartyId]=useState('');
  const [newPartyName,setNewPartyName]=useState('');
  const [newAccountId,setNewAccountId]=useState('');
  const [newAccountName,setNewAccountName]=useState('');
  const [newAccountKind,setNewAccountKind]=useState('expense');
  const [stepId,setStepId]=useState(initialSource?.stepId||'');
  const [priceInputs,setPriceInputs]=useState({});
  const [working,setWorking]=useState(false);
  const [notice,setNotice]=useState('');
  const inFlight=useRef(false);
  const retryToken=useRef(null);
  const money=n=>formatLegacyMoney(n,moneyUnit);
  const signedMoney=n=>formatLegacyMoney(n,moneyUnit,{fallback:'نامشخص'});
  const readAmount=(value,allowZero=false)=>parseMoneyInput(value,moneyUnit,{allowZero});
  const moneyArg=(value,allowZero=false)=>{
    const parsed=readAmount(value,allowZero);
    return parsed.error?'':String(parsed.amount);
  };
  const changeMoneyUnit=next=>{
    if(next===moneyUnit||!Object.hasOwn(MONEY_UNITS,next)||working||inFlight.current)return;
    let cleared=false;
    const convert=(setter,value)=>{
      const outcome=convertTypedMoney(value,moneyUnit,next);
      cleared ||= outcome.cleared;
      setter(outcome.value);
    };
    // All amount inputs change unit in the same React event batch.
    convert(setSettlementAmount,settlementAmount);
    convert(setFundAmount,fundAmount);
    convert(setManualUnitPrice,manualUnitPrice);
    convert(setManualDiscount,manualDiscount);
    convert(setManualTax,manualTax);
    convert(setUnitPrice,unitPrice);
    const nextPriceInputs=Object.fromEntries(Object.entries(priceInputs).map(([key,value])=>{
      const outcome=convertTypedMoney(value,moneyUnit,next);
      cleared ||= outcome.cleared;
      return [key,outcome.value];
    }));
    setPriceInputs(nextPriceInputs);
    setMoneyUnit(next);
    setNotice(cleared?'واحد پول تغییر کرد. ورودی‌های مبلغی نامعتبر پاک شدند؛ مبلغ‌ها را دوباره وارد کنید.':
      'واحد نمایش و ورود تغییر کرد. ارقام موجود بدون گرد کردن تبدیل شدند؛ ذخیره‌سازی دفترکل فعلی همچنان تومان است.');
  };
  const selectedTask=tasks.find(t=>t.id===taskId && (!projectId||t.projectId===projectId));
  const steps=useMemo(()=>selectedTask?.checklist?.filter(x=>x.id&&x.text) ||[],[selectedTask]);
  const sourceDescription=selectedTask?.title||'';
  const availableTasks=tasks.filter(t=>!projectId||t.projectId===projectId).filter(t=>t.deleted!==true);
  const projectsList=projects;
  const readReady=canManage&&!status.loading&&!status.error&&loadedScope===projectId;
  const shown=readReady?snapshot:normalizeSnapshot(null);
  const settlementCandidates=outstandingAccountingDocuments(shown.documents,settlementKind,projectId);
  const settlementTarget=settlementCandidates.find(d=>d.id===settlementDocumentId);
  const settlementParsed=readAmount(settlementAmount);
  const settlementError=(settlementAmount&&settlementParsed.error)||
    buildSettlementCommand({kind:settlementKind,document:settlementTarget,
      amount:settlementParsed.error?'':String(settlementParsed.amount),accountId:settlementAccount,
      postingDate:settlementDate,eventId:'preview'}).error;
  const fundParsed=readAmount(fundAmount);
  const manualParsed=[readAmount(manualUnitPrice),readAmount(manualDiscount,true),readAmount(manualTax,true)];
  const manualMoneyError=[manualUnitPrice,manualDiscount,manualTax]
    .map((raw,i)=>raw?manualParsed[i].error:'').find(Boolean)||'';
  const manualPreview=buildStandaloneDocumentCommand({kind:manualKind,
    projectId:projectId||manualProject,partyId:manualParty,documentDate:manualDate,
    description:manualDescription,quantity:manualQuantity,unitPrice:moneyArg(manualUnitPrice),
    discount:moneyArg(manualDiscount,true),tax:moneyArg(manualTax,true),
    itemId:manualItem,note:manualNote,
    eventId:'preview',items:shown.items});
  useEffect(()=>{
    let cancelled=false;
    if(!canManage){setLoadedScope(null);setStatus({loading:false,error:'دسترسی حسابداری فقط برای افراد مجاز است.',message:''});return;}
    setLoadedScope(null);
    setStatus({loading:true,error:'',message:''});
    Promise.resolve().then(()=>{
      if(typeof api?.accountingRead!=='function')throw Error('سرویس خواندن حسابداری در میزبان متصل نیست.');
      return api.accountingRead(projectId);
    }).then(data=>{
      if(!data||!Array.isArray(data.documents)||!Array.isArray(data.balances))throw Error('پاسخ خواندن حسابداری ناقص است.');
      if(!cancelled){setSnapshot(normalizeSnapshot(data));setLoadedScope(projectId);setStatus({loading:false,error:'',message:''});}
    }).catch(error=>{
      if(!cancelled){setLoadedScope(null);setStatus({loading:false,error:String(error?.message||error),message:''});}
    });
    return()=>{cancelled=true;};
  },[api,canManage,projectId,refreshIndex]);
  const reload=()=>setRefreshIndex(x=>x+1);
  const submit=async command=>{
    if(inFlight.current || !readReady || !canManage || typeof api?.accountingCommand!=='function'){
      setNotice('اطلاعات حسابداری آماده نیست یا عملیات دیگری در جریان است.');return false;
    }
    // The receipt/payment identifier must match the durable event identifier
    // even on an uncertain-network retry. Never regenerate one without the other.
    const settlement=command.type==='receipt.record'||command.type==='payment.record';
    const standalone=command.type==='document.create';
    const {eventId,receiptId:ignoredReceipt,paymentId:ignoredPayment,
      documentId:ignoredDoc,...payload}=command;
    if(!ID_RE.test(eventId||'')){setNotice('شناسه عملیات معتبر نیست.');return false;}
    if(!standalone&&ignoredDoc!==undefined)payload.documentId=ignoredDoc;
    const identity=JSON.stringify(payload);
    if(retryToken.current?.identity!==identity)
      retryToken.current={identity,eventId};
    const authoritativeCommand={...payload,eventId:retryToken.current.eventId,
      ...(settlement?{[command.type==='receipt.record'?'receiptId':'paymentId']:retryToken.current.eventId}:{}),
      ...(standalone?{documentId:retryToken.current.eventId}:{})};
    inFlight.current=true;setWorking(true);setNotice('');
    try{
      const result=await api.accountingCommand(authoritativeCommand);
      retryToken.current=null;
      setLoadedScope(null);
      setNotice('در دفترکل ذخیره شد. '+(result?.documentId?'شماره شناسه: '+result.documentId:''));
      reload();
      return true;
    }catch(error){setNotice('نتیجه عملیات نامشخص است: '+String(error?.message||error)+'؛ برای تلاش دوباره اطلاعات را بدون تغییر نگه دارید.');return false;}
    finally{inFlight.current=false;setWorking(false);}
  };
  const recordSettlement=async event=>{
    event.preventDefault();
    if(!readReady){setNotice('ابتدا داده‌ها را تازه‌سازی کنید.');return;}
    if(settlementParsed.error){setNotice(settlementParsed.error);return;}
    const built=buildSettlementCommand({kind:settlementKind,document:settlementTarget,
      amount:String(settlementParsed.amount),accountId:settlementAccount,
      postingDate:settlementDate,eventId:nextEvent('settlement')});
    if(built.error){setNotice(built.error);return;}
    const party=settlementTarget.party?.name||settlementTarget.party.id;
    const type=settlementKind==='receipt'?'دریافت از مشتری':'پرداخت به تأمین‌کننده';
    if(!window.confirm([type,party,settlementTarget.number||settlementTarget.id,
      money(built.command.allocations[0].amount),settlementDate].join(' | ')+'\nتأیید می‌کنید که وجه واقعاً جابه‌جا شده است؟'))return;
    if(await submit(built.command)){setSettlementDocumentId('');setSettlementAmount('');}
  };
  const recordDeposit=async event=>{
    event.preventDefault();
    if(fundParsed.error){setNotice(fundParsed.error);return;}
    const amount=fundParsed.amount;
    if(!amount||!fundNote.trim()||fundNote.trim().length>1000||
       !['1010','1000'].includes(fundAccount)||!validAccountingDate(fundDate)||!readReady){
      setNotice('برای ورود سرمایه، مبلغ مثبت، منبع وجه و تاریخ معتبر الزامی است.');return;
    }
    if(!window.confirm('ورود واقعی '+money(amount)+' به '+(fundAccount==='1010'?'بانک':'صندوق')+' تأیید می‌شود؟'))return;
    if(await submit({type:'funds.deposit',eventId:nextEvent('deposit'),accountId:fundAccount,
      amount,postingDate:fundDate,note:fundNote.trim()})){setFundAmount('');setFundNote('');}
  };
  const registerItem=async event=>{
    event.preventDefault();
    const built=buildItemCreateCommand({itemId,itemSku,name:itemName,kind:itemKind,
      unit:itemUnit,eventId:nextEvent('item')});
    if(built.error){setNotice(built.error);return;}
    if(Object.values(shown.items).some(item=>item.sku?.toLowerCase()===itemSku.trim().toLowerCase())){
      setNotice('کد کالا/خدمت تکراری است.');return;
    }
    if(await submit(built.command)){setItemId('');setItemSku('');setItemName('');}
  };
  const createStandalone=async event=>{
    event.preventDefault();
    if(manualMoneyError||manualPreview.error||!readReady){
      setNotice(manualMoneyError||manualPreview.error||'ابتدا داده‌های دفترکل را دریافت کنید.');return;
    }
    const found=shown.parties[manualParty];
    if(!found||!(found.kind===(manualKind==='sales'?'customer':'vendor')||found.kind==='both')){
      setNotice('طرف‌حساب ثبت‌شده و متناسب با نوع سند انتخاب کنید.');return;
    }
    if(!window.confirm('پیش‌نویس '+(manualKind==='sales'?'فروش':'خرید')+' به مبلغ '+money(manualPreview.total)+' برای '+found.name+' ساخته شود؟ صدور قطعی جداگانه انجام می‌شود.'))return;
    if(await submit({...manualPreview.command,eventId:nextEvent('doc')})){
      setManualDescription('');setManualUnitPrice('');setManualNote('');
    }
  };
  const createSale=()=>{
    const qty=integer(quantity), priceResult=readAmount(unitPrice),price=priceResult.amount;
    if(priceResult.error){setNotice(priceResult.error);return;}
    if(!selectedTask||!customerName.trim()||!customerId.trim()||!qty||!price){
      setNotice('کارت، مشتری، تعداد و قیمت واحد معتبر الزامی است.');return;
    }
    return submit({type:'draft.sales.fromTask',eventId:nextEvent('sale'),
      projectId:selectedTask.projectId,cardId:selectedTask.id,
      party:{id:customerId.trim(),name:customerName.trim(),reference:'',kind:'customer'},
      lines:[{id:'task-line',description:sourceDescription,quantity:qty,unitPrice:price}],
      discount:0,tax:0,advance:0});
  };
  const createIntake=()=>{
    const qty=integer(quantity);
    if(!selectedTask||!stepId||!qty||!supplierId.trim()||!supplierName.trim()){
      setNotice('مرحله، تعداد و حساب تأمین‌کننده الزامی است؛ قیمت لازم نیست.');return;
    }
    return submit({type:'intake.create',eventId:nextEvent('intake'),
      intakeId:nextEvent('work'),projectId:selectedTask.projectId,
      cardId:selectedTask.id,stepId,quantity:qty,
      supplier:{id:supplierId.trim(),name:supplierName.trim(),reference:'',kind:'supplier'}});
  };
  const issueable=shown.documents.filter(d=>['Draft','Review','Issued'].includes(d.status));
  if(!canManage)return <div className="accw-root" dir="rtl"><header><button type="button" onClick={onExit}>بازگشت به تسک‌منیجر</button></header><p role="alert">شما مجوز دسترسی به حسابداری را ندارید.</p></div>;
  return <div className="accw-root" dir="rtl">
    <aside className="accw-side" aria-label="بخش‌های حسابداری">
      <div className="accw-brand"><BookOpen size={26}/><strong>حسابداری مدار</strong><small>محیط مستقل حساب‌ها و اسناد</small></div>
      <button type="button" className="accw-exit" onClick={onExit}><ArrowRight size={16}/> بازگشت به تسک‌منیجر</button>
      <nav>{TABS.map(([id,label])=><button key={id} type="button" className={tab===id?'current':''} aria-current={tab===id?'page':undefined} onClick={()=>{setTab(id);setNotice('');}}>{label}</button>)}</nav>
      <small className="accw-sidefoot">واحد نمایشی: {MONEY_UNITS[moneyUnit]}. ذخیره‌سازی فعلی موتور حسابداری تومان است؛ پیش‌نویس بدهی قطعی نیست.</small>
    </aside>
    <main className="accw-main">
      <header className="accw-top"><div><span>فضای کاری حسابداری</span><h1>{TABS.find(([id])=>id===tab)?.[1]}</h1></div><div className="accw-top-actions">
        <label className="accw-currency-control">واحد نمایش و ورود
          <select aria-label="واحد پولی حسابداری" value={moneyUnit} disabled={working} onChange={e=>changeMoneyUnit(e.target.value)}>
            <option value="TOMAN">تومان</option><option value="RIAL">ریال</option>
          </select>
        </label>
        <select aria-label="فیلتر پروژه در حسابداری" value={projectId} onChange={e=>{setProjectId(e.target.value);setTaskId('');setStepId('');setSettlementDocumentId('');setSettlementAmount('');setLoadedScope(null);setStatus({loading:true,error:'',message:''});}}>
          <option value="">تمام پروژه‌ها</option>{projectsList.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
        </select><button type="button" onClick={reload} disabled={status.loading}><RefreshCw size={16}/> تازه‌سازی</button></div>
      </header>
      <p className="accw-money-disclosure" role="note">مبالغ نمایش‌داده‌شده به {MONEY_UNITS[moneyUnit]} هستند. میزبان فعلی و داده‌های قدیمی به <strong>تومان صحیح</strong> کار می‌کنند؛ ورود ریال فقط در مضرب‌های ۱۰ پذیرفته می‌شود و هیچ مبلغی گرد نمی‌شود. این گزینه واحد پایه دفترکل را تغییر نمی‌دهد.</p>
      <Status status={status} onRetry={reload}/>
      {!!notice&&<p className="accw-notice" role="status">{notice}</p>}
      {tab==='overview'&&<Pane title="تصویر کلی دفترکل" description="اطلاعات ثبت‌شده؛ پیش‌نویس‌ها هنوز اثر حسابداری ندارند.">
        <div className="accw-kpis"><div><span>فاکتورهای مرتبط</span><strong>{shown.documents.length}</strong></div>
          <div><span>کارهای تأمین‌کننده بدون قیمت</span><strong>{shown.purchaseIntakes.filter(r=>r.status==='unpriced').length}</strong></div>
          <div><span>اسناد قیمت‌گذاری‌شده در انتظار تبدیل</span><strong>{shown.purchaseIntakes.filter(r=>r.status==='priced').length}</strong></div>
          <div><span>مانده‌های طرف‌حساب</span><strong>{shown.balances.length}</strong></div></div>
        <p>مانده حساب‌ها و تراز کل در سطح <strong>همه پروژه‌ها</strong> محاسبه می‌شود. فیلتر پروژه الزاماً به معنی تراز پروژه‌ای نیست.</p>
      </Pane>}
      {tab==='sales'&&<Pane title="فاکتور فروش از کارت" description="شرح از عنوان کارت خوانده می‌شود. تعداد و قیمت واحد قبل از ساخت پیش‌نویس قابل اصلاح‌اند.">
        <div className="accw-form">
          <label>کارت مرتبط<select value={taskId} onChange={e=>{const t=tasks.find(t=>t.id===e.target.value);setTaskId(e.target.value);setQuantity(String(t?.saleQuantity||1));setUnitPrice(formatLegacyEntry(t?.saleUnitPrice,moneyUnit));}}><option value="">انتخاب کارت</option>{availableTasks.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
          <label>شرح کالا یا خدمت<input value={sourceDescription} readOnly/></label>
          <label>تعداد<input inputMode="numeric" value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>
          <label>قیمت واحد ({MONEY_UNITS[moneyUnit]})<input inputMode="numeric" value={unitPrice} aria-invalid={unitPrice!==''&&!!readAmount(unitPrice).error} onChange={e=>setUnitPrice(e.target.value)}/></label>
          <label>شناسه مشتری<input value={customerId} onChange={e=>setCustomerId(e.target.value)} placeholder="شناسه موجود یا جدید"/></label>
          <label>نام مشتری<input value={customerName} onChange={e=>setCustomerName(e.target.value)}/></label>
          <button type="button" disabled={working||status.loading||!selectedTask} onClick={createSale}>ساخت پیش‌نویس فروش</button>
          {unitPrice&&readAmount(unitPrice).error&&<p className="accw-validation accw-form-hint" role="status">{readAmount(unitPrice).error}</p>}
        </div>
        <h3>اسناد فروش</h3>
        {issueable.filter(d=>d.kind==='sales').length?issueable.filter(d=>d.kind==='sales').map(d=><div className="accw-record" key={d.id}><strong>{d.party?.name||d.partyId}</strong><span>{d.status} · {money(d.total)}</span>{d.status==='Draft'&&<button onClick={()=>submit({type:'document.review',eventId:nextEvent('approve'),documentId:d.id,projectId:d.projectId})}>بررسی و تأیید</button>}{d.status==='Review'&&<button onClick={()=>submit({type:'document.issue',eventId:nextEvent('issue'),documentId:d.id,projectId:d.projectId,postingDate:new Date().toISOString().slice(0,10)})}>صدور سند</button>}</div>):<Empty>هنوز سند فروشی در این محدوده ثبت نشده است.</Empty>}
      </Pane>}
      {tab==='purchases'&&<Pane title="خرید و کارهای برون‌سپاری‌شده" description="ثبت اولیه فقط شرح، تعداد و تأمین‌کننده است. قیمت و سند پرداختنی بعداً تعیین می‌شود.">
        <div className="accw-form">
          <label>کارت<select value={taskId} onChange={e=>{setTaskId(e.target.value);setStepId('');}}><option value="">انتخاب کارت</option>{availableTasks.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
          <label>مرحله کار<select value={stepId} onChange={e=>setStepId(e.target.value)}><option value="">انتخاب مرحله</option>{steps.map(s=><option key={s.id} value={s.id}>{s.text}</option>)}</select></label>
          <label>تعداد<input inputMode="numeric" value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>
          <label>شناسه تأمین‌کننده<input value={supplierId} onChange={e=>setSupplierId(e.target.value)}/></label>
          <label>نام تأمین‌کننده<input value={supplierName} onChange={e=>setSupplierName(e.target.value)}/></label>
          <button type="button" disabled={working||status.loading||!selectedTask||!stepId} onClick={createIntake}>ثبت کار برای قیمت‌گذاری</button>
        </div>
        <h3>کارهای تحویلی تأمین‌کنندگان</h3>
        {shown.purchaseIntakes.length?shown.purchaseIntakes.map(row=><div className="accw-record" key={row.id}>
          <div><strong>{row.description}</strong><small>تأمین‌کننده: {row.supplier.name} · تعداد: {row.quantity.toLocaleString('fa-IR')}</small><small>وضعیت: {row.status} · {row.unitPrice===null?'بدون قیمت':money(row.unitPrice)+' برای هر واحد'}</small></div>
          {row.status==='unpriced'&&<div className="accw-record-actions"><input aria-label={'قیمت واحد '+row.description+' ('+MONEY_UNITS[moneyUnit]+')'} inputMode="numeric" aria-invalid={!!priceInputs[row.id]&&!!readAmount(priceInputs[row.id]).error} placeholder={'قیمت واحد '+MONEY_UNITS[moneyUnit]} value={priceInputs[row.id]||''} onChange={e=>setPriceInputs(p=>({...p,[row.id]:e.target.value}))}/><button type="button" disabled={working} onClick={()=>{const result=readAmount(priceInputs[row.id]);if(result.error){setNotice(result.error);return;}submit({type:'intake.price',eventId:nextEvent('price'),intakeId:row.id,unitPrice:result.amount});}}>ثبت قیمت</button>{priceInputs[row.id]&&readAmount(priceInputs[row.id]).error&&<small className="accw-validation" role="status">{readAmount(priceInputs[row.id]).error}</small>}</div>}
          {row.status==='priced'&&<button type="button" disabled={working} onClick={()=>submit({type:'intake.convert',eventId:nextEvent('convert'),intakeId:row.id})}>ساخت پیش‌نویس خرید</button>}
        </div>):<Empty>هنوز کار قیمت‌گذاری‌نشده‌ای ثبت نشده است.</Empty>}
        <h3>فاکتورهای خرید</h3>{issueable.filter(d=>d.kind==='purchase').map(d=><div className="accw-record" key={d.id}><strong>{d.party?.name||d.partyId}</strong><span>{d.status} · {money(d.total)}</span>{d.status==='Draft'&&<button type="button" onClick={()=>submit({type:'document.review',eventId:nextEvent('p-review'),documentId:d.id,projectId:d.projectId})}>تأیید</button>}{d.status==='Review'&&<button type="button" onClick={()=>submit({type:'document.issue',eventId:nextEvent('p-issue'),documentId:d.id,projectId:d.projectId,postingDate:new Date().toISOString().slice(0,10)})}>صدور خرید</button>}</div>)}
      </Pane>}
      {tab==='items'&&<Pane title="کاتالوگ کالا و خدمات" description="تعریف شناسه کالا یا خدمت برای استفاده در ردیف فاکتور. این فهرست موجودی انبار را ثبت یا کنترل نمی‌کند.">
        <form className="accw-form" aria-label="ثبت کالا یا خدمت" onSubmit={registerItem}>
          <label>شناسه داخلی<input required dir="ltr" maxLength={96} value={itemId} onChange={e=>setItemId(e.target.value)} placeholder="item-001"/></label>
          <label>کد کالا یا خدمت (SKU)<input required maxLength={64} value={itemSku} onChange={e=>setItemSku(e.target.value)} placeholder="PRINT-A4"/></label>
          <label>نام کالا یا خدمت<input required maxLength={200} value={itemName} onChange={e=>setItemName(e.target.value)}/></label>
          <label>دسته<select value={itemKind} onChange={e=>setItemKind(e.target.value)}><option value="goods">کالا</option><option value="service">خدمت</option></select></label>
          <label>واحد سنجش<input required maxLength={40} value={itemUnit} onChange={e=>setItemUnit(e.target.value)} placeholder="عدد، برگ، متر"/></label>
          <button type="submit" disabled={working||!readReady||!!buildItemCreateCommand({itemId,sku:itemSku,name:itemName,kind:itemKind,unit:itemUnit,eventId:'preview'}).error}>ثبت در کاتالوگ</button>
        </form>
        <h3>کاتالوگ ثبت‌شده</h3>
        {Object.values(shown.items).length?Object.values(shown.items).map(item=><div className="accw-record" key={item.id}>
          <div><strong>{item.name} · {item.sku}</strong><small>{item.kind==='service'?'خدمت':'کالا'} · {item.unit} · {item.active?'فعال':'غیرفعال'}</small><small>انبارداری: غیرقابل‌ردیابی در این نسخه</small></div>
          <button type="button" disabled={working||!readReady} onClick={()=>{
            if(window.confirm((item.active?'غیرفعال':'فعال')+' کردن این کالا/خدمت تأیید شود؟'))
              submit({type:'item.update',eventId:nextEvent('item-update'),itemId:item.id,active:!item.active});
          }}>{item.active?'غیرفعال‌کردن':'فعال‌کردن'}</button>
        </div>):<Empty>کالا یا خدمتی در کاتالوگ ثبت نشده است.</Empty>}
      </Pane>}
      {tab==='manual'&&<Pane title="پیش‌نویس فاکتور مستقل" description="فاکتور فروش یا خرید بدون الزام اتصال به کارت ساخته می‌شود. طرف‌حساب باید قبلاً در بخش اشخاص ثبت شده باشد؛ صدور قطعی جداگانه است.">
        <form className="accw-form" aria-label="ثبت مستقل پیش‌نویس فاکتور" onSubmit={createStandalone}>
          <label>نوع فاکتور<select value={manualKind} onChange={e=>{setManualKind(e.target.value);setManualParty('');}}><option value="sales">فروش</option><option value="purchase">خرید</option></select></label>
          <label>پروژه<select required value={projectId||manualProject} disabled={!!projectId} onChange={e=>setManualProject(e.target.value)}><option value="">انتخاب پروژه</option>{projectsList.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <label>طرف‌حساب ثبت‌شده<select required value={manualParty} onChange={e=>setManualParty(e.target.value)}><option value="">طرف‌حساب را انتخاب کنید</option>
            {Object.values(shown.parties).filter(p=>p.kind==='both'||p.kind===(manualKind==='sales'?'customer':'vendor')).map(p=><option key={p.id} value={p.id}>{p.name} · {p.id}</option>)}
          </select></label>
          <label>کالا/خدمت کاتالوگ (اختیاری)<select value={manualItem} onChange={e=>{
            setManualItem(e.target.value);if(e.target.value&&shown.items[e.target.value])setManualDescription(shown.items[e.target.value].name);
          }}><option value="">بدون کالای کاتالوگی</option>{Object.values(shown.items).filter(item=>item.active).map(item=><option key={item.id} value={item.id}>{item.name} · {item.sku}</option>)}</select></label>
          <label>شرح ردیف<input required maxLength={200} value={manualDescription} onChange={e=>setManualDescription(e.target.value)}/></label>
          <label>تعداد<input required type="text" dir="ltr" inputMode="numeric" value={manualQuantity} onChange={e=>setManualQuantity(e.target.value)}/></label>
          <label>قیمت واحد ({MONEY_UNITS[moneyUnit]})<input required type="text" dir="ltr" inputMode="numeric" value={manualUnitPrice} aria-invalid={manualUnitPrice!==''&&!!manualParsed[0].error} onChange={e=>setManualUnitPrice(e.target.value)}/></label>
          <label>تخفیف ({MONEY_UNITS[moneyUnit]})<input type="text" dir="ltr" inputMode="numeric" value={manualDiscount} aria-invalid={manualDiscount!==''&&!!manualParsed[1].error} onChange={e=>setManualDiscount(e.target.value)}/></label>
          <label>مالیات مبلغ صریح ({MONEY_UNITS[moneyUnit]})<input type="text" dir="ltr" inputMode="numeric" value={manualTax} aria-invalid={manualTax!==''&&!!manualParsed[2].error} onChange={e=>setManualTax(e.target.value)}/></label>
          <label>یادداشت (اختیاری)<input maxLength={1000} value={manualNote} onChange={e=>setManualNote(e.target.value)}/></label>
          <label>تاریخ فاکتور<AccountingJalaliField max={todayLocal()} value={manualDate} onChange={setManualDate}/></label>
          <p className="accw-form-hint">مالیات خودکار محاسبه نمی‌شود؛ مبلغ مالیات به‌صورت صریح وارد می‌شود.</p>
          <button type="submit" disabled={working||!readReady||!!manualPreview.error||!!manualMoneyError||!shown.parties[manualParty]}>ساخت پیش‌نویس مستقل</button>
        </form>
        {manualMoneyError||manualPreview.error?<p className="accw-validation" role="status">{manualMoneyError||manualPreview.error}</p>:
          <p className="accw-settlement-summary" role="status">جمع پیش‌نویس: {money(manualPreview.total)}. این هنوز سند صادرشده یا تسویه نیست.</p>}
        <p>برای بررسی و صدور پیش‌نویس ایجادشده به بخش «فروش و فاکتورها» یا «خرید و خدمات دریافتی» بروید.</p>
      </Pane>}
      {tab==='parties'&&<Pane title="طرف‌حساب‌ها" description="موجودی حساب‌ها بر مبنای دفترکل همه پروژه‌هاست.">
        <div className="accw-form">
          <label>شناسه طرف‌حساب<input value={newPartyId} onChange={e=>setNewPartyId(e.target.value)} placeholder="مثلاً person-001"/></label>
          <label>نام شخص یا شرکت<input value={newPartyName} onChange={e=>setNewPartyName(e.target.value)}/></label>
          <label>نوع<select value={newPartyKind} onChange={e=>setNewPartyKind(e.target.value)}><option value="customer">مشتری</option><option value="vendor">تأمین‌کننده</option><option value="both">مشتری و تأمین‌کننده</option></select></label>
          <button type="button" disabled={working||!newPartyId.trim()||!newPartyName.trim()} onClick={()=>submit({
            type:'party.register',eventId:nextEvent('party'),partyId:newPartyId.trim(),
            name:newPartyName.trim(),kind:newPartyKind})}>ثبت طرف‌حساب</button>
        </div>
        {shown.balances.length?shown.balances.map(b=><div className="accw-record" key={b.partyId}><strong>{b.name}</strong><span>دریافتنی: {money(b.receivable)} · پرداختنی: {money(b.payable)}</span></div>):<Empty>طرف‌حساب ثبت‌شده‌ای با مانده یا سند وجود ندارد.</Empty>}
      </Pane>}
      {tab==='accounts'&&<Pane title="سرفصل‌ها و دفترکل" description="مانده‌های زیر مربوط به تمام پروژه‌هاست و وضعیت دفاتر پس از ثبت سند تغییر می‌کند.">
        <div className="accw-form">
          <label>کد حساب<input value={newAccountId} onChange={e=>setNewAccountId(e.target.value)} placeholder="مثلاً 5300"/></label>
          <label>نام سرفصل<input value={newAccountName} onChange={e=>setNewAccountName(e.target.value)}/></label>
          <label>ماهیت<select value={newAccountKind} onChange={e=>setNewAccountKind(e.target.value)}>
            <option value="asset">دارایی</option><option value="liability">بدهی</option><option value="equity">حقوق مالکانه</option><option value="revenue">درآمد</option><option value="expense">هزینه</option>
          </select></label>
          <button type="button" disabled={working||!newAccountId.trim()||!newAccountName.trim()} onClick={()=>submit({
            type:'account.create',eventId:nextEvent('account'),accountId:newAccountId.trim(),
            name:newAccountName.trim(),kind:newAccountKind,liquid:false})}>ثبت سرفصل حساب</button>
        </div>
        {Object.values(shown.accounts).length?Object.values(shown.accounts).map(a=><div className="accw-record" key={a.id}><strong dir="auto">{a.id} · {a.name}</strong><span>ماهیت: {a.kind||''} · مانده با ماهیت حساب: {signedMoney(a.normalBalance)} · تفاضل بدهکار و بستانکار: {signedMoney(a.debitMinusCredit)}</span></div>):<Empty>دفترکل هنوز اطلاعات قابل نمایش ندارد.</Empty>}
        <h3>اسناد ثبت‌شده</h3>
        {!projectId?shown.journals.length?shown.journals.slice().reverse().map(j=><div className="accw-record" key={j.id}>
                <strong>{j.id}</strong><span>{displayAccountingDate(j.date)} · {j.sourceType} · {j.lines?.length||0} آرتیکل</span>
        </div>):<Empty>سند ثبت‌شده‌ای در دفترکل وجود ندارد.</Empty>:<Empty>برای دیدن دفاتر سراسری، فیلتر پروژه را روی «تمام پروژه‌ها» بگذارید.</Empty>}
      </Pane>}
      {tab==='payments'&&<Pane title="دریافت و پرداخت" description="عملیات این صفحه مستقیماً با ثبت سند دوبل حسابداری انجام می‌شود؛ هیچ دریافت یا پرداختی با ساخت پیش‌نویس به‌صورت خودکار ثبت نمی‌شود.">
        <div className="accw-settlement" aria-label="فرم‌های دریافت و پرداخت">
          <form className="accw-payment-card" onSubmit={recordSettlement} aria-label="ثبت دریافت یا پرداخت فاکتور">
            <h3>تسویه فاکتور صادرشده</h3>
            <fieldset className="accw-kind-switch"><legend>نوع عملیات</legend>
              <label><input type="radio" name="accounting-settlement-kind" checked={settlementKind==='receipt'} onChange={()=>{setSettlementKind('receipt');setSettlementDocumentId('');setSettlementAmount('');}}/> دریافت از مشتری</label>
              <label><input type="radio" name="accounting-settlement-kind" checked={settlementKind==='payment'} onChange={()=>{setSettlementKind('payment');setSettlementDocumentId('');setSettlementAmount('');}}/> پرداخت به تأمین‌کننده</label>
            </fieldset>
            <label>فاکتور صادرشده دارای مانده
              <select required value={settlementTarget?.id||''} disabled={working||!readReady||!settlementCandidates.length}
                onChange={e=>{setSettlementDocumentId(e.target.value);setSettlementAmount('');}}>
                <option value="">فاکتور را صریحاً انتخاب کنید</option>
                {settlementCandidates.map(d=><option value={d.id} key={d.id}>{d.number||d.id} · {d.party?.name||d.party?.id} · مانده {money(d.total-d.allocated)}</option>)}
              </select>
            </label>
            {settlementTarget&&<p className="accw-settlement-summary" role="status">{settlementKind==='receipt'?'دریافتنی از':'پرداختنی به'} {settlementTarget.party?.name||settlementTarget.party?.id} · مانده: {money(settlementTarget.total-settlementTarget.allocated)} · تاریخ صدور: {settlementTarget.postingDate||'نامشخص'}</p>}
            {readReady&&!settlementCandidates.length&&<p className="accw-empty">در این محدوده، فاکتور {settlementKind==='receipt'?'فروش':'خرید'} صادرشده با مانده مثبت وجود ندارد.</p>}
            <label>مبلغ واقعی ({MONEY_UNITS[moneyUnit]})
              <input required type="text" inputMode="numeric" dir="ltr" value={settlementAmount}
                aria-invalid={settlementAmount!==''&&!!settlementError} onChange={e=>setSettlementAmount(e.target.value)} placeholder={'مبلغ صحیح به '+MONEY_UNITS[moneyUnit]}/>
            </label>
            <label>حساب بانک یا صندوق
              <select value={settlementAccount} onChange={e=>setSettlementAccount(e.target.value)}>
                <option value="1010">بانک (۱۰۱۰)</option><option value="1000">صندوق (۱۰۰۰)</option>
              </select>
            </label>
            <label>تاریخ ثبت
              <AccountingJalaliField max={todayLocal()} value={settlementDate}
                onChange={setSettlementDate}/>
            </label>
            {settlementAmount&&settlementError&&<p className="accw-validation" role="status">{settlementError}</p>}
            <button type="submit" disabled={working||!readReady||!!settlementError}>{settlementKind==='receipt'?'ثبت دریافت واقعی':'ثبت پرداخت واقعی'}</button>
            <p className="accw-hint">پیش از ثبت، مبلغ و شماره سند برای تأیید نشان داده می‌شوند. وجه باید واقعاً دریافت یا پرداخت شده باشد؛ موجودی بانک در رابط به‌صورت برخط تأیید نمی‌شود.</p>
          </form>
          <form className="accw-payment-card" onSubmit={recordDeposit} aria-label="ثبت آورده نقدی واقعی">
            <h3>ورود سرمایه واقعی به صندوق یا بانک</h3>
            <p>فقط در صورت وقوع واقعی واریز ثبت کنید. این عملیات فاکتور یا پرداخت به تأمین‌کننده نیست.</p>
            <label>مبلغ واریز ({MONEY_UNITS[moneyUnit]})
              <input required type="text" dir="ltr" inputMode="numeric" value={fundAmount} aria-invalid={fundAmount!==''&&!!fundParsed.error} onChange={e=>setFundAmount(e.target.value)} placeholder={'مبلغ واریزی به '+MONEY_UNITS[moneyUnit]}/>
            </label>
            <label>شرح منبع وجه
              <input required maxLength={1000} value={fundNote} onChange={e=>setFundNote(e.target.value)} placeholder="مانند آورده واقعی مالک"/>
            </label>
            <label>حساب مقصد<select value={fundAccount} onChange={e=>setFundAccount(e.target.value)}><option value="1010">بانک (۱۰۱۰)</option><option value="1000">صندوق (۱۰۰۰)</option></select></label>
            <label>تاریخ واقعی واریز<AccountingJalaliField max={todayLocal()} value={fundDate} onChange={setFundDate}/></label>
            {fundAmount&&fundParsed.error&&<p className="accw-validation" role="status">{fundParsed.error}</p>}
            <button type="submit" disabled={working||!readReady||!!fundParsed.error||!fundNote.trim()||!validAccountingDate(fundDate)}>ثبت واریز واقعی پس از تأیید</button>
          </form>
        </div>
        {projectId?<Empty>گردش دریافت‌ها و پرداخت‌های دفترکل فقط در حالت «تمام پروژه‌ها» از میزبان خوانده می‌شود. ثبت تسویه فاکتورِ همین پروژه در بالا ممکن است.</Empty>:
          <div className="accw-settlement-history">
            <section aria-label="دریافت‌های ثبت‌شده"><h3>دریافت‌های ثبت‌شده</h3>{Object.values(shown.receipts).length?Object.values(shown.receipts).map(r=><div className="accw-record" key={r.id}><strong>{r.partyId}</strong><span>{displayAccountingDate(r.date)} · {money(r.total)} · {r.accountId==='1010'?'بانک':'صندوق'} {r.reversed?'· برگشت‌شده':''}</span></div>):<Empty>دریافت ثبت‌شده‌ای وجود ندارد.</Empty>}</section>
            <section aria-label="پرداخت‌های ثبت‌شده"><h3>پرداخت‌های ثبت‌شده</h3>{Object.values(shown.payments).length?Object.values(shown.payments).map(r=><div className="accw-record" key={r.id}><strong>{r.partyId}</strong><span>{displayAccountingDate(r.date)} · {money(r.total)} · {r.accountId==='1010'?'بانک':'صندوق'} {r.reversed?'· برگشت‌شده':''}</span></div>):<Empty>پرداخت ثبت‌شده‌ای وجود ندارد.</Empty>}</section>
          </div>}
        <p>بستانکاری تأمین‌کننده فقط از فاکتور خرید صادرشده ایجاد می‌شود. ثبت کار بدون قیمت، بدهی نیست. گردش سراسری به معنای تفکیک معتبر پروژه‌ای نیست.</p>
      </Pane>}
      {tab==='reports'&&<Pane title="گزارش‌های واقعی دفترکل" description="تراز آزمایشی، سود و زیان، ترازنامه و گردش حساب از سندهای قطعی محاسبه می‌شوند؛ ارقام سراسری‌اند.">
        {projectId?<Empty>گزارش‌های تراز آزمایشی و سود و زیان فقط در سطح همه پروژه‌ها معتبرند؛ فیلتر را روی «تمام پروژه‌ها» قرار دهید.</Empty>:
          !shown.reports?<Empty>گزارش دفترکل در این نسخه میزبان موجود نیست یا هنوز بارگذاری نشده است.</Empty>:<>
            <div className="accw-report-summary" aria-label="خلاصه گزارش‌های دفترکل">
              <div><span>درآمد ثبت‌شده</span><strong>{signedMoney(shown.reports.profitLoss?.revenue)}</strong></div>
              <div><span>هزینه ثبت‌شده</span><strong>{signedMoney(shown.reports.profitLoss?.expense)}</strong></div>
              <div><span>سود یا زیان حسابداری</span><strong>{signedMoney(shown.reports.profitLoss?.net)}</strong></div>
              <div><span>دارایی ثبت‌شده</span><strong>{signedMoney(shown.reports.balanceSheet?.assets)}</strong></div>
              <div><span>بدهی ثبت‌شده</span><strong>{signedMoney(shown.reports.balanceSheet?.liabilities)}</strong></div>
              <div><span>حقوق مالکانه و سود انباشته</span><strong>{signedMoney(shown.reports.balanceSheet?.liabilitiesAndEquity)}</strong></div>
            </div>
            <h3>تراز آزمایشی سراسری</h3>
            <div className="accw-table-scroll"><table className="accw-table"><caption>تراز آزمایشی، مبالغ {MONEY_UNITS[moneyUnit]}، همه پروژه‌ها</caption>
              <thead><tr><th scope="col">کد</th><th scope="col">حساب</th><th scope="col">بدهکار</th><th scope="col">بستانکار</th></tr></thead>
              <tbody>{(shown.reports.trialBalance?.rows||[]).map(row=><tr key={row.accountId}><th scope="row" dir="ltr">{row.accountId}</th><td>{row.name}</td><td>{signedMoney(row.debit)}</td><td>{signedMoney(row.credit)}</td></tr>)}</tbody>
              <tfoot><tr><th colSpan={2} scope="row">جمع</th><td>{signedMoney(shown.reports.trialBalance?.totalDebit)}</td><td>{signedMoney(shown.reports.trialBalance?.totalCredit)}</td></tr></tfoot>
            </table></div>
            <h3>گردش حساب از اسناد قطعی</h3>
            <label className="accw-report-account">حساب برای مشاهده گردش
              <select value={reportAccountId} onChange={e=>setReportAccountId(e.target.value)}>
                <option value="">انتخاب حساب</option>{Object.values(shown.accounts).map(a=><option key={a.id} value={a.id}>{a.id} · {a.name}</option>)}
              </select>
            </label>
            {reportAccountId&&<div className="accw-table-scroll"><table className="accw-table"><caption>گردش حساب {reportAccountId} به {MONEY_UNITS[moneyUnit]}</caption>
              <thead><tr><th scope="col">تاریخ</th><th scope="col">سند</th><th scope="col">بدهکار</th><th scope="col">بستانکار</th></tr></thead>
              <tbody>{(shown.reports.accountStatements?.[reportAccountId]||[]).map((row,i)=><tr key={row.journalId+'-'+i}><td>{displayAccountingDate(row.date)}</td><td dir="ltr">{row.journalId}</td><td>{signedMoney(row.debit)}</td><td>{signedMoney(row.credit)}</td></tr>)}</tbody>
            </table></div>}
            <p>ترازنامه شامل سود و زیان بسته‌نشده است؛ نمایش آن سند بستن حساب‌ها ایجاد نمی‌کند. گزارش رسمی مالیاتی، موجودی کالا و سود تفکیکی پروژه در این نسخه آماده نیست.</p>
          </>}
      </Pane>}
      {tab==='migration'&&<Pane title="بررسی بکاپ پارسیان" description="در این مرحله فقط نوع فایل به‌صورت آفلاین شناسایی می‌شود؛ قابلیت انتقال حساب‌ها هنوز پیاده نشده است.">
        <div className="accw-form" aria-label="بررسی آفلاین سربرگ بکاپ پارسیان">
          <label>انتخاب کپی فایل پشتیبان BAK از دستگاه شما
            <input type="file" accept=".bak" disabled={working} onChange={async event=>{
              const file=event.target.files?.[0];
              setParsianProbe({status:'reading',message:'در حال خواندن فقط ۱۶ بایت ابتدایی فایل روی دستگاه...'});
              try {setParsianProbe(await inspectBackupFileLocally(file));}
              catch {setParsianProbe({status:'invalid',message:'خواندن محلی فایل ناموفق بود؛ هیچ داده‌ای منتقل نشده است.'});}
              event.target.value='';
            }}/>
          </label>
          <p>این بررسی فایل را آپلود نمی‌کند، اطلاعات اشخاص و مبالغ را نمی‌خواند و پایگاه داده مدار را تغییر نمی‌دهد.</p>
          {parsianProbe.status!=='idle'&&<p role="status" className={parsianProbe.status==='invalid'||parsianProbe.status==='unknown'?'accw-validation':'accw-settlement-summary'}>
            {parsianProbe.message}{Number.isSafeInteger(parsianProbe.size)?' · حجم فایل: '+parsianProbe.size.toLocaleString('fa-IR')+' بایت':''}
          </p>}
        </div>
        <div className="accw-caution"><ShieldAlert size={23}/> شناسایی امضای TAPE به معنی سالم‌بودن فایل یا آماده‌بودن مهاجرت نیست. هیچ بازیابی روی SQL Server فعال یا داده واقعی مدار انجام نمی‌شود.</div>
        <p>برای انتقال معتبر، جدول‌ها و روابط پارسیان باید روی SQL Server ایزوله بررسی شوند، سپس کدینگ حساب، اشخاص، کالا، فاکتور، چک، اسناد افتتاحیه و دوره‌ها نگاشت شوند و ترازها قبل و بعد از انتقال تطبیق داده شوند.</p>
        <p>بازیابی بکاپ مدار فرایندی جداست. تا زمان آزمون کامل restore و تطبیق، از هیچ فایل واقعی برای آزمایش مهاجرت استفاده نکنید.</p>
      </Pane>}
    </main>
  </div>;
}
