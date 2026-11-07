'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');

function loadModule(file){
  const entry=path.join(root,file);
  const code=esbuild.buildSync({entryPoints:[entry],platform:'node',bundle:true,format:'cjs',write:false,
    loader:{'.css':'empty'},external:['react','react/jsx-runtime','react-dom','react-dom/client','lucide-react']}).outputFiles[0].text;
  const instance=new Module(entry,module);instance.filename=entry;
  instance.paths=Module._nodeModulePaths(path.dirname(entry));
  instance._compile(code,entry);return instance.exports;
}

test('notification destination is restricted to authorized snapshot, correct project and active location',()=>{
  const {resolveNotificationLocation:resolve}=loadModule('src/teamplus.jsx');
  const view={projects:[{id:'visible'}],boards:[{id:'board',projectId:'visible',workspaceId:'space',archived:false,
    stages:[{id:'todo',archived:false}]}],workspaces:[{id:'space',archived:false}],
    tasks:[{id:'card',projectId:'visible',boardId:'board',listId:'todo'}]};
  const notice={id:'n',projectId:'visible',cardId:'card'};
  assert.deepEqual(resolve(notice,view),{kind:'card',projectId:'visible',cardId:'card',boardId:'board',workspaceId:'space'});
  assert.deepEqual(resolve({...notice,cardId:null},view),
    {kind:'project',projectId:'visible',boardId:'board',workspaceId:'space'});
  assert.equal(resolve({...notice,projectId:'hidden'},view),null);
  assert.equal(resolve({...notice,cardId:'gone'},view),null);
  assert.equal(resolve(notice,{...view,tasks:[{...view.tasks[0],projectId:'hidden'}]}),null);
  assert.equal(resolve(notice,{...view,tasks:[{...view.tasks[0],deleted:true}]}),null);
  assert.equal(resolve(notice,{...view,boards:[{...view.boards[0],archived:true}]}),null);
  assert.equal(resolve(notice,{...view,workspaces:[{id:'space',archived:true}]}),null);
  assert.equal(resolve({...notice,cardId:null},{...view,boards:[]}),null);
  assert.equal(resolve(notice,{...view,boards:[{...view.boards[0],stages:[{id:'todo',archived:true}]}]}),null);
});

