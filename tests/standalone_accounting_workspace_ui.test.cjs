'use strict';
const {test}=require('node:test');
const {spawnSync}=require('node:child_process');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

const root=path.resolve(__dirname,'..');
const entry=path.join(root,'src','standalone_accounting_workspace.jsx');
const compiled=esbuild.buildSync({
  entryPoints:[entry],bundle:true,platform:'node',format:'cjs',write:false,
  external:['react','react/jsx-runtime','lucide-react'],
  loader:{'.css':'empty','.jpg':'dataurl'},
}).outputFiles[0].text;
const virtual=path.join(root,'tests','standalone-ui-virtual.cjs');
const moduleShim=new Module(virtual,module);
moduleShim.filename=virtual;moduleShim.paths=Module._nodeModulePaths(path.dirname(virtual));
moduleShim._compile(compiled,virtual);
const {
  StandaloneAccountingWorkspace,parseStandaloneToman,validStandaloneDate,
  buildStandaloneInvoiceCommand,buildStandaloneProformaCommand,
  buildStandaloneSettlementCommand,
  buildStandaloneManualCommand,outstandingStandaloneDocuments,
  validateStandaloneResponse,formatStandaloneMoney,
}=moduleShim.exports;

const accounts={
  '1000':{id:'1000',name:'Cash',kind:'asset',liquid:true},
  '1010':{id:'1010',name:'Bank',kind:'asset',liquid:true},
  '1200':{id:'1200',name:'Receivable',kind:'asset',liquid:false},
  '2000':{id:'2000',name:'Payable',kind:'liability',liquid:false},
  '4000':{id:'4000',name:'Sales',kind:'revenue',liquid:false},
  '5000':{id:'5000',name:'Expense',kind:'expense',liquid:false},
};
const doc={
  id:'sale-A',status:'issued',partyId:'customer-A',documentDate:'2026-10-01',
  postingDate:'2026-10-02',total:9000,allocated:2000,
};
const bill={...doc,id:'bill-A',partyId:'supplier-A',total:5000,allocated:500};
const eventId='evt.synthetic-1',today='2026-10-22';
const lines=[
  {description:'Design work',quantity:'3',unitPrice:'2,000',accountId:'4000'},
  {description:'Finishing',quantity:'1',unitPrice:'3,000',accountId:'4000'},
];
const makeInvoice=(diff={})=>buildStandaloneInvoiceCommand({
  kind:'invoice',documentId:'invoice-A',partyId:'customer-A',documentDate:'2026-10-02',
  discount:'500',tax:'100',lines,eventId,accounts,items:{},today,...diff,
});
const makeSettlement=(diff={})=>buildStandaloneSettlementCommand({
  kind:'receipt',document:doc,accountId:'1010',amount:'2,000',
  postingDate:'2026-10-05',eventId,accounts,today,...diff,
});

test('initial SSR uses full-screen independent RTL layout; no fake persisted data',()=>{
  const api={standaloneAccountingRead:async()=>({}),standaloneAccountingCommand:async()=>({})};
  const markup=renderToStaticMarkup(React.createElement(StandaloneAccountingWorkspace,{
    api,onExit(){},canManage:true,
  }));
  assert.match(markup,/sac-root/);
  assert.match(markup,/dir="rtl"/);
  assert.match(markup,/حسابداری مستقل مدار/);
  for(const name of ['داشبورد','مشخصات شرکت','پیش‌فاکتور مستقل','فاکتورهای فروش',
    'صورتحساب‌های خرید','اشخاص','خزانه و چک','کالا، انبار و کاردکس',
    'دریافت، پرداخت و اقساط','صندوق، بانک و مغایرت','حساب‌ها و دفترکل',
    'سند دستی و برگشت','حقوق و مالیات','سال مالی و بستن دوره'])
      assert.ok(markup.includes(name),name);
  assert.match(markup,/تمام مبالغ: ریال/);
  assert.match(markup,/دریافت داده دفترکل/);
  assert.doesNotMatch(markup,/فاکتور نمونه|تراکنش نمونه|مبلغ آزمایشی/);
  assert.doesNotMatch(markup,/projectId|taskId/);
});

