'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

const root=path.resolve(__dirname,'..');
const source=path.join(root,'src/rial_journal_panel.jsx');
const compiled=esbuild.buildSync({entryPoints:[source],bundle:true,
  platform:'node',format:'cjs',write:false,external:['react','react/jsx-runtime'],
  loader:{'.css':'empty'}}).outputFiles[0].text;
const virtual=path.join(root,'tests','rial-journal-ui-virtual.cjs');
const loaded=new Module(virtual,module);
loaded.filename=virtual;loaded.paths=Module._nodeModulePaths(path.dirname(virtual));
loaded._compile(compiled,virtual);
const {
  RialJournalPanel,formatExactRial,parseCanonicalRial,validateRialLines,
  validateRialJournalSnapshot,validateRialInvoicePreview,RIAL_V2_SCHEMA,
}=loaded.exports;

const scope={companyId:'company-1',fiscalPeriodId:'FY26'};
const lines=[
  {accountCode:'1010',debitRial:'101',creditRial:'0',costCenterCode:'CTR-01'},
  {accountCode:'4010',debitRial:'0',creditRial:'101'},
];
const journal={eventId:'evt-001',companyId:'company-1',fiscalPeriodId:'FY26',
  postingDate:'2026-10-21',source:{kind:'task',sourceId:'task-001'},lines};
const snap=()=>({schema:RIAL_V2_SCHEMA,currency:'RIAL',...scope,
  revision:'a'.repeat(64),journals:[journal]});
const invoice={invoiceId:'INV-001',invoiceKind:'sales'};
const preview=()=>({schema:RIAL_V2_SCHEMA,currency:'RIAL',...scope,
  ...invoice,previewOnly:true,postingDate:'2026-10-21',totalRial:'101',lines});
const render=props=>renderToStaticMarkup(React.createElement(RialJournalPanel,props));

test('one RIAL and maximum safe integer render exactly without division by ten',()=>{
  assert.equal(formatExactRial('1'),'۱ ریال');
  assert.equal(formatExactRial('11'),'۱۱ ریال');
  assert.equal(formatExactRial('9007199254740991'),'۹,۰۰۷,۱۹۹,۲۵۴,۷۴۰,۹۹۱ ریال');
  assert.equal(formatExactRial('0'),'۰ ریال');
  assert.equal(parseCanonicalRial('101'),101n);
});

test('unsafe JS numbers and noncanonical inputs must never be displayed as valid RIAL',()=>{
  for(const bad of [101,101n,-1,'-1','1.0','1e3','01','۱۰۰','1,000','1 ',
    '9007199254740992','9999999999999999999999999999999',{},null,'']){
    assert.equal(parseCanonicalRial(bad),null,String(bad));
    assert.equal(formatExactRial(bad),'مبلغ ریالی نامعتبر',String(bad));
  }
});

test('balanced posting validation accepts 1 RIAL exactly and rejects invalid lines',()=>{
  assert.deepEqual(validateRialLines([
    {accountCode:'1010',debitRial:'1',creditRial:'0'},
    {accountCode:'4010',debitRial:'0',creditRial:'1'},
  ]),{error:'',totalRial:'1'});
  assert.equal(validateRialLines(lines).totalRial,'101');
  for(const bad of [
    [],
    [lines[0]],
    Array.from({length:101},()=>lines[0]),
    [lines[0],{accountCode:'4010',debitRial:'0',creditRial:'100'}],
    [lines[0],{accountCode:'4010',debitRial:'1',creditRial:'101'}],
    [lines[0],{accountCode:'4010',debitRial:'0',creditRial:'101.5'}],
    [lines[0],{accountCode:4010,debitRial:'0',creditRial:'101'}],
    [lines[0],{accountCode:'4010',debitRial:'0',creditRial:'101',costCenterCode:{}}],
    [{accountCode:'1010',debitRial:'9007199254740991',creditRial:'0'},
      {accountCode:'1011',debitRial:'1',creditRial:'0'},lines[1]],
  ])assert.ok(validateRialLines(bad).error);
});

