import React from 'react';
import {ArrowRight,BookOpen,Building2,FilePlus2,FileText,Landmark,Layers3,
  Printer,RefreshCw,Search,Settings2,ShieldCheck,Users,Wallet} from 'lucide-react';
import './accounting_top_ribbon.css';

/** Human-friendly top menu influenced by the independent Mohsensoft Faktor
 * ribbon workflow, not a copy of any proprietary icons or code.
 * Every shortcut maps to an already-authorized standalone accounting action.
 */
export const ACCOUNTING_RIBBON_GROUPS=[
  {id:'general',title:'عمومی',icon:Landmark,items:['overview','invoice','proforma']},
  {id:'documents',title:'فاکتورها و سفارش‌ها',icon:FileText,items:['invoice','proforma','bill','contractors']},
  {id:'records',title:'اشخاص و کالا',icon:Users,items:['parties','items','company']},
  {id:'treasury',title:'خزانه و پرداخت',icon:Wallet,items:['settlements','cash','cheques']},
  {id:'ledger',title:'حسابداری',icon:BookOpen,items:['accounts','journal','period']},
  {id:'reports',title:'گزارش‌ها و سوابق',icon:Layers3,items:['reports','migration']},
  {id:'settings',title:'تنظیمات و مدیریت',icon:Settings2,items:['settings','company','payroll','period']},
];
export const accountingRibbonGroupFor=tab=>{
  if(tab==='overview')return 'general';
  if(tab==='settings')return 'settings';
  if(['invoice','proforma','bill','contractors'].includes(tab))return 'documents';
  return ACCOUNTING_RIBBON_GROUPS.find(g=>g.items.includes(tab))?.id||'general';
};

