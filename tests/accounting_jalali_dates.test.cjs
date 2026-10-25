'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const entry=path.resolve(__dirname,'../src/accounting_jalali_dates.js');
const compiled=esbuild.buildSync({entryPoints:[entry],bundle:true,
  platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const synthetic=path.resolve(__dirname,'accounting-jalali-virtual.cjs');
const m=new Module(synthetic,module);m.filename=synthetic;
m.paths=Module._nodeModulePaths(__dirname);m._compile(compiled,synthetic);
const {formatAccountingJalali,parseAccountingJalali,displayAccountingDate}=m.exports;

test('Persian 1405 date and bidirectional conversion',()=>{
  assert.equal(formatAccountingJalali('2026-10-24'),'۱۴۰۵/۰۸/۰۲');
  assert.equal(parseAccountingJalali('۱۴۰۵/۰۸/۰۲'),'2026-10-24');
  assert.equal(parseAccountingJalali('1405/08/02'),'2026-10-24');
  assert.equal(parseAccountingJalali('١٤٠٥/٠٨/٠٢'),'2026-10-24');
  assert.equal(formatAccountingJalali('2026-10-24',{digits:'ascii'}),'1405/08/02');
  assert.equal(displayAccountingDate('2026-10-24'),'۱۴۰۵/۰۸/۰۲');
});
test('Nowruz and leap Esfand do not shift days or silently round',()=>{
  for(const [iso,solar] of [
    ['2026-03-21','۱۴۰۵/۰۱/۰۱'],
    ['2025-03-20','۱۴۰۳/۱۲/۳۰'],
    ['2024-03-20','۱۴۰۳/۰۱/۰۱'],
    ['2024-03-19','۱۴۰۲/۱۲/۲۹'],
    ['2021-03-20','۱۳۹۹/۱۲/۳۰'],
  ]){
    assert.equal(formatAccountingJalali(iso),solar,iso);
    assert.equal(parseAccountingJalali(solar),iso,solar);
  }
  for(const impossible of ['۱۴۰۴/۱۲/۳۰','۱۴۰۵/۱۳/۰۱','۱۴۰۵/۰۸/۳۲',
    '۱۴۰۵/۰۲/۳۲','۱۴۰۵-۰۸-۰۰','2026-10-24']){
    assert.equal(parseAccountingJalali(impossible),null,impossible);
  }
});
test('365-day exhaustiveness near Jalali/Gregorian year boundary',()=>{
  const start=Date.UTC(2025,2,1);
  for(let i=0;i<400;i++){
    const iso=new Date(start+i*86400000).toISOString().slice(0,10);
    const solar=formatAccountingJalali(iso);
    assert.equal(parseAccountingJalali(solar),iso,iso);
  }
});
