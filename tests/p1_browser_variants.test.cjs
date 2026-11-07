'use strict';
// P1 cross-environment matrix on a REAL Chrome/Chromium process running on
// the Windows 10 host. User-Agent strings do NOT emulate a Windows OS.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const net=require('node:net');
const path=require('node:path');

const root=path.resolve(__dirname,'..');
const chrome=[process.env.MADAR_CHROME_PATH,
  path.join(process.env.PROGRAMFILES||'C:\\Program Files','Google','Chrome','Application','chrome.exe'),
  path.join(process.env.LOCALAPPDATA||'','Google','Chrome','Application','chrome.exe')]
  .find(value=>value&&fs.existsSync(value));
let playwright;
for(const name of ['playwright',path.join(process.env.APPDATA||'','npm','node_modules','playwright')]){
  try{playwright=require(name);break;}catch{/* Try global installed Playwright. */}
}
async function freePort(){
  return new Promise((resolve,reject)=>{
    const socket=net.createServer();
    socket.once('error',reject);
    socket.listen(0,'127.0.0.1',()=>{
      const port=socket.address().port;
      socket.close(error=>error?reject(error):resolve(port));
    });
  });
}

const cases=[
  {name:'compact dark Iran',width:320,height:640,locale:'fa-IR',timezoneId:'Asia/Tehran',colorScheme:'dark',reducedMotion:'reduce',touch:true,dpr:1},
  {name:'small light Berlin',width:375,height:812,locale:'fa-IR',timezoneId:'Europe/Berlin',colorScheme:'light',reducedMotion:'no-preference',touch:true,dpr:2},
  {name:'iPhone scale Tokyo',width:390,height:844,locale:'en-US',timezoneId:'Asia/Tokyo',colorScheme:'dark',reducedMotion:'reduce',touch:true,dpr:3},
  {name:'large compact US time',width:430,height:932,locale:'fa-IR',timezoneId:'America/Los_Angeles',colorScheme:'light',reducedMotion:'no-preference',touch:true,dpr:2},
  {name:'tablet portrait',width:768,height:1024,locale:'fa-IR',timezoneId:'Europe/Berlin',colorScheme:'dark',reducedMotion:'reduce',touch:true,dpr:1},
  // Legacy OS identification only. Chrome still executes on the Win10 host.
  {name:'Windows 7 user-agent only',width:1024,height:768,locale:'fa-IR',timezoneId:'UTC',colorScheme:'light',reducedMotion:'no-preference',touch:false,dpr:1,
    userAgent:'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
  {name:'desktop high contrast scheme',width:1366,height:768,locale:'en-US',timezoneId:'America/New_York',colorScheme:'dark',reducedMotion:'reduce',touch:false,dpr:1},
  {name:'desktop large',width:1920,height:1080,locale:'fa-IR',timezoneId:'UTC',colorScheme:'light',reducedMotion:'no-preference',touch:false,dpr:1},
];

test('P1 multi-variant Chromium matrix: eight viewport/locale/timezone/theme/motion/touch contexts',
  {timeout:120000},async()=>{
    assert.ok(chrome,'Chrome executable required: cannot call this a browser acceptance without Chrome');
    assert.ok(playwright,'Playwright required: cannot replace actual browser acceptance with a skip');
    assert.ok(fs.existsSync(path.join(root,'dist-web','index.html')),'Build dist-web first');
    const {preview}=await import('vite');
    const server=await preview({root,mode:'web',build:{outDir:'dist-web'},
      preview:{host:'127.0.0.1',port:await freePort(),strictPort:true}});
    let browser;
    const observed=[];
    try{
      browser=await playwright.chromium.launch({headless:true,executablePath:chrome});
      for(const config of cases){
        const context=await browser.newContext({
          viewport:{width:config.width,height:config.height},
          locale:config.locale,timezoneId:config.timezoneId,
          colorScheme:config.colorScheme,reducedMotion:config.reducedMotion,
          hasTouch:config.touch,isMobile:config.touch&&config.width<500,
          deviceScaleFactor:config.dpr,
          ...(config.userAgent?{userAgent:config.userAgent}:{})
        });
        try{
          const page=await context.newPage(),errors=[];
          page.on('pageerror',error=>errors.push(error.message));
          await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
          await page.locator('.web-pwa-banner').waitFor();
          const computed=await page.evaluate(()=>({
            dir:document.documentElement.dir,
            scrollWidth:document.documentElement.scrollWidth,
            innerWidth:innerWidth,
            locale:navigator.language,
            zone:Intl.DateTimeFormat().resolvedOptions().timeZone,
            dark:matchMedia('(prefers-color-scheme: dark)').matches,
            reduced:matchMedia('(prefers-reduced-motion: reduce)').matches,
            hasTouch:'ontouchstart' in window,
            ua:navigator.userAgent
          }));
          assert.ok(computed.scrollWidth<=config.width+2,
            config.name+' global horizontal overflow: '+JSON.stringify(computed));
          assert.equal(computed.zone,config.timezoneId,config.name+' timezone');
          assert.equal(computed.dark,config.colorScheme==='dark',config.name+' theme');
          assert.equal(computed.reduced,config.reducedMotion==='reduce',config.name+' motion');
          if(config.userAgent)assert.match(computed.ua,/Windows NT 6\.1/);
          const connect=page.locator('.web-pwa-banner__actions button').last();
          await connect.click();
          const dialog=page.locator('.web-sync-dialog');
          await dialog.waitFor();
          const rect=await dialog.evaluate(e=>{
            const r=e.getBoundingClientRect();
            return {left:r.left,right:r.right};
          });
          assert.ok(rect.left>=-2&&rect.right<=config.width+2,
            config.name+' dialog clipping: '+JSON.stringify(rect));
          await page.getByRole('button',{name:'بستن اتصال آنلاین'}).click();
          if(config.width<500){
            const toggle=page.locator('.mobile-nav-toggle');
            await toggle.click();
            await page.locator('#madar-sidebar.sidebar--mobile-open').waitFor();
            await page.keyboard.press('Escape');
            await page.locator('#madar-sidebar.sidebar--mobile-open').waitFor({state:'hidden'});
            assert.equal(await toggle.getAttribute('aria-expanded'),'false');
          }
          assert.deepEqual(errors,[],config.name+' uncaught browser errors');
          observed.push(config.name);
        }finally{await context.close();}
      }
      assert.deepEqual(observed,cases.map(x=>x.name));
    }finally{
      if(browser)await browser.close();
      await new Promise(resolve=>server.httpServer.close(resolve));
    }
  });

test('P1 OS compatibility policy: current Windows installer explicitly rejects Windows 7',()=>{
  const installer=fs.readFileSync(path.join(root,'scripts','madar-update.iss'),'utf8');
  assert.match(installer,/^MinVersion=10\.0\.17763\s*$/m);
  // Do not interpret a fake User-Agent as guest-OS runtime evidence.
  assert.equal(cases.filter(value=>value.userAgent).length,1);
});
