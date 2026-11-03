'use strict';
/**
 * Browser-level fail-closed contract for 1.0.13 dashboard personalization.
 * SYNTHETIC ONLY: a stubbed window.madar, no native finance or user database.
 * Baseline 90e331b is expected RED until the prime integrates the production fix.
 * This file intentionally does not modify any source or an existing QA suite.
 */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome=path.join(process.env.USERPROFILE||'',
  'AppData','Roaming','npm','node_modules','playwright');
const PREF_PREFIX='madar.accounting.home.v1.';

const freePort=()=>new Promise((resolve,reject)=>{
  const socket=net.createServer();socket.once('error',reject);
  socket.listen(0,'127.0.0.1',()=>{
    const port=socket.address().port;
    socket.close(error=>error?reject(error):resolve(port));
  });
});

async function setupBrowser(t){
  assert.ok(fs.existsSync(chrome),`Chrome missing: ${chrome}`);
  assert.ok(fs.existsSync(playwrightHome),`Playwright missing: ${playwrightHome}`);
  const {chromium}=require(playwrightHome);
  const {createServer}=await import('vite');
  const server=await createServer({root,logLevel:'error',
    server:{host:'127.0.0.1',port:await freePort(),strictPort:true}});
  await server.listen();
  const browser=await chromium.launch({headless:true,executablePath:chrome});
  t.after(async()=>{
    await browser.close();
    await server.close();
  });
  return {browser,url:new URL('/accounting.html',server.resolvedUrls.local[0]).href};
}

async function createScenario(browser,url,{company='alpha',user='viewer.one',
  role='viewer',width=390,deny=false,failPreferences=false}={}){
  const context=await browser.newContext({viewport:{width,height:900},
    locale:'fa-IR',reducedMotion:'reduce'});
  const mutations=[];
  await context.exposeBinding('recordSyntheticMutation',(_source,command)=>{
    mutations.push(command);
  });
  await context.addInitScript(({company,user,role,deny,failPreferences})=>{
    localStorage.setItem('madar-ui-theme','light');
    if(!sessionStorage.getItem('qa-company'))sessionStorage.setItem('qa-company',company);
    if(!sessionStorage.getItem('qa-user'))sessionStorage.setItem('qa-user',user);
    if(!sessionStorage.getItem('qa-role'))sessionStorage.setItem('qa-role',role);
    if(deny&&!sessionStorage.getItem('qa-mode'))sessionStorage.setItem('qa-mode','deny');
    if(failPreferences){
      const read=Storage.prototype.getItem;
      Storage.prototype.getItem=function(key){
        if(String(key).startsWith('madar.accounting.home.v1.'))
          throw Error('QA_STORAGE_UNREADABLE');
        return read.call(this,key);
      };
    }
    const ids={alpha:'a'.repeat(32),beta:'b'.repeat(32)};
    const readReport=()=>{
      const book=sessionStorage.getItem('qa-company')||company;
      const actor=sessionStorage.getItem('qa-user')||user;
      const actorRole=sessionStorage.getItem('qa-role')||role;
      const amount=book==='alpha'?123000:456000;
      const edit=actorRole==='editor';
      return {revision:2,
        capabilities:{canView:true,canManage:edit,canDraft:edit,canAdmin:false},
        currentUser:{username:actor,role:actorRole,jobTitle:''},
        view:{currency:'RIAL',companyWorkspaceId:ids[book],
          companyWorkspaceLabel:'Synthetic Same-Name Company',
          companyProfile:{legalName:'Synthetic Same-Name Company',postingUtcOffsetMinutes:210},
          parties:{buyer:{id:'buyer',name:'Synthetic buyer',kind:'customer'}},
          accounts:{},items:{},returns:{},stockMovements:{},bankStatements:{},
          invoices:{['SALE-'+book]:{id:'SALE-'+book,status:'issued',partyId:'buyer',
            total:amount,allocated:0,returnedAmount:0,
            documentDate:'2026-11-01',postingDate:'2026-11-02',
            dueDate:'2026-11-03',lines:[{description:'Synthetic service',quantity:1,unitPrice:amount}]}},
          bills:{},receipts:{},payments:{},journals:[]}};
    };
    window.__qaReadCalls=0;
    window.madar={
      standaloneAccountingRead:async()=>{
        window.__qaReadCalls++;
        if(sessionStorage.getItem('qa-mode')==='deny')throw Error('QA_PERMISSION_REVOKED');
        if(sessionStorage.getItem('qa-mode')==='error')throw Error('QA_READ_FAILURE');
        const response=readReport();
        if(sessionStorage.getItem('qa-missing-id')==='true')
          delete response.view.companyWorkspaceId;
        return structuredClone(response);
      },
      standaloneAccountingCommand:async command=>{
        await window.recordSyntheticMutation(command);
        throw Error('SYNTHETIC_DENY_ALL_FINANCIAL_MUTATIONS');
      },
    };
  },{company,user,role,deny,failPreferences});
  const page=await context.newPage();
  page.setDefaultTimeout(6500);
  await page.clock.setFixedTime(new Date('2026-11-03T10:00:00Z'));
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(url,{waitUntil:'domcontentloaded',timeout:20000});
  return {context,page,mutations,errors};
}

