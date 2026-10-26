'use strict';
// Synthetic projected data only. No APPDATA, SQL, live accounting or DOM.
const test=require('node:test');
const assert=require('node:assert/strict');
const esbuild=require('esbuild');

const code=esbuild.buildSync({
  entryPoints:['src/accounting_management_analytics.js'],bundle:true,
  write:false,format:'cjs',platform:'node'
}).outputFiles[0].text;
const moduleRef={exports:{}};
new Function('module','exports',code)(moduleRef,moduleRef.exports);
const {buildManagementAnalytics}=moduleRef.exports;

const invoice=(id,date,total,lines=[],extra={})=>({
  id,status:'issued',documentDate:date,postingDate:date,
  total,returnedAmount:0,lines,...extra,
});
const line=(itemId,quantity,unitPrice)=>({
  itemId,description:itemId,quantity,unitPrice,total:quantity*unitPrice,
  accountId:'4000',
});
const journal=(id,date,lines,sourceType='journal.manual')=>({
  id,date,sourceType,sourceId:id,reversalOf:null,
  lines:lines.map(([accountId,debit,credit])=>({accountId,debit,credit})),
});
const base=(currency='RIAL')=>({
  currency,
  accounts:{
    '4000':{id:'4000',kind:'revenue',name:'Sales'},
    '4100':{id:'4100',kind:'expense',name:'Sales discount'},
    '5000':{id:'5000',kind:'expense',name:'Purchases'},
    '5100':{id:'5100',kind:'revenue',name:'Purchase discount'},
    '1010':{id:'1010',kind:'asset',name:'Bank'},
    '1200':{id:'1200',kind:'asset',name:'Receivable'},
    '3000':{id:'3000',kind:'equity',name:'Capital'},
  },
  invoices:{},items:{
    'paper':{id:'paper',name:'کاغذ',sku:'P',unit:'برگ',kind:'goods'},
    'ink':{id:'ink',name:'مرکب',sku:'I',unit:'عدد',kind:'goods'},
  },journals:[],cheques:{},returns:{},bills:{},proformas:{},
});
const options={from:'2026-01-01',to:'2026-03-31',today:'2026-03-15'};
const metric=(out,id)=>out.kpis.find(x=>x.id===id);
const chart=(out,id)=>out.charts.find(x=>x.id===id);
const reducedTop=out=>out.topProducts.map(({itemId,name,quantity,unit,salesAmount})=>({
  itemId,name,quantity,unit,salesAmount,
}));

test('dashboard contract: stable navigation, exact RIAL unit, empty month gaps and no fake profit',()=>{
  const v=base();
  const out=buildManagementAnalytics(v,options);
  assert.equal(out.error,'');
  assert.equal(out.currency,'RIAL');
  assert.equal(out.unit,'ریال');
  assert.deepEqual(out.range,options);
  assert.deepEqual(out.kpis.map(x=>x.id),
    ['sales','revenue','expenses','net','dueCheques']);
  assert.deepEqual(out.charts.map(x=>x.id),
    ['monthlySales','ledgerPerformance','topProducts']);
  assert.deepEqual(chart(out,'monthlySales').data,[
    {label:'2026-01',value:0},{label:'2026-02',value:0},
    {label:'2026-03',value:0}]);
  assert.equal(metric(out,'net').value,0);
  assert.equal(out.costData.available,false);
  assert.match(out.costData.reason,/بهای تمام‌شده/);
  assert.equal(out.reminders.length,0);
  assert.equal(out.topProducts.length,0);
  assert.ok(out.charts.every(x=>x.navigate&&x.type&&Array.isArray(x.data)));
  assert.ok(out.kpis.every(x=>x.navigate&&x.unit));
});