test('read-only permission displays honest restriction and never shows write buttons',()=>{
  const markup=renderToStaticMarkup(React.createElement(StandaloneAccountingWorkspace,{
    api:{},canManage:false,onExit(){},
  }));
  assert.match(markup,/دسترسی مشاهده/);
  assert.doesNotMatch(markup,/ثبت پیش‌نویس|ثبت واریز|ثبت بستن دوره/);
});

test('finance draft-only role is visibly distinguished from read-only access',()=>{
  const markup=renderToStaticMarkup(React.createElement(StandaloneAccountingWorkspace,{
    api:{},canManage:false,canDraft:true,onExit(){},
  }));
  assert.match(markup,/دسترسی ثبت اولیه/);
  assert.match(markup,/تأیید، صدور و تغییر اسناد قطعی فقط با مدیر/);
  assert.doesNotMatch(markup,/دسترسی مشاهده: مجوز ثبت/);
});

test('TOMAN parser exact Persian and Arabic digits; rejects overflow and fractions',()=>{
  for(const [raw,expect] of [
    ['۱٬۲۳۴',1234],['١٢٣٤',1234],['1,000,000',1e6],['1000000000000000',1e15],
  ])assert.equal(parseStandaloneToman(raw),expect,raw);
  for(const raw of ['',null,undefined,true,'-1','1.1','1e2','01','۱٬۲۳','1,23,456',
    '1000000000000001','0','100 000',NaN])assert.equal(parseStandaloneToman(raw),null,String(raw));
  assert.equal(parseStandaloneToman('0',{allowZero:true}),0);
  assert.match(formatStandaloneMoney(12500),/تومان/);
});

test('date validation rejects invalid calendar, future and Persian dates',()=>{
  assert.equal(validStandaloneDate('2024-02-29',today),true);
  for(const value of ['2026-02-30','2026-10-23','1405-07-30','۱۴۰۵-۰۷-۳۰',
    '2026-10-2','2026/10/22','2026-00-11'])assert.equal(validStandaloneDate(value,today),false,value);
});

test('host revision contract is integer zero or positive, never string',()=>{
  const view={currency:'TOMAN',accounts:{},parties:{},items:{},
    invoices:{},bills:{},receipts:{},payments:{},journals:[],closedThrough:null};
  assert.deepEqual(validateStandaloneResponse({revision:0,view}),{revision:0,view});
  assert.deepEqual(validateStandaloneResponse({revision:17,view}).revision,17);
  for(const revision of ['0','17',-1,0.5,NaN,null,undefined]){
    assert.throws(()=>validateStandaloneResponse({revision,view}),/پاسخ میزبان/);
  }
  assert.deepEqual(validateStandaloneResponse({revision:1,view:{...view,currency:'RIAL'}}).view.currency,'RIAL');
  assert.throws(()=>validateStandaloneResponse({revision:1,view:{...view,journals:{}}}));
});

test('sale draft command equals accounting_core schema with explicit tax and discount',()=>{
  const actual=makeInvoice();
  assert.equal(actual.error,'');
  assert.equal(actual.total,8600);
  assert.deepEqual(actual.command,{
    type:'invoice.create',eventId,invoiceId:'invoice-A',partyId:'customer-A',
    documentDate:'2026-10-02',lines:[
      {description:'Design work',quantity:3,unitPrice:2000,accountId:'4000'},
      {description:'Finishing',quantity:1,unitPrice:3000,accountId:'4000'},
    ],discount:500,tax:100,
  });
  for(const forbidden of ['actor','company','projectId','proof','role','taskId']){
    assert.ok(!Object.hasOwn(actual.command,forbidden),forbidden);
  }
});

