'use strict';
// Real Chromium geometry against current Vite source using synthetic storage.
// The app's desktop bridge and all financial data remain untouched.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

const project=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightRoot='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable=fs.existsSync(chrome)&&fs.existsSync(playwrightRoot);
const layouts=[1440,1080,850,480];
const task=(id,title,status)=>({
  id,title,status,listId:status,projectId:'qa-project',boardId:'qa-board',
  description:'',priority:'medium',dueDate:'',labels:[],checklist:[],reports:[],
  createdAt:'2026-10-20T12:00:00Z',updatedAt:'2026-10-20T12:00:00Z',
});
const seed={
  version:1,
  projects:[{id:'qa-project',name:'پروژه آزمایشی',color:'#729ee9'}],
  workspaces:[{id:'qa-space',name:'فضای آزمایش',archived:false}],
  boards:[{id:'qa-board',projectId:'qa-project',workspaceId:'qa-space',
    name:'برد آزمایشی',stages:[
      {id:'planned',label:'برنامه‌ریزی',color:'#729ee9'},
      {id:'active',label:'در جریان',color:'#f4c15a'},
      {id:'review',label:'بازبینی',color:'#b38bd5'},
      {id:'done',label:'تکمیل',color:'#5fbd95'},
    ],archived:false}],
  tasks:[task('qa-task-1','کار تست اول','planned'),task('qa-task-2','کار تست دوم','active')],
  stages:[{id:'planned',label:'برنامه‌ریزی',color:'#729ee9'},
    {id:'active',label:'در جریان',color:'#f4c15a'},
    {id:'review',label:'بازبینی',color:'#b38bd5'},
    {id:'done',label:'تکمیل',color:'#5fbd95'}],
  settings:{theme:'dark',costDefault:false},
};

