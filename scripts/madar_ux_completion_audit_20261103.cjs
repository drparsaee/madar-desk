'use strict';
/**
 * Reproducible UX-01..10 audit of the real Vite accounting UI, in headless
 * Chromium with axe-core 4.14.0 and an in-memory synthetic RIAL ledger.
 * This runner deliberately exits non-zero for unmet acceptance criteria.
 * It never sends a successful accounting mutation to the synthetic bridge.
 */
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const {spawnSync}=require('node:child_process');
const {observation,assessAxe,assessContrast,assessTouch,summarize}=
  require('./madar_ux_acceptance_rules_20261103.cjs');

const root=path.resolve(__dirname,'..');
const outDir=path.join(root,'.qa-uxqa-20261103');
const axePath=process.env.MADAR_UXQA_AXE_PATH||
  path.join(root,'.qa-uxqa-tools','node_modules','axe-core','axe.min.js');
const widths=[390,560,768,1440];
const themes=['dark','light'];
const report={format:1,baseline:'6bf687b4b643fb26b0186dc1b0d425f1b2ad0c29',
  runUTC:new Date().toISOString(),scope:'Synthetic accounting UI, Chromium + axe 4.14.0',
  matrix:[],checks:[],errors:[],limitations:[],toolchain:{}};
const save=()=>{
  fs.mkdirSync(outDir,{recursive:true});
  report.summary=summarize(report.checks);
  fs.writeFileSync(path.join(outDir,'acceptance.json'),JSON.stringify(report,null,2)+'\n');
  console.log('UXQA_REPORT '+path.join(outDir,'acceptance.json'));
  console.log('UXQA_SUMMARY '+JSON.stringify(report.summary));
};
const add=(id,status,evidence,context={})=>report.checks.push(observation(id,status,evidence,context));
const errorText=error=>String(error?.message||error).slice(0,650);

function playwrightModule(){
  const tries=[process.env.MADAR_UXQA_PLAYWRIGHT,
    path.join(process.env.APPDATA||'', 'npm','node_modules','playwright'),
    'playwright'];
  for(const location of tries){if(!location)continue;try{return require(location);}catch{}}
  throw Error('Playwright missing; supply MADAR_UXQA_PLAYWRIGHT or install globally');
}
function fixture(){
  const run=spawnSync('python',['-B','scripts/madar_ux_fixture_20261103.py'],{
    cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'},
    maxBuffer:8*1024*1024});
  if(run.status!==0)throw Error('Synthetic in-memory ledger failed: '+run.stderr);
  const payload=JSON.parse(run.stdout);
  if(payload?.view?.currency!=='RIAL'||Object.keys(payload.view.invoices||{}).length!==2)
    throw Error('Synthetic fixture invariant failed (RIAL / issued+draft)');
  return payload;
}
function freePort(){return new Promise((resolve,reject)=>{
  const socket=net.createServer();socket.once('error',reject);
  socket.listen(0,'127.0.0.1',()=>{
    const port=socket.address().port;socket.close(err=>err?reject(err):resolve(port));
  });
});}

