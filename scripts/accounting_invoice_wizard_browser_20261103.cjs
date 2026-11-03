/* Isolated browser acceptance: synthesized RIAL state and a host command spy
 * that deliberately rejects every mutation. No user's accounting store touched. */
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const assert=require('node:assert/strict');
const {spawn,spawnSync}=require('node:child_process');
const {chromium}=require(path.join(process.env.APPDATA,'npm','node_modules','playwright'));
const root=path.resolve(__dirname,'..');
const dist=path.join(root,process.env.INVOICE_WIZARD_DIST||'.qa-invoice-dist');
const evidence=path.join(root,'tests','evidence','invoice_wizard_20261103');
fs.mkdirSync(evidence,{recursive:true});
const fixturePython=`
import json
from accounting_core import empty_rial_accounting_state,apply_accounting_command,accounting_view
state=empty_rial_accounting_state()
users=[{"username":"root","role":"admin","financeEdit":True,"financeView":True}]
now="2026-11-03T10:00:00Z"
commands=[
  {"type":"party.register","partyId":"CUSTOMER-QA","name":"مشتری آزمون","kind":"customer"},
  {"type":"party.register","partyId":"SUPPLIER-QA","name":"تأمین‌کننده آزمون","kind":"vendor"},
  {"type":"invoice.create","invoiceId":"INV-QA-DRAFT","partyId":"CUSTOMER-QA",
    "documentDate":"2026-11-01","lines":[{"description":"draft","quantity":1,"unitPrice":10000}]},
  {"type":"invoice.create","invoiceId":"INV-QA-APPROVED","partyId":"CUSTOMER-QA",
    "documentDate":"2026-11-01","lines":[{"description":"approved","quantity":1,"unitPrice":20000}]},
  {"type":"invoice.approve","invoiceId":"INV-QA-APPROVED"},
  {"type":"invoice.create","invoiceId":"INV-QA-ISSUED","partyId":"CUSTOMER-QA",
    "documentDate":"2026-11-01","lines":[{"description":"issued","quantity":1,"unitPrice":30000}]},
  {"type":"invoice.approve","invoiceId":"INV-QA-ISSUED"},
  {"type":"invoice.issue","invoiceId":"INV-QA-ISSUED","postingDate":"2026-11-02"},
]
for i,c in enumerate(commands):
  state=apply_accounting_command(state,{**c,"eventId":"UX-WIZARD-"+str(i+1)},
    actor="root",accounts=users,now=now)["state"]
view=accounting_view(state,actor="root",accounts=users)
print(json.dumps({"revision":len(commands),"view":view,
  "capabilities":{"canManage":True,"canDraft":True,"canAdmin":True}},ensure_ascii=False))
`;
const py=spawnSync('python',['-B','-c',fixturePython],{
  cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'}});
if(py.status!==0)throw Error('Synthetic fixture failed: '+py.stderr);
const fixture=JSON.parse(py.stdout);
const report={baseline:'6bf687b4 + isolated UX-05/06/09',mode:'synthetic read-only host',
  checks:[],axe:[],errors:[],screenshots:[]};
const checkpoint=(name,value)=>{report.checks.push({name,value});};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function assertTouchTargets(page,label){
  const controls=await page.evaluate(()=>{
    return [...document.querySelectorAll('.sac-invoice-editor button,.sac-invoice-editor input,.sac-invoice-editor select,.sac-invoice-editor summary')]
      .filter(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
        return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';})
      .map(el=>{const r=el.getBoundingClientRect();return {
        label:(el.getAttribute('aria-label')||el.textContent||'').trim().slice(0,50),
        width:Math.round(r.width),height:Math.round(r.height)};});
  });
  assert.ok(controls.length>5,label);
  assert.deepEqual(controls.filter(t=>t.width<44||t.height<44),[],label);
  checkpoint('touch controls '+label,controls.length);
}
async function freePort(){return new Promise((resolve,reject)=>{
  const server=net.createServer();server.once('error',reject);
  server.listen(0,'127.0.0.1',()=>{
    const port=server.address().port;server.close(()=>resolve(port));});
});}
async function main(){
  const port=await freePort();
  const server=spawn('python',['-m','http.server',String(port),'--bind','127.0.0.1',
    '--directory',dist],{cwd:root,stdio:'ignore',windowsHide:true});
  let browser=null;
  try{
    for(let i=0;i<40;i++){
      try{if((await fetch('http://127.0.0.1:'+port+'/accounting.html')).ok)break;}
      catch{}
      await sleep(150);
    }
    browser=await chromium.launch({headless:true,channel:'chrome'});
    const context=await browser.newContext({viewport:{width:390,height:844},
      locale:'fa-IR',reducedMotion:'reduce'});
    await context.addInitScript(payload=>{
      window.__invoiceCommandAttempts=[];
      window.madar={
        standaloneAccountingRead:async()=>structuredClone(payload),
        standaloneAccountingCommand:async request=>{
          window.__invoiceCommandAttempts.push(request);
          throw Error('Synthetic host deliberately rejects mutations');
        },
      };
    },fixture);
    const page=await context.newPage();
    page.on('pageerror',e=>report.errors.push('pageerror: '+e.message));
    page.on('console',m=>{if(m.type()==='error')report.errors.push('console: '+m.text());});
    await page.goto('http://127.0.0.1:'+port+'/accounting.html',{
      waitUntil:'domcontentloaded'});
    await page.locator('.sac-ribbon-tabs button').first().waitFor({timeout:15000});
    await page.locator('.sac-ribbon-tabs').getByRole('button',{
      name:'فاکتورها و سفارش‌ها',exact:true}).click();
    await page.locator('.sac-ribbon-tools').getByRole('button',{
      name:'فاکتورهای فروش',exact:true}).click();
    await page.locator('.sac-ribbon-tools').getByRole('button',{
      name:'ثبت فاکتور جدید',exact:true}).click();
    const form=page.locator('form.sac-invoice-editor');
    await form.waitFor({state:'visible'});
    assert.equal(await form.getAttribute('novalidate'),'');
    assert.equal(await page.locator('.sac-wizard-step-nav button').count(),5);
    assert.equal(await page.locator('.sac-invoice-commandbar').isVisible(),false);
    assert.equal(await page.locator('.sac-workflow-nav').isVisible(),false);
    const input=page.locator('#sac-wizard-panel-document input').first();
    const generated=await input.inputValue();
    assert.ok(generated.startsWith('INV-'));
    await assertTouchTargets(page,'stage 1 / customer');
    await page.locator('.sac-wizard-sticky-actions').getByRole('button',{name:/ادامه/}).click();
    assert.ok(await page.locator('#sac-wizard-panel-document .sac-wizard-field-error').isVisible());
    assert.equal(await page.evaluate(()=>window.__invoiceCommandAttempts.length),0);
    checkpoint('invalid customer stays at first step',true);
    await page.locator('#sac-wizard-panel-document select').selectOption('CUSTOMER-QA');
    await page.locator('.sac-wizard-sticky-actions').getByRole('button',{name:/ادامه/}).click();
    assert.ok(await page.locator('#sac-wizard-panel-lines').isVisible());
    await assertTouchTargets(page,'stage 2 / lines');
    await page.locator('.sac-wizard-sticky-actions').getByRole('button',{name:/ادامه/}).click();
    assert.ok(await page.locator('#sac-wizard-panel-lines .sac-wizard-field-error').isVisible());
    await page.locator('#sac-wizard-panel-lines input[data-invoice-col="0"]').fill('خدمت ویرایش‌پذیر');
    await page.locator('#sac-wizard-panel-lines input[data-invoice-col="2"]').fill('150000');
    await page.locator('.sac-wizard-sticky-actions').getByRole('button',{name:/ادامه/}).click();
    assert.ok(await page.locator('#sac-wizard-panel-tax').isVisible());
    await assertTouchTargets(page,'stage 3 / tax');
    await page.locator('#sac-wizard-panel-tax input').first().fill('1000');
    await page.locator('.sac-wizard-sticky-actions').getByRole('button',{name:/ادامه/}).click();
    assert.ok(await page.locator('#sac-wizard-panel-due').isVisible());
    await assertTouchTargets(page,'stage 4 / due');
    await page.locator('#sac-wizard-panel-due').getByLabel('یادداشت (اختیاری)').fill('یادداشت حفظ شود');
    await page.locator('.sac-wizard-sticky-actions').getByRole('button',{name:/ادامه/}).click();
    assert.ok(await page.locator('#sac-wizard-panel-review').isVisible());
    assert.match(await page.locator('.sac-wizard-sticky-amount strong').textContent(),/۱۴۹٬۰۰۰/);
    const beforeSaveCommands=await page.evaluate(()=>window.__invoiceCommandAttempts);
    checkpoint('commands before explicit save',beforeSaveCommands);
    assert.equal(beforeSaveCommands.length,0);
    checkpoint('five stages move without financial commands',true);
    await page.locator('.sac-wizard-step-nav button').nth(1).click();
    assert.equal(await page.locator('#sac-wizard-panel-lines input[data-invoice-col="0"]').inputValue(),
      'خدمت ویرایش‌پذیر');
    await page.locator('#sac-wizard-panel-lines input[data-invoice-col="2"]').fill('160000');
    await page.locator('.sac-wizard-step-nav button').nth(3).click();
    assert.equal(await page.locator('#sac-wizard-panel-due').getByLabel('یادداشت (اختیاری)').inputValue(),
      'یادداشت حفظ شود');
    await page.locator('.sac-wizard-step-nav button').nth(4).click();
    assert.match(await page.locator('.sac-wizard-sticky-amount strong').textContent(),/۱۵۹٬۰۰۰/);
    await assertTouchTargets(page,'stage 5 / review');
    const mobileMetrics=await page.evaluate(()=>({
      width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,
      note:document.querySelector('.sac-wizard-review-status')?.textContent,
      amount:document.querySelector('.sac-wizard-sticky-amount strong')?.textContent,
      footer:document.querySelector('.sac-wizard-sticky-footer')?.getBoundingClientRect().toJSON()}));
    assert.equal(mobileMetrics.overflow,false);
    checkpoint('390px no viewport overflow and sticky summary',mobileMetrics);
    await page.screenshot({path:path.join(evidence,'invoice-guided-390.png')});
    report.screenshots.push('invoice-guided-390.png');
    const axePath=process.env.INVOICE_WIZARD_AXE;
    if(!axePath||!fs.existsSync(axePath))throw Error('Set INVOICE_WIZARD_AXE to axe-core/axe.min.js');
    await page.addScriptTag({path:axePath});
    async function axe(label){
      const violations=await page.evaluate(async()=>{
        const result=await window.axe.run(document,{runOnly:{type:'tag',
          values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}});
        return {violations:result.violations.map(v=>({id:v.id,impact:v.impact,
          nodes:v.nodes.map(n=>n.target)})),incomplete:result.incomplete.length};});
      report.axe.push({label,...violations});
      assert.deepEqual(violations.violations.filter(v=>
        ['critical','serious'].includes(v.impact)),[]);
    }
    await axe('guided-390');
    await page.setViewportSize({width:1440,height:900});
    await page.locator('.sac-wizard-view').getByRole('button',{name:'حالت حرفه‌ای'}).click();
    assert.equal(await page.locator('#sac-wizard-panel-document').isVisible(),true);
    assert.equal(await page.locator('#sac-wizard-panel-lines').isVisible(),true);
    assert.equal(await page.locator('#sac-wizard-panel-tax').isVisible(),true);
    assert.equal(await page.locator('#sac-wizard-panel-due').isVisible(),true);
    assert.equal(await page.locator('#sac-wizard-panel-review').isVisible(),true);
    assert.equal(await page.locator('#sac-wizard-panel-lines input[data-invoice-col="2"]').inputValue(),'160000');
    await page.screenshot({path:path.join(evidence,'invoice-professional-1440.png')});
    report.screenshots.push('invoice-professional-1440.png');
    await axe('professional-1440');
    await page.locator('.sac-wizard-view').getByRole('button',{name:'راهنمای مرحله‌ای'}).click();
    assert.equal(await page.locator('#sac-wizard-panel-review').isVisible(),true);
    await page.locator('.sac-wizard-step-nav button').nth(4).focus();
    await page.keyboard.press('Shift+Tab');
    checkpoint('keyboard focus after wizard navigation',await page.evaluate(()=>({
      tag:document.activeElement?.tagName,
      label:document.activeElement?.getAttribute('aria-label')||document.activeElement?.textContent?.trim().slice(0,35)})));
    await page.screenshot({path:path.join(evidence,'invoice-guided-1440.png')});
    report.screenshots.push('invoice-guided-1440.png');
    await axe('guided-1440');
    await page.locator('.sac-wizard-sticky-actions button[type="submit"]').click();
    await page.waitForTimeout(350);
    const commands=await page.evaluate(()=>window.__invoiceCommandAttempts);
    assert.equal(commands.length,1);
    assert.equal(commands[0].command.type,'invoice.create');
    assert.equal(commands[0].command.lines[0].unitPrice,160000);
    assert.equal(commands[0].command.discount,1000);
    assert.equal(commands[0].command.note,'یادداشت حفظ شود');
    assert.equal(commands[0].command.partyId,'CUSTOMER-QA');
    assert.equal(commands[0].command.invoiceId,generated);
    assert.equal(await page.locator('#sac-wizard-panel-lines input[data-invoice-col="2"]').inputValue(),'160000');
    checkpoint('single explicit save attempts draft only; failed host leaves edited state intact',true);
    await context.close();

    async function openList(capabilities=fixture.capabilities){
      const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR'});
      await context.addInitScript(payload=>{
        window.__invoiceCommandAttempts=[];
        window.madar={standaloneAccountingRead:async()=>structuredClone(payload),
          standaloneAccountingCommand:async req=>{
            window.__invoiceCommandAttempts.push(req);
            throw Error('Synthetic host deliberately rejects mutations');}};
      },{...fixture,capabilities});
      const page=await context.newPage();
      page.on('pageerror',e=>report.errors.push('pageerror: '+e.message));
      await page.goto('http://127.0.0.1:'+port+'/accounting.html',
        {waitUntil:'domcontentloaded'});
      await page.locator('.sac-ribbon-tabs button').first().waitFor();
      await page.locator('.sac-ribbon-tabs').getByRole('button',{
        name:'فاکتورها و سفارش‌ها',exact:true}).click();
      await page.locator('.sac-ribbon-tools').getByRole('button',{
        name:'فاکتورهای فروش',exact:true}).click();
      await page.getByText('INV-QA-DRAFT',{exact:true}).first().waitFor();
      return {page,context};
    }
    const approval=await openList();
    const draftRow=approval.page.locator('tr').filter({hasText:'INV-QA-DRAFT'}).first();
    assert.match(await draftRow.textContent(),/گام بعدی: بازبینی و تأیید/);
    let confirmText='';
    approval.page.once('dialog',async dialog=>{
      confirmText=dialog.message();await dialog.dismiss();});
    await draftRow.getByRole('button',{name:'تأیید',exact:true}).click();
    assert.match(confirmText,/هنوز سندی در دفترکل ثبت نخواهد شد/);
    assert.equal(await approval.page.evaluate(()=>window.__invoiceCommandAttempts.length),0);
    approval.page.once('dialog',async dialog=>dialog.accept());
    await draftRow.getByRole('button',{name:'تأیید',exact:true}).click();
    const approveCommands=await approval.page.evaluate(()=>window.__invoiceCommandAttempts);
    assert.equal(approveCommands.length,1);
    assert.equal(approveCommands[0].command.type,'invoice.approve');
    checkpoint('draft confirmation gates approval; no ledger issue command',true);
    await approval.context.close();
    const issuance=await openList();
    const approvedRow=issuance.page.locator('tr').filter({hasText:'INV-QA-APPROVED'}).first();
    assert.match(await approvedRow.textContent(),/گام بعدی: صدور قطعی/);
    let irreversiblePreview='';
    issuance.page.once('dialog',async dialog=>{
      irreversiblePreview=dialog.message();await dialog.dismiss();});
    await approvedRow.getByRole('button',{name:'صدور سند',exact:true}).click();
    assert.match(irreversiblePreview,/در دفترکل ثبت می‌شود/);
    assert.match(irreversiblePreview,/بهای تمام‌شده/);
    assert.equal(await issuance.page.evaluate(()=>window.__invoiceCommandAttempts.length),0);
    issuance.page.once('dialog',async dialog=>dialog.accept());
    await approvedRow.getByRole('button',{name:'صدور سند',exact:true}).click();
    const issueCommands=await issuance.page.evaluate(()=>window.__invoiceCommandAttempts);
    assert.equal(issueCommands.length,1);
    assert.equal(issueCommands[0].command.type,'invoice.issue');
    const issuedRow=issuance.page.locator('tr').filter({hasText:'INV-QA-ISSUED'}).first();
    assert.match(await issuedRow.textContent(),/تسویه و کنترل انبار/);
    assert.ok(await issuedRow.getByRole('button',{name:'تسویه',exact:true}).isVisible());
    checkpoint('approved and issued states present correct next action and explicit issue preview',true);
    await issuance.context.close();
    const correction=await openList();
    const originalRow=correction.page.locator('tr').filter({hasText:'INV-QA-ISSUED'}).first();
    await originalRow.getByRole('button',{name:'مشاهده جزئیات'}).click();
    await correction.page.getByRole('button',{name:'اصلاح فاکتور صادرشده'}).click();
    await correction.page.locator('#sac-wizard-panel-document')
      .getByLabel('علت اصلاح (الزامی)').fill('اصلاح مبلغ با اجازه مدیر');
    await correction.page.locator('.sac-wizard-step-nav button').nth(4).click();
    assert.ok(await correction.page.locator('#sac-wizard-panel-review').isVisible());
    assert.match(await correction.page.locator('.sac-wizard-impact-warning').textContent(),
      /سند صادرشدهٔ قبلی را برگشت می‌دهد/);
    let correctionPreview='';
    correction.page.once('dialog',async dialog=>{
      correctionPreview=dialog.message();await dialog.dismiss();});
    await correction.page.locator('.sac-wizard-sticky-actions button[type="submit"]').click();
    assert.match(correctionPreview,/سند قطعی قبلی را برگشت می‌دهد/);
    assert.equal(await correction.page.evaluate(()=>window.__invoiceCommandAttempts.length),0);
    correction.page.once('dialog',async dialog=>dialog.accept());
    await correction.page.locator('.sac-wizard-sticky-actions button[type="submit"]').click();
    const correctionCommands=await correction.page.evaluate(()=>window.__invoiceCommandAttempts);
    assert.equal(correctionCommands.length,1);
    assert.equal(correctionCommands[0].command.type,'invoice.correct');
    assert.equal(correctionCommands[0].command.invoiceId,'INV-QA-ISSUED');
    assert.equal(correctionCommands[0].command.reason,'اصلاح مبلغ با اجازه مدیر');
    checkpoint('issued invoice correction explicitly previews reversal and requires confirmation',true);
    await correction.context.close();
    const draftOnly=await openList({canManage:false,canDraft:true,canAdmin:false});
    const draftOnlyRow=draftOnly.page.locator('tr').filter({hasText:'INV-QA-DRAFT'}).first();
    assert.equal(await draftOnlyRow.getByRole('button',{name:'تأیید',exact:true}).count(),0);
    assert.equal(await draftOnly.page.locator('tr').filter({hasText:'INV-QA-APPROVED'})
      .getByRole('button',{name:'صدور سند',exact:true}).count(),0);
    checkpoint('draft-only role cannot approve or issue through the UI',true);
    await draftOnly.context.close();
  }catch(err){report.errors.push(err.stack||String(err));}
  finally{
    if(browser)await browser.close().catch(()=>{});
    server.kill();
    fs.writeFileSync(path.join(evidence,'report.json'),JSON.stringify(report,null,2),'utf8');
    console.log(JSON.stringify({checks:report.checks,axe:report.axe,
      errors:report.errors,screenshots:report.screenshots},null,2));
  }
  if(report.errors.length)process.exitCode=1;
}
main();