test('independent proforma builder is exact, task-free and rejects invalid expiration',()=>{
  const out=buildStandaloneProformaCommand({
    proformaId:'PF.1',partyId:'customer-A',documentDate:'2026-10-02',
    validUntil:'2026-11-01',lines,discount:'500',tax:'100',
    eventId,accounts,items:{},today,
  });
  assert.equal(out.error,'');
  assert.equal(out.total,8600);
  assert.equal(out.command.type,'proforma.create');
  assert.equal(out.command.proformaId,'PF.1');
  assert.equal(out.command.validUntil,'2026-11-01');
  for(const forbidden of ['invoiceId','taskId','projectId','cardId','actor',
    'companyId','proof','postingDate','sourceType']){
    assert.ok(!Object.hasOwn(out.command,forbidden),forbidden);
  }
  const edited=buildStandaloneProformaCommand({
    proformaId:'PF.1',partyId:'customer-A',documentDate:'2026-10-02',
    lines,discount:'500',tax:'100',eventId,accounts,items:{},today,update:true,
  });
  assert.equal(edited.command.type,'proforma.update');
  const invalid=buildStandaloneProformaCommand({
    proformaId:'PF.1',partyId:'customer-A',documentDate:'2026-10-02',
    validUntil:'2026-10-01',lines,eventId,accounts,items:{},today,
  });
  assert.match(invalid.error,/اعتبار/);
});

test('purchase uses bill.create expense account, not invoice or a task link',()=>{
  const out=makeInvoice({
    kind:'bill',documentId:'purchase-A',partyId:'supplier-A',discount:'0',tax:'0',
    lines:[{description:'Paper',quantity:'2',unitPrice:'500',accountId:'5000'}],
  });
  assert.equal(out.error,'');
  assert.deepEqual(out.command,{
    type:'bill.create',eventId,billId:'purchase-A',partyId:'supplier-A',
    documentDate:'2026-10-02',
    lines:[{description:'Paper',quantity:2,unitPrice:500,accountId:'5000'}],
    discount:0,tax:0,
  });
});

test('document builder fails closed on invalid lines, mismatched account kind and math',()=>{
  const rejects=[
    {lines:[]},{lines:[{...lines[0],quantity:'0'}]},
    {lines:[{...lines[0],quantity:'1000001'}]},
    {lines:[{...lines[0],unitPrice:'1.5'}]},
    {lines:[{...lines[0],unitPrice:'1000000000000000',quantity:'2'}]},
    {lines:[{...lines[0],accountId:'5000'}]},
    {discount:'10000'},{tax:'-1'},
    {lines:[{...lines[0],itemId:'not-registered'}]},
    {documentDate:'2026-10-23'}, {partyId:'a bad id'},
  ];
  for(const input of rejects)assert.ok(makeInvoice(input).error,JSON.stringify(input));
  const zero=makeInvoice({discount:'9000',tax:'0'});
  assert.ok(zero.error);
});

test('settlement targets exactly one issued document and positive outstanding balance',()=>{
  const out=makeSettlement();
  assert.equal(out.error,'');
  assert.deepEqual(out.command,{
    type:'receipt.record',eventId,receiptId:eventId,partyId:'customer-A',
    accountId:'1010',postingDate:'2026-10-05',
    allocations:[{invoiceId:'sale-A',amount:2000}],
  });
  const payment=makeSettlement({kind:'payment',document:bill,amount:'4500'});
  assert.equal(payment.error,'');
  assert.deepEqual(payment.command.allocations,[{billId:'bill-A',amount:4500}]);
  assert.equal(payment.command.type,'payment.record');
  for(const changes of [
    {amount:'7001'},{amount:'0'},{amount:'1.5'},{accountId:'1200'},
    {postingDate:'2026-10-01'},{document:{...doc,status:'draft'}},
    {document:{...doc,allocated:doc.total}},
    {document:{...doc,allocated:doc.total+1}},
  ])assert.ok(makeSettlement(changes).error,JSON.stringify(changes));
});

