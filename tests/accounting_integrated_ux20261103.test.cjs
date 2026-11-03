'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const root=path.resolve(__dirname,'..');
const load=relative=>{
  const file=path.join(root,'src',relative);
  const code=esbuild.buildSync({entryPoints:[file],bundle:true,platform:'node',
    format:'cjs',write:false,jsx:'automatic',loader:{'.css':'empty','.jpg':'dataurl'},
    external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
  const mod=new Module(file+'.compiled.cjs',module);
  mod.filename=file+'.compiled.cjs';
  mod.paths=Module._nodeModulePaths(path.dirname(file));
  mod._compile(code,mod.filename);
  return mod.exports;
};
const source=fs.readFileSync(path.join(root,'src/standalone_accounting_workspace.jsx'),'utf8');
const ribbonSource=fs.readFileSync(path.join(root,'src/accounting_top_ribbon.jsx'),'utf8');
const darkCss=fs.readFileSync(path.join(root,'src/accounting_unslop.css'),'utf8');
const mobileCss=fs.readFileSync(path.join(root,'src/standalone_accounting_ux20.css'),'utf8');
const {AccountingVitreaHome,accountingCompanyToday}=load('standalone_accounting_workspace.jsx');
const AccountingTopRibbon=load('accounting_top_ribbon.jsx').default;
const ReleaseUpdateSettings=load('release_update_settings.jsx').default;

test('receivable and payable shortcuts count only issued documents with a positive valid balance',()=>{
  const view={currency:'RIAL',accounts:{},parties:{},receipts:{},payments:{},
    invoices:{
      open:{id:'open',status:'issued',total:2000,allocated:300,returnedAmount:500},
      settled:{id:'settled',status:'issued',total:1000,allocated:1000,returnedAmount:0},
      draft:{id:'draft',status:'draft',total:9000,allocated:0,returnedAmount:0},
      invalid:{id:'invalid',status:'issued',total:'oops',allocated:0,returnedAmount:0},
      overflow:{id:'overflow',status:'issued',total:Number.MAX_SAFE_INTEGER,
        allocated:Number.MAX_SAFE_INTEGER,returnedAmount:1}},
    bills:{
      payable:{id:'payable',status:'issued',total:3000,allocated:0,returnedAmount:1000},
      reviewed:{id:'reviewed',status:'approved',total:2000,allocated:0,returnedAmount:0}}};
  const html=renderToStaticMarkup(React.createElement(AccountingVitreaHome,{
    view,currency:'RIAL',today:'2026-11-03',canDraft:false,disabled:false,
    onNavigate:()=>{},onNewInvoice:()=>{}}));
  assert.match(html,/اسناد باز قابل پیگیری/);
  assert.match(html,/فاکتور فروش با مانده دریافتنی<\/span><strong>۱ سند<\/strong>/);
  assert.match(html,/صورتحساب خرید با مانده پرداختنی<\/span><strong>۱ سند<\/strong>/);
  assert.match(html,/بررسی فاکتورها/);
  assert.match(html,/بررسی خریدها/);
  assert.doesNotMatch(html,/ثبت دریافت|ثبت پرداخت/,
    'read-only users do not get posting shortcuts');
  assert.doesNotMatch(html,/۹٬۰۰۰ ریال/,'drafts must not appear as receivable totals');
  const managerHtml=renderToStaticMarkup(React.createElement(AccountingVitreaHome,{
    view,currency:'RIAL',today:'2026-11-03',canDraft:true,canSettle:true,
    disabled:false,onNavigate:()=>{},onNewInvoice:()=>{}}));
  assert.match(managerHtml,/ثبت دریافت/);
  assert.match(managerHtml,/ثبت پرداخت/);
});

test('accounting settings appears in the ribbon and uses the shared desktop updater',()=>{
  const html=renderToStaticMarkup(React.createElement(AccountingTopRibbon,{
    tab:'settings',sections:[['overview','داشبورد'],['settings','تنظیمات حسابداری']],
    onNavigate:()=>{},onRefresh:()=>{},onExit:()=>{},disabled:false}));
  assert.match(html,/aria-current="page"[^>]*title="تنظیمات حسابداری و بررسی به‌روزرسانی"/);
  assert.match(html,/تنظیمات حسابداری/);
  assert.match(html,/رفتن سریع به بخش حسابداری/);
  assert.match(ribbonSource,/event\.key==='ArrowDown'/);
  assert.match(ribbonSource,/event\.key==='Escape'/);
  assert.match(ribbonSource,/event\.key\.toLocaleLowerCase\('en-US'\)==='k'/);
  assert.match(source,/tab==='settings'&&<Panel title="تنظیمات حسابداری"/);
  assert.match(source,/<ReleaseUpdateSettings api=\{api\} context="accounting"\/>/);
  const release=renderToStaticMarkup(React.createElement(ReleaseUpdateSettings,{api:{},context:'accounting'}));
  assert.match(release,/به‌روزرسانی حسابداری/);
  assert.match(release,/فقط در نسخهٔ نصب‌شدهٔ ویندوز/);
  assert.match(ribbonSource,/\['settings','company','payroll','period'\]/);
});

test('horizontal tables and accounting scroll regions can receive keyboard focus',()=>{
  assert.match(source,/className="sac-body" role="region" aria-label="محتوای صفحه حسابداری" tabIndex=\{0\}/);
  assert.match(source,/className="sac-table-wrap" role="region" tabIndex=\{0\}/);
  assert.match(source,/className="sac-vtr-table-scroll" role="region" aria-label="جدول آخرین دریافت‌ها و پرداخت‌ها" tabIndex=\{0\}/);
  assert.match(ribbonSource,/className="sac-ribbon-tabs" tabIndex=\{0\}/);
  assert.match(ribbonSource,/className="sac-ribbon-tools"[^>]*tabIndex=\{0\}/);
  assert.match(mobileCss,/\.sac-vtr-table-scroll[^)]*\):focus-visible/);
});