function pageMetrics(){
  const visible=el=>{
    const r=el.getBoundingClientRect(),s=getComputedStyle(el);
    return !!(r.width&&r.height&&s.display!=='none'&&s.visibility!=='hidden');
  };
  const color=text=>{
    const values=String(text).match(/\d+(?:\.\d+)?/g);
    return values&&values.length>=3?values.slice(0,3).map(Number):null;
  };
  const light=rgb=>{
    const linear=rgb.map(value=>{
      const v=value/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;
    });
    return .2126*linear[0]+.7152*linear[1]+.0722*linear[2];
  };
  const contrast=el=>{
    const fg=color(getComputedStyle(el).color);
    let ancestor=el,bg=null,unresolved=false;
    while(ancestor&&ancestor.nodeType===1){
      const style=getComputedStyle(ancestor);
      if(style.backgroundImage!=='none')unresolved=true;
      const alpha=(style.backgroundColor.match(/[\d.]+/g)||[])[3];
      if(alpha!==undefined&&Number(alpha)<1)unresolved=true;
      if(style.backgroundColor!=='transparent'&&alpha!=='0'&&alpha!==0&&
          !style.backgroundColor.endsWith(', 0)')&&!style.backgroundColor.endsWith(',0)')){
        bg=color(style.backgroundColor);break;
      }
      ancestor=ancestor.parentElement;
    }
    if(unresolved||!fg||!bg)return null;
    const a=light(fg),b=light(bg);
    return Math.round((Math.max(a,b)+.05)/(Math.min(a,b)+.05)*100)/100;
  };
  const labels=[...document.querySelectorAll(
    '.sac-invoice-editor label.sac-field>span,.sac-invoice-editor .sac-field>span,'+
    '.sac-invoice-editor .sac-panel-title p,.sac-vtr-due-title h3,'+
    '.sac-vtr-due-item strong,.sac-vtr-due-item small')].filter(visible);
  const samples=labels.map(el=>({text:(el.textContent||'').trim().slice(0,55),
    ratio:contrast(el)}));
  const targets=[...document.querySelectorAll(
    '.sac-ribbon-quick button,.sac-vtr-cta,.sac-vtr-due-actions button,'+
    '.sac-invoice-commandbar-actions button,.sac-workflow-actions button,'+
    '.sac-ribbon-tabs button,.sac-ribbon-tools button,'+
    '.sac-simple-nav button,.sac-nav-quick-actions button')].filter(el=>visible(el)&&!el.disabled)
    .map(el=>({text:(el.getAttribute('aria-label')||el.textContent||'').trim().slice(0,44),
      width:Math.round(el.getBoundingClientRect().width),
      height:Math.round(el.getBoundingClientRect().height)}));
  const scrollables=[...document.querySelectorAll('.sac-vtr-table-scroll,.sac-ribbon-tabs,.sac-ribbon-tools')]
    .filter(visible).map(el=>({name:el.getAttribute('aria-label')||el.className,
      overflow:el.scrollWidth>el.clientWidth+1,tabIndex:el.tabIndex,
      scrollWidth:el.scrollWidth,clientWidth:el.clientWidth,
      hasName:!!(el.getAttribute('aria-label')||el.getAttribute('aria-labelledby'))}));
  const composer=document.querySelector('.sac-invoice-editor');
  const activeActions=[...document.querySelectorAll(
    '.sac-invoice-commandbar-actions button,.sac-wizard-sticky-footer button,'+
    '.sac-invoice-summary button.sac-summary-save,.sac-invoice-editor .sac-form-actions button')]
    .filter(el=>visible(el)&&!el.disabled&&
      /ذخیره|پیش‌نویس|ادامه|بعد|مرور|ثبت اصلاح/.test(el.textContent||el.getAttribute('aria-label')||''));
  const activeRects=activeActions.map(el=>el.getBoundingClientRect());
  const heading=(document.querySelector('.sac-header h1')?.textContent||'').trim();
  const actionText=document.querySelector('.sac-vtr-due')?.textContent||'';
  return {heading,theme:document.documentElement.dataset.theme,
    viewport:innerWidth,pageScrollWidth:document.documentElement.scrollWidth,
    horizontalOverflow:document.documentElement.scrollWidth>innerWidth+1,
    labels:samples,targets,scrollables,invoiceForm:!!composer,
    actionableOverview:/دریافتنی|مطالبات/.test(actionText),
    dueSectionText:actionText.slice(0,250),
    saveVisibleInViewport:activeRects.some(rect=>rect.top>=0&&rect.bottom<=innerHeight),
    composerActionCount:activeActions.length,
    activeActionNames:activeActions.map(el=>el.textContent?.trim()?.slice(0,45)),
    hasInvoiceSummary:!!document.querySelector('.sac-invoice-summary,.sac-invoice-totals,'+
      '[aria-label="خلاصه فاکتور"],.sac-wizard-sticky-footer'),
    routeIds:[...document.querySelectorAll('.sac-ribbon-tools [data-accounting-tab],'+
      '.sac-simple-nav [data-accounting-tab],.sac-nav-more-menu [data-accounting-tab]')]
      .filter(visible).map(b=>({id:b.getAttribute('data-route-id')||
        b.getAttribute('data-ux-route')||b.getAttribute('data-accounting-tab')||
        b.getAttribute('data-tab-id')||b.getAttribute('aria-controls')||'',
        label:b.textContent?.trim()?.slice(0,50)})),
    jumpSearchCount:document.querySelectorAll('[data-accounting-action="search"]').length};
}

