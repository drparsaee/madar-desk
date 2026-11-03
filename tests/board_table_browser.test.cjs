'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const esbuild=require('esbuild');
let playwright;
try{playwright=require('playwright');}
catch{playwright=require(path.join(process.env.USERPROFILE||process.env.HOME,
  'AppData','Roaming','npm','node_modules','playwright'));}
const root=path.resolve(__dirname,'..');
const output=esbuild.buildSync({stdin:{contents:`
import React from 'react';import{createRoot}from'react-dom/client';
import{BoardTableView}from'./src/board_table_view.jsx';
const board={id:'b',customFields:[{id:'amount',type:'number',name:'Quantity'}]};
const tasks=[{id:'one',boardId:'b',projectId:'p',listId:'todo',title:'First',
  priority:'high',customFieldValues:{amount:12.5}},
  {id:'two',boardId:'b',projectId:'p',listId:'todo',title:'Second',
  priority:'high',customFieldValues:{amount:7.5}}];
window.opened=[];
createRoot(document.getElementById('root')).render(React.createElement(BoardTableView,{
  board,scopeId:'b',identity:'test-user',storage:{getItem:()=>null,setItem:()=>{}},tasks,
  stages:[{id:'todo',label:'Todo'}],projects:[{id:'p',name:'Project'}],
  priorities:[{id:'high',label:'High'}],onOpen:id=>window.opened.push(id)
}));`,resolveDir:root,sourcefile:'table-browser-fixture.jsx',loader:'jsx'},
  bundle:true,write:false,platform:'browser',format:'iife',
  outdir:'table-browser-fixture-build',loader:{'.css':'css'}}).outputFiles;
const js=output.find(file=>file.path.endsWith('.js')).text;
const css=output.find(file=>file.path.endsWith('.css')).text;
test('board table in RTL light/dark fits viewport and opens cards',async t=>{
  const browser=await playwright.chromium.launch({channel:'msedge',headless:true});
  t.after(()=>browser.close());
  const page=await browser.newPage({viewport:{width:390,height:700}});
  await page.setContent('<html lang="fa" dir="rtl"><head><meta charset="utf-8">'+
    '<style>*{box-sizing:border-box}body{margin:0;padding:8px}#root{width:100%;min-width:0}</style>'+
    '</head><body><div id="root"></div></body></html>');
  await page.addStyleTag({content:css});
  await page.addScriptTag({content:js});
  await page.locator('.madar-board-table tbody tr').first().waitFor();
  for(const theme of ['light','dark'])for(const width of [390,1280]){
    await page.setViewportSize({width,height:700});
    await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
    const m=await page.evaluate(()=>{
      const wrapper=document.querySelector('.madar-board-table');
      const scroll=wrapper.querySelector('.madar-board-table__scroller');
      const style=getComputedStyle(wrapper);
      return {width:wrapper.getBoundingClientRect().width,doc:document.documentElement.scrollWidth,
        viewport:window.innerWidth,scrollable:scroll.scrollWidth>scroll.clientWidth,
        background:style.backgroundColor,color:style.color};
    });
    assert.ok(m.width<=width&&m.doc<=width+1,JSON.stringify(m));
    if(width===390)assert.ok(m.scrollable,JSON.stringify(m));
    assert.notEqual(m.color,m.background,'foreground matches background');
  }
  await page.locator('.madar-board-table__open').first().click();
  assert.deepEqual(await page.evaluate(()=>window.opened),['one']);
  await page.locator('.madar-board-table__configure').click();
  assert.equal(await page.locator('.madar-board-table__config-item').count(),7);
});
