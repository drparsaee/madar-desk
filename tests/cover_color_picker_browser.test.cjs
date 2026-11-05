'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const esbuild=require('esbuild');
let playwright;
try {playwright=require('playwright');}
catch {
  // Synthetic QA intentionally redirects APPDATA away from real profiles.
  // Resolve the globally installed test runner from the retained user home.
  const home=process.env.USERPROFILE||process.env.HOME||'';
  playwright=require(path.join(home,'AppData','Roaming','npm','node_modules','playwright'));
}

const root=path.resolve(__dirname,'..');
const output=esbuild.buildSync({
  stdin:{contents:`import React from 'react';
    import {createRoot} from 'react-dom/client';
    import {CoverColorPicker} from './src/cover_color_picker.jsx';
    import {CommonColorOptions} from './src/common_color_palette.jsx';
    import './src/cardextras.css';
    import './src/common_color_palette.css';
    window.__coverChanges=[];
    function Fixture(){
      const [value,setValue]=React.useState('#5672CA');
      return React.createElement(CoverColorPicker,{value,
        onChange:color=>{window.__coverChanges.push(color);setValue(color)}});
    }
    window.__commonChanges=[];
    function CommonFixture(){
      const [value,setValue]=React.useState('#5672CA');
      return React.createElement(CommonColorOptions,{value,label:'اولویت',
        onChange:color=>{window.__commonChanges.push(color);setValue(color)}});
    }
    if(document.getElementById('picker'))
      createRoot(document.getElementById('picker')).render(React.createElement(Fixture));
    if(document.getElementById('commonpicker'))
      createRoot(document.getElementById('commonpicker')).render(React.createElement(CommonFixture));`,
    resolveDir:root,sourcefile:'synthetic-picker-entry.jsx',loader:'jsx'},
  bundle:true,write:false,outdir:'synthetic-build',format:'iife',platform:'browser',loader:{'.css':'css'}
}).outputFiles;
const js=output.find(item=>item.path.endsWith('.js')).text;
const css=output.find(item=>item.path.endsWith('.css')).text;

async function measure(page,{width,theme,dir}){
  await page.evaluate(({width,theme,dir})=>{
    document.documentElement.setAttribute('data-theme',theme);
    document.getElementById('fixture').style.width=width+'px';
    document.getElementById('fixture').dir=dir;
  },{width,theme,dir});
  await page.locator('.cover-picker__advanced').evaluate(el=>el.open=true);
  return page.evaluate(()=>{
    const root=document.querySelector('#fixture');
    const picker=document.querySelector('.cover-picker');
    const palette=document.querySelector('.madar-common-colors');
    const swatches=[...palette.querySelectorAll('button')];
    const controls=[...picker.querySelectorAll('button,input,summary,.cover-picker__spectrum')];
    const rect=root.getBoundingClientRect();
    const outside=controls.filter(el=>{
      const b=el.getBoundingClientRect();
      return b.width>0&&(b.left<rect.left-0.5||b.right>rect.right+0.5);
    }).map(el=>({type:el.tagName,label:el.getAttribute('aria-label'),
      left:Math.round(el.getBoundingClientRect().left),right:Math.round(el.getBoundingClientRect().right)}));
    return {width:root.clientWidth,scrollWidth:root.scrollWidth,pickerScroll:picker.scrollWidth,
      paletteColumns:getComputedStyle(palette).gridTemplateColumns,
      presets:palette.querySelectorAll('button').length,
      smallestPreset:Math.round(Math.min(...swatches.map(el=>el.getBoundingClientRect().width))),
      spectrumHeight:Math.round(document.querySelector('.cover-picker__spectrum').getBoundingClientRect().height),
      outside, theme:document.documentElement.dataset.theme,dir:root.dir};
  });
}

