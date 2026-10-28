'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');

const chrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPath = 'C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable = fs.existsSync(chrome) && fs.existsSync(playwrightPath);
const root = path.resolve(__dirname, '..');

const stages = [
  {id:'original',label:'شروع',subtitle:'ستون نمونه',color:'#64748b'},
  {id:'next',label:'مرحله بعد',subtitle:'',color:'#3465a1'},
];
const task = (id,title,order,cost) => ({
  id,boardId:'board',projectId:'project',listId:'original',status:'original',
  title,description:'',priority:'medium',completed:false,cardOrder:order,
  dueDate:'',labels:[],checklist:[{id:id+'-step',text:'هزینه ثبت‌شده',done:false,cost:2400}],
  reports:[],cost,createdAt:'2026-10-20T12:00:00Z',updatedAt:'2026-10-20T12:00:00Z',
  accountingReference:'immutable-'+id,
});
const fixture = {
  version:1,
  projects:[{id:'project',name:'پروژه آزمایشی',color:'#657faa',costEnabled:false,price:0}],
  workspaces:[{id:'workspace',name:'فضای تست',archived:false}],
  boards:[{id:'board',workspaceId:'workspace',projectId:'project',
    name:'برد واقعی آزمون',archived:false,color:'#657faa',stages}],
  stages,
  tasks:[task('old-a','کارت اول',0,90000),task('old-b','کارت دوم',1,80000),task('old-c','کارت سوم',2,70000)],
  settings:{theme:'light',costDefault:false},
};

async function unusedPort(){
  return new Promise((resolve,reject)=>{
    const server = net.createServer();
    server.once('error',reject);
    server.listen(0,'127.0.0.1',()=>{
      const port=server.address().port;
      server.close(error=>error?reject(error):resolve(port));
    });
  });
}

async function storedState(page){
  return page.evaluate(()=>JSON.parse(localStorage.getItem('madar-preview')||'null'));
}

async function waitForCardsSaved(page,titles){
  await page.waitForFunction(expected=>{
    try {
      const state=JSON.parse(localStorage.getItem('madar-preview')||'null');
      return expected.every(title=>state?.tasks?.some(card=>card.title===title));
    }catch{return false;}
  },titles);
}

function financeSnapshot(state){
  return Object.fromEntries(state.tasks.filter(t=>t.id.startsWith('old-')).map(t=>[
    t.id,{cost:t.cost,checklist:t.checklist,accountingReference:t.accountingReference,
      status:t.status,listId:t.listId,boardId:t.boardId,projectId:t.projectId},
  ]));
}

async function titlesIn(lane){
  return lane.locator('.task-card .task-title').allTextContents();
}

async function addInline(lane,trigger,title){
  await trigger.click();
  const form=lane.getByRole('form',{name:'افزودن کارت به شروع'});
  await form.waitFor({state:'visible'});
  assert.equal(await lane.getByRole('dialog',{name:'ایجاد کار جدید'}).count(),0);
  await form.getByRole('textbox',{name:'عنوان کارت جدید'}).fill(title);
  await form.getByRole('button',{name:'افزودن کارت',exact:true}).click();
  await lane.getByRole('button',{name:'جزئیات '+title}).waitFor({state:'visible'});
}