test('outstanding filtering excludes draft, paid, wrong party and wrong subtype',()=>{
  const view={invoices:{a:doc,b:{...doc,id:'draft',status:'draft'},
    c:{...doc,id:'paid',allocated:doc.total}},bills:{d:bill}};
  assert.deepEqual(outstandingStandaloneDocuments(view,'receipt').map(d=>d.id),['sale-A']);
  assert.deepEqual(outstandingStandaloneDocuments(view,'payment','supplier-A').map(d=>d.id),['bill-A']);
  assert.deepEqual(outstandingStandaloneDocuments(view,'payment','customer-A'),[]);
});

test('partial return reduces every receipt/payment capacity without altering original total',()=>{
  const partlyReturned={...doc,returnedAmount:3500};
  assert.equal(partlyReturned.total,9000);
  const eligible=outstandingStandaloneDocuments({invoices:{a:partlyReturned}},'receipt');
  assert.equal(eligible.length,1);
  assert.equal(makeSettlement({document:partlyReturned,amount:'3,500'}).error,'');
  assert.ok(makeSettlement({document:partlyReturned,amount:'3,501'}).error);
  const fullySatisfied={...partlyReturned,returnedAmount:7000};
  assert.deepEqual(outstandingStandaloneDocuments({invoices:{a:fullySatisfied}},'receipt'),[]);
  assert.ok(makeSettlement({document:fullySatisfied,amount:'1'}).error);
  const partlyReturnedPurchase={...bill,returnedAmount:2500};
  assert.equal(makeSettlement({kind:'payment',document:partlyReturnedPurchase,
    amount:'2,000'}).error,'');
  assert.ok(makeSettlement({kind:'payment',document:partlyReturnedPurchase,
    amount:'2,001'}).error);
});

test('manual journal is exact, balanced, and never bypasses AR/AP',()=>{
  const args={
    lines:[{accountId:'1000',debit:'100',credit:'0'},
      {accountId:'4000',debit:'0',credit:'100'}],
    note:'Independent adjustment',postingDate:'2026-10-05',eventId,accounts,today,
  };
  const out=buildStandaloneManualCommand(args);
  assert.equal(out.error,'');
  assert.deepEqual(out.command,{type:'journal.manual',eventId,postingDate:'2026-10-05',
    note:'Independent adjustment',lines:[
      {accountId:'1000',debit:100,credit:0},
      {accountId:'4000',debit:0,credit:100},
    ]});
  for(const changes of [
    {lines:[args.lines[0]]},
    {lines:[args.lines[0],{...args.lines[1],credit:'101'}]},
    {lines:[{...args.lines[0],accountId:'1200'},args.lines[1]]},
    {lines:[{...args.lines[0],debit:'0'},args.lines[1]]},
    {lines:[{...args.lines[0],credit:'20'},args.lines[1]]},
    {postingDate:'2026-10-23'}, {note:''},
  ])assert.ok(buildStandaloneManualCommand({...args,...changes}).error,JSON.stringify(changes));
});

