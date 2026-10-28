'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');

const root=path.resolve(__dirname,'..');
const source=path.join(root,'src/board_lane_actions.jsx');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const browserAvailable=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);
const bundled=esbuild.buildSync({
  entryPoints:[source],bundle:true,platform:'node',format:'cjs',write:false,
  external:['react','react-dom','lucide-react']
}).outputFiles[0].text;
const loaded=new Module(source,module);
loaded.filename=source;
loaded.paths=Module._nodeModulePaths(root);
loaded._compile(bundled,loaded.filename);
const {laneContextPopupPosition}=loaded.exports;

test('pointer popup preserves cursor position and stays visible near viewport edges',()=>{
  assert.deepEqual(laneContextPopupPosition({x:125,y:80},{width:290,height:200},1024,768),
    {left:125,top:80});
  assert.deepEqual(laneContextPopupPosition({x:950,y:700},{width:290,height:260},1024,768),
    {left:726,top:435});
  assert.deepEqual(laneContextPopupPosition({x:-10,y:900},{width:290,height:200},1024,768),
    {left:8,top:560});
});

test('right-click uses the same list menu, supports keyboard dismissal and guards callbacks',
  {skip:!browserAvailable,timeout:45000},async()=>{
    const {chromium}=require(playwrightHome);
    const harness=`
      import React, {useState} from 'react';
      import {createRoot} from 'react-dom/client';
      import {LaneActionsMenu} from './src/board_lane_actions.jsx';
      window.menuEvents=[];
      function Fixture() {
        const [request,setRequest]=useState(null);
        const [collapsed,setCollapsed]=useState(false);
        const [flags,setFlags]=useState({canEdit:true,canManage:true,hasTop:true,hasCollapse:true,hasSave:true});
        window.setMenuFlags=next=>setFlags(current=>({...current,...next}));
        const stage={id:'lane-1',label:'تست کانبان',subtitle:'',color:'#64748b'};
        const context=e=>{e.preventDefault();setRequest(previous=>({stageId:stage.id,id:(previous?.id||0)+1,x:e.clientX,y:e.clientY}));};
        return React.createElement('div',{id:'lane',onContextMenu:context},
          React.createElement('header',{id:'lane-head'},'تیتر ستون'),
          React.createElement('div',{id:'lane-body'},'فضای کارت‌ها'),
          React.createElement(LaneActionsMenu,{
            stage,count:2,canEdit:flags.canEdit,canManage:flags.canManage,index:0,total:2,
            contextRequest:request,collapsed,
            onSave:flags.hasSave?fields=>window.menuEvents.push(['save',fields]):undefined,
            onAddCard:()=>window.menuEvents.push(['bottom']),
            onAddCardTop:flags.hasTop?()=>window.menuEvents.push(['top']):undefined,
            onToggleCollapse:flags.hasCollapse?()=>{window.menuEvents.push(['collapse']);setCollapsed(v=>!v);}:undefined,
            onMove:direction=>window.menuEvents.push(['move',direction]),
            onArchive:()=>window.menuEvents.push(['archive']),
          })
        );
      }
      createRoot(document.getElementById('root')).render(React.createElement(Fixture));
    `;
    const js=esbuild.buildSync({
      stdin:{contents:harness,resolveDir:root,sourcefile:'lane_context_harness.jsx',loader:'jsx'},
      bundle:true,platform:'browser',format:'iife',write:false
    }).outputFiles[0].text;
    const browser=await chromium.launch({headless:true,executablePath:chrome});
    try {
      const page=await browser.newPage({viewport:{width:920,height:768},locale:'fa-IR'});
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.setContent(`<style>
        body{margin:0}#lane{width:440px;height:350px;background:#e6eef8}
        #lane-head{height:65px;background:#bbd0eb}
        #lane-body{height:190px}
        .lane-actions-popover{position:fixed;box-sizing:border-box;width:290px;padding:10px;background:white}
        .lane-actions-popover button{display:block;min-height:26px}
      </style><div id="root"></div>`);
      await page.addScriptTag({content:js});
      await page.locator('#lane-head').waitFor();
      await page.mouse.click(110,30,{button:'right'});
      const menu=page.getByRole('dialog',{name:'تنظیمات ستون تست کانبان'});
      await menu.waitFor({state:'visible'});
      const rect=await menu.boundingBox();
      assert.equal(Math.round(rect.x),110,'header right-click must anchor menu at pointer x');
      assert.equal(Math.round(rect.y),30,'header right-click must anchor menu at pointer y');
      assert.equal(await menu.getByRole('button',{name:'افزودن کارت در ابتدای ستون'}).isEnabled(),true);
      assert.equal(await menu.getByRole('button',{name:'یک ستون به راست'}).isEnabled(),false);
      // Click exposed lane space: the first popover overlays its original anchor.
      await page.mouse.click(40,170,{button:'right'});
      await menu.waitFor({state:'visible'});
      const moved=await menu.boundingBox();
      assert.equal(Math.round(moved.x),40,'second right-click repositions open menu');
      assert.equal(Math.round(moved.y),170,'second right-click updates y');
      await menu.getByRole('button',{name:'افزودن کارت در ابتدای ستون'}).click();
      await menu.waitFor({state:'hidden'});
      assert.deepEqual(await page.evaluate(()=>window.menuEvents),[['top']]);

      await page.mouse.click(120,30,{button:'right'});
      await menu.getByRole('button',{name:'جمع‌کردن ستون'}).click();
      assert.deepEqual(await page.evaluate(()=>window.menuEvents),[['top'],['collapse']]);
      await page.mouse.click(120,30,{button:'right'});
      await menu.getByRole('button',{name:'بازکردن ستون'}).waitFor();
      await page.keyboard.press('Escape');
      await menu.waitFor({state:'hidden'});
      await page.mouse.click(130,35,{button:'right'});
      await menu.waitFor({state:'visible'});
      await page.mouse.click(600,500);
      await menu.waitFor({state:'hidden'});

      await page.evaluate(()=>window.setMenuFlags({
        canEdit:false,canManage:false,hasTop:false,hasCollapse:false
      }));
      await page.mouse.click(100,20,{button:'right'});
      await menu.waitFor({state:'visible'});
      assert.equal(await menu.getByRole('button',{name:'افزودن کارت',exact:true}).isDisabled(),true);
      assert.equal(await menu.getByRole('button',{name:'افزودن کارت در ابتدای ستون'}).isDisabled(),true);
      assert.equal(await menu.getByRole('button',{name:'بازکردن ستون'}).isDisabled(),true);
      assert.equal(await menu.getByRole('button',{name:'بایگانی ستون'}).count(),0);
      assert.deepEqual(await page.evaluate(()=>window.menuEvents),[['top'],['collapse']]);

      await page.evaluate(()=>window.setMenuFlags({
        canEdit:true,canManage:true,hasTop:true,hasCollapse:true,hasSave:false
      }));
      await menu.waitFor({state:'visible'});
      assert.equal(await menu.getByRole('button',{name:'ذخیره تغییرات'}).isDisabled(),true);
      assert.equal(await menu.locator('input[type=color]').isDisabled(),true);
      await menu.getByRole('button',{name:'بستن عملیات ستون'}).click();
      await page.getByRole('button',{name:'عملیات ستون تست کانبان'}).click();
      await menu.waitFor({state:'visible'});
      const byEllipsis=await menu.boundingBox();
      assert.ok(byEllipsis.x>=8&&byEllipsis.x+byEllipsis.width<=920);
      assert.ok(byEllipsis.y>=8&&byEllipsis.y+byEllipsis.height<=768);
      assert.deepEqual(errors,[]);
    } finally {
      await browser.close();
    }
  });