test('App navigation checks live backend ACL before selecting project or card',()=>{
  const source=fs.readFileSync(path.join(root,'src','App.jsx'),'utf8');
  assert.match(source,/const openNotificationTarget=async notice=>/);
  assert.match(source,/api\.collabRead\(initial\.kind==='card'\?'comments':'project-comments'/);
  assert.match(source,/const current=resolve\(latestData\.current\|\|data\)/);
  assert.match(source,/onOpenTarget=\{openNotificationTarget\}/);
  assert.match(source,/setProjectChatOpen\(true\)/);
});

let chromium;
try{({chromium}=require('playwright'));}
catch{
  try{({chromium}=require('C:/Users/Parsa/AppData/Roaming/npm/node_modules/playwright'));}
  catch{}
}
const chrome='C:/Program Files/Google/Chrome/Application/chrome.exe';
test('notifications dialog: keyboard focus, explicit reads with retry IDs, generic denied navigation, authorized open',
  {skip:!chromium||!fs.existsSync(chrome),timeout:45000},async()=>{
  const entry=`import React,{useState} from 'react';
    import{createRoot}from'react-dom/client';
    import{NotificationsDialog}from './src/teamplus.jsx';
    window.__p2={events:[],commands:[],failOnce:true,notices:[
      {id:'notice-card',kind:'mention',message:'You were mentioned',projectId:'project',cardId:'card',readAt:null,createdAt:'2026-11-07T10:00:00Z'},
      {id:'notice-project',kind:'mention',message:'Project mention',projectId:'project',cardId:null,readAt:null,createdAt:'2026-11-07T11:00:00Z'},
      {id:'notice-gone',kind:'watch',message:'Old card',projectId:'hidden',cardId:'gone',readAt:null,createdAt:'2026-11-07T12:00:00Z'}]};
    const api={collabRead:async kind=>{window.__p2.events.push('read:'+kind);return window.__p2.notices;},
      collabCommand:async command=>{window.__p2.commands.push(command);if(window.__p2.failOnce){window.__p2.failOnce=false;throw Error('private backend error');}
        const readAt='2026-11-07T12:30:00Z';window.__p2.notices=window.__p2.notices.map(n=>n.id===command.notificationId?{...n,readAt}:n);
        return {notificationId:command.notificationId,readAt};}};
    function Demo(){const[open,setOpen]=useState(false);
      return <><button id='trigger' onClick={()=>setOpen(true)}>اعلان‌ها</button>
        {open&&<NotificationsDialog api={api} onClose={()=>setOpen(false)} onOpenTarget={async item=>{
          window.__p2.events.push('open:'+item.id);return item.id!=='notice-gone';}}/>}</>}
    createRoot(document.getElementById('root')).render(<Demo/>);`;
  const bundled=esbuild.buildSync({stdin:{contents:entry,resolveDir:root,sourcefile:'p2-notifications-fixture.jsx',loader:'jsx'},
    bundle:true,write:false,platform:'browser',format:'iife',loader:{'.css':'empty'}}).outputFiles[0].text;
  const browser=await chromium.launch({headless:true,executablePath:chrome});
  try{
    for(const width of [480,1440]){
      const page=await browser.newPage({viewport:{width,height:800},locale:'fa-IR'});
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.setContent(`<html lang="fa" dir="rtl"><head><meta charset="utf-8"/><style>
        .overlay{position:fixed;inset:0;display:grid;place-items:center;background:#aaa}
        .dialog{background:#fff;color:#233149;width:min(580px,100%);max-height:90vh;overflow:auto}
        .dialog-head{display:flex;justify-content:space-between;padding:12px}
        .dialog-body{padding:12px;overflow:auto}
        .notifications-actions{display:flex;gap:8px}
        </style></head><body><div id="root"></div></body></html>`);
      await page.addStyleTag({content:fs.readFileSync(path.join(root,'src','teamplus.css'),'utf8')});
      await page.addScriptTag({content:bundled});
      const trigger=page.locator('#trigger');await trigger.click();
      const dialog=page.getByRole('dialog',{name:'اعلان‌های من'});
      await dialog.waitFor();
      assert.equal(await dialog.getByText('۳ خوانده‌نشده').count(),1);
      assert.equal(await dialog.locator('.notifications-close').evaluate(el=>document.activeElement===el),true);
      await page.keyboard.press('Shift+Tab');
      assert.equal(await dialog.getByRole('button',{name:'خوانده شد'}).last().evaluate(el=>document.activeElement===el),true);
      await page.keyboard.press('Tab');
      assert.equal(await dialog.locator('.notifications-close').evaluate(el=>document.activeElement===el),true);
      await dialog.getByRole('button',{name:'نمایش مقصد اعلان'}).last().click();
      assert.match(await dialog.getByRole('alert').innerText(),/در دسترس نیست یا مجوز/);
      assert.equal(await dialog.isVisible(),true);
      const mark=dialog.getByRole('button',{name:'خوانده شد'}).first();
      await mark.click();
      assert.match(await dialog.getByRole('alert').innerText(),/ناموفق یا نامشخص/);
      assert.equal(await dialog.getByText('۳ خوانده‌نشده').count(),1);
      await mark.click();
      await dialog.getByText('۲ خوانده‌نشده').waitFor();
      const commands=await page.evaluate(()=>window.__p2.commands);
      assert.equal(commands.length,2);
      assert.equal(commands[0].eventId,commands[1].eventId,'retry must reuse original idempotency key');
      assert.equal(commands[0].notificationId,'notice-card');
      assert.equal(await dialog.getByText('۲ خوانده‌نشده').count(),1);
      // Read marking must be independent from opening a target.
      await dialog.getByRole('button',{name:'نمایش مقصد اعلان'}).nth(1).click();
      await dialog.waitFor({state:'hidden'});
      assert.equal(await trigger.evaluate(el=>document.activeElement===el),true);
      assert.deepEqual(errors,[]);
      await page.close();
    }
  }finally{await browser.close();}
});