test('Trello list controls: right-click, completion, insert positions, collapse and RTL persist safely',
  {skip:!runnable,timeout:90000},async()=>{
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    // Dev Vite serves the current JSX in this shared working tree; preview()
    // would instead exercise a potentially stale dist/ from another task.
    const server=await createServer({root,logLevel:'error',
      server:{host:'127.0.0.1',port:await unusedPort(),strictPort:true,hmr:false,
        // Native WebView2 QA profiles may live under this repository and
        // Windows locks their cookie journals. They are not Vite source.
        watch:{ignored:['**/.qa-*','**/.qa-*/**','**/WebView2/**','**/research/**']}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR'});
      await context.addInitScript(data=>{
        if(!localStorage.getItem('madar-preview')){
          localStorage.setItem('madar-preview',JSON.stringify(data));
        }
        localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      },fixture);
      const page=await context.newPage();
      page.setDefaultTimeout(10000);
      const errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await page.locator('.vitrea-overview').waitFor({state:'visible'});
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
        .getByRole('button',{name:'برد کارها'}).click();
      await page.getByRole('heading',{name:'برد واقعی آزمون'}).waitFor();
      const lane=page.locator('.kanban-lane[aria-label="ستون شروع"]');
      const other=page.locator('.kanban-lane[aria-label="ستون مرحله بعد"]');
      assert.deepEqual(await titlesIn(lane),['کارت اول','کارت دوم','کارت سوم']);
      assert.equal(await page.locator('.kanban-lane').count(),2);

      // Completion is independent of list/status and survives a full reload.
      const first=lane.locator('[data-progressive-card-id="old-a"]');
      const toggle=first.locator('.task-complete-toggle');
      assert.equal(await toggle.getAttribute('aria-pressed'),'false');
      await toggle.click();
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')||'{}')
        .tasks?.find(t=>t.id==='old-a')?.completed===true);
      assert.equal(await first.locator('.task-card--completed').count(),1);
      await page.reload({waitUntil:'domcontentloaded'});
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
        .getByRole('button',{name:'برد کارها'}).click();
      await page.getByRole('heading',{name:'برد واقعی آزمون'}).waitFor();
      assert.equal(await lane.locator('[data-progressive-card-id="old-a"] .task-complete-toggle')
        .getAttribute('aria-pressed'),'true');
      await lane.locator('[data-progressive-card-id="old-a"] .task-complete-toggle').click();
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')||'{}')
        .tasks?.find(t=>t.id==='old-a')?.completed===false);

      // The same quick composer is used for all three insertion locations.
      await addInline(lane,lane.getByRole('button',{name:'افزودن کارت در ابتدای شروع'}),'کارت ابتدا');
      assert.deepEqual(await titlesIn(lane),['کارت ابتدا','کارت اول','کارت دوم','کارت سوم']);
      await addInline(lane,lane.getByRole('button',{name:'افزودن کارت پیش از کارت دوم'}),'کارت میانی');
      assert.deepEqual(await titlesIn(lane),['کارت ابتدا','کارت اول','کارت میانی','کارت دوم','کارت سوم']);
      await addInline(lane,lane.locator('.lane-add-card'),'کارت انتها');
      const expected=['کارت ابتدا','کارت اول','کارت میانی','کارت دوم','کارت سوم','کارت انتها'];
      assert.deepEqual(await titlesIn(lane),expected);
      await waitForCardsSaved(page,['کارت ابتدا','کارت میانی','کارت انتها']);

      // A collapsed lane becomes narrow, its neighbor remains expanded, and
      // the collapsed lane can be restored without losing any cards.
      const wide=await lane.evaluate(el=>el.getBoundingClientRect().width);
      await lane.locator('.lane-collapse-toggle').click();
      assert.equal(await lane.evaluate(el=>el.classList.contains('kanban-lane--collapsed')),true);
      assert.ok((await lane.evaluate(el=>el.getBoundingClientRect().width))<wide);
      assert.equal(await other.evaluate(el=>el.classList.contains('kanban-lane--collapsed')),false);
      assert.equal(await lane.locator('.task-card').first().isVisible(),false);
      await lane.locator('.lane-expand-control').click();
      assert.equal(await lane.evaluate(el=>el.classList.contains('kanban-lane--collapsed')),false);
      assert.deepEqual(await titlesIn(lane),expected);

      const rtl=await page.evaluate(()=>{
        const board=document.querySelector('.kanban');
        const lanes=[...board.querySelectorAll('.kanban-lane')];
        return {direction:getComputedStyle(board).direction,
          firstX:lanes[0].getBoundingClientRect().x,
          secondX:lanes[1].getBoundingClientRect().x};
      });
      assert.equal(rtl.direction,'rtl');
      assert.ok(rtl.firstX>rtl.secondX,JSON.stringify(rtl));
      await page.setViewportSize({width:480,height:800});
      const mobile=await page.evaluate(()=>{
        const board=document.querySelector('.kanban');
        return {direction:getComputedStyle(board).direction,
          viewport:innerWidth,body:document.documentElement.scrollWidth,
          boardWidth:board.clientWidth,boardScrollWidth:board.scrollWidth};
      });
      assert.equal(mobile.direction,'rtl');
      assert.ok(mobile.body<=mobile.viewport+2,JSON.stringify(mobile));
      assert.ok(mobile.boardScrollWidth>mobile.boardWidth,JSON.stringify(mobile));

      // Reload validates persisted card order and invariance of existing
      // finance metadata in the isolated test state, not a real ledger.
      const before=financeSnapshot(fixture);
      const after=await storedState(page);
      assert.deepEqual(financeSnapshot(after),before);
      assert.equal(after.tasks.find(t=>t.id==='old-a').completed,false);
      assert.ok(after.tasks.filter(t=>t.boardId==='board'&&t.listId==='original')
        .every(t=>Number.isInteger(t.cardOrder)));
      await page.reload({waitUntil:'domcontentloaded'});
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
        .getByRole('button',{name:'برد کارها'}).click();
      await page.getByRole('heading',{name:'برد واقعی آزمون'}).waitFor();
      assert.deepEqual(await titlesIn(lane),expected);
      assert.deepEqual(financeSnapshot(await storedState(page)),before);

      // Right click the list itself, without touching the ellipsis button.
      // Check this after the persistence flow so a context-menu regression
      // cannot mask otherwise independent card-insertion evidence.
      await page.setViewportSize({width:1440,height:900});
      await lane.locator('.lane-head').click({button:'right'});
      const menu=page.getByRole('dialog',{name:'تنظیمات ستون شروع'});
      await menu.waitFor({state:'visible'});
      assert.equal(await menu.getByText('عملیات ستون').count(),1);
      await menu.getByRole('button',{name:'کپی ستون خالی'}).click();
      assert.equal(await menu.count(),0);
      const copied=page.locator('.kanban-lane[aria-label="ستون شروع (کپی)"]');
      await copied.waitFor({state:'visible'});
      assert.equal(await copied.locator('.task-card').count(),0);
      assert.deepEqual(await titlesIn(lane),expected);
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')||'{}')
        .boards?.find(b=>b.id==='board')?.stages?.some(s=>s.label==='شروع (کپی)'));
      assert.deepEqual(financeSnapshot(await storedState(page)),before);
      assert.deepEqual(errors,[]);
    }finally{
      await browser?.close();
      await server.close();
    }
  });
