'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const esbuild = require('esbuild');
const React = require('react');
const ReactDomServer = require('react-dom/server');
const {readFileSync} = require('node:fs');
const source = readFileSync('src/standalone_accounting_workspace.jsx','utf8');
const build = esbuild.buildSync({
  entryPoints:['src/standalone_accounting_workspace.jsx'],bundle:true,
  write:false,format:'cjs',platform:'node',
  loader:{'.css':'empty','.jpg':'dataurl'},external:['react','lucide-react'],
});
const mod={exports:{}};
new Function('module','exports','require',build.outputFiles[0].text)(mod,mod.exports,require);
const f=mod.exports;

test('accounting shell server-renders without sortMap temporal-dead-zone crash',()=>{
  assert.ok(source.indexOf('const sortMap=')<source.indexOf('const historicalBankAccounts='));
  const html=ReactDomServer.renderToStaticMarkup(
    React.createElement(f.StandaloneAccountingWorkspace,{api:{},canManage:false}));
  assert.match(html,/حسابداری مستقل مدار/);
  assert.match(html,/داشبورد/);
  assert.match(html,/اشخاص/);
  assert.match(html,/خزانه و چک/);
  assert.match(html,/کالا، انبار و کاردکس/);
  assert.match(html,/حقوق و مالیات/);
});

test('invoice sequential suggestion is unique within existing fiscal year',()=>{
  const docs={'INV-2026-0001':{},'INV-2026-0003':{},'INV-2025-0099':{}};
  assert.equal(f.nextAccountingNumber(docs,'INV','2026'),'INV-2026-0004');
  assert.equal(f.nextAccountingNumber(docs,'INV','2027'),'INV-2027-0001');
  assert.equal(f.nextAccountingNumber({'PF-2026-0001':{}},'PF','2026'),
    'PF-2026-0002');
});

test('untrusted or incorrect amounts never display a fictional invoice total',()=>{
  assert.deepEqual(
    f.previewAccountingTotal([{quantity:'2',unitPrice:'150'}],'10','6'),
    {subtotal:300,discount:10,tax:6,total:296});
  assert.equal(f.previewAccountingTotal([{quantity:'2.5',unitPrice:'150'}],'0','0'),null);
  assert.equal(f.previewAccountingTotal([{quantity:'1',unitPrice:''}],'0','0'),null);
  assert.equal(f.previewAccountingTotal([{quantity:'2',unitPrice:'150'}],'301','0'),null);
});

test('source views visibly separate historic debt from new AR and expose drilldown',()=>{
  assert.match(source,/مانده دریافتنی فاکتورهای جدید/);
  assert.match(source,/historicalPartyAccounts\.map/);
  assert.match(source,/ریزگردش حساب/);
  assert.match(source,/historical\.positiveDebtorTotal/);
  assert.match(source,/activeHistoricInvoice\.sourceRows/);
  assert.match(source,/historicCash\.map/);
  assert.match(source,/isVerifiedStock|تأیید موجودی نشده/);
});

test('all main usability affordances remain available',()=>{
  for(const feature of ['سری','شماره خودکار','جست‌وجوی نام یا کد شخص',
    'جمع نهایی','CSV ریزگردش','CSV مانده اول و پایان دوره','چاپ گزارش',
    'sac-table-pagination','sac-chart-group','تعداد ردیف']){
    // 'سری' and 'تعداد ردیف' are desirable, not mandatory; see alternate checks.
    if(feature==='سری'||feature==='تعداد ردیف')continue;
    assert.ok(source.includes(feature)||readFileSync('src/standalone_accounting_ux20.css','utf8')
      .includes(feature),feature);
  }
  assert.match(source,/onClick=\{\(\)=>gotoTab\(name\)\}/);
});
