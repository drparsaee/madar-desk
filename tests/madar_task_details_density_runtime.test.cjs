'use strict';

const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const available=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);

const stages=[{id:'planned',label:'برنامه‌ریزی',color:'#5e82b1',subtitle:''}];
const fixture={version:1,
  projects:[{id:'qa-project',name:'پروژه آزمون',color:'#6688ab',costEnabled:true,price:0}],
  workspaces:[{id:'qa-space',name:'فضای QA',archived:false}],
  boards:[{id:'qa-board',name:'برد QA',workspaceId:'qa-space',projectId:'qa-project',
    archived:false,stages,customFields:[
      {id:'sku',name:'کد سفارش',type:'text'},
      {id:'quantity',name:'تیراژ',type:'number'}]}],
  stages,tasks:[{id:'qa-task',projectId:'qa-project',boardId:'qa-board',listId:'planned',
    title:'کارت بررسی فشردگی',status:'planned',priority:'medium',description:'',
    labels:[],assignees:[],reports:[],costEnabled:true,cost:0,
    customFieldValues:{sku:'ABC-001',quantity:121},
    checklist:[{id:'step1',text:'مرحله اول',done:false,cost:0},
      {id:'step2',text:'مرحله دوم',done:false,cost:2300,costCategory:'پیک',costDate:'2026-10-20'}],
    createdAt:'2026-10-20T10:00:00.000Z',updatedAt:'2026-10-20T10:00:00.000Z'}],
  settings:{theme:'dark',costDefault:true}
};

async function freePort(){
  // Chromium blocks a set of local ports (including 1719) even though the
  // TCP listener is valid. Choose within a safe high range instead of the
  // OS-assigned ephemeral range, which may consist entirely of low ports.
  for(let attempt=0;attempt<40;attempt++){
    const port=20000+Math.floor(Math.random()*20000);
    try{
      await new Promise((resolve,reject)=>{
        const server=net.createServer();server.once('error',reject);
        server.listen(port,'127.0.0.1',()=>{
          server.close(error=>error?reject(error):resolve());
        });
      });
      return port;
    }catch(error){if(error.code!=='EADDRINUSE')throw error;}
  }
  throw new Error('Could not reserve a browser-safe test port');
}

test('full App card details keep checklist costs folded and board definitions separate at 1440/480',
  {skip:!available,timeout:100000},async()=>{
    const {createServer}=await import('vite');
    const {chromium}=require(playwrightHome);
    const server=await createServer({root,logLevel:'error',
      server:{host:'127.0.0.1',port:await freePort(),strictPort:true,hmr:false,
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
        const page=await context.newPage();
        const errors=[];page.on('pageerror',error=>errors.push(error.message));
        page.setDefaultTimeout(12000);
        try{
          await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
          await page.getByRole('button',{name:'نمای کلی',exact:true}).click();
          await page.locator('.vitrea-overview').waitFor({state:'visible'});
          await page.locator('.vitrea-overview-task').filter({hasText:'کارت بررسی فشردگی'}).first().click();
          const drawer=page.getByRole('dialog',{name:'جزئیات کار'});
          await drawer.waitFor({state:'visible'});
          // Board-level custom field definitions were intentionally moved under
          // per-card Settings to keep the primary task editor compact.
          assert.equal(await drawer.locator('#task-section-settings').count(),0,'settings hidden until requested');
          await drawer.locator('.task-quick-actions').getByRole('button',{name:'بیشتر'}).click();
          await drawer.locator('.task-more-menu').getByRole('button',{name:'تنظیمات پیشرفته'}).click();
          const taskSettings=drawer.locator('#task-section-settings');
          await taskSettings.waitFor({state:'visible'});
          const custom=drawer.locator('details.task-card-custom-fields');
          assert.notEqual(await custom.getAttribute('open'),null);
          assert.match(await custom.locator(':scope > summary').innerText(),/فیلدهای سفارشی/);
          assert.equal(await custom.getByRole('textbox',{name:'کد سفارش'}).inputValue(),'ABC-001');
          const definitions=custom.locator('details.task-board-field-settings');
          assert.equal(await definitions.getAttribute('open'),null);
          assert.equal(await definitions.getByRole('button',{name:'افزودن فیلد'}).count(),0);
          const color=await custom.locator('.cardextras-field label').first().evaluate(el=>getComputedStyle(el).color);
          assert.notEqual(color,'rgb(0, 0, 0)','dark field label must not inherit black');
          const directCost=drawer.locator('.task-direct-cost-fields');
          assert.equal(await directCost.evaluate(el=>getComputedStyle(el).display),'grid');
          assert.equal(await directCost.getByRole('textbox',{name:'هزینه مستقیم این کار'}).count(),1);
          const directColumns=await directCost.evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length);
          assert.equal(directColumns,width===480?2:3,'direct expense controls use a compact grid');
          const categoryBg=await directCost.locator('.expense-category-field input').evaluate(el=>getComputedStyle(el).backgroundColor);
          assert.notEqual(categoryBg,'rgb(255, 255, 255)','direct expense input must respect dark theme');
          const checklist=drawer.locator('#task-section-checklist');
          assert.equal(await checklist.isVisible(),true,'checklist shows without another accordion');
          const steps=drawer.locator('.task-compact-step');
          assert.equal(await steps.count(),2);
          assert.equal(await steps.locator('.task-checklist-item__panel').count(),0,'secondary fields start collapsed');
          assert.equal(await steps.getByRole('button',{name:'هزینه مرحله اول'}).count(),1);
          assert.equal(await steps.getByRole('button',{name:'زمان مرحله دوم'}).count(),1);
          const screenshotDir=path.join(root,'.qa-madar-card-density-20261028');
          fs.mkdirSync(screenshotDir,{recursive:true});
          await custom.scrollIntoViewIfNeeded();
          await page.screenshot({path:path.join(screenshotDir,'custom-fields-'+width+'.png')});
          await steps.first().scrollIntoViewIfNeeded();
          await page.screenshot({path:path.join(screenshotDir,'checklist-'+width+'.png')});
          assert.equal(await steps.first().getByRole('textbox',{name:'هزینه مرحله مرحله اول'}).count(),0);
          await steps.first().getByRole('button',{name:'هزینه مرحله اول'}).click();
          assert.equal(await steps.first().locator('.task-checklist-item__fields').evaluate(el=>getComputedStyle(el).display),'grid');
          assert.equal(await steps.first().getByRole('combobox',{name:'طرف حساب مرحله اول'}).isDisabled(),true,'unknown accounting connectivity must not invent party data');
          await definitions.locator(':scope > summary').click();
          assert.equal(await definitions.getByRole('button',{name:'افزودن فیلد'}).count(),1);
          const bounds=await drawer.boundingBox();
          assert.ok(bounds&&bounds.x>=-2&&bounds.x+bounds.width<=width+2,'drawer fits viewport '+width);
          assert.deepEqual(errors,[],width+'px page errors');
          console.log('Madar task compact full App '+width+'px: disclosures, values, costs, RTL, no pageerrors');
        }finally{await context.close();}
      }
    }finally{await browser?.close();await server.close();}
  });
