'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const net=require('node:net');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);
const root=path.resolve(__dirname,'..');
const stage=(id,label)=>({id,label,color:'#64748b',subtitle:''});
const original=stage('original','شروع');
const fixture={
  version:1,projects:[{id:'project',name:'پروژه آزمایشی',color:'#657faa',costEnabled:false,price:0}],
  workspaces:[{id:'workspace',name:'فضای تست',archived:false}],
  boards:[{id:'board',workspaceId:'workspace',projectId:'project',name:'برد واقعی آزمون',
    archived:false,color:'#657faa',stages:[original]}],stages:[original],
  tasks:[{id:'existing',boardId:'board',projectId:'project',listId:'original',status:'original',
    title:'کارت حفظ‌شده',description:'',priority:'medium',dueDate:'',labels:[],checklist:[],
    reports:[],cost:90000,createdAt:'2026-10-20T12:00:00Z',updatedAt:'2026-10-20T12:00:00Z'}],
  settings:{theme:'light',costDefault:false},
};
async function freePort(){return new Promise((resolve,reject)=>{
  const s=net.createServer();s.once('error',reject);s.listen(0,'127.0.0.1',()=>{
    const port=s.address().port;s.close(e=>e?reject(e):resolve(port));
  });
});}
test('Trello board opens and stage added in settings/board appears in live card dropdown, without changing old card',
  {skip:!runnable,timeout:60000},async()=>{
    const {preview}=await import('vite');
    const {chromium}=require(playwrightHome);
    const server=await preview({root,logLevel:'error',preview:{host:'127.0.0.1',port:await freePort(),strictPort:true}});
    let browser;
    try{
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const ctx=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR'});
      const page=await ctx.newPage();page.setDefaultTimeout(7000);
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.addInitScript(data=>localStorage.setItem('madar-preview',JSON.stringify(data)),fixture);
      await page.goto(new URL('index.html',server.resolvedUrls.local[0]).href,{waitUntil:'domcontentloaded'});
      await page.locator('.vitrea-overview').waitFor({state:'visible'});

      // Legacy/global stage settings remain compatible with real boards.
      await page.getByRole('button',{name:'تنظیمات مدار'}).click();
      const settings=page.getByRole('dialog',{name:'تنظیمات مدار'});
      await settings.getByText('مدیریت ستون‌ها و مراحل برد').click();
      await settings.getByRole('textbox',{name:'نام ستون جدید'}).fill('ستون عمومی تازه');
      await settings.getByRole('button',{name:'افزودن ستون'}).click();
      await settings.getByRole('button',{name:'بستن'}).click();

      // Top Board button cannot silently leave us in aggregate Overview.
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'}).getByRole('button',{name:'برد کارها'}).click();
      await page.getByRole('heading',{name:'برد واقعی آزمون'}).waitFor();
      assert.equal(await page.locator('.kanban-lane').count(),2);
      const globalLane=page.locator('.kanban-lane').filter({hasText:'ستون عمومی تازه'});
      await globalLane.locator('.lane-add-card').click();
      const create=page.getByRole('dialog',{name:'ایجاد کار جدید'});
      const options=await create.locator('select').filter({has:page.locator('option',{hasText:'ستون عمومی تازه'})}).locator('option').allTextContents();
      assert.ok(options.includes('ستون عمومی تازه'),JSON.stringify(options));
      await create.getByRole('textbox',{name:'عنوان کار'}).fill('کارت ستون جدید');
      await create.getByRole('button',{name:'ایجاد کار'}).click();
      await page.getByRole('dialog',{name:'جزئیات کار'}).waitFor();
      await page.getByRole('button',{name:'بستن'}).last().click();
      await page.waitForFunction(()=>{
        const state=JSON.parse(localStorage.getItem('madar-preview')||'{}');
        return state.tasks?.some(t=>t.title==='کارت ستون جدید');
      });
      const after=await page.evaluate(()=>JSON.parse(localStorage.getItem('madar-preview')));
      const newStage=after.boards[0].stages.find(s=>s.label==='ستون عمومی تازه');
      assert.ok(newStage);
      assert.equal(after.tasks.find(t=>t.title==='کارت ستون جدید')?.listId,newStage.id);
      assert.equal(after.tasks.find(t=>t.id==='existing')?.cost,90000);
      assert.equal(after.tasks.find(t=>t.id==='existing')?.listId,'original');

      // A second column created directly on board also appears immediately.
      await page.getByRole('button',{name:'افزودن یک لیست دیگر'}).click();
      await page.getByRole('textbox',{name:'نام ستون جدید'}).fill('ستون مستقل');
      await page.getByRole('button',{name:'افزودن لیست',exact:true}).click();
      const directLane=page.locator('.kanban-lane').filter({hasText:'ستون مستقل'});
      await directLane.locator('.lane-add-card').click();
      const updatedOptions=await page.getByRole('dialog',{name:'ایجاد کار جدید'}).locator('select')
        .filter({has:page.locator('option',{hasText:'ستون مستقل'})}).locator('option').allTextContents();
      assert.ok(updatedOptions.includes('ستون مستقل'));
      assert.deepEqual(errors,[]);
    }finally{await browser?.close();await server.httpServer.close();}
  });
