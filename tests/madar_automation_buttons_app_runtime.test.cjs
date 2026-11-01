'use strict';

const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);

const stages=[
  {id:'todo',label:'در انتظار',subtitle:'',color:'#64748b'},
  {id:'done',label:'انجام‌شده',subtitle:'',color:'#3465a1'},
];
const fixture={
  version:1,
  projects:[{id:'project-qa',name:'پروژه اتوماسیون آزمایشی',color:'#657faa',costEnabled:false,price:0}],
  workspaces:[{id:'workspace-qa',name:'فضای آزمایشی',archived:false}],
  boards:[{id:'board-qa',workspaceId:'workspace-qa',projectId:'project-qa',
    name:'برد دکمه‌های اتوماسیون',archived:false,color:'#657faa',stages}],
  stages,
  tasks:[{id:'card-qa',boardId:'board-qa',projectId:'project-qa',listId:'todo',status:'todo',
    title:'کارت نمونه اتوماسیون',description:'',priority:'medium',completed:false,
    cardOrder:0,createdAt:'2026-10-20T12:00:00Z',updatedAt:'2026-10-20T12:00:00Z',
    dueDate:'',labels:[],checklist:[],reports:[],cost:0}],
  settings:{theme:'light',costDefault:false},
};

const mockButtons=[
  {id:'board-button-qa',projectId:'project-qa',boardId:'board-qa',scope:'board',
    title:'دکمه آزمایشی برد',icon:'bell',enabled:true,
    actions:[{type:'comment',text:'فقط داده آزمایشی'}]},
  {id:'card-button-qa',projectId:'project-qa',boardId:'board-qa',scope:'card',
    title:'دکمه آزمایشی کارت',icon:'message-square',enabled:true,closeAfterAction:false,
    actions:[{type:'comment',text:'فقط داده آزمایشی'}]},
];

async function freePort(){
  return new Promise((resolve,reject)=>{
    const socket=net.createServer();
    socket.once('error',reject);
    socket.listen(0,'127.0.0.1',()=>{
      const port=socket.address().port;
      socket.close(error=>error?reject(error):resolve(port));
    });
  });
}

// Inject a read-only fake API *during Vite transformation* of the full App.
// Nothing is written to src/App.jsx or a native host; calls are visible in
// window.__automationListCalls for scope assertions.
function mockButtonsPlugin(){
  const target='const api=window.madar||mockBridge;';
  const methods=[
    'mockBridge.automationButtonsList=async ({projectId,boardId})=>{',
    'window.__automationListCalls.push({projectId,boardId});',
    'return '+JSON.stringify(mockButtons)+';',
    '};',
  ].join('');
  return {
    name:'madar-automation-buttons-test-api',
    enforce:'pre',
    transform(code,id){
      if(!/[\\/]src[\\/]App\.jsx(?:\?|$)/.test(id))return;
      assert.ok(code.includes(target),'the mock bridge injection target must exist in full App');
      return code.replace(target,methods+'\n'+target);
    },
  };
}

async function withApp({mockHost=false},run){
  const {createServer}=await import('vite');
  const {chromium}=require(playwrightHome);
  const server=await createServer({
    root,logLevel:'error',plugins:mockHost?[mockButtonsPlugin()]:[],
    server:{host:'127.0.0.1',port:await freePort(),strictPort:true,hmr:false,
      watch:{ignored:['**/.qa-*','**/.qa-*/**','**/WebView2/**','**/research/**']}},
  });
  let browser;
  try{
    await server.listen();
    browser=await chromium.launch({headless:true,executablePath:chrome});
    const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR'});
    await context.addInitScript(data=>{
      localStorage.setItem('madar-preview',JSON.stringify(data));
      localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      window.__automationListCalls=[];
    },fixture);
    const page=await context.newPage();
    const pageErrors=[];
    page.on('pageerror',error=>pageErrors.push(error.message));
    page.setDefaultTimeout(10000);
    await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
    await page.locator('.vitrea-primary-nav button').first().click();
    await page.locator('.vitrea-overview').waitFor({state:'visible'});
    await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
      .getByRole('button',{name:'برد کارها'}).click();
    await page.getByRole('heading',{name:'برد دکمه‌های اتوماسیون'}).waitFor();
    await run(page,pageErrors);
  }finally{
    await browser?.close();
    await server.close();
  }
}

async function expectRtlWithinViewport(page,locator,width){
  const box=await locator.boundingBox();
  assert.ok(box, 'UI element should be visible at '+width);
  assert.ok(box.x>=-2 && box.x+box.width<=width+2,JSON.stringify({width,box}));
  assert.equal(await locator.evaluate(el=>getComputedStyle(el).direction),'rtl');
}

async function openBoardPanel(page,width,{supported}){
  const launcher=page.locator('.page-controls .ab-launcher').filter({hasText:'دکمه‌های برد'});
  await launcher.waitFor({state:'visible'});
  await launcher.click();
  const dialog=page.getByRole('dialog',{name:'دکمه‌های اتوماسیون مدار'});
  await dialog.waitFor({state:'visible'});
  await expectRtlWithinViewport(page,dialog,width);
  const tabs=dialog.getByRole('group',{name:'نوع دکمه'});
  assert.equal(await tabs.getByRole('button',{name:'دکمه‌های برد'}).getAttribute('aria-pressed'),'true');
  if(supported){
    await dialog.getByText('دکمه آزمایشی برد').waitFor({state:'visible'});
    assert.equal(await dialog.getByText('دکمه آزمایشی کارت').count(),0);
    assert.equal(await dialog.getByRole('button',{name:'ساخت دکمه'}).isEnabled(),false,
      'test injects only list API; saving is not enabled without a host method');
  }else{
    await dialog.getByText('میزبان این قابلیت را ارائه نمی‌کند',{exact:false}).waitFor({state:'visible'});
    assert.equal(await dialog.getByRole('button',{name:'ساخت دکمه'}).isDisabled(),true);
  }
  await dialog.getByRole('button',{name:'بستن دکمه‌های اتوماسیون'}).click();
  await dialog.waitFor({state:'hidden'});
}

