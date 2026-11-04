'use strict';
// Browser regression for task-board saved-filter privacy. Synthetic data only.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPath=path.join(process.env.USERPROFILE||'',
  'AppData','Roaming','npm','node_modules','playwright');
const runnable=fs.existsSync(chrome)&&fs.existsSync(playwrightPath);
const fixture=`
  import React from 'react';
  import {createRoot} from 'react-dom/client';
  import {AdvancedFilters} from './src/boardplus.jsx';
  import {EMPTY_ADVANCED_FILTER,readScopedAdvancedFilter,updateScopedAdvancedFilter}
    from './src/advanced_filter_scope.js';
  function Fixture(){
    const [scope,setScope]=React.useState({identity:'solo:owner',board:'board-1'});
    const [state,setState]=React.useState({scope:'',value:EMPTY_ADVANCED_FILTER});
    const key=scope.identity+'|'+scope.board;
    const value=readScopedAdvancedFilter(state,key);
    const setValue=change=>setState(old=>updateScopedAdvancedFilter(old,key,change));
    window.switchScope=(identity,board)=>setScope({identity,board});
    window.activeFilter=value;
    return React.createElement(AdvancedFilters,{
      key:scope.identity+'|'+scope.board,
      identity:scope.identity,scopeId:scope.board,
      tasks:[],users:[],stages:[],value,onChange:setValue});
  }
  createRoot(document.getElementById('root')).render(React.createElement(Fixture));
`;

test('saved task filters are separated by authenticated identity and board; global legacy key is not auto-imported',
  {skip:!runnable,timeout:45000},async()=>{
  const {chromium}=require(playwrightPath);
  const js=esbuild.buildSync({stdin:{contents:fixture,resolveDir:root,
    sourcefile:'madar-saved-filter-fixture.jsx',loader:'jsx'},
    bundle:true,platform:'browser',format:'iife',write:false}).outputFiles[0].text;
  const browser=await chromium.launch({headless:true,executablePath:chrome});
  try{
    const page=await browser.newPage({viewport:{width:950,height:700},locale:'fa-IR'});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    // A synthetic HTTP origin permits localStorage without loading any
    // actual site, API or operational profile.
    await page.route('http://madar.test/',route=>route.fulfill({
      status:200,contentType:'text/html',
      body:'<html dir="rtl"><div id="root"></div></html>'}));
    await page.goto('http://madar.test/');
    await page.evaluate(()=>localStorage.setItem('madar-saved-filters-v1',
      JSON.stringify([{name:'LEAK_LEGACY',filter:{priority:'high'}}])));
    await page.addScriptTag({content:js});
    const toggle=page.getByRole('button',{name:'فیلترهای پیشرفته'});
    const open=async()=>{await toggle.click();await page.locator('.filter-popover').waitFor();};
    const saved=()=>page.locator('.saved-searches');
    const persist=async name=>{
      await page.locator('.filter-save input').fill(name);
      await page.locator('.filter-save button').click();
      await saved().getByRole('button',{name,exact:true}).waitFor();
    };
    await open();
    assert.equal(await page.getByText('LEAK_LEGACY').count(),0);
    await persist('فیلتر تیم الف');
    await page.locator('.filter-grid label').first().locator('select').selectOption('high');
    await page.waitForFunction(()=>window.activeFilter.priority==='high');
    let keys=await page.evaluate(()=>Object.keys(localStorage));
    assert.ok(keys.some(key=>key.startsWith('madar-saved-filters-v2:')));
    assert.ok(keys.includes('madar-saved-filters-v1'),
      'Old unattributed data is retained without exposing it to other accounts');

    await page.evaluate(()=>window.switchScope('solo:other','board-1'));
    await open();
    assert.equal(await page.evaluate(()=>window.activeFilter.priority),'all',
      'A different user must not inherit a previous user active filter');
    assert.equal(await page.getByText('فیلتر تیم الف').count(),0);
    await persist('فیلتر تیم ب');
    await page.evaluate(()=>window.switchScope('solo:owner','board-1'));
    await open();
    await saved().getByRole('button',{name:'فیلتر تیم الف',exact:true}).waitFor();
    assert.equal(await page.getByText('فیلتر تیم ب').count(),0);

    await page.evaluate(()=>window.switchScope('solo:owner','board-2'));
    await open();
    assert.equal(await page.evaluate(()=>window.activeFilter.priority),'all',
      'A different board must not inherit active filters');
    assert.equal(await page.getByText('فیلتر تیم الف').count(),0);
    assert.deepEqual(errors,[]);
  }finally{
    await browser.close();
  }
});
