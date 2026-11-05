'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
test('board and list card surfaces handle right click without lane context interception',()=>{
  const source=fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');
  assert.match(source,/onContextRequest=\{requestCardMenu\}/);
  assert.match(source,/onContextMenu=\{e=>\{e\.preventDefault\(\);e\.stopPropagation\(\);onContextRequest/);
  assert.match(source,/onContextMenu=\{event=>\{event\.preventDefault\(\);requestCardMenu\(t,event\)/);
  assert.match(source,/if\(event\.target\.closest\('\.task-card/);
});
test('real card context opens by mouse, archives only for editors, dismisses on Escape',
  {skip:!fs.existsSync(chrome)||!fs.existsSync(playwrightHome),timeout:45000},async()=>{
    const {chromium}=require(playwrightHome);
    const source=[
      "import React,{useState} from 'react';",
      "import {createRoot} from 'react-dom/client';",
      "import {CardContextMenu} from './src/card_context_menu.jsx';",
      "window.events=[];",
      "function App(){const [request,setRequest]=useState(null);const [canEdit,setCanEdit]=useState(true);const [card,setCard]=useState({id:'synthetic-1',title:'کارت آزمایشی',cover:null});",
      "window.setEdit=setCanEdit;return <><div id='card' role='button' tabIndex={0} onContextMenu={e=>{e.preventDefault();setRequest({id:Date.now(),cardId:'synthetic-1',title:'کارت آزمایشی',x:e.clientX,y:e.clientY});}}>Card</div>",
      "<CardContextMenu request={request} task={card} canEdit={canEdit} onClose={()=>setRequest(null)}",
      "onOpen={id=>window.events.push('open:'+id)} onArchive={id=>window.events.push('archive:'+id)}",
      "onDelete={id=>window.events.push('delete:'+id)} onDuplicate={id=>window.events.push('copy:'+id)}",
      "onToggleComplete={id=>window.events.push('complete:'+id)}",
      "onOpenSection={(id,section)=>window.events.push('section:'+section+':'+id)}",
      "onCoverChange={(id,changes)=>{setCard(current=>({...current,...changes}));window.events.push('cover:'+id+':'+changes.cover?.size)}}/></>;}",
      "createRoot(document.getElementById('root')).render(<App/>);"
    ].join('\n');
    const js=esbuild.buildSync({stdin:{contents:source,resolveDir:root,sourcefile:'card-context-test.jsx',loader:'jsx'},
      bundle:true,platform:'browser',format:'iife',write:false,loader:{'.css':'empty'}}).outputFiles[0].text;
    const browser=await chromium.launch({headless:true,executablePath:chrome});
    try{
      const page=await browser.newPage({viewport:{width:700,height:500},locale:'fa-IR'});
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.setContent('<style>#card{width:320px;height:100px;background:#eee}.madar-card-context-menu{position:fixed;width:240px;background:white;border:1px solid black}.madar-card-context-menu button{display:block}</style><div id="root"></div>');
      await page.addScriptTag({content:js});
      await page.locator('#card').waitFor();
      await page.locator('#card').focus();
      await page.mouse.click(80,45,{button:'right'});
      const menu=page.getByRole('menu',{name:'عملیات کارت کارت آزمایشی'});
      await menu.waitFor({state:'visible'});
      await page.waitForFunction(()=>document.activeElement?.getAttribute('role')==='menuitem');
      assert.match(await page.evaluate(()=>document.activeElement.textContent),/بازکردن کارت/);
      await page.keyboard.press('ArrowDown');
      assert.match(await page.evaluate(()=>document.activeElement.textContent),/برچسب/);
      await page.keyboard.press('Home');
      assert.match(await page.evaluate(()=>document.activeElement.textContent),/بازکردن کارت/);
      await page.keyboard.press('End');
      assert.match(await page.evaluate(()=>document.activeElement.textContent),/حذف کارت/);
      await page.keyboard.press('Escape');
      await menu.waitFor({state:'hidden'});
      assert.equal(await page.evaluate(()=>document.activeElement?.id),'card');
      await page.mouse.click(80,45,{button:'right'});
      await menu.waitFor({state:'visible'});
      await menu.getByRole('menuitem',{name:'ویرایش برچسب‌ها'}).click();
      assert.deepEqual(await page.evaluate(()=>window.events),['section:tags:synthetic-1']);
      await page.mouse.click(80,45,{button:'right'});
      await menu.getByRole('menuitem',{name:'کاور و رنگ کارت'}).click();
      const editor=menu.getByRole('group',{name:'تنظیم کاور کارت'});
      await editor.waitFor({state:'visible'});
      await editor.getByRole('button',{name:'رنگ تمام کارت'}).click();
      assert.equal((await page.evaluate(()=>window.events)).at(-1),'cover:synthetic-1:full');
      assert.equal(await editor.getByRole('img',{name:/نمایش کاور تمام کارت/}).count(),1);
      assert.equal(await menu.isVisible(),true,'cover edit must remain in right-click menu');
      await page.keyboard.press('Escape');
      await menu.waitFor({state:'hidden'});
      await page.mouse.click(80,45,{button:'right'});
      await menu.getByRole('menuitem',{name:'کپی کارت'}).click();
      assert.equal((await page.evaluate(()=>window.events)).at(-1),'copy:synthetic-1');
      await page.mouse.click(80,45,{button:'right'});
      await menu.getByRole('menuitem',{name:'بایگانی کارت'}).click();
      assert.equal((await page.evaluate(()=>window.events)).at(-1),'copy:synthetic-1',
        'archive must not mutate without an explicit confirmation');
      await menu.getByRole('button',{name:'انصراف'}).click();
      assert.equal((await page.evaluate(()=>window.events)).at(-1),'copy:synthetic-1');
      await menu.getByRole('menuitem',{name:'حذف کارت'}).click();
      await menu.getByRole('button',{name:'انصراف'}).click();
      assert.equal((await page.evaluate(()=>window.events)).at(-1),'copy:synthetic-1');
      await menu.getByRole('menuitem',{name:'بایگانی کارت'}).click();
      await menu.getByRole('button',{name:'تأیید بایگانی'}).click();
      assert.equal((await page.evaluate(()=>window.events)).at(-1),'archive:synthetic-1');
      await page.evaluate(()=>window.setEdit(false));
      await page.mouse.click(100,50,{button:'right'});
      await menu.waitFor({state:'visible'});
      assert.equal(await menu.getByRole('menuitem',{name:'بایگانی کارت'}).count(),0);
      assert.equal(await menu.getByRole('menuitem',{name:'حذف کارت'}).count(),0);
      assert.equal(await menu.getByRole('menuitem',{name:'کپی کارت'}).count(),0);
      await page.keyboard.press('Escape');
      await menu.waitFor({state:'hidden'});
      await page.mouse.click(110,55,{button:'right'});
      await menu.getByRole('menuitem',{name:'بازکردن کارت'}).click();
      assert.equal((await page.evaluate(()=>window.events)).at(-1),'open:synthetic-1');
      assert.deepEqual(errors,[]);
    } finally {await browser.close();}
  });
