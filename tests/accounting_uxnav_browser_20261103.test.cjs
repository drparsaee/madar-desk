'use strict';
/** One isolated Chromium run; fake accounts and records, no native accounting host. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPath='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const available=fs.existsSync(chrome)&&fs.existsSync(playwrightPath);
const freePort=()=>new Promise((resolve,reject)=>{
  const server=net.createServer();server.once('error',reject);
  server.listen(0,'127.0.0.1',()=>{
    const port=server.address().port;server.close(error=>error?reject(error):resolve(port));
  });
});
const events=page=>page.evaluate(()=>window.__uxnavEvents);
const clearEvents=page=>page.evaluate(()=>{window.__uxnavEvents.length=0;});

test('UX-03/07/08 real Chromium: 1440/390, keyboard, roles, records and More',
  {skip:!available,timeout:95000},async()=>{
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',server:{
      host:'127.0.0.1',port:await freePort(),strictPort:true}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const page=await browser.newPage({viewport:{width:1440,height:900},locale:'fa-IR'});
      page.setDefaultTimeout(9000);
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      const url=new URL('tests/accounting_uxnav_fixture.html',server.resolvedUrls.local[0]);
      await page.goto(url.href,{waitUntil:'domcontentloaded'});
      const primary=page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'});
      await primary.waitFor();
      if(process.env.UXNAV_SCREENSHOT==='1')await page.screenshot({
        path:path.join(root,'tests','.uxnav-nav-desktop-1440.png'),fullPage:true});
      assert.equal(await primary.getByRole('button').count(),6);
      assert.equal(await page.getByRole('group',{name:'کارهای پرتکرار حسابداری'}).isVisible(),true);
      await page.getByRole('group',{name:'کارهای پرتکرار حسابداری'})
        .getByRole('button',{name:'فاکتور جدید'}).click();
      assert.ok((await events(page)).some(e=>e.type==='invoice'));
      await page.getByRole('group',{name:'کارهای پرتکرار حسابداری'})
        .getByRole('button',{name:'ثبت پرداخت'}).click();
      assert.ok((await events(page)).some(e=>e.type==='quick'&&e.action==='payment'));
      await page.getByRole('group',{name:'کارهای پرتکرار حسابداری'})
        .getByRole('button',{name:'خرید جدید'}).click();
      assert.ok((await events(page)).some(e=>e.type==='quick'&&e.action==='purchase'));
      await primary.getByRole('button',{name:'بیشتر'}).click();
      const more=page.getByRole('region',{name:'بخش‌های بیشتر حسابداری'});
      await more.waitFor();
      assert.equal(await more.getByRole('button',{name:'مهاجرت و سوابق'}).count(),1);
      await page.keyboard.press('Escape');
      assert.equal(await more.count(),0);
      assert.equal(await primary.getByRole('button',{name:'بیشتر'}).evaluate(
        el=>el===document.activeElement),true);

      await page.keyboard.press('Control+k');
      let dialog=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'});
      await dialog.waitFor();
      let input=dialog.getByRole('combobox',{name:/شماره فاکتور/});
      assert.equal(await input.evaluate(el=>el===document.activeElement),true);
      await input.fill('INV-QA-001');
      assert.equal(await dialog.getByRole('option').count(),1);
      await page.keyboard.press('Enter');
      assert.ok((await events(page)).some(e=>e.type==='select'&&
        e.kind==='invoice'&&e.id==='INV-QA-001'&&e.tab==='invoice'));
      assert.equal(await dialog.count(),0);

      await page.keyboard.press('Control+k');
      dialog=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'});
      input=dialog.getByRole('combobox');
      await input.fill('مشتری آزمایشی');
      assert.ok(await dialog.getByRole('option').count()>=2,
        'Customer name should find both party and associated invoice');
      await input.fill('1100');
      assert.equal(await dialog.getByRole('option').count(),1);
      assert.match(await dialog.getByRole('option').first().innerText(),/حساب دریافتنی/);
      await input.fill('SECRET-NOTE');
      assert.equal(await dialog.getByRole('option').count(),0,
        'Raw notes must never be searchable or rendered');
      await page.keyboard.press('Escape');
      assert.equal(await dialog.count(),0);

      await page.getByRole('group',{name:'سطح نمایش حسابداری'})
        .getByRole('button',{name:'پیشرفته'}).click();
      const advanced=page.getByRole('navigation',{name:'دسته‌بندی‌های حسابداری'});
      await advanced.waitFor();
      await advanced.getByRole('button',{name:'گزارش‌ها و سوابق'}).click();
      await page.getByRole('navigation',{name:'فرمان‌های گروه انتخاب‌شده'})
        .locator('[data-accounting-tab="reports"]').click();
      assert.ok((await events(page)).some(e=>e.type==='navigate'&&e.tab==='reports'));
      await page.getByRole('group',{name:'سطح نمایش حسابداری'})
        .getByRole('button',{name:'ساده'}).click();

      await page.evaluate(()=>window.__uxnavSetRole('viewer'));
      await page.waitForFunction(()=>
        !document.querySelector('.sac-nav-quick-actions [data-accounting-action="invoice"]'));
      assert.equal(await page.getByRole('group',{name:'کارهای پرتکرار حسابداری'})
        .getByRole('button',{name:'فاکتور جدید'}).count(),0);
      assert.equal(await page.getByRole('group',{name:'کارهای پرتکرار حسابداری'})
        .getByRole('button',{name:'ثبت پرداخت'}).count(),0);
      await primary.getByRole('button',{name:'بیشتر'}).click();
      assert.equal(await more.getByRole('button',{name:'مهاجرت و سوابق'}).count(),0);
      await page.keyboard.press('Escape');
      await page.keyboard.press('Control+k');
      dialog=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'});
      input=dialog.getByRole('combobox');
      for(const term of ['BILL-QA-001','1100','GL-QA-001']){
        await input.fill(term);
        assert.equal(await dialog.getByRole('option').count(),0,
          `Denied record must not be exposed by search: ${term}`);
      }
      await input.fill('INV-QA-001');
      assert.equal(await dialog.getByRole('option').count(),1,
        'Viewer retains read access to allowed invoice');
      await page.keyboard.press('Escape');
      await page.evaluate(()=>window.__uxnavClearView());
      await page.keyboard.press('Control+k');
      dialog=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'});
      await dialog.getByRole('combobox').fill('INV-QA-001');
      assert.equal(await dialog.getByRole('option').count(),0,
        'Previous company records must disappear immediately after snapshot removal');
      await page.keyboard.press('Escape');

      await page.setViewportSize({width:390,height:844});
      if(process.env.UXNAV_SCREENSHOT==='1')await page.screenshot({
        path:path.join(root,'tests','.uxnav-nav-mobile-390.png'),fullPage:true});
      const narrow=await page.evaluate(()=>({
        scrollWidth:document.documentElement.scrollWidth,viewportWidth:innerWidth,
        navCount:[...document.querySelectorAll('.sac-ux-shell nav')]
          .filter(node=>node.getClientRects().length&&getComputedStyle(node).display!=='none').length,
        tabRows:document.querySelectorAll('.sac-ux-shell .sac-simple-nav').length,
      }));
      assert.ok(narrow.scrollWidth<=narrow.viewportWidth+1,
        `Unexpected mobile horizontal overflow: ${JSON.stringify(narrow)}`);
      assert.equal(await primary.isVisible(),true);
      assert.equal(await primary.getByRole('button',{name:'بیشتر'}).isVisible(),true);
      assert.equal(await primary.getByRole('button',{name:'گزارش‌ها'}).isVisible(),false);
      assert.equal(await page.locator('.sac-nav-quick-actions').isVisible(),false);
      await page.getByRole('group',{name:'سطح نمایش حسابداری'})
        .getByRole('button',{name:'پیشرفته'}).click();
      assert.equal(await primary.isVisible(),true,
        'Mobile must preserve compact navigation in advanced mode');
      assert.equal(await advanced.isVisible(),false,
        'Advanced desktop Ribbon must not add horizontal mobile rows');
      await primary.getByRole('button',{name:'بیشتر'}).click();
      await more.locator('[data-accounting-tab="settings"]').click();
      assert.ok((await events(page)).some(e=>e.type==='navigate'&&e.tab==='settings'));
      await page.evaluate(()=>window.__uxnavSetTheme('dark'));
      await page.keyboard.press('Control+k');
      dialog=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'});
      const box=await dialog.boundingBox();
      assert.ok(box.x>=-1&&box.x+box.width<=391,`Search dialog overflows mobile: ${JSON.stringify(box)}`);
      await dialog.getByRole('combobox').fill('گزارش');
      assert.ok(await dialog.getByRole('option').count()>=1);
      if(process.env.UXNAV_SCREENSHOT==='1'){
        await page.screenshot({path:path.join(root,'tests','.uxnav-mobile-390.png'),fullPage:true});
        await page.setViewportSize({width:1440,height:900});
        await page.screenshot({path:path.join(root,'tests','.uxnav-desktop-1440.png'),fullPage:true});
      }
      assert.deepEqual(errors,[]);
    }finally{
      await browser?.close();
      await server.close();
    }
  });
