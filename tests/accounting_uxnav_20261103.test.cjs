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
const load=file=>{
  const target=path.join(root,'src',file);
  const built=esbuild.buildSync({entryPoints:[target],bundle:true,platform:'node',
    format:'cjs',write:false,jsx:'automatic',external:['react','react/jsx-runtime','lucide-react'],
    loader:{'.css':'empty','.jpg':'dataurl'}}).outputFiles[0].text;
  const mod=new Module(path.join(root,'tests','uxnav-virtual.cjs'),module);
  mod.filename=path.join(root,'tests','uxnav-virtual.cjs');
  mod.paths=Module._nodeModulePaths(path.dirname(mod.filename));
  mod._compile(built,mod.filename);
  return mod.exports;
};
const {ACCOUNTING_PRIMARY_SECTIONS,normalizeAccountingSearch,
  accountingVisibleSections,buildAccountingSearchIndex,searchAccountingIndex}=
  load('accounting_nav_search.js');
const Ribbon=load('accounting_top_ribbon.jsx').default;
const SECTIONS=[['overview','داشبورد'],['invoice','فاکتورهای فروش'],
  ['bill','صورتحساب‌های خرید'],['settlements','دریافت و پرداخت'],
  ['reports','گزارش‌های مالی'],['parties','اشخاص'],['accounts','حساب‌ها و دفترکل'],
  ['journal','سند دستی و برگشت'],['migration','مهاجرت و سوابق'],
  ['settings','تنظیمات حسابداری']];
const view={
  companyProfile:{legalName:'شرکت ساختگی'},
  invoices:{'INV-QA-001':{id:'INV-QA-001',number:68,partyId:'buyer',
    note:'SECRET-NOTE-DO-NOT-INDEX',lines:[{description:'SECRET-LINE'}]}},
  bills:{'BILL-QA-01':{id:'BILL-QA-01',partyId:'supplier'}},
  proformas:{'PF-QA-01':{id:'PF-QA-01',partyId:'buyer'}},
  parties:{buyer:{id:'buyer',name:'مشتری آزمایشی'},
    supplier:{id:'supplier',name:'تأمین‌کننده آزمایشی',password:'SECRET-LOGIN'}},
  accounts:{'1100':{id:'1100',name:'حساب دریافتنی'}},
  journals:[{id:'GL-001',note:'SECRET-JOURNAL-NOTE'}],
  receipts:{'RC-001':{id:'RC-001',partyId:'buyer',total:155000}},
  payments:{'PAY-001':{id:'PAY-001',partyId:'supplier',total:150000}},
  parsianMigration:{raw:'SECRET-ARCHIVE'},
};
const render=overrides=>renderToStaticMarkup(React.createElement(Ribbon,{
  tab:'overview',sections:SECTIONS,currentUser:{role:'admin',username:'admin'},
  canDraft:true,canManage:true,canAdmin:true,searchView:view,
  onNavigate:()=>{},onNewInvoice:()=>{},onExit:()=>{},...overrides
}));

test('normalization supports Persian/Arabic spelling and numeric invoice identifiers',()=>{
  assert.equal(normalizeAccountingSearch('  حساب كاربري  ۶٨ '),'حساب کاربری 68');
  assert.equal(normalizeAccountingSearch('مُشتریِ ۰۰۶۸'),'مشتری 0068');
});

test('global search indexes only whitelisted fields from the host-visible snapshot',()=>{
  const index=buildAccountingSearchIndex({sections:SECTIONS,view,role:'admin'});
  const byId=searchAccountingIndex(index,'INV-QA-001');
  assert.equal(byId[0].recordId,'INV-QA-001');
  assert.equal(byId[0].tab,'invoice');
  assert.equal(byId[0].type,'invoice');
  assert.match(byId[0].subtitle,/مشتری آزمایشی/);
  assert.equal(searchAccountingIndex(index,'68')[0].recordId,'INV-QA-001',
    'plain numeric invoice number must be indexed');
  assert.ok(searchAccountingIndex(index,'مشتری').some(item=>item.type==='party'));
  assert.ok(searchAccountingIndex(index,'مشتری').some(item=>item.type==='invoice'));
  assert.ok(searchAccountingIndex(index,'1100').some(item=>item.type==='account'));
  assert.ok(searchAccountingIndex(index,'GL-001').some(item=>item.type==='journal'));
  assert.ok(searchAccountingIndex(index,'PAY-001').some(item=>item.type==='payment'));
  const serial=JSON.stringify(index);
  for(const secret of ['SECRET-NOTE','SECRET-LINE','SECRET-LOGIN','SECRET-JOURNAL','SECRET-ARCHIVE','155000'])
    assert.ok(!serial.includes(secret),'Must not index sensitive metadata: '+secret);
});

