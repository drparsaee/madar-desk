'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');

const root=path.resolve(__dirname,'..');
const nodeModules=fs.existsSync(path.join(root,'node_modules','esbuild'))?
  path.join(root,'node_modules'):path.join(root,'..','madar-desk','node_modules');
const esbuild=require(path.join(nodeModules,'esbuild'));
const React=require(path.join(nodeModules,'react'));
const {renderToStaticMarkup}=require(path.join(nodeModules,'react-dom/server'));
const entry=path.join(root,'src/accounting_operational_panels.jsx');
const compiled=esbuild.buildSync({entryPoints:[entry],bundle:true,format:'cjs',
  platform:'node',write:false,jsx:'automatic',nodePaths:[nodeModules],
  external:['react','react/jsx-runtime','lucide-react'],loader:{'.css':'empty'}})
  .outputFiles[0].text;
const mod=new Module(entry,module);
mod.filename=entry;
mod.paths=[nodeModules,...Module._nodeModulePaths(path.dirname(entry))];
mod._compile(compiled,entry);
const {LiveInventory,previewExactPurchaseDiscountAllocation:preview}=mod.exports;

const bill={id:'B1',status:'issued',discount:10,tax:18,
  lines:[
    {itemId:'A',description:'Synthetic goods A',quantity:3,unitPrice:100,total:300},
    {itemId:'B',description:'Synthetic goods B',quantity:2,unitPrice:70,total:140},
    {description:'Synthetic service',quantity:1,unitPrice:50,total:50},
  ]};
const valid={bill,amounts:['1','3','6'],reference:'supplier-evidence-1',
  reason:'Supplier invoice line discount statement',itemId:'A',quantity:'2',
  taxTreatment:'expense',movements:{},returns:{}};

test('exact integers, supplier line indexes, total, and received FIFO preview are source-derived',()=>{
  const review=preview(valid);
  assert.equal(review.ready,true,review.error);
  assert.equal(review.documentDiscount,10);
  assert.equal(review.allocatedTotal,10);
  assert.equal(review.expectedReceiptValue,200);
  assert.equal(review.availableQuantity,3);
  assert.equal(review.expectedUnitCostLow,99);
  assert.equal(review.expectedUnitCostHigh,100);
  assert.deepEqual(review.fields,{
    discountAllocation:'per-line-exact',
    lineDiscounts:[{lineIndex:0,amount:1},{lineIndex:1,amount:3},{lineIndex:2,amount:6}],
    allocationReference:'supplier-evidence-1',
    allocationReason:'Supplier invoice line discount statement',
  });
  assert.equal(preview({...valid,quantity:'3'}).expectedReceiptValue,299);
  assert.equal(preview({...valid,quantity:'1',movements:{M:{id:'M',type:'inventory.receive',
    billId:'B1',itemId:'A',quantity:2,discountAllocation:'per-line-exact'}}})
    .expectedReceiptValue,99);
});

test('unsafe and unproven input stays blocked before engine mutation',()=>{
  const bad=[
    [{...valid,amounts:['1','3','']},'تخفیف ردیف'],
    [{...valid,amounts:['1','3','5']},'جمع تخفیف'],
    [{...valid,amounts:['1','3','7']},'جمع تخفیف'],
    [{...valid,amounts:['1.5','3','6']},'عدد باید'],
    [{...valid,amounts:['NaN','3','6']},'عدد باید'],
    [{...valid,amounts:['9007199254740994','3','6']},'محدوده'],
    [{...valid,amounts:['1','3']},'همه ردیف'],
    [{...valid,reference:''},'شناسه مدرک'],
    [{...valid,reference:'supplier ref'},'شناسه مدرک'],
    [{...valid,reason:' '},'دلیل'],
    [{...valid,itemId:'missing'},'دقیقاً در یک ردیف'],
    [{...valid,quantity:'4'},'بیشتر'],
    [{...valid,taxTreatment:''},'۵۲۰۰'],
    [{...valid,movements:{old:{type:'inventory.receive',billId:'B1',itemId:'A',
      quantity:1}}},'سیاست تخصیص دیگری'],
    [{...valid,returns:{old:{direction:'purchase',documentId:'B1'}}},'برگشت قبلی'],
    [{...valid,bill:{...bill,returnedQuantities:[1,0,0]}},'برگشت جزئی'],
    [{...valid,bill:{...bill,receiptDiscountAllocation:{lineDiscounts:[2,2,6],
      allocationReference:'supplier-evidence-1',allocationReason:valid.reason}}},
    'قابل تغییر نیست'],
    [{...valid,bill:{...bill,lines:[bill.lines[0],{...bill.lines[1],itemId:'A'},
      bill.lines[2]]}},'دقیقاً در یک ردیف'],
  ];
  for(const [scenario,message] of bad){
    const result=preview(scenario);
    assert.equal(result.ready,false,JSON.stringify(scenario));
    assert.match(result.error,new RegExp(message));
    assert.equal(result.fields,null);
  }
});

