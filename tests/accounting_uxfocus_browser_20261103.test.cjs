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

async function assertFocusedRecord(page,kind,id){
  const row=page.locator('tr.sac-search-target-row')
    .filter({has:page.locator(`td:first-child:text-is("${id}")`)}).first();
  await row.waitFor({state:'visible'});
  await page.waitForFunction(({kind,id})=>{
    const row=[...document.querySelectorAll('tr.sac-search-target-row')]
      .find(node=>node.dataset.accountingSearchKind===kind&&
        node.dataset.accountingSearchId===id);
    if(!row||document.activeElement!==row)return false;
    const bounds=row.getBoundingClientRect();
    return bounds.height>0&&bounds.bottom>0&&bounds.top<innerHeight;
  },{kind,id});
  assert.equal(await row.getAttribute('aria-label'),'رکورد انتخاب‌شده: '+id);
  assert.equal(await row.getAttribute('tabindex'),'-1');
  return row;
}

function projection(){
  const p=spawnSync('python',['-B','scripts/madar_uxfocus_host_projection_20261103.py'],{
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
        const response=window.__review.overrideResponse||(
          window.__review.mode==='primaryViewer'?data.primaryViewer:
          window.__review.mode==='otherCompany'?data.otherCompany:data.primaryAdmin);
        window.__review.lastResponse=structuredClone(response);
        return structuredClone(response);
      },
      standaloneAccountingCommand:async command=>{
        window.__review.mutations.push(command);
        if(window.__review.deferNextCommand){
          window.__review.deferNextCommand=false;
          return new Promise((resolve,reject)=>{
            window.__review.deferredHost={resolve,reject,eventId:command.command.eventId};
          });
        }
        if(window.__review.conflictsRemaining>0){
          window.__review.conflictsRemaining--;
          throw Error('CONFLICT: synthetic concurrent company revision');
        }
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

test('UXFocus projected host rejects revoked role and isolates companies',()=>{
  projectionFacts(projection());
});

test('UXFocus: journal/party/receipt/payment exact focused records and unsaved draft guard',
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
      await assertFocusedRecord(page,'party',data.expected.customer);

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
      await assertFocusedRecord(page,'journal',data.expected.journal);

      r=await search(page,data.expected.lastJournal);
      assert.ok(await r.options.count()>=1);
      await r.options.first().click();
      const longJournal=await assertFocusedRecord(page,'journal',data.expected.lastJournal);
      assert.equal((await longJournal.locator('td').first().textContent()).trim(),
        data.expected.lastJournal,'Target beyond initial 100 rows must become visible and focused');

      for(const [kind,id] of [['receipt',data.expected.receipt],
        ['payment',data.expected.payment]]){
        r=await search(page,id);
        assert.ok(await r.options.count()>=1,`Expected indexed ${kind} from host ledger`);
        assert.equal((await r.options.first().locator('strong').textContent()).trim(),id);
        await r.options.first().click();
        assert.equal(await page.locator('.sac-header h1').textContent().then(x=>x.includes('پرداخت')),true);
        await assertFocusedRecord(page,kind,id);
      }

      await nav.locator('[data-accounting-tab="invoice"]').click();
      await page.locator('.sac-nav-quick-actions [data-accounting-action="invoice"]').click();
      const editable=page.locator('.sac-invoice-editor input[dir="ltr"]').first();
      await editable.waitFor({state:'visible'});
      await editable.fill('REVIEW-UNSAVED-A');
      const dialogs=[];
      page.once('dialog',async dialog=>{dialogs.push(dialog.message());await dialog.dismiss();});
      r=await search(page,data.expected.customer);
      await r.options.filter({hasText:'طرف‌حساب'}).first().click();
      assert.equal(dialogs.length,1,'Navigation must request confirmation for unsaved invoice');
      assert.equal(await editable.inputValue(),'REVIEW-UNSAVED-A',
        'Cancelled record switch must preserve the edited invoice');
      assert.equal(await page.locator('.sac-invoice-editor').isVisible(),true);
      assert.equal(await page.locator('.sac-document-detail').count(),0,
        'Cancelled deep link must not silently replace draft with a different record');
      const retainedSearch=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'});
      assert.equal(await retainedSearch.isVisible(),true,
        'Refusing to discard an unsaved invoice must retain the search dialog');
      assert.equal(await retainedSearch.getByRole('combobox').inputValue(),
        data.expected.customer,'Cancelled navigation must retain the search query');

      page.once('dialog',async dialog=>{dialogs.push(dialog.message());await dialog.accept();});
      r=await search(page,data.expected.journal);
      await r.options.first().click();
      await assertFocusedRecord(page,'journal',data.expected.journal);
      assert.equal(dialogs.length,2);
      assert.deepEqual(await page.evaluate(()=>window.__review.mutations),[],
        'Read-only search and cancelled draft must not write financial state');
      // Exit uses its own handler rather than gotoTab. Both ribbon and sidebar
      // must preserve unsaved invoice/correction work when the user refuses.
      await nav.locator('[data-accounting-tab="invoice"]').click();
      await page.locator('.sac-nav-quick-actions [data-accounting-action="invoice"]').click();
      const exitDraft=page.locator('.sac-invoice-editor input[dir="ltr"]').first();
      await exitDraft.waitFor({state:'visible'});
      await exitDraft.fill('REVIEW-EXIT-GUARD');
      const exitDialogs=[];
      page.once('dialog',async dialog=>{exitDialogs.push(dialog.message());await dialog.dismiss();});
      await page.locator('.sac-ribbon-exit').click();
      assert.equal(exitDialogs.length,1,'Exiting with unsaved invoice must ask before discarding');
      assert.equal(await exitDraft.inputValue(),'REVIEW-EXIT-GUARD',
        'Cancelled exit must preserve the draft');
      assert.equal(await page.locator('.sac-invoice-editor').isVisible(),true);
      const sidebarExit=page.locator('.sac-sidebar-footer button').last();
      if(await sidebarExit.isVisible()){
        page.once('dialog',async dialog=>{exitDialogs.push(dialog.message());await dialog.dismiss();});
        await sidebarExit.click();
        assert.equal(exitDialogs.length,2,'Sidebar exit must share the same draft guard');
        assert.equal(await exitDraft.inputValue(),'REVIEW-EXIT-GUARD');
      }
      assert.deepEqual(await page.evaluate(()=>window.__review.mutations),[],
        'Exit validation must not create or update finance records');
      page.once('dialog',async dialog=>{exitDialogs.push(dialog.message());await dialog.accept();});
      await page.locator('.sac-ribbon-exit').click();
      await page.waitForURL(/\/index\.html(?:[?#]|$)/,{timeout:15000});
      assert.ok(exitDialogs.length>=2,'Accepted exit must require the discard confirmation');
      assert.deepEqual(errors,[],`Browser exceptions: ${errors}`);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('UXFocus authorized viewer 390/1440 selection and cross-company isolation',
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
      let selected=await search(page,data.expected.receipt);
      await selected.options.first().click();
      await assertFocusedRecord(page,'receipt',data.expected.receipt);
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

test('UXFocus: unsaved purchase bill rejects both exit and tab navigation without losing rows',
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
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const {context,page,errors}=await beginContext(browser,data,'primaryAdmin');
      await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
        {waitUntil:'domcontentloaded'});
      await page.locator('.sac-simple-nav [data-accounting-tab="invoice"]')
        .waitFor({state:'visible',timeout:15000});
      let r=await search(page,data.expected.bill);
      await r.options.first().click();
      assert.match(await page.locator('.sac-header h1').innerText(),/خرید/);
      const billForm=page.locator('.sac-invoice-editor');
      await billForm.waitFor({state:'attached'});
      const billId=billForm.locator('input[dir="ltr"]').first();
      await billId.fill('BILL-UNSAVED-20261104');
      const billDescription=billForm.locator('[data-invoice-row="0"][data-invoice-col="0"]');
      const billQuantity=billForm.locator('[data-invoice-row="0"][data-invoice-col="1"]');
      const billPrice=billForm.locator('[data-invoice-row="0"][data-invoice-col="2"]');
      await billDescription.fill('ردیف خرید هنوز ذخیره نشده');
      await billQuantity.fill('3');
      await billPrice.fill('7143');
      assert.equal(await page.evaluate(()=>typeof window.__madarAccountingConfirmNativeClose),
        'function','Native titlebar must have a live React editor close gate');
      let nativeClosePrompts=0;
      page.once('dialog',async dialog=>{nativeClosePrompts++;await dialog.dismiss();});
      assert.equal(await page.evaluate(()=>window.__madarAccountingConfirmNativeClose()),false);
      assert.equal(nativeClosePrompts,1,'Native X must reject closing a dirty purchase form');
      const assertPurchaseRows=async()=>{
        assert.equal(await billId.inputValue(),'BILL-UNSAVED-20261104');
        assert.equal(await billDescription.inputValue(),'ردیف خرید هنوز ذخیره نشده');
        assert.equal(await billQuantity.inputValue(),'3');
        assert.equal(await billPrice.inputValue(),'7143');
      };
      const cancelled=[];
      page.once('dialog',async dialog=>{cancelled.push(dialog.message());await dialog.dismiss();});
      await page.locator('.sac-ribbon-exit').click();
      assert.equal(cancelled.length,1,'Bill exit must ask about unsaved changes');
      await assertPurchaseRows();
      page.once('dialog',async dialog=>{cancelled.push(dialog.message());await dialog.dismiss();});
      await page.locator('.sac-nav-quick-actions [data-accounting-action="invoice"]').click();
      assert.equal(cancelled.length,2,'New sale shortcut must protect the current unsaved bill');
      await assertPurchaseRows();
      assert.match(await page.locator('.sac-header h1').innerText(),/خرید/);
      const nav=page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'});
      page.once('dialog',async dialog=>{cancelled.push(dialog.message());await dialog.dismiss();});
      await nav.locator('[data-accounting-tab="invoice"]').click();
      assert.equal(cancelled.length,3,'Changing section must protect unsaved bill too');
      await assertPurchaseRows();
      assert.match(await page.locator('.sac-header h1').innerText(),/خرید/);
      // Re-clicking the current section must not clear edit/correction state.
      await nav.locator('[data-accounting-tab="bill"]').click();
      await assertPurchaseRows();
      // Both neighboring actions are visible while the purchase editor is
      // open. Neither may silently replace the current unsaved purchase.
      const draftRow=page.getByRole('row').filter({
        has:page.getByText('REVIEW-BILL-DRAFT-A',{exact:true})});
      page.once('dialog',async dialog=>{cancelled.push(dialog.message());await dialog.dismiss();});
      await draftRow.getByRole('button',{name:'ویرایش پیش‌نویس'}).click();
      assert.equal(cancelled.length,4,'Selecting another draft must ask to discard unsaved purchase rows');
      await assertPurchaseRows();
      const issuedRow=page.getByRole('row').filter({
        has:page.getByText(data.expected.bill,{exact:true})});
      page.once('dialog',async dialog=>{cancelled.push(dialog.message());await dialog.dismiss();});
      await issuedRow.getByRole('button',{name:'تسویه'}).click();
      assert.equal(cancelled.length,5,'Settlement shortcut must respect unsaved purchase edits');
      await assertPurchaseRows();
      assert.match(await page.locator('.sac-header h1').innerText(),/خرید/);
      page.once('dialog',async dialog=>{cancelled.push(dialog.message());await dialog.accept();});
      await nav.locator('[data-accounting-tab="invoice"]').click();
      assert.equal(cancelled.length,6);
      assert.match(await page.locator('.sac-header h1').innerText(),/فروش/);
      r=await search(page,data.expected.bill);
      await r.options.first().click();
      assert.equal(await page.locator('.sac-invoice-editor input[dir="ltr"]').first().inputValue(),'',
        'After explicitly discarding a purchase draft, returning cannot resurrect it');
      assert.deepEqual(await page.evaluate(()=>window.__review.mutations),[],
        'Cancel/accept navigation must not post a bill or journal');
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('UXFocus: unsettled issued invoice and bill corrections cannot be lost on exit',
  {timeout:90000},async()=>{
    assert.ok(fs.existsSync(chrome));assert.ok(fs.existsSync(playwrightPath));
    const data=projection();
    assert.equal(data.primaryAdmin.view.invoices['REVIEW-INV-COR-A'].allocated,0);
    assert.equal(data.primaryAdmin.view.bills['REVIEW-BILL-COR-A'].allocated,0);
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
      await page.locator('.sac-simple-nav [data-accounting-tab="invoice"]')
        .waitFor({state:'visible',timeout:15000});
      let r=await search(page,'REVIEW-INV-COR-A');
      await r.options.first().click();
      await page.getByRole('button',{name:'اصلاح فاکتور صادرشده'}).click();
      const invoiceEditor=page.locator('.sac-invoice-editor');
      await invoiceEditor.waitFor({state:'visible'});
      const replacementInvoice=await invoiceEditor.locator('input[dir="ltr"]').first().inputValue();
      assert.match(replacementInvoice,/INV-COR/,
        'This must be a replacement draft, not an ordinary new invoice');
      let prompts=0;
      page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
      await page.locator('.sac-ribbon-exit').click();
      assert.equal(prompts,1);
      assert.equal(await invoiceEditor.locator('input[dir="ltr"]').first().inputValue(),replacementInvoice);
      // Accept discarding the unsaved correction by navigating to a bill.
      page.once('dialog',async dialog=>{prompts++;await dialog.accept();});
      r=await search(page,'REVIEW-BILL-COR-A');
      await r.options.first().click();
      assert.equal(prompts,2);
      assert.match(await page.locator('.sac-header h1').innerText(),/خرید/);
      await page.getByRole('button',{name:'اصلاح فاکتور صادرشده'}).click();
      const billEditor=page.locator('.sac-invoice-editor');
      const replacementBill=await billEditor.locator('input[dir="ltr"]').first().inputValue();
      assert.match(replacementBill,/BILL-COR/);
      const correctionRow=billEditor.locator('[data-invoice-row="0"][data-invoice-col="0"]');
      await correctionRow.fill('اصلاحیه خرید هنوز ذخیره نشده');
      const correctionReason=billEditor.getByPlaceholder('دلیل اصلاح سند صادرشده');
      await correctionReason.fill('بازبینی ارقام خرید بدون ثبت قطعی');
      const assertCorrection=async()=>{
        assert.equal(await billEditor.locator('input[dir="ltr"]').first().inputValue(),replacementBill);
        assert.equal(await correctionRow.inputValue(),'اصلاحیه خرید هنوز ذخیره نشده');
        assert.equal(await correctionReason.inputValue(),'بازبینی ارقام خرید بدون ثبت قطعی');
        assert.equal(await billEditor.getByRole('button',{name:'ثبت اصلاحیه'}).count()>0,true,
          'The pending correction must not silently become bill.create');
      };
      // Same-tab navigation used to silently turn bill.correct into create.
      await page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'})
        .locator('[data-accounting-tab="bill"]').click();
      await assertCorrection();
      // Reopening another editor while correcting must ask and preserve data.
      page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
      await page.getByRole('button',{name:'اصلاح فاکتور صادرشده'}).click();
      assert.equal(prompts,3);
      await assertCorrection();
      page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
      await page.locator('.sac-ribbon-exit').click();
      assert.equal(prompts,4);
      await assertCorrection();
      page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
      await page.locator('.sac-nav-quick-actions [data-accounting-action="invoice"]').click();
      assert.equal(prompts,5,'New sale shortcut must not discard a pending issued-bill correction');
      await assertCorrection();
      page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
      await page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'})
        .locator('[data-accounting-tab="invoice"]').click();
      assert.equal(prompts,6,'Bill correction must guard section changes');
      await assertCorrection();
      assert.deepEqual(await page.evaluate(()=>window.__review.mutations),[],
        'Correction discard checks must not reverse or post journal records');
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('UXFocus revoked financeView clears focused selection and cached search records',
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
      let prior=await search(page,data.expected.receipt);
      await prior.options.first().click();
      await assertFocusedRecord(page,'receipt',data.expected.receipt);
      await switchModeAndRefresh(page,'denied');
      await page.getByText('Accounting read access denied').waitFor({state:'visible'});
      const r=await search(page,data.expected.invoice);
      assert.equal(await r.options.count(),0,
        'Revoked host read must drop stale invoice from Ctrl+K index');
      await escape(page);
      assert.equal(await page.locator('.sac-document-detail').count(),0);
      assert.equal(await page.locator('tr.sac-search-target-row').count(),0,
        'Revocation must remove prior focused record, not just the search index');
      assert.equal(await page.locator('.sac-body').getByText(data.expected.invoice).count(),0,
        'Revoked host read must drop all stale financial content');
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('UXFocus: unsaved proforma survives native X, section and new-invoice cancellation',
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
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const {context,page,errors}=await beginContext(browser,data,'primaryAdmin');
      await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
        {waitUntil:'domcontentloaded'});
      const nav=page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'});
      await nav.locator('[data-accounting-action="more"]').click();
      await page.getByRole('region',{name:'بخش‌های بیشتر حسابداری'})
        .locator('[data-accounting-tab="proforma"]').click();
      const note=page.getByRole('textbox',{name:'شرایط و توضیحات'});
      await note.fill('پیش‌فاکتور آزمایشی هنوز ذخیره نشده');
      const currentNote=async()=>assert.equal(await note.inputValue(),
        'پیش‌فاکتور آزمایشی هنوز ذخیره نشده');
      const prompts=[];
      page.once('dialog',async dialog=>{prompts.push(dialog.message());await dialog.dismiss();});
      assert.equal(await page.evaluate(()=>window.__madarAccountingConfirmNativeClose()),false,
        'Native titlebar-X hook must veto loss of an unsaved proforma');
      await currentNote();
      page.once('dialog',async dialog=>{prompts.push(dialog.message());await dialog.dismiss();});
      await page.locator('.sac-ribbon-exit').click();
      await currentNote();
      page.once('dialog',async dialog=>{prompts.push(dialog.message());await dialog.dismiss();});
      await nav.locator('[data-accounting-tab="invoice"]').click();
      await currentNote();
      page.once('dialog',async dialog=>{prompts.push(dialog.message());await dialog.dismiss();});
      await page.locator('.sac-nav-quick-actions [data-accounting-action="invoice"]').click();
      await currentNote();
      assert.equal(prompts.length,4);
      page.once('dialog',async dialog=>{prompts.push(dialog.message());await dialog.accept();});
      await nav.locator('[data-accounting-tab="invoice"]').click();
      assert.match(await page.locator('.sac-header h1').innerText(),/فروش/);
      await nav.locator('[data-accounting-action="more"]').click();
      await page.getByRole('region',{name:'بخش‌های بیشتر حسابداری'})
        .locator('[data-accounting-tab="proforma"]').click();
      assert.equal(await page.getByRole('textbox',{name:'شرایط و توضیحات'}).inputValue(),'',
        'Explicitly discarded proforma must not silently reappear on return');
      assert.deepEqual(await page.evaluate(()=>window.__review.mutations),[]);
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('UXFocus: unsaved cash deposit and manual journal cannot be lost on exit or navigation',
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
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const {context,page,errors}=await beginContext(browser,data,'primaryAdmin');
      await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
        {waitUntil:'domcontentloaded'});
      const nav=page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'});
      const more=async destination=>{
        await nav.locator('[data-accounting-action="more"]').click();
        await page.getByRole('region',{name:'بخش‌های بیشتر حسابداری'})
          .locator('[data-accounting-tab="'+destination+'"]').click();
      };
      await more('cash');
      const deposit=page.locator('form').filter({has:page.getByRole('button',{name:'ثبت واریز'})});
      const depositNote=deposit.getByRole('textbox',{name:'شرح'});
      await depositNote.fill('واریز ذخیره نشده');
      let dialogs=0;
      page.once('dialog',async dialog=>{dialogs++;await dialog.dismiss();});
      assert.equal(await page.evaluate(()=>window.__madarAccountingConfirmNativeClose()),false);
      assert.equal(await depositNote.inputValue(),'واریز ذخیره نشده');
      page.once('dialog',async dialog=>{dialogs++;await dialog.dismiss();});
      await nav.locator('[data-accounting-tab="invoice"]').click();
      assert.equal(await depositNote.inputValue(),'واریز ذخیره نشده');
      page.once('dialog',async dialog=>{dialogs++;await dialog.dismiss();});
      await page.locator('.sac-ribbon-exit').click();
      assert.equal(await depositNote.inputValue(),'واریز ذخیره نشده');
      assert.equal(dialogs,3);
      page.once('dialog',async dialog=>await dialog.accept());
      await nav.locator('[data-accounting-tab="invoice"]').click();
      await more('cash');
      assert.equal(await page.locator('form').filter({has:page.getByRole('button',{name:'ثبت واریز'})})
        .getByRole('textbox',{name:'شرح'}).inputValue(),'');
      await more('journal');
      const journalNote=page.getByRole('textbox',{name:'شرح سند'});
      await journalNote.fill('شرح سند دستی ناتمام');
      page.once('dialog',async dialog=>{dialogs++;await dialog.dismiss();});
      assert.equal(await page.evaluate(()=>window.__madarAccountingConfirmNativeClose()),false);
      assert.equal(await journalNote.inputValue(),'شرح سند دستی ناتمام');
      page.once('dialog',async dialog=>{dialogs++;await dialog.dismiss();});
      await nav.locator('[data-accounting-tab="invoice"]').click();
      assert.equal(await journalNote.inputValue(),'شرح سند دستی ناتمام');
      assert.equal(dialogs,5);
      assert.deepEqual(await page.evaluate(()=>window.__review.mutations),[]);
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('UXFocus: native accepted close freezes edits through backup and abort restores access',
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
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const {context,page,errors}=await beginContext(browser,data,'primaryAdmin');
      await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
        {waitUntil:'domcontentloaded'});
      const nav=page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'});
      await nav.locator('[data-accounting-action="more"]').click();
      await page.getByRole('region',{name:'بخش‌های بیشتر حسابداری'})
        .locator('[data-accounting-tab="proforma"]').click();
      const note=page.getByRole('textbox',{name:'شرایط و توضیحات'});
      await note.fill('ویرایش قبل از بستن');
      page.once('dialog',async dialog=>await dialog.accept());
      assert.equal(await page.evaluate(()=>window.__madarAccountingConfirmNativeClose()),true);
      assert.equal(await page.locator('.sac-root').getAttribute('inert'),'');
      assert.equal(await page.locator('.sac-root').getAttribute('aria-busy'),'true');
      assert.equal(await page.evaluate(()=>window.__madarAccountingConfirmNativeClose()),false,
        'A second titlebar X cannot bypass the pending close');
      const clickAllowed=await note.click({timeout:1200}).then(()=>true,()=>false);
      assert.equal(clickAllowed,false,
        'An inert accounting root must reject user pointer focus during final backup');
      const focused=await note.evaluate(node=>{
        document.activeElement?.blur();node.focus();
        return document.activeElement===node;
      });
      assert.equal(focused,false,
        'No text field can regain keyboard focus while the native close is pending');
      assert.equal(await page.evaluate(()=>window.__madarAccountingAbortNativeClose()),true);
      assert.equal(await page.locator('.sac-root').getAttribute('inert'),null);
      assert.equal(await page.locator('.sac-root').getAttribute('aria-busy'),null);
      await note.fill('ویرایش بعد از شکست پشتیبان');
      assert.equal(await note.inputValue(),'ویرایش بعد از شکست پشتیبان');
      assert.deepEqual(await page.evaluate(()=>window.__review.mutations),[]);
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('UXFocus: nested bank and installment drafts veto native X and parent navigation',
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
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const {context,page,errors}=await beginContext(browser,data,'primaryAdmin');
      await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
        {waitUntil:'domcontentloaded'});
      const nav=page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'});
      const more=async destination=>{
        await nav.locator('[data-accounting-action="more"]').click();
        await page.getByRole('region',{name:'بخش‌های بیشتر حسابداری'})
          .locator('[data-accounting-tab="'+destination+'"]').click();
      };
      await more('cash');
      const bank=page.locator('.sac-operational-form').filter({
        has:page.getByRole('heading',{name:'ثبت ردیف صورتحساب بانکی'})});
      const bankId=bank.getByRole('textbox',{name:'شناسه رکورد بانک'});
      await bankId.fill('BANK-UNSAVED-20261104');
      let prompts=0;
      page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
      assert.equal(await page.evaluate(()=>window.__madarAccountingConfirmNativeClose()),false);
      page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
      await nav.locator('[data-accounting-tab="invoice"]').click();
      assert.equal(await bankId.inputValue(),'BANK-UNSAVED-20261104');
      page.once('dialog',async dialog=>await dialog.accept());
      await nav.locator('[data-accounting-tab="invoice"]').click();
      await nav.locator('[data-accounting-tab="settlements"]').click();
      const instalment=page.locator('.sac-operational-form').filter({
        has:page.getByRole('heading',{name:'ایجاد برنامه اقساط'})});
      const planId=instalment.getByRole('textbox',{name:'کد برنامه'});
      await planId.fill('PLAN-UNSAVED-20261104');
      page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
      assert.equal(await page.evaluate(()=>window.__madarAccountingConfirmNativeClose()),false);
      page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
      await nav.locator('[data-accounting-tab="invoice"]').click();
      assert.equal(await planId.inputValue(),'PLAN-UNSAVED-20261104');
      assert.equal(prompts,4);
      assert.deepEqual(await page.evaluate(()=>window.__review.mutations),[]);
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('UXFocus: all remaining nested operational finance drafts veto native X and tab changes',
  {timeout:100000},async()=>{
    assert.ok(fs.existsSync(chrome));assert.ok(fs.existsSync(playwrightPath));
    const data=projection();
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
      const more=async destination=>{
        await nav.locator('[data-accounting-action="more"]').click();
        await page.getByRole('region',{name:'بخش‌های بیشتر حسابداری'})
          .locator(`[data-accounting-tab="${destination}"]`).click();
      };
      const samples=[
        {tab:'cheques',field:'شناسه چک',value:'CHEQUE-DRAFT-20261104'},
        {tab:'items',field:'کد انبار',value:'WAREHOUSE-DRAFT-20261104'},
        {tab:'payroll',field:'شناسه لیست حقوق',value:'PAYROLL-DRAFT-20261104'},
        {tab:'period',field:'شناسه دوره مالی (اختیاری)',value:'PERIOD-DRAFT-20261104'},
        {tab:'company',field:'دلیل ثبت/تغییر',value:'COMPANY-DRAFT-20261104'},
      ];
      let prompts=0;
      for(const sample of samples){
        await more(sample.tab);
        const input=page.getByRole('textbox',{name:sample.field,exact:true}).first();
        await input.fill(sample.value);
        page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
        assert.equal(await page.evaluate(()=>window.__madarAccountingConfirmNativeClose()),false,
          `Dirty ${sample.tab} must veto a titlebar close`);
        page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
        await nav.locator('[data-accounting-tab="invoice"]').click();
        assert.equal(await input.inputValue(),sample.value,
          `Cancelled tab navigation must retain ${sample.tab} input`);
        page.once('dialog',async dialog=>dialog.accept());
        await nav.locator('[data-accounting-tab="invoice"]').click();
      }
      assert.equal(prompts,samples.length*2);
      assert.deepEqual(await page.evaluate(()=>window.__review.mutations),[],
        'No synthetic financial mutation may be posted by navigation');
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('UXFocus: company profile refresh merges untouched host fields and prevents same-field lost updates',
  {timeout:75000},async()=>{
    assert.ok(fs.existsSync(chrome));assert.ok(fs.existsSync(playwrightPath));
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',server:{
      host:'127.0.0.1',port:await freePort(),strictPort:true,
      fs:{allow:[root,sharedDeps]}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const {context,page,errors}=await beginContext(browser,projection(),'primaryAdmin');
      await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
        {waitUntil:'domcontentloaded'});
      const nav=page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'});
      await nav.locator('[data-accounting-action="more"]').click();
      await page.getByRole('region',{name:'بخش‌های بیشتر حسابداری'})
        .locator('[data-accounting-tab="company"]').click();
      const phone=page.getByRole('textbox',{name:'شماره تماس'});
      const offset=page.getByRole('textbox',{name:/اختلاف ثابت ساعت دفتر با UTC/});
      await phone.fill('02199991111');
      page.once('dialog',async dialog=>dialog.dismiss());
      await page.locator('.sac-header-actions').getByRole('button',{name:'بازخوانی'}).click();
      assert.equal(await phone.inputValue(),'02199991111',
        'A declined manual refresh must not unmount an unsaved editor');
      await page.evaluate(()=>{
        const newer=structuredClone(window.__review.lastResponse);
        newer.view.companyProfile.postingUtcOffsetMinutes=240;
        newer.view.companyProfile.history.push({reason:'Synthetic different user update'});
        window.__review.overrideResponse=newer;
        window.__review.conflictsRemaining=3;
      });
      await page.getByRole('textbox',{name:'دلیل ثبت/تغییر'}).fill('تغییر تلفن');
      await page.getByRole('button',{name:'ثبت با سابقه حسابداری'}).click();
      await page.waitForFunction(()=>window.__review.mutations.length===1&&
        window.__review.reads>=2);
      await page.waitForFunction(()=>{
        const textbox=[...document.querySelectorAll('input')].find(n=>
          n.closest('label')?.textContent?.includes('اختلاف ثابت ساعت دفتر'));
        return textbox?.value==='240';
      });
      assert.equal(await phone.inputValue(),'02199991111',
        'An operator-entered phone should survive a host profile refresh');
      assert.equal(await offset.inputValue(),'240',
        'An untouched posting UTC offset must adopt the NEW host value');
      const readsBeforeCancelledErrorRefresh=await page.evaluate(()=>window.__review.reads);
      page.once('dialog',async dialog=>dialog.dismiss());
      await page.getByRole('button',{name:'بازخوانی از میزبان'}).click();
      assert.equal(await phone.inputValue(),'02199991111',
        'Error-banner refresh must not bypass the dirty editor guard');
      assert.equal(await page.evaluate(()=>window.__review.reads),readsBeforeCancelledErrorRefresh,
        'Declined error-banner refresh may not initiate another host read');
      await page.getByRole('button',{name:'ثبت با سابقه حسابداری'}).click();
      await page.waitForFunction(()=>window.__review.mutations.length===2);
      const posted=await page.evaluate(()=>window.__review.mutations[1]);
      assert.equal(posted.command.type,'company.profile.set');
      assert.equal(posted.command.postingUtcOffsetMinutes,240);
      assert.equal(posted.command.phone,'02199991111');
      // A newer host writes the SAME locally modified phone field. It must
      // never be silently overwritten using a fresh parent CAS revision.
      await page.evaluate(()=>{
        const newer=structuredClone(window.__review.lastResponse);
        newer.view.companyProfile.phone='02112340000';
        newer.view.companyProfile.history.push({reason:'Synthetic concurrent phone update'});
        window.__review.overrideResponse=newer;
      });
      // A fresh explicit refresh is denied unless the user discards the draft;
      // simulate the host conflict-read in the same command flow instead.
      await page.getByRole('button',{name:'ثبت با سابقه حسابداری'}).click();
      await page.waitForFunction(()=>window.__review.mutations.length===3);
      await page.getByText(/تغییر هم‌زمان مشخصات شرکت شناسایی شد/).waitFor({state:'visible'});
      assert.equal(await phone.inputValue(),'02199991111');
      await page.getByRole('button',{name:'ثبت با سابقه حسابداری'}).click();
      assert.equal(await page.evaluate(()=>window.__review.mutations.length),3,
        'Same-field conflict must veto a later company mutation');
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('UXFocus: proforma same-tab selection and draft replacement preserve edit intent',
  {timeout:85000},async()=>{
    assert.ok(fs.existsSync(chrome));assert.ok(fs.existsSync(playwrightPath));
    const data=projection();
    assert.ok(data.primaryAdmin.view.proformas['REVIEW-PROFORMA-A']);
    assert.ok(data.primaryAdmin.view.proformas['REVIEW-PROFORMA-B']);
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
      const selectProforma=async()=>{
        await page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'})
          .locator('[data-accounting-action="more"]').click();
        await page.getByRole('region',{name:'بخش‌های بیشتر حسابداری'})
          .locator('[data-accounting-tab="proforma"]').click();
      };
      await selectProforma();
      const note=page.getByRole('textbox',{name:'شرایط و توضیحات'});
      const row=id=>page.getByRole('row').filter({
        has:page.getByText(id,{exact:true})}).first();
      await note.fill('پیشنهاد جدیدی که ذخیره نشده');
      let prompts=0;
      page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
      await row('REVIEW-PROFORMA-A').getByRole('button',{name:'ویرایش'}).click();
      assert.equal(await note.inputValue(),'پیشنهاد جدیدی که ذخیره نشده');
      assert.equal(await page.getByRole('button',{name:'ایجاد پیش‌فاکتور'}).count(),1);
      page.once('dialog',async dialog=>{prompts++;await dialog.accept();});
      await row('REVIEW-PROFORMA-A').getByRole('button',{name:'ویرایش'}).click();
      assert.equal(await page.getByRole('button',{name:'ثبت اصلاح'}).count(),1);
      await note.fill('ویرایش ذخیره‌نشده پیش‌فاکتور الف');
      await selectProforma();
      assert.equal(await page.getByRole('button',{name:'ثبت اصلاح'}).count(),1,
        'Selecting the current tab must not turn UPDATE into CREATE');
      assert.equal(await note.inputValue(),'ویرایش ذخیره‌نشده پیش‌فاکتور الف');
      page.once('dialog',async dialog=>{prompts++;await dialog.dismiss();});
      await row('REVIEW-PROFORMA-B').getByRole('button',{name:'ویرایش'}).click();
      assert.equal(await note.inputValue(),'ویرایش ذخیره‌نشده پیش‌فاکتور الف');
      page.once('dialog',async dialog=>{prompts++;await dialog.accept();});
      await row('REVIEW-PROFORMA-B').getByRole('button',{name:'ویرایش'}).click();
      assert.equal(await page.getByRole('button',{name:'ثبت اصلاح'}).count(),1);
      assert.equal(await note.inputValue(),data.primaryAdmin.view.proformas['REVIEW-PROFORMA-B'].note||'');
      assert.equal(prompts,4);
      assert.deepEqual(await page.evaluate(()=>window.__review.mutations),[],
        'Navigating and replacing a draft never issues or corrects a document');
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{await browser?.close();await server.close();}
  });

test('UXFocus: in-flight proforma and manual journal preserve line drafts while host is pending',
  {timeout:105000},async()=>{
    assert.ok(fs.existsSync(chrome));assert.ok(fs.existsSync(playwrightPath));
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',server:{
      host:'127.0.0.1',port:await freePort(),strictPort:true,
      fs:{allow:[root,sharedDeps]}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      for(const kind of ['proforma','manual']){
        const {context,page,errors}=await beginContext(browser,projection(),'primaryAdmin');
        await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
          {waitUntil:'domcontentloaded'});
        const nav=page.getByRole('navigation',{name:'مسیرهای اصلی حسابداری'});
        await nav.locator('[data-accounting-action="more"]').click();
        await page.getByRole('region',{name:'بخش‌های بیشتر حسابداری'})
          .locator(`[data-accounting-tab="${kind==='manual'?'journal':'proforma'}"]`).click();
        let line,oldValue,submitButton,expectedType;
        if(kind==='proforma'){
          const source=page.getByRole('row').filter({
            has:page.getByText('REVIEW-PROFORMA-A',{exact:true})}).first();
          await source.getByRole('button',{name:'ویرایش'}).click();
          const description=page.locator('.sac-doc-line input').first();
          await description.fill('پیشنهاد ویرایش معلق در میزبان');
          line=description;
          submitButton=page.getByRole('button',{name:'ثبت اصلاح'});
          expectedType='proforma.update';
        }else{
          const journal=page.locator('.sac-columns').filter({
            has:page.getByRole('heading',{name:'ثبت سند دستی'})}).first();
          await journal.getByRole('textbox',{name:'شرح سند'}).fill('سند آزمون معلق');
          const first=journal.locator('.sac-journal-row').nth(0);
          const second=journal.locator('.sac-journal-row').nth(1);
          await first.getByRole('combobox',{name:'سرفصل حساب ردیف 1'}).selectOption('1010');
          await second.getByRole('combobox',{name:'سرفصل حساب ردیف 2'}).selectOption('4000');
          await first.getByRole('textbox',{name:'بدهکار ردیف 1'}).fill('100');
          await second.getByRole('textbox',{name:'بستانکار ردیف 2'}).fill('100');
          line=first.getByRole('textbox',{name:'بدهکار ردیف 1'});
          submitButton=journal.getByRole('button',{name:'ثبت سند دستی'});
          expectedType='journal.manual';
        }
        oldValue=await line.inputValue();
        await page.evaluate(()=>{window.__review.deferNextCommand=true;});
        await submitButton.click();
        await page.waitForFunction(()=>Boolean(window.__review.deferredHost));
        const type=await page.evaluate(()=>window.__review.mutations[0].command.type);
        assert.equal(type,expectedType);
        assert.equal(await line.getAttribute('readonly'),'');
        assert.equal(await line.inputValue(),oldValue);
        await page.evaluate(()=>window.__review.deferredHost.reject(
          Error('synthetic lost host acknowledgement')));
        await page.waitForFunction(()=>document.body.textContent.includes(
          'synthetic lost host acknowledgement'));
        assert.equal(await line.inputValue(),oldValue,
          `${kind} rows must survive a host error without reset`);
        assert.equal(await page.evaluate(()=>window.__review.mutations.length),1,
          'Pending financial write cannot be replayed with a new event ID');
        assert.deepEqual(errors,[]);
        await context.close();
      }
    }finally{await browser?.close();await server.close();}
  });