const cards=page=>page.locator('.sac-ah-cards article');
const home=page=>page.locator('.sac-ah');
async function ensureHome(page,expectedAmount){
  await home(page).waitFor({state:'visible'});
  assert.equal(await home(page).getByText(expectedAmount+' ریال').first().isVisible(),true);
  assert.equal(await cards(page).count(),6);
}
async function hideCard(page,label){
  const settings=page.locator('.sac-ah-customize');
  await settings.locator('summary').click();
  await settings.getByRole('checkbox',{name:label}).uncheck();
  await page.waitForFunction(()=>document.querySelectorAll('.sac-ah-cards article').length===5);
}
const setIdentity=(page,company,user,role)=>page.evaluate(({company,user,role})=>{
  if(company!==null)sessionStorage.setItem('qa-company',company);
  if(user!==null)sessionStorage.setItem('qa-user',user);
  if(role!==null)sessionStorage.setItem('qa-role',role);
},{company,user,role});
async function gotoHomeAfterReload(page){
  await page.reload({waitUntil:'domcontentloaded'});
  await home(page).waitFor({state:'visible'});
}
async function preferences(page){
  return page.evaluate(prefix=>Object.fromEntries(Object.entries(localStorage)
    .filter(([key])=>key.startsWith(prefix))),PREF_PREFIX);
}

