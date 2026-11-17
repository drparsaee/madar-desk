'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const esbuild=require('esbuild');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPath='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const browserAvailable=fs.existsSync(chrome)&&fs.existsSync(playwrightPath);

test('interactive LAN account form saves default viewer/editor to the real host API shape and enforces admin UI', {
  skip:!browserAvailable,timeout:45000,
},async()=>{
  const {chromium}=require(playwrightPath);
  const harness=`
    import React,{useState} from 'react';
    import {createRoot} from 'react-dom/client';
    import {LanPanel,LAN_BUILTIN_DISPLAY_ROLES} from './src/features.jsx';
    const saved=[{username:'owner',role:'admin',displayRole:'superadmin',projects:null}];
    window.hostCalls=[];
    function Fixture(){
      const [status,setStatus]=useState({mode:'server',port:48370,
        user:{role:'admin',username:'owner'},transport:'https'});
      window.changeSession=(mode,role)=>setStatus({
        mode,port:48370,transport:'https',user:{role,username:'owner'}});
      const api={
        lanUsers:async()=>{if(status.mode==='solo'||status.user.role!=='admin')throw Error('Permission denied');return [...saved];},
        lanDisplayRoles:async()=>LAN_BUILTIN_DISPLAY_ROLES,
        lanSaveUser:async(payload)=>{
          window.hostCalls.push(payload);
          if(status.mode==='solo'||status.user.role!=='admin')throw Error('Permission denied');
          if('displayMode' in payload&&payload.displayMode===null)throw Error('User display mode must be valid');
          if('displayFeatures' in payload&&payload.displayFeatures===null)throw Error('User display features must be a list');
          const index=saved.findIndex(user=>user.username===payload.username);
          const next=index>=0?{...saved[index],...payload}:{...payload};
          if(index>=0)saved[index]=next;else saved.push(next);
          return next;
        },
      };
      return React.createElement(LanPanel,{
        api,projects:[{id:'p-sample',name:'پروژه نمونه'}],initialView:'users',status,
        onClose:()=>{},onRefresh:async()=>{},onConnected:async()=>{},
      });
    }
    createRoot(document.getElementById('root')).render(React.createElement(Fixture));
  `;
  const script=esbuild.buildSync({
    stdin:{contents:harness,resolveDir:root,sourcefile:'madar_lan_user_fixture.jsx',loader:'jsx'},
    bundle:true,write:false,platform:'browser',format:'iife',loader:{'.css':'empty'},
  }).outputFiles[0].text;
  const browser=await chromium.launch({headless:true,executablePath:chrome});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900},locale:'fa-IR'});
    const pageErrors=[];
    page.on('pageerror',error=>pageErrors.push(error.message));
    await page.setContent('<html lang="fa" dir="rtl"><body><div id="root"></div></body></html>');
    await page.addScriptTag({content:script});
    const dialog=page.getByRole('dialog',{name:'شبکه محلی و کاربران'});
    await dialog.getByText('ساخت حساب جدید').waitFor();
    const fillAccount=async(name,role,displayRole)=>{
      await dialog.getByLabel('نام کاربری انگلیسی').fill(name);
      await dialog.getByLabel('رمز (حداقل ۱۰ نویسه)').fill('staff-password-2026');
      await dialog.getByLabel('مجوز فنی (مستقل از قالب نمایش)').selectOption(role);
      await dialog.getByLabel('قالب نقش و امکانات قابل نمایش').selectOption(displayRole);
      await dialog.getByRole('button',{name:'ایجاد حساب کاربر'}).click();
      await dialog.getByText('@'+name).waitFor();
    };
    await fillAccount('worker-view','viewer','employee');
    await fillAccount('worker-edit','editor','middle');
    const calls=await page.evaluate(()=>window.hostCalls);
    assert.equal(calls.length,2);
    assert.deepEqual(calls.map(x=>[x.username,x.role,x.displayRole]),[
      ['worker-view','viewer','employee'],['worker-edit','editor','middle']]);
    assert.equal(calls.every(x=>!('displayMode' in x)&&!('displayFeatures' in x)),true,
      'default template must inherit host role without invalid null overrides');
    assert.equal(calls[0].projects,null);
    const aiPanel=dialog.getByRole('region',{name:'داشبورد کنترل هوش مصنوعی کاربران'});
    assert.equal(await aiPanel.getByRole('button',{name:'فعال کردن AI برای worker-view'}).isDisabled(),true);
    await aiPanel.getByRole('button',{name:'فعال کردن AI برای worker-edit'}).click();
    await aiPanel.getByRole('button',{name:'غیرفعال کردن AI برای worker-edit'}).waitFor();
    const grantCall=(await page.evaluate(()=>window.hostCalls))[2];
    assert.deepEqual(grantCall,{username:'worker-edit',aiEnabled:true});
    await aiPanel.getByRole('button',{name:'غیرفعال کردن AI برای worker-edit'}).click();
    await aiPanel.getByRole('button',{name:'فعال کردن AI برای worker-edit'}).waitFor();
    assert.deepEqual((await page.evaluate(()=>window.hostCalls))[3],
      {username:'worker-edit',aiEnabled:false});
    await page.evaluate(()=>window.changeSession('server','viewer'));
    await dialog.getByText('ساخت حساب جدید').waitFor({state:'hidden'});
    await page.evaluate(()=>window.changeSession('solo','admin'));
    await dialog.getByText('تعریف کاربران و تعیین دسترسی پس از راه‌اندازی میزبان').waitFor();
    assert.equal(await dialog.getByRole('button',{name:'ایجاد حساب کاربر'}).count(),0);
    assert.equal((await page.evaluate(()=>window.hostCalls)).length,4);
    assert.deepEqual(pageErrors,[]);
  }finally{
    await browser.close();
  }
});
