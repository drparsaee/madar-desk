'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const esbuild=require('esbuild');

let playwright;
try {playwright=require('playwright');}
catch {
  const base=process.env.APPDATA||path.join(process.env.USERPROFILE||'', 'AppData','Roaming');
  try {playwright=require(path.join(base,'npm','node_modules','playwright'));}
  catch {playwright=null;}
}

const root=path.resolve(__dirname,'..');
const output=esbuild.buildSync({
  stdin:{contents:`
    import React from 'react';
    import {createRoot} from 'react-dom/client';
    import {GanttView} from './src/gantt_view.jsx';
    import './src/gantt_view.css';
    const seed=[
      {id:'a',title:'پیش‌نیاز عمومی',projectId:'p',status:'active',priority:'medium',
        plannedStart:'2026-11-07',plannedEnd:'2026-11-10'},
      {id:'b',title:'مرحله دوم',projectId:'p',status:'active',priority:'high',dependencies:['a'],
        plannedStart:'2026-11-09',plannedEnd:'2026-11-12'},
      {id:'c',title:'مرحله سوم',projectId:'p',status:'active',priority:'medium',
        dependencies:['secret-private-card'],plannedStart:'2026-11-13',plannedEnd:'2026-11-15'}
    ];
    window.__updates=[];
    function Fixture(){
      const [tasks,setTasks]=React.useState(seed);
      const [canEdit,setCanEdit]=React.useState(true);
      window.__setCanEdit=setCanEdit;
      window.__setTasks=setTasks;
      return React.createElement(GanttView,{tasks,calendar:'gregorian',canEdit,
        onOpen:id=>window.__updates.push(['open',id]),
        onUpdate:(id,patch)=>{window.__updates.push(['update',id,patch]);
          setTasks(before=>before.map(t=>t.id===id?{...t,...patch}:t));}});
    }
    createRoot(document.getElementById('app')).render(React.createElement(Fixture));
  `,resolveDir:root,sourcefile:'p2-gantt-browser.jsx',loader:'jsx'},
  bundle:true,write:false,outdir:'synthetic-p2-gantt',format:'iife',platform:'browser',
  loader:{'.css':'css'}}).outputFiles;
const js=output.find(item=>item.path.endsWith('.js')).text;
const css=output.find(item=>item.path.endsWith('.css')).text;

test('P2 Chromium Gantt reports dependency conflicts, fixes one card and respects viewer mode',
  {skip:!playwright,timeout:60000},async t=>{
    const browser=await playwright.chromium.launch({channel:'msedge',headless:true});
    t.after(()=>browser.close());
    const page=await browser.newPage({viewport:{width:375,height:780},locale:'fa-IR'});
    const errors=[];page.on('pageerror',err=>errors.push(err.message));
    await page.setContent(`<html dir="rtl" data-theme="light"><head><meta charset="utf-8">
      <style>*{box-sizing:border-box}body{margin:10px;font:13px Arial;background:#fff}
      #app{width:100%;min-width:0}:root{--surface:#fff;--surface-2:#f4f7fa;--border:#d7dfe6;--text:#27344a}</style>
      </head><body><div id="app"></div></body></html>`);
    await page.addStyleTag({content:css});
    await page.addScriptTag({content:js});
    const status=page.getByRole('status',{name:'کنترل ارتباط و زمان‌بندی گانت'});
    await status.waitFor();
    assert.match(await status.innerText(),/۱ کارت دارای تداخل زمانی/);
    assert.match(await status.innerText(),/پیش‌نیاز در نمای فعلی قابل بررسی نیست/);
    assert.equal((await page.locator('body').innerText()).includes('secret-private-card'),false);
    const critical=page.getByRole('region',{name:'تحلیل مسیر بحرانی'});
    assert.match(await critical.innerText(),/تحلیل کامل نیست/);
    assert.equal((await critical.innerText()).includes('secret-private-card'),false);
    const repair=page.getByRole('button',{name:'اصلاح تاریخ کارت مرحله دوم بر اساس پیش‌نیازها'});
    assert.equal(await repair.count(),1);
    await repair.click();
    assert.deepEqual(await page.evaluate(()=>window.__updates.filter(x=>x[0]==='update')),
      [['update','b',{plannedStart:'2026-11-11',plannedEnd:'2026-11-14'}]]);
    assert.match(await status.innerText(),/تداخل زمانی شناسایی نشد/);
    assert.equal(await repair.count(),0);
    await page.evaluate(()=>window.__setTasks(current=>current.filter(task=>task.id!=='c')));
    await page.getByRole('button',{name:/نوار مرحله دوم، در مسیر بحرانی/}).waitFor();
    assert.match(await critical.innerText(),/طولانی‌ترین زنجیره: ۸ روز/);
    assert.match(await critical.innerText(),/پیش‌نیاز عمومی/);
    assert.match(await critical.innerText(),/مرحله دوم/);
    assert.match(await page.locator('.gantt-critical-chip').first().innerText(),/بحرانی/);
    await page.evaluate(()=>window.__setCanEdit(false));
    assert.equal(await page.getByRole('button',{name:/اصلاح تاریخ کارت/}).count(),0);
    assert.equal(await page.getByLabel('شروع مرحله دوم').isDisabled(),true);
    for(const width of [320,375,768]){
      await page.setViewportSize({width,height:780});
      const metrics=await page.evaluate(()=>({width:window.innerWidth,
        document:document.documentElement.scrollWidth,
        scroll:document.querySelector('.gantt-scroll').scrollWidth,
        client:document.querySelector('.gantt-scroll').clientWidth}));
      assert(metrics.document<=metrics.width+1,JSON.stringify(metrics));
      assert(metrics.scroll>metrics.client,JSON.stringify(metrics));
    }
    assert.deepEqual(errors,[]);
  });
