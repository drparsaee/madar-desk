'use strict';
// UX pilot: actual Chrome keyboard interactions, synthetic records only.
// No desktop profile, financial service, database or live application is opened.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const esbuild=require('esbuild');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPath=path.join(process.env.USERPROFILE||'',
  'AppData','Roaming','npm','node_modules','playwright');
const browserAvailable=fs.existsSync(chrome)&&fs.existsSync(playwrightPath);

const fixture=`
  import React,{useState} from 'react';
  import {createRoot} from 'react-dom/client';
  import AccountingGlobalSearch from './src/accounting_global_search.jsx';
  import {LaneActionsMenu} from './src/board_lane_actions.jsx';
  window.uxEvents=[];
  const index=[
    {key:'section:sales',type:'section',tab:'invoice',title:'فاکتور فروش',
      subtitle:'بخش حسابداری',searchable:'فاکتور فروش'},
    {key:'section:buy',type:'section',tab:'bill',title:'فاکتور خرید',
      subtitle:'بخش حسابداری',searchable:'فاکتور خرید'}
  ];
  function Fixture(){
    const [open,setOpen]=useState(false);
    const stage={id:'synthetic-lane',label:'لیست آزمایشی',subtitle:'',color:'#64748b'};
    return React.createElement('main',{},
      React.createElement('button',{id:'open-search',onClick:()=>setOpen(true)},'بازکردن جست‌وجو'),
      React.createElement(AccountingGlobalSearch,{open,index,
        onSelect:item=>window.uxEvents.push(['select',item.key]),
        onClose:()=>{window.uxEvents.push(['close']);setOpen(false);}}),
      React.createElement(LaneActionsMenu,{stage,count:0,canManage:true,canEdit:true,
        index:0,total:2,onAddCard:()=>window.uxEvents.push(['add-card']),
        onSave:()=>{},onMove:()=>{}})
    );
  }
  createRoot(document.getElementById('root')).render(React.createElement(Fixture));
`;

test('accounting result selection respects focused Enter control; board menu receives keyboard focus',
  {skip:!browserAvailable,timeout:60000},async()=>{
  const {chromium}=require(playwrightPath);
  const js=esbuild.buildSync({stdin:{contents:fixture,resolveDir:root,
    sourcefile:'madar-ux-keyboard-pilot.jsx',loader:'jsx'},
    bundle:true,platform:'browser',format:'iife',write:false,
    loader:{'.css':'empty'}}).outputFiles[0].text;
  const browser=await chromium.launch({headless:true,executablePath:chrome});
  try{
    const page=await browser.newPage({viewport:{width:900,height:800},locale:'fa-IR'});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setContent(`<style>
      .lane-actions-popover{position:fixed;box-sizing:border-box;width:290px;
        padding:12px;background:#fff;border:1px solid #ddd}
      .sac-global-search-layer{position:fixed;inset:0;background:#ddd;z-index:200}
      .sac-global-search-dialog{position:relative;background:white;padding:12px}
    </style><div id="root"></div>`);
    await page.addScriptTag({content:js});
    const openSearch=page.locator('#open-search');
    await openSearch.click();
    const search=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'});
    await search.waitFor({state:'visible'});
    await search.getByRole('combobox').fill('فاکتور');
    assert.equal(await search.getByRole('option').count(),2);

    // Enter on Close must close only, never open a highlighted financial record.
    await search.getByRole('button',{name:'بستن جست‌وجو'}).focus();
    await page.keyboard.press('Enter');
    await search.waitFor({state:'hidden'});
    assert.deepEqual(await page.evaluate(()=>window.uxEvents),[['close']]);

    // Enter on the second focused result must select the second result,
    // regardless of which item the search input previously highlighted.
    await openSearch.click();
    await search.getByRole('combobox').fill('فاکتور');
    assert.match(await search.getByRole('option').nth(1).innerText(),/فاکتور فروش/);
    await search.getByRole('option').nth(1).focus();
    assert.equal(await search.getByRole('option').nth(1).getAttribute('aria-selected'),'true');
    await page.keyboard.press('ArrowDown');
    assert.equal(await search.getByRole('option').nth(1).getAttribute('aria-selected'),'true',
      'Arrow keys on a focused option must not select a different option');
    await page.keyboard.press('Enter');
    await search.waitFor({state:'hidden'});
    assert.deepEqual(await page.evaluate(()=>window.uxEvents),
      [['close'],['select','section:sales'],['close']]);

    // Enter in the input itself still selects the highlighted search result.
    await openSearch.click();
    await search.getByRole('combobox').fill('فاکتور');
    await page.keyboard.press('Enter');
    await search.waitFor({state:'hidden'});
    assert.deepEqual(await page.evaluate(()=>window.uxEvents),
      [['close'],['select','section:sales'],['close'],
       ['select','section:buy'],['close']]);

    const trigger=page.getByRole('button',{name:'عملیات لیست لیست آزمایشی'});
    await trigger.focus();
    await page.keyboard.press('Enter');
    const menu=page.getByRole('dialog',{name:'تنظیمات ستون لیست آزمایشی'});
    await menu.waitFor({state:'visible'});
    assert.equal(await page.evaluate(()=>
      !!document.activeElement?.closest('.lane-actions-popover')),true,
    'The portal menu must own keyboard focus after opening');
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(()=>
      !!document.activeElement?.closest('.lane-actions-popover')),true,
      'Tab must stay in the open list popover instead of dismissing it');
    await page.keyboard.press('Shift+Tab');
    assert.equal(await page.evaluate(()=>
      !!document.activeElement?.closest('.lane-actions-popover')),true,
      'Shift+Tab must let users navigate back to earlier list actions');
    await page.keyboard.press('Escape');
    await menu.waitFor({state:'hidden'});
    assert.equal(await trigger.evaluate(el=>document.activeElement===el),true,
      'Escape must restore keyboard focus to the originating list action');
    assert.deepEqual(errors,[]);
  }finally{
    await browser.close();
  }
});
