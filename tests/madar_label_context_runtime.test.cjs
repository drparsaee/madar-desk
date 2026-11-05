'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const net=require('node:net');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);
const stage={id:'todo',label:'انجام',color:'#4568a3',subtitle:''};
const date='2026-10-20T12:00:00Z';
const makeTask=(id,title,labels)=>({id,title,boardId:'b',projectId:'p',listId:'todo',status:'todo',
  labels,description:'',priority:'medium',checklist:[],reports:[],dueDate:'',
  createdAt:date,updatedAt:date});
const fixture={version:1,
  projects:[{id:'p',name:'پروژهٔ تست',color:'#5379be',costEnabled:false,price:0}],
  workspaces:[{id:'w',name:'فضای تست',archived:false}],
  boards:[{id:'b',workspaceId:'w',projectId:'p',name:'برچسب‌ها در برد',archived:false,stages:[stage]}],
  stages:[stage],tasks:[makeTask('a','کارت اول',['Done']),
    makeTask('b','کارت دوم',['Done']),makeTask('c','کارت سوم',[])],
  settings:{theme:'dark',costDefault:false,labelLibrary:[{id:'global-done',name:'Done',color:'#4bce97'}]}};
const freePort=()=>new Promise((resolve,reject)=>{
  const server=net.createServer();server.once('error',reject);
  server.listen(0,'127.0.0.1',()=>{
    const port=server.address().port;
    server.close(error=>error?reject(error):resolve(port));
  });
});

test('right-clicking a board label edits its shared definition; global deletion removes all assignments',
  {skip:!runnable,timeout:75000},async()=>{
    const {createServer}=await import('vite');
    const {chromium}=require(playwrightHome);
    const server=await createServer({root,logLevel:'error',server:{host:'127.0.0.1',
      port:await freePort(),strictPort:true,hmr:false}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const page=await browser.newPage({viewport:{width:1440,height:900},locale:'fa-IR'});
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.addInitScript(data=>localStorage.setItem('madar-preview',JSON.stringify(data)),fixture);
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      const board=page.locator('.kanban-lane').first();
      await board.locator('.task-card').first().waitFor({state:'visible'});
      await board.locator('.task-label-context-trigger').first().click({button:'right'});
      const dialog=page.getByRole('dialog',{name:'مدیریت برچسب‌ها'});
      await dialog.waitFor();
      assert.equal(await dialog.locator('.label-editor-palette-color').count(),30);
      await dialog.getByRole('textbox',{name:'نام جدید برچسب Done'}).fill('Complete');
      await dialog.locator('.label-editor-palette-color').nth(12).click();
      await dialog.getByRole('button',{name:'ذخیره',exact:true}).click();
      await page.waitForFunction(()=>{
        const state=JSON.parse(localStorage.getItem('madar-preview')||'{}');
        return state.tasks?.filter(card=>card.labels?.includes('Complete')).length===2;
      });
      let state=await page.evaluate(()=>JSON.parse(localStorage.getItem('madar-preview')));
      assert.deepEqual(state.tasks.map(task=>task.labels),[['Complete'],['Complete'],[]]);
      assert.equal(state.settings.labelLibrary[0].name,'Complete');
      assert.notEqual(state.settings.labelLibrary[0].color,'#4bce97');

      await dialog.getByRole('button',{name:'بستن مدیریت برچسب‌ها'}).click();
      await page.locator('.vitrea-quickdock__main').click();
      const sidebar=page.locator('#madar-sidebar');
      await sidebar.getByRole('button',{name:'مدیریت برچسب‌ها'}).click();
      await dialog.getByRole('button',{name:'ویرایش برچسب Complete'}).click();
      await dialog.getByRole('button',{name:'حذف برچسب'}).click();
      await dialog.getByRole('button',{name:'حذف از همهٔ کارت‌ها'}).click();
      await page.waitForFunction(()=>{
        const state=JSON.parse(localStorage.getItem('madar-preview')||'{}');
        return state.tasks?.every(card=>(card.labels||[]).length===0)&&
          state.settings.labelLibrary?.length===0;
      });
      state=await page.evaluate(()=>JSON.parse(localStorage.getItem('madar-preview')));
      assert.ok(state.tasks.every(card=>card.labels.length===0));
      assert.equal(state.settings.labelLibrary.length,0);
      assert.deepEqual(errors,[]);
    }finally{
      await browser?.close();
      await server.close();
    }
  });
