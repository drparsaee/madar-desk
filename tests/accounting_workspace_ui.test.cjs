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
const source=path.join(root,'src/accounting_workspace.jsx');
const compiled=esbuild.buildSync({entryPoints:[source],bundle:true,
  platform:'node',format:'cjs',write:false,external:['react','react/jsx-runtime','lucide-react'],
  loader:{'.css':'empty'}}).outputFiles[0].text;
const virtual=path.join(root,'tests','accounting-workspace-ui-virtual.cjs');
const loaded=new Module(virtual,module);
loaded.filename=virtual;loaded.paths=Module._nodeModulePaths(path.dirname(virtual));
loaded._compile(compiled,virtual);
const {AccountingWorkspace,parseWholeToman,validAccountingDate,
  outstandingAccountingDocuments,buildSettlementCommand,
  buildItemCreateCommand,buildStandaloneDocumentCommand}=loaded.exports;
const props={api:{accountingRead:async()=>({}),accountingCommand:async()=>({})},
  canManage:true,projects:[{id:'p1',name:'پروژه آزمایشی'}],
  tasks:[{id:'t1',projectId:'p1',title:'جعبه سفارشی',saleQuantity:3,
    saleUnitPrice:8000,checklist:[{id:'step1',text:'برش قالب',done:false}]}],onExit(){}};
const render=overrides=>renderToStaticMarkup(React.createElement(AccountingWorkspace,{...props,...overrides}));
const app=fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');

