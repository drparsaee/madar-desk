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
const file=path.join(root,'src/accounting_panel.jsx');
const source=fs.readFileSync(file,'utf8');
const css=fs.readFileSync(path.join(root,'src/accounting_panel.css'),'utf8');
const compiled=esbuild.buildSync({entryPoints:[file],bundle:true,
  platform:'node',format:'cjs',write:false,external:['react','react/jsx-runtime','lucide-react'],
  loader:{'.css':'empty'}}).outputFiles[0].text;
const mockFile=path.join(root,'tests','accounting-panel-ui-virtual.cjs');
const mod=new Module(mockFile,module);
mod.filename=mockFile;
mod.paths=Module._nodeModulePaths(path.dirname(mockFile));
mod._compile(compiled,mockFile);
const {AccountingPanel,parseAccountingAmount,validateSaleInput,validPostingDate,
  activeExpenseSources,outstandingDocuments,validateSettlement}=mod.exports;

const render=props=>renderToStaticMarkup(React.createElement(AccountingPanel,{
  api:{accountingRead:async()=>({expenseSources:[],balances:[],documents:[]}),
    accountingCommand:async()=>({})},
  canManage:true,projects:[{id:'p1',name:'پروژه یک'}],
  tasks:[{id:'t1',projectId:'p1',title:'تسک شماره یک',cost:250000,
    checklist:[{id:'step1',cost:6000,text:'مرحله'}]}],onClose(){},...props,
}));

test('amount parsing supports valid Persian, Arabic and grouped whole tomans',()=>{
  for(const [value,expected] of [
    ['0',0],['1000',1000],['۱۰۰۰',1000],['١٠٠٠',1000],['۱٬۲۳۴',1234],
    ['1,234,567',1234567],[' ۲۵۰٬۰۰۰ ',250000],['1000000000000000',1e15],
  ])assert.equal(parseAccountingAmount(value),expected,value);
  for(const bad of ['',undefined,null,[],{},true,'۰۱','01','1,00','1,2345',
    '-15','0.5','1.0','2e5','NaN','Infinity','1 000','1,23,456',
    '1000000000000001','9007199254740992'])assert.equal(parseAccountingAmount(bad),null,String(bad));
});

test('sales validation rejects empty or zero prices, overflow and invalid totals',()=>{
  const baseline={description:'خدمات طراحی',quantity:'۲',unitPrice:'۱۵۰٬۰۰۰',
    discount:'0',tax:'0',advance:'0'};
  const valid=validateSaleInput(baseline);
  assert.equal(valid.error,'');
  assert.deepEqual(valid.values,{count:2,unit:150000,discountValue:0,
    taxValue:0,advanceValue:0,total:300000});
  for(const update of [
    {unitPrice:'0'},{unitPrice:''},{quantity:'0'},{quantity:'100001'},
    {discount:'300001'},{tax:'1000000000000000'}, {advance:'300001'},
    {description:' '},{description:'x'.repeat(301)},
    {quantity:'100000',unitPrice:'1000000000000'},
  ])assert.ok(validateSaleInput({...baseline,...update}).error,JSON.stringify(update));
  assert.equal(validateSaleInput({...baseline,discount:'۳۰۰٬۰۰۰'}).error.length>0,true);
});

test('purchase sources always use authoritative backend IDs and positive basis',()=>{
  const rows=[
    {cardId:'t1',sourceId:'direct',description:'هزینه مستقیم',actual:0,estimated:5000},
    {cardId:'t1',sourceId:'list-a:step-1',description:'مرحله اول',actual:375,estimated:425},
    {cardId:'t1',sourceId:'list-a:step-2',description:'مرحله دوم',actual:0,estimated:0},
    {cardId:'t2',sourceId:'direct',description:'Other task',actual:900,estimated:900},
    {cardId:'t1',sourceId:'bad',description:'Invalid',actual:-100,estimated:1},
  ];
  assert.deepEqual(activeExpenseSources(rows,'t1','actual').map(s=>s.id),['list-a:step-1']);
  assert.deepEqual(activeExpenseSources(rows,'t1','estimated').map(s=>s.id),
    ['direct','list-a:step-1','bad']);
  assert.deepEqual(activeExpenseSources(undefined,'t1','actual'),[]);
  assert.deepEqual(activeExpenseSources(rows,'t1','arbitrary'),[]);
  assert.deepEqual(activeExpenseSources(rows,'unknown','actual'),[]);
});

test('payment candidates are issued, same-project, identified, and strictly outstanding',()=>{
  const base={id:'I-1',projectId:'p1',status:'Issued',kind:'sales',
    party:{id:'customer-1',name:'مشتری'},total:1000,allocated:200,
    postingDate:'2026-10-15'};
  const variants=[base,
    {...base,id:'B-2',kind:'purchase',allocated:0},
    {...base,id:'I-3',projectId:'p2'},
    {...base,id:'I-4',status:'Draft'},
    {...base,id:'I-5',allocated:1000},
    {...base,id:'I-6',total:0,allocated:0},
    {...base,id:'I-7',party:null},
    {...base,id:'I-8',allocated:'0'},
  ];
  assert.deepEqual(outstandingDocuments(variants,'p1').map(d=>d.id),['I-1','B-2']);
  assert.deepEqual(outstandingDocuments(variants,'other'),[]);
  assert.deepEqual(outstandingDocuments(null,'p1'),[]);
});