test('Chromium: centered compact nav, profile and search hit geometry at 1440/1080/850/480 in both themes',
  {skip:!runnable,timeout:100000},async()=>{
    const {chromium}=require(playwrightRoot);
    const {createServer}=await import('vite');
    const server=await createServer({root:project,logLevel:'error',
      server:{host:'127.0.0.1',port:0,strictPort:false,
        // This large checkout holds locked private SQL archive files. Never
        // watch or inspect those files merely to test source UI geometry.
        watch:{ignored:['**/.*','**/.*/**','**/*.mdf','**/*.ldf',
          '**/*.sqlite3','**/*.sqlite3-*','**/qa-evidence/**',
          '**/research/**','**/release/**','**/dist/**']}}});
    let browser;
    try {
      await server.listen();
      const address=server.httpServer.address();
      assert.ok(address&&typeof address.port==='number');
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1440,height:900},
        locale:'fa-IR',colorScheme:'dark'});
      const page=await context.newPage();
      page.setDefaultTimeout(8000);
      const errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.addInitScript(data=>{
        localStorage.setItem('madar-preview',JSON.stringify(data));
        localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      },seed);
      await page.goto('http://127.0.0.1:'+address.port+'/index.html',
        {waitUntil:'domcontentloaded',timeout:20000});
      await page.locator('.vitrea-top-row > .vitrea-account-capsule').waitFor({state:'visible'});
      const evidence=[];
      for(const width of layouts){
        await page.setViewportSize({width,height:900});
        for(const theme of ['dark','light']){
          // The host's theme preference drives the CSS tokens; changing this
          // attribute tests the same rendered layout without writing data.
          await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
          await page.evaluate(()=>document.fonts.ready);
          const dims=await page.evaluate(()=>{
            const rect=selector=>{
              const element=document.querySelector(selector);
              if(!element)return null;
              const r=element.getBoundingClientRect();
              return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height};
            };
            const hit=element=>{
              const r=element.getBoundingClientRect();
              const target=document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2);
              return element===target||element.contains(target);
            };
            const nav=document.querySelector('.vitrea-top-row > .vitrea-primary-nav');
            const account=document.querySelector('.vitrea-top-row > .vitrea-account-capsule');
            const brand=document.querySelector('.vitrea-top-row > .vitrea-brand-capsule');
            const search=document.querySelector('.vitrea-header-main .searchplus-shell');
            const current=document.querySelector('.vitrea-primary-nav button[aria-current=page]');
            const buttons=[...nav.querySelectorAll('button')];
            return {
              theme:document.documentElement.dataset.theme,
              dir:getComputedStyle(nav).direction,
              viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,
              header:rect('.vitrea-header-main'),brand:rect('.vitrea-brand-capsule'),
              nav:rect('.vitrea-primary-nav'),account:rect('.vitrea-account-capsule'),
              search:rect('.vitrea-header-main .searchplus-shell'),
              navScrollWidth:nav.scrollWidth,navClientWidth:nav.clientWidth,
              navButtonCount:buttons.length,
              navButtonHits:buttons.map(button=>({
                text:button.textContent.trim(),hit:hit(button),
                minHeight:button.getBoundingClientRect().height})),
              accountHit:hit(account),brandHit:hit(brand),currentHit:hit(current),
              searchHit:hit(search.querySelector('input')),
              background:getComputedStyle(nav).backgroundColor,
            };
          });
          evidence.push(dims);
          const contextMessage=JSON.stringify(dims);
          assert.equal(dims.theme,theme,contextMessage);
          assert.equal(dims.dir,'rtl',contextMessage);
          assert.ok(dims.navButtonCount>=4,contextMessage);
          assert.ok(dims.documentWidth<=width+2,contextMessage);
          assert.ok(dims.nav.width<dims.header.width-10,contextMessage);
          assert.ok(Math.abs((dims.nav.x+dims.nav.right)/2-
            (dims.header.x+dims.header.right)/2)<25,contextMessage);
          assert.ok(dims.nav.right<=dims.header.right+1&&
            dims.nav.x>=dims.header.x-1,contextMessage);
          assert.ok(dims.brand.x>=dims.nav.right-1 || width<=600,contextMessage);
          assert.ok(dims.account.right<=dims.nav.x+1 || width<=600,contextMessage);
          assert.ok(dims.search.y>=dims.nav.bottom-1,contextMessage);
          assert.ok(dims.account.bottom<=dims.search.y+1,contextMessage);
          assert.ok(dims.accountHit&&dims.brandHit&&dims.currentHit&&dims.searchHit,contextMessage);
          assert.ok(dims.navButtonHits.every(item=>item.hit && item.minHeight>=34),
            contextMessage);
          if(width<=600){
            assert.ok(dims.nav.y>=dims.brand.bottom-1,contextMessage);
            assert.ok(dims.nav.y>=dims.account.bottom-1,contextMessage);
          }
          const screenshotDir=process.env.MADAR_QA_SCREENSHOT_DIR;
          if(screenshotDir){
            fs.mkdirSync(screenshotDir,{recursive:true});
            await page.screenshot({path:path.join(screenshotDir,'vitrea-nav-'+width+'-'+theme+'.png'),
              animations:'disabled'});
          }
          // Real pointer interactions confirm the profile surface and primary
          // nav do not merely appear uncovered in elementFromPoint.
          if(theme==='dark' && (width===1440 || width===480)){
            await page.getByRole('button',{name:'نمایش پروفایل من'}).click();
            await page.locator('.member-modal[role="dialog"]').waitFor({state:'visible'});
            await page.locator('.member-modal .dialog-head button').click();
            // An unrelated concurrently loaded dialog must not be mistaken
            // for the profile whose own close button was just exercised.
            await page.locator('.member-modal').waitFor({state:'hidden',timeout:12000});
            await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
              .getByRole('button',{name:'فهرست'}).click();
            await page.locator('.list-mode').waitFor({state:'visible'});
            await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'})
              .getByRole('button',{name:'نمای کلی'}).click();
          }
        }
      }
      assert.deepEqual(errors,[],JSON.stringify(errors));
      console.log('Vitrea header Chromium geometry:',JSON.stringify(evidence));
      await context.close();
    } finally {
      if(browser)await browser.close();
      await server.close();
    }
  });
