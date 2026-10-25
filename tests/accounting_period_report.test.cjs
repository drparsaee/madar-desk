'use strict';
const test=require('node:test'), assert=require('node:assert/strict');
const esbuild=require('esbuild');
const code=esbuild.buildSync({entryPoints:['src/accounting_period_report.js'],
  bundle:true,write:false,format:'cjs',platform:'node'}).outputFiles[0].text;
const mod={exports:{}};new Function('module','exports',code)(mod,mod.exports);
const {accountingPeriodRows}=mod.exports;
const view={
  accounts:{
    bank:{id:'bank',name:'Bank',kind:'asset',debitMinusCredit:950},
    sale:{id:'sale',name:'Revenue',kind:'revenue',debitMinusCredit:-950},
  },
  journals:[
    {id:'J:1',date:'2026-09-30',lines:[
      {accountId:'bank',debit:600,credit:0},
      {accountId:'sale',debit:0,credit:600}]},
    {id:'J:3',date:'2026-10-12',lines:[
      {accountId:'bank',debit:150,credit:0},
      {accountId:'sale',debit:0,credit:150}]},
    {id:'J:2',date:'2026-10-01',lines:[
      {accountId:'bank',debit:200,credit:0},
      {accountId:'sale',debit:0,credit:200}]},
  ],
};
test('opening, movements, closing are exact across dates and both sides',()=>{
  const out=accountingPeriodRows(view,{fromDate:'2026-10-01',toDate:'2026-10-11'});
  assert.equal(out.error,'');
  assert.equal(out.journalCount,1);
  const bank=out.rows.find(x=>x.accountId==='bank');
  const sale=out.rows.find(x=>x.accountId==='sale');
  assert.deepEqual([bank.openingDebit,bank.debitMovement,bank.creditMovement,bank.closingDebit],
    [600,200,0,800]);
  assert.deepEqual([sale.openingCredit,sale.debitMovement,sale.creditMovement,sale.closingCredit],
    [600,0,200,800]);
  assert.equal(out.periodDebit,out.periodCredit);
});
test('without a start date opening zero and all entries through endpoint counted',()=>{
  const out=accountingPeriodRows(view,{toDate:'2026-10-12'});
  assert.equal(out.error,'');
  assert.equal(out.journalCount,3);
  assert.equal(out.rows[0].openingSigned,0);
  assert.equal(out.rows[0].closingSigned,950);
});
test('account-only filter counts selected entries and rejects unknown account',()=>{
  const out=accountingPeriodRows(view,{fromDate:'2026-10-01',accountId:'sale'});
  assert.equal(out.error,'');
  assert.equal(out.rows.length,1);
  assert.equal(out.journalCount,2);
  assert.equal(out.periodDebit,0);
  assert.equal(out.periodCredit,350);
  assert.match(accountingPeriodRows(view,{accountId:'missing'}).error,/کد حساب/);
});
test('invalid dates, malformed ledger amounts and overflow fail closed',()=>{
  assert.ok(accountingPeriodRows(view,{fromDate:'2026-02-31'}).error);
  assert.ok(accountingPeriodRows(view,{fromDate:'2026-10-20',toDate:'2026-10-19'}).error);
  assert.ok(accountingPeriodRows({...view,journals:[
    {...view.journals[0],lines:[{accountId:'bank',debit:NaN,credit:0}]}
  ]}).error);
  assert.ok(accountingPeriodRows({...view,journals:[
    {...view.journals[0],lines:[{accountId:'bank',debit:Number.MAX_SAFE_INTEGER,credit:0}]},
    {...view.journals[0],id:'second',lines:[
      {accountId:'bank',debit:Number.MAX_SAFE_INTEGER,credit:0}]},
  ]}).error);
});