test('settlement requires explicit selected invoice, positive bounded amount and valid chronology',()=>{
  const invoice={total:1000,allocated:400,postingDate:'2026-10-15'};
  assert.equal(validateSettlement(invoice,'۶۰۰','2026-10-15','2026-10-21').amount,600);
  for(const [target,amount,date] of [
    [null,'100','2026-10-20'],[invoice,'0','2026-10-20'],
    [invoice,'601','2026-10-20'],[invoice,'-1','2026-10-20'],
    [invoice,'','2026-10-20'],[invoice,'100','2026-10-14'],
    [invoice,'100','2026-10-22'],[invoice,'100','2026-02-30'],
  ])assert.ok(validateSettlement(target,amount,date,'2026-10-21').error);
  assert.equal(validPostingDate('2024-02-29','2026-10-21'),true);
  assert.equal(validPostingDate('2025-02-29','2026-10-21'),false);
});

test('unauthorized user receives no accounting form or balances (SSR)',()=>{
  const html=render({canManage:false});
  assert.match(html,/فقط برای مدیر/);
  assert.doesNotMatch(html,/ثبت سرمایه واقعی|فاکتور صادرشده|ثبت پیش‌نویس/);
});

test('SSR uses labelled dialog, reliable close button, RTL, required inputs and visible loading state',()=>{
  const html=render();
  assert.match(html,/role="dialog"/);
  assert.match(html,/aria-modal="true"/);
  assert.match(html,/aria-labelledby="accounting-title"/);
  assert.match(html,/aria-describedby="accounting-guidance"/);
  assert.match(html,/dir="rtl"/);
  assert.match(html,/aria-label="بستن حسابداری"/);
  assert.match(html,/تاریخ ثبت و صدور/);
  assert.match(html,/فاکتور موردنظر را انتخاب کنید/);
  assert.match(source,/منبع هزینه را انتخاب کنید/);
  assert.match(html,/نام شخص/);
  assert.match(html,/در حال دریافت اطلاعات این پروژه/);
  assert.doesNotMatch(html,/PRIVATE_TASK/);
});

test('SSR has no automatic default payment or speculative purchase source',()=>{
  const html=render();
  assert.match(html,/value=""/);
  assert.match(source,/منبع هزینه را انتخاب کنید/);
  assert.match(html,/فاکتور موردنظر را انتخاب کنید/);
  assert.match(html,/disabled=""/);
  assert.doesNotMatch(html,/checklist-legacy:|برآورد ۲۵۰٬۰۰۰/);
  assert.match(source,/const paymentTarget=issuedDocuments\.find\(d=>d\.id===paymentFor\)/);
  assert.doesNotMatch(source,/issuedDocuments\[0\]/);
  assert.doesNotMatch(source,/expenseSources\[0\]/);
});

test('stateless UI contract preserves payment posting idempotency and user confirmation',()=>{
  assert.match(source,/if\(pending\.current\?\.identity!==identity\)pending\.current=/);
  assert.match(source,/const id=pending\.current\.eventId/);
  assert.match(source,/\.\.\.recordId,eventId:id/);
  assert.match(source,/paymentId:id/);
  assert.match(source,/receiptId:id/);
  assert.match(source,/window\.confirm\(summary/);
  assert.match(source,/paymentTarget\.kind==='sales'/);
  assert.match(source,/setPaymentFor\(''\);setPaymentAmount\(''\)/);
  assert.match(source,/inFlight\.current/);
});

test('readiness and change controls require project scoped authoritative read',()=>{
  assert.match(source,/const readReady=loadedProjectId===projectId&&!loading/);
  assert.match(source,/setLoadedProjectId\(''\)/);
  assert.match(source,/d\.projectId===projectId/);
  assert.match(source,/typeof api\.accountingRead!=='function'/);
  assert.match(source,/!Array\.isArray\(value\.expenseSources\)/);
  assert.match(source,/!hasSelectedCost/);
  assert.match(source,/const sourceId=selectedSource\.id/);
  assert.doesNotMatch(source,/selected\.checklists\.flatMap/);
});

test('modal styles support own scrolling with body locked, mobile layout and keyboard focus',()=>{
  assert.match(css,/max-height:calc\(100dvh/);
  assert.match(css,/overflow:auto/);
  assert.match(css,/grid-template-columns:minmax\(0,1fr\)/);
  assert.match(css,/:focus-visible/);
  assert.match(css,/prefers-reduced-motion/);
  assert.match(css,/overscroll-behavior:contain/);
  assert.match(source,/event\.key==='Escape'/);
  assert.match(source,/event\.key!=='Tab'/);
  assert.match(source,/previousFocus\.current\?\.focus/);
});
