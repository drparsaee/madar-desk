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

async function addInline(page,lane,trigger,title){
  await trigger.click();
  const form=lane.getByRole('form',{name:'افزودن کارت به شروع'});
  await form.waitFor({state:'visible'});
  assert.equal(await lane.getByRole('dialog',{name:'ایجاد کار جدید'}).count(),0);
  await form.getByRole('textbox',{name:'عنوان کارت جدید'}).fill(title);
  await form.getByRole('button',{name:'افزودن کارت',exact:true}).click();
  await lane.getByRole('button',{name:'جزئیات '+title}).waitFor({state:'visible'});
  // React's optimistic card is not durable until the host/local save succeeds.
  await waitForCardsSaved(page,[title]);
  await form.waitFor({state:'detached'});
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
    const evidenceDir=process.env.MADAR_BOARD_UX_EVIDENCE_DIR;
    if(evidenceDir)fs.mkdirSync(evidenceDir,{recursive:true});
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
      await page.locator('.vitrea-primary-nav button').first().click();
      await page.locator('.vitrea-overview').waitFor({state:'visible'});
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
        .getByRole('button',{name:'برد کارها'}).click();
      await page.getByRole('heading',{name:'برد واقعی آزمون'}).waitFor();
      if(evidenceDir)await page.screenshot({path:path.join(evidenceDir,
        'board-before-1440.png'),fullPage:false});
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
      await addInline(page,lane,lane.getByRole('button',{name:'افزودن کارت در ابتدای شروع'}),'کارت ابتدا');
      assert.deepEqual(await titlesIn(lane),['کارت ابتدا','کارت اول','کارت دوم','کارت سوم']);
      await addInline(page,lane,lane.getByRole('button',{name:'افزودن کارت پیش از کارت دوم'}),'کارت میانی');
      assert.deepEqual(await titlesIn(lane),['کارت ابتدا','کارت اول','کارت میانی','کارت دوم','کارت سوم']);
      await addInline(page,lane,lane.locator('.lane-add-card'),'کارت انتها');
      const expected=['کارت ابتدا','کارت اول','کارت میانی','کارت دوم','کارت سوم','کارت انتها'];
      assert.deepEqual(await titlesIn(lane),expected);
      await waitForCardsSaved(page,['کارت ابتدا','کارت میانی','کارت انتها']);
      if(evidenceDir)await page.screenshot({path:path.join(evidenceDir,
        'board-after-1440.png'),fullPage:false});

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
      await page.evaluate(()=>{
        window.scrollTo(0,0);
        document.querySelector('.workspace-scroll')?.scrollTo({top:0,behavior:'instant'});
      });
      const mobile=await page.evaluate(()=>{
        const board=document.querySelector('.kanban');
        return {direction:getComputedStyle(board).direction,
          viewport:innerWidth,body:document.documentElement.scrollWidth,
          boardWidth:board.clientWidth,boardScrollWidth:board.scrollWidth};
      });
      assert.equal(mobile.direction,'rtl');
      assert.ok(mobile.body<=mobile.viewport+2,JSON.stringify(mobile));
      assert.ok(mobile.boardScrollWidth>mobile.boardWidth,JSON.stringify(mobile));
      const mobileBoardTop=await page.locator('.kanban').evaluate(node=>
        Math.round(node.getBoundingClientRect().top));
      assert.ok(mobileBoardTop>=0&&mobileBoardTop<=600,
        'Mobile board content must be visible before the bottom dock, not buried beneath toolbars: '+mobileBoardTop);
      if(evidenceDir)await page.screenshot({path:path.join(evidenceDir,
        'board-mobile-480.png'),fullPage:false});
      await page.setViewportSize({width:390,height:800});
      await page.evaluate(()=>{
        window.scrollTo(0,0);
        document.querySelector('.workspace-scroll')?.scrollTo({top:0,behavior:'instant'});
      });
      const narrow=await page.evaluate(()=>{
        const board=document.querySelector('.kanban');
        return {viewport:innerWidth,docWidth:document.documentElement.scrollWidth,
          boardTop:Math.round(board.getBoundingClientRect().top)};
      });
      assert.ok(narrow.docWidth<=narrow.viewport+2,JSON.stringify(narrow));
      assert.ok(narrow.boardTop>=0&&narrow.boardTop<=620,
        '390px first-screen board access: '+JSON.stringify(narrow));
      const advancedToggle=page.locator('.board-toolbar .filter-toggle');
      assert.equal(await advancedToggle.getAttribute('aria-label'),'فیلترهای پیشرفته');
      await advancedToggle.click();
      await page.locator('.board-toolbar .filter-popover').waitFor({state:'visible'});
      await page.locator('.board-toolbar .filter-header button[aria-label="بستن"]').click();
      const listTab=page.locator('.board-toolbar .board-tabs button[aria-label="فهرست"]');
      await listTab.click();
      assert.equal(await page.locator('.list-mode').isVisible(),true);
      await page.locator('.board-toolbar .board-tabs button[aria-label="برد کارها"]').click();
      assert.equal(await page.locator('.kanban').isVisible(),true);

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
      assert.equal(await menu.getByText('عملیات لیست · شروع').count(),1);
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

test('quick-add refuses false success when a visible legacy card has an invalid ordering ID',
  {skip:!runnable,timeout:60000},async()=>{
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',
      server:{host:'127.0.0.1',port:await unusedPort(),strictPort:true,hmr:false,
        watch:{ignored:['**/.qa-*','**/WebView2/**','**/research/**']}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1440,height:900},
        locale:'fa-IR',reducedMotion:'reduce'});
      const legacy={...task('legacy','کارت میراثی',3,55000),id:'',
        accountingReference:'immutable-legacy',checklist:[
          {id:'legacy-step',text:'سابقه مالی بدون تغییر',done:true,cost:2400}]};
      const baseline={...fixture,tasks:[...fixture.tasks,legacy]};
      await context.addInitScript(data=>{
        if(!localStorage.getItem('madar-preview'))
          localStorage.setItem('madar-preview',JSON.stringify(data));
        localStorage.setItem('madar-preferences',
          JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      },baseline);
      const page=await context.newPage();
      page.setDefaultTimeout(12000);
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
        .getByRole('button',{name:'برد کارها'}).click();
      await page.getByRole('heading',{name:'برد واقعی آزمون'}).waitFor();
      const lane=page.locator('.kanban-lane[aria-label="ستون شروع"]');
      assert.ok((await titlesIn(lane)).includes('کارت میراثی'),
        'Host-valid legacy card remains visible rather than being discarded');
      await lane.locator('.lane-add-card').click();
      const form=lane.getByRole('form',{name:'افزودن کارت به شروع'});
      const editor=form.getByRole('textbox',{name:'عنوان کارت جدید'});
      await editor.fill('کارت با عنوان حفظ‌شده');
      await form.getByRole('button',{name:'افزودن کارت',exact:true}).click();
      await form.getByRole('alert').waitFor({state:'visible'});
      assert.match(await form.getByRole('alert').innerText(),/ثبت کارت|عنوان شما حفظ شد/);
      assert.equal(await editor.inputValue(),'کارت با عنوان حفظ‌شده');
      assert.equal((await titlesIn(lane)).includes('کارت با عنوان حفظ‌شده'),false,
        'Rejected creation must not render a phantom card');
      const after=await storedState(page);
      assert.equal(after.tasks.length,baseline.tasks.length);
      assert.deepEqual(after.tasks.find(item=>item.id===''),legacy,
        'Legacy card and its financial metadata must remain unmodified');
      assert.deepEqual(financeSnapshot(after),financeSnapshot(baseline));
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('quick-add never claims durable success if isolated host save rejects',
  {skip:!runnable,timeout:60000},async()=>{
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',server:{
      host:'127.0.0.1',port:await unusedPort(),strictPort:true,hmr:false,
      watch:{ignored:['**/.qa-*','**/WebView2/**','**/research/**']}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR'});
      await context.addInitScript(data=>{
        if(!localStorage.getItem('madar-preview'))
          localStorage.setItem('madar-preview',JSON.stringify(data));
        const write=Storage.prototype.setItem;
        Storage.prototype.setItem=function(key,value){
          if(key==='madar-preview')throw Error('Synthetic host rejected save');
          return write.call(this,key,value);
        };
        localStorage.setItem('madar-preferences',
          JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      },fixture);
      const page=await context.newPage();
      page.setDefaultTimeout(14000);
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
        .getByRole('button',{name:'برد کارها'}).click();
      const lane=page.locator('.kanban-lane[aria-label="ستون شروع"]');
      await lane.locator('.lane-add-card').click();
      const form=lane.getByRole('form',{name:'افزودن کارت به شروع'});
      const editor=form.getByRole('textbox',{name:'عنوان کارت جدید'});
      await editor.fill('کارت با ذخیره ناموفق');
      await form.getByRole('button',{name:'افزودن کارت',exact:true}).click();
      await form.getByRole('alert').waitFor({state:'visible'});
      assert.match(await form.getByRole('alert').innerText(),/ذخیره کارت رد شد/);
      assert.equal(await editor.inputValue(),'کارت با ذخیره ناموفق');
      assert.equal(await form.getByRole('button',{name:'ذخیره متوقف شد'}).isDisabled(),true);
      assert.equal(await form.getByRole('button',{name:'بستن افزودن کارت'}).isEnabled(),true,
        'A failed save must not keep the composer permanently stuck in pending');
      const durable=await storedState(page);
      assert.equal(durable.tasks.some(t=>t.title==='کارت با ذخیره ناموفق'),false,
        'Never confuse a staged React card with a host-persisted record');
      const recovery=await page.evaluate(()=>
        JSON.parse(localStorage.getItem('madar-unsaved-recovery')||'null'));
      assert.ok(recovery?.tasks?.some(t=>t.title==='کارت با ذخیره ناموفق'),
        'Keep a recovery snapshot instead of silently discarding a rejected card');
      assert.equal(await page.getByText('کارت ذخیره شد؛ برای تکمیل جزئیات روی آن کلیک کنید.').count(),0);
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('quick-add distinguishes a queued offline client save from host acknowledgment',
  {skip:!runnable,timeout:60000},async()=>{
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',server:{
      host:'127.0.0.1',port:await unusedPort(),strictPort:true,hmr:false,
      watch:{ignored:['**/.qa-*','**/WebView2/**','**/research/**']}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR'});
      await context.addInitScript(data=>{
        localStorage.setItem('madar-preview',JSON.stringify(data));
        const read=()=>JSON.parse(localStorage.getItem('madar-preview'));
        window.madar={
          getState:async()=>read(),getStateForUi:async()=>read(),
          saveState:async state=>{
            localStorage.setItem('madar-preview',JSON.stringify(state));
            return {revision:'qa-offline',offline:true};
          },
          lanStatus:async()=>({mode:'client',user:{username:'qa-editor',role:'editor',projects:null}}),
          lanProfiles:async()=>[],getPreferences:async()=>({calendar:'jalali',clockWidget:'hidden'}),
          syncStatus:async()=>({}),releaseCheck:async()=>({available:false}),
        };
      },fixture);
      const page=await context.newPage();
      page.setDefaultTimeout(15000);
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
        .getByRole('button',{name:'برد کارها'}).click();
      const lane=page.locator('.kanban-lane[aria-label="ستون شروع"]');
      await lane.locator('.lane-add-card').click();
      const form=lane.getByRole('form',{name:'افزودن کارت به شروع'});
      await form.getByRole('textbox',{name:'عنوان کارت جدید'}).fill('کارت در صف آفلاین');
      await form.getByRole('button',{name:'افزودن کارت',exact:true}).click();
      await page.getByText('کارت در صف آفلاین ثبت شد؛ تأیید میزبان هنوز دریافت نشده است.')
        .waitFor({state:'visible'});
      assert.ok((await storedState(page)).tasks.some(t=>t.title==='کارت در صف آفلاین'));
      assert.equal(await page.getByText('کارت ذخیره شد؛ برای تکمیل جزئیات روی آن کلیک کنید.').count(),0,
        'Offline:true must never claim host acknowledged the write');
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('quick-add warns when both host save and browser recovery storage fail',
  {skip:!runnable,timeout:60000},async()=>{
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',server:{
      host:'127.0.0.1',port:await unusedPort(),strictPort:true,hmr:false,
      watch:{ignored:['**/.qa-*','**/WebView2/**','**/research/**']}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR'});
      await context.addInitScript(data=>{
        localStorage.setItem('madar-preview',JSON.stringify(data));
        localStorage.setItem('madar-unsaved-recovery',JSON.stringify({
          ...data,tasks:[...data.tasks,{id:'prior-stale-recovery',title:'نسخه قبلی نامعتبر'}],
        }));
        const objectUrl=URL.createObjectURL.bind(URL);
        URL.createObjectURL=function(blob){window.__lastRecoveryDownload=blob;return objectUrl(blob);};
        const original=Storage.prototype.setItem;
        Storage.prototype.setItem=function(key,value){
          if(key==='madar-preview'||key==='madar-unsaved-recovery')
            throw Error('Synthetic storage unavailable');
          return original.call(this,key,value);
        };
        localStorage.setItem('madar-preferences',
          JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      },fixture);
      const page=await context.newPage();page.setDefaultTimeout(14000);
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
        .getByRole('button',{name:'برد کارها'}).click();
      const lane=page.locator('.kanban-lane[aria-label="ستون شروع"]');
      await lane.locator('.lane-add-card').click();
      const form=lane.getByRole('form',{name:'افزودن کارت به شروع'});
      const editor=form.getByRole('textbox',{name:'عنوان کارت جدید'});
      await editor.fill('متن نجات نیافته');
      await form.getByRole('button',{name:'افزودن کارت',exact:true}).click();
      await form.getByRole('alert').waitFor({state:'visible'});
      assert.match(await form.getByRole('alert').innerText(),/ثبت نسخهٔ بازیابی نیز ممکن نبود/);
      assert.equal(await editor.inputValue(),'متن نجات نیافته');
      assert.equal(await form.getByRole('button',{name:'بستن افزودن کارت'}).isEnabled(),true);
      await page.getByRole('button',{name:'دریافت تغییرات ذخیره‌نشده'}).click();
      const exported=await page.evaluate(async()=>JSON.parse(await window.__lastRecoveryDownload.text()));
      assert.ok(exported.tasks.some(t=>t.title==='متن نجات نیافته'),
        'Downloaded recovery must use the latest failed state, not a stale storage key');
      assert.equal(exported.tasks.some(t=>t.id==='prior-stale-recovery'),false);
      assert.ok((await page.evaluate(()=>JSON.parse(localStorage.getItem('madar-unsaved-recovery'))))
        .tasks.some(t=>t.id==='prior-stale-recovery'),
        'The stale key remains unchanged when the newer recovery storage write failed');
      assert.equal((await storedState(page)).tasks.some(t=>t.title==='متن نجات نیافته'),false);
      page.once('dialog',async dialog=>await dialog.accept());
      await page.getByRole('button',{name:'بازخوانی نسخه سرور'}).click();
      await page.waitForFunction(()=>localStorage.getItem('madar-unsaved-recovery')===null);
      assert.equal(await page.getByRole('button',{name:'دریافت تغییرات ذخیره‌نشده'}).count(),0,
        'Confirmed server recovery must invalidate the stale failed-save download');
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('authoritative recovery read cannot silently overwrite a concurrent card edit',
  {skip:!runnable,timeout:65000},async()=>{
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',server:{
      host:'127.0.0.1',port:await unusedPort(),strictPort:true,hmr:false,
      watch:{ignored:['**/.qa-*','**/WebView2/**','**/research/**']}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR'});
      await context.addInitScript(data=>{
        const baseline=structuredClone(data);
        window.__recoveryReadCount=0;
        window.__recoveryReadPending=false;
        window.madar={
          getState:async()=>structuredClone(baseline),
          getStateForUi:async()=>{
            if(++window.__recoveryReadCount===1)return structuredClone(baseline);
            window.__recoveryReadPending=true;
            return new Promise(resolve=>{
              window.__finishRecoveryRead=()=>resolve(structuredClone(baseline));
            });
          },
          saveState:async()=>{throw Error('Synthetic rejected host save');},
          lanStatus:async()=>({mode:'solo',user:{username:'qa',role:'admin',projects:null}}),
          lanProfiles:async()=>[],
          getPreferences:async()=>({calendar:'jalali',clockWidget:'hidden'}),
          syncStatus:async()=>({}),
          releaseCheck:async()=>({available:false}),
        };
      },fixture);
      const page=await context.newPage();page.setDefaultTimeout(15000);
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
        .getByRole('button',{name:'برد کارها'}).click();
      const lane=page.locator('.kanban-lane[aria-label="ستون شروع"]');
      await lane.locator('.lane-add-card').click();
      const form=lane.getByRole('form',{name:'افزودن کارت به شروع'});
      await form.getByRole('textbox',{name:'عنوان کارت جدید'}).fill('کارت آزمایش بازیابی');
      await form.getByRole('button',{name:'افزودن کارت',exact:true}).click();
      await form.getByRole('alert').waitFor({state:'visible'});
      page.once('dialog',async dialog=>await dialog.accept());
      await page.getByRole('button',{name:'بازخوانی نسخه سرور'}).click();
      await page.waitForFunction(()=>window.__recoveryReadPending===true);
      const toggle=lane.locator('[data-progressive-card-id="old-a"] .task-complete-toggle');
      assert.equal(await toggle.getAttribute('aria-pressed'),'false');
      await toggle.click();
      assert.equal(await toggle.getAttribute('aria-pressed'),'false',
        'No speculative edit is permitted during a forced host read');
      await page.getByText('بازخوانی اطلاعات در جریان است؛ پس از پایان آن دوباره ویرایش کنید.')
        .waitFor({state:'visible'});
      await page.evaluate(()=>window.__finishRecoveryRead());
      await page.locator('.recovery-alert').waitFor({state:'detached'});
      assert.equal(await toggle.getAttribute('aria-pressed'),'false');
      assert.equal((await storedState(page))?.tasks,undefined,
        'A rejected host save never becomes a durable preview write');
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('native backup restore replaces stale polling and reacquires the host CAS token before editing',
  {skip:!runnable,timeout:70000},async()=>{
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',server:{
      host:'127.0.0.1',port:await unusedPort(),strictPort:true,hmr:false,
      watch:{ignored:['**/.qa-*','**/WebView2/**','**/research/**']}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR'});
      await context.addInitScript(data=>{
        let host=structuredClone(data),revision='qa-revision-0';
        const clone=state=>structuredClone(state);
        window.__syntheticSaves=[];
        window.__syntheticReads=0;
        const actualSetInterval=window.setInterval.bind(window);
        window.setInterval=(fn,ms,...args)=>{
          if(ms===15000)window.__runBoardPoll=fn;
          return actualSetInterval(fn,ms,...args);
        };
        window.madar={
          getState:async()=>clone(host),
          getStateForUi:async()=>{
            ++window.__syntheticReads;
            if(window.__failNextAuthoritativeRead){
              window.__failNextAuthoritativeRead=false;
              throw Error('Synthetic post-restore host read unavailable');
            }
            const snapshot={...clone(host),__localRevision:revision};
            if(window.__delayNextPollRead){
              window.__delayNextPollRead=false;
              window.__oldPollingReadPending=true;
              return new Promise(resolve=>{
                window.__releaseOldPollingRead=()=>resolve(snapshot);
              });
            }
            return snapshot;
          },
          saveState:async state=>{
            if(state.__localRevision!==revision)
              throw Error('CONFLICT: synthetic localRevision was not read after restore');
            window.__syntheticSaves.push(clone(state));
            host=clone(state);revision='qa-revision-'+(window.__syntheticSaves.length+1);
            return {localRevision:revision};
          },
          listLocalBackups:async()=>[{name:'madar-qa-synthetic-backup.json'}],
          driveStatus:async()=>({connected:false}),
          driveFolderStatus:async()=>({configured:false,folder:'',available:false}),
          driveFolderList:async()=>[],
          cloudPeerStatus:async()=>({paired:false,enabled:false}),
          restoreLocalBackup:async()=>{
            const restored=clone(data);
            restored.tasks[0].title='کارت بازگردانی‌شده';
            delete restored.__localRevision;
            host=restored;revision='qa-revision-restored';
            return clone(restored); // Real native backup APIs return bare state.
          },
          lanStatus:async()=>({mode:'solo',user:{username:'qa',role:'admin',projects:null}}),
          lanProfiles:async()=>[],
          getPreferences:async()=>({calendar:'jalali',clockWidget:'hidden'}),
          syncStatus:async()=>({}),releaseCheck:async()=>({available:false}),
        };
        localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      },fixture);
      const page=await context.newPage();page.setDefaultTimeout(16000);
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
        .getByRole('button',{name:'برد کارها'}).click();
      await page.waitForFunction(()=>typeof window.__runBoardPoll==='function');
      // Capture a pre-restore host snapshot and leave its background read open.
      await page.evaluate(()=>{
        window.__delayNextPollRead=true;
        window.__runBoardPoll();
      });
      await page.waitForFunction(()=>window.__oldPollingReadPending===true);
      await page.locator('.vitrea-quickdock').getByRole('button',{name:'Google Drive'}).click();
      const recent=page.locator('.backup-easy-recent');
      page.once('dialog',async dialog=>dialog.accept());
      await recent.getByRole('button',{name:'بازیابی'}).click();
      // Only the synthetic host and in-memory synthetic state are modified.
      await page.getByRole('button',{name:'جزئیات کارت بازگردانی‌شده'})
        .waitFor({state:'visible'});
      await page.evaluate(()=>window.__releaseOldPollingRead());
      await page.waitForTimeout(200);
      await page.getByRole('button',{name:'جزئیات کارت بازگردانی‌شده'})
        .waitFor({state:'visible'});
      const lane=page.locator('.kanban-lane[aria-label="ستون شروع"]');
      await lane.locator('.lane-add-card').click();
      const form=lane.getByRole('form',{name:'افزودن کارت به شروع'});
      await form.getByRole('textbox',{name:'عنوان کارت جدید'}).fill('کارت پس از بازیابی');
      await form.getByRole('button',{name:'افزودن کارت',exact:true}).click();
      await page.waitForFunction(()=>window.__syntheticSaves.length===1);
      const saved=await page.evaluate(()=>window.__syntheticSaves[0]);
      assert.equal(saved.__localRevision,'qa-revision-restored',
        'Post-restore save must use the fresh native host revision, not the raw backup payload');
      assert.ok(saved.tasks.some(t=>t.title==='کارت بازگردانی‌شده'));
      assert.ok(saved.tasks.some(t=>t.title==='کارت پس از بازیابی'));
      assert.equal(await page.locator('.recovery-alert').count(),0);
      // Host restore can commit successfully while the subsequent token read
      // fails. The UI must remain fail-closed rather than publish stale CAS.
      await page.evaluate(()=>{window.__failNextAuthoritativeRead=true;});
      await page.locator('.vitrea-quickdock').getByRole('button',{name:'Google Drive'}).click();
      page.once('dialog',async dialog=>dialog.accept());
      await page.locator('.backup-easy-recent').getByRole('button',{name:'بازیابی'}).click();
      await page.locator('.recovery-alert').waitFor({state:'visible'});
      assert.ok((await page.locator('.recovery-alert').innerText()).includes('نتیجه بازیابی نسخه نامشخص است'));
      assert.equal(await page.evaluate(()=>window.__syntheticSaves.length),1,
        'Unknown host restore outcome must not trigger an automatic stale save');
      page.once('dialog',async dialog=>dialog.accept());
      await page.getByRole('button',{name:'بازخوانی نسخه سرور'}).click();
      await page.locator('.recovery-alert').waitFor({state:'detached'});
      await page.getByRole('button',{name:'جزئیات کارت بازگردانی‌شده'})
        .waitFor({state:'visible'});
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });
