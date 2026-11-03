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
const source=fs.readFileSync(path.join(root,'src/accounting_action_home.jsx'),'utf8');
const css=fs.readFileSync(path.join(root,'src/accounting_action_home.css'),'utf8');
const workspace=fs.readFileSync(path.join(root,'src/standalone_accounting_workspace.jsx'),'utf8');
const code=esbuild.buildSync({entryPoints:[path.join(root,'src/accounting_action_home.jsx')],
  bundle:true,platform:'node',format:'cjs',write:false,jsx:'automatic',
  loader:{'.css':'empty'},external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const shim=new Module(path.join(root,'tests/accounting-action-home-virtual.cjs'),module);
shim.filename=path.join(root,'tests/accounting-action-home-virtual.cjs');
shim.paths=Module._nodeModulePaths(path.dirname(shim.filename));
shim._compile(code,shim.filename);
const {buildAccountingActionSummary,readActionHomePreferences,default:AccountingActionHome}=shim.exports;

const today='2026-11-03';
function sample(){
  return {currency:'RIAL',accounts:{
    '4000':{kind:'revenue'},'5000':{kind:'expense'},'5300':{kind:'expense'}},
    invoices:{
      sale:{id:'sale',status:'issued',postingDate:today,dueDate:'2026-11-01',
        total:300000,allocated:0,returnedAmount:0,
        lines:[{itemId:'SKU',quantity:2}]},
      draft:{id:'draft',status:'draft',total:9000000000,allocated:0,
        lines:[{description:'Not posted'}]}},
    bills:{purchase:{id:'purchase',status:'issued',dueDate:'2026-11-10',
      total:700000,allocated:200000,returnedAmount:100000},
      reviewed:{id:'reviewed',status:'approved',total:90000}},
    items:{SKU:{id:'SKU',stockTracked:true}},stockMovements:{},returns:{},
    bankStatements:{b1:{id:'b1',journalId:null},b2:{id:'b2',journalId:'j1'}},
    receipts:{},payments:{},
    journals:[{id:'j1',date:today,sourceType:'invoice.issue',lines:[
      {accountId:'4000',debit:0,credit:300000}]}]};
}

test('issued-open AR/AP monetary amounts, counts, and supported due dates are exact',()=>{
  const s=buildAccountingActionSummary(sample(),today);
  assert.equal(s.error,'');
  assert.deepEqual({sum:s.ar.amount,count:s.ar.count,overdue:s.ar.overdueAmount,
    overdueCount:s.ar.overdueCount},
    {sum:300000n,count:1,overdue:300000n,overdueCount:1});
  assert.deepEqual({sum:s.ap.amount,count:s.ap.count,overdue:s.ap.overdueCount,
    undated:s.ap.undatedCount},
    {sum:400000n,count:1,overdue:0,undated:0});
  assert.deepEqual(s.approvals,{draft:1,approved:1});
  assert.deepEqual(s.bank,{unmatched:1,registered:2});
  assert.equal(s.cogs.count,1);
  assert.deepEqual(s.cogs.pending,[{invoiceId:'sale',itemId:'SKU',missingQuantity:2n}]);
  assert.equal(s.cashReceivedMonth,0n);
  assert.equal(s.salesMonth,300000n);
  assert.equal(s.ledgerNetMonth,300000n);
});

test('cash receipts and sales stay distinct, partial returns reduce open AR, issues clear COGS',()=>{
  const view=sample();
  view.receipts={r:{date:today,total:50000,reversed:false},
    void:{date:today,total:1000000,reversed:true}};
  view.invoices.sale.returnedAmount=50000;
  view.invoices.sale.returnedQuantities=[1];
  view.returns={credit:{kind:'partial',direction:'sale',documentId:'sale',
    lines:[{lineIndex:0,quantity:1}]}};
  view.stockMovements={issue:{id:'issue',type:'inventory.issue',itemId:'SKU',
    invoiceId:'sale',quantity:1}};
  view.journals.push({id:'cost',sourceType:'inventory.issue',date:today,
    lines:[{accountId:'5300',debit:70000,credit:0}]});
  const s=buildAccountingActionSummary(view,today);
  assert.equal(s.ar.amount,250000n);
  assert.equal(s.cashReceivedMonth,50000n);
  assert.equal(s.salesMonth,250000n);
  assert.equal(s.ledgerNetMonth,230000n);
  assert.deepEqual(s.cogs,{count:0,pending:[]});
});

test('large valid sums use BigInt, malformed money and dates fail closed',()=>{
  const v=sample();
  v.invoices.sale.total=Number.MAX_SAFE_INTEGER;
  v.invoices.other={id:'other',status:'issued',total:Number.MAX_SAFE_INTEGER,
    allocated:0,dueDate:null,postingDate:today,lines:[]};
  let s=buildAccountingActionSummary(v,today);
  assert.equal(s.ar.amount,2n*BigInt(Number.MAX_SAFE_INTEGER));
  assert.equal(s.ar.undatedCount,1);
  v.invoices.other.total=Number.MAX_SAFE_INTEGER+1;
  s=buildAccountingActionSummary(v,today);
  assert.equal(s.ar.amount,null);
  assert.equal(s.ar.count,null);
  v.invoices.other.total=100;
  v.invoices.other.dueDate='2026-11-99';
  s=buildAccountingActionSummary(v,today);
  assert.equal(s.ar.overdueAmount,null);
  assert.equal(s.ar.invalid,true);
  assert.equal(buildAccountingActionSummary(v,'1405/08/12').error.length>0,true);
});

test('only existing bank statement rows count as unmatched, absent source is unknown',()=>{
  const v=sample();
  delete v.bankStatements;
  delete v.stockMovements;
  let s=buildAccountingActionSummary(v,today);
  assert.equal(s.bank,null);
  assert.equal(s.cogs,null);
  v.bankStatements={};v.stockMovements={};
  s=buildAccountingActionSummary(v,today);
  assert.deepEqual(s.bank,{unmatched:0,registered:0});
  assert.equal(s.cogs.count,1);
});

test('host-verified outstanding COGS takes precedence over local projection',()=>{
  const v=sample();
  v.financialReports={profitLossComplete:true,unpostedGoodsIssues:[]};
  assert.deepEqual(buildAccountingActionSummary(v,today).cogs,{count:0,pending:[]});
  v.financialReports={profitLossComplete:false,unpostedGoodsIssues:[
    {invoiceId:'posted',itemId:'SKU',lineIndex:0,missingQuantity:1}]};
  assert.deepEqual(buildAccountingActionSummary(v,today).cogs,{count:1,
    pending:[{invoiceId:'posted',itemId:'SKU',missingQuantity:1n}]});
  v.financialReports.profitLossComplete=true;
  assert.equal(buildAccountingActionSummary(v,today).cogs,null);
});

test('read-only user sees six real destinations but no posting CTA',()=>{
  const markup=renderToStaticMarkup(React.createElement(AccountingActionHome,{
    view:sample(),today,canDraft:false,canSettle:false,onNavigate:()=>{},
    onNewInvoice:()=>{}}));
  assert.match(markup,/کارهای مالی امروز/);
  assert.match(markup,/۳۰۰٬۰۰۰ ریال/);
  assert.match(markup,/۴۰۰٬۰۰۰ ریال/);
  assert.match(markup,/مغایرت‌گیری/);
  assert.match(markup,/پیش‌نویس/);
  assert.match(markup,/سود قطعی نیست/);
  assert.doesNotMatch(markup,/فاکتور فروش جدید|ثبت دریافت|ثبت پرداخت/);
  assert.equal((markup.match(/class="sac-ah-action /g)||[]).length,6);
  assert.equal((markup.match(/type="checkbox"/g)||[]).length,7);
  const manager=renderToStaticMarkup(React.createElement(AccountingActionHome,{
    view:sample(),today,canDraft:true,canSettle:true,disabled:false,
    onNavigate:()=>{},onNewInvoice:()=>{}}));
  assert.match(manager,/فاکتور فروش جدید/);
  assert.match(manager,/ثبت دریافت/);
  assert.match(manager,/ثبت پرداخت/);
});

test('custom layout reads only per-user-company storage key; invalid data restores defaults',()=>{
  const data=new Map();
  const storage={getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value)};
  data.set('madar.accounting.home.v1.admin%7CAlpha',JSON.stringify(['payables','cogs']));
  assert.deepEqual(readActionHomePreferences(storage,'admin|Alpha'),['payables','cogs']);
  assert.equal(readActionHomePreferences(storage,'admin|Beta').length,7);
  assert.equal(readActionHomePreferences(storage,'viewer|Alpha').length,7);
  data.set('madar.accounting.home.v1.admin%7CAlpha','corrupt');
  assert.equal(readActionHomePreferences(storage,'admin|Alpha').length,7);
  assert.equal(readActionHomePreferences(storage,'').length,7);
});

test('integration is a single home insertion and mobile styles have keyboard targets',()=>{
  assert.match(workspace,/import AccountingActionHome from '\.\/accounting_action_home\.jsx'/);
  assert.match(workspace,/<AccountingActionHome view=\{view\} today=\{today\}/);
  assert.match(workspace,/snapshot\.currentUser\.username\+'\|'\+view\.companyWorkspaceLabel/);
  assert.match(source,/onNavigate\(tab\)/);
  assert.match(css,/\.sac-ah :is\(button,summary,input\):focus-visible/);
  assert.match(css,/@media\(max-width:650px\)/);
  assert.match(css,/min-height:44px/);
  assert.doesNotMatch(source,/execute\(|standaloneAccountingCommand|\.command\(/);
});
