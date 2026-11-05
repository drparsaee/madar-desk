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
  projects:[{id:'qa-project',name:'پروژه نمونه',color:'#6688ab',costEnabled:true,price:0}],
  boards:[{id:'qa-board',name:'برد نمونه',workspaceId:'qa-space',projectId:'qa-project',archived:false,stages,customFields:[]}],
  stages,tasks:[{id:'qa-task',projectId:'qa-project',boardId:'qa-board',listId:'planned',status:'planned',
    title:'کارت نمونه بازطراحی',priority:'medium',description:'شرح کوتاه کارت',labels:[],assignees:[],costEnabled:true,
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
          assert.equal(await drawer.locator('.task-primary-section').count(),3,'only description, checklist and files remain');
          assert.equal(await drawer.locator('#task-section-dependencies').count(),0,'dependency panel removed');
          assert.equal(await drawer.locator('#task-section-settings').count(),0,'advanced panel hidden initially');
          const screenshotDir=path.join(root,'.qa-trello-reference-20261105');
          fs.mkdirSync(screenshotDir,{recursive:true});
          await page.screenshot({path:path.join(screenshotDir,'card-opening-'+width+'.png')});
          await nav.getByRole('button',{name:'برچسب',exact:true}).click();
          const popover=nav.locator('.task-quick-popover');
          await popover.getByRole('textbox',{name:'نام برچسب جدید'}).fill('آماده');
          await popover.getByRole('button',{name:'افزودن برچسب'}).click();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].labels.includes('آماده'));
          await nav.getByRole('button',{name:'چک‌لیست',exact:true}).click();
          await popover.getByRole('textbox',{name:'مرحله جدید چک‌لیست'}).fill('کار قابل انجام');
          await popover.getByRole('button',{name:'افزودن',exact:true}).click();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].checklist.some(x=>x.text==='کار قابل انجام'));
          await drawer.locator('#task-section-checklist .step-row').filter({hasText:'کار قابل انجام'}).locator('button.step-check').click();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].checklist.some(x=>x.text==='کار قابل انجام'&&x.done));
          const step=drawer.locator('.task-checklist-item').filter({hasText:'کار قابل انجام'});
          await step.getByRole('button',{name:'مسئول کار قابل انجام'}).click();
          const memberBox=step.locator('.assignee-picker input[type="checkbox"]');
          if(await memberBox.count()){
            await memberBox.first().check();
            await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].checklist.some(x=>x.text==='کار قابل انجام'&&x.assignees?.length));
          }
          await step.getByRole('button',{name:'زمان کار قابل انجام'}).click();
          const dateControl=step.getByText('موعد این مرحله');
          assert.equal(await dateControl.count(),1,'step has its own date field');
          await step.getByRole('button',{name:'انتخاب تاریخ موعد این مرحله'}).click();
          await page.getByRole('group',{name:'تقویم انتخاب تاریخ'})
            .locator('.madar-mini-calendar__days button:not(.madar-mini-calendar__outside)').first().click();
          await page.waitForFunction(()=>/^\d{4}-\d{2}-\d{2}$/.test(
            JSON.parse(localStorage.getItem('madar-preview')).tasks[0].checklist.find(x=>x.text==='کار قابل انجام')?.dueDate||''));
          await step.getByRole('button',{name:'هزینه کار قابل انجام'}).click();
          assert.equal(await step.getByRole('combobox',{name:'طرف حساب کار قابل انجام'}).isDisabled(),true,'offline party list cannot be fabricated');
          await step.getByRole('textbox',{name:'هزینه مرحله کار قابل انجام',exact:true}).fill('2500');
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].checklist.find(x=>x.text==='کار قابل انجام')?.cost===2500);
          await step.getByRole('button',{name:'راهنمای هزینه'}).count().then(n=>assert.ok(n===0||n===1));
          await step.getByRole('button',{name:'بیشتر کار قابل انجام'}).click();
          assert.equal(await step.getByRole('button',{name:'حذف مرحله'}).count(),1);
          assert.equal(await step.getByRole('button',{name:'حذف مرحله'}).isDisabled(),true,'paid checklist item stays protected');
          await nav.getByRole('button',{name:'چک‌لیست',exact:true}).click();
          await popover.getByRole('textbox',{name:'نام چک‌لیست جدید'}).fill('بررسی قبل از تحویل');
          await popover.getByRole('button',{name:'ساخت'}).click();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].checklists?.some(x=>x.name==='بررسی قبل از تحویل'));
          await popover.getByRole('textbox',{name:'مرحله جدید چک‌لیست'}).press('Escape');
          assert.equal(await popover.count(),0,'Escape dismisses the menu, not the card');
          assert.equal(await drawer.isVisible(),true);
          await nav.getByRole('button',{name:'اعضا',exact:true}).click();
          assert.equal(await popover.isVisible(),true,'members have a compact editor');
          await nav.getByRole('button',{name:'اعضا',exact:true}).click();
          assert.equal(await popover.count(),0,'second click closes the menu');
          const fileSection=drawer.locator('#task-section-attachments');
          assert.equal(await fileSection.isVisible(),true);
          assert.equal(await fileSection.locator('.attachment-warning:visible').count(),0,'host warning hidden under help');
          assert.equal(await fileSection.getByLabel('بارگذاری فایل کارت').count(),1);
          await fileSection.getByRole('button',{name:'لینک اشتراکی'}).click();
          await fileSection.getByRole('textbox',{name:'عنوان فایل'}).fill('نمونه');
          await fileSection.getByRole('textbox',{name:'مسیر اشتراک ویندوز'}).fill('\\\\OFFICE-PC\\Projects\\sample.pdf');
          await fileSection.getByRole('button',{name:'ثبت لینک'}).click();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].fileLinks?.some(x=>x.name==='نمونه'));
          assert.equal(await fileSection.getByRole('button',{name:'دانلود نمونه'}).count(),1,'clickable filename downloads');
          await nav.getByRole('button',{name:'بیشتر'}).click();
          assert.equal(await nav.locator('.task-more-menu').getByRole('button',{name:'مرحله و اولویت'}).count(),1);
          await nav.locator('.task-more-menu').getByRole('button',{name:'مرحله و اولویت'}).click();
          assert.equal(await drawer.locator('#task-section-metadata').isVisible(),true);
          assert.equal(await drawer.locator('#task-section-dependencies').count(),0);
          await drawer.getByRole('button',{name:'بستن جزئیات تکمیلی'}).click();
          assert.equal(await drawer.locator('#task-section-metadata').count(),0);
          await activity.getByRole('button',{name:'افزودن گزارش'}).click();
          await activity.getByRole('textbox',{name:'گزارش یک‌خطی'}).fill('نمونه گزارش آزمایشی');
          await activity.getByRole('button',{name:'ثبت گزارش'}).click();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].reports.some(x=>x.summary==='نمونه گزارش آزمایشی'));
          await page.screenshot({path:path.join(screenshotDir,'card-'+width+'.png')});
          const bounds=await drawer.boundingBox();
          assert.ok(bounds&&bounds.x>=-2&&bounds.x+bounds.width<=width+2,'card stays within viewport');
          assert.deepEqual(errors,[],'no uncaught browser errors');
          console.log('TRELLO_REFERENCE_RUNTIME_PASSED',width,'px');
        }finally{await context.close();}
      }
    }finally{await browser?.close();await server.close();}
  });
