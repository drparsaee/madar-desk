'use strict';
// Actual headless Edge renders the same React customer-selection component
// used by TaskEditor. This test never touches a production network or ledger.
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
// Playwright is already installed in the adjacent Taraz QA workspace. Reuse
// it without npm install or modifying Madar's pinned v1.0.28 dependencies.
const playwright=(()=>{try{return require('playwright');}catch(error){
  if(error.code!=='MODULE_NOT_FOUND')throw error;
  return require(path.resolve(root,'..','..','000- Taraz',
    'taraz-mtr-e2-isolated-20261109','node_modules','playwright'));
}})();

test('admin-only mailbox search selects immutable Taraz party ref and survives card reopen',async t=>{
  const app=`import React,{useState} from 'react';
    import {createRoot} from 'react-dom/client';
    import Picker from './src/taraz_customer_picker.jsx';
    const W='d'.repeat(32), I='a'.repeat(32), C='c'.repeat(32),K='ik_'+'e'.repeat(24);
    window.qa={W,I,C,K,reads:0,writes:0,finance:0,pending:0,ready:false,selected:null};
    const api={
      integrationMailboxConnections:async auth=>{if(auth.username!=='owner'||auth.password!=='safe-qa-password')throw Error('AUTH_REQUIRED');
        return {connections:[{keyId:K,product:'TARAZ',status:'active',installationId:I,username:'owner'}]};},
      integrationMailboxApproveCompany:async(auth,body)=>{if(auth.password!=='safe-qa-password'||body.companyId!==C||body.keyId!==K||body.manualConfirmation!==true)throw Error('AUTH_REQUIRED');return {approved:true};},
      integrationMailboxEnqueue:async(auth,body)=>{if(auth.password!=='safe-qa-password'||body.companyId!==C||!body.requestId)throw Error('AUTH_REQUIRED');window.qa.pending++;return {status:'pending',workspaceId:W,requestId:body.requestId};},
      integrationMailboxReconcile:async(auth,body)=>{if(auth.password!=='safe-qa-password')throw Error('AUTH_REQUIRED');window.qa.reads++;
        return window.qa.ready?{status:'completed',result:{parties:[{partyId:'TARAZ-A01',name:'شرکت آریا',kind:'customer'}],hasMore:false,nextCursor:null}}:{status:'pending',result:null};},
      standaloneAccountingCommand:async()=>{window.qa.finance++;}
    };
    function Harness(){const [card,setCard]=useState({id:'task-1',title:'QA card'});
      window.qa.currentCard=card;
      return <Picker api={api} task={card} username='owner' canEdit={true}
        onUpdate={next=>{window.qa.writes++;setCard(old=>({...old,...next}));}}/>;}
    createRoot(document.getElementById('root')).render(<Harness/>);`;
  const output=(await esbuild.build({stdin:{contents:app,resolveDir:root,
      loader:'jsx',sourcefile:'taraz-customer-picker-browser-test.jsx'},
      bundle:true,write:false,platform:'browser',format:'iife',outdir:'qa',
      logLevel:'silent'})).outputFiles;
  const browser=await playwright.chromium.launch({channel:'msedge',headless:true});
  t.after(()=>browser.close());
  const page=await browser.newPage();
  await page.setContent('<div id="root"></div>');
  await page.addScriptTag({content:output.find(item=>item.path.endsWith('.js')).text});
  await page.getByRole('button',{name:'بازکردن جست‌وجو'}).click();
  await page.getByLabel('رمز ورود مدیر').fill('safe-qa-password');
  await page.getByRole('button',{name:'بررسی نصب‌های Pairشده'}).click();
  await page.getByText('نصب‌های تراز شناسایی شدند.',{exact:false}).waitFor();
  await page.getByLabel('شناسهٔ ۳۲رقمی شرکت از داخل تراز').fill('c'.repeat(32));
  await page.getByLabel('شناسهٔ شرکت را با اطلاعات همان شرکت در تراز مستقل تطبیق دادم.').check();
  await page.getByRole('button',{name:'تأیید مجوز شرکت'}).click();
  await page.getByText('مجوز مستقل این شرکت',{exact:false}).waitFor();
  await page.getByLabel('جست‌وجوی مشتری تراز').fill('آریا');
  await page.getByRole('button',{name:'ثبت درخواست جست‌وجو در Mailbox'}).click();
  await page.getByText('درخواست در صندوق پایدار مدار ثبت شد.',{exact:false}).waitFor();
  let captured=await page.evaluate(()=>window.qa);
  assert.equal(captured.pending,1);
  assert.equal(captured.currentCard.tarazCustomerRef,undefined);
  assert.match(captured.currentCard.tarazCustomerRequest.requestId,/^[a-f0-9]{32}$/);
  await page.getByRole('button',{name:'دریافت پاسخ امضاشدهٔ تراز'}).click();
  await page.getByText('درخواست هنوز در انتظار پاسخ تراز است.',{exact:false}).waitFor();
  assert.equal(await page.getByText('شرکت آریا').count(),0);
  await page.evaluate(()=>{window.qa.ready=true;});
  await page.getByRole('button',{name:'دریافت پاسخ امضاشدهٔ تراز'}).click();
  await page.getByRole('button',{name:'انتخاب'}).click();
  await page.getByText('مشتری مرتبط:').waitFor();
  captured=await page.evaluate(()=>window.qa);
  assert.deepEqual(captured.currentCard.tarazCustomerRef,{
    workspaceId:'d'.repeat(32),companyId:'c'.repeat(32),
    installationId:'a'.repeat(32),partyId:'TARAZ-A01',kind:'customer'});
  assert.equal(captured.currentCard.tarazCustomerRequest,null);
  assert.equal(captured.finance,0);
  await page.getByRole('button',{name:'بستن جست‌وجو'}).click();
  await page.getByRole('button',{name:'بازکردن جست‌وجو'}).click();
  assert.equal(await page.getByText('TARAZ-A01').count()>0,true);
  assert.equal(await page.getByText('شرکت آریا').count(),0);
});
