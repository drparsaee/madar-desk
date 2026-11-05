'use strict';
// Synthetic UI-only proof: startup chooses a real board, labels expand,
// and standalone finance shares the visual tokens without financial writes.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const net=require('node:net');
const path=require('node:path');
const browserPath='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPath='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable=fs.existsSync(browserPath)&&fs.existsSync(playwrightPath);
const root=path.resolve(__dirname,'..');
const shots=process.env.MADAR_UNSLOP_SHOTS||'';
async function capture(page,name){
  if(!shots)return;
  fs.mkdirSync(shots,{recursive:true});
  await page.screenshot({path:path.join(shots,name+'.png'),animations:'disabled',fullPage:false});
}
const stage={id:'inbox',label:'صندوق ورودی',color:'#7aaef0',subtitle:''};
const fixture={
  version:1,workspaces:[{id:'workspace-safe',name:'فضای آزمایشی',archived:false}],
  projects:[{id:'project-safe',name:'پروژه آزمایشی',color:'#729ee9',costEnabled:false,price:0}],
  boards:[{id:'board-safe',workspaceId:'workspace-safe',projectId:'project-safe',
    name:'برد شروع آزمایش',archived:false,stages:[stage]}],
  stages:[stage],tasks:[{id:'card-safe',projectId:'project-safe',boardId:'board-safe',
    listId:'inbox',status:'inbox',title:'کار نمونه',description:'',priority:'medium',
    labels:[],checklist:[],reports:[],dueDate:'',
    createdAt:'2026-10-20T12:00:00Z',updatedAt:'2026-10-20T12:00:00Z'}],
  settings:{theme:'dark',costDefault:false},
};
const freePort=()=>new Promise((resolve,reject)=>{
  const server=net.createServer();
  server.once('error',reject);
  server.listen(0,'127.0.0.1',()=>{
    const port=server.address().port;
    server.close(error=>error?reject(error):resolve(port));
  });
});
test('Madar opens board by default, keeps side dock compact and accounting graphite',
  {skip:!runnable,timeout:65000},async()=>{
    const {preview}=await import('vite');
    const {chromium}=require(playwrightPath);
    const server=await preview({root,logLevel:'error',
      preview:{host:'127.0.0.1',port:await freePort(),strictPort:true}});
    let browser;
    try {
      browser=await chromium.launch({headless:true,executablePath:browserPath});
      const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR'});
      const page=await context.newPage();
      const errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.addInitScript(data=>{
        localStorage.setItem('madar-preview',JSON.stringify(data));
        localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      },fixture);
      const base=server.resolvedUrls.local[0];
      await page.goto(new URL('index.html',base).href,{waitUntil:'domcontentloaded'});
      await page.locator('.kanban-lane').first().waitFor({state:'visible'});
      await capture(page,'board-start-dark');
      assert.equal(await page.locator('.vitrea-overview').count(),0);
      assert.equal(await page.locator('.task-card').count(),1);
      assert.equal(await page.locator('.vitrea-primary-nav button[aria-label="برد کارها"]')
        .getAttribute('aria-current'),'page');
      const overview=page.locator('.vitrea-primary-nav button[aria-label="نمای کلی"]');
      // Browser pointer position is not a reliable collapsed-state fixture:
      // a prior screenshot or page load can leave the item already hovered.
      await page.mouse.move(1,899);
      await page.waitForFunction(()=>{
        const button=document.querySelector('.vitrea-primary-nav button[aria-label="نمای کلی"]');
        return button&&!button.matches(':hover')&&button.getBoundingClientRect().width<=45;
      });
      const before=await overview.evaluate(el=>el.getBoundingClientRect().width);
      await overview.hover();
      await page.waitForFunction(width=>document.querySelector(
        '.vitrea-primary-nav button[aria-label="نمای کلی"]').getBoundingClientRect().width>width+25,
      before,{timeout:5000});
      const expanded=await overview.evaluate(el=>el.getBoundingClientRect().width);
      assert.ok(expanded>before+25,JSON.stringify({before,expanded}));
      assert.ok(await overview.getByText('نمای کلی').isVisible());
      const rail=page.locator('.vitrea-quickdock');
      await page.mouse.move(1,899);
      await page.waitForFunction(()=>document.querySelector('.vitrea-quickdock')
        .getBoundingClientRect().width<=65);
      const collapsed=await rail.evaluate(el=>el.getBoundingClientRect().width);
      await page.locator('.vitrea-quickdock__refresh').hover();
      const afterHover=await rail.evaluate(el=>el.getBoundingClientRect().width);
      assert.ok(afterHover<=65&&Math.abs(afterHover-collapsed)<=3,
        'Side dock must stay narrow on hover '+JSON.stringify({collapsed,afterHover}));
      assert.equal(await page.locator('.vitrea-quickdock__refresh .vitrea-quickdock__label').isVisible(),false);
      assert.equal(await page.locator('.vitrea-quickdock__update').count(),1,
        'Software update action must be in the compact side dock');
      await capture(page,'board-expanded-labels');
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await overview.click();
      await page.locator('.vitrea-overview').waitFor({state:'visible'});

      // No accounting bridge is connected. This is intentionally presentation only.
      for(const [theme,expected] of [['dark','rgb(17, 17, 19)'],['light','rgb(237, 241, 246)']]){
        const finance=await browser.newContext({viewport:{width:1280,height:900},locale:'fa-IR'});
        const window=await finance.newPage();
        await window.addInitScript(v=>localStorage.setItem('madar-ui-theme',v),theme);
        await window.goto(new URL('accounting.html',base).href,{waitUntil:'domcontentloaded'});
        await window.locator('.sac-root').waitFor({state:'visible'});
        const bg=await window.locator('.sac-root').evaluate(el=>getComputedStyle(el).backgroundColor);
        assert.equal(bg,expected,'Accounting must use Madar shared '+theme+' background');
        assert.equal(await window.locator('html').getAttribute('dir'),'rtl');
        await capture(window,'accounting-home-'+theme);
        await finance.close();
      }
      assert.deepEqual(errors,[]);
    }finally{
      if(browser)await browser.close();
      await new Promise(resolve=>server.httpServer.close(resolve));
    }
  });
