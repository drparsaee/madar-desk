'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');

const root = path.resolve(__dirname, '..');
const chrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome = 'C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable = fs.existsSync(chrome) && fs.existsSync(playwrightHome);
const laneName = 'شروع آزمایش';
const stages = [
  {id:'lane-start',label:laneName,subtitle:'توضیح ستون',color:'#64748b'},
  {id:'lane-empty',label:'ستون خالی',subtitle:'',color:'#3465a1'},
];
const fixture = {
  version:1,
  projects:[{id:'p1',name:'پروژه تست',color:'#657faa',costEnabled:false,price:0}],
  workspaces:[{id:'w1',name:'فضای تست',archived:false}],
  boards:[{id:'b1',workspaceId:'w1',projectId:'p1',name:'برد آزمایشی منوی لیست',
    archived:false,color:'#657faa',stages}],
  stages,
  tasks:[{id:'c1',boardId:'b1',projectId:'p1',listId:'lane-start',status:'lane-start',
    title:'کارت آزمایشی',description:'',priority:'medium',completed:false,
    cardOrder:0,createdAt:'2026-10-20T12:00:00Z',updatedAt:'2026-10-20T12:00:00Z',
    dueDate:'',labels:[],checklist:[],reports:[],cost:0}],
  settings:{theme:'light',costDefault:false},
};

async function freePort() {
  return new Promise((resolve,reject)=>{
    const socket=net.createServer();
    socket.once('error',reject);
    socket.listen(0,'127.0.0.1',()=>{
      const port=socket.address().port;
      socket.close(error=>error?reject(error):resolve(port));
    });
  });
}

// A normal Vite transform keeps the full App tree. Only the test viewer's
// mock LAN identity is replaced; no production storage or source is changed.
function viewerPlugin() {
  return {
    name:'madar-test-viewer-identity',
    enforce:'pre',
    transform(code,id) {
      if (!/[\\/]src[\\/]App\.jsx(?:\?|$)/.test(id)) return;
      const before="lanStatus:async()=>({mode:'solo',user:{username:'local',role:'admin',projects:null}})";
      const after="lanStatus:async()=>({mode:'client',user:{username:'local',role:'viewer',projects:null}})";
      assert.ok(code.includes(before),'viewer fixture must find the actual app mock bridge');
      return code.replace(before,after);
    },
  };
}

async function withApp(role,run) {
  const {createServer}=await import('vite');
  const {chromium}=require(playwrightHome);
  const server=await createServer({
    root,logLevel:'error',plugins:role==='viewer'?[viewerPlugin()]:[],
    server:{host:'127.0.0.1',port:await freePort(),strictPort:true,hmr:false,
      watch:{ignored:['**/.qa-*','**/.qa-*/**','**/WebView2/**','**/research/**']}},
  });
  let browser;
  try {
    await server.listen();
    browser=await chromium.launch({headless:true,executablePath:chrome});
    const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR'});
    await context.addInitScript(data=>{
      localStorage.setItem('madar-preview',JSON.stringify(data));
      localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      window.__contextHits=[];
      document.addEventListener('contextmenu',e=>{
        const hit={target:e.target?.className?.baseVal||e.target?.className||e.target?.tagName,
          prevented:false};
        window.__contextHits.push(hit);
        setTimeout(()=>{hit.prevented=e.defaultPrevented;},0);
      },true);
    },fixture);
    const page=await context.newPage();
    page.setDefaultTimeout(8000);
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
    await page.locator('.vitrea-primary-nav button').first().click();
    await page.locator('.vitrea-overview').waitFor({state:'visible'});
    await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
      .getByRole('button',{name:'برد کارها'}).click();
    await page.getByRole('heading',{name:'برد آزمایشی منوی لیست'}).waitFor();
    await run(page,errors);
  } finally {
    await browser?.close();
    await server.close();
  }
}

// Close a previous portal before measuring the next hit target, since a
// pointerdown on the portal itself would otherwise skew the result.
async function probe(page,lane,selector,stageLabel=laneName) {
  const menu=page.getByRole('dialog',{name:'تنظیمات ستون '+stageLabel});
  if(await page.locator('.lane-actions-popover').count()) {
    await page.keyboard.press('Escape');
    await page.locator('.lane-actions-popover').first().waitFor({state:'hidden'});
  }
  await page.evaluate(()=>{window.__contextHits=[];});
  await lane.locator(selector).click({button:'right',position:{x:3,y:3}});
  await page.waitForTimeout(75);
  const opened=await menu.isVisible();
  const hit=await page.evaluate(()=>window.__contextHits.at(-1));
  return {selector,opened,prevented:hit?.prevented,target:hit?.target};
}

