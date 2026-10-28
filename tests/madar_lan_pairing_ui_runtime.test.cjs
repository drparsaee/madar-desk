'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPath='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable=fs.existsSync(chrome)&&fs.existsSync(playwrightPath);
const entry=path.join(root,'src/features.jsx');
const bundle=esbuild.buildSync({entryPoints:[entry],bundle:true,write:false,platform:'node',
  format:'cjs',jsx:'automatic',loader:{'.css':'empty'},
  external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const loaded=new Module(path.join(root,'src','lan-pairing-test.cjs'),module);
loaded.filename=path.join(root,'src','lan-pairing-test.cjs');
loaded.paths=Module._nodeModulePaths(root);
loaded._compile(bundle,loaded.filename);
const {LanPanel,lanDiscoveredHttpsHosts}=loaded.exports;

test('LAN discovery rejects insecure or malformed endpoints and never infers trust',()=>{
  const rows=lanDiscoveredHttpsHosts([
    {name:'Safe host',url:'https://192.168.1.10:48370',fingerprint:'A'.repeat(64)},
    {name:'old http',url:'http://192.168.1.11:48370',fingerprint:'B'.repeat(64)},
    {name:'trick URL',url:'https://user:pass@192.168.1.12:48370'},
    {name:'redirect path',url:'https://192.168.1.13:48370/login'},
    {name:'invalid URL',url:'javascript:alert(1)'},
    {name:'duplicate',url:'https://192.168.1.10:48370',fingerprint:'C'.repeat(64)},
    {name:'default secure port',url:'https://192.168.1.15:443'},
  ]);
  assert.deepEqual(rows,[
    {name:'Safe host',url:'https://192.168.1.10:48370',fingerprint:'A'.repeat(64)},
    {name:'default secure port',url:'https://192.168.1.15:443',fingerprint:''},
  ]);
});

test('LAN simple UI stays honest when discovery and service APIs are unavailable',()=>{
  const html=renderToStaticMarkup(React.createElement(LanPanel,{
    api:{},projects:[],initialView:'connection',
    status:{mode:'solo',user:{role:'admin',username:'local'}},
    onClose:()=>{},onRefresh:async()=>{},onConnected:async()=>{},
  }));
  assert.match(html,/جست‌وجوی میزبان در شبکه/);
  assert.match(html,/تنظیمات پیشرفته: میزبان و اتصال دستی/);
  assert.match(html,/HTTPS با گواهی و کلید PEM/);
  assert.doesNotMatch(html,/اثر انگشت اعلام‌شده در شبکه \(تأییدنشده\)/);
  assert.doesNotMatch(html,/سرویس میزبان طبق گزارش برنامه فعال است/);
});

test('Chromium LAN pairing requires independently verified fingerprint; discovery never auto-joins', {
  skip:!runnable,timeout:45000,
},async()=>{
  const {chromium}=require(playwrightPath);
  const fixture=`
    import React,{useState} from 'react';
    import {createRoot} from 'react-dom/client';
    import {LanPanel} from './src/features.jsx';
    window.__lanCalls=[];
    window.__discoveryRows=[
      {name:'میزبان امن یک',url:'https://192.168.1.20:48370',fingerprint:'A'.repeat(64)},
      {name:'HTTP ناامن',url:'http://192.168.1.21:48370',fingerprint:'C'.repeat(64)},
      {name:'میزبان امن دو',url:'https://192.168.1.22:48370',fingerprint:'C'.repeat(64)},
    ];
    function Fixture(){
      const [status,setStatus]=useState({mode:'solo',user:{role:'admin',username:'local'}});
      const [api]=useState(()=>({
        lanDiscover:async()=>{window.__lanCalls.push(['discover']);return window.__discoveryRows;},
        hostServiceStatus:async()=>({supported:false,status:'unsupported'}),
        lanJoin:async(...args)=>{
          window.__lanCalls.push(['join',...args]);
          setStatus({mode:'client',user:{role:'editor',username:args[1]},
            transport:'https',url:args[0]});
          return {mode:'client'};
        },
      }));
      return React.createElement(LanPanel,{
        api,projects:[],status,initialView:'connection',
        onClose:()=>{},onRefresh:async()=>{},onConnected:async()=>{},
      });
    }
    createRoot(document.getElementById('root')).render(React.createElement(Fixture));
  `;
  const script=esbuild.buildSync({
    stdin:{contents:fixture,resolveDir:root,sourcefile:'madar_lan_pairing_fixture.jsx',loader:'jsx'},
    bundle:true,platform:'browser',format:'iife',write:false,loader:{'.css':'empty'},
  }).outputFiles[0].text;
  const css=fs.readFileSync(path.join(root,'src/settings_density.css'),'utf8');
  const browser=await chromium.launch({headless:true,executablePath:chrome});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900},locale:'fa-IR'});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.setContent(`<html lang="fa" dir="rtl"><head><style>
      body{margin:0;font:14px sans-serif}.dialog{max-height:96vh;overflow:auto}
      .lan-modal{margin:10px auto}.lan-modes{display:grid}
      .setting-block{display:grid}.dialog-body{overflow:auto}.overlay{width:100%}
      ${css}
    </style></head><body><div id="root"></div></body></html>`);
    await page.addScriptTag({content:script});
    const dialog=page.getByRole('dialog',{name:'شبکه محلی و کاربران'});
    const pairing=dialog.getByRole('region',{name:'اتصال ساده به شبکه'});
    await pairing.getByRole('button',{name:/میزبان امن یک/}).waitFor();
    assert.equal(await pairing.getByText('HTTP ناامن').count(),0);
    assert.match(await pairing.innerText(),/استعلام سرویس ویندوز در این محیط پشتیبانی نمی‌شود/);
    assert.equal((await page.evaluate(()=>window.__lanCalls)).filter(item=>item[0]==='join').length,0);
    await pairing.getByRole('button',{name:/میزبان امن یک/}).click();
    assert.equal(await pairing.getByLabel('نشانی HTTPS انتخاب‌شده').inputValue(),
      'https://192.168.1.20:48370');
    assert.equal(await pairing.getByLabel('اثر انگشت بررسی‌شده میزبان').inputValue(),'',
      'the broadcast fingerprint must never populate the verified pin');
    assert.match(await pairing.innerText(),/اثر انگشت اعلام‌شده در شبکه \(تأییدنشده\)/);
    const advanced=dialog.locator('.lan-advanced');
    await advanced.locator('summary').click();
    assert.equal(await advanced.getByLabel('نشانی سرور').inputValue(),
      'https://192.168.1.20:48370','discovered HTTPS URL is also filled for manual pairing');
    assert.equal(await advanced.getByLabel('اثر انگشت کامل SHA-256 گواهی سرور').inputValue(),'');
    assert.equal(await advanced.getByLabel('HTTPS با گواهی و کلید PEM').count(),1,
      'manual HTTPS host setup is still available');
    await advanced.locator('summary').click();
    await pairing.getByLabel('نام کاربری شبکه').fill('operator');
    await pairing.getByLabel('رمز حساب شبکه').fill('operator-strong-password');
    const join=pairing.getByRole('button',{name:'اتصال امن و دریافت کارها'});
    assert.equal(await join.isEnabled(),false);
    await pairing.getByLabel('اثر انگشت بررسی‌شده میزبان').fill('B'.repeat(64));
    assert.equal(await join.isEnabled(),false);
    await pairing.getByLabel('اثر انگشت واردشده را جداگانه با رایانه میزبان تطبیق دادم.').check();
    assert.equal(await join.isEnabled(),true);
    await pairing.getByRole('button',{name:/میزبان امن دو/}).click();
    assert.equal(await pairing.getByLabel('اثر انگشت بررسی‌شده میزبان').inputValue(),'');
    assert.equal(await pairing.getByLabel('رمز حساب شبکه').inputValue(),'');
    assert.equal(await join.isEnabled(),false,'changing host resets verified pin');
    await pairing.getByRole('button',{name:/میزبان امن یک/}).click();
    await pairing.getByLabel('رمز حساب شبکه').fill('operator-strong-password');
    await pairing.getByLabel('اثر انگشت بررسی‌شده میزبان').fill('B'.repeat(64));
    await pairing.getByLabel('اثر انگشت واردشده را جداگانه با رایانه میزبان تطبیق دادم.').check();
    // Mobile layout keeps fields on a single line and within viewport.
    await page.setViewportSize({width:480,height:790});
    assert.equal(await pairing.evaluate(el=>getComputedStyle(el).direction),'rtl');
    const grid=pairing.locator('.lan-pairing__verify .setting-grid');
    const columns=await grid.evaluate(el=>getComputedStyle(el).gridTemplateColumns);
    assert.equal(columns.trim().split(/\s+/).length,1);
    const bounds=await pairing.boundingBox();
    assert.ok(bounds&&bounds.x>=-2&&bounds.x+bounds.width<=482,JSON.stringify(bounds));
    await join.click();
    const calls=await page.evaluate(()=>window.__lanCalls.filter(item=>item[0]==='join'));
    assert.deepEqual(calls,[['join','https://192.168.1.20:48370','operator',
      'operator-strong-password','B'.repeat(64)]]);
    await dialog.getByText('متصل به سرور').waitFor();
    assert.deepEqual(errors,[]);
  }finally{
    await browser.close();
  }
});
