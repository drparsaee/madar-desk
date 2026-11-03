'use strict';
/** Real browser, purely synthetic task state, no desktop host or live profile. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const root=path.resolve(__dirname,'..');
const browserPath='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
// The safe QA runner intentionally replaces APPDATA; this tool installation is
// a read-only package location and never an application data/profile input.
const playwrightPath='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const ready=fs.existsSync(browserPath)&&fs.existsSync(playwrightPath);
const stages=[{id:'inbox',label:'ورودی',color:'#546b86',subtitle:''}];
const fixture={version:1,projects:[],workspaces:[],boards:[],tasks:[],stages,
  settings:{theme:'dark',themeForAllUsers:false,costDefault:false}};
const freePort=()=>new Promise((resolve,reject)=>{
  const socket=net.createServer();socket.once('error',reject);
  socket.listen(0,'127.0.0.1',()=>{const port=socket.address().port;
    socket.close(error=>error?reject(error):resolve(port));});
});

test('quick theme button and settings remain aligned; shared theme persists only when admin enables it',
  {skip:!ready,timeout:60000},async()=>{
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',
      server:{host:'127.0.0.1',port:await freePort(),strictPort:true}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:browserPath});
      const page=await browser.newPage({viewport:{width:1360,height:820},locale:'fa-IR'});
      page.setDefaultTimeout(10000);
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.addInitScript(state=>localStorage.setItem('madar-preview',JSON.stringify(state)),fixture);
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await page.getByRole('button',{name:'تنظیمات مدار'}).waitFor();
      assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'dark');
      await page.getByRole('button',{name:'تنظیمات مدار'}).click();
      let dialog=page.getByRole('dialog',{name:'تنظیمات مدار'});
      assert.equal(await dialog.getByRole('button',{name:/تاریک/}).getAttribute('aria-pressed'),'true');
      await dialog.getByRole('button',{name:'بستن'}).click();
      await page.getByRole('button',{name:'انتخاب تم روشن'}).click();
      assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'light');
      await page.getByRole('button',{name:'تنظیمات مدار'}).click();
      dialog=page.getByRole('dialog',{name:'تنظیمات مدار'});
      assert.equal(await dialog.getByRole('button',{name:/روشن/}).getAttribute('aria-pressed'),'true');
      assert.equal(await dialog.getByRole('checkbox',{name:/اعمال تم برای همهٔ کاربران/}).isChecked(),false);
      await dialog.getByRole('checkbox',{name:/اعمال تم برای همهٔ کاربران/}).check();
      assert.equal(await dialog.getByRole('checkbox',{name:/اعمال تم برای همهٔ کاربران/}).isChecked(),true);
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')||'{}').settings?.themeForAllUsers===true);
      const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('madar-preview')));
      assert.equal(saved.settings.themeForAllUsers,true);
      assert.equal(saved.settings.theme,'light');
      await dialog.getByRole('button',{name:/تاریک/}).click();
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')||'{}').settings?.theme==='dark');
      assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'dark');
      assert.deepEqual(errors,[]);
    } finally{
      await browser?.close();
      await server.close();
    }
  });