test('real App: list context-menu target matrix and action availability',
  {skip:!runnable,timeout:90000},async()=>{
    await withApp('admin',async(page,errors)=>{
      const lane=page.locator('.kanban-lane[aria-label="ستون '+laneName+'"]');
      const empty=page.locator('.kanban-lane[aria-label="ستون ستون خالی"]');
      await lane.waitFor();
      const cases=[
        ['.lane-heading strong',true],
        ['.lane-count',true],
        ['.lane-subtitle',true],
        ['.stage-drag-handle',true],
        ['.lane-insert-before',true],
        ['.lane-add-card',true],
        ['.task-card .task-title',false],
        ['.task-complete-toggle',false],
        ['.lane-collapse-toggle',true],
      ];
      const results=[];
      for(const [selector,expected] of cases) {
        const result=await probe(page,lane,selector);
        results.push({...result,expected});
      }
      const emptyResult=await probe(page,empty,'.lane-empty-message','ستون خالی');
      results.push({...emptyResult,expected:true});
      console.log('List context target matrix (full App):',JSON.stringify(results));
      await page.keyboard.press('Escape');
      await page.locator('.project-file-panel summary').click({button:'right'});
      assert.equal(await page.locator('.lane-actions-popover').count(),0,
        'right-clicking project summary outside a lane must not open a list menu');

      // The collapsed lane must retain a context target, independently of
      // the ellipsis and the expand button.
      await page.keyboard.press('Escape');
      await lane.locator('.lane-collapse-toggle').click();
      assert.ok(await lane.evaluate(el=>el.classList.contains('kanban-lane--collapsed')));
      const collapsed=await probe(page,lane,'.lane-collapsed-title');
      results.push({...collapsed,expected:true});
      const collapsedButton=await probe(page,lane,'.lane-expand-control');
      results.push({...collapsedButton,expected:true});
      const menu=page.getByRole('dialog',{name:'تنظیمات ستون '+laneName});
      await menu.waitFor({state:'visible'});
      assert.ok(await menu.getByRole('button',{name:'افزودن کارت در ابتدای ستون'}).isEnabled());
      assert.ok(await menu.getByRole('button',{name:'کپی ستون خالی'}).isEnabled());
      assert.ok(await menu.getByRole('button',{name:/بایگانی ستون/}).isEnabled());
      await page.keyboard.press('Escape');
      assert.equal(await menu.count(),0);
      await lane.locator('.lane-expand-control').click();
      assert.equal(await lane.evaluate(el=>el.classList.contains('kanban-lane--collapsed')),false);
      await page.waitForTimeout(100);
      assert.equal(await menu.count(),0,
        'expanding a lane after Escape must not replay the old context request');
      await lane.getByRole('button',{name:'عملیات لیست '+laneName}).click();
      await menu.waitFor({state:'visible'});
      assert.ok(await menu.getByRole('button',{name:'افزودن کارت',exact:true}).isEnabled());
      await page.keyboard.press('Escape');
      assert.equal(await menu.count(),0);
      console.log('Collapsed and full menu target matrix:',JSON.stringify(results.slice(-2)));
      const cardHits=results.filter(item=>item.selector.includes('task-'));
      assert.ok(cardHits.every(item=>!item.prevented),
        'card right-click should remain available for a future card-specific context menu');
      assert.ok(results.filter(item=>!item.selector.includes('task-'))
        .every(item=>item.prevented),'list-target right-click must suppress the native browser menu');
      assert.deepEqual(errors,[],'App must not emit runtime errors');
      const failures=results.filter(item=>item.opened!==item.expected);
      assert.deepEqual(failures,[],'right-click should open list actions on list header, including nested drag handle');
    });
  });

test('real App: viewer opens read-only list actions without management controls',
  {skip:!runnable,timeout:90000},async()=>{
    await withApp('viewer',async(page,errors)=>{
      const lane=page.locator('.kanban-lane[aria-label="ستون '+laneName+'"]');
      assert.equal(await lane.locator('.stage-drag-handle').count(),0);
      const target=await probe(page,lane,'.lane-heading strong');
      assert.equal(target.opened,true,JSON.stringify(target));
      const menu=page.getByRole('dialog',{name:'تنظیمات ستون '+laneName});
      assert.equal(await menu.getByRole('button',{name:'افزودن کارت',exact:true}).isDisabled(),true);
      assert.equal(await menu.getByRole('button',{name:'افزودن کارت در ابتدای ستون'}).isDisabled(),true);
      assert.equal(await menu.locator('.lane-actions-popover__editor').count(),0);
      assert.equal(await menu.getByRole('button',{name:'بایگانی ستون'}).count(),0);
      assert.ok(await menu.getByText('تنظیم ستون فقط برای مدیر مجاز است.').isVisible());
      assert.deepEqual(errors,[]);
    });
  });
