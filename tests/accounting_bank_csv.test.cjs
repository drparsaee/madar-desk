'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const esbuild=require('esbuild');
const code=esbuild.buildSync({entryPoints:['src/accounting_bank_csv.js'],
  bundle:true,write:false,format:'cjs',platform:'node'}).outputFiles[0].text;
const mod={exports:{}};new Function('module','exports',code)(mod,mod.exports);
const {parseAccountingBankCSV,parseAccountingBankAmount,accountingBankNetExact}=mod.exports;
const context={today:'2026-10-25',accounts:{
  '1010':{liquid:true,kind:'asset'},'1000':{liquid:true,kind:'asset'},
  '2000':{liquid:false,kind:'liability'},
}};
const csv=lines=>'statementId;accountId;date;amount;reference\n'+lines.join('\n');

test('valid offline bank CSV parses Persian dates/digits and keeps exact signed amounts',()=>{
  const rows=parseAccountingBankCSV(csv([
    'S01;1010;۱۴۰۵/۰۸/۰۳;۱,۰۰۰;ref-01',
    'S02;1010;2026-10-24;-999;ref-02',
  ]),context);
  assert.deepEqual(rows.map(r=>[r.date,r.amount]),[
    ['2026-10-25',1000],['2026-10-24',-999]]);
  assert.equal(accountingBankNetExact(rows),1n);
});

test('impossible, future and disguised Gregorian dates rejected before entire batch',()=>{
  for(const bad of ['2026-02-31','2026-10-26','2025-13-01','1880-01-01']){
    assert.throws(()=>parseAccountingBankCSV(csv([
      'S01;1010;2026-10-24;100;valid',
      'S02;1010;'+bad+';200;bad',
    ]),context),/تاریخ/);
  }
});

test('duplicate bank ids and references reject import before posting',()=>{
  const existing={old:{id:'old',accountId:'1010',reference:'r1'}};
  assert.throws(()=>parseAccountingBankCSV(csv(['OLD;1010;2026-10-24;1;r2']),
    {...context,existing}),/تکراری/);
  assert.throws(()=>parseAccountingBankCSV(csv(['fresh;1010;2026-10-24;1;r1']),
    {...context,existing}),/تکراری/);
  assert.throws(()=>parseAccountingBankCSV(csv([
    'A;1010;2026-10-24;1;r2',
    'a;1010;2026-10-24;2;r3']),context),/تکراری/);
  assert.throws(()=>parseAccountingBankCSV(csv([
    'A;1010;2026-10-24;1;r2',
    'B;1010;2026-10-24;2;r2']),context),/تکراری/);
});

test('refuse zero, fractional, oversized, control characters and malformed CSV',()=>{
  for(const bad of ['0','1.5','1000000000000001','--3','Infinity',
    '1 000','1,23','12,34,567','1,,000','۱٬۲۳']){
    assert.throws(()=>parseAccountingBankCSV(csv(['A;1010;2026-10-24;'+bad+';r']),
      context),/مبلغ/);
  }
  assert.throws(()=>parseAccountingBankCSV(csv(['A;1010;2026-10-24;1;']),
    context),/مرجع/);
  assert.throws(()=>parseAccountingBankCSV(csv(['A;2000;2026-10-24;1;r']),
    context),/حساب/);
  assert.throws(()=>parseAccountingBankCSV(csv(['A;1010;2026-10-24;1;foo\rbar']),
    context),/قالب/);
  assert.throws(()=>parseAccountingBankCSV(csv(['A;1010;2026-10-24;1;foo;bar']),
    context),/قالب/);
});

test('manual signed bank amounts refuse ambiguous commas and padded zeros',()=>{
  assert.equal(parseAccountingBankAmount('−10'.replace('−','-')),-10);
  assert.equal(parseAccountingBankAmount('۱٬۲۳۴'),1234);
  for(const raw of ['1,2','1,23','01','0001','-01','1 234','+1','1.000','-0'])
    assert.throws(()=>parseAccountingBankAmount(raw),undefined,raw);
});

test('exact aggregate avoids JavaScript Number overflow in 500-record preview',()=>{
  const lines=Array.from({length:20},(_,i)=>
    'S'+i+';1010;2026-10-24;1000000000000000;ref'+i);
  const rows=parseAccountingBankCSV(csv(lines),context);
  assert.equal(accountingBankNetExact(rows),20000000000000000n);
});
