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
const jsx=fs.readFileSync(path.join(root,'src/standalone_accounting_workspace.jsx'),'utf8');
const css=fs.readFileSync(path.join(root,'src/accounting_vitrea.css'),'utf8');
const file=path.join(root,'src/standalone_accounting_workspace.jsx');
const built=esbuild.buildSync({entryPoints:[file],bundle:true,platform:'node',format:'cjs',
  write:false,jsx:'automatic',loader:{'.css':'empty','.jpg':'dataurl'},
  external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const mod=new Module(path.join(root,'tests/accounting-vitrea-virtual.cjs'),module);
mod.filename=path.join(root,'tests/accounting-vitrea-virtual.cjs');
mod.paths=Module._nodeModulePaths(path.dirname(mod.filename));
mod._compile(built,mod.filename);
const {accountingSettlementOverview,accountingOutstandingOverview,
  accountingSettlementCsv,AccountingVitreaHome}=mod.exports;

const today='2026-10-27';
const view={
  currency:'RIAL',parties:{p1:{name:'مشتری الف'},p2:{name:'تأمین‌کننده ب'}},
  accounts:{bank:{name:'بانک الف',liquid:true,debitMinusCredit:13000}},
  receipts:{r1:{id:'r1',partyId:'p1',accountId:'bank',date:'2026-10-05',total:1500,reversed:false},
    r2:{id:'r2',date:'2026-09-13',total:2000,reversed:true},
    r3:{id:'r3',date:'2025-09-20',total:300}},
  payments:{p1:{id:'p1',partyId:'p2',accountId:'bank',date:'2026-10-06',total:800,reversed:false},
    p2:{id:'p2',date:'2026-09-20',total:100,reversed:false}}
};

test('last 12 Gregorian months use actual posted receipts/payments, exclude reversals and old rows',()=>{
  const res=accountingSettlementOverview(view,today);
  assert.equal(res.months.length,12);
  assert.equal(res.earliest,'2025-11');
  assert.equal(res.latest,'2026-10');
  assert.equal(res.received,1500);
  assert.equal(res.paid,900);
  assert.equal(res.net,600);
  assert.equal(res.months.at(-1).received,1500);
  assert.equal(res.months.at(-1).paid,800);
  assert.equal(res.months.at(-2).paid,100);
  assert.equal(res.months.at(-2).received,0);
  assert.equal(res.entries.length,5);
  assert.equal(res.entries.find(e=>e.id==='r2').reversed,true);
});

test('empty account gives no fabricated movements, bank status or successful postings',()=>{
  const res=accountingSettlementOverview({receipts:{},payments:{}},today);
  assert.deepEqual(res.entries,[]);
  assert.equal(res.received,0);
  assert.equal(res.paid,0);
  assert(res.months.every(m=>m.received===0&&m.paid===0));
  assert.equal(res.omitted,0);
});

test('overview distinguishes issued unsettled invoices and bills from cash, drafts and historic balances',()=>{
  const data={invoices:{
    issued:{id:'issued',status:'issued',total:300000,allocated:100000,
      returnedAmount:25000,dueDate:'2026-10-20'},
    draft:{id:'draft',status:'draft',total:800000,allocated:0},
    fully:{id:'fully',status:'issued',total:200,allocated:200},
  },bills:{pending:{id:'pending',status:'issued',total:70000,allocated:0,dueDate:'2026-11-10'}},
  receipts:{r1:{id:'r1',date:'2026-10-21',total:100000}},payments:{},historical:{debtor:12345}};
  const pending=accountingOutstandingOverview(data,today);
  assert.equal(pending.receivable,175000);
  assert.equal(pending.payable,70000);
  assert.equal(pending.receivableCount,1);
  assert.equal(pending.overdueReceivableCount,1);
  assert.equal(pending.overduePayableCount,0);
  assert.equal(pending.invalidReceivable,0);
  const cash=accountingSettlementOverview(data,today);
  assert.equal(cash.received,100000);
  const html=renderToStaticMarkup(React.createElement(AccountingVitreaHome,{
    view:{...data,accounts:{},parties:{}},currency:'RIAL',today,
    canDraft:true,disabled:false,onNavigate:()=>{},onNewInvoice:()=>{}}));
  assert.match(html,/مبالغ در انتظار تسویه/);
  assert.match(html,/۱۷۵٬۰۰۰ ریال/);
  assert.match(html,/۷۰٬۰۰۰ ریال/);
  assert.match(html,/این مبالغ وجه دریافت یا پرداخت‌شده نیستند/);
  assert.match(html,/فاکتور با سررسید گذشته/);
  assert.match(html,/دسترسی مستقیم به کارهای حسابداری/);
  assert.match(html,/role="region" tabindex="0"/);
});

test('unrepresentable or malformed outstanding values fail closed and never appear as zero',()=>{
  const huge=Number.MAX_SAFE_INTEGER;
  const data={invoices:{a:{id:'a',status:'issued',total:huge,allocated:0},
    b:{id:'b',status:'issued',total:100,allocated:0}},
  bills:{bad:{id:'bad',status:'issued',total:123,allocated:undefined},
    over:{id:'over',status:'issued',total:100,allocated:110}}};
  const pending=accountingOutstandingOverview(data,today);
  assert.equal(pending.receivable,null);
  assert.equal(pending.payable,null);
  assert.equal(pending.invalidPayable,2);
  assert.equal(pending.receivableCount,2);
  const html=renderToStaticMarkup(React.createElement(AccountingVitreaHome,{
    view:{...data,accounts:{},parties:{},receipts:{},payments:{}},
    currency:'RIAL',today,canDraft:false,disabled:false,onNavigate:()=>{}}));
  assert.match(html,/مبلغ بخشی از اسناد صادرشده معتبر یا قابل جمع دقیق نیست/);
  assert.match(html,/نامشخص/);
});

test('malformed monetary and date records are counted as omitted, not added',()=>{
  const res=accountingSettlementOverview({receipts:{
    unsafe:{id:'unsafe',date:'2026-10-01',total:3.5},
    future:{id:'future',date:'2026-13-01',total:100},
    missing:{date:'2026-10-01',total:50},
    safe:{id:'safe',date:'2026-10-02',total:18}},payments:{}},today);
  assert.equal(res.omitted,3);
  assert.equal(res.received,18);
  assert.deepEqual(res.entries.map(e=>e.id),['safe']);
});

test('overflow in legal records fails closed for aggregate totals rather than rounding money',()=>{
  const res=accountingSettlementOverview({receipts:{a:{id:'a',date:'2026-10-01',total:Number.MAX_SAFE_INTEGER},
    b:{id:'b',date:'2026-10-02',total:1}},payments:{}},today);
  assert.equal(res.unrepresentable,true);
  assert.equal(res.received,null);
  assert.equal(res.months[11].received,null);
  assert.equal(res.entries.length,2);
  const split=accountingSettlementOverview({receipts:{a:{id:'a',date:'2026-10-01',total:Number.MAX_SAFE_INTEGER}},
    payments:{p:{id:'p',date:'2026-10-02',total:1}}},today);
  assert.equal(split.unrepresentable,true);
});

test('rendered live settlement homepage labels real totals, bank balances and empty states',()=>{
  const common={currency:'RIAL',today,canDraft:true,disabled:false,onNavigate:()=>{},onNewInvoice:()=>{}};
  const html=renderToStaticMarkup(React.createElement(AccountingVitreaHome,{...common,view}));
  assert.match(html,/دریافت‌ها و پرداخت‌ها/);
  assert.match(html,/۱٬۵۰۰ ریال/);
  assert.match(html,/۹۰۰ ریال/);
  assert.match(html,/خالص گردش نقدی این بازه/);
  assert.match(html,/مشتری الف/);
  assert.match(html,/تأمین‌کننده ب/);
  assert.match(html,/برگشت‌شده/);
  assert.match(html,/بانک الف/);
  assert.match(html,/فاکتور جدید/);
  assert.match(html,/خروجی CSV/);
  const empty=renderToStaticMarkup(React.createElement(AccountingVitreaHome,
    {...common,canDraft:false,view:{accounts:{},receipts:{},payments:{},parties:{}}}));
  assert.match(empty,/در دوازده ماه اخیر دریافت یا پرداخت قطعی ثبت نشده است/);
  assert.doesNotMatch(empty,/فاکتور جدید/);
  assert.doesNotMatch(empty,/واریز موفق|تسویه تأییدشده/);
});

test('CSV contains genuine records and protects formula injection from account and party names',()=>{
  const entries=accountingSettlementOverview(view,today).entries;
  const csv=accountingSettlementCsv(entries,{p1:{name:'=1+1'}},
    {bank:{name:'+test'}},'ریال');
  assert(csv.startsWith('\ufeff'));
  assert.match(csv,/"'=1\+1"/);
  assert.match(csv,/"'\+test"/);
  assert.match(csv,/"برگشت شده"/);
  assert.equal(csv.split('\r\n').length,6);
  assert.match(csv,/"1500"/);
});

test('accounting home uses live host view, permission gated action and navigates existing flows',()=>{
  assert.match(jsx,/import '\.\/accounting_vitrea\.css'/);
  assert.match(jsx,/tab==='overview'\?' sac-overview-work-mode sac-vtr-overview'/);
  assert.match(jsx,/<AccountingVitreaHome view=\{view\} currency=\{ledgerCurrency\} today=\{today\}/);
  assert.match(jsx,/onNewInvoice=\{openQuickInvoice\}/);
  assert.match(jsx,/canDraft&&<button type="button" className="sac-vtr-cta"/);
  assert.match(jsx,/onNavigate\('settlements'\)/);
  assert.match(jsx,/onNavigate\('cash'\)/);
  assert.match(jsx,/onNavigate\('reports'\)/);
  assert.match(jsx,/accountingSettlementCsv\(filtered,parties,accounts,unit\)/);
  assert.match(jsx,/<AccountingManagementDashboard view=\{view\}/);
  assert.doesNotMatch(jsx,/fakePayout|mockPayout|mockBalance/);
});

test('vitrea theme keeps light, dark, mobile, focus, RTL and original system flows',()=>{
  assert.match(css,/\.sac-root\.sac-vtr-overview/);
  assert.match(css,/:root\[data-theme="dark"\] \.sac-root\.sac-vtr-overview/);
  assert.match(css,/\.sac-vtr-overview-grid,.sac-vtr-bottom-grid\{display:grid/);
  assert.match(css,/@media\(max-width:1030px\)/);
  assert.match(css,/@media\(max-width:680px\)/);
  assert.match(css,/:focus-visible/);
  assert.match(css,/@media print/);
  assert(!/\.sac-vtr-home\s*\{[^}]*display\s*:\s*none/.test(css));
});

test('dark accounting ribbon overrides inherited light tab/tool surfaces without touching light mode',()=>{
  const ribbonCss=fs.readFileSync(path.join(root,'src/accounting_top_ribbon.css'),'utf8');
  assert.match(ribbonCss,/\.sac-ribbon-tabs\{[^}]*background:#f5f8f9/);
  assert.match(ribbonCss,/\.sac-ribbon-tools\{[^}]*background:#fff/);
  const source=css.slice(css.indexOf('/* The ribbon is imported through AccountingTopRibbon'));
  assert(source.length>1000,'dark ribbon overrides must be present');
  assert.match(source,/:root\[data-theme="dark"\] \.sac-root > \.sac-ribbon-shell/);
  for(const part of ['sac-ribbon-titlebar','sac-ribbon-tabs','sac-ribbon-tools',
    'sac-ribbon-tabs button.active','sac-ribbon-tools button.selected',
    'sac-ribbon-tools button.sac-ribbon-highlight',
    'sac-ribbon-quick button','sac-ribbon-hint']){
    assert(source.includes(part),part);
  }
  assert.match(source,/\.sac-ribbon-tabs\{[^}]*background:linear-gradient/);
  assert.match(source,/\.sac-ribbon-tools\{[^}]*background:linear-gradient/);
  // Every added ribbon selector is within :root[data-theme="dark"] and
  // the independent accounting root. No unconditional light-theme regression.
  const selectors=[...source.matchAll(/(^|\n)([^\n{}]+)\{/g)]
    .map(([, ,selector])=>selector.trim())
    .filter(selector=>!selector.startsWith('*')&&!selector.startsWith('/*'));
  assert(selectors.length>10);
  for(const selector of selectors){
    assert.match(selector,/:root\[data-theme="dark"\] \.sac-root > \.sac-ribbon-shell/,
      'unscoped ribbon rule: '+selector);
  }
});

test('dark accounting home adopts verified graphite glass roles without changing light defaults',()=>{
  const darkRule=css.match(/:root\[data-theme="dark"\] \.sac-root\.sac-vtr-overview\{([^}]+)\}/)?.[1];
  assert.ok(darkRule,'expected dark accounting token override');
  for(const token of ['--vtr-bg:#111113','--vtr-card:#1e1e226b',
    '--vtr-text:#f6f8fc','--vtr-soft:#c9d1de',
    '--vtr-line:#ffffff2e','--vtr-accent:#7aaef0']){
    assert(darkRule.includes(token),token);
  }
  assert.match(css,/\.sac-root\.sac-vtr-overview \.sac-vtr-panel\{[^}]*border-radius:26px/);
  assert.match(css,/\.sac-root\.sac-vtr-overview \.sac-vtr-panel\{[^}]*blur\(14px\)/);
  assert.match(css,/\.sac-root\.sac-vtr-overview :is\(\.sac-vtr-overview-grid,\.sac-vtr-bottom-grid\)\{\s*gap:16px/);
  assert.match(css,/\.sac-root\.sac-vtr-overview\{\s*--vtr-bg:#edf2f8/);
});