test('dark panel colours meet WCAG 4.5:1 for text and mobile invoice has visible row labels',()=>{
  const lum=hex=>{
    const rgb=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255)
      .map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);
    return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
  };
  const contrast=(a,b)=>{const [hi,lo]=[lum(a),lum(b)].sort((x,y)=>y-x);
    return (hi+.05)/(lo+.05);};
  assert(contrast('#e8f0fb','#262c38')>=4.5);
  assert(contrast('#c3d3e8','#262c38')>=4.5);
  assert(contrast('#8ce2ba','#22252e')>=4.5);
  assert.match(darkCss,/\.sac-document-detail/);
  assert.match(darkCss,/\.sac-invoice-editor \.sac-invoice-line/);
  assert.match(source,/className="sac-invoice-row-heading"/);
  assert.match(source,/className="sac-invoice-total-caption"/);
  assert.match(mobileCss,/@media\(max-width:560px\)[\s\S]*?\.sac-invoice-row-heading\{display:block/);
  assert.match(mobileCss,/\.sac-invoice-work-mode \.sac-invoice-summary\{position:static\}/);
});

test('posting date uses configured fixed company UTC offset at the day boundary',()=>{
  const instant=new Date('2026-11-02T22:00:00Z');
  assert.equal(accountingCompanyToday({companyProfile:{postingUtcOffsetMinutes:210}},instant),
    '2026-11-03');
  assert.equal(accountingCompanyToday({companyProfile:{postingUtcOffsetMinutes:-120}},instant),
    '2026-11-02');
  assert.equal(accountingCompanyToday({companyProfile:{postingUtcOffsetMinutes:0}},instant),
    '2026-11-02');
  assert.equal(accountingCompanyToday({companyProfile:{}},instant),
    '2026-11-02','Unconfigured historical books must follow the native UTC day');
  assert.equal(accountingCompanyToday({companyProfile:{postingUtcOffsetMinutes:900}},instant),
    '2026-11-02','Invalid offset must not invent a company day');
  assert.match(source,/const today=accountingCompanyToday\(view\)/);
  assert.match(source,/\['settlement','postingDate'\]/);
  assert.match(source,/setIssueDate\(date=>date===previous\?today:date\)/);
});
