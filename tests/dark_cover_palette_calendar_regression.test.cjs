'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
let playwright;
try{playwright=require('playwright');}
catch{playwright=require(path.join(process.env.USERPROFILE||process.env.HOME,
  'AppData','Roaming','npm','node_modules','playwright'));}

const browser=()=>playwright.chromium.launch({channel:'msedge',headless:true});
const css=file=>fs.readFileSync(path.join(root,'src',file),'utf8');
const linear=n=>n/255<=.04045?n/255/12.92:((n/255+.055)/1.055)**2.4;
const luminance=value=>{
  const digits=value.match(/[\d.]+/g).slice(0,3).map(Number).map(linear);
  return .2126*digits[0]+.7152*digits[1]+.0722*digits[2];
};
const ratio=(a,b)=>{
  const x=luminance(a),y=luminance(b);
  return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);
};

test('calendar today follows local civil day, not the previous UTC date',()=>{
  const input=`import {localTodayISO} from './src/calendar_today.js';
    console.log(localTodayISO(new Date('2026-11-02T22:20:00Z')))`;
  const asia=spawnSync(process.execPath,['--input-type=module','-e',input],{
    cwd:root,encoding:'utf8',env:{...process.env,TZ:'Asia/Tehran'}});
  assert.equal(asia.status,0,asia.stderr);
  assert.equal(asia.stdout.trim(),'2026-11-03');
  const utc=spawnSync(process.execPath,['--input-type=module','-e',input],{
    cwd:root,encoding:'utf8',env:{...process.env,TZ:'UTC'}});
  assert.equal(utc.status,0,utc.stderr);
  assert.equal(utc.stdout.trim(),'2026-11-02');
});

test('solid cover paints entire card regardless of dark mode and priority style',async(t)=>{
  const b=await browser();t.after(()=>b.close());
  const page=await b.newPage();
  await page.setContent('<html data-theme="dark"><body><section class="kanban">'+
    '<div class="task-card task-card--cover-full priority-effect-solid" '+
    'style="--card-cover-color:#EAB308;--card-cover-contrast:#152238">'+
    '<header class="task-card-head"><b class="task-title">عنوان کارت</b></header>'+
    '<span class="task-description">توضیحات</span></div></section>'+
    '<div class="drawer"><details class="task-optional-block" open>'+
    '<div class="edit-section"><div class="cardextras task-card-custom-fields">'+
    '<h3>فیلدهای سفارشی</h3><p class="cardextras-muted">فیلد سفارشی تعریف نشده است.</p>'+
    '</div></div></details></div></body></html>');
  await page.addStyleTag({content:css('styles.css').replace(/^@import[^;]+;/gm,'')});
  await page.addStyleTag({content:css('priorities.css')});
  await page.addStyleTag({content:css('kanban_compact.css')});
  await page.addStyleTag({content:css('task_editor_compact.css')});
  await page.addStyleTag({content:css('cardextras.css')});
  for(const theme of ['dark','light']){
    await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
    const colors=await page.evaluate(()=>{
      const card=document.querySelector('.task-card');
      const text=card.querySelector('.task-title');
      const muted=document.querySelector('.cardextras-muted');
      const section=document.querySelector('.task-optional-block');
      return {card:getComputedStyle(card).backgroundColor,text:getComputedStyle(text).color,
        muted:getComputedStyle(muted).color,section:getComputedStyle(section).backgroundColor};
    });
    assert.equal(colors.card,'rgb(234, 179, 8)',theme+' full cover must fill card');
    assert.equal(colors.text,'rgb(21, 34, 56)',theme+' cover text must contrast');
    if(theme==='dark')assert.ok(ratio(colors.muted,colors.section)>=4.5,
      'dark empty custom-field message lacks contrast: '+JSON.stringify(colors));
  }
});

test('all common color selectors share cover picker presets, spectrum and hex',async(t)=>{
  const output=esbuild.buildSync({
    stdin:{contents:`import React from 'react';import{createRoot}from'react-dom/client';
      import{CommonColorOptions}from'./src/common_color_palette.jsx';
      import './src/common_color_palette.css';
      window.colors=[];function Fixture(){const[v,set]=React.useState('#5672CA');
      return React.createElement(CommonColorOptions,{value:v,label:'اولویت',onChange:c=>{
      window.colors.push(c);set(c)}})}
      createRoot(document.getElementById('root')).render(React.createElement(Fixture));`,
      resolveDir:root,sourcefile:'color-unified-entry.jsx',loader:'jsx'},
    write:false,bundle:true,outdir:'color-unified-build',platform:'browser',format:'iife',
    loader:{'.css':'css'}}).outputFiles;
  const b=await browser();t.after(()=>b.close());
  const page=await b.newPage({viewport:{width:600,height:800}});
  await page.setContent('<html data-theme="dark" dir="rtl"><body>'+
    '<div id="root" style="width:270px"></div></body></html>');
  await page.addStyleTag({content:output.find(item=>item.path.endsWith('.css')).text});
  await page.addScriptTag({content:output.find(item=>item.path.endsWith('.js')).text});
  const selector=page.locator('.madar-common-colors__details');
  await selector.locator('summary').first().click();
  assert.equal(await selector.locator('.madar-common-colors__swatch').count(),16);
  await selector.locator('.cover-picker__advanced>summary').click();
  assert.equal(await selector.locator('.cover-picker__spectrum').count(),1);
  assert.equal(await selector.locator('.cover-picker__hue input[type="range"]').count(),1);
  await selector.locator('.cover-picker__custom input[type="text"]').fill('#A1B2C3');
  await selector.locator('.cover-picker__custom button').click();
  assert.equal(await page.evaluate(()=>window.colors.at(-1)),'#A1B2C3');
  assert.ok(await page.evaluate(()=>document.getElementById('root').scrollWidth<=270),
    'unified picker overflows its narrow host');
});
