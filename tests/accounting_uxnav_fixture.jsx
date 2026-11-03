import React from 'react';
import {createRoot} from 'react-dom/client';
import AccountingTopRibbon from '../src/accounting_top_ribbon.jsx';
import '../src/standalone_accounting_workspace.css';
import '../src/accounting_unslop.css';

// Synthetic records only. This page never opens a native host or a real user DB.
const sections=[['overview','داشبورد'],['company','مشخصات شرکت'],
  ['proforma','پیش‌فاکتور مستقل'],['invoice','فاکتورهای فروش'],
  ['bill','صورتحساب‌های خرید'],['contractors','کارهای پیمانکاران'],
  ['parties','اشخاص'],['migration','مهاجرت و سوابق'],['cheques','خزانه و چک'],
  ['items','کالا، انبار و کاردکس'],['settlements','دریافت، پرداخت و اقساط'],
  ['cash','صندوق، بانک و مغایرت'],['accounts','حساب‌ها و دفترکل'],
  ['journal','سند دستی و برگشت'],['reports','گزارش‌های مالی'],
  ['payroll','حقوق و مالیات'],['period','سال مالی و بستن دوره'],
  ['settings','تنظیمات حسابداری']];
const view={
  parties:{buyer:{id:'buyer',name:'مشتری آزمایشی'},
    vendor:{id:'vendor',name:'فروشنده آزمایشی',password:'SECRET-NEVER-SHOW'}},
  accounts:{'1100':{id:'1100',name:'حساب دریافتنی'}},
  invoices:{'INV-QA-001':{id:'INV-QA-001',number:68,partyId:'buyer',
    note:'SECRET-NOTE-NEVER-SHOW',lines:[{description:'SECRET-LINE-NEVER-SHOW'}]}},
  bills:{'BILL-QA-001':{id:'BILL-QA-001',partyId:'vendor'}},
  proformas:{'PF-QA-001':{id:'PF-QA-001',partyId:'buyer'}},
  journals:[{id:'GL-QA-001'}],receipts:{'RC-QA-001':{id:'RC-QA-001',partyId:'buyer'}},
  payments:{'PAY-QA-001':{id:'PAY-QA-001',partyId:'vendor'}},
  parsianMigration:{raw:'SECRET-ARCHIVE-NEVER-SHOW'},
};
window.__uxnavEvents=[];
document.documentElement.dataset.theme='light';

function SyntheticApp(){
  const [role,setRole]=React.useState('admin');
  const [tab,setTab]=React.useState('overview');
  const [disabled,setDisabled]=React.useState(false);
  const [authorizedView,setAuthorizedView]=React.useState(view);
  const log=(type,payload)=>window.__uxnavEvents.push({type,...payload});
  const navigate=key=>{log('navigate',{tab:key});setTab(key);};
  window.__uxnavSetRole=setRole;
  window.__uxnavSetDisabled=setDisabled;
  window.__uxnavClearView=()=>setAuthorizedView(null);
  window.__uxnavSetTheme=theme=>document.documentElement.dataset.theme=theme;
  return <div dir="rtl" className="sac-root" style={{height:'100dvh'}}>
    <AccountingTopRibbon tab={tab} sections={sections}
      currentUser={{username:'QA synthetic '+role,role}}
      searchView={authorizedView}
      recordAccess={role==='viewer'?{accounts:false,bills:false,journals:false}:null}
      canDraft={role!=='viewer'} canManage={role!=='viewer'} canAdmin={role==='admin'}
      currency="ریال" companyName="شرکت ساختگی" disabled={disabled}
      onNavigate={navigate}
      onNewInvoice={()=>{log('invoice',{});setTab('invoice');}}
      onQuickAction={action=>{log('quick',{action});
        setTab(action==='purchase'?'bill':'settlements');}}
      onSearchSelect={result=>{log('select',result);setTab(result.tab);}}
      onRefresh={()=>log('refresh',{})} onExit={()=>log('exit',{})}
      onPrint={()=>log('print',{})} onSwitchCompany={()=>log('company',{})}
      onManageUsers={()=>log('users',{})}/>
    <main className="sac-main" style={{padding:20,minHeight:0}}>
      <h1>محیط آزمون ساختگی</h1><output id="uxnav-current-tab">{tab}</output>
      <p>این صفحه فقط رفتار ناوبری را آزمایش می‌کند.</p>
    </main>
  </div>;
}
createRoot(document.getElementById('root')).render(<SyntheticApp/>);
