'use strict';
// Disposable browser profile, in-memory Vite server and synthetic localStorage.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const available=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);
const stamp='2026-11-03T00:00:00.000Z';
const stages=[{id:'todo',label:'انجام‌دادنی',color:'#557799'}];
const fixture={version:1,projects:[{id:'p',name:'آزمایشی',color:'#6889bb'}],
  boards:[{id:'b',projectId:'p',workspaceId:'w',name:'برد آزمایش',archived:false,stages}],
  workspaces:[{id:'w',name:'فضای تست',archived:false}],stages,
  tasks:[{id:'c',projectId:'p',boardId:'b',listId:'todo',status:'todo',
    title:'عنوان اولیه',description:'متن قدیم',priority:'medium',completed:false,
    checklist:[{id:'paid',text:'مرحله پرداخت',done:true,cost:91000}],
    invoiceId:'issued-abc',cost:640000,reports:[],assignees:[],labels:[],
    createdAt:stamp,updatedAt:stamp}],settings:{theme:'light',costDefault:false}};
async function safePort(){
  const server=net.createServer();
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const port=server.address().port;
  await new Promise((resolve,reject)=>server.close(error=>error?reject(error):resolve()));
  return port;
}

test('full App drawer Undo/Redo and board keyboard reversal preserve issued financial data',
  {skip:!available,timeout:90000},async()=>{
    const {createServer}=await import('vite');
    const {chromium}=require(playwrightHome);
    const server=await createServer({root,logLevel:'error',server:{host:'127.0.0.1',
      port:await safePort(),strictPort:true,hmr:false,watch:{ignored:['**/research/**']}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1280,height:850},locale:'fa-IR'});
      await context.addInitScript(state=>{
        localStorage.setItem('madar-preview',JSON.stringify(state));
        localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      },fixture);
      const page=await context.newPage();page.setDefaultTimeout(12000);
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await page.locator('.task-card .task-title').first().click();
      const drawer=page.getByRole('dialog',{name:'جزئیات کار'});
      await drawer.waitFor();
      const title=drawer.getByRole('textbox',{name:'عنوان کار'});
      await title.fill('عنوان تازه');
      const undo=drawer.getByRole('button',{name:'بازگرداندن ویرایش کارت'});
      const redo=drawer.getByRole('button',{name:'انجام دوباره ویرایش کارت'});
      await undo.waitFor({state:'visible'});
      await page.waitForFunction(()=>document.querySelector('button[aria-label="بازگرداندن ویرایش کارت"]')?.disabled===false);
      await undo.click();
      assert.equal(await title.inputValue(),'عنوان اولیه');
      await redo.click();
      assert.equal(await title.inputValue(),'عنوان تازه');
      await drawer.getByRole('button',{name:'بستن'}).click();
      await page.locator('.page-heading h1').click();
      await page.keyboard.press('Control+z');
      await page.waitForFunction(()=>document.querySelector('.task-card .task-title')?.textContent.includes('عنوان اولیه'));
      await page.keyboard.press('Control+y');
      await page.waitForFunction(()=>document.querySelector('.task-card .task-title')?.textContent.includes('عنوان تازه'));
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].title==='عنوان تازه');
      const final=await page.evaluate(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0]);
      assert.equal(final.invoiceId,'issued-abc');
      assert.equal(final.cost,640000);
      assert.deepEqual(final.checklist,fixture.tasks[0].checklist);
      assert.deepEqual(errors,[]);
    }finally{if(browser)await browser.close();await server.close();}
  });
