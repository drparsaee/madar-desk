'use strict';

// Isolated browser acceptance for the user-provided Trello card walkthrough.
// Only a disposable browser localStorage fixture is changed, never APPDATA.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const available=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);
const stages=[{id:'planned',label:'در انتظار',color:'#5e82b1',subtitle:''}];
const fixture={version:1,workspaces:[{id:'qa-space',name:'فضای آزمایشی',archived:false}],
  projects:[{id:'qa-project',name:'پروژه نمونه',color:'#6688ab',costEnabled:false,price:0}],
  boards:[{id:'qa-board',name:'برد نمونه',workspaceId:'qa-space',projectId:'qa-project',archived:false,stages,customFields:[]}],
  stages,tasks:[{id:'qa-task',projectId:'qa-project',boardId:'qa-board',listId:'planned',status:'planned',
    title:'کارت نمونه بازطراحی',priority:'medium',description:'شرح کوتاه کارت',labels:[],assignees:[],
    reports:[],checklist:[{id:'step1',text:'مرحله اولیه',done:false,cost:0}],cost:0,
    createdAt:'2026-11-04T10:00:00.000Z',updatedAt:'2026-11-04T10:00:00.000Z'}],
  settings:{theme:'dark',costDefault:false}};

async function freePort(){
  for(let i=0;i<50;i++){
    const port=20000+Math.floor(Math.random()*20000);
    try{await new Promise((resolve,reject)=>{
      const server=net.createServer();server.once('error',reject);
      server.listen(port,'127.0.0.1',()=>server.close(err=>err?reject(err):resolve()));
    });return port;
    }catch(err){if(err.code!=='EADDRINUSE')throw err;}
  }
  throw Error('No free Chromium-safe port');
}

test('Trello-like card quick menus, inline checklist and activity run in Chrome at desktop and mobile',
  {skip:!available,timeout:110000},async()=>{
    const {createServer}=await import('vite');
    const {chromium}=require(playwrightHome);
    const server=await createServer({root,logLevel:'error',server:{host:'127.0.0.1',port:await freePort(),strictPort:true,hmr:false,
      watch:{ignored:['**/.qa-*','**/.qa-*/**','**/research/**']}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      for(const width of [1440,480]){
        const context=await browser.newContext({viewport:{width,height:900},locale:'fa-IR'});
        await context.addInitScript(state=>{
          localStorage.setItem('madar-preview',JSON.stringify(state));
          localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
        },fixture);
        const page=await context.newPage(),errors=[];
        page.on('pageerror',err=>errors.push(err.message));
        page.setDefaultTimeout(12000);
        try{
          await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
          await page.getByRole('button',{name:'نمای کلی',exact:true}).click();
          await page.locator('.vitrea-overview-task').filter({hasText:'کارت نمونه بازطراحی'}).first().click();
          const drawer=page.getByRole('dialog',{name:'جزئیات کار'});
          await drawer.waitFor({state:'visible'});
          const layout=drawer.locator('.task-editor-layout');
          const cols=await layout.evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').filter(Boolean).length);
          assert.equal(cols,width===1440?2:1,'desktop has a separate activity column; mobile stacks it');
          const activity=drawer.locator('.task-activity-panel');
          assert.equal(await activity.isVisible(),true,'conversation visible by default');
          const nav=drawer.locator('.task-quick-actions');
          await nav.locator('> button[aria-controls="task-section-tags"]').click();
          const popover=nav.locator('.task-quick-popover');
          await popover.getByRole('textbox',{name:'نام برچسب جدید'}).fill('آماده');
          await popover.getByRole('button',{name:'افزودن برچسب'}).click();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].labels.includes('آماده'));
          await nav.locator('> button[aria-controls="task-section-checklist"]').click();
          await popover.getByRole('textbox',{name:'مرحله جدید چک‌لیست'}).fill('کار قابل انجام');
          await popover.getByRole('button',{name:'افزودن',exact:true}).click();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].checklist.some(x=>x.text==='کار قابل انجام'));
          await drawer.locator('#task-section-checklist .step-row').filter({hasText:'کار قابل انجام'}).locator('button.step-check').click();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].checklist.some(x=>x.text==='کار قابل انجام'&&x.done));
          await nav.locator('> button[aria-controls="task-section-checklist"]').click();
          await popover.getByRole('textbox',{name:'نام چک‌لیست جدید'}).fill('بررسی قبل از تحویل');
          await popover.getByRole('button',{name:'ساخت'}).click();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].checklists?.some(x=>x.name==='بررسی قبل از تحویل'));
          await popover.getByRole('textbox',{name:'مرحله جدید چک‌لیست'}).press('Escape');
          assert.equal(await popover.count(),0,'Escape dismisses the menu, not the card');
          assert.equal(await drawer.isVisible(),true);
          await nav.locator('> button[aria-controls="task-section-assignees"]').click();
          assert.equal(await popover.isVisible(),true,'members have a compact editor');
          await nav.locator('> button[aria-controls="task-section-assignees"]').click();
          assert.equal(await popover.count(),0,'second click closes the menu');
          await activity.getByRole('button',{name:'افزودن گزارش'}).click();
          await activity.getByRole('textbox',{name:'گزارش یک‌خطی'}).fill('نمونه گزارش آزمایشی');
          await activity.getByRole('button',{name:'ثبت گزارش'}).click();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].reports.some(x=>x.summary==='نمونه گزارش آزمایشی'));
          const screenshotDir=path.join(root,'.qa-trello-reference-20261105');
          fs.mkdirSync(screenshotDir,{recursive:true});
          await page.screenshot({path:path.join(screenshotDir,'card-'+width+'.png')});
          const bounds=await drawer.boundingBox();
          assert.ok(bounds&&bounds.x>=-2&&bounds.x+bounds.width<=width+2,'card stays within viewport');
          assert.deepEqual(errors,[],'no uncaught browser errors');
          console.log('TRELLO_REFERENCE_RUNTIME_PASSED',width,'px');
        }finally{await context.close();}
      }
    }finally{await browser?.close();await server.close();}
  });
