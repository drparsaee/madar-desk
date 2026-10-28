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
test('Trello board opens and stage added from the board appears in live card dropdown, without changing old card',
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

      // Global stage management is intentionally retired; lanes belong to
      // their own board, exactly like Trello.
      await page.getByRole('button',{name:'تنظیمات مدار'}).click();
      const settings=page.getByRole('dialog',{name:'تنظیمات مدار'});
      assert.equal(await settings.getByText('مدیریت ستون‌ها و مراحل برد').count(),0);
      await settings.getByRole('button',{name:'بستن'}).click();

      // Top Board button cannot silently leave us in aggregate Overview.
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'}).getByRole('button',{name:'برد کارها'}).click();
      await page.getByRole('heading',{name:'برد واقعی آزمون'}).waitFor();
      await page.getByRole('button',{name:'افزودن یک لیست دیگر'}).click();
      await page.getByRole('textbox',{name:'نام ستون جدید'}).fill('ستون عمومی تازه');
      await page.getByRole('button',{name:'افزودن لیست',exact:true}).click();
      assert.equal(await page.locator('.kanban-lane').count(),2);
      const globalLane=page.locator('.kanban-lane').filter({hasText:'ستون عمومی تازه'});
      await globalLane.locator('.lane-add-card').click();
      const compose=globalLane.getByRole('form',{name:'افزودن کارت به ستون عمومی تازه'});
      await compose.getByRole('textbox',{name:'عنوان کارت جدید'}).fill('کارت ستون جدید');
      assert.equal(await page.getByRole('dialog',{name:'ایجاد کار جدید'}).count(),0);
      await compose.getByRole('button',{name:'افزودن کارت',exact:true}).click();
      const newCard=globalLane.getByRole('button',{name:'جزئیات کارت ستون جدید'});
      await newCard.waitFor({state:'visible'});
      assert.equal(await page.getByRole('dialog',{name:'جزئیات کار'}).count(),0);
      await newCard.click();
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
      assert.equal(await directLane.getByRole('form',{name:'افزودن کارت به ستون مستقل'}).count(),1);
      await directLane.getByRole('button',{name:'بستن افزودن کارت'}).click();
      assert.equal(await directLane.locator('form.lane-quick-add').count(),0);
      // Keyboard-only Trello flow: Enter creates, but never launches the
      // full editor; details are available only when the card is opened.
      await directLane.locator('.lane-add-card').click();
      const title=directLane.getByRole('textbox',{name:'عنوان کارت جدید'});
      await title.fill('کارت با صفحه‌کلید');
      await title.press('Enter');
      const keyboardCard=directLane.getByRole('button',{name:'جزئیات کارت با صفحه‌کلید'});
      await keyboardCard.waitFor({state:'visible'});
      assert.equal(await page.locator('.drawer[role=dialog]').count(),0);
      await keyboardCard.click();
      await page.getByRole('dialog',{name:'جزئیات کار'}).waitFor();
      assert.deepEqual(errors,[]);
    }finally{await browser?.close();await server.httpServer.close();}
  });
