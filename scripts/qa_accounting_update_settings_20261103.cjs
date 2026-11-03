'use strict';
// Chromium-only synthetic acceptance; does not execute or download any installer.
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const assert=require('node:assert/strict');
const {chromium}=require(path.join(process.env.APPDATA,'npm','node_modules','playwright'));
const root=path.resolve(__dirname,'..');
const binary='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const fixture={
  revision:0,capabilities:{canManage:false,canDraft:false,canAdmin:false},
  view:{currency:'RIAL',companyProfile:{legalName:'QA synthetic',history:[]},
    accounts:{},parties:{},items:{},invoices:{},bills:{},receipts:{},
    payments:{},journals:[],cheques:{},proformas:{},returns:{},closedThrough:null},
};
async function port(){
  const server=net.createServer();
  await new Promise((resolve,reject)=>server.listen(0,'127.0.0.1',error=>error?reject(error):resolve()));
  const selected=server.address().port;
  await new Promise(resolve=>server.close(resolve));
  return selected;
}
async function main(){
  if(!fs.existsSync(binary))throw Error('Chrome missing');
  const {preview}=await import('vite');
  const server=await preview({root,logLevel:'error',preview:{host:'127.0.0.1',port:await port(),strictPort:true}});
  let browser;
  try{
    browser=await chromium.launch({headless:true,executablePath:binary});
    const context=await browser.newContext({viewport:{width:1360,height:900},locale:'fa-IR'});
    const page=await context.newPage();
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(payload=>{
      localStorage.setItem('madar-ui-theme','dark');
      window.__UPDATE_CALLS__={check:0,download:0,install:0,financialMutations:0};
      window.madar={
        standaloneAccountingRead:async()=>structuredClone(payload),
        standaloneAccountingCommand:async()=>{window.__UPDATE_CALLS__.financialMutations++;throw Error('No writes');},
        releaseCheck:async()=>{window.__UPDATE_CALLS__.check++;return {available:true,current:'1.0.11',latest:'1.0.12'};},
        releaseDownload:async()=>{window.__UPDATE_CALLS__.download++;return {verified:true,path:'synthetic-not-real'};},
        releaseInstall:async()=>{window.__UPDATE_CALLS__.install++;return {scheduledAfterExit:true,version:'1.0.12'};},
      };
    },fixture);
    await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,{waitUntil:'domcontentloaded'});
    await page.locator('.sac-ribbon-tabs').getByRole('button',{name:'تنظیمات و مدیریت',exact:true}).click();
    await page.locator('.sac-ribbon-tools').getByRole('button',{name:'تنظیمات برنامه',exact:true}).click();
    await page.getByRole('heading',{name:'به‌روزرسانی نرم‌افزار'}).waitFor();
    await page.getByRole('button',{name:'بررسی به‌روزرسانی'}).click();
    await page.getByText('نسخهٔ جدید قابل دریافت است.').waitFor();
    let calls=await page.evaluate(()=>window.__UPDATE_CALLS__);
    assert.deepEqual(calls,{check:1,download:0,install:0,financialMutations:0});
    await page.getByRole('button',{name:'دریافت نسخهٔ 1.0.12'}).click();
    await page.getByText(/بستهٔ رسمی دریافت و SHA-256/).waitFor();
    calls=await page.evaluate(()=>window.__UPDATE_CALLS__);
    assert.deepEqual(calls,{check:1,download:1,install:0,financialMutations:0});
    page.once('dialog',dialog=>dialog.accept());
    await page.getByRole('button',{name:'نصب امن پس از خروج'}).click();
    await page.getByText(/پس از بسته‌شدن کامل این برنامه/).waitFor();
    calls=await page.evaluate(()=>window.__UPDATE_CALLS__);
    assert.deepEqual(calls,{check:1,download:1,install:1,financialMutations:0});
    await page.getByRole('button',{name:/روشن/}).click();
    const theme=await page.evaluate(()=>({
      root:document.documentElement.dataset.theme,
      stored:localStorage.getItem('madar-ui-theme')
    }));
    assert.deepEqual(theme,{root:'light',stored:'light'});
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({checks:9,status:'PASS',calls,theme,mode:'synthetic Chromium, no financial writes or real downloads'}));
    await context.close();
  }finally{
    if(browser)await browser.close();
    await new Promise(resolve=>server.httpServer.close(resolve));
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