test('permission changes revoke results immediately; an absent snapshot yields only sections',()=>{
  const viewer=buildAccountingSearchIndex({sections:SECTIONS,view,role:'viewer',
    recordAccess:{bills:false,accounts:false}});
  assert.equal(searchAccountingIndex(viewer,'BILL-QA-01').length,0);
  assert.equal(searchAccountingIndex(viewer,'1100').length,0);
  assert.equal(searchAccountingIndex(viewer,'مهاجرت').length,0);
  assert.ok(searchAccountingIndex(viewer,'INV-QA-001').length>0,
    'Read-only users may find already-authorized invoices');
  const hidden=buildAccountingSearchIndex({sections:SECTIONS,view,role:'admin',
    sectionAccess:{invoices:false,invoice:false,journal:false}});
  assert.equal(searchAccountingIndex(hidden,'INV-QA-001').length,0);
  assert.equal(searchAccountingIndex(hidden,'GL-001').length,0);
  const noHost=buildAccountingSearchIndex({sections:SECTIONS,role:'admin'});
  assert.equal(searchAccountingIndex(noHost,'INV-QA-001').length,0);
  assert.ok(searchAccountingIndex(noHost,'گزارش').length>0);
  assert.deepEqual(accountingVisibleSections(SECTIONS,'invalid'),[]);
});

test('bounded search does not interpret markup as trusted HTML or arbitrary fields',()=>{
  const hostile={parties:{a:{id:'a',name:'<img src=x onerror=alert(1)>'}}};
  const index=buildAccountingSearchIndex({sections:SECTIONS,view:hostile,role:'viewer'});
  const matched=searchAccountingIndex(index,'img');
  assert.equal(matched.length,1);
  assert.equal(matched[0].type,'party');
  assert.deepEqual(searchAccountingIndex(index,'x'.repeat(141)),[]);
  assert.deepEqual(searchAccountingIndex(index,'',12),[]);
  assert.equal(searchAccountingIndex(index,'img',1000).length,1);
});

test('simple task navigation uses familiar routes; viewer sees no privileged quick actions',()=>{
  const html=render({currentUser:{username:'viewer',role:'viewer'},
    canDraft:false,canManage:false,canAdmin:false});
  assert.match(html,/sac-simple-nav/);
  assert.match(html,/مسیرهای اصلی حسابداری/);
  assert.match(html,/جست‌وجوی حسابداری \(Ctrl\+K\)/);
  assert.match(html,/aria-pressed="true">ساده<\/button>/);
  assert.match(html,/aria-pressed="false">پیشرفته<\/button>/);
  assert.match(html,/data-accounting-tab="overview"/);
  assert.match(html,/data-accounting-tab="invoice"/);
  assert.match(html,/data-accounting-tab="bill"/);
  assert.match(html,/data-accounting-tab="reports"/);
  assert.doesNotMatch(html,/ثبت پرداخت|فاکتور جدید|خرید جدید/);
  assert.deepEqual(ACCOUNTING_PRIMARY_SECTIONS,
    ['overview','invoice','bill','settlements','reports']);
});

test('manager and admin privileges are reflected only where authorized',()=>{
  const manager=render({currentUser:{username:'manager',role:'editor'},canAdmin:false});
  assert.match(manager,/فاکتور جدید/);
  assert.match(manager,/دریافت و پرداخت/);
  const wiredManager=render({currentUser:{username:'manager',role:'editor'},
    canAdmin:false,onQuickAction:()=>{}});
  assert.match(wiredManager,/ثبت پرداخت/);
  assert.match(manager,/خرید جدید/);
  assert.match(manager,/گزارش‌ها/);
  const contradictory=render({currentUser:{username:'readonly',role:'viewer'},
    canDraft:true,canManage:true,canAdmin:true});
  assert.doesNotMatch(contradictory,/ثبت پرداخت|فاکتور جدید|خرید جدید/);
  const noContext=render({searchView:null});
  assert.match(noContext,/جست‌وجوی حسابداری/);
});

test('navigation CSS provides one visible mobile navigation row and explicit More',()=>{
  const css=fs.readFileSync(path.join(root,'src/accounting_navigation_shell.css'),'utf8');
  assert.match(css,/@media\(max-width:700px\)/);
  assert.match(css,/\.sac-simple-nav\{display:grid;grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/);
  assert.match(css,/\.sac-nav-quick-actions\{display:none\}/);
  assert.match(css,/\.sac-ux-advanced \.sac-simple-navigation\{display:block\}/);
  const source=fs.readFileSync(path.join(root,'src/accounting_navigation_shell.jsx'),'utf8');
  assert.match(source,/data-accounting-tab=\{key\}/);
  assert.match(source,/data-accounting-tab="settings"/);
  assert.match(source,/aria-expanded=\{moreOpen\}/);
  assert.match(source,/aria-label="فهرست بخش‌های دیگر"/);
  assert.match(source,/onSearchSelect=|onSearchSelect=null/);
});
