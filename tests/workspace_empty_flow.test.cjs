'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPath='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable=fs.existsSync(chrome)&&fs.existsSync(playwrightPath);
const root=path.resolve(__dirname,'..');
const firstStage={id:'inbox',label:'صندوق ورودی',subtitle:'جدید',color:'#64748b'};
const seed={
  version:1,workspaces:[{id:'old-w',name:'فضای اولیه',archived:false},
    {id:'empty-w',name:'فضای جدید',archived:false}],
  projects:[{id:'existing-project',name:'پروژه موجود',costEnabled:true,price:245000}],
  boards:[{id:'existing-board',workspaceId:'old-w',projectId:'existing-project',
    name:'برد اصلی',archived:false,stages:[firstStage]}],
  stages:[firstStage],tasks:[{id:'valuable-task',title:'کار مالی قبلی',projectId:'existing-project',
    boardId:'existing-board',listId:'inbox',status:'inbox',cost:120500,description:'',
    priority:'medium',dueDate:'',labels:[],checklist:[],reports:[],createdAt:'2026-10-01T08:00:00Z',
    updatedAt:'2026-10-01T08:00:00Z'}],
  settings:{theme:'dark',costDefault:false},
};
async function freePort(){return new Promise((resolve,reject)=>{
  const socket=net.createServer();socket.on('error',reject);
  socket.listen(0,'127.0.0.1',()=>{const port=socket.address().port;
    socket.close(err=>err?reject(err):resolve(port));});
});}
test('empty workspace explicitly offers projects, never opens card dialog without a board, and preserves old financial cards',
  {skip:!runnable,timeout:60000},async()=>{
    const {preview}=await import('vite');
    const {chromium}=require(playwrightPath);
    const server=await preview({root,logLevel:'error',preview:{host:'127.0.0.1',port:await freePort(),strictPort:true}});
    let browser;
    try{
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1280,height:860},locale:'fa-IR'});
      const page=await context.newPage();page.setDefaultTimeout(7000);
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.addInitScript(data=>localStorage.setItem('madar-preview',JSON.stringify(data)),seed);
      await page.goto(new URL('index.html',server.resolvedUrls.local[0]).href,{waitUntil:'domcontentloaded'});
      await page.locator('.vitrea-primary-nav button').first().click();
      await page.locator('.vitrea-overview').waitFor({state:'visible'});
      await page.getByRole('button',{name:'نمایش منوی کامل مدار'}).click();
      const select=page.getByRole('combobox',{name:'انتخاب فضای کاری'});
      await select.selectOption('empty-w');
      const empty=page.getByRole('region',{name:'راه‌اندازی برد فضای کاری'});
      await empty.waitFor({state:'visible'});
      assert.equal(await page.locator('.kanban-lane').count(),0);
      assert.equal(await page.getByRole('dialog',{name:'ایجاد کار جدید'}).count(),0);
      await empty.getByRole('combobox',{name:'پروژه موجود'}).selectOption('existing-project');
      await empty.getByRole('button',{name:'ساخت برد در این فضا'}).click();
      await page.getByRole('heading',{name:'پروژه موجود'}).waitFor();
      assert.equal(await page.locator('.kanban-lane').count(),1);
      await page.locator('.kanban-lane .lane-add-card').click();
      const composer=page.locator('.kanban-lane .lane-quick-add');
      assert.equal(await page.getByRole('dialog',{name:'ایجاد کار جدید'}).count(),0);
      await composer.getByRole('textbox',{name:'عنوان کارت جدید'}).fill('کارت جدید در فضای جدید');
      await composer.getByRole('button',{name:'افزودن کارت',exact:true}).click();
      await page.getByRole('button',{name:'جزئیات کارت جدید در فضای جدید'}).waitFor();
      await page.getByRole('button',{name:'جزئیات کارت جدید در فضای جدید'}).click();
      await page.getByRole('dialog',{name:'جزئیات کار'}).waitFor();
      await page.getByRole('button',{name:'بستن'}).last().click();
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')||'{}')
        .tasks?.some(task=>task.title==='کارت جدید در فضای جدید'));
      const after=await page.evaluate(()=>JSON.parse(localStorage.getItem('madar-preview')));
      const createdBoard=after.boards.find(board=>board.workspaceId==='empty-w');
      assert.ok(createdBoard);
      assert.equal(createdBoard.projectId,'existing-project');
      const card=after.tasks.find(item=>item.title==='کارت جدید در فضای جدید');
      assert.equal(card.boardId,createdBoard.id);
      assert.equal(after.tasks.find(item=>item.id==='valuable-task').boardId,'existing-board');
      assert.equal(after.tasks.find(item=>item.id==='valuable-task').cost,120500);
      assert.equal(after.projects[0].price,245000);
      assert.deepEqual(errors,[]);
    }finally{await browser?.close();await server.httpServer.close();}
  });
