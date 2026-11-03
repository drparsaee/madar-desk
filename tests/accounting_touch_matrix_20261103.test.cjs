'use strict';
/** Real Chrome layout QA. In-memory RIAL fixture; no file, host or ledger mutations. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const {spawnSync}=require('node:child_process');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPath=path.join(process.env.APPDATA||'','npm','node_modules','playwright');
const fixtureCode=`
import json
from accounting_core import empty_rial_accounting_state,apply_accounting_command,accounting_view
from accounting_reporting import ledger_reports
state=empty_rial_accounting_state()
accounts={"root":{"username":"root","role":"admin","financeEdit":True,"financeView":True}}
commands=[
 {"type":"party.register","partyId":"TOUCH-CUSTOMER","name":"مشتری تست لمس","kind":"customer"},
 {"type":"invoice.create","invoiceId":"TOUCH-INVOICE","partyId":"TOUCH-CUSTOMER",
  "documentDate":"2026-11-01","lines":[{"description":"خدمت آزمون","quantity":1,"unitPrice":100000}]},
 {"type":"invoice.approve","invoiceId":"TOUCH-INVOICE"},
 {"type":"invoice.issue","invoiceId":"TOUCH-INVOICE","postingDate":"2026-11-02"}
]
for i,command in enumerate(commands):
 state=apply_accounting_command(state,{**command,"eventId":"TOUCH-TEST-"+str(i+1)},
   actor="root",accounts=accounts,now="2026-11-03T10:00:00Z")["state"]
view=accounting_view(state,actor="root",accounts=accounts)
view["financialReports"]=ledger_reports(view)
print(json.dumps({"revision":len(commands),"view":view,
 "capabilities":{"canView":True,"canManage":True,"canDraft":True,"canAdmin":True},
 "currentUser":{"username":"touch.qa","role":"admin","jobTitle":""}},ensure_ascii=False))
`;
const freePort=()=>new Promise((resolve,reject)=>{
  const server=net.createServer();server.once('error',reject);
  server.listen(0,'127.0.0.1',()=>{
    const port=server.address().port;
    server.close(error=>error?reject(error):resolve(port));
  });
});

const REQUIRED=[
  '.sac-ux-shell .sac-nav-search-trigger',
  '.sac-ux-shell .sac-nav-mode button',
  '.sac-ux-shell .sac-ribbon-exit',
  '.sac-simple-nav button',
  '.sac-ah-actions button',
  '.sac-ah-card button',
  '.sac-ah-customize>summary',
  '.sac-vtr-home button',
];

async function inspect(page,width,theme,mode){
  const sizes=await page.evaluate(selectors=>{
    const visible=node=>{
      const style=getComputedStyle(node),r=node.getBoundingClientRect();
      return r.width>0&&r.height>0&&style.display!=='none'&&style.visibility!=='hidden';
    };
    const matches=selectors.flatMap(selector=>
      [...document.querySelectorAll(selector)].filter(visible).map(el=>{
        const rect=el.getBoundingClientRect();
        return {selector,label:(el.getAttribute('aria-label')||el.textContent||'').trim().slice(0,45),
          width:Math.round(rect.width*100)/100,height:Math.round(rect.height*100)/100,
          left:rect.left,right:rect.right};
      }));
    return {
      matches,documentWidth:document.documentElement.scrollWidth,
      viewportWidth:innerWidth,
      simpleNavigationRows:(()=>{
        const nav=document.querySelector('.sac-simple-nav');
        if(!nav||!visible(nav))return 0;
        const tops=[...nav.querySelectorAll('button')].filter(visible)
          .map(el=>el.getBoundingClientRect().top);
        if(!tops.length)return 0;
        // Fractional CSS pixel rounding can offset adjacent controls by 0.5px.
        return Math.max(...tops)-Math.min(...tops)<1?1:2;
      })(),
      simpleNavigationButtons:(()=>{
        const nav=document.querySelector('.sac-simple-nav');
        if(!nav)return [];
        return [...nav.querySelectorAll('button')].filter(visible).map(el=>({
          label:el.textContent.trim(),top:el.getBoundingClientRect().top,
          width:el.getBoundingClientRect().width}));
      })(),
      titlebarWidth:document.querySelector('.sac-ribbon-titlebar')?.getBoundingClientRect().width,
    };
  },REQUIRED);
  assert.ok(sizes.matches.length>15,`No meaningful controls at ${width}/${theme}/${mode}`);
  const undersized=sizes.matches.filter(item=>item.width<43.9||item.height<43.9);
  assert.deepEqual(undersized,[],`UX-06 touch control violations at ${width}/${theme}/${mode}`);
  assert.ok(sizes.documentWidth<=sizes.viewportWidth+1,
    `Document-level overflow at ${width}/${theme}/${mode}: ${JSON.stringify(sizes)}`);
  if(width<=700)assert.equal(sizes.simpleNavigationRows,1,
    `Novice navigation must stay one row at ${width}/${theme}/${mode}: ${JSON.stringify(sizes.simpleNavigationButtons)}`);
  for(const selector of ['.sac-nav-search-trigger','.sac-nav-mode button','.sac-ribbon-exit']){
    const target=page.locator('.sac-ux-shell '+selector).first();
    await target.focus();
    await page.keyboard.press('Tab');
    await page.keyboard.press('Shift+Tab');
    assert.equal(await target.evaluate(node=>node===document.activeElement),true,
      `Keyboard focus missing on ${selector} at ${width}/${theme}/${mode}`);
    assert.equal(await target.evaluate(node=>getComputedStyle(node).outlineStyle),'solid',
      `Visible outline missing on ${selector} at ${width}/${theme}/${mode}`);
  }
  return {width,theme,mode,count:sizes.matches.length,
    minWidth:Math.min(...sizes.matches.map(v=>v.width)),
    minHeight:Math.min(...sizes.matches.map(v=>v.height)),
    simpleNavigationRows:sizes.simpleNavigationRows,
    documentWidth:sizes.documentWidth};
}

test('UX-06 Chrome eight-width/theme matrix with novice and advanced keyboard controls',{
  timeout:120000
},async()=>{
  assert.ok(fs.existsSync(chrome),`Required Chrome unavailable: ${chrome}`);
  assert.ok(fs.existsSync(playwrightPath),`Required Playwright unavailable: ${playwrightPath}`);
  const python=spawnSync('python',['-B','-c',fixtureCode],{
    cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'},
    maxBuffer:8*1024*1024
  });
  assert.equal(python.status,0,python.stderr||python.stdout);
  const payload=JSON.parse(python.stdout);
  const {chromium}=require(playwrightPath);
  const {createServer}=await import('vite');
  const evidenceDir=process.env.MADAR_TOUCH_EVIDENCE_DIR;
  if(evidenceDir)fs.mkdirSync(evidenceDir,{recursive:true});
  const server=await createServer({root,logLevel:'error',server:{
    host:'127.0.0.1',port:await freePort(),strictPort:true,
    fs:{allow:[root,path.resolve(root,'..','madar-desk','node_modules')]}
  }});
  let browser;
  try{
    await server.listen();
    browser=await chromium.launch({headless:true,executablePath:chrome});
    const page=await browser.newPage({locale:'fa-IR',viewport:{width:1440,height:900},
      reducedMotion:'reduce'});
    page.on('pageerror',error=>{throw Error('Browser page error: '+error.message);});
    await page.addInitScript(data=>{
      window.madar={
        standaloneAccountingRead:async()=>structuredClone(data),
        standaloneAccountingCommand:async()=>{throw Error('Synthetic host cannot post');}
      };
    },payload);
    await page.goto(new URL('accounting.html',server.resolvedUrls.local[0]).href,
      {waitUntil:'domcontentloaded'});
    await page.locator('.sac-ah-actions .sac-ah-action').first().waitFor();
    const checked=[];
    for(const theme of ['light','dark']){
      await page.evaluate(value=>{
        document.documentElement.dataset.theme=value;
      },theme);
      for(const width of [390,560,768,1440]){
        await page.setViewportSize({width,height:width<=560?844:900});
        for(const mode of ['simple','advanced']){
          const button=page.getByRole('group',{name:'سطح نمایش حسابداری'})
            .getByRole('button',{name:mode==='simple'?'ساده':'پیشرفته'});
          await button.click();
          assert.equal(await button.getAttribute('aria-pressed'),'true');
          checked.push(await inspect(page,width,theme,mode));
          if(evidenceDir&&(width===390||width===1440)&&
            (mode==='simple'||width===390&&theme==='dark')){
            await page.screenshot({path:path.join(evidenceDir,
              `touch-${width}-${theme}-${mode}.png`),fullPage:false});
          }
        }
      }
    }
    if(evidenceDir)fs.writeFileSync(path.join(evidenceDir,'measurements.json'),
      JSON.stringify(checked,null,2),'utf8');
    console.log('TOUCH_MATRIX_EVIDENCE='+JSON.stringify(checked));
  }finally{
    await browser?.close();
    server.httpServer?.closeAllConnections?.();
    await server.close();
  }
});