async function axeScan(page){
  await page.addScriptTag({path:axePath});
  return page.evaluate(async()=>{
    if(!window.axe)throw Error('axe injection failed');
    const result=await window.axe.run(document);
    return {version:window.axe.version,
      violations:result.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.length,
        targets:v.nodes.slice(0,3).map(node=>node.target)})),
      incomplete:result.incomplete.map(v=>({id:v.id,nodes:v.nodes.length})),
      passes:result.passes.length};
  });
}

async function main(){
  fs.mkdirSync(outDir,{recursive:true});
  if(!fs.existsSync(axePath))throw Error('axe-core 4.14.0 not installed at '+axePath);
  const axePkg=JSON.parse(fs.readFileSync(path.join(path.dirname(axePath),'package.json'),'utf8'));
  if(axePkg.version!=='4.14.0')throw Error('Expected axe-core 4.14.0, got '+axePkg.version);
  const sha=spawnSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'});
  report.sourceSHA=sha.stdout.trim();
  const playwright=playwrightModule();
  const payload=fixture();
  report.toolchain={axe:axePkg.version,chromium:await playwright.chromium.executablePath(),
    node:process.version,python:'3.12+',fixture:'RIAL, one issued unpaid invoice and one unposted draft'};
  const {build,preview}=await import('vite');
  await build({root,logLevel:'error'});
  const port=await freePort();
  const server=await preview({root,logLevel:'error',preview:{host:'127.0.0.1',port,strictPort:true}});
  let browser;
  const origin=server.resolvedUrls.local[0];
  const start=async(width,theme,role='admin')=>{
    const context=await browser.newContext({viewport:{width,height:850},locale:'fa-IR',
      timezoneId:'Asia/Tehran',reducedMotion:'reduce',colorScheme:theme});
    const cap=role==='admin'?{canManage:true,canDraft:true,canAdmin:true}:
      role==='editor'?{canManage:false,canDraft:true,canAdmin:false}:
      {canManage:false,canDraft:false,canAdmin:false};
    await context.addInitScript(({payload,cap,theme,role})=>{
      window.localStorage.setItem('madar-ui-theme',theme);
      window.__uxqaCalls=[];
      window.madar={
        standaloneAccountingRead:async()=>structuredClone({...payload,capabilities:cap,
          currentUser:{username:'uxqa-'+role,role,jobTitle:'آزمون رابط'}}),
        standaloneAccountingCommand:async request=>{
          window.__uxqaCalls.push(request);
          throw Error('UX QA fixture blocks all persisted accounting mutations');
        }
      };
    },{payload,cap,theme,role});
    const page=await context.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(errorText(error)));
    const http=await page.goto(new URL('accounting.html',origin).href,
      {waitUntil:'domcontentloaded',timeout:30000});
    if(http.status()!==200)throw Error('Vite accounting page HTTP '+http.status());
    await page.locator('.sac-root').waitFor({state:'visible',timeout:20000});
    // v1.0.13 defaults to the novice navigation. The old unconditional wait
    // for an advanced Ribbon was a false hang, especially at 390/560px.
    if(width>700){
      await page.getByRole('group',{name:'سطح نمایش حسابداری'})
        .getByRole('button',{name:'پیشرفته'}).click();
      await page.locator('.sac-ribbon-tabs button').first()
        .waitFor({state:'visible',timeout:4000});
    }else{
      await page.locator('.sac-simple-nav [data-accounting-tab="invoice"]')
        .waitFor({state:'visible',timeout:4000});
    }
    await page.waitForFunction(()=>!document.querySelector('.sac-alert')?.textContent?.includes('دریافت داده دفترکل'),null,{timeout:9000}).catch(()=>{});
    return {context,page,errors};
  };
  const nav=async(page,key)=>{
    await page.keyboard.press('Control+k');
    const input=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'})
      .getByRole('combobox');
    await input.waitFor({state:'visible',timeout:4000});
    if(!(await input.evaluate(el=>document.activeElement===el)))throw Error('Ctrl+K did not focus search');
    await input.fill(key);
    await page.keyboard.press('Enter');
    return (await page.locator('.sac-header h1').textContent()).trim();
  };
  const newInvoice=async page=>{
    const more=page.locator('.sac-nav-more-trigger:visible').first();
    await more.click({timeout:4000});
    await page.locator('.sac-nav-more-menu').getByRole('button',{name:'فاکتور جدید'})
      .click({timeout:4000});
  };
  const keyboardOperate=async(page,selector,{activate=false}={})=>{
    await page.keyboard.press('Control+k');
    await page.getByRole('dialog',{name:'جست‌وجوی حسابداری'}).waitFor({state:'visible'});
    await page.keyboard.press('Escape'); // Close focus-trapping modal before keyboard-walking page.
    let found=false,tabs=0;
    for(let index=0;index<100;index++){
      await page.keyboard.press('Tab');
      tabs=index+1;
      found=await page.evaluate(css=>{
        const el=document.activeElement;
        return !!el?.matches(css)&&!!el.getClientRects().length&&!el.disabled;
      },selector);
      if(found)break;
    }
    if(!found)return {success:false,tabs,reason:'Tab focus never reached workflow control'};
    const before=await page.evaluate(()=>({tag:document.activeElement.tagName,
      value:document.activeElement.value||'',type:document.activeElement.type||''}));
    if(activate){
      await page.keyboard.press('Enter');
      return {success:await page.locator('.sac-invoice-editor').isVisible().catch(()=>false),
        tabs,before,action:'Enter opens invoice editor'};
    }
    if(before.tag==='INPUT'&&!['date','number','checkbox','radio'].includes(before.type)){
      await page.keyboard.type('UX');
      const after=await page.evaluate(()=>document.activeElement.value);
      return {success:after.includes('UX'),tabs,before,after,action:'typed into focused field'};
    }
    if(before.tag==='SELECT'){
      await page.keyboard.press('ArrowDown');
      const after=await page.evaluate(()=>document.activeElement.value);
      return {success:true,tabs,before,after,action:'keyboard operated focused select'};
    }
    return {success:false,tabs,before,reason:'Focused control has no safe keyboard edit action'};
  };
  try{
    browser=await playwright.chromium.launch({channel:'msedge',headless:true});
    report.toolchain.browser=browser.version();
    for(const theme of themes)for(const width of widths){
      const scope=theme+'/'+width;
      let session;
      try{
        session=await start(width,theme);
        const {page,errors}=session;
        const overview=await page.evaluate(pageMetrics);
        const overviewAxe=await axeScan(page);
        await newInvoice(page);
        await page.locator('.sac-invoice-editor').waitFor({state:'visible',timeout:7000});
        const composer=await page.evaluate(pageMetrics);
        const composerAxe=await axeScan(page);
        const scrollInfo=await page.evaluate(()=>{
          const body=document.querySelector('.sac-body');
          const before=body?.scrollTop||0;
          const middle=body?Math.max(0,(body.scrollHeight-body.clientHeight)/2):0;
          if(body)body.scrollTop=middle;
          return {before,middle,afterMiddle:body?.scrollTop||0,
            scrollHeight:body?.scrollHeight||0,clientHeight:body?.clientHeight||0};
        });
        await page.waitForTimeout(80);
        const composerMidScroll=await page.evaluate(pageMetrics);
        await page.evaluate(()=>{
          const body=document.querySelector('.sac-body');
          if(body)body.scrollTop=body.scrollHeight;
          window.scrollTo(0,document.documentElement.scrollHeight);
        });
        await page.waitForTimeout(80);
        const composerAfterScroll=await page.evaluate(pageMetrics);
        const entry={scope,overview,composer,composerMidScroll,composerAfterScroll,scrollInfo,
          axe:{overview:overviewAxe,composer:composerAxe},errors};
        report.matrix.push(entry);
        for(const [screen,measured,scan] of [['overview',overview,overviewAxe],['composer',composer,composerAxe]]){
          const sample=scope+'/'+screen;
          const axeResult=assessAxe(scan);
          add('UX-02',axeResult.status,axeResult.reason,{scope:sample,
            severe:axeResult.severe,incomplete:axeResult.incomplete});
          const colorViolations=scan.violations.filter(v=>v.id==='color-contrast');
          if(colorViolations.length)add('UX-01','FAIL',
            'axe-core 4.14.0 found actual text contrast violations',
            {scope:sample,colorViolations});
          if(measured.horizontalOverflow)add('UX-07','FAIL','Page-level horizontal overflow',{scope:sample,
            pageScrollWidth:measured.pageScrollWidth,viewport:width});
          else add('UX-07','PASS','No page-level horizontal overflow',{scope:sample});
          const touch=assessTouch(measured.targets);
          add('UX-06',touch.status,touch.reason,{scope:sample,
            count:touch.measured,failures:touch.failures?.slice(0,16)});
        }
        const contrast=assessContrast([...overview.labels,...composer.labels]);
        add('UX-01',contrast.status,contrast.reason,{scope,samples:contrast.sampleCount,
          failures:contrast.failures?.slice(0,16),unresolved:contrast.unresolved?.slice(0,16)});
        if(composer.invoiceForm&&composer.saveVisibleInViewport&&
          composerMidScroll.saveVisibleInViewport&&composerAfterScroll.saveVisibleInViewport&&
          composer.composerActionCount>=1)
          add('UX-05','PASS','Active invoice step action visible at start, middle and end of scroll',{scope,
            actions:composer.activeActionNames,scrollInfo});
        else add('UX-05','FAIL','Invoice form action or save bar not visible without scrolling',{
          scope,invoiceForm:composer.invoiceForm,
          initialVisible:composer.saveVisibleInViewport,
          middleVisible:composerMidScroll.saveVisibleInViewport,
          afterScrollVisible:composerAfterScroll.saveVisibleInViewport,
          actions:composer.activeActionNames,scrollInfo});
        if(overview.actionableOverview)add('UX-04','PASS','Outstanding receivable has visible action context',{scope});
        else add('UX-04','FAIL','Outstanding synthetic issued receivable is not surfaced as receivable',{scope,
          excerpt:overview.dueSectionText});
        const tooWide=overview.scrollables.filter(s=>s.overflow);
        if(tooWide.length){
          const cues=await page.locator('button[aria-label*="بیشتر"],button[aria-label*="پیمایش"],'+
            'button[aria-label*="بعدی"],button[aria-label*="قبلی"],.sac-ribbon-more').count();
          add('UX-07',cues?'PASS':'FAIL',cues?'Overflow has explicit navigation cues':
            'Ribbon overflows with no discoverable more/scroll control',{scope,scrolls:tooWide,cues});
        }
        if(width===390||width===1440){
          const name='invoice-'+theme+'-'+width+'.png';
          await page.screenshot({path:path.join(outDir,name),animations:'disabled'});
          entry.screenshot=name;
        }
        if(errors.length)add('UX-10','FAIL','Uncaught JS exceptions while rendering',{scope,errors});
      }catch(error){
        const reason=errorText(error);
        report.errors.push({scope,error:reason});
        for(const id of ['UX-01','UX-02','UX-04','UX-05','UX-06','UX-07'])
          add(id,'BLOCKED','Browser checkpoint did not complete: '+reason,{scope});
      }finally{if(session)await session.context.close();}
    }
    const session=await start(1440,'dark','admin');
    try{
      const {page}=session;
      const goals=[
        {name:'invoice',query:'فاکتورهای فروش',expect:'فاکتورهای فروش'},
        {name:'purchase',query:'صورتحساب‌های خرید',expect:'صورتحساب‌های خرید'},
        {name:'receipts',query:'دریافت، پرداخت',expect:'دریافت، پرداخت و اقساط'},
        {name:'ledger',query:'حساب‌ها و دفترکل',expect:'حساب‌ها و دفترکل'},
        {name:'reports',query:'گزارش‌های مالی',expect:'گزارش‌های مالی'}
      ];
      for(const goal of goals){
        try{
          const label=await nav(page,goal.query);
          add('UX-03',label===goal.expect?'PASS':'FAIL',
            label===goal.expect?'Keyboard route within two navigation actions':
              'Unexpected route after keyboard search',{goal:goal.name,result:label,actions:2});
          add('UX-08',label===goal.expect?'PASS':'FAIL',
            label===goal.expect?'Global section keyboard route reached intended page':
              'Global section shortcut did not reach page',{goal:goal.name,result:label});
        }catch(error){
          add('UX-03','FAIL','Cannot reach novice target through keyboard route',{goal:goal.name,error:errorText(error)});
          add('UX-08','FAIL','Keyboard workflow failed',{goal:goal.name,error:errorText(error)});
        }
      }
      // Five actual keyboard interaction checkpoints, following keyboard
      // navigation. These do not assert persistence or ledger acceptance.
      for(const goal of [
        {name:'invoice-draft',query:'فاکتورهای فروش',selector:
          '.sac-ribbon-quick button[title*="باز کردن صفحه ورود اطلاعات فاکتور"]',activate:true},
        {name:'purchase-draft',query:'صورتحساب‌های خرید',selector:
          '.sac-invoice-editor input[dir="ltr"]:not([readonly])'},
        {name:'receipt-entry',query:'دریافت، پرداخت',selector:
          '.sac-body form input:not([readonly]):not([disabled]):not([type="hidden"])'},
        {name:'ledger-filter',query:'حساب‌ها و دفترکل',selector:
          '.sac-body input:not([readonly]):not([disabled]):not([type="hidden"])'},
        {name:'report-filter',query:'گزارش‌های مالی',selector:
          '.sac-body input:not([readonly]):not([disabled]):not([type="hidden"]),.sac-body select:not([disabled])'}
      ]){
        if(goal.name==='report-filter'&&!payload.view.financialReports){
          add('UX-08','BLOCKED',
            'Synthetic accounting_core view has no financialReports payload; report input controls are intentionally not rendered',
            {goal:goal.name,fixtureMissing:'view.financialReports'});
          continue;
        }
        try{
          await nav(page,goal.query);
          const result=await keyboardOperate(page,goal.selector,{activate:goal.activate});
          add('UX-08',result.success?'PASS':'FAIL',
            result.success?'Tab and keyboard operated a real workflow control':
              'Workflow control inaccessible or inoperable via keyboard',
            {goal:goal.name,...result});
          if(goal.activate&&result.success){
            // Cancel without editing; subsequent tasks start from clean UI.
            await nav(page,'داشبورد');
          }
        }catch(error){
          add('UX-08','FAIL','Keyboard workflow action failed',
            {goal:goal.name,error:errorText(error)});
        }
      }
      // Measured novice click paths: one immediate action for sales, at most
      // one ribbon category plus one command for the remaining four tasks.
      const novice=[
        {name:'invoice',group:'فاکتورها و سفارش‌ها',label:'فاکتورهای فروش'},
        {name:'purchase',group:'فاکتورها و سفارش‌ها',label:'صورتحساب‌های خرید'},
        {name:'receipts',group:'خزانه و پرداخت',label:'دریافت، پرداخت و اقساط'},
        {name:'reconciliation',group:'خزانه و پرداخت',label:'صندوق، بانک و مغایرت'},
        {name:'reports',group:'گزارش‌ها و سوابق',label:'گزارش‌های مالی'}
      ];
      for(const route of novice){
        try{
          await page.locator('.sac-ribbon-tabs').getByRole('button',
            {name:route.group,exact:true}).click({timeout:3500});
          await page.locator('.sac-ribbon-tools').getByRole('button',
            {name:route.label,exact:true}).click({timeout:3500});
          const actual=(await page.locator('.sac-header h1').textContent()).trim();
          add('UX-03',actual===route.label?'PASS':'FAIL',
            'Novice route via two visible menu actions',{goal:route.name,
              actions:2,result:actual});
        }catch(error){
          add('UX-03','FAIL','Novice navigation target not reachable in two actions',
            {goal:route.name,error:errorText(error)});
        }
      }
      const guide=await page.getByRole('button',{name:/راهنمای میانبر|راهنمای میان‌بر|راهنمای شروع|راهنمای کلید/}).count();
      add('UX-08',guide?'PASS':'MISSING',guide?'Keyboard guidance accessible':
        'Keyboard shortcut/help guide control not found');
      const searchLabels=await page.locator('[role=search]').evaluateAll(nodes=>nodes.map(x=>x.getAttribute('aria-label')||''));
      const recordSearch=searchLabels.some(label=>/سراسری|اسناد|رکورد|فاکتور.*شخص|جست‌وجوی اطلاعات/.test(label));
      add('UX-08',recordSearch?'PASS':'MISSING',recordSearch?
        'Search explicitly exposes record-level retrieval':'Only section jump search exposed; record-level search contract absent',
        {searchLabels});
      const routeIds=await page.locator('.sac-sidebar nav button').evaluateAll(buttons=>buttons.map(el=>({
        id:el.getAttribute('data-route-id')||el.getAttribute('data-ux-route')||
          el.getAttribute('data-accounting-tab')||el.getAttribute('data-tab-id')||
          el.getAttribute('aria-controls'),
        text:(el.textContent||'').trim().slice(0,35)})));
      const unique=routeIds.length&&routeIds.every(item=>item.id)&&
        new Set(routeIds.map(item=>item.id)).size===routeIds.length;
      add('UX-10',unique?'PASS':'MISSING',unique?'Navigation uses unique stable route identifiers':
        'Navigation lacks stable route identifiers; tests would rely on display strings',
        {total:routeIds.length,withoutId:routeIds.filter(item=>!item.id).slice(0,8)});
      try{
        await nav(page,'فاکتورهای فروش');
        const statuses=[];
        for(const item of [{id:'UX-DRAFT-002',kind:'draft'},
          {id:'UX-ISSUED-001',kind:'issued'}]){
          const row=page.locator('tr').filter({hasText:item.id}).first();
          await row.waitFor({state:'visible',timeout:3500});
          const text=(await row.innerText()).trim();
          const actions=await row.locator('button').allTextContents();
          const actionText=actions.join(' ');
          const valid=item.kind==='draft'?
            /تأیید/.test(actionText)&&/ویرایش/.test(actionText)&&!/تسویه|صدور سند/.test(actionText):
            /تسویه/.test(actionText)&&!/تأیید|ویرایش پیش‌نویس|صدور سند/.test(actionText);
          statuses.push({id:item.id,kind:item.kind,text:text.slice(0,160),actions,valid});
        }
        add('UX-09',statuses.every(x=>x.valid)?'PASS':'FAIL',
          'Document actions must match draft versus issued status without implicit posting',
          {statuses});
      }catch(error){
        add('UX-09','BLOCKED','Status-dependent actions not verified: '+errorText(error));
      }
      // Actual novice use: one quick action opens an editable invoice, then
      // changed data must remain if an attempted navigation is cancelled.
      await newInvoice(page);
      await page.locator('.sac-invoice-editor').waitFor();
      const rowInput=page.locator('.sac-invoice-editor input').filter({visible:true});
      const draftInput=page.locator('.sac-invoice-editor input[dir=ltr]').first();
      await draftInput.fill('UX-DRAFT-UNSAVED');
      const details=page.locator('.sac-invoice-editor details.sac-disclosure').first();
      if(await details.count())await details.locator('summary').click();
      const stillEdited=await draftInput.inputValue().catch(()=>null);
      add('UX-05',stillEdited==='UX-DRAFT-UNSAVED'?'PASS':'FAIL',
        'Expanding optional invoice details must not reset unsaved form values',
        {preserved:stillEdited});
      let dialogs=0;
      page.on('dialog',async dialog=>{dialogs++;await dialog.dismiss();});
      await nav(page,'گزارش‌های مالی');
      const preserved=await page.locator('.sac-invoice-editor input[dir=ltr]').first()
        .inputValue({timeout:900}).catch(()=>null);
      add('UX-09',dialogs>0&&preserved==='UX-DRAFT-UNSAVED'?'PASS':'FAIL',
        dialogs>0?'Unsaved form retains values when user rejects navigation':
          'No user-facing unsaved draft confirmation before leaving',
        {dialogs,preserved});
      add('UX-05',dialogs>0&&preserved==='UX-DRAFT-UNSAVED'?'PASS':'FAIL',
        'Unsaved invoice data must survive cancelled navigation',{dialogs,preserved});
      const noMutation=await page.evaluate(()=>window.__uxqaCalls.length===0);
      add('UX-09',noMutation?'PASS':'FAIL',
        noMutation?'Unsaved draft navigation did not invoke accounting mutations':
          'Unexpected accounting mutation attempt',{count:await page.evaluate(()=>window.__uxqaCalls.length)});
    }catch(error){
      report.errors.push({scope:'desktop/admin-workflows',error:errorText(error)});
      for(const id of ['UX-03','UX-08','UX-09','UX-10'])
        add(id,'BLOCKED','Keyboard/guide/draft scenario did not complete: '+errorText(error));
    }finally{await session.context.close();}
    for(const role of ['viewer','editor']){
      const restricted=await start(1440,'dark',role);
      try{
        const {page}=restricted;
        const newInvoice=await page.locator('.sac-ribbon-quick').getByRole('button',
          {name:/فاکتور جدید/}).count();
        add('UX-08',(role==='viewer'?newInvoice===0:newInvoice>0)?'PASS':'FAIL',
          'Quick-create permission matches synthetic UI capability',{role,newInvoice});
        await nav(page,'فاکتورهای فروش');
        const issue=await page.getByRole('button',{name:/^صدور فاکتور$|^تأیید فاکتور$/}).count();
        add('UX-08',issue===0?'PASS':'FAIL','Viewer/editor cannot issue or approve without management grant',
          {role,issueCount:issue});
        const guide=await page.getByRole('button',{name:/راهنمای میانبر|راهنمای میان‌بر|راهنمای شروع/}).count();
        add('UX-09',guide?'PASS':'MISSING',guide?'Beginner guide available to restricted role':
          'Guided novice workflow is not available in the restricted role',{role});
      }catch(error){
        add('UX-08','BLOCKED','Restricted role search/navigation scenario failed: '+errorText(error),{role});
      }finally{await restricted.context.close();}
    }
    report.limitations.push('Synthetic JS capability flags test UI only; server ACL, host persistence, and real user-role data filtering were not exercised.');
    report.limitations.push('axe incomplete and calculated foreground/background ambiguity require human review; no claim of full WCAG compliance.');
  }finally{
    if(browser)await browser.close();
    await new Promise(resolve=>server.httpServer.close(resolve));
  }
}

(async()=>{
  try{await main();}
  catch(error){report.errors.push({scope:'harness',error:errorText(error)});
    for(const id of ['UX-01','UX-02','UX-03','UX-04','UX-05','UX-06','UX-07','UX-08','UX-09','UX-10'])
      add(id,'BLOCKED','Harness could not fully execute: '+errorText(error));}
  finally{save();if(report.summary.overall!=='PASS')process.exitCode=1;}
})();
