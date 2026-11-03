'use strict';
/**
 * Regression of the *integrated* accounting.html, not a copied navigation mock.
 * Host responses are produced by the real accounting_core accounting_view() on
 * an in-memory RIAL ledger, delivered through a read-only synthetic JS bridge.
 * No APPDATA, real companies, installers, databases or command mutation.
 */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const sharedDeps=path.resolve(root,'..','madar-desk','node_modules');
const chrome=process.env.MADAR_UXREVIEW_CHROMIUM||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPath=process.env.MADAR_UXREVIEW_PLAYWRIGHT||
  'C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const freePort=()=>new Promise((resolve,reject)=>{
  const s=net.createServer();s.once('error',reject);
  s.listen(0,'127.0.0.1',()=>{
    const port=s.address().port;s.close(e=>e?reject(e):resolve(port));
  });
});

test('legacy UX audit readiness waits for the correct simple/advanced navigation',()=>{
  const source=fs.readFileSync(path.join(root,
    'scripts/madar_ux_completion_audit_20261103.cjs'),'utf8');
  assert.match(source,/if\(width>700\)[\s\S]*?name:'پیشرفته'/);
  assert.match(source,/\.sac-simple-nav \[data-accounting-tab=/);
  assert.match(source,/getByRole\('dialog',\{name:'جست‌وجوی حسابداری'\}\)/);
  assert.match(source,/const newInvoice=async page/);
  assert.doesNotMatch(source,/getByRole\('searchbox',\{name:'رفتن سریع به بخش حسابداری'\}\)/);
});

function projection(){
  const p=spawnSync('python',['-B','scripts/madar_uxreview_host_projection_20261103.py'],{
    cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'},
    maxBuffer:12*1024*1024});
  assert.equal(p.status,0,p.stderr||p.stdout);
  return JSON.parse(p.stdout);
}
function projectionFacts(data){
  const invoice=data.expected.invoice,other=data.expected.otherInvoice;
  assert.ok(data.deniedOnRevocation,'Real accounting_view must reject removed financeView');
  assert.ok(data.primaryAdmin.view.invoices[invoice]);
  assert.ok(data.primaryViewer.view.invoices[invoice],
    'Viewer with financeView=true can legitimately read the invoice');
  assert.ok(!data.primaryViewer.view.invoices[other]);
  assert.ok(!data.otherCompany.view.invoices[invoice]);
  assert.ok(data.primaryAdmin.view.journals.some(j=>j.id===data.expected.journal));
  assert.ok(data.primaryAdmin.view.accounts[data.expected.account]);
  for(const [key,id] of [['bills',data.expected.bill],
    ['receipts',data.expected.receipt],['payments',data.expected.payment]]){
    assert.ok(data.primaryAdmin.view[key][id],`Real host projection missing ${key}/${id}`);
  }
}
const beginContext=async(browser,data,mode,{width=1440,height=900,theme='light'}={})=>{
  const context=await browser.newContext({viewport:{width,height},locale:'fa-IR',
    reducedMotion:'reduce',colorScheme:theme});
  await context.addInitScript(({data,mode,theme})=>{
    localStorage.setItem('madar-ui-theme',theme);
    window.__review={mode,reads:0,mutations:[],errorMode:false};
    window.madar={
      standaloneAccountingRead:async()=>{
        window.__review.reads++;
        if(window.__review.mode==='denied')throw Error('Accounting read access denied');
        const response=window.__review.mode==='primaryViewer'?data.primaryViewer:
          window.__review.mode==='otherCompany'?data.otherCompany:data.primaryAdmin;
        return structuredClone(response);
      },
      standaloneAccountingCommand:async command=>{
        window.__review.mutations.push(command);
        throw Error('Synthetic host forbids all accounting mutation');
      },
      releaseCheck:async()=>({available:false,current:'1.0.13',latest:'1.0.13'}),
      releaseDownload:async()=>{throw Error('Synthetic fixture has no updater');},
      releaseInstall:async()=>{throw Error('Synthetic fixture has no installer');},
    };
  },{data,mode,theme});
  const page=await context.newPage();
  page.setDefaultTimeout(7500);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  return {context,page,errors};
};
async function search(page,query){
  await page.keyboard.press('Control+k');
  const dialog=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'});
  await dialog.waitFor({state:'visible'});
  const input=dialog.getByRole('combobox');
  assert.equal(await input.evaluate(n=>n===document.activeElement),true,
    'Ctrl+K should focus the real accessible combobox');
  await input.fill(query);
  return {dialog,input,options:dialog.getByRole('option')};
}
async function escape(page){await page.keyboard.press('Escape');
  await page.getByRole('dialog',{name:'جست‌وجوی حسابداری'}).waitFor({state:'detached'});}
async function switchModeAndRefresh(page,mode){
  await page.evaluate(value=>{window.__review.mode=value;},mode);
  await page.getByRole('group',{name:'سطح نمایش حسابداری'})
    .getByRole('button',{name:'پیشرفته'}).click();
  await page.getByRole('navigation',{name:'فرمان‌های گروه انتخاب‌شده'})
    .getByRole('button',{name:'بازخوانی'}).click();
  await page.waitForFunction(()=>{
    const a=document.querySelector('.sac-ux-shell .sac-nav-search-trigger');
    return a&&!a.disabled;
  });
}

test('official projected view denies revoked role and isolates independent company records',()=>{
  projectionFacts(projection());
});

test('integrated global search deep-links invoice/customer/account/journal and protects unsaved draft',
  {timeout:85000},async()=>{
    assert.ok(fs.existsSync(chrome),'Chromium executable is missing');
    assert.ok(fs.existsSync(playwrightPath),'Playwright runtime is missing');
    const data=projection();projectionFacts(data);
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',server:{
      host:'127.0.0.1',port:await freePort(),strictPort:true,
      fs:{allow:[root,sharedDeps]}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const {context,page,errors}=await beginContext(browser,data,'primaryAdmin');
      await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
        {waitUntil:'domcontentloaded'});
      const nav=page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'});
      await nav.locator('[data-accounting-tab="invoice"]').waitFor({state:'visible'});
      let r=await search(page,data.expected.invoice);
      assert.ok(await r.options.count()>=1,'Must resolve host-projected invoice');
      assert.equal((await r.options.first().locator('strong').textContent()).trim(),
        data.expected.invoice,'Exact document should rank ahead of linked journal');
      await r.options.first().click();
      await page.locator('.sac-document-detail').waitFor({state:'visible'});
      assert.match(await page.locator('.sac-document-detail').innerText(),/REVIEW-INV-A/);
      assert.equal(await nav.locator('[data-accounting-tab="invoice"][aria-current="page"]').count(),1);

      r=await search(page,data.expected.bill);
      assert.ok(await r.options.count()>=1);
      assert.equal((await r.options.first().locator('strong').textContent()).trim(),
        data.expected.bill);
      await r.options.first().click();
      await page.locator('.sac-document-detail').waitFor({state:'visible'});
      assert.match(await page.locator('.sac-document-detail').innerText(),/REVIEW-BILL-A/);
      assert.equal(await page.locator('.sac-header h1').textContent().then(x=>x.includes('خرید')),true);

      r=await search(page,data.expected.customerName);
      assert.ok(await r.options.count()>=2,'Customer must resolve both customer and invoice');
      await r.options.filter({hasText:'طرف‌حساب'}).first().click();
      await page.getByRole('dialog',{name:'جست‌وجوی حسابداری'}).waitFor({state:'detached'});
      assert.ok(await page.locator('.sac-header h1').isVisible());

      r=await search(page,data.expected.account);
      await r.options.filter({hasText:data.expected.account}).first().click();
      await page.locator('#sac-account-movements').waitFor({state:'attached'});
      assert.equal(await page.locator('.sac-header h1').textContent().then(x=>x.includes('حساب')),true);
      assert.equal(await page.locator('#sac-account-movements select').first().inputValue(),
        data.expected.account,'Selected account must be filtered, not merely navigated');

      r=await search(page,data.expected.journal);
      assert.ok(await r.options.count()>=1,'Posted journal ID must be indexed');
      await r.options.first().click();
      assert.match(await page.locator('.sac-header h1').textContent(),/سند/);
      assert.ok(await page.locator('.sac-body tr').filter({hasText:data.expected.journal}).count()>0);

      for(const [kind,id] of [['receipt',data.expected.receipt],
        ['payment',data.expected.payment]]){
        r=await search(page,id);
        assert.ok(await r.options.count()>=1,`Expected indexed ${kind} from host ledger`);
        assert.equal((await r.options.first().locator('strong').textContent()).trim(),id);
        await r.options.first().click();
        assert.equal(await page.locator('.sac-header h1').textContent().then(x=>x.includes('پرداخت')),true);
        assert.ok(await page.locator('.sac-body tr').filter({hasText:id}).count()>0,
          `${kind} record must appear in the correct table`);
      }

      await nav.locator('[data-accounting-tab="invoice"]').click();
      await page.locator('.sac-nav-quick-actions [data-accounting-action="invoice"]').click();
      const editable=page.locator('.sac-invoice-editor input[dir="ltr"]').first();
      await editable.waitFor({state:'visible'});
      await editable.fill('REVIEW-UNSAVED-A');
      const dialogs=[];
      page.once('dialog',async dialog=>{dialogs.push(dialog.message());await dialog.dismiss();});
      r=await search(page,data.expected.invoice);
      await r.options.first().click();
      assert.equal(dialogs.length,1,'Navigation must request confirmation for unsaved invoice');
      assert.equal(await editable.inputValue(),'REVIEW-UNSAVED-A',
        'Cancelled record switch must preserve the edited invoice');
      assert.equal(await page.locator('.sac-invoice-editor').isVisible(),true);
      assert.equal(await page.locator('.sac-document-detail').count(),0,
        'Cancelled deep link must not silently replace draft with a different record');

      page.once('dialog',async dialog=>{dialogs.push(dialog.message());await dialog.accept();});
      r=await search(page,data.expected.invoice);
      await r.options.first().click();
      await page.locator('.sac-document-detail').waitFor({state:'visible'});
      assert.match(await page.locator('.sac-document-detail').innerText(),/REVIEW-INV-A/);
      assert.equal(dialogs.length,2);
      assert.deepEqual(await page.evaluate(()=>window.__review.mutations),[],
        'Read-only search and cancelled draft must not write financial state');
      assert.deepEqual(errors,[],`Browser exceptions: ${errors}`);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('integrated viewer and mobile navigation enforce visible-route constraints',
  {timeout:85000},async()=>{
    assert.ok(fs.existsSync(chrome),'Chromium executable is missing');
    assert.ok(fs.existsSync(playwrightPath),'Playwright runtime is missing');
    const data=projection();projectionFacts(data);
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',server:{
      host:'127.0.0.1',port:await freePort(),strictPort:true,
      fs:{allow:[root,sharedDeps]}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const {context,page,errors}=await beginContext(browser,data,'primaryViewer',{
        width:390,height:844,theme:'dark'});
      await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
        {waitUntil:'domcontentloaded'});
      const nav=page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'});
      await nav.locator('[data-accounting-tab="invoice"]').waitFor({state:'visible'});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      assert.equal(await page.locator('.sac-nav-quick-actions').isVisible(),false);
      assert.equal(await nav.locator('[data-accounting-tab="reports"]').isVisible(),false);
      assert.equal(await page.locator('[data-accounting-action="invoice"]').count(),0,
        'Viewer must not see create-invoice action');
      await nav.locator('[data-accounting-action="more"]').click();
      const more=page.getByRole('region',{name:'بخش‌های بیشتر حسابداری'});
      await more.waitFor();
      assert.equal(await more.locator('[data-accounting-tab="migration"]').count(),0);
      await more.locator('[data-accounting-tab="accounts"]').click();
      assert.match(await page.locator('.sac-header h1').innerText(),/حساب/);
      let r=await search(page,data.expected.otherInvoice);
      assert.equal(await r.options.count(),0,'Cross-company invoice must never be indexed');
      await escape(page);
      r=await search(page,data.expected.invoice);
      assert.ok(await r.options.count()>=1,'Read-authorized viewer may locate own invoice');
      assert.equal((await r.options.first().locator('strong').textContent()).trim(),
        data.expected.invoice);
      await r.options.first().click();
      await page.locator('.sac-document-detail').waitFor({state:'visible'});
      assert.match(await page.locator('.sac-document-detail').innerText(),/REVIEW-INV-A/);
      await page.getByRole('group',{name:'سطح نمایش حسابداری'})
        .getByRole('button',{name:'پیشرفته'}).click();
      assert.equal(await nav.isVisible(),true,'Advanced on mobile retains one compact nav row');
      assert.equal(await page.locator('.sac-ribbon-tabs').isVisible(),false);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await page.setViewportSize({width:1440,height:900});
      await page.locator('.sac-ribbon-tabs button').first().waitFor({state:'visible'});
      const focusable=await page.locator('.sac-ribbon-tabs').evaluate(n=>n.tabIndex===0);
      assert.equal(focusable,true);
      await page.keyboard.press('Control+k');
      const combobox=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'}).getByRole('combobox');
      assert.equal(await combobox.evaluate(n=>n===document.activeElement),true);
      await escape(page);
      assert.deepEqual(await page.evaluate(()=>window.__review.mutations),[]);
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('revoking authenticated financeView invalidates cached searchable records on refresh',
  {timeout:85000},async()=>{
    assert.ok(fs.existsSync(chrome));assert.ok(fs.existsSync(playwrightPath));
    const data=projection();
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',server:{
      host:'127.0.0.1',port:await freePort(),strictPort:true,
      fs:{allow:[root,sharedDeps]}}});
    let browser;
    try{
      await server.listen();browser=await chromium.launch({headless:true,executablePath:chrome});
      const {context,page}=await beginContext(browser,data,'primaryAdmin');
      await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
        {waitUntil:'domcontentloaded'});
      await page.locator('.sac-simple-nav [data-accounting-tab="invoice"]').waitFor();
      await switchModeAndRefresh(page,'denied');
      await page.getByText('Accounting read access denied').waitFor({state:'visible'});
      const r=await search(page,data.expected.invoice);
      assert.equal(await r.options.count(),0,
        'Revoked host read must drop stale invoice from Ctrl+K index');
      await escape(page);
      assert.equal(await page.locator('.sac-document-detail').count(),0);
      assert.equal(await page.locator('.sac-body').getByText(data.expected.invoice).count(),0,
        'Revoked host read must drop all stale financial content');
      await context.close();
    }finally{await browser?.close();await server.close();}
  });
