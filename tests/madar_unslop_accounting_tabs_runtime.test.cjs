'use strict';
// Screen-by-screen visual contract, using an empty authorized read-only ledger
// fixture. No accounting mutation API is provided or called.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const net=require('node:net');
const path=require('node:path');
const binary='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwright='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable=fs.existsSync(binary)&&fs.existsSync(playwright);
const root=path.resolve(__dirname,'..');
const shots=process.env.MADAR_UNSLOP_SHOTS||'';
const syntheticLedger={revision:0,capabilities:{canManage:false,canDraft:false,canAdmin:false},
  view:{currency:'RIAL',companyProfile:{legalName:'آزمون کاملاً ساختگی',history:[]},
    accounts:{},parties:{},items:{},invoices:{},bills:{},receipts:{},payments:{},
    journals:[],cheques:{},proformas:{},returns:{},closedThrough:null}};
const groups=[
  ['عمومی',['داشبورد','فاکتورهای فروش','پیش‌فاکتور مستقل']],
  ['فاکتورها و سفارش‌ها',['صورتحساب‌های خرید','کارهای پیمانکاران']],
  ['اشخاص و کالا',['اشخاص','کالا، انبار و کاردکس','مشخصات شرکت']],
  ['خزانه و پرداخت',['دریافت، پرداخت و اقساط','صندوق، بانک و مغایرت','خزانه و چک']],
  ['حسابداری',['حساب‌ها و دفترکل','سند دستی و برگشت','سال مالی و بستن دوره']],
  ["گزارش‌ها و سوابق",["گزارش‌های مالی"]],
  ['تنظیمات و مدیریت',['تنظیمات حسابداری','حقوق و مالیات']],
];
const port=()=>new Promise((resolve,reject)=>{
  const server=net.createServer();
  server.once('error',reject);
  server.listen(0,'127.0.0.1',()=>{
    const selected=server.address().port;
    server.close(error=>error?reject(error):resolve(selected));
  });
});
test('Unslop graphite/blue theme keeps all 17 viewer-permitted accounting screens reachable in both themes',
  {skip:!runnable,timeout:115000},async()=>{
    const {preview}=await import('vite');
    const {chromium}=require(playwright);
    const server=await preview({root,logLevel:'error',
      preview:{host:'127.0.0.1',port:await port(),strictPort:true}});
    let browser;
    try{
      browser=await chromium.launch({headless:true,executablePath:binary});
      for(const [theme,expected] of [['dark','rgb(17, 17, 19)'],['light','rgb(237, 241, 246)']]){
        const context=await browser.newContext({viewport:{width:1360,height:900},
          locale:'fa-IR',colorScheme:theme});
        const page=await context.newPage();
        page.setDefaultTimeout(7000);
        const errors=[];
        page.on('pageerror',error=>errors.push(error.message));
        await page.addInitScript(({theme,ledger})=>{
          localStorage.setItem('madar-ui-theme',theme);
          window.madar={
            standaloneAccountingRead:async()=>ledger,
          };
        },{theme,ledger:syntheticLedger});
        await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
          {waitUntil:'domcontentloaded',timeout:20000});
        await page.locator('.sac-root').waitFor({state:'visible'});
        await page.locator('.sac-header h1').waitFor({state:'visible'});
        // Novice navigation is default in 1.0.13. Explicitly open the retained professional Ribbon.
        await page.locator('.sac-nav-mode button:nth-child(2)').click();
        await page.locator('.sac-ribbon-tabs').waitFor({state:'visible'});
        let count=0;
        for(const [group,sections] of groups){
          for(const label of sections){
            // Choosing a page can legitimately select its canonical ribbon
            // category. Reopen the requested group for each independent page.
            await page.locator('.sac-ribbon-tabs').getByRole('button',{name:group,exact:true}).click();
            await page.locator('.sac-ribbon-tools').getByRole('button',{name:label,exact:true}).click();
            // Some modes intentionally hide the redundant H1. Assert its
            // actual state text, not a particular ribbon-group presentation.
            await page.waitForFunction(value=>
              document.querySelector('.sac-header h1')?.textContent?.trim()===value,
            label,{timeout:7000});
            const metrics=await page.evaluate(()=>{
              const root=document.querySelector('.sac-root');
              return {bg:getComputedStyle(root).backgroundColor,
                width:document.documentElement.scrollWidth,viewport:innerWidth,
                direction:getComputedStyle(root).direction,
                text:getComputedStyle(root).color};
            });
            assert.equal(metrics.bg,expected,label+' / '+theme);
            assert.equal(metrics.direction,'rtl');
            assert.ok(metrics.width<=metrics.viewport+1,
              label+' horizontal page overflow: '+JSON.stringify(metrics));
            if(shots){
              fs.mkdirSync(shots,{recursive:true});
              await page.screenshot({path:path.join(shots,'accounting-'+theme+'-'+
                String(count+1).padStart(2,'0')+'.png'),fullPage:false,animations:'disabled'});
            }
            count++;
          }
        }
        assert.equal(count,17,'Viewer must see 17 allowed tabs, not admin-only migration');
        assert.deepEqual(errors,[]);
        await context.close();
      }
    }finally{
      if(browser)await browser.close();
      await new Promise(resolve=>server.httpServer.close(resolve));
    }
  });
