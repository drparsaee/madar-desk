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
const text=fs.readFileSync(path.join(root,'src','accounting_panel.jsx'),'utf8');
const transformed=esbuild.buildSync({entryPoints:[path.join(root,'src','accounting_panel.jsx')],
  bundle:true,platform:'node',format:'cjs',write:false,
  external:['react','react/jsx-runtime','lucide-react'],loader:{'.css':'empty'}}).outputFiles[0].text;
const modulePath=path.join(root,'tests','accounting-ssr-bundle.cjs');
const loader=new Module(modulePath,module);
loader.filename=modulePath;
loader.paths=Module._nodeModulePaths(path.dirname(modulePath));
loader._compile(transformed,modulePath);
const {AccountingPanel}=loader.exports;

function render(props={}){
  const api={accountingRead:async()=>({documents:[],balances:[]}),accountingCommand:async()=>({})};
  return renderToStaticMarkup(React.createElement(AccountingPanel,{
    api,canManage:true,projects:[{id:'p1',name:'کارگاه'}],
    tasks:[{id:'t1',projectId:'p1',title:'چاپ جعبه',cost:700000,
      checklist:[{id:'c1',text:'چاپ',cost:250000}]}],...props}));
}

test('finance viewer cannot render protected accounting data or action form',()=>{
  const markup=render({canManage:false});
  assert.match(markup,/فقط برای مدیر/);
  assert.doesNotMatch(markup,/طرف‌حساب‌ها/);
  assert.doesNotMatch(markup,/درآمد|ثبت پیش‌نویس/);
});
test('Admin sees explicit task-to-named-person sales invoice fields',()=>{
  const markup=render();
  for(const label of ['فروش به شخص','نام شخص','تسک','قیمت واحد','تخفیف','مالیات، مبلغ صریح','پیش‌دریافت اعلامی'])
    assert.ok(markup.includes(label),'missing '+label);
  assert.match(markup,/چاپ جعبه/);
  assert.match(markup,/ثبت پیش‌نویس بدون صدور قطعی/);
});
test('UI prohibits hidden direct issue of drafts',()=>{
  const markup=render();
  assert.doesNotMatch(markup,/نام رسمی مالیاتی|تأییدشده توسط دولت/);
  assert.match(markup,/صدور و ثبت وجه نیاز به تأیید جداگانه/);
  assert.match(text,/d\.status==='Draft'/);
  assert.match(text,/d\.status==='Review'/);
  assert.match(text,/window\.confirm\(/);
});
test('purchase selection requires explicit supplier and basis and confirmation',()=>{
  const source=fs.readFileSync(path.join(root,'src','accounting_panel.jsx'),'utf8');
  for(const marker of ['خرید از تأمین‌کننده','نام تأمین‌کننده','actual','estimated','approveEstimate','هزینه انتخابی','تأیید صریح لازم است'])
    assert.ok(source.includes(marker),'missing '+marker);
});
test('component sends only asserted cost source IDs and no guessed paid flags',()=>{
  assert.match(text,/selections:\[\{cardId:selected\.id,sourceId\}\]/);
  assert.match(text,/type:'draft\.purchase\.fromCosts'/);
  assert.match(text,/type:'draft\.sales\.fromTask'/);
  assert.doesNotMatch(text,/paid:true|isPaid:true|forcePay:true/);
});
test('retry preserves original event id when payload unchanged',()=>{
  assert.match(text,/if\(pending\.current\?\.identity!==identity\)pending\.current=/);
  assert.match(text,/const id=pending\.current\.eventId/);
  assert.match(text,/\.\.\.recordId,eventId:id/);
  assert.match(text,/pending\.current=null/);
});
test('unrelated project tasks are not available in sales selection',()=>{
  const markup=render({tasks:[
    {id:'t1',projectId:'p1',title:'چاپ',cost:1,checklist:[]},
    {id:'secret',projectId:'p2',title:'PRIVATE_CARD_SHOULD_NOT_DISPLAY',cost:10,checklist:[]},
  ]});
  assert.match(markup,/چاپ/);
  assert.doesNotMatch(markup,/PRIVATE_CARD_SHOULD_NOT_DISPLAY/);
});
test('response balance labels distinguish receivable from payable',()=>{
  const markup=render();
  assert.match(text,/طلب از مشتری/);
  assert.match(text,/بدهی به تأمین‌کننده/);
  assert.match(markup,/حسابداری مدار/);
});