test('accounting occupies full-screen route, not an old modal overlay',()=>{
  const html=render();
  assert.match(html,/accw-root/);
  assert.match(html,/حسابداری مدار/);
  assert.match(html,/بازگشت به تسک‌منیجر/);
  assert.match(app,/if\(accountingOpen&&canManage\)return <AccountingWorkspace/);
  assert.doesNotMatch(app,/accountingOpen&&<AccountingPanel/);
});
test('independent accountant navigation includes eight specific working domains',()=>{
  const html=render();
  for(const value of ['داشبورد','فروش و فاکتورها','خرید و خدمات دریافتی',
    'اشخاص و طرف‌حساب‌ها','حساب‌ها و دفترکل','دریافت و پرداخت','گزارش‌ها',
    'مهاجرت و پشتیبان'])assert.ok(html.includes(value),value);
  assert.match(html,/role="status"/);
  assert.match(html,/dir="rtl"/);
});
test('sale deep-link contains task title, quantity and unit price',()=>{
  const html=render({initialSource:{kind:'sales',projectId:'p1',cardId:'t1',
    quantity:3,unitPrice:8000}});
  assert.match(html,/جعبه سفارشی/);
  assert.match(html,/value="3"/);
  assert.match(html,/value="8000"/);
  assert.match(html,/ساخت پیش‌نویس فروش/);
});
test('supplier intake deep-link only captures stage/quantity/supplier not price',()=>{
  const html=render({initialSource:{kind:'purchase',projectId:'p1',
    cardId:'t1',stepId:'step1',quantity:1}});
  assert.match(html,/برش قالب/);
  assert.match(html,/ثبت کار برای قیمت‌گذاری/);
  assert.match(html,/قیمت و سند پرداختنی بعداً تعیین می‌شود/);
});
test('no financial tools are rendered for role without manage grant',()=>{
  const html=render({canManage:false});
  assert.match(html,/مجوز دسترسی/);
  assert.doesNotMatch(html,/ساخت پیش‌نویس فروش|ثبت کار برای قیمت‌گذاری|فاکتورهای خرید/);
});
test('new task actions use trusted standalone host while retaining legacy accounting as optional historical route',()=>{
  assert.match(app,/onOpenPurchase=\{\(task,expense\)=>prepareIndependentAccounting\(task,expense\)\}/);
  assert.match(app,/onOpenSale=\{task=>prepareIndependentAccounting\(task\)\}/);
  assert.match(app,/if\(dirty.current\|\|saving.current\|\|blocked.current\)/);
  assert.match(app,/prepareStandaloneFromTask\(api/);
  assert.doesNotMatch(app,/onOpenSale=\{task=>openAccounting/);
  assert.doesNotMatch(app,/onOpenPurchase=\{\(task,step\)=>openAccounting/);
});

test('strict amount parser rejects malformed amounts, fractional tomans and overflow',()=>{
  for(const [value,expected] of [['۱٬۲۳۴',1234],['١٢٣٤',1234],['1,234,567',1234567],
    ['1000000000000000',1e15]])assert.equal(parseWholeToman(value),expected,value);
  for(const value of ['',null,undefined,true,NaN,'0','-1','1.5','1e4','01','۱٬۲۳',
    '1,23,456','1,2','1 000','1000000000000001'])assert.equal(parseWholeToman(value),null,String(value));
  assert.equal(parseWholeToman('0',{allowZero:true}),0);
});

test('accounting posting dates are strict calendar dates and not in the future',()=>{
  assert.equal(validAccountingDate('2024-02-29','2026-10-21'),true);
  for(const date of ['2025-02-29','2026-10-22','2026-2-01','2026/10/21','2026-13-01',
    '2026-10-00',''])assert.equal(validAccountingDate(date,'2026-10-21'),false,date);
});

const saleDoc={id:'S-001',projectId:'p1',kind:'sales',status:'Issued',
  party:{id:'person-1',name:'مشتری'},postingDate:'2026-10-10',
  total:1000,allocated:250,number:'101'};
const purchaseDoc={...saleDoc,id:'B-001',kind:'purchase',party:{id:'vendor-1',name:'تأمین‌کننده'},
  total:2200,allocated:200};

test('receipt and payment targets are segregated, issued, same-project and outstanding',()=>{
  const documents=[saleDoc,purchaseDoc,{...saleDoc,id:'S-002',status:'Draft'},
    {...purchaseDoc,id:'B-002',allocated:2200},{...saleDoc,id:'S-003',projectId:'p2'},
    {...saleDoc,id:'S-004',party:null},{...saleDoc,id:'S-005',allocated:'0'}];
  assert.deepEqual(outstandingAccountingDocuments(documents,'receipt','p1').map(d=>d.id),['S-001']);
  assert.deepEqual(outstandingAccountingDocuments(documents,'payment','p1').map(d=>d.id),['B-001']);
  assert.deepEqual(outstandingAccountingDocuments(documents,'payment','p2'),[]);
  assert.deepEqual(outstandingAccountingDocuments(documents,'unknown','p1'),[]);
});

test('receipt command uses exactly real host receipt.record and invoice allocation fields',()=>{
  const result=buildSettlementCommand({kind:'receipt',document:saleDoc,amount:'۷۵۰',
    accountId:'1010',postingDate:'2026-10-21',eventId:'event-receipt-1',today:'2026-10-21'});
  assert.equal(result.error,'');
  assert.deepEqual(result.command,{type:'receipt.record',eventId:'event-receipt-1',
    receiptId:'event-receipt-1',partyId:'person-1',accountId:'1010',
    postingDate:'2026-10-21',allocations:[{invoiceId:'S-001',amount:750}]});
});

test('payment command uses exact payment.record and bill allocation without guessed paid flags',()=>{
  const result=buildSettlementCommand({kind:'payment',document:purchaseDoc,
    amount:'۲٬۰۰۰',accountId:'1000',postingDate:'2026-10-19',
    eventId:'event-payment-1',today:'2026-10-21'});
  assert.equal(result.error,'');
  assert.deepEqual(result.command,{type:'payment.record',eventId:'event-payment-1',
    paymentId:'event-payment-1',partyId:'vendor-1',accountId:'1000',
    postingDate:'2026-10-19',allocations:[{billId:'B-001',amount:2000}]});
  assert.doesNotMatch(fs.readFileSync(source,'utf8'),/paid:true|isPaid:true|forcePaid:true/);
});

test('settlement preflight rejects zero, overpayment, mismatched kind, invalid dates and account',()=>{
  const good={kind:'receipt',document:saleDoc,amount:'500',accountId:'1010',
    postingDate:'2026-10-20',eventId:'event-1',today:'2026-10-21'};
  for(const changes of [{document:null},{amount:''},{amount:'0'},{amount:'751'},
    {amount:'abc'},{kind:'payment'},{accountId:'2000'},
    {postingDate:'2026-10-09'},{postingDate:'2026-10-22'},
    {postingDate:'2026-02-30'},{eventId:'with spaces'}]){
    assert.ok(buildSettlementCommand({...good,...changes}).error,JSON.stringify(changes));
  }
});

test('workspace payments SSR displays native receipts/payments controls, no legacy panel',()=>{
  const html=render({initialSource:{kind:'payment',projectId:'p1'}});
  for(const label of ['تسویه فاکتور صادرشده','دریافت از مشتری','پرداخت به تأمین‌کننده',
    'فاکتور را صریحاً انتخاب کنید','حساب بانک یا صندوق','ثبت پرداخت واقعی',
    'ورود سرمایه واقعی'])assert.ok(html.includes(label),'Missing '+label);
  assert.match(html,/aria-label="ثبت دریافت یا پرداخت فاکتور"/);
  assert.match(html,/type="radio"/);
  assert.match(html,/disabled=""/);
  const content=fs.readFileSync(source,'utf8');
  assert.doesNotMatch(content,/AccountingPanel|showOldForm|setShowOldForm/);
  assert.match(content,/type:'funds\.deposit'/);
  assert.match(content,/'receipt\.record'/);
  assert.match(content,/'payment\.record'/);
});

test('a loading or failed project read does not permit command posting or show stale ledger',()=>{
  const content=fs.readFileSync(source,'utf8');
  assert.match(content,/loadedScope===projectId/);
  assert.match(content,/shown=readReady\?snapshot:normalizeSnapshot\(null\)/);
  assert.match(content,/!readReady \|\| !canManage/);
  assert.match(content,/setLoadedScope\(null\)/);
  assert.match(content,/setSettlementDocumentId\(''\)/);
  assert.doesNotMatch(content,/\{snapshot\.(?:documents|purchaseIntakes|balances|accounts|journals|receipts|payments)/);
  assert.match(content,/shown\.purchaseIntakes/);
  assert.match(content,/shown\.balances/);
  assert.match(content,/shown\.accounts/);
});

test('uncertain retry uses the same event ID also as receipt/payment and document ID',()=>{
  const content=fs.readFileSync(source,'utf8');
  assert.match(content,/retryToken\.current\?\.identity!==identity/);
  assert.match(content,/eventId:retryToken\.current\.eventId/);
  assert.match(content,/receiptId':'paymentId'\]:retryToken\.current\.eventId/);
  assert.match(content,/documentId:retryToken\.current\.eventId/);
  assert.match(content,/if\(inFlight\.current \|\| !readReady/);
});

test('catalog registration command matches backend and rejects missing/invalid fields',()=>{
  const example={itemId:'it-1',sku:'BOX-100',name:'جعبه',kind:'goods',unit:'عدد',eventId:'event-item-1'};
  assert.deepEqual(buildItemCreateCommand(example),{error:'',command:{type:'item.create',
    eventId:'event-item-1',itemId:'it-1',sku:'BOX-100',name:'جعبه',kind:'goods',unit:'عدد'}});
  for(const update of [{itemId:'invalid id'},{sku:''},{name:' '},{unit:' '},
    {kind:'stock'},{eventId:'bad id'}])assert.ok(buildItemCreateCommand({...example,...update}).error);
});

test('standalone purchase draft is task-free but real backend document.create',()=>{
  const input={kind:'purchase',projectId:'p1',partyId:'vendor-1',
    documentDate:'2026-10-20',description:'کاغذ تحویلی',quantity:'۲',
    unitPrice:'۳٬۰۰۰',discount:'100',tax:'50',note:'سند خرید',eventId:'event-doc-1',
    items:{}};
  const result=buildStandaloneDocumentCommand({...input,today:'2026-10-21'});
  assert.equal(result.error,'');assert.equal(result.total,5950);
  assert.deepEqual(result.command,{type:'document.create',eventId:'event-doc-1',
    documentId:'event-doc-1',projectId:'p1',kind:'purchase',partyId:'vendor-1',
    documentDate:'2026-10-20',lines:[{description:'کاغذ تحویلی',quantity:2,unitPrice:3000}],
    discount:100,tax:50,note:'سند خرید'});
  assert.equal(buildStandaloneDocumentCommand({...input,itemId:'unknown',today:'2026-10-21'}).error.length>0,true);
});

test('standalone invoice validation prevents zero, over-limit, future and invalid selected SKU',()=>{
  const input={kind:'sales',projectId:'p1',partyId:'person-1',documentDate:'2026-10-21',
    description:'خدمت چاپ',quantity:'1',unitPrice:'100',discount:'0',tax:'0',
    note:'',eventId:'test-1',today:'2026-10-21',items:{'it-1':{active:true}}};
  assert.equal(buildStandaloneDocumentCommand({...input,itemId:'it-1'}).error,'');
  for(const updates of [{projectId:''},{partyId:''},{quantity:'0'},{quantity:'1000001'},
    {unitPrice:'0'},{unitPrice:''},{discount:'101'},{tax:'1000000000000000'},
    {documentDate:'2026-10-22'},{itemId:'other'},{description:''},
    {note:'x'.repeat(1001)}])assert.ok(buildStandaloneDocumentCommand({...input,...updates}).error);
});

test('separate catalog, standalone document and reports pages are wired with honest nonstock scope',()=>{
  const catalog=render({initialSource:{kind:'items'}});
  assert.match(catalog,/ثبت در کاتالوگ/);
  assert.match(catalog,/انبار/);
  const manual=render({initialSource:{kind:'manual'}});
  assert.match(manual,/پیش‌نویس فاکتور مستقل/);
  assert.match(manual,/طرف‌حساب ثبت‌شده/);
  const code=fs.readFileSync(source,'utf8');
  assert.match(code,/shown\.reports\.trialBalance/);
  assert.match(code,/shown\.reports\.profitLoss/);
  assert.match(code,/shown\.reports\.balanceSheet/);
  assert.match(code,/گزارش‌های تراز آزمایشی و سود و زیان فقط در سطح همه پروژه‌ها معتبرند/);
});

test('RTL responsive payment forms have keyboard focus outline and scroll-safe tables',()=>{
  const css=fs.readFileSync(path.join(root,'src/accounting_workspace.css'),'utf8');
  assert.match(css,/direction:rtl/);
  assert.match(css,/\.accw-payment-card/);
  assert.match(css,/:focus-visible/);
  assert.match(css,/\.accw-table-scroll\{max-width:100%;overflow:auto/);
  assert.match(css,/@media\(max-width:660px\)/);
});

test('accounting exposes selectable display/input unit with explicit TOMAN legacy storage',()=>{
  const html=render({initialSource:{kind:'manual',projectId:'p1'}});
  assert.match(html,/aria-label="واحد پولی حسابداری"/);
  assert.match(html,/<option value="TOMAN" selected="">تومان<\/option>/);
  assert.match(html,/<option value="RIAL">ریال<\/option>/);
  assert.match(html,/میزبان فعلی و داده‌های قدیمی به/);
  assert.match(html,/مضرب‌های ۱۰/);
  assert.match(html,/قیمت واحد \(تومان\)/);
  assert.match(html,/تخفیف \(تومان\)/);
  assert.match(html,/مالیات مبلغ صریح \(تومان\)/);
});

test('all UI money inputs are converted at the TOMAN host boundary',()=>{
  const content=fs.readFileSync(source,'utf8');
  assert.match(content,/const settlementParsed=readAmount\(settlementAmount\)/);
  assert.match(content,/amount:String\(settlementParsed.amount\)/);
  assert.match(content,/const fundParsed=readAmount\(fundAmount\)/);
  assert.match(content,/const qty=integer\(quantity\), priceResult=readAmount\(unitPrice\)/);
  assert.match(content,/const result=readAmount\(priceInputs\[row.id\]\)/);
  assert.match(content,/unitPrice:moneyArg\(manualUnitPrice\)/);
  assert.match(content,/discount:moneyArg\(manualDiscount,true\),tax:moneyArg\(manualTax,true\)/);
  assert.match(content,/formatLegacyEntry\(t\?\.saleUnitPrice,moneyUnit\)/);
  assert.match(content,/setPriceInputs\(nextPriceInputs\)/);
  assert.match(content,/formatLegacyMoney\(n,moneyUnit/);
  assert.match(content,/تراز آزمایشی، مبالغ \{MONEY_UNITS\[moneyUnit\]\}/);
  assert.match(content,/گردش حساب \{reportAccountId\} به \{MONEY_UNITS\[moneyUnit\]\}/);
  assert.doesNotMatch(content,/const money=n=>Number\.isSafeInteger/);
});
