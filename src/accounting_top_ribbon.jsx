import React from 'react';
import {ArrowRight,BookOpen,Building2,FilePlus2,FileText,Landmark,Layers3,
  Printer,RefreshCw,Settings2,ShieldCheck,Users,Wallet} from 'lucide-react';
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
  if(['invoice','proforma','bill','contractors'].includes(tab))return 'documents';
  return ACCOUNTING_RIBBON_GROUPS.find(g=>g.items.includes(tab))?.id||'general';
};

export default function AccountingTopRibbon({tab,sections,onNavigate,onNewInvoice,
  onPrint,canDraft=false,canManage=false,canAdmin=false,hasPrintableInvoice=false,
  currency='ریال',companyName='',currentUser=null,onRefresh,onExit,onSwitchCompany,onManageUsers,
  onBack=null,backLabel='بازگشت به صفحه اصلی',disabled=false}){
  const [chosen,setChosen]=React.useState('');
  React.useEffect(()=>setChosen(''),[tab]);
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
    <nav aria-label="دسته‌بندی‌های حسابداری" className="sac-ribbon-tabs">
      {ACCOUNTING_RIBBON_GROUPS.map(g=>{
        const Icon=g.icon;
        return <button key={g.id} type="button" onClick={()=>chooseGroup(g)}
          aria-pressed={active.id===g.id} className={active.id===g.id?'active':''}>
          <Icon size={16}/>{g.title}</button>;
      })}
    </nav>
    <nav className="sac-ribbon-tools" aria-label="فرمان‌های گروه انتخاب‌شده">
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
