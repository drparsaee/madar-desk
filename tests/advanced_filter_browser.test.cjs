'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const esbuild=require('esbuild');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);

test('Chromium: nested filter editor combines clauses, handles invalid text, and remains usable in RTL/dark',
 {skip:!runnable,timeout:60000},async()=>{
 const {chromium}=require(playwrightHome);
 const output=esbuild.buildSync({stdin:{contents:`
   import React from 'react';
   import {createRoot} from 'react-dom/client';
   import {AdvancedFilters,matchAdvanced} from './src/boardplus.jsx';
   import './src/boardplus.css';
   const cards=[
     {id:'a',title:'first',priority:'high',labels:[],assignees:[],status:'todo'},
     {id:'b',title:'second',priority:'low',labels:[],assignees:[],status:'todo'}
   ];
   function Fixture(){
     const [value,setValue]=React.useState({priority:'all',member:'all',label:'all',status:'all',due:'all',attachments:false});
     window.__filter=value;
     window.__visible=cards.filter(card=>matchAdvanced(card,value)).map(card=>card.id);
     return React.createElement(AdvancedFilters,{tasks:cards,priorities:[{id:'high',label:'بالا'},{id:'low',label:'پایین'}],
       stages:[{id:'todo',label:'در جریان'}],value,onChange:setValue});
   }
   createRoot(document.getElementById('app')).render(React.createElement(Fixture));
 `,resolveDir:root,sourcefile:'synthetic-advanced-filter.jsx',loader:'jsx'},
 bundle:true,write:false,outdir:'synthetic-filter',format:'iife',platform:'browser',loader:{'.css':'css'}}).outputFiles;
 const js=output.find(file=>file.path.endsWith('.js')).text;
 const css=output.find(file=>file.path.endsWith('.css')).text;
 const browser=await chromium.launch({headless:true,executablePath:chrome});
 try{
   const page=await browser.newPage({viewport:{width:360,height:800},locale:'fa-IR'});
   page.setDefaultTimeout(7000);
   const errors=[];page.on('pageerror',err=>errors.push(err.message));
   await page.setContent('<html dir="rtl" data-theme="dark"><head><meta charset="utf-8"><style>*{box-sizing:border-box}body{font:13px Arial;margin:12px}#app{width:max-content}</style></head><body><div id="app"></div></body></html>');
   await page.addStyleTag({content:css});
   await page.addScriptTag({content:js});
   await page.getByRole('button',{name:'فیلترهای پیشرفته'}).click();
   await page.locator('.filter-rule-builder summary').click();
   await page.locator('.filter-rule-group .filter-rule-actions button').first().click();
   assert.deepEqual(await page.evaluate(()=>window.__visible),['a']);
   await page.locator('.filter-rule-group .filter-rule-actions button').nth(1).click();
   const sub=page.locator('.filter-rule-group.nested').first();
   await sub.getByLabel('فیلد شرط').selectOption('title');
   await sub.getByLabel('عبارت عنوان').fill('second');
   assert.deepEqual(await page.evaluate(()=>window.__visible),[]);
   await page.locator('.filter-rule-group-header').first().getByLabel('نوع ترکیب شرط‌ها').selectOption('or');
   assert.deepEqual(await page.evaluate(()=>window.__visible),['a','b']);
   await sub.getByLabel('عبارت عنوان').fill('');
   assert.deepEqual(await page.evaluate(()=>window.__visible),[]);
   assert.equal(await page.locator('.filter-rule-error').count(),1);
   await page.locator('.filter-save input').fill('فیلتر آزمایشی');
   assert.equal(await page.locator('.filter-save button').isDisabled(),true);
   await sub.getByLabel('عبارت عنوان').fill('second');
   assert.deepEqual(await page.evaluate(()=>window.__visible),['a','b']);
   assert.equal(await page.locator('.filter-save button').isEnabled(),true);
   await page.locator('.filter-grid label').first().locator('select').selectOption('low');
   assert.deepEqual(await page.evaluate(()=>window.__visible),['b']);
   for(const dir of ['rtl','ltr'])for(const theme of ['dark','light']){
     await page.evaluate(({dir,theme})=>{
       document.documentElement.dir=dir;document.documentElement.dataset.theme=theme;
     },{dir,theme});
     const box=await page.locator('.filter-popover').boundingBox();
     assert(box&&box.x>=0&&box.x+box.width<=360.5,`filter popup clips narrow ${dir}/${theme} viewport: ${JSON.stringify(box)}`);
   }
   assert.equal(errors.length,0,errors.join('\n'));
 }finally{await browser.close();}
});