test('snapshot only accepts explicit V2 RIAL version, company, period and digest',()=>{
  const valid=validateRialJournalSnapshot(snap(),scope);
  assert.equal(valid.error,'');
  assert.equal(valid.journals[0].eventId,'evt-001');
  for(const patch of [
    {schema:'legacy-v1'},{currency:'TOMAN'},
    {companyId:'other-company'},{fiscalPeriodId:'FY25'},
    {revision:'invalid'},{journals:null},
    {journals:[journal,journal]},
    {journals:[{...journal,companyId:'other-company'}]},
    {journals:[{...journal,source:{kind:'external',sourceId:'task-001'}}]},
    {journals:[{...journal,source:{kind:'task',sourceId:123}}]},
    {journals:[{...journal,reversalOf:'bad reversal id'}]},
    {journals:[{...journal,postingDate:'2026-02-30'}]},
    {journals:[{...journal,lines:[lines[0],{...lines[1],creditRial:'102'}]}]},
    {journals:[{...journal,lines:[lines[0],{...lines[1],creditRial:101}]}]},
  ])assert.ok(validateRialJournalSnapshot({...snap(),...patch},scope).error,
    JSON.stringify(patch).slice(0,200));
  assert.equal(validateRialJournalSnapshot({...snap(),journals:[]},scope).error,'');
  assert.match(validateRialJournalSnapshot({...snap(),journals:Array(501).fill(journal)},scope).error,/۵۰۰/);
});

test('issuance preview requires explicit dry-run proof, identity and balanced lines',()=>{
  const checked=validateRialInvoicePreview(preview(),scope,invoice);
  assert.equal(checked.error,'');
  assert.equal(checked.preview.totalRial,'101');
  for(const patch of [
    {previewOnly:false},{previewOnly:undefined},{schema:'legacy'},
    {currency:'TOMAN'},{companyId:'company-2'},{fiscalPeriodId:'FY25'},
    {invoiceId:'INV-002'},{invoiceKind:'purchase'},{totalRial:'0'},
    {totalRial:101},{postingDate:'2026-02-30'},
    {lines:[lines[0],{...lines[1],creditRial:'100'}]},
  ])assert.ok(validateRialInvoicePreview({...preview(),...patch},scope,invoice).error,
    JSON.stringify(patch));
  assert.ok(validateRialInvoicePreview(preview(),scope,{...invoice,invoiceKind:'unknown'}).error);
});

test('unprivileged users cannot access journal or preview controls',()=>{
  const html=render({...scope,canView:false,canPreview:true});
  assert.match(html,/مجوز مشاهده دفتر روزنامه ریالی/);
  assert.doesNotMatch(html,/rjv-form|اسناد ثبت‌شده|endpoint/);
});

test('missing V2 endpoints display hard warning and disable preview',()=>{
  const html=render({...scope,canView:true,canPreview:true,api:{}});
  assert.match(html,/role="alert"/);
  assert.match(html,/اتصال کامل و معتبر/);
  assert.match(html,/خواندن دفترکل V2 موجود نیست/);
  assert.match(html,/پیش‌نمایش صدور V2 موجود نیست/);
  assert.match(html,/داده‌های تومانی قدیمی نباید/);
  assert.match(html,/disabled=""/);
  assert.doesNotMatch(html,/صدور قطعی|ثبت فاکتور/);
});

test('a healthy V2 function pair still awaits a validated snapshot before preview',()=>{
  const api={rialJournalRead:async()=>snap(),rialInvoiceIssuePreview:async()=>preview()};
  const html=render({...scope,canView:true,canPreview:true,api});
  assert.match(html,/IR-JOURNAL-V2.1/);
  assert.match(html,/RIAL · ریال/);
  assert.match(html,/فقط محاسبه پیش‌نمایش/);
  assert.match(html,/disabled=""/);
  assert.match(html,/هیچ فاکتوری صادر یا ثبت نمی‌کند/);
  assert.doesNotMatch(html,/اتصال کامل و معتبر/);
});

test('preview permissions and missing company identity are fail-closed',()=>{
  const api={rialJournalRead:()=>Promise.resolve(snap()),
    rialInvoiceIssuePreview:()=>Promise.resolve(preview())};
  const noGrant=render({...scope,canView:true,canPreview:false,api});
  assert.match(noGrant,/مجوز دریافت پیش‌نمایش/);
  const badIdentity=render({companyId:'',fiscalPeriodId:'FY26',canView:true,canPreview:true,api});
  assert.match(badIdentity,/شناسه معتبر شرکت و دوره مالی/);
  assert.match(badIdentity,/disabled=""/);
});

test('component references only RIAL V2 endpoints and CSS supports keyboard/RTL',()=>{
  const code=fs.readFileSync(source,'utf8');
  assert.match(code,/api\.rialJournalRead\(\{companyId,fiscalPeriodId\}\)/);
  assert.match(code,/api\.rialInvoiceIssuePreview\(\{/);
  assert.match(code,/previewOnly:true/);
  assert.doesNotMatch(code,/api\.accountingCommand\(|formatLegacyMoney\(|parseMoneyInput\(|\.issue\(/);
  const css=fs.readFileSync(path.join(root,'src/rial_journal_panel.css'),'utf8');
  assert.match(css,/direction:rtl/);
  assert.match(css,/:focus-visible/);
  assert.match(css,/overflow-x:auto/);
  assert.match(css,/@media\(max-width:860px\)/);
});
