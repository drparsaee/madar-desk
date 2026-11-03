'use strict';
// Standalone Chromium/axe 4.14.0 gate for the actual 1.0.13 accounting UI.
// All finance data comes from accounting_core in memory; mutation bridge fails.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const {spawnSync}=require('node:child_process');

const root=path.resolve(__dirname,'..');
const axePath=process.env.MADAR_UXQA_AXE_PATH||
  path.join(root,'.qa-uxqa-tools','node_modules','axe-core','axe.min.js');
const playwrightPath=process.env.MADAR_UXQA_PLAYWRIGHT||
  path.join(process.env.APPDATA||'','npm','node_modules','playwright');
const targetViewports=process.env.MADAR_UXQA_WIDTH?
  [Number(process.env.MADAR_UXQA_WIDTH)]:[390,560,768,1440];
const targetThemes=process.env.MADAR_UXQA_THEME?
  [process.env.MADAR_UXQA_THEME]:['dark','light'];

const freePort=()=>new Promise((resolve,reject)=>{
  const socket=net.createServer();socket.once('error',reject);
  socket.listen(0,'127.0.0.1',()=>{
    const port=socket.address().port;
    socket.close(error=>error?reject(error):resolve(port));
  });
});

function fixture(){
  const run=spawnSync('python',['-B','scripts/madar_ux_fixture_20261103.py'],{
    cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'},
    maxBuffer:8*1024*1024});
  assert.equal(run.status,0,'Synthetic in-memory ledger failed: '+run.stderr);
  const data=JSON.parse(run.stdout);
  assert.equal(data.view.currency,'RIAL');
  assert.equal(Object.keys(data.view.invoices).length,2);
  return data;
}

test('actual integrated accounting UI has zero serious/critical axe 4.14 issues at all five invoice stages',
  {timeout:240000},async t=>{
    assert.ok(fs.existsSync(axePath),'Missing exact axe-core 4.14.0; set MADAR_UXQA_AXE_PATH');
    const version=JSON.parse(fs.readFileSync(path.join(path.dirname(axePath),'package.json'),'utf8')).version;
    assert.equal(version,'4.14.0','Do not silently test against a different axe version');
    const {chromium}=require(playwrightPath);
    const ledger=fixture();
    const {build,preview}=await import('vite');
    await build({root,logLevel:'error'});
    const port=await freePort();
    const server=await preview({root,logLevel:'error',
      preview:{host:'127.0.0.1',port,strictPort:true}});
    const failures=[];
    let browser;
    try{
      browser=await chromium.launch({channel:'msedge',headless:true});
      for(const theme of targetThemes)for(const width of targetViewports){
        const scope=theme+'/'+width;
        const context=await browser.newContext({viewport:{width,height:850},
          colorScheme:theme,locale:'fa-IR',timezoneId:'Asia/Tehran',reducedMotion:'reduce'});
        try{
          await context.addInitScript(({ledger,theme})=>{
            localStorage.setItem('madar-ui-theme',theme);
            window.__uxqaMutationCount=0;
            window.madar={
              standaloneAccountingRead:async()=>structuredClone(ledger),
              standaloneAccountingCommand:async()=>{
                window.__uxqaMutationCount++;
                throw Error('Synthetic audit never writes financial data');
              }
            };
          },{ledger,theme});
          const page=await context.newPage();
          page.on('pageerror',error=>failures.push({scope,type:'pageerror',message:error.message}));
          const url=new URL('accounting.html',server.resolvedUrls.local[0]).href;
          const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000});
          assert.equal(response.status(),200,scope+' HTTP status');
          await page.locator('.sac-simple-nav [data-accounting-tab]').first()
            .waitFor({state:'visible',timeout:15000});
          const audit=async stage=>{
            await page.addScriptTag({path:axePath});
            const report=await page.evaluate(async()=>{
              const result=await window.axe.run(document);
              return {version:window.axe.version,
                severe:result.violations.filter(v=>['serious','critical'].includes(v.impact))
                  .map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({
                    target:n.target,summary:n.failureSummary,html:n.html}))})),
                incomplete:result.incomplete.length};
            });
            assert.equal(report.version,'4.14.0');
            if(report.severe.length)failures.push({scope,stage,...report});
          };
          await audit('home');
          const quick=page.locator('.sac-nav-quick-actions [data-accounting-action="invoice"]');
          if(await quick.isVisible())await quick.click();
          else await page.locator('.sac-ah-action.sac-ah-sale').click();
          await page.locator('.sac-invoice-editor').waitFor({state:'visible'});
          assert.equal(await page.locator('.sac-wizard-step-nav button').count(),5,
            scope+' five guided steps');
          await audit('document');
          await page.locator('#sac-wizard-panel-document input[dir=ltr]').first()
            .fill('UX-AXE-VALID-001');
          await page.locator('#sac-wizard-panel-document select').first().selectOption({index:1});
          const next=async()=>{
            await page.locator('.sac-wizard-sticky-actions button.sac-primary').click();
            await page.waitForTimeout(55);
          };
          await next();
          assert.match(await page.locator('.sac-wizard-step-nav [aria-current=step]').textContent(),/اقلام/);
          await audit('lines');
          await page.locator('#sac-wizard-panel-lines [data-invoice-col="0"]').first().fill('Axe QA service');
          await page.locator('#sac-wizard-panel-lines [data-invoice-col="2"]').first().fill('25000');
          await next();
          assert.match(await page.locator('.sac-wizard-step-nav [aria-current=step]').textContent(),/مالیات/);
          await audit('tax');
          await next();
          assert.match(await page.locator('.sac-wizard-step-nav [aria-current=step]').textContent(),/پرداخت/);
          await audit('due');
          await next();
          assert.match(await page.locator('.sac-wizard-step-nav [aria-current=step]').textContent(),/مرور/);
          assert.equal(await page.locator('.sac-wizard-impact-warning').isVisible(),true,
            scope+' financial warning must remain visible');
          await audit('review');
          assert.equal(await page.evaluate(()=>window.__uxqaMutationCount),0,
            scope+' must not issue a financial command');
          await page.close();
        }finally{await context.close();}
      }
      assert.equal(failures.length,0,JSON.stringify(failures,null,2));
      t.diagnostic('PASS: '+(targetViewports.length*targetThemes.length*6)+
        ' exact axe-core 4.14.0 scans, '+targetViewports.join('/')+' widths, '+
        targetThemes.join('/')+' themes, home plus five wizard stages.');
    }finally{
      if(browser)await browser.close();
      await new Promise(resolve=>server.httpServer.close(resolve));
    }
  });