test('1.0.13 synthetic browser company/user preference and revocation gates',
  {timeout:120000},async t=>{
    const {browser,url}=await setupBrowser(t);

    await t.test('same visible company name, DIFFERENT opaque 32-hex IDs never share cards, including reload',async()=>{
      const s=await createScenario(browser,url,{width:390});
      try{
        await ensureHome(s.page,'۱۲۳٬۰۰۰');
        await hideCard(s.page,'مغایرت بانکی');
        await gotoHomeAfterReload(s.page);
        assert.equal(await cards(s.page).count(),5,'Same company+user restores choice after reload');
        await setIdentity(s.page,'beta','viewer.one','viewer');
        await gotoHomeAfterReload(s.page);
        await ensureHome(s.page,'۴۵۶٬۰۰۰');
        assert.equal(await cards(s.page).count(),6,
          'Two ledger IDs with the SAME company name MUST NOT share preferences');
        await hideCard(s.page,'بهای تمام‌شده');
        await setIdentity(s.page,'alpha','viewer.one','viewer');
        await gotoHomeAfterReload(s.page);
        assert.equal(await cards(s.page).count(),5,'First company card customization must survive second company');
        const saved=await preferences(s.page);
        assert.equal(Object.keys(saved).length,2,
          'Only two distinct per-company keys should exist for same user; no label-key fallback');
        assert.deepEqual(s.mutations,[]);
        assert.deepEqual(s.errors,[]);
      }finally{await s.context.close();}
    });

    await t.test('different authenticated users in SAME immutable company ID remain isolated',async()=>{
      const s=await createScenario(browser,url,{width:1440});
      try{
        await ensureHome(s.page,'۱۲۳٬۰۰۰');
        await hideCard(s.page,'مغایرت بانکی');
        await setIdentity(s.page,'alpha','viewer.two','viewer');
        await gotoHomeAfterReload(s.page);
        await ensureHome(s.page,'۱۲۳٬۰۰۰');
        await hideCard(s.page,'بهای تمام‌شده');
        await setIdentity(s.page,'alpha','viewer.one','viewer');
        await gotoHomeAfterReload(s.page);
        assert.equal(await cards(s.page).count(),5);
        const setting=s.page.locator('.sac-ah-customize');
        await setting.locator('summary').click();
        assert.equal(await setting.getByRole('checkbox',{name:'مغایرت بانکی'}).isChecked(),false);
        assert.equal(await setting.getByRole('checkbox',{name:'بهای تمام‌شده'}).isChecked(),true);
        assert.equal(Object.keys(await preferences(s.page)).length,2);
        assert.deepEqual(s.mutations,[]);
        assert.deepEqual(s.errors,[]);
      }finally{await s.context.close();}
    });

    await t.test('initial permission/read denial never shows last company dashboard or stale saved amounts',async()=>{
      const s=await createScenario(browser,url,{deny:true});
      try{
        await s.page.getByText('QA_PERMISSION_REVOKED').waitFor({state:'visible'});
        assert.equal(await home(s.page).count(),0);
        assert.equal(await s.page.getByText('۱۲۳٬۰۰۰ ریال').count(),0);
        assert.equal(await s.page.locator('.sac-ah-action').count(),0);
        assert.deepEqual(s.mutations,[]);
        assert.deepEqual(s.errors,[]);
      }finally{await s.context.close();}
    });

    await t.test('denial on reload after prior success does not hydrate a previous company book',async()=>{
      const s=await createScenario(browser,url);
      try{
        await ensureHome(s.page,'۱۲۳٬۰۰۰');
        await hideCard(s.page,'مغایرت بانکی');
        await setIdentity(s.page,'beta','viewer.one','viewer');
        await s.page.evaluate(()=>sessionStorage.setItem('qa-mode','deny'));
        await s.page.reload({waitUntil:'domcontentloaded'});
        await s.page.getByText('QA_PERMISSION_REVOKED').waitFor({state:'visible'});
        assert.equal(await home(s.page).count(),0,
          'A rejected reload must not revive old company data from persisted UI preferences');
        assert.equal(await s.page.getByText('۱۲۳٬۰۰۰ ریال').count(),0);
        assert.deepEqual(s.mutations,[]);
        assert.deepEqual(s.errors,[]);
      }finally{await s.context.close();}
    });

    await t.test('missing immutable company ID cannot silently persist under display-name fallback',async()=>{
      const s=await createScenario(browser,url);
      try{
        await s.page.evaluate(()=>sessionStorage.setItem('qa-missing-id','true'));
        await s.page.reload({waitUntil:'domcontentloaded'});
        // A stricter implementation may reject display entirely; rendering a
        // read-only dashboard is permissible, persistence on guessed ID is not.
        await s.page.waitForLoadState('domcontentloaded');
        if(await home(s.page).count()===1)await hideCard(s.page,'مغایرت بانکی');
        assert.deepEqual(await preferences(s.page),{},
          'Unknown company identity must not use username|companyLabel localStorage');
        assert.deepEqual(s.mutations,[]);
        assert.deepEqual(s.errors,[]);
      }finally{await s.context.close();}
    });

    await t.test('unreadable local preference storage fails safely, without account writes',async()=>{
      const s=await createScenario(browser,url,{failPreferences:true});
      try{
        await ensureHome(s.page,'۱۲۳٬۰۰۰');
        assert.equal(await cards(s.page).count(),6);
        await s.page.locator('.sac-ah-sale').click();
        assert.equal(await s.page.locator('.sac-header h1').textContent(),'فاکتورهای فروش');
        assert.deepEqual(s.mutations,[]);
        assert.deepEqual(s.errors,[]);
      }finally{await s.context.close();}
    });

    await t.test('failed refresh AFTER success clears old book, never retains financial or create CTAs',async()=>{
      const s=await createScenario(browser,url,{role:'editor',width:390});
      try{
        await ensureHome(s.page,'۱۲۳٬۰۰۰');
        assert.equal(await s.page.locator('.sac-ah-sale').getByText('فاکتور فروش جدید').count(),1);
        await setIdentity(s.page,'beta','viewer.one','viewer');
        await s.page.evaluate(()=>sessionStorage.setItem('qa-mode','deny'));
        await s.page.locator('.sac-header-actions button').first().click();
        await s.page.getByText('QA_PERMISSION_REVOKED').waitFor({state:'visible'});
        assert.equal(await home(s.page).count(),0,
          'Revoked read must clear old company dashboard (no stale snapshot)');
        assert.equal(await s.page.locator('.sac-ah-sale').count(),0,
          'Revoked read must remove old financial CREATE shortcut');
        assert.equal(await s.page.getByText('۱۲۳٬۰۰۰ ریال').count(),0,
          'Revoked read cannot expose old company receivable');
        assert.deepEqual(s.mutations,[]);
        assert.deepEqual(s.errors,[]);
      }finally{await s.context.close();}
    });

    await t.test('failed refresh AFTER success with generic read error also clears stale book',async()=>{
      const s=await createScenario(browser,url,{width:1440});
      try{
        await ensureHome(s.page,'۱۲۳٬۰۰۰');
        await s.page.evaluate(()=>sessionStorage.setItem('qa-mode','error'));
        await s.page.locator('.sac-header-actions button').first().click();
        await s.page.getByText('QA_READ_FAILURE').waitFor({state:'visible'});
        assert.equal(await home(s.page).count(),0);
        assert.deepEqual(s.mutations,[]);
        assert.deepEqual(s.errors,[]);
      }finally{await s.context.close();}
    });
  });
