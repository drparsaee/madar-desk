'use strict';
/** UX-03/04: real Chrome/Vite, synthetic in-memory core projection, viewer only. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const {spawnSync}=require('node:child_process');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPath=path.join(process.env.USERPROFILE||'',
  'AppData','Roaming','npm','node_modules','playwright');

const freePort=()=>new Promise((resolve,reject)=>{
  const s=net.createServer();s.once('error',reject);
  s.listen(0,'127.0.0.1',()=>{
    const port=s.address().port;
    s.close(error=>error?reject(error):resolve(port));
  });
});

// The entire fixture is generated from accounting_core; no SQLite, host API,
// customer data, APPDATA, installer or live financial source is accessed.
const fixtureCode=`
import json
from accounting_core import empty_rial_accounting_state, apply_accounting_command, accounting_view
from accounting_reporting import ledger_reports
state=empty_rial_accounting_state()
accounts={"root":{"username":"root","role":"admin","financeEdit":True,"financeView":True}}
commands=[
 {"type":"company.profile.set","legalName":"Synthetic Browser Company","address":"","phone":"","nationalId":"","economicCode":"","postalCode":"","reason":"Isolated browser QA","postingUtcOffsetMinutes":210},
 {"type":"party.register","partyId":"BUYER","name":"Synthetic Buyer","kind":"customer"},
 {"type":"party.register","partyId":"VENDOR","name":"Synthetic Vendor","kind":"vendor"},
 {"type":"item.create","itemId":"SKU","sku":"SKU-01","name":"Synthetic goods","kind":"goods","unit":"piece"},
 {"type":"item.stock.enable","itemId":"SKU"},
 {"type":"invoice.create","invoiceId":"SALE-OPEN","partyId":"BUYER","documentDate":"2026-11-01","dueDate":"2026-11-02","lines":[{"description":"Synthetic goods","itemId":"SKU","quantity":2,"unitPrice":150000}]},
 {"type":"invoice.approve","invoiceId":"SALE-OPEN"},
 {"type":"invoice.issue","invoiceId":"SALE-OPEN","postingDate":"2026-11-02"},
 {"type":"bill.create","billId":"BILL-OPEN","partyId":"VENDOR","documentDate":"2026-11-01","dueDate":"2026-11-08","lines":[{"description":"Synthetic supplies","quantity":1,"unitPrice":100000}]},
 {"type":"bill.approve","billId":"BILL-OPEN"},
 {"type":"bill.issue","billId":"BILL-OPEN","postingDate":"2026-11-02"},
 {"type":"bank.statement.add","statementId":"BANK-UNMATCHED","accountId":"1010","date":"2026-11-02","amount":80000,"reference":"QA-STMT-1"},
]
for i,command in enumerate(commands):
 state=apply_accounting_command(state,{**command,"eventId":"UX-BROWSER-"+str(i+1)},actor="root",accounts=accounts,now="2026-11-03T10:00:00Z")["state"]
view=accounting_view(state,actor="root",accounts=accounts)
view["financialReports"]=ledger_reports(view)
view["companyWorkspaceLabel"]="QA Company One"
view["companyWorkspaceId"]="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
print(json.dumps({"revision":len(commands),"view":view,
 "capabilities":{"canView":True,"canManage":False,"canDraft":False,"canAdmin":False},
 "currentUser":{"username":"synthetic.viewer","role":"viewer","jobTitle":""}},ensure_ascii=False))
`;

const buildFixture=()=>{
  const result=spawnSync('python',['-B','-c',fixtureCode],{
    cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'},
    maxBuffer:8*1024*1024});
  assert.equal(result.status,0,result.stderr||result.stdout);
  const payload=JSON.parse(result.stdout);
  assert.equal(payload.view.invoices['SALE-OPEN'].total,300000);
  assert.equal(payload.view.financialReports.profitLossComplete,false);
  return payload;
};

async function ratioFromComputedColors(locator,backgroundSelector){
  return locator.evaluate((el,selector)=>{
    const parse=value=>{
      if(value.startsWith('#')){
        const hex=value.slice(1).trim();
        if(hex.length!==6)return null;
        return [0,2,4].map(i=>parseInt(hex.slice(i,i+2),16)).concat(1);
      }
      const m=value.match(/rgba?\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)(?:\s*,\s*([\d.]+))?\s*\)/);
      return m?[Number(m[1]),Number(m[2]),Number(m[3]),m[4]===undefined?1:Number(m[4])]:null;
    };
    const root=el.closest('.sac-root');
    const base=parse(getComputedStyle(root).getPropertyValue('--vtr-bg').trim());
    const panel=el.closest(selector),overlay=parse(getComputedStyle(panel).backgroundColor);
    const fg=parse(getComputedStyle(el).color);
    if(!base||!overlay||!fg)return null;
    const composite=overlay.slice(0,3).map((x,i)=>x*overlay[3]+base[i]*(1-overlay[3]));
    const lum=rgb=>{
      const linear=rgb.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
      return .2126*linear[0]+.7152*linear[1]+.0722*linear[2];
    };
    const a=lum(fg),b=lum(composite);
    return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
  },backgroundSelector);
}

async function exerciseLayout(page,{width,theme}){
  await page.setViewportSize({width,height:width===390?844:900});
  const home=page.getByRole('region',{name:'میز اقدامات حسابداری'});
  await home.waitFor({state:'visible'});
  assert.equal(await page.locator('.sac-ah-actions button').count(),6,
    'Six direct shortcuts must remain visible to a viewer');
  assert.equal(await home.getByText('۳۰۰٬۰۰۰ ریال').first().isVisible(),true);
  assert.equal(await home.getByText('۱۰۰٬۰۰۰ ریال').first().isVisible(),true);
  assert.equal(await home.getByText('۱ فروش ناقص').isVisible(),true);
  assert.equal(await home.getByText('۱ ردیف').first().isVisible(),true);
  assert.equal(await home.getByText('سود قطعی نیست؛ ثبت هزینه کالا نیازمند کنترل است.').isVisible(),true);
  assert.equal(await home.getByRole('button',{name:/فاکتور فروش جدید/}).count(),0,
    'Viewer cannot receive a create-invoice CTA');
  assert.equal(await home.getByRole('button',{name:/ثبت دریافت|ثبت پرداخت/}).count(),0,
    'Viewer cannot receive posting CTAs');

  const geometry=await page.evaluate(()=>{
    const home=document.querySelector('.sac-ah'),body=document.querySelector('.sac-body');
    const rect=home.getBoundingClientRect();
    const buttons=[...document.querySelectorAll('.sac-ah-actions button, .sac-ah-card button, .sac-ah-customize > summary')];
    return {docWidth:document.documentElement.scrollWidth,viewport:innerWidth,
      homeLeft:rect.left,homeRight:rect.right,bodyScrollWidth:body.scrollWidth,
      bodyClientWidth:body.clientWidth,buttons:buttons.map(node=>({
        label:node.textContent.trim().slice(0,50),width:node.getBoundingClientRect().width,
        height:node.getBoundingClientRect().height}))};
  });
  assert.ok(geometry.docWidth<=width+1,
    `${theme} ${width}: document-level horizontal overflow ${JSON.stringify(geometry)}`);
  assert.ok(geometry.bodyScrollWidth<=geometry.bodyClientWidth+1,
    `${theme} ${width}: dashboard scroll region horizontally overflows`);
  assert.ok(geometry.homeLeft>=-1&&geometry.homeRight<=width+1,
    `${theme} ${width}: dashboard edges leave viewport`);
  for(const button of geometry.buttons){
    assert.ok(button.width>=44&&button.height>=44,
      `${theme} ${width}: critical CTA below 44 CSS px ${JSON.stringify(button)}`);
  }

  const contrasts=[
    ['.sac-ah-action strong','.sac-ah-action'],
    ['.sac-ah-card.primary > span','.sac-ah-card'],
    ['.sac-ah-card button','.sac-ah-card'],
    ['.sac-ah-customize > summary','.sac-ah-customize'],
    ['.sac-ah-title p','.sac-root'],
    ['.sac-ah-kicker','.sac-root'],
  ];
  const measured=[];
  for(const [selector,background] of contrasts){
    const element=page.locator(selector).first();
    const ratio=await ratioFromComputedColors(element,background);
    measured.push(ratio);
    assert.ok(ratio!==null&&ratio>=4.5,
      `${theme} ${width}: ${selector} computed contrast ${ratio} below 4.5:1`);
  }
  await page.locator('.sac-ah-performance').scrollIntoViewIfNeeded();
  const scrolled=await page.evaluate(()=>{
    const body=document.querySelector('.sac-body');
    return {top:body.scrollTop,max:body.scrollHeight-body.clientHeight};
  });
  assert.ok(scrolled.max>40&&scrolled.top>0,
    `${theme} ${width}: expected real vertical dashboard scrolling ${JSON.stringify(scrolled)}`);
  return {minimumContrast:Math.min(...measured),
    minimumCTAHeight:Math.min(...geometry.buttons.map(button=>button.height)),
    minimumCTAWidth:Math.min(...geometry.buttons.map(button=>button.width)),
    scrollTop:scrolled.top,scrollRange:scrolled.max};
}

test('actual Vite/Chrome dashboard: responsive themes, computed CTA contrast/size, viewer ACL and card persistence',
  {timeout:100000},async t=>{
    assert.ok(fs.existsSync(chrome),`Google Chrome executable missing at ${chrome}`);
    assert.ok(fs.existsSync(playwrightPath),`Playwright missing at ${playwrightPath}`);
    const payload=buildFixture();
    const {chromium}=require(playwrightPath);
    const {createServer}=await import('vite');
    const server=await createServer({root,logLevel:'error',
      server:{host:'127.0.0.1',port:await freePort(),strictPort:true}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      for(const theme of ['light','dark'])for(const width of [390,1440]){
        await t.test(`${theme} ${width}px`,async()=>{
          const context=await browser.newContext({viewport:{width,height:900},locale:'fa-IR',
            reducedMotion:'reduce'});
          try{
            await context.addInitScript(({payload,theme})=>{
              localStorage.setItem('madar-ui-theme',theme);
              window.__qaCommandCalls=[];
              const report=structuredClone(payload);
              report.view.companyWorkspaceLabel=sessionStorage.getItem('qa-company')||
                report.view.companyWorkspaceLabel;
              report.view.companyWorkspaceId=sessionStorage.getItem('qa-company-id')||
                report.view.companyWorkspaceId;
              report.currentUser.username=sessionStorage.getItem('qa-user')||
                report.currentUser.username;
              window.__qaFinancialView=JSON.stringify(report.view);
              window.__qaReport=report;
              window.madar={
                standaloneAccountingRead:async()=>structuredClone(report),
                standaloneAccountingCommand:async command=>{
                  window.__qaCommandCalls.push(command);
                  throw Error('Read-only synthetic viewer cannot mutate ledger');
                },
              };
            },{payload,theme});
            const page=await context.newPage();
            page.setDefaultTimeout(11000);
            page.clock.setFixedTime(new Date('2026-11-03T10:00:00Z'));
            const errors=[];
            page.on('pageerror',error=>errors.push(error.message));
            await page.goto(new URL('/accounting.html',server.resolvedUrls.local[0]).href,
              {waitUntil:'domcontentloaded'});
            assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),theme);
            const measured=await exerciseLayout(page,{theme,width});
            t.diagnostic(`${theme} ${width}px computed ${JSON.stringify(measured)}`);

            if(theme==='light'&&width===390){
              const options=page.locator('.sac-ah-customize');
              await options.locator('summary').click();
              const checkbox=options.getByRole('checkbox',{name:'مغایرت بانکی'});
              await checkbox.uncheck();
              assert.equal(await page.locator('.sac-ah-cards article').count(),5);
              const prefs=await page.evaluate(()=>localStorage.getItem(
                'madar.accounting.home.v1.synthetic.viewer%7Caaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'));
              assert.ok(prefs&&JSON.parse(prefs).includes('reconciliation')===false,
                'Only local UI card IDs should persist');
              await page.reload({waitUntil:'domcontentloaded'});
              await page.locator('.sac-ah-cards article').first().waitFor();
              assert.equal(await page.locator('.sac-ah-cards article').count(),5,
                'Card visibility should survive reload for this same user/company');
              await page.evaluate(()=>{
                sessionStorage.setItem('qa-company','QA Company Two');
                sessionStorage.setItem('qa-company-id','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
              });
              await page.reload({waitUntil:'domcontentloaded'});
              await page.locator('.sac-ah-cards article').first().waitFor();
              assert.equal(await page.locator('.sac-ah-cards article').count(),6,
                'Different company label must not inherit first company cards');
              await page.evaluate(()=>{
                sessionStorage.setItem('qa-company','QA Company One');
                sessionStorage.setItem('qa-company-id','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
                sessionStorage.setItem('qa-user','different.viewer');
              });
              await page.reload({waitUntil:'domcontentloaded'});
              await page.locator('.sac-ah-cards article').first().waitFor();
              assert.equal(await page.locator('.sac-ah-cards article').count(),6,
                'Different authenticated user must not inherit first user cards');
            }

            const destinations={sale:'فاکتورهای فروش',purchase:'صورتحساب‌های خرید',
              receipt:'دریافت، پرداخت و اقساط',payment:'دریافت، پرداخت و اقساط',
              reconcile:'صندوق، بانک و مغایرت',reports:'گزارش‌های مالی'};
            for(const [action,destination] of Object.entries(destinations)){
              await page.locator('.sac-ah-'+action).click();
              assert.equal(await page.locator('.sac-header h1').textContent(),destination,
                `Direct action ${action} must navigate to its existing task page`);
              assert.deepEqual(await page.evaluate(()=>window.__qaCommandCalls),[],
                `Viewer ${action} must not call the accounting mutation bridge`);
              assert.equal(await page.evaluate(()=>JSON.stringify(window.__qaReport.view)),
                await page.evaluate(()=>window.__qaFinancialView),
                `Viewer ${action} must preserve the read-only projection`);
              await page.reload({waitUntil:'domcontentloaded'});
              await page.locator('.sac-ah-'+action).waitFor();
            }
            assert.deepEqual(errors,[],`Browser exceptions in ${theme} ${width}`);
          }finally{await context.close();}
        });
      }
    }finally{
      await browser?.close();
      await server.close();
    }
  });