test('previous supplier policy is frozen; source-backed documents render for viewer without edit forms',()=>{
  const saved={lineDiscounts:[1,3,6],allocationReference:valid.reference,
    allocationReason:valid.reason};
  assert.equal(preview({...valid,bill:{...bill,receiptDiscountAllocation:saved}}).ready,true);
  const view={bills:{B1:{...bill,receiptDiscountAllocation:saved}},invoices:{},
    items:{A:{id:'A',kind:'goods',stockTracked:true,name:'A'}},
    warehouses:{WH1:{id:'WH1',name:'Main'}},stock:{},stockMovements:{},returns:{}};
  const html=renderToStaticMarkup(React.createElement(LiveInventory,{
    view,canManage:false,canAdmin:false,disabled:false,today:'2026-11-03',
    unit:'ریال',execute:async()=>true}));
  assert.doesNotMatch(html,/sac-operational-form/);
  assert.doesNotMatch(html,/تخصیص مستندِ مبلغ تخفیف/);
});

test('live React/Chrome: admin opt-in exact submission, validation, stored policy, editor and revoked ACL',
  {timeout:120000},async()=>{
    const playwrightDir=path.join(process.env.USERPROFILE||'',
      'AppData','Roaming','npm','node_modules','playwright');
    const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
    assert.ok(fs.existsSync(playwrightDir),'Playwright installation missing');
    assert.ok(fs.existsSync(chrome),'Chrome installation missing');
    const {chromium}=require(playwrightDir);
    const browserCode=esbuild.buildSync({
      stdin:{contents:`
        import React from 'react';
        import {createRoot} from 'react-dom/client';
        import {LiveInventory} from './src/accounting_operational_panels.jsx';
        const root=createRoot(document.querySelector('#app'));
        const bill=${JSON.stringify(bill)};
        const simpleBill={id:'B2',status:'issued',discount:10,tax:0,
          lines:[{itemId:'A',description:'Simple two-unit goods',
            quantity:2,unitPrice:50,total:100}]};
        const baseView={
          bills:{B1:bill,B2:simpleBill},invoices:{},
          items:{A:{id:'A',name:'Goods A',kind:'goods',stockTracked:true},
            B:{id:'B',name:'Goods B',kind:'goods',stockTracked:true}},
          warehouses:{WH1:{id:'WH1',name:'Main warehouse'}},stock:{},
          stockMovements:{},returns:{},
        };
        let mountKey=0;
        window.__commands=[];
        window.__mount=(role='admin',options={})=>{
          if(options.fresh!==false){mountKey++;window.__commands=[];}
          const view={...baseView,bills:{B1:{...bill,...options.bill},B2:simpleBill}};
          root.render(React.createElement(LiveInventory,{
            key:mountKey,view,canManage:role!=='viewer',canAdmin:role==='admin',
            disabled:false,today:'2026-11-03',unit:'ریال',
            execute:async create=>{
              const result=create('synthetic-ui-'+(window.__commands.length+1));
              window.__commands.push(result.command);
              return true;
            },
          }));
        };
        window.__mount('admin');
      `,resolveDir:root,sourcefile:'fin02-browser-entry.jsx',loader:'jsx'},
      bundle:true,format:'iife',platform:'browser',write:false,jsx:'automatic',
      nodePaths:[nodeModules],loader:{'.css':'empty'},
    }).outputFiles[0].text;
    const browser=await chromium.launch({headless:true,executablePath:chrome});
    try{
      for(const width of [390,1440]){
        const page=await browser.newPage({viewport:{width,height:900},locale:'fa-IR'});
        const errors=[];
        page.on('pageerror',error=>errors.push(error.message));
        try{
          await page.setContent('<html lang="fa" dir="rtl"><body><div id="app"></div></body></html>');
          await page.addScriptTag({content:browserCode});
          const form=page.locator('.sac-operational-form').last();
          await form.getByLabel('انبار مبدأ').selectOption('WH1');
          await form.getByLabel('کالای دارای رهگیری').selectOption('A');
          await form.getByLabel('تعداد صحیح در واحد پایه').fill('2');
          await form.getByLabel('فاکتور خرید قطعی').selectOption('B1');
          await form.getByLabel('تعیین تکلیف مالیات خرید').selectOption('expense');
          await form.getByLabel('تخصیص تخفیف خرید در ارزش موجودی')
            .selectOption('per-line-exact');
          await form.getByLabel('تخفیف ردیف 1').fill('1');
          await form.getByLabel('تخفیف ردیف 2').fill('3');
          await form.getByLabel('تخفیف ردیف 3').fill('5');
          await form.getByLabel('شناسه مدرک تخصیص تأمین‌کننده (حروف/اعداد لاتین)')
            .fill('supplier-evidence-1');
          await form.getByLabel('علت و مبنای مستند تخصیص تخفیف')
            .fill('Supplier invoice line discount statement');
          assert.match(await form.locator('[role="alert"]').last().innerText(),/جمع تخفیف/);
          assert.equal(await form.getByRole('button',{name:'ثبت با سابقه حسابداری'}).isDisabled(),true);
          assert.equal(await page.evaluate(()=>window.__commands.length),0);
          await form.getByLabel('تخفیف ردیف 3').fill('6');
          assert.match(await form.locator('[role="status"]').innerText(),/۲۰۰/);
          await form.getByRole('checkbox').check();
          await form.getByRole('button',{name:'ثبت با سابقه حسابداری'}).click();
          await page.waitForFunction(()=>window.__commands.length===1);
          const posted=await page.evaluate(()=>window.__commands[0]);
          assert.deepEqual({type:posted.type,discountAllocation:posted.discountAllocation,
            lineDiscounts:posted.lineDiscounts,allocationReference:posted.allocationReference,
            allocationReason:posted.allocationReason,taxTreatment:posted.taxTreatment,
            quantity:posted.quantity,billId:posted.billId},
          {type:'inventory.receive',discountAllocation:'per-line-exact',
            lineDiscounts:[{lineIndex:0,amount:1},{lineIndex:1,amount:3},
              {lineIndex:2,amount:6}],allocationReference:'supplier-evidence-1',
            allocationReason:'Supplier invoice line discount statement',
            taxTreatment:'expense',quantity:2,billId:'B1'});
          // Changing bill must discard the previously edited admin policy and approval.
          await form.getByLabel('فاکتور خرید قطعی').selectOption('B2');
          assert.equal(await form.getByLabel('تخصیص تخفیف خرید در ارزش موجودی').inputValue(),'');
          assert.equal(await form.locator('input[aria-label="تخفیف ردیف 1"]').count(),0);
          await form.getByLabel('فاکتور خرید قطعی').selectOption('B1');
          assert.equal(await form.getByLabel('تخصیص تخفیف خرید در ارزش موجودی').inputValue(),'');
          // Existing per-bill source allocation remains locked and reusable.
          await page.evaluate(()=>window.__mount('admin',{bill:{
            receiptDiscountAllocation:{lineDiscounts:[1,3,6],
              allocationReference:'supplier-evidence-1',
              allocationReason:'Supplier invoice line discount statement'}
          }}));
          await form.getByLabel('فاکتور خرید قطعی').selectOption('B1');
          await form.getByLabel('تخصیص تخفیف خرید در ارزش موجودی')
            .selectOption('per-line-exact');
          assert.equal(await form.getByLabel('تخفیف ردیف 1').getAttribute('readonly'),'');
          assert.equal(await form.getByLabel('شناسه مدرک تخصیص تأمین‌کننده (حروف/اعداد لاتین)')
            .getAttribute('readonly'),'');
          // Editor with finance edit permissions cannot establish exact policy.
          await page.evaluate(()=>window.__mount('editor'));
          await form.getByLabel('فاکتور خرید قطعی').selectOption('B1');
          assert.equal(await form.locator('option[value="per-line-exact"]').count(),0);
          assert.match(await form.innerText(),/حسابدار نمی‌تواند این سیاست را ایجاد/);
          // The existing one-line uniform route remains available to authorized editors.
          await form.getByLabel('انبار مبدأ').selectOption('WH1');
          await form.getByLabel('کالای دارای رهگیری').selectOption('A');
          await form.getByLabel('تعداد صحیح در واحد پایه').fill('1');
          await form.getByLabel('فاکتور خرید قطعی').selectOption('B2');
          await form.getByLabel('تخصیص تخفیف خرید در ارزش موجودی')
            .selectOption('single-line-uniform');
          await form.getByRole('button',{name:'ثبت با سابقه حسابداری'}).click();
          await page.waitForFunction(()=>window.__commands.length===1);
          const editorPosted=await page.evaluate(()=>window.__commands[0]);
          assert.equal(editorPosted.discountAllocation,'single-line-uniform');
          assert.equal(editorPosted.billId,'B2');
          assert.equal('lineDiscounts' in editorPosted,false);
          assert.equal('taxTreatment' in editorPosted,false);
          // Revocation clears the selected administrator-only mode before any submit.
          await page.evaluate(()=>window.__mount('admin'));
          await form.getByLabel('فاکتور خرید قطعی').selectOption('B1');
          await form.getByLabel('تخصیص تخفیف خرید در ارزش موجودی')
            .selectOption('per-line-exact');
          await page.evaluate(()=>window.__mount('editor',{fresh:false}));
          await page.waitForFunction(()=>document.querySelector(
            'select option[value="per-line-exact"]')===null);
          assert.equal(await page.evaluate(()=>window.__commands.length),0);
          await page.evaluate(()=>window.__mount('viewer'));
          assert.equal(await page.locator('.sac-operational-form').count(),0);
          assert.deepEqual(errors,[]);
        }finally{await page.close();}
      }
    }finally{await browser.close();}
  });
