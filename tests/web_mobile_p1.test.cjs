'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const net=require('node:net');

const root=path.resolve(__dirname,'..');
const chrome=[process.env.MADAR_CHROME_PATH,
  path.join(process.env.PROGRAMFILES||'C:\\Program Files','Google','Chrome','Application','chrome.exe'),
  path.join(process.env.LOCALAPPDATA||'','Google','Chrome','Application','chrome.exe')]
  .find(value=>value&&fs.existsSync(value));
let playwright;
for(const name of ['playwright',path.join(process.env.APPDATA||'','npm','node_modules','playwright')]){
  try{playwright=require(name);break;}catch{}
}
async function freePort(){
  return new Promise((resolve,reject)=>{
    const server=net.createServer();
    server.once('error',reject);
    server.listen(0,'127.0.0.1',()=>{
      const port=server.address().port;
      server.close(error=>error?reject(error):resolve(port));
    });
  });
}

test('P1 web mobile: compact view, modal and keyboard drawer stay accessible without viewport overflow',
  {skip:!chrome||!playwright||!fs.existsSync(path.join(root,'dist-web','index.html')),
    timeout:85000},async()=>{
    const {preview}=await import('vite');
    const server=await preview({root,mode:'web',build:{outDir:'dist-web'},
      preview:{host:'127.0.0.1',port:await freePort(),strictPort:true}});
    let browser;
    try{
      browser=await playwright.chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({locale:'fa-IR'});
      const page=await context.newPage();
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      for(const width of [320,375,430,768]){
        await page.setViewportSize({width,height:730});
        await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
        await page.locator('.web-pwa-banner').waitFor();
        const sizes=await page.evaluate(()=>{
          const banner=document.querySelector('.web-pwa-banner');
          const rect=banner.getBoundingClientRect();
          return {doc:document.documentElement.scrollWidth,
            viewport:innerWidth,bannerLeft:rect.left,bannerRight:rect.right};
        });
        assert.ok(sizes.doc<=width+1,'Mobile app caused global horizontal scrolling: '+JSON.stringify(sizes));
        assert.ok(sizes.bannerLeft>=-1&&sizes.bannerRight<=width+1,
          'PWA status banner is not within viewport: '+JSON.stringify(sizes));
        const connect=page.locator('.web-pwa-banner__actions button').last();
        await connect.click();
        const dialog=page.locator('.web-sync-dialog');
        await dialog.waitFor();
        const rect=await dialog.evaluate(e=>{
          const r=e.getBoundingClientRect();
          return {left:r.left,right:r.right,width:r.width};
        });
        assert.ok(rect.left>=-1&&rect.right<=width+1,'Sync modal clips on narrow mobile: '+JSON.stringify({width,...rect}));
        await page.getByRole('button',{name:'بستن اتصال آنلاین'}).click();
        const nav=page.locator('.mobile-nav-toggle');
        await nav.click();
        await page.locator('#madar-sidebar.sidebar--mobile-open').waitFor();
        assert.equal(await nav.getAttribute('aria-expanded'),'true');
        await page.keyboard.press('Escape');
        await page.locator('#madar-sidebar:not(.sidebar--mobile-open)').waitFor();
        assert.equal(await nav.getAttribute('aria-expanded'),'false');
      }
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{
      if(browser)await browser.close();
      await new Promise(resolve=>server.httpServer.close(resolve));
    }
  });