test('issued sales only; drafts, approved, cancelled, reversed never count as turnover',()=>{
  const v=base();
  v.invoices={
    a:invoice('a','2026-01-10',200,[line('paper',2,100)]),
    b:invoice('b','2026-02-01',900,[line('ink',9,100)],{status:'draft'}),
    c:invoice('c','2026-02-02',900,[line('ink',9,100)],{status:'approved'}),
    d:invoice('d','2026-02-03',900,[line('ink',9,100)],{status:'cancelled'}),
    e:invoice('e','2026-02-04',900,[line('ink',9,100)],{status:'reversed'}),
    f:invoice('f','2025-12-15',500,[line('ink',5,100)]),
    g:invoice('g','2026-04-01',700,[line('ink',7,100)]),
  };
  const out=buildManagementAnalytics(v,options);
  assert.equal(out.error,'');
  assert.equal(metric(out,'sales').value,200);
  assert.equal(out.salesDocumentCount,1);
  assert.deepEqual(chart(out,'monthlySales').data,[
    {label:'2026-01',value:200},{label:'2026-02',value:0},
    {label:'2026-03',value:0}]);
  assert.deepEqual(reducedTop(out),[{
    itemId:'paper',name:'کاغذ',quantity:2,unit:'برگ',salesAmount:200}]);
  // A draft invoice creates no GL revenue, even when it has a large total.
  assert.equal(metric(out,'revenue').value,0);
});

test('issued returns reduce net invoice sales, original issue month and item quantities',()=>{
  const v=base();
  v.invoices={
    a:invoice('a','2026-01-15',240,[line('paper',2,100),line('ink',1,60)],{
      returnedAmount:80,returnedQuantities:[1,0],discount:20,tax:0}),
    b:invoice('b','2026-02-10',60,[line('ink',2,30)]),
  };
  v.returns={
    part:{id:'part',documentId:'a',kind:'partial',direction:'sale',
      postingDate:'2026-03-01',amount:80,lines:[{lineIndex:0,quantity:1}]},
  };
  const out=buildManagementAnalytics(v,options);
  assert.equal(metric(out,'sales').value,220);
  assert.deepEqual(chart(out,'monthlySales').data,[
    {label:'2026-01',value:160},{label:'2026-02',value:60},
    {label:'2026-03',value:0}]);
  assert.deepEqual(reducedTop(out),[
    {itemId:'paper',name:'کاغذ',quantity:1,unit:'برگ',salesAmount:100},
    {itemId:'ink',name:'مرکب',quantity:3,unit:'عدد',salesAmount:120},
  ].sort((a,b)=>b.salesAmount-a.salesAmount));
  assert.ok(out.warnings.some(x=>/برگشت جزئی/.test(x)));
});

test('legacy partial return rows can supply per-line returned quantity',()=>{
  const v=base();
  v.invoices.a=invoice('a','2026-01-01',200,[line('paper',2,100)],{
    returnedAmount:100});
  v.returns={one:{kind:'partial',direction:'sale',documentId:'a',
    lines:[{lineIndex:0,quantity:1}],postingDate:'2026-02-10'}};
  const out=buildManagementAnalytics(v,options);
  assert.equal(out.error,'');
  assert.equal(out.topProducts[0].quantity,1);
  assert.equal(metric(out,'sales').value,100);
});

test('journal-based revenue, expenses, net include discounts, reversals and period filter',()=>{
  const v=base();
  v.invoices.a=invoice('a','2026-01-02',10000,[line('paper',2,5000)]);
  v.journals=[
    journal('old','2025-12-31',[['4000',0,2000],['1200',2000,0]]),
    journal('sale','2026-01-02',[['1200',1000,0],['4000',0,1000]],
      'invoice.issue'),
    journal('purchase','2026-01-03',[['5000',400,0],['1010',0,400]],
      'bill.issue'),
    journal('discount','2026-01-04',[['4100',60,0],['1200',0,60]]),
    journal('purchase-discount','2026-01-05',[['1010',20,0],['5100',0,20]]),
    journal('refund','2026-02-01',[['4000',300,0],['1200',0,300]],
      'invoice.return'),
    journal('future','2026-04-01',[['1200',777,0],['4000',0,777]]),
    journal('closure','2026-03-31',[['4000',3000,0],['3000',0,3000]],
      'fiscal.year.close'),
  ];
  const out=buildManagementAnalytics(v,options);
  assert.equal(out.error,'');
  assert.equal(metric(out,'sales').value,10000);
  assert.equal(metric(out,'revenue').value,720); // 1000+20-300
  assert.equal(metric(out,'expenses').value,460); // 400+60
  assert.equal(metric(out,'net').value,260);
  assert.deepEqual(chart(out,'ledgerPerformance').data,[
    {label:'درآمد',value:720},{label:'هزینه',value:460},{label:'تراز',value:260}]);
  assert.equal(v.journals[7].sourceType,'fiscal.year.close');
});

