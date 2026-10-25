'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
const code=esbuild.buildSync({entryPoints:[path.join(root,'src/ir_money_display.js')],
  platform:'node',format:'cjs',bundle:true,write:false}).outputFiles[0].text;
const virtual=path.join(root,'tests','ir-money-virtual.cjs');
const loaded=new Module(virtual,module);
loaded.filename=virtual;
loaded.paths=Module._nodeModulePaths(path.dirname(virtual));
loaded._compile(code,virtual);
const {MAX_LEGACY_TOMAN,MONEY_UNITS,parseMoneyInput,formatLegacyMoney,
  formatLegacyEntry,convertTypedMoney}=loaded.exports;

test('existing legacy TOMAN values render exact Persian grouped numbers in either unit',()=>{
  assert.equal(formatLegacyMoney(1234567),'۱,۲۳۴,۵۶۷ تومان');
  assert.equal(formatLegacyMoney(1234567,'RIAL'),'۱۲,۳۴۵,۶۷۰ ریال');
  assert.equal(formatLegacyMoney(-1234,'RIAL'),'−۱۲,۳۴۰ ریال');
  assert.equal(formatLegacyMoney(0,'TOMAN'),'۰ تومان');
  assert.equal(formatLegacyMoney(MAX_LEGACY_TOMAN,'RIAL'),'۱۰,۰۰۰,۰۰۰,۰۰۰,۰۰۰,۰۰۰ ریال');
  assert.equal(formatLegacyMoney(12.5,'RIAL'),'ثبت نشده');
  assert.equal(formatLegacyMoney(Number.MAX_SAFE_INTEGER+1),'ثبت نشده');
  assert.equal(formatLegacyMoney('123'),'ثبت نشده');
  assert.equal(formatLegacyMoney(undefined,'RIAL',{fallback:'نامشخص'}),'نامشخص');
  assert.equal(MONEY_UNITS.RIAL,'ریال');
});

test('RIAL entry converts only an exact multiple of ten, preserving existing engine units',()=>{
  assert.deepEqual(parseMoneyInput('۱۵۰','RIAL'),{amount:15,error:''});
  assert.deepEqual(parseMoneyInput('١٠٬٠٠٠','RIAL'),{amount:1000,error:''});
  assert.deepEqual(parseMoneyInput('۱۰,۰۰۰','RIAL'),{amount:1000,error:''});
  assert.deepEqual(parseMoneyInput('۱۵','TOMAN'),{amount:15,error:''});
  assert.match(parseMoneyInput('۱۵','RIAL').error,/مضرب ۱۰/);
  assert.equal(parseMoneyInput('۱۵','RIAL').amount,null);
  assert.match(parseMoneyInput('۱','RIAL').error,/مضرب ۱۰/);
  assert.deepEqual(parseMoneyInput('0','RIAL',{allowZero:true}),{amount:0,error:''});
});

test('parsing rejects fraction, ambiguous grouping, negative, exponent and malformed digits',()=>{
  for(const input of ['',null,undefined,1.1,'01','۱٬۲۳۴٬۵۶','1,2,3','1.5',
    '۰٫۵','۰.۵','1e3','+10','-10','1 000','100,00','۰۰۱۰','1/10']){
    assert.notEqual(parseMoneyInput(input,'RIAL').error,'',String(input));
  }
  assert.ok(parseMoneyInput('10','FAKE').error);
});

test('engine TOMAN bound is enforced with BigInt without unsafe Number coercion',()=>{
  const maximum=MAX_LEGACY_TOMAN.toString();
  assert.equal(parseMoneyInput(maximum,'TOMAN').amount,Number(maximum));
  assert.equal(parseMoneyInput((MAX_LEGACY_TOMAN*10n).toString(),'RIAL').amount,Number(maximum));
  for(const [text,unit] of [[(MAX_LEGACY_TOMAN+1n).toString(),'TOMAN'],
    [((MAX_LEGACY_TOMAN+1n)*10n).toString(),'RIAL'],
    ['9999999999999999999999999999999999999999990','RIAL']]){
    const outcome=parseMoneyInput(text,unit);
    assert.equal(outcome.amount,null); assert.match(outcome.error,/سقف/);
  }
});

test('unit change converts typed values exactly, clears invalid input, preserves zero',()=>{
  assert.deepEqual(convertTypedMoney('1,250','TOMAN','RIAL'),{value:'12500',cleared:false});
  assert.deepEqual(convertTypedMoney('۱۲٬۵۰۰','RIAL','TOMAN'),{value:'1250',cleared:false});
  assert.deepEqual(convertTypedMoney('۱۵','RIAL','TOMAN'),{value:'',cleared:true});
  assert.deepEqual(convertTypedMoney('۱,۲','TOMAN','RIAL'),{value:'',cleared:true});
  assert.deepEqual(convertTypedMoney('0','TOMAN','RIAL'),{value:'0',cleared:false});
  assert.deepEqual(convertTypedMoney('','RIAL','TOMAN'),{value:'',cleared:false});
  assert.deepEqual(convertTypedMoney('10','RIAL','RIAL'),{value:'10',cleared:false});
  assert.equal(formatLegacyEntry(2000,'RIAL'),'20000');
  assert.equal(formatLegacyEntry(2000,'TOMAN'),'2000');
  assert.equal(formatLegacyEntry(undefined,'RIAL'),'');
});