test('component routes only through dedicated standalone host API and carries integer CAS',()=>{
  const source=fs.readFileSync(entry,'utf8');
  assert.match(source,/api\.standaloneAccountingRead\(\)/);
  assert.match(source,/api\.standaloneAccountingCommand\(\{/);
  assert.match(source,/command,expectedRevision:latest\.current\.revision/);
  assert.match(source,/validateStandaloneResponse\(payload\)/);
  assert.match(source,/crypto\?\.randomUUID\?\.\(\)/);
  assert.match(source,/isConflict/);
  assert.match(source,/canManage/);
  assert.doesNotMatch(source,/api\.(?:accountingRead|accountingCommand|financeCommand)\(/);
  assert.doesNotMatch(source,/sourceType:'task'|projectId:|taskId:|actorId:|companyId:/);
});

test('synthetic command lifecycle replays in the real accounting_core without touching disk',()=>{
  const invoice={...makeInvoice().command,eventId:'evt.invoice'};
  const purchase={...makeInvoice({kind:'bill',documentId:'bill-A',partyId:'supplier-A',
    discount:'0',tax:'0',lines:[{description:'Materials',quantity:'2',
      unitPrice:'2500',accountId:'5000'}]}).command,eventId:'evt.purchase'};
  const receipt={...makeSettlement().command,eventId:'evt.receipt',receiptId:'evt.receipt'};
  const payment={...makeSettlement({kind:'payment',document:bill,
    amount:'4500'}).command,eventId:'evt.payment',paymentId:'evt.payment'};
  const manual=buildStandaloneManualCommand({
    eventId:'evt.manual',postingDate:'2026-10-09',note:'Example adjustment',
    lines:[{accountId:'1000',debit:'15',credit:'0'},
      {accountId:'4000',debit:'0',credit:'15'}],accounts,today,
  }).command;
  const commands=[
    {type:'party.register',eventId:'evt.party1',partyId:'customer-A',
      name:'Customer Sample',kind:'customer'},
    {type:'party.register',eventId:'evt.party2',partyId:'supplier-A',
      name:'Vendor Sample',kind:'vendor'},
    {type:'item.create',eventId:'evt.item',itemId:'service-A',
      sku:'S-01',name:'Design',kind:'service',unit:'session'},
    invoice,
    {type:'invoice.approve',eventId:'evt.approve',invoiceId:'invoice-A'},
    {type:'invoice.issue',eventId:'evt.issue',invoiceId:'invoice-A',postingDate:'2026-10-02'},
    {type:'funds.deposit',eventId:'evt.deposit',accountId:'1010',amount:10000,
      note:'Owner contribution',postingDate:'2026-10-02'},
    {...receipt,allocations:[{invoiceId:'invoice-A',amount:2000}]},
    purchase,
    {type:'bill.approve',eventId:'evt.billApprove',billId:'bill-A'},
    {type:'bill.issue',eventId:'evt.billIssue',billId:'bill-A',postingDate:'2026-10-02'},
    {...payment,allocations:[{billId:'bill-A',amount:4500}]},
    manual,
    {type:'journal.reverse',eventId:'evt.reverse',journalId:'J:evt.manual',
      postingDate:'2026-10-10',reason:'Example correction'},
    {type:'period.close',eventId:'evt.close',throughDate:'2026-10-11'},
  ];
  const py=[
    'import sys,json',
    'from accounting_core import empty_accounting_state, apply_accounting_command, accounting_view, validate_accounting_state',
    'commands=json.load(sys.stdin)',
    'state=empty_accounting_state()',
    'for command in commands:',
    "    state=apply_accounting_command(state,command,actor='root',accounts=[{'username':'root','role':'admin'}],now='2026-10-22T16:00:00+03:30')['state']",
    "view=accounting_view(state,actor='root',accounts=[{'username':'root','role':'admin'}])",
    "assert validate_accounting_state(state)",
    "assert view['invoices']['invoice-A']['total']==8600",
    "assert view['invoices']['invoice-A']['allocated']==2000",
    "assert view['bills']['bill-A']['allocated']==4500",
    "assert view['parties']['customer-A']['receivable']==6600",
    "assert view['parties']['supplier-A']['payable']==500",
    "assert view['closedThrough']=='2026-10-11'",
    "assert view['reversed']['J:evt.manual']=='J:evt.reverse'",
    "print('synthetic accounting_core lifecycle PASS; %d journal entries'%len(view['journals']))",
  ].join('\n');
  const res=spawnSync('python',['-B','-c',py],{
    cwd:root,input:JSON.stringify(commands),encoding:'utf8',timeout:12000,
  });
  assert.equal(res.status,0,JSON.stringify({stdout:res.stdout,stderr:res.stderr,error:res.error?.message}));
  assert.match(res.stdout,/lifecycle PASS/);
});
