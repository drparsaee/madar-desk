'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPath='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const fixture={version:1,
  projects:[{id:'project',name:'پروژه مصنوعی',color:'#657faa',costEnabled:false,price:0}],
  workspaces:[{id:'workspace',name:'فضای آزمون',archived:false}],
  boards:[{id:'board',workspaceId:'workspace',projectId:'project',name:'برد آزمون',
    archived:false,stages:[{id:'inbox',label:'شروع',subtitle:'',color:'#657faa'}]}],
  stages:[{id:'inbox',label:'شروع',subtitle:'',color:'#657faa'}],
  tasks:[],settings:{theme:'light',costDefault:false}};

async function freePort(){return new Promise((resolve,reject)=>{
  const server=net.createServer();server.once('error',reject);
  server.listen(0,'127.0.0.1',()=>{
    const port=server.address().port;
    server.close(err=>err?reject(err):resolve(port));
  });
});}

test('integrated task titlebar vetoes unsubmitted and pending host-save drafts, then safely unfreezes',
  {timeout:90000},async()=>{
  assert.ok(fs.existsSync(chrome));assert.ok(fs.existsSync(playwrightPath));
  const {chromium}=require(playwrightPath);
  const {createServer}=await import('vite');
  const server=await createServer({root,logLevel:'error',server:{
    host:'127.0.0.1',port:await freePort(),strictPort:true,hmr:false,
    watch:{ignored:['**/.qa-*','**/WebView2/**','**/research/**']}}});
  let browser;
  try{
    await server.listen();
    browser=await chromium.launch({headless:true,executablePath:chrome});
    const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR'});
    await context.addInitScript(data=>{
      const clone=value=>structuredClone(value);
      let host=clone(data);
      localStorage.setItem('madar-preview',JSON.stringify(host));
      localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      window.__qaTaskClose={saves:0,alerts:[],pending:false};
      window.alert=message=>window.__qaTaskClose.alerts.push(String(message));
      window.madar={
        getState:async()=>clone(host),getStateForUi:async()=>clone(host),
        saveState:state=>{
          window.__qaTaskClose.saves++;
          window.__qaTaskClose.pending=true;
          return new Promise(resolve=>{
            window.__qaTaskClose.ack=()=>{
              host=clone(state);
              window.__qaTaskClose.pending=false;
              resolve({localRevision:'qa-native-close-ack'});
            };
          });
        },
        lanStatus:async()=>({mode:'solo',user:{username:'qa',role:'admin',projects:null}}),
        lanProfiles:async()=>[],getPreferences:async()=>({calendar:'jalali',clockWidget:'hidden'}),
        syncStatus:async()=>({}),releaseCheck:async()=>({available:false}),
      };
    },fixture);
    const page=await context.newPage();
    page.setDefaultTimeout(14000);
    const errors=[];page.on('pageerror',err=>errors.push(err.message));
    await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>typeof window.__madarTasksConfirmNativeClose==='function');
    await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
      .getByRole('button',{name:'برد کارها'}).click();
    const lane=page.locator('.kanban-lane[aria-label="ستون شروع"]');
    await lane.locator('.lane-add-card').click();
    const form=lane.getByRole('form',{name:'افزودن کارت به شروع'});
    const title=form.getByRole('textbox',{name:'عنوان کارت جدید'});
    await title.fill('پیش‌نویس کارت بدون ذخیره');
    assert.equal(await page.evaluate(()=>window.__madarTasksConfirmNativeClose()),false,
      'Native X must veto before the quick-add title is committed');
    assert.equal(await title.inputValue(),'پیش‌نویس کارت بدون ذخیره');
    await form.getByRole('button',{name:'افزودن کارت',exact:true}).click();
    await page.waitForFunction(()=>window.__qaTaskClose.pending);
    assert.equal(await page.evaluate(()=>window.__madarTasksConfirmNativeClose()),false,
      'A pending host save must not be lost when the titlebar X is clicked');
    await page.evaluate(()=>window.__qaTaskClose.ack());
    await page.getByText('کارت ذخیره شد؛ برای تکمیل جزئیات روی آن کلیک کنید.')
      .waitFor({state:'visible'});
    await page.waitForFunction(()=>window.__qaTaskClose.pending===false);
    assert.equal(await page.evaluate(()=>window.__madarTasksConfirmNativeClose()),true);
    assert.equal(await page.locator('.app-shell').getAttribute('aria-busy'),'true');
    assert.equal(await page.evaluate(()=>document.querySelector('.app-shell').inert),true);
    assert.equal(await page.evaluate(()=>window.__madarTasksAbortNativeClose()),true);
    assert.equal(await page.evaluate(()=>document.querySelector('.app-shell').inert),false);
    assert.equal(await page.locator('.app-shell').getAttribute('aria-busy'),null);
    assert.ok((await page.evaluate(()=>window.__qaTaskClose.alerts)).length>=2);
    assert.deepEqual(errors,[]);
    await context.close();
  }finally{await browser?.close();await server.close();}
});