async function openCardInline(page,width,{supported}){
  await page.getByRole('button',{name:'جزئیات کارت نمونه اتوماسیون'}).click();
  const drawer=page.getByRole('dialog',{name:'جزئیات کار'});
  await drawer.waitFor({state:'visible'});
  await drawer.locator('.task-quick-actions .ab-launcher').click();
  const panel=drawer.getByRole('region',{name:'دکمه‌های اتوماسیون مدار'});
  await panel.waitFor({state:'visible'});
  assert.equal(await panel.evaluate(el=>getComputedStyle(el).direction),'rtl');
  assert.equal(await panel.getByRole('button',{name:'دکمه‌های کارت'}).getAttribute('aria-pressed'),'true');
  if(supported){
    await panel.getByText('دکمه آزمایشی کارت').waitFor({state:'visible'});
    await drawer.getByRole('group',{name:'دکمه‌های اتوماسیون کارت'})
      .getByRole('button',{name:'دکمه آزمایشی کارت'}).waitFor({state:'visible'});
    assert.equal(await panel.getByText('دکمه آزمایشی برد').count(),0);
  }else{
    await panel.getByText('میزبان این قابلیت را ارائه نمی‌کند',{exact:false}).waitFor({state:'visible'});
    assert.equal(await drawer.getByRole('group',{name:'دکمه‌های اتوماسیون کارت'}).count(),0);
  }
  await drawer.locator('.task-quick-actions .ab-launcher').click();
  await panel.waitFor({state:'hidden'});
  await drawer.getByRole('button',{name:'بستن',exact:true}).click();
  await drawer.waitFor({state:'hidden'});
  // Mobile test checks the board launcher and overlays against the viewport;
  // the card drawer itself may intentionally use a full-screen overlay.
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),true,
    'document should not gain horizontal overflow at '+width);
}

async function goViaRulesSidebar(page,width,scope,{supported}){
  await page.getByRole('button',{name:'قوانین خودکار پروژه'}).click();
  const rules=page.getByRole('dialog',{name:'اتوماسیون پروژه پروژه اتوماسیون آزمایشی'});
  await rules.waitFor({state:'visible'});
  await expectRtlWithinViewport(page,rules,width);
  const section=scope==='board'?'دکمه‌های برد':'دکمه‌های کارت';
  await rules.getByRole('navigation',{name:'بخش‌های اتوماسیون'})
    .getByRole('button',{name:section}).click();
  await rules.waitFor({state:'hidden'});
  const buttons=page.getByRole('dialog',{name:'دکمه‌های اتوماسیون مدار'});
  await buttons.waitFor({state:'visible'});
  await expectRtlWithinViewport(page,buttons,width);
  const active=buttons.getByRole('group',{name:'نوع دکمه'})
    .getByRole('button',{name:section});
  assert.equal(await active.getAttribute('aria-pressed'),'true');
  if(supported){
    await buttons.getByText(scope==='board'?'دکمه آزمایشی برد':'دکمه آزمایشی کارت')
      .waitFor({state:'visible'});
  }else{
    await buttons.getByText('میزبان این قابلیت را ارائه نمی‌کند',{exact:false})
      .waitFor({state:'visible'});
  }
  await buttons.getByRole('button',{name:'بستن دکمه‌های اتوماسیون'}).click();
  await buttons.waitFor({state:'hidden'});
}

test('full App mock API: board and card button entry points, rules navigation, RTL at 1440 and 480',
  {skip:!runnable,timeout:120000},async()=>{
    await withApp({mockHost:true},async(page,errors)=>{
      for(const width of [1440,480]){
        await page.setViewportSize({width,height:900});
        await openBoardPanel(page,width,{supported:true});
        await openCardInline(page,width,{supported:true});
        for(const scope of ['board','card'])
          await goViaRulesSidebar(page,width,scope,{supported:true});
      }
      const calls=await page.evaluate(()=>window.__automationListCalls);
      assert.ok(calls.length>=8,JSON.stringify(calls));
      assert.ok(calls.every(call=>call.projectId==='project-qa'&&call.boardId==='board-qa'),
        'all mock reads must remain bound to the isolated project and board');
      assert.deepEqual(errors,[]);
      console.log('Full App mocked list reads:',calls.length,
        'viewports:1440,480; workflows:board launcher,card inline,rules board/card navigation');
    });
  });

test('full App without native host: board and card launchers expose explicit unsupported state',
  {skip:!runnable,timeout:90000},async()=>{
    await withApp({mockHost:false},async(page,errors)=>{
      await page.setViewportSize({width:480,height:900});
      await openBoardPanel(page,480,{supported:false});
      await openCardInline(page,480,{supported:false});
      await goViaRulesSidebar(page,480,'card',{supported:false});
      assert.deepEqual(errors,[]);
    });
  });