test('negative net GL result remains negative; no phantom estimate of cost',()=>{
  const v=base('TOMAN');
  v.journals=[
    journal('operational','2026-03-08',[['5000',2000,0],['1010',0,2000]]),
    journal('income','2026-03-09',[['1010',500,0],['4000',0,500]]),
  ];
  const out=buildManagementAnalytics(v,{...options,currency:'TOMAN'});
  assert.equal(out.unit,'تومان');
  assert.equal(metric(out,'net').value,-1500);
  assert.equal(metric(out,'expenses').value,2000);
  assert.equal(out.costData.available,false);
  assert.match(metric(out,'net').label,/غیرقطعی/);
  assert.ok(out.warnings.some(w=>/سود عملیاتی قطعی/.test(w)));
});

test('live cheque reminders only: overdue, today, next 7 days, returned exceptions',()=>{
  const v=base();
  const ch=(id,date,status,direction='payment')=>({
    id,status,dueDate:date,direction,amount:500,
    bankAccountId:'1010',reference:id,partyId:'P',documentId:'I'});
  v.cheques={
    old:ch('old','2026-02-15','issued'),
    bounce:ch('bounce','2026-05-15','returned'),
    now:ch('now','2026-03-15','received','receipt'),
    soon:ch('soon','2026-03-22','deposited','receipt'),
    beyond:ch('beyond','2026-03-23','issued'),
    cleared:ch('cleared','2026-03-15','cleared'),
    cancelled:ch('cancelled','2026-03-15','cancelled'),
  };
  v.historicalCheques={archived:{...ch('archived','2026-03-15','issued')}};
  const out=buildManagementAnalytics(v,options);
  assert.equal(out.error,'');
  assert.deepEqual(out.reminders.map(x=>x.id),
    ['cheque:bounce','cheque:old','cheque:now','cheque:soon']);
  assert.deepEqual(out.reminders.map(x=>x.status),
    ['returned','overdue','today','upcoming']);
  assert.ok(out.reminders.every(x=>x.navigate==='cheques'));
  assert.equal(metric(out,'dueCheques').value,4);
  assert.ok(out.reminders[0].subtitle.includes('ریال'));
  assert.ok(!out.reminders.some(x=>/archived/.test(x.id)));
});

test('top goods AND catalog services rank by gross line amount, not mixed quantity units',()=>{
  const v=base();
  v.items.consulting={id:'consulting',name:'مشاوره',kind:'service',unit:'ساعت'};
  v.invoices.a=invoice('a','2026-02-12',750,[
    line('paper',4,50),line('ink',1,250),line('consulting',3,100)]);
  const out=buildManagementAnalytics(v,options);
  assert.deepEqual(out.topProducts.map(x=>x.itemId),
    ['consulting','ink','paper']);
  assert.deepEqual(chart(out,'topProducts').data,[
    {label:'مشاوره',value:300},{label:'مرکب',value:250},
    {label:'کاغذ',value:200}]);
  assert.equal(out.topProducts[0].unit,'ساعت');
  assert.equal(out.topProducts[0].kind,'service');
  assert.equal(out.topProducts[1].unit,'عدد');
  assert.equal(out.topProducts[2].unit,'برگ');
});

test('uncatalogued services from real descriptions aggregate normalized equivalents only',()=>{
  const v=base();
  const free=(description,quantity,unitPrice)=>({
    description,quantity,unitPrice,total:quantity*unitPrice,accountId:'4000'});
  v.invoices.a=invoice('a','2026-02-20',500,[
    free('Design',2,100),free(' Design  ',1,100),
    free('Artwork',1,200)],{returnedAmount:100,returnedQuantities:[1,0,0]});
  const out=buildManagementAnalytics(v,options);
  assert.equal(out.error,'');
  assert.equal(metric(out,'sales').value,400);
  const descriptions=out.topProducts.filter(x=>x.kind==='uncatalogued');
  assert.equal(descriptions.length,2);
  assert.equal(new Set(descriptions.map(x=>x.key)).size,2);
  assert.ok(descriptions.every(x=>x.itemId===null&&/بدون کاتالوگ/.test(x.name)));
  const design=descriptions.find(x=>x.key==='description:design');
  const artwork=descriptions.find(x=>x.key==='description:artwork');
  assert.deepEqual([design.quantity,design.salesAmount],[2,200]);
  assert.deepEqual([artwork.quantity,artwork.salesAmount],[1,200]);
  assert.deepEqual(chart(out,'topProducts').data.map(x=>x.value),[200,200]);
});

test('full returns remove reversed invoice from issued sales and GL reversal nets revenue',()=>{
  const v=base();
  v.invoices.a=invoice('a','2026-01-05',200,[line('paper',2,100)],{
    status:'reversed'});
  v.journals=[
    journal('issue','2026-01-05',[
      ['1200',200,0],['4000',0,200]],'invoice.issue'),
    journal('reverse','2026-02-10',[
      ['1200',0,200],['4000',200,0]],'journal.reverse'),
  ];
  const out=buildManagementAnalytics(v,options);
  assert.equal(out.error,'');
  assert.equal(metric(out,'sales').value,0);
  assert.equal(metric(out,'revenue').value,0);
  assert.equal(metric(out,'net').value,0);
  assert.deepEqual(out.topProducts,[]);
  assert.deepEqual(chart(out,'monthlySales').data.map(x=>x.value),[0,0,0]);
});

test('valid dates and alias options; purely read only and independent of wall clock',()=>{
  const v=base();
  v.invoices.a=invoice('a','2026-02-12',30,[line('paper',1,30)]);
  const snapshot=structuredClone(v);
  const out=buildManagementAnalytics(v,{
    fromDate:'2026-02-01',toDate:'2026-02-28',
    today:'2026-02-15',currency:'RIAL'});
  assert.equal(out.error,'');
  assert.deepEqual(out.range,{
    from:'2026-02-01',to:'2026-02-28',today:'2026-02-15'});
  assert.equal(out.kpis[0].value,30);
  assert.deepEqual(v,snapshot);
  assert.equal(buildManagementAnalytics(v,{}).error,'');
});

test('invalid inputs, untrusted journal rows, broken returns, and FX mismatch fail closed',()=>{
  const v=base();
  assert.match(buildManagementAnalytics(null,options).error,/ساختار دفتر/);
  assert.ok(buildManagementAnalytics({...v,currency:'USD'},options).error);
  assert.ok(buildManagementAnalytics(v,{...options,currency:'TOMAN'}).error);
  assert.ok(buildManagementAnalytics(v,{...options,from:'2026-02-31'}).error);
  assert.ok(buildManagementAnalytics(v,{...options,to:'2025-01-01'}).error);
  assert.ok(buildManagementAnalytics(v,{...options,today:'2026-99-01'}).error);
  assert.ok(buildManagementAnalytics(v,{...options,
    from:'2010-01-01',to:'2026-03-31'}).error);
  v.invoices.a=invoice('a','2026-01-01',100,[line('paper',1,100)],{
    returnedAmount:101});
  assert.match(buildManagementAnalytics(v,options).error,/برگشت/);
  v.invoices.a.returnedAmount=0;
  v.invoices.a.returnedQuantities=[2];
  assert.ok(buildManagementAnalytics(v,options).error);
  v.invoices.a.returnedQuantities=[0];
  v.journals=[journal('bad','2026-01-02',[['unknown',0,1]])];
  assert.match(buildManagementAnalytics(v,options).error,/سرفصل/);
});

test('overflow of summed safe integers is explicitly rejected, not rounded',()=>{
  const v=base();
  v.invoices={
    a:invoice('a','2026-01-01',Number.MAX_SAFE_INTEGER,
      [line('paper',1,1)]),
    b:invoice('b','2026-02-01',100,[line('paper',1,100)]),
  };
  assert.match(buildManagementAnalytics(v,options).error,/دقت مجاز/);
  const w=base();
  w.journals=[
    journal('one','2026-01-01',[
      ['4000',0,Number.MAX_SAFE_INTEGER],['1200',Number.MAX_SAFE_INTEGER,0]]),
    journal('two','2026-02-01',[['4000',0,1],['1200',1,0]]),
  ];
  assert.match(buildManagementAnalytics(w,options).error,/دقت مجاز/);
});