export default function AccountingTopRibbon({tab,sections,onNavigate,onNewInvoice,
  onPrint,canDraft=false,canManage=false,canAdmin=false,hasPrintableInvoice=false,
  currency='ریال',companyName='',currentUser=null,onRefresh,onExit,onSwitchCompany,onManageUsers,
  onBack=null,backLabel='بازگشت به صفحه اصلی',disabled=false}){
  const [chosen,setChosen]=React.useState('');
  const [jumpQuery,setJumpQuery]=React.useState('');
  const [jumpIndex,setJumpIndex]=React.useState(0);
  const jumpInput=React.useRef(null);
  React.useEffect(()=>{setChosen('');setJumpQuery('');setJumpIndex(0);},[tab]);
  React.useEffect(()=>{
    const shortcut=event=>{
      if(!disabled&&(event.ctrlKey||event.metaKey)&&!event.altKey&&
         event.key.toLocaleLowerCase('en-US')==='k'){
        event.preventDefault();jumpInput.current?.focus();
      }
    };
    window.addEventListener('keydown',shortcut);
    return ()=>window.removeEventListener('keydown',shortcut);
  },[disabled]);
  const matches=jumpQuery.trim()?sections.filter(([,label])=>
    label.toLocaleLowerCase('fa-IR').includes(jumpQuery.trim().toLocaleLowerCase('fa-IR')))
    .slice(0,8):[];
  const jumpTo=key=>{
    if(disabled)return;
    setJumpQuery('');setJumpIndex(0);onNavigate(key);
  };
  const jumpKeyDown=event=>{
    if(event.key==='Escape'){setJumpQuery('');setJumpIndex(0);return;}
    if(!matches.length)return;
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){
      event.preventDefault();setJumpIndex(index=>
        (index+(event.key==='ArrowDown'?1:-1)+matches.length)%matches.length);
    }else if(event.key==='Enter'){
      event.preventDefault();jumpTo(matches[Math.min(jumpIndex,matches.length-1)][0]);
    }
  };
  const active=ACCOUNTING_RIBBON_GROUPS.find(g=>g.id===(chosen||accountingRibbonGroupFor(tab)))||
    ACCOUNTING_RIBBON_GROUPS[0];
  const labels=new Map(sections);
  const chooseGroup=g=>{
    setChosen(g.id);
  };
  const goTo=key=>{
    onNavigate(key);
  };
  return <div className="sac-ribbon-shell">
    <div className="sac-ribbon-titlebar">
      <div className="sac-ribbon-identity">
        <span className="sac-ribbon-app-icon"><Landmark size={22}/></span>
        <span><strong>مدار | حسابداری مستقل</strong>
          <small>محیط کار مالی · {companyName||'دفتر مستقل'}</small></span>
      </div>
      <div className="sac-ribbon-quick" aria-label="دسترسی سریع حسابداری">
        <div className="sac-ribbon-jump" role="search" aria-label="جست‌وجوی بخش‌های حسابداری"
          onBlur={event=>{
            if(!event.currentTarget.contains(event.relatedTarget))setJumpQuery('');
          }}>
          <Search size={16} aria-hidden="true"/>
          <input ref={jumpInput} type="search" value={jumpQuery} disabled={disabled}
            aria-label="رفتن سریع به بخش حسابداری"
            placeholder="بخش موردنظر… (Ctrl+K)"
            onChange={event=>{setJumpQuery(event.target.value);setJumpIndex(0);}}
            onKeyDown={jumpKeyDown}/>
          {jumpQuery.trim()&&<div className="sac-ribbon-jump-results"
            role="group" aria-label="بخش‌های پیدا شده">
            {matches.map(([key,label],index)=><button key={key} type="button"
              className={index===jumpIndex?'active':''} onClick={()=>jumpTo(key)}>
              {label}</button>)}
            {!matches.length&&<span>بخشی با این عنوان پیدا نشد.</span>}
            {!!matches.length&&<span className="sac-ribbon-jump-announcement" role="status">
              {matches.length.toLocaleString('fa-IR')} نتیجه؛ انتخاب: {matches[Math.min(jumpIndex,matches.length-1)][1]}
            </span>}
          </div>}
        </div>
        {currentUser?.username&&<span className="sac-ribbon-user"
          title="نام کاربری و عنوان سازمانی؛ مجوز فنی مستقل است">
          <Users size={14}/>{currentUser.username}
          {currentUser.jobTitle&&<b>· {currentUser.jobTitle}</b>}</span>}
        {tab!=='overview'&&onBack&&<button type="button" className="sac-ribbon-back"
          onClick={onBack} disabled={disabled} title={backLabel}>
          <ArrowRight size={17}/> {backLabel}
        </button>}
        {canDraft&&<button type="button" onClick={()=>{setChosen('documents');onNewInvoice();}}
          disabled={disabled} title="باز کردن صفحه ورود اطلاعات فاکتور">
          <FilePlus2 size={17}/> فاکتور جدید</button>}
        {canManage&&<button type="button" onClick={onPrint}
          disabled={disabled||!hasPrintableInvoice} title="دریافت PDF فاکتور انتخاب‌شده">
          <Printer size={17}/> PDF فاکتور</button>}
        <button type="button" onClick={()=>goTo('settings')} disabled={disabled}
          aria-current={tab==='settings'?'page':undefined}
          title="تنظیمات حسابداری و بررسی به‌روزرسانی">
          <Settings2 size={16}/> تنظیمات</button>
        <button type="button" onClick={onRefresh} disabled={disabled}
          title="بازخوانی اطلاعات ثبت‌شده"><RefreshCw size={16}/> بازخوانی</button>
        <span className="sac-ribbon-unit" title="واحد واقعی دفتر حسابداری">{currency}</span>
        {canAdmin&&onManageUsers&&<button type="button" disabled={disabled}
          onClick={onManageUsers} title="مدیریت کاربران و نقش‌های همین شرکت">
          <ShieldCheck size={16}/> کاربران</button>}
        {onSwitchCompany&&<button type="button" disabled={disabled} onClick={onSwitchCompany}
          title="بستن ایمن دفتر فعلی و بازکردن انتخاب‌گر شرکت، بدون خروج از برنامه">
          <Building2 size={16}/> تغییر شرکت</button>}
        <button type="button" className="sac-ribbon-exit" onClick={onExit}>خروج</button>
      </div>
    </div>
    <nav aria-label="دسته‌بندی‌های حسابداری" className="sac-ribbon-tabs" tabIndex={0}>
      {ACCOUNTING_RIBBON_GROUPS.map(g=>{
        const Icon=g.icon;
        return <button key={g.id} type="button" onClick={()=>chooseGroup(g)}
          aria-pressed={active.id===g.id} className={active.id===g.id?'active':''}>
          <Icon size={16}/>{g.title}</button>;
      })}
    </nav>
    <nav className="sac-ribbon-tools" aria-label="فرمان‌های گروه انتخاب‌شده" tabIndex={0}>
      {active.items.filter(id=>labels.has(id)).map(id=><button key={id}
        type="button" onClick={()=>goTo(id)} aria-current={tab===id?'page':undefined}
        className={tab===id?'selected':''}>
        {labels.get(id)}
      </button>)}
      {active.id==='documents'&&canDraft&&<button className="sac-ribbon-highlight"
        type="button" onClick={onNewInvoice} disabled={disabled}>
        <FilePlus2 size={16}/> ثبت فاکتور جدید
      </button>}
      {active.id==='settings'&&<span className="sac-ribbon-hint">
        <ShieldCheck size={14}/> شرکت‌ها باید دفتر مالی مستقل داشته باشند
      </span>}
    </nav>
  </div>;
}
