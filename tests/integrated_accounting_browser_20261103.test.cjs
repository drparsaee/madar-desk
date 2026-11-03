'use strict';
/** Built accounting UI, headless Chrome, synthetic immutable ledger/host only. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwright='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const available=fs.existsSync(chrome)&&fs.existsSync(playwright);
const freePort=()=>new Promise((resolve,reject)=>{
  const s=net.createServer();s.once('error',reject);
  s.listen(0,'127.0.0.1',()=>{const port=s.address().port;
    s.close(error=>error?reject(error):resolve(port));});
});

const fixtureCode=`
import json
from accounting_core import empty_rial_accounting_state,apply_accounting_command,accounting_view
state=empty_rial_accounting_state()
users=[{"username":"root","role":"admin","financeEdit":True,"financeView":True}]
commands=[
{"type":"company.profile.set","legalName":"شرکت آزمایشی","address":"","phone":"","nationalId":"","economicCode":"","postalCode":"","reason":"Synthetic QA","postingUtcOffsetMinutes":210},
{"type":"party.register","partyId":"CUSTOMER-QA","name":"مشتری آزمایشی","kind":"customer"},
{"type":"invoice.create","invoiceId":"QA-INV-001","partyId":"CUSTOMER-QA","documentDate":"2026-11-01","lines":[{"description":"خدمت آزمایشی","quantity":2,"unitPrice":150000}]},
{"type":"invoice.approve","invoiceId":"QA-INV-001"},
{"type":"invoice.issue","invoiceId":"QA-INV-001","postingDate":"2026-11-02"},
]
for i,c in enumerate(commands):
    state=apply_accounting_command(state,{**c,"eventId":"INTEGRATED-QA-"+str(i+1)},actor="root",accounts=users,now="2026-11-03T10:00:00Z")["state"]
view=accounting_view(state,actor="root",accounts=users)
print(json.dumps({"revision":len(commands),"view":view,"capabilities":{"canManage":True,"canDraft":True,"canAdmin":True}},ensure_ascii=False))
`;

function contrastSample(el){
  return el.evaluate(node=>{
    const rgb=value=>{const m=String(value).match(/rgba?\((\d+)[, ]+(\d+)[, ]+(\d+)/);
      return m?[+m[1],+m[2],+m[3]]:null;};
    const lum=values=>{const c=values.map(x=>x/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);
      return .2126*c[0]+.7152*c[1]+.0722*c[2];};
    const foreground=rgb(getComputedStyle(node).color);
    let bg=null;
    for(let parent=node;parent&&!bg;parent=parent.parentElement){
      const style=getComputedStyle(parent),color=style.backgroundColor;
      if(color&&!/rgba?\(0, 0, 0, 0\)/.test(color)&&color!=='transparent')bg=rgb(color);
    }
    if(!foreground||!bg)return null;
    const a=lum(foreground),b=lum(bg);
    return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
  });
}

test('built accounting: safe Settings update, Ctrl+K, dark invoice contrast, narrow navigation',
  {skip:!available,timeout:85000},async()=>{
    const python=spawnSync('python',['-B','-c',fixtureCode],{
      cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'},maxBuffer:8*1024*1024,
    });
    assert.equal(python.status,0,python.stderr||python.stdout);
    const payload=JSON.parse(python.stdout);
    const {chromium}=require(playwright);
    const {preview}=await import('vite');
    const server=await preview({root,logLevel:'error',preview:{
      host:'127.0.0.1',port:await freePort(),strictPort:true,
    }});
    let browser;
    try{
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR',reducedMotion:'reduce'});
      await context.addInitScript(data=>{
        localStorage.setItem('madar-ui-theme','dark');
        window.madar={
          standaloneAccountingRead:async()=>structuredClone(data),
          standaloneAccountingCommand:async()=>{throw Error('Read-only synthetic QA');},
          releaseCheck:async()=>({available:false,current:'1.0.12',latest:'1.0.12'}),
          releaseDownload:async()=>{throw Error('Synthetic QA cannot download releases');},
          releaseInstall:async()=>{throw Error('Synthetic QA cannot schedule setup');},
        };
      },payload);
      const page=await context.newPage();
      page.setDefaultTimeout(11000);
      const errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
        {waitUntil:'domcontentloaded'});
      await page.locator('.sac-simple-nav [data-accounting-tab="overview"]').waitFor();
      await page.locator('.sac-simple-nav .sac-nav-more-trigger').click();
      await page.locator('.sac-nav-more-menu [data-accounting-tab="settings"]').click();
      await page.getByRole('button',{name:'بررسی به‌روزرسانی'}).click();
      await page.getByText('نسخهٔ جدیدتری در مخزن انتشار رسمی گزارش نشد.').waitFor();
      assert.equal(await page.locator('.madar-release-settings').count(),1);
      await page.keyboard.press('Control+k');
      const search=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'})
        .getByRole('combobox');
      await search.fill('گزارش');
      await page.keyboard.press('Enter');
      assert.equal(await page.locator('.sac-simple-nav [data-accounting-tab="reports"][aria-current="page"]').count(),1);

      await page.locator('.sac-simple-nav [data-accounting-tab="invoice"]').click();
      await page.locator('.sac-nav-quick-actions [data-accounting-action="invoice"]').click();
      const labels=page.locator('.sac-invoice-editor label.sac-field span');
      assert.ok(await labels.count()>=8,'Expected invoice labels in actual built composer');
      const ratios=[];
      for(const el of await labels.all()){
        if(await el.isVisible()){const ratio=await contrastSample(el);if(ratio!==null)ratios.push(ratio);}
      }
      assert.ok(ratios.length>=4,'Invoice labels contrast measurement unavailable; measured '+ratios.length+' of '+await labels.count());
      assert.ok(Math.min(...ratios)>=4.5,'WCAG text contrast below 4.5:1: '+Math.min(...ratios));
      await page.setViewportSize({width:390,height:844});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,
        'Narrow accounting page has document-level overflow');
      assert.deepEqual(errors,[]);
      await context.close();
    }finally{
      await browser?.close();
      await new Promise(resolve=>server.httpServer.close(resolve));
    }
  });
