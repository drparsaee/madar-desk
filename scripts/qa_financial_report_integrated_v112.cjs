'use strict';
// End-to-end UI read-only evidence, backed by a genuine synthetic accounting_core projection.
const assert=require('node:assert/strict');
const path=require('node:path');
const net=require('node:net');
const {spawnSync}=require('node:child_process');
const {chromium}=require(path.join(process.env.APPDATA,'npm','node_modules','playwright'));
const root=path.resolve(__dirname,'..');
const binary='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const py=`
import json
from accounting_core import empty_rial_accounting_state,apply_accounting_command,accounting_view
from accounting_reporting import ledger_reports
now="2026-11-03T10:00:00+00:00"
users=[{"username":"local","role":"admin"}]
state=empty_rial_accounting_state()
steps=[
{"type":"item.create","itemId":"GOOD","sku":"TEST-G","name":"کالای نمونه","kind":"goods","unit":"pcs"},
{"type":"item.stock.enable","itemId":"GOOD"},
{"type":"warehouse.create","warehouseId":"WH","name":"انبار ساختگی"},
{"type":"inventory.opening","warehouseId":"WH","itemId":"GOOD","quantity":3,"unitCost":60,"postingDate":"2026-10-01","reason":"Synthetic opening"},
{"type":"party.register","partyId":"C","name":"مشتری ساختگی","kind":"customer"},
{"type":"invoice.create","invoiceId":"QA-INV","partyId":"C","documentDate":"2026-10-10",
 "lines":[{"description":"کالای نمونه","quantity":1,"unitPrice":100,"itemId":"GOOD"}]},
{"type":"invoice.approve","invoiceId":"QA-INV"},
{"type":"invoice.issue","invoiceId":"QA-INV","postingDate":"2026-10-11"},
{"type":"fiscal.year.close","startDate":"2026-10-01","throughDate":"2026-10-31","reason":"Synthetic year close"}
]
for i,step in enumerate(steps):
  r=apply_accounting_command(state,{**step,"eventId":"QA-E"+str(i+1)},actor="local",accounts=users,now=now)
  state=r["state"]
view=accounting_view(state,actor="local",accounts=users)
view["financialReports"]=ledger_reports(view)
print(json.dumps({"revision":len(steps),"view":view,"capabilities":{"canManage":True,"canDraft":True,"canAdmin":True}},ensure_ascii=False))
`;
const fixtureRun=spawnSync('python',['-B','-c',py],{
  cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'},
  maxBuffer:8*1024*1024
});
if(fixtureRun.status!==0)throw Error('Python ledger failed: '+fixtureRun.stderr);
const fixture=JSON.parse(fixtureRun.stdout);
assert.equal(fixture.view.financialReports.profitLoss.revenue,100);
assert.equal(fixture.view.financialReports.profitLossReconciliation.reconciled,true);
assert.equal(fixture.view.financialReports.stockCostControl.sales[0].unpostedQuantity,1);
async function freePort(){
  const server=net.createServer();
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const result=server.address().port;
  await new Promise(resolve=>server.close(resolve));
  return result;
}
async function main(){
  const {preview}=await import('vite');
  const server=await preview({root,logLevel:'error',
    preview:{host:'127.0.0.1',port:await freePort(),strictPort:true}});
  let browser;
  try{
    browser=await chromium.launch({headless:true,executablePath:binary});
    const page=await browser.newPage({viewport:{width:1360,height:900},locale:'fa-IR'});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(payload=>{
      window.madar={
        standaloneAccountingRead:async()=>structuredClone(payload),
        standaloneAccountingCommand:async()=>{throw Error('Synthetic read-only QA blocks writes');}
      };
    },fixture);
    await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,{waitUntil:'domcontentloaded'});
    await page.locator('.sac-ribbon-tabs').getByRole('button',{name:'گزارش‌ها و سوابق'}).click();
    await page.locator('.sac-ribbon-tools').getByRole('button',{name:'گزارش‌های مالی'}).click();
    await page.getByText('گزارش سود هنوز نهایی نیست.').waitFor({timeout:9000});
    await page.getByText(/فروش QA-INV/).waitFor();
    await page.getByRole('heading',{name:'صورت سود و زیان عملیاتی'}).waitFor();
    await page.getByText(/تطبیق با سند بستن سال/).waitFor();
    const stats=await page.evaluate(()=>({
      notice:document.querySelector('.sac-alert.error')?.textContent?.slice(0,210),
      profitText:[...document.querySelectorAll('.sac-panel')]
        .find(el=>el.querySelector('h2')?.textContent?.includes('صورت سود و زیان عملیاتی'))
        ?.textContent?.slice(0,400)
    }));
    assert.match(stats.notice,/بهای تمام‌شده/);
    assert.match(stats.profitText,/تطبیق با سند بستن سال/);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({status:'PASS',checks:8,profit:fixture.view.financialReports.profitLoss,
      stock:fixture.view.financialReports.stockCostControl.assessment,
      reconciliation:fixture.view.financialReports.profitLossReconciliation.reconciled,
      runtime:'Chrome synthetic verified ledger projection, no writes'}));
  }finally{
    if(browser)await browser.close();
    await new Promise(resolve=>server.httpServer.close(resolve));
  }
}
main().catch(error=>{console.error(error);process.exitCode=1});
