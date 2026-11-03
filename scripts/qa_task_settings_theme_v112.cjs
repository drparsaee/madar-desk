'use strict';
// Real Chromium UI with browser-local synthetic task data (no desktop bridge).
const assert=require('node:assert/strict');
const path=require('node:path');
const net=require('node:net');
const {chromium}=require(path.join(process.env.APPDATA,'npm','node_modules','playwright'));
const root=path.resolve(__dirname,'..');
const browserPath='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
async function freePort(){
  const sock=net.createServer();
  await new Promise(resolve=>sock.listen(0,'127.0.0.1',resolve));
  const port=sock.address().port;
  await new Promise(resolve=>sock.close(resolve));
  return port;
}
async function main(){
  const {preview}=await import('vite');
  const server=await preview({root,logLevel:'error',
    preview:{host:'127.0.0.1',port:await freePort(),strictPort:true}});
  let browser;
  try{
    browser=await chromium.launch({headless:true,executablePath:browserPath});
    const page=await browser.newPage({viewport:{width:1360,height:900}});
    page.setDefaultTimeout(8000);
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(()=>{
      localStorage.setItem('madar-ui-theme:solo:local','dark');
      localStorage.setItem('madar-ui-theme','dark');
    });
    await page.goto(new URL('index.html',server.resolvedUrls.local[0]).href,
      {waitUntil:'domcontentloaded'});
    await page.getByRole('button',{name:'تنظیمات مدار'}).waitFor({timeout:15000});
    await page.getByRole('button',{name:'تنظیمات مدار'}).click();
    const modal=page.getByRole('dialog',{name:'تنظیمات مدار'});
    await modal.waitFor({timeout:7000});
    const personal=modal.getByRole('group',{name:'تم فعلی من'});
    const shared=modal.getByRole('group',{name:'تم پیش‌فرض مشترک کاربران'});
    assert.equal(await personal.getByRole('button',{name:/تاریک/}).getAttribute('aria-pressed'),'true');
    await personal.getByRole('button',{name:/روشن/}).click();
    const active=await page.evaluate(()=>({
      scope:localStorage.getItem('madar-ui-theme:solo:local'),
      document:document.documentElement.dataset.theme
    }));
    assert.deepEqual(active,{scope:'light',document:'light'});
    assert.equal(await personal.getByRole('button',{name:/روشن/}).getAttribute('aria-pressed'),'true');
    assert.equal(await shared.getByRole('button',{name:/پیش‌فرض تاریک/}).getAttribute('aria-pressed'),'true',
      'shared default remains independent of personal theme');
    assert.equal(await shared.getByRole('button',{name:/پیش‌فرض روشن/}).getAttribute('aria-pressed'),'false');
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({status:'PASS',checks:7,scope:active.scope,
      sharedDefault:'dark',errors,mode:'mock task manager browser localStorage'}));
  }finally{
    if(browser)await browser.close();
    await new Promise(resolve=>server.httpServer.close(resolve));
  }
}
main().catch(error=>{console.error(error);process.exitCode=1});
