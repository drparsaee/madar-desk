/* Synthetic, non-mutating browser DOM/UI review of the built Madar 1.0.11 accounting page.
 * This is not a packaged-desktop or authenticated-host end-to-end test.
 */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const {spawn, spawnSync} = require('node:child_process');
const {chromium} = require(path.join(process.env.APPDATA, 'npm', 'node_modules', 'playwright'));

const root = path.resolve(__dirname, '..');
const dist = path.join(root, 'dist');
const evidence = path.join(root, 'docs', 'modernization', 'evidence', 'uiux_20261103');
fs.mkdirSync(evidence, {recursive:true});

const fixtureCode = `
import json
from accounting_core import empty_rial_accounting_state,apply_accounting_command,accounting_view
state=empty_rial_accounting_state()
users=[{"username":"root","role":"admin","financeEdit":True,"financeView":True}]
now="2026-11-03T10:00:00Z"
commands=[
{"type":"party.register","partyId":"CUSTOMER-QA","name":"مشتری آزمایشی","kind":"customer"},
{"type":"party.register","partyId":"SUPPLIER-QA","name":"تأمین‌کننده آزمایشی","kind":"vendor"},
{"type":"invoice.create","invoiceId":"QA-INV-001","partyId":"CUSTOMER-QA","documentDate":"2026-11-01","lines":[{"description":"خدمت آزمایشی","quantity":2,"unitPrice":150000}]},
{"type":"invoice.approve","invoiceId":"QA-INV-001"},
{"type":"invoice.issue","invoiceId":"QA-INV-001","postingDate":"2026-11-02"},
]
for i,c in enumerate(commands):
  outcome=apply_accounting_command(state,{**c,"eventId":"AUDIT-"+str(i+1)},actor="root",accounts=users,now=now)
  state=outcome["state"]
view=accounting_view(state,actor="root",accounts=users)
print(json.dumps({"revision":len(commands),"view":view,"capabilities":{"canManage":True,"canDraft":True,"canAdmin":True}},ensure_ascii=False))
`;
const py = spawnSync('python', ['-B','-c',fixtureCode], {cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'},maxBuffer:8*1024*1024});
if(py.status!==0)throw new Error('Synthetic fixture failed: '+py.stderr);
const fixture=JSON.parse(py.stdout);

function getFreePort(){
  return new Promise((resolve,reject)=>{
    const s=net.createServer();
    s.on('error',reject);
    s.listen(0,'127.0.0.1',()=>{const port=s.address().port;s.close(()=>resolve(port));});
  });
}
function domAudit(){
  const visible = el => {const r=el.getBoundingClientRect(),s=getComputedStyle(el);return s.visibility!=='hidden'&&s.display!=='none'&&r.width>0&&r.height>0};
  const roots=[...document.querySelectorAll('.sac-root')];
  const root=roots[0];
  const nav=[...document.querySelectorAll('.sac-ribbon-tabs button')].filter(visible);
  const ribbonActions=[...document.querySelectorAll('.sac-ribbon-tools button')].filter(visible);
  const controls=[...document.querySelectorAll('.sac-main input,.sac-main select,.sac-main textarea')].filter(visible);
  const nameless=controls.filter(c=>!c.getAttribute('aria-label')&&!c.getAttribute('aria-labelledby')&&!c.closest('label')&&!c.labels?.length);
  const buttons=[...document.querySelectorAll('.sac-main button')].filter(visible);
  const namelessButtons=buttons.filter(b=>!(b.textContent||'').trim()&&!b.getAttribute('aria-label')&&!b.getAttribute('title'));
  const smallButtons=buttons.filter(b=>{const r=b.getBoundingClientRect();return (r.width<36||r.height<36)&&!b.disabled;});
  const main=document.querySelector('.sac-main');
  const body=document.querySelector('.sac-body');
  const h1=document.querySelector('.sac-header h1');
  const tables=[...document.querySelectorAll('.sac-table-wrap')].filter(visible).map(t=>({scrollWidth:t.scrollWidth,clientWidth:t.clientWidth}));
  const labels=[...document.querySelectorAll('.sac-invoice-editor label.sac-field span,.sac-invoice-editor .sac-field>span')].filter(visible);
  const rgb=s=>{const m=String(s).match(/rgba?\((\d+)[, ]+(\d+)[, ]+(\d+)/);return m?[+m[1],+m[2],+m[3]]:null;};
  const luminance=c=>{const v=c.map(x=>x/255).map(x=>x<=0.04045?x/12.92:((x+0.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722;};
  const labelsContrast=labels.map(el=>{
    let parent=el,bg='rgba(0, 0, 0, 0)';
    while(parent&&parent.nodeType===1){
      const value=getComputedStyle(parent).backgroundColor;
      if(value&&value!=='transparent'&&!value.endsWith(', 0)')&&!value.endsWith(',0)')){bg=value;break;}
      parent=parent.parentElement;
    }
    const fg=getComputedStyle(el).color,a=rgb(fg),b=rgb(bg);
    const contrast=a&&b?(Math.max(luminance(a),luminance(b))+.05)/(Math.min(luminance(a),luminance(b))+.05):null;
    return {text:(el.textContent||'').trim().slice(0,40),fg,bg,contrast:contrast&&Math.round(contrast*100)/100};
  });
  return {
    title:document.title,lang:document.documentElement.lang,htmlDir:document.documentElement.dir,
    viewport:{width:innerWidth,height:innerHeight},rootDir:root?.dir||getComputedStyle(root).direction,
    rootSize:root?{width:Math.round(root.getBoundingClientRect().width),height:Math.round(root.getBoundingClientRect().height)}:null,
    heading:(h1?.textContent||'').trim(),navbar:nav.map(x=>({text:(x.textContent||'').trim(),active:x.classList.contains('active')})),
    ribbonActions:ribbonActions.map(x=>({text:(x.textContent||'').trim(),selected:x.classList.contains('selected')})),
    controlCount:controls.length,unlabelledControlCount:nameless.length,
    unlabelledControls:nameless.slice(0,12).map(x=>({tag:x.tagName,outer:x.outerHTML.slice(0,175)})),
    buttonCount:buttons.length,unlabelledButtonCount:namelessButtons.length,
    unlabelledButtons:namelessButtons.slice(0,12).map(x=>x.outerHTML.slice(0,170)),
    undersizedButtonCount:smallButtons.length,undersizedButtons:smallButtons.slice(0,8).map(x=>({text:x.textContent?.trim().slice(0,35),label:x.getAttribute('aria-label'),width:Math.round(x.getBoundingClientRect().width),height:Math.round(x.getBoundingClientRect().height)})),
    horizontalOverflow:document.documentElement.scrollWidth>innerWidth,
    ribbonTabsScroll:(document.querySelector('.sac-ribbon-tabs')?.scrollWidth||0)>(document.querySelector('.sac-ribbon-tabs')?.clientWidth||0),
    ribbonToolsScroll:(document.querySelector('.sac-ribbon-tools')?.scrollWidth||0)>(document.querySelector('.sac-ribbon-tools')?.clientWidth||0),
    bodyScrollHeight:body?.scrollHeight,bodyClientHeight:body?.clientHeight,
    mainWidth:main?.clientWidth,tables
    ,fieldLabelsContrast:labelsContrast.slice(0,25)
  };
}
async function main(){
  const port=await getFreePort();
  const server=spawn('python',['-m','http.server',String(port),'--bind','127.0.0.1','--directory',dist],{cwd:root,stdio:'ignore',windowsHide:true});
  let browser;
  const report={baseline:'Madar Desk 1.0.11 / 53dcd69',mode:'Chromium headless with synthetic read-only API, built Vite page',testedAt:new Date().toISOString(),steps:[],errors:[],consoleErrors:[],visuals:[],accessibility:[]};
  try{
    let ok=false;
    for(let n=0;n<45;n++){
      try{const r=await fetch('http://127.0.0.1:'+port+'/accounting.html');if(r.ok){ok=true;break;}}catch{}
      await new Promise(resolve=>setTimeout(resolve,150));
    }
    if(!ok)throw Error('Static built Vite host did not serve accounting.html');
    browser=await chromium.launch({headless:true,channel:'chrome'});
    const context=await browser.newContext({viewport:{width:1440,height:900},locale:'fa-IR',reducedMotion:'reduce'});
    await context.addInitScript(payload=>{
      window.madar={
        standaloneAccountingRead:async()=>structuredClone(payload),
        standaloneAccountingCommand:async()=>{throw new Error('Synthetic UI audit is read only');}
      };
    },fixture);
    const page=await context.newPage();
    page.on('pageerror',err=>report.errors.push(err.message));
    page.on('console',msg=>{if(msg.type()==='error')report.consoleErrors.push(msg.text())});
    const url='http://127.0.0.1:'+port+'/accounting.html';
    await page.goto(url,{waitUntil:'domcontentloaded'});
    await page.locator('.sac-ribbon-tabs button').first().waitFor({timeout:15000});
    await page.waitForTimeout(700);
    const axePath=path.join(root,'.uiux-tools','node_modules','axe-core','axe.min.js');
    const axeAvailable=fs.existsSync(axePath);
    async function auditAxe(checkpoint){
      if(!axeAvailable){report.accessibility.push({checkpoint,status:'NOT_AVAILABLE'});return;}
      await page.addScriptTag({path:axePath});
      const result=await page.evaluate(async()=>{
        const r=await window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}});
        return {violations:r.violations.map(v=>({id:v.id,impact:v.impact,description:v.help,affected:v.nodes.length,nodes:v.nodes.slice(0,4).map(n=>({target:n.target,summary:n.failureSummary?.slice(0,260)}))})),incomplete:r.incomplete.length,passes:r.passes.length};
      });
      report.accessibility.push({checkpoint,status:'MEASURED',...result});
    }
    const desktop=await page.evaluate(domAudit);
    report.steps.push({checkpoint:'desktop/overview',data:desktop});
    await auditAxe('desktop/overview');
    await page.screenshot({path:path.join(evidence,'01-overview-1440.png'),fullPage:false});
    report.visuals.push('01-overview-1440.png');
    const navs=await page.locator('.sac-sidebar nav button').allTextContents();
    const labels=navs.map(x=>x.trim());
    report.navLabels=labels;
    const targets=[
      {name:'invoice',group:'فاکتورها و سفارش‌ها',contains:'فاکتورهای فروش'},
      {name:'purchase',group:'فاکتورها و سفارش‌ها',contains:'صورت‌حساب‌های خرید'},
      {name:'parties',group:'اشخاص و کالا',contains:'اشخاص'},
      {name:'reports',group:'گزارش‌ها و سوابق',contains:'گزارش‌های مالی'},
      {name:'bank',group:'خزانه و پرداخت',contains:'صندوق، بانک'},
      {name:'ledger',group:'حسابداری',contains:'حساب‌ها'},
      {name:'migration',group:'گزارش‌ها و سوابق',contains:'سوابق انتقالی پارسیان'},
    ];
    for(const target of targets){
      const i=labels.findIndex(x=>x.includes(target.contains));
      if(i<0){report.steps.push({checkpoint:'nav/'+target.name,status:'NOT_FOUND'});continue;}
      const groupButton=page.locator('.sac-ribbon-tabs').getByRole('button',{name:target.group,exact:true});
      const toolButton=page.locator('.sac-ribbon-tools').getByRole('button',{name:labels[i],exact:true});
      let navigated=false,navError='';
      for(let attempt=0;attempt<3&&!navigated;attempt++){
        try{
          await groupButton.click();
          await toolButton.waitFor({state:'visible',timeout:1200});
          await toolButton.click({timeout:3000});
          await page.waitForTimeout(125);
          navigated=true;
        }catch(error){navError=String(error.message).slice(0,300);}
      }
      if(!navigated){
        report.steps.push({checkpoint:'nav/'+target.name,status:'FAIL',error:navError});
        continue;
      }
      await page.waitForTimeout(200);
      report.steps.push({checkpoint:'nav/'+target.name,data:await page.evaluate(domAudit)});
      if(target.name==='invoice'){
        await page.screenshot({path:path.join(evidence,'02-invoices-1440.png'),fullPage:false});
        report.visuals.push('02-invoices-1440.png');
        await auditAxe('desktop/invoice-list');
      }
    }
    for(const width of [1024,768,560,390]){
      await page.setViewportSize({width,height:844});
      await page.locator('.sac-root').waitFor();
      await page.waitForTimeout(250);
      const overview=labels.findIndex(x=>x.includes('داشبورد'));
      if(overview>=0){
        await page.locator('.sac-ribbon-tabs').getByRole('button',{name:'عمومی',exact:true}).click();
        await page.locator('.sac-ribbon-tools').getByRole('button',{name:labels[overview],exact:true}).click();
      }
      await page.waitForTimeout(150);
      report.steps.push({checkpoint:'responsive/'+width,data:await page.evaluate(domAudit)});
      if(width===768||width===390){
        const png='03-overview-'+width+'.png';
        await page.screenshot({path:path.join(evidence,png),fullPage:false});
        report.visuals.push(png);
      }
      if(width===390)await auditAxe('mobile/overview-390');
    }
    await page.setViewportSize({width:1440,height:900});
    await page.locator('.sac-ribbon-tabs').getByRole('button',{name:'فاکتورها و سفارش‌ها',exact:true}).click();
    const invoice=page.locator('.sac-ribbon-tools').getByRole('button',{name:'فاکتورهای فروش',exact:true});
    await invoice.click({timeout:4500});
    const newInvoice=page.locator('.sac-ribbon-tools').getByRole('button',{name:'ثبت فاکتور جدید',exact:true});
    if(await newInvoice.isVisible().catch(()=>false)){
      await newInvoice.click();
      await page.waitForTimeout(250);
      report.steps.push({checkpoint:'invoice-composer/1440',data:await page.evaluate(domAudit)});
      await page.screenshot({path:path.join(evidence,'04-invoice-composer-1440.png'),fullPage:false});
      report.visuals.push('04-invoice-composer-1440.png');
      await auditAxe('desktop/invoice-composer');
      await page.setViewportSize({width:390,height:844});
      await page.waitForTimeout(200);
      report.steps.push({checkpoint:'invoice-composer/390',data:await page.evaluate(domAudit)});
      await page.screenshot({path:path.join(evidence,'05-invoice-composer-390.png'),fullPage:false});
      report.visuals.push('05-invoice-composer-390.png');
      await auditAxe('mobile/invoice-composer-390');
    } else {
      report.steps.push({checkpoint:'invoice-composer',status:'ACTION_NOT_VISIBLE'});
    }
    const focus=await page.keyboard.press('Tab').then(()=>page.evaluate(()=>({tag:document.activeElement?.tagName,outer:document.activeElement?.outerHTML?.slice(0,250)})));
    report.keyboardTab=focus;
    await context.close();
  }catch(error){
    report.errors.push(String(error.stack||error));
  }finally{
    if(browser)await browser.close().catch(()=>{});
    server.kill();
    fs.writeFileSync(path.join(evidence,'layout_report.json'),JSON.stringify(report,null,2),'utf8');
    console.log(JSON.stringify({steps:report.steps.length,errors:report.errors,consoleErrors:report.consoleErrors,navLabels:report.navLabels,visuals:report.visuals,report:path.join(evidence,'layout_report.json')},null,2));
  }
  if(report.errors.length)process.exitCode=1;
}
main();