test('synthetic Chromium computed geometry: narrow/wide RTL LTR light/dark and keyboard',async(t)=>{
  const browser=await playwright.chromium.launch({channel:'msedge',headless:true});
  t.after(()=>browser.close());
  const page=await browser.newPage({viewport:{width:850,height:850}});
  await page.setContent(`<html dir="rtl"><head><meta charset="utf-8"><style>
    *{box-sizing:border-box}:root{--surface:#fff;--text:#263347;--border:#dce2eb;--accent:#5672ca}
    :root[data-theme="dark"]{--surface:#172238;--text:#e9f1fc;--border:#52627d;--accent:#8db8ff}
    body{padding:20px;background:var(--surface);color:var(--text);font:13px Arial}
    #fixture{min-width:0;max-width:100%;border:1px solid var(--border);padding:10px}
    </style></head><body><main id="fixture" class="cardextras"><div id="picker"></div></main></body></html>`);
  await page.addStyleTag({content:css});
  await page.addScriptTag({content:js});
  await page.locator('.madar-common-colors button').first().waitFor();
  const rows=[];
  for(const width of [180,220,280,360])for(const theme of ['light','dark'])for(const dir of ['rtl','ltr']){
    const item=await measure(page,{width,theme,dir});
    rows.push(item);
    assert.ok(item.scrollWidth<=item.width+1,`horizontal overflow ${JSON.stringify(item)}`);
    assert.equal(item.outside.length,0,`controls overflow ${JSON.stringify(item)}`);
    assert.ok(item.spectrumHeight>=110,`spectrum too short ${JSON.stringify(item)}`);
    assert.ok(item.smallestPreset>=26,`presets too narrow ${JSON.stringify(item)}`);
  }
  console.log('COMPUTED_PICKER_LAYOUT '+JSON.stringify(rows));
  const button=page.getByRole('button',{name:'انتخاب قرمز برای کاور'});
  await button.focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(()=>window.__coverChanges.at(-1)),'#EF4444');
  await page.locator('.cover-picker__advanced>summary').click();
  await page.getByRole('slider',{name:'طیف رنگ کاور'}).focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.locator('.cover-picker__spectrum').count(),1);
  const spectrum=page.getByRole('slider',{name:'اشباع و روشنایی رنگ کاور'});
  await spectrum.focus();
  await page.keyboard.press('ArrowLeft');
  assert.match(await page.evaluate(()=>window.__coverChanges.at(-1)),/^#[A-F0-9]{6}$/);
  await page.mouse.click(20,20); // leave focus and start a pointer check by geometry
  await page.locator('.cover-picker__advanced>summary').click();
  const bounds=await spectrum.boundingBox();
  await page.mouse.move(bounds.x+30,bounds.y+20);
  await page.mouse.down();
  await page.mouse.move(bounds.x+bounds.width-30,bounds.y+bounds.height-20,{steps:3});
  await page.mouse.up();
  assert.match(await page.evaluate(()=>window.__coverChanges.at(-1)),/^#[A-F0-9]{6}$/);
  await page.getByRole('button',{name:'انتخاب سفید برای کاور'}).click();
  await page.locator('.cover-picker__advanced>summary').click();
  await page.getByRole('slider',{name:'طیف رنگ کاور'}).fill('140');
  const before=await spectrum.evaluate(el=>getComputedStyle(el).backgroundImage);
  await page.mouse.click(bounds.x+bounds.width*.8,bounds.y+bounds.height*.2);
  assert.match(await page.evaluate(()=>window.__coverChanges.at(-1)),/^#[A-F0-9]{6}$/);
  assert.notEqual(await page.evaluate(()=>window.__coverChanges.at(-1)),'#FFFFFF');
  assert.match(before,/linear-gradient/);
});

test('shared color disclosure dismisses on outside pointer, Escape and final selection',async(t)=>{
  const browser=await playwright.chromium.launch({channel:'msedge',headless:true});
  t.after(()=>browser.close());
  const page=await browser.newPage({viewport:{width:600,height:700}});
  await page.setContent('<html dir="rtl"><head><meta charset="utf-8"></head><body>'+
    '<section id="parent-editor"><main id="commonpicker"></main><form id="other-form">'+
    '<input id="other-field" aria-label="فیلد دیگر">'+
    '<button type="button" id="outside">بیرون</button></form></section></body></html>');
  await page.addStyleTag({content:css});
  await page.addScriptTag({content:js});
  await page.evaluate(()=>{
    window.__parentEscapes=0;
    document.getElementById('parent-editor').addEventListener('keydown',event=>{
      if(event.key==='Escape')window.__parentEscapes++;
    });
  });
  const outer=page.locator('.madar-common-colors__details');
  const outerSummary=outer.locator(':scope > summary');
  const advanced=outer.locator('.cover-picker__advanced');
  await outerSummary.click();
  assert.equal(await outer.evaluate(el=>el.open),true);
  await page.locator('#other-field').click();
  await page.locator('#other-field').fill('متن آزمایشی');
  assert.equal(await outer.evaluate(el=>el.open),false,'outside input closes picker without changing the form');
  assert.equal(await page.locator('#other-field').inputValue(),'متن آزمایشی');

  await outerSummary.click();
  await advanced.locator('summary').click();
  assert.equal(await advanced.evaluate(el=>el.open),true);
  await page.locator('.cover-picker__custom input[type=text]').focus();
  await page.keyboard.press('Escape');
  assert.equal(await advanced.evaluate(el=>el.open),false,'first Escape closes nested custom picker');
  assert.equal(await outer.evaluate(el=>el.open),true,'parent remains open after first Escape');
  await page.keyboard.press('Escape');
  assert.equal(await outer.evaluate(el=>el.open),false,'second Escape closes parent picker');
  assert.equal(await outerSummary.evaluate(el=>document.activeElement===el),true);
  assert.equal(await page.evaluate(()=>window.__parentEscapes),0,
    'color picker Escape does not bubble into parent editor');

  await outerSummary.click();
  await page.getByRole('button',{name:'انتخاب سبز برای اولویت'}).click();
  assert.equal(await outer.evaluate(el=>el.open),false,'preset selection dismisses color menu');
  assert.equal(await outerSummary.evaluate(el=>document.activeElement===el),true,
    'keyboard focus returns to the color menu summary');
  assert.deepEqual(await page.evaluate(()=>window.__commonChanges),['#22C55E']);

  await outerSummary.click();
  await advanced.locator('summary').click();
  await advanced.locator('.cover-picker__hue input').fill('140');
  assert.equal(await outer.evaluate(el=>el.open),true,'hue adjustment keeps disclosure available');
  assert.equal(await advanced.evaluate(el=>el.open),true);
  await advanced.locator('.cover-picker__custom input[type=text]').fill('#A1B2C3');
  await advanced.getByRole('button',{name:'اعمال'}).click();
  assert.equal(await outer.evaluate(el=>el.open),false,'Apply closes parent picker');
  assert.equal(await advanced.evaluate(el=>el.open),false,'Apply closes custom picker');
  assert.equal(await page.evaluate(()=>window.__commonChanges.at(-1)),'#A1B2C3');

  await outerSummary.click();
  await advanced.locator('summary').click();
  await advanced.locator('input[type=color]').fill('#ABCDEF');
  assert.equal(await outer.evaluate(el=>el.open),false,'native color change dismisses menu');
  assert.equal(await advanced.evaluate(el=>el.open),false);
  assert.equal(await page.evaluate(()=>window.__commonChanges.at(-1)),'#ABCDEF');
  await page.locator('#other-field').focus();
  await page.keyboard.press('Escape');
  assert.equal(await page.evaluate(()=>window.__parentEscapes),1,
    'closed picker does not intercept unrelated form Escape');
});
